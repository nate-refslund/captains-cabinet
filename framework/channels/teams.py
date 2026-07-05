"""Microsoft Teams channel adapter [AX-5] — transport-injectable, never direct.

This adapter NEVER calls the Microsoft Graph API (or any other Teams
endpoint) itself: per `.claude/rules/brain-bridge.md` the ONLY sanctioned
outbound path on personal instances is the brain MCP `queue_draft` tool
behind the Captain's approval gate — "NEVER call email or Teams APIs
directly (no Graph calls, no Make webhooks, no SMTP, no chat POSTs)". The
default transports are therefore `contract.queue_draft_stub` callables that
raise NotImplementedError pointing at that bridge; a deployment with a
different Captain-approved bridge injects its own `send_transport` /
`delete_transport` at construction. Refactoring the pre-axes Captain-specific
Teams path onto this contract = binding that bridge as the injected
transport (axes spec docs/plans/cabinet-axes-spec-2026-07-05.md §4).

Teams messages are deletable → pseudo-undo via `delete_window` (spec §4);
the 48h window matches the undo plane's receipt window
(.claude/rules/courses-of-action.md §2).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.channels.contract import (
    ChannelAdapter,
    ChannelDeleteError,
    UndoContract,
    queue_draft_stub,
)

# 48h — the undo plane's receipt window (courses-of-action rule §2).
DELETE_WINDOW_SECONDS = 172800

# send_transport(recipient, body, thread_id) -> artifact_id
SendTransport = Callable[[str, str, Optional[str]], str]
# delete_transport(artifact_id) -> truthy on success
DeleteTransport = Callable[[str], bool]


class TeamsAdapter(ChannelAdapter):
    name = "teams"
    capabilities = frozenset({"send", "delete"})
    undo_contract = UndoContract.delete_window(DELETE_WINDOW_SECONDS)
    internal_action_type = "internal_message"
    external_action_type = "external_message"

    def __init__(
        self,
        send_transport: Optional[SendTransport] = None,
        delete_transport: Optional[DeleteTransport] = None,
        org_domains: Optional[Iterable[str]] = None,
        root: str | Path | None = None,
        actor: str = "system",
    ) -> None:
        super().__init__(org_domains=org_domains, root=root, actor=actor)
        self._send_transport = send_transport or \
            queue_draft_stub(self.name, "send")
        self._delete_transport = delete_transport or \
            queue_draft_stub(self.name, "delete")

    def _dispatch_send(self, recipient: str, body: str,
                       thread_id: Optional[str]) -> str:
        return self._send_transport(recipient, body, thread_id)

    def delete(self, artifact_id: str) -> bool:
        """Pseudo-undo: delete a sent Teams message inside the delete window
        (via the injected transport — same never-direct rule as send)."""
        self._require_capability("delete")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ChannelDeleteError(
                "teams: artifact_id must be a non-empty string")
        return bool(self._delete_transport(artifact_id))
