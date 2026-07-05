"""Slack channel adapter [AX-5] — the greenfield real adapter (spec §4).

Stdlib-only (urllib) Slack Web API client behind an injectable transport
seam. Secret hygiene: SLACK_BOT_TOKEN is read from the environment AT CALL
TIME, never stored on the instance, never logged, and every error string is
scrubbed of the token value before it can reach a raised message or the
event ledger (wrapped errors are raised `from None` so no token-bearing
cause chain survives either).

The DEFAULT transport is hard-gated on `framework.env.allow_sends()` —
outside CABINET_ENV=runtime it refuses with ZERO network IO, the same
single-switch discipline as the front-door Telegram channel
(framework/frontdoor/channel.py). Arena/sim harnesses additionally bind
`framework.channels.mocks`, never this adapter (no live sends in
experiments — the evolution-engine invariant, spec §4). Tests inject a fake
transport and never reach the network.

Pseudo-undo: Slack messages are deletable → `undo_contract` is
`delete_window` (48h, the undo plane's receipt window); `delete()` calls
`chat.delete` with the channel + ts parsed back out of the artifact id
(`"<channel>:<ts>"`, exactly what chat.delete needs).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.channels.contract import (
    ChannelAdapter,
    ChannelConfigError,
    ChannelDeleteError,
    ChannelSendError,
    UndoContract,
)

SLACK_API_BASE = "https://slack.com/api/"

# 48h — the undo plane's receipt window (courses-of-action rule §2).
DELETE_WINDOW_SECONDS = 172800

_TIMEOUT_SECONDS = 15

# transport(method, payload, token) -> decoded Slack JSON response mapping
SlackTransport = Callable[[str, "dict[str, Any]", str], "dict[str, Any]"]


def _scrub(text: str, token: str) -> str:
    """Strip the bot token value from any outbound error string."""
    if token:
        text = text.replace(token, "[SLACK_BOT_TOKEN]")
    return text


def default_transport(method: str, payload: "dict[str, Any]",
                      token: str) -> "dict[str, Any]":
    """POST one Slack Web API method — LIVE, so gated on allow_sends().

    Outside CABINET_ENV=runtime this raises BEFORE any socket is opened
    (framework.env single switch): dev/test/build/sim sessions cannot reach
    the Slack API through this adapter, period.
    """
    from framework.env import allow_sends
    if not allow_sends():
        raise ChannelSendError(
            "slack: live sends are disabled outside CABINET_ENV=runtime "
            "(framework.env.allow_sends) — arena/sim must bind "
            "framework.channels.mocks instead")
    req = urllib.request.Request(
        SLACK_API_BASE + method,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


class SlackAdapter(ChannelAdapter):
    name = "slack"
    capabilities = frozenset({"send", "delete"})
    undo_contract = UndoContract.delete_window(DELETE_WINDOW_SECONDS)
    internal_action_type = "internal_message"
    external_action_type = "external_message"

    def __init__(
        self,
        transport: Optional[SlackTransport] = None,
        org_domains: Optional[Iterable[str]] = None,
        root: str | Path | None = None,
        actor: str = "system",
    ) -> None:
        super().__init__(org_domains=org_domains, root=root, actor=actor)
        self._transport = transport or default_transport

    @staticmethod
    def _token() -> str:
        """SLACK_BOT_TOKEN from the environment, at call time only — never
        persisted on the instance. The error names the VARIABLE, never a
        value (fail-closed before any network attempt)."""
        token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
        if not token:
            raise ChannelConfigError(
                "slack: SLACK_BOT_TOKEN is not set in the environment")
        return token

    def _call(self, method: str, payload: "dict[str, Any]",
              error_cls: "type") -> "dict[str, Any]":
        token = self._token()
        try:
            resp = self._transport(method, payload, token)
        except Exception as exc:
            # `from None`: the original exception (and its args) could carry
            # the token if a custom transport embedded it — scrub the text,
            # drop the cause chain.
            raise error_cls(
                "slack %s failed: %s: %s"
                % (method, type(exc).__name__, _scrub(str(exc), token))
            ) from None
        if not isinstance(resp, dict):
            raise error_cls(
                "slack %s returned a non-mapping response" % method)
        if resp.get("ok") is not True:
            raise error_cls(
                "slack %s error: %s"
                % (method,
                   _scrub(str(resp.get("error") or "unknown_error"), token)))
        return resp

    def _dispatch_send(self, recipient: str, body: str,
                       thread_id: Optional[str]) -> str:
        payload = {"channel": recipient, "text": body}
        if thread_id:
            payload["thread_ts"] = thread_id
        resp = self._call("chat.postMessage", payload, ChannelSendError)
        channel_id = resp.get("channel")
        ts = resp.get("ts")
        if not isinstance(channel_id, str) or not channel_id \
                or not isinstance(ts, str) or not ts:
            raise ChannelSendError(
                "slack chat.postMessage response carried no channel/ts — "
                "send outcome unknown, treated as failed")
        return "%s:%s" % (channel_id, ts)

    def delete(self, artifact_id: str) -> bool:
        """Pseudo-undo via chat.delete inside the declared delete window."""
        self._require_capability("delete")
        if not isinstance(artifact_id, str) or ":" not in artifact_id:
            raise ChannelDeleteError(
                "slack: artifact_id must be '<channel>:<ts>' (got %r)"
                % (artifact_id,))
        channel_id, ts = artifact_id.split(":", 1)
        if not channel_id or not ts:
            raise ChannelDeleteError(
                "slack: artifact_id must be '<channel>:<ts>' (got %r)"
                % (artifact_id,))
        self._call("chat.delete", {"channel": channel_id, "ts": ts},
                   ChannelDeleteError)
        return True
