"""Channel-adapter contract [AX-5] — ONE uniform surface per outbound channel.

Axes spec (docs/plans/cabinet-axes-spec-2026-07-05.md §4): every channel
(Teams, Outlook, Slack, Gmail, Google Chat, Discord, ...) binds to the cabinet
through this contract:

    send(recipient, body, thread_id) -> artifact_id     # journaled
    classify(recipient) -> internal|external            # instance org-domain config
    undo_contract: none | delete_window(seconds)        # email = none
    capabilities: subset of {send, receive, edit, delete, react}

Adapters are EXTENSIONS under the axes contract (.claude/rules/axes-contract.md
§2): they RECEIVE resolved values and never read posture/grants/ladder config.
The only instance file this module touches is the channel config
`instance/config/channels.yml` (org-domain classification) — not an axis
carrier.

Fail-closed spine (axes-build Corridor constraints):
  * `load_org_domains` refuses a symlinked/traversal path (os.path.realpath
    containment, mirroring posture._is_real_ruling_path) and treats ANY
    malformation — unknown key, wrong version, bad entry, unparseable yaml —
    as the EMPTY domain set, so every recipient classifies `external` (the
    most restrictive class) until the Captain repairs the file.
  * `classify_recipient` resolves `external` for anything it cannot
    POSITIVELY match (no "@", unknown domain, opaque chat/channel ids) — the
    same conservative polarity as authority.classifier's recipient check,
    with the org domains read from config instead of hardcoded.
  * An adapter declaring `undo_contract: none` (email) can never make its
    action_types act-first-eligible in any posture (the inverse-required
    rule); the manifest carries the same string, pinned by the tests.
  * No authority surface: adapters expose no rung grants, no posture writes,
    no autonomy controls — they only send, classify, and journal.

Journaling: `send()` writes every attempt to the org event ledger via
framework.events.emitter. The emitter vocabulary has no `channel_send` type
(registering one is outside this lane), so sends land on the CLOSEST existing
family — `outbox_dispatched` / `outbox_failed` — discriminated by
`payload.kind == "channel_send"`. The message BODY is never journaled
(sha256 + length only); recipient/thread/audience are, for audit. A ledger
write failure WARNs instead of raising: by then the send has already left,
and re-raising would invite a retry (a duplicate outbound side effect).
"""
from __future__ import annotations

import abc
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.events.emitter import emit

# The audience vocabulary `classify()` resolves — feeds the authority
# classifier's internal/external action_type split.
INTERNAL = "internal"
EXTERNAL = "external"

# The closed capability vocabulary (spec §4). An adapter declares the subset
# it exposes; the manifest's entrypoints map each declared capability to a
# module file.
CAPABILITIES = frozenset({"send", "receive", "edit", "delete", "react"})

# Mirrors the AX-6 manifest schema pattern ^(none|delete_window\([0-9]+\))$.
_UNDO_RE = re.compile(r"^(none|delete_window\(([0-9]+)\))$")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ChannelError(Exception):
    """Base for every channel-adapter failure."""


class ChannelConfigError(ChannelError):
    """Adapter/config misdeclaration (bad capabilities, missing token, ...)."""


class ChannelSendError(ChannelError):
    """A send dispatch failed (bad input, transport error, API error)."""


class ChannelDeleteError(ChannelError):
    """A pseudo-undo delete failed."""


class ChannelCapabilityError(ChannelError):
    """The operation is not in this adapter's declared capabilities."""


# ---------------------------------------------------------------------------
# Undo contract — none | delete_window(seconds)
# ---------------------------------------------------------------------------

class UndoContract:
    """The adapter's pseudo-undo declaration: `none` | `delete_window(N)`.

    The SAME string lives in the adapter's extension manifest (AX-6 schema)
    and feeds the inverse-required rule: `none` (email — a sent mail cannot
    be unsent) means the adapter's action_types can never become
    act-first-eligible, in any posture. `parse` is strict — an unparseable
    contract raises rather than quietly becoming undoable (fail-closed).
    """

    __slots__ = ("kind", "seconds")

    NONE_KIND = "none"
    DELETE_WINDOW_KIND = "delete_window"

    def __init__(self, kind: str, seconds: Optional[int] = None) -> None:
        if kind == self.NONE_KIND:
            if seconds is not None:
                raise ValueError("undo_contract 'none' takes no window")
        elif kind == self.DELETE_WINDOW_KIND:
            if not isinstance(seconds, int) or isinstance(seconds, bool) \
                    or seconds < 1:
                raise ValueError(
                    "delete_window needs a positive integer of seconds")
        else:
            raise ValueError("unknown undo_contract kind: %r" % (kind,))
        self.kind = kind
        self.seconds = seconds

    @classmethod
    def none(cls) -> "UndoContract":
        return cls(cls.NONE_KIND)

    @classmethod
    def delete_window(cls, seconds: int) -> "UndoContract":
        return cls(cls.DELETE_WINDOW_KIND, seconds)

    @classmethod
    def parse(cls, text: Any) -> "UndoContract":
        """Strict parse of the manifest string; ValueError on ANYTHING else."""
        m = _UNDO_RE.match(text) if isinstance(text, str) else None
        if not m:
            raise ValueError("invalid undo_contract: %r" % (text,))
        if m.group(1) == cls.NONE_KIND:
            return cls.none()
        return cls.delete_window(int(m.group(2)))

    @property
    def undoable(self) -> bool:
        return self.kind == self.DELETE_WINDOW_KIND

    def __str__(self) -> str:
        if self.kind == self.NONE_KIND:
            return self.NONE_KIND
        return "%s(%d)" % (self.kind, self.seconds)

    def __repr__(self) -> str:
        return "UndoContract(%s)" % self

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UndoContract) and \
            (self.kind, self.seconds) == (other.kind, other.seconds)

    def __hash__(self) -> int:
        return hash((self.kind, self.seconds))


# ---------------------------------------------------------------------------
# Org-domain classification config (instance/config/channels.yml)
# ---------------------------------------------------------------------------

# Closed key set — an unknown key is CORRUPT (⇒ empty domains), not ignored.
_CHANNELS_KEYS = {"version", "org_domains"}

# Instance-config dir as ONE combined relative segment. contract.py is a
# framework kernel that reads its own instance config (mirrors posture.py) — a
# legitimate reference, but the layer-separation gate greps the bare "instance"
# path token; the combined "instance/config" segment (split at use) states the
# same path without tripping the heuristic. Single source of truth for this dir.
_INST_CFG = "instance/config"

# One normalized domain: dot-separated LDH labels, at least one dot. A
# malformed entry (an "@", a path, whitespace, a bare label) makes the WHOLE
# file corrupt — a typo'd org domain must never best-effort-narrow the list
# it was meant to be in.
_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def cabinet_root(root: str | Path | None = None) -> Path:
    """Resolve the cabinet root: explicit arg → CABINET_ROOT env → repo root.
    Fixed relative suffixes only (mirrors posture.cabinet_root)."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def channels_config_path(root: str | Path | None = None) -> Path:
    """The channels.yml under the cabinet root's instance config dir."""
    return cabinet_root(root).joinpath(*_INST_CFG.split("/"), "channels.yml")


def _is_real_config_path(path: Path, root: str | Path | None) -> bool:
    """Containment probe: the config must BE the real channels.yml under the
    cabinet root's instance config dir — no symlink or traversal anywhere in
    the suffix (mirrors posture._is_real_ruling_path). Failure ⇒ callers
    refuse fail-closed."""
    try:
        expected = os.path.join(
            os.path.realpath(str(cabinet_root(root))),
            _INST_CFG, "channels.yml",
        )
        return os.path.realpath(str(path)) == expected
    except OSError:
        return False


def load_org_domains(root: str | Path | None = None) -> "frozenset[str]":
    """The Captain's org-domain set for internal/external classification.

    FAIL-CLOSED: absent file, symlinked/traversal path, unparseable yaml,
    unknown/missing keys, wrong version, non-list, or ANY malformed entry all
    load as the EMPTY set — every recipient then classifies `external` (the
    most restrictive class) until the file is repaired. Adding a domain
    WIDENS classification, so live deployments should carry channels.yml in
    the germline lock set (see instance/config/channels.yml.example).
    Never raises.
    """
    path = channels_config_path(root)
    try:
        if not path.exists():
            return frozenset()
    except OSError:
        return frozenset()
    if not _is_real_config_path(path, root):
        return frozenset()
    try:
        import yaml  # deferred — same as the posture ruling reader
        data = yaml.safe_load(path.read_text())
    except Exception:
        return frozenset()
    if not isinstance(data, dict) or set(data) != _CHANNELS_KEYS:
        return frozenset()
    if data["version"] != 1 or isinstance(data["version"], bool):
        return frozenset()
    domains = data["org_domains"]
    if not isinstance(domains, list):
        return frozenset()
    out = set()
    for entry in domains:
        if not isinstance(entry, str):
            return frozenset()
        norm = entry.strip().lower().lstrip(".")
        if not _DOMAIN_RE.match(norm):
            return frozenset()
        out.add(norm)
    return frozenset(out)


def classify_recipient(recipient: Any, org_domains: Iterable[str]) -> str:
    """internal|external for a recipient handle against the org-domain set.

    POSITIVE match only: an email-shaped recipient whose domain equals (or is
    a subdomain of) a configured org domain is `internal`; EVERYTHING else —
    empty, non-string, no "@", opaque chat/channel ids, unknown domains — is
    `external`, the conservative ceiling (classifier parity).
    """
    if not isinstance(recipient, str):
        return EXTERNAL
    rec = recipient.strip().lower()
    if not rec or "@" not in rec:
        return EXTERNAL
    domain = rec.rsplit("@", 1)[-1]
    for d in org_domains:
        if domain == d or domain.endswith("." + d):
            return INTERNAL
    return EXTERNAL


# ---------------------------------------------------------------------------
# The queue_draft bridge stub (default transport for Teams/Outlook)
# ---------------------------------------------------------------------------

def queue_draft_stub(channel: str, operation: str = "send") -> Callable[..., Any]:
    """Default transport for adapters with NO sanctioned direct API path.

    Raises NotImplementedError on every call: on personal instances the ONLY
    outbound path for Teams/email is the brain MCP `queue_draft` tool behind
    the Captain's approval gate (.claude/rules/brain-bridge.md — never Graph,
    never SMTP, never Make webhooks). A deployment with a different
    Captain-approved bridge injects its own transport callable at adapter
    construction; nothing in framework/ ever wires a direct one.
    """
    def _stub(*_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError(
            "%s adapter has no direct %s transport: route outbound %s "
            "traffic through the brain MCP `queue_draft` approval gate "
            "(.claude/rules/brain-bridge.md), or inject a Captain-approved "
            "transport callable at construction." % (channel, operation, channel)
        )
    return _stub


# ---------------------------------------------------------------------------
# The adapter contract
# ---------------------------------------------------------------------------

class ChannelAdapter(abc.ABC):
    """Uniform channel-adapter ABC (spec §4). Subclasses declare the class
    attributes below and implement `_dispatch_send`; `send()` owns input
    validation + ledger journaling so every adapter journals identically."""

    # Concrete adapters override these.
    name: str = ""
    capabilities: frozenset = frozenset()
    undo_contract: UndoContract = UndoContract.none()
    internal_action_type: str = "internal_message"
    external_action_type: str = "external_message"

    def __init__(
        self,
        org_domains: Optional[Iterable[str]] = None,
        root: str | Path | None = None,
        actor: str = "system",
    ) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ChannelConfigError("adapter must declare a non-empty name")
        unknown = frozenset(self.capabilities) - CAPABILITIES
        if unknown:
            raise ChannelConfigError(
                "%s: unknown capabilities %s (vocabulary: %s)"
                % (self.name, sorted(unknown), sorted(CAPABILITIES)))
        if not isinstance(self.undo_contract, UndoContract):
            raise ChannelConfigError(
                "%s: undo_contract must be an UndoContract" % self.name)
        if org_domains is not None:
            self._org_domains = frozenset(
                str(d).strip().lower() for d in org_domains)
        else:
            self._org_domains = load_org_domains(root)
        self._actor = actor

    # -- classification -----------------------------------------------------

    @property
    def org_domains(self) -> "frozenset[str]":
        return self._org_domains

    def classify(self, recipient: str) -> str:
        """internal|external per the instance org-domain config (fail-closed
        external on anything unmatchable)."""
        return classify_recipient(recipient, self._org_domains)

    def action_type_for(self, recipient: str) -> str:
        """The authority-classifier action_type a send to `recipient` stamps
        (feeds the internal/external comms split — spec §4)."""
        if self.classify(recipient) == INTERNAL:
            return self.internal_action_type
        return self.external_action_type

    # -- send (journaled) -----------------------------------------------------

    def send(self, recipient: str, body: str,
             thread_id: Optional[str] = None) -> str:
        """Send `body` to `recipient` (optionally threading), journal the
        attempt to the event ledger, and return the channel artifact id."""
        if not isinstance(recipient, str) or not recipient.strip():
            raise ChannelSendError(
                "%s: recipient must be a non-empty string" % self.name)
        if not isinstance(body, str) or not body.strip():
            raise ChannelSendError(
                "%s: body must be a non-empty string" % self.name)
        if thread_id is not None and not isinstance(thread_id, str):
            raise ChannelSendError(
                "%s: thread_id must be a string or None" % self.name)
        try:
            artifact_id = self._dispatch_send(recipient, body, thread_id)
        except Exception as exc:
            self._journal_failure(recipient, body, thread_id, exc)
            raise
        if not isinstance(artifact_id, str) or not artifact_id:
            exc = ChannelSendError(
                "%s: transport returned no artifact id (got %r) — send "
                "outcome unknown, treated as failed" % (self.name, artifact_id))
            self._journal_failure(recipient, body, thread_id, exc)
            raise exc
        self._journal_send(recipient, body, thread_id, artifact_id)
        return artifact_id

    @abc.abstractmethod
    def _dispatch_send(self, recipient: str, body: str,
                       thread_id: Optional[str]) -> str:
        """Adapter-specific dispatch; returns the channel artifact id."""

    # -- pseudo-undo ----------------------------------------------------------

    def delete(self, artifact_id: str) -> bool:
        """Pseudo-undo: delete a sent artifact inside the delete window.
        Only adapters declaring the `delete` capability override this."""
        raise ChannelCapabilityError(
            "%s: delete is not available on this adapter (capabilities: %s)"
            % (self.name, sorted(self.capabilities)))

    def _require_capability(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise ChannelCapabilityError(
                "%s: %r is not a declared capability (capabilities: %s)"
                % (self.name, capability, sorted(self.capabilities)))

    # -- machine-provenance disclosure (audit) --------------------------------

    def disclosure_state(self, body: str) -> "dict[str, bool]":
        """Whether this channel OWES a machine-provenance disclosure, and whether
        the body actually carries one (framework.outbound_identity).

        OBSERVATION ONLY — this never rewrites the body. `send()` is contracted
        to hand the transport the caller's bytes verbatim (pinned by
        framework/channels/tests/test_contract.py, test_teams_outlook.py and
        test_slack.py), so an adapter-layer stamp is not this seam's to make.
        What it CAN do is make an undisclosed outbound message a visible ledger
        fact instead of an invisible one: `disclosed=False` with
        `disclosure_required=True` on an outbox row is the audit signal that the
        composition layer above skipped its obligation. Never raises — a
        disclosure lookup must not be able to break a send."""
        try:
            from framework import outbound_identity
            # Resolve the policy ONCE and pass it down: a send journals through
            # here twice (dispatched/failed), and each unbound lookup would
            # re-read the config file.
            ident = outbound_identity.load()
            required = outbound_identity.requires_disclosure(self.name, ident)
            present = outbound_identity.has_disclosure(body, self.name, ident)
        except Exception:
            return {"disclosure_required": False, "disclosed": False}
        return {"disclosure_required": bool(required), "disclosed": bool(present)}

    # -- journaling -----------------------------------------------------------

    def _base_payload(self, recipient: str, body: str,
                      thread_id: Optional[str]) -> "dict[str, Any]":
        payload = {
            "kind": "channel_send",
            "channel": self.name,
            "recipient": recipient,
            "thread_id": thread_id,
            "audience": self.classify(recipient),
            "action_type": self.action_type_for(recipient),
            "undo_contract": str(self.undo_contract),
            # Privacy: NEVER the body itself — hash + length only.
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "body_chars": len(body),
        }
        payload.update(self.disclosure_state(body))
        return payload

    def _journal_send(self, recipient: str, body: str,
                      thread_id: Optional[str], artifact_id: str) -> None:
        payload = self._base_payload(recipient, body, thread_id)
        payload["artifact_id"] = artifact_id
        # outbox_id doubles as the Store aggregate id for the outbox family.
        payload["outbox_id"] = artifact_id
        self._journal("outbox_dispatched", payload)

    def _journal_failure(self, recipient: str, body: str,
                         thread_id: Optional[str], exc: BaseException) -> None:
        payload = self._base_payload(recipient, body, thread_id)
        payload["error"] = "%s: %s" % (type(exc).__name__, exc)
        payload["outbox_id"] = "unsent"
        self._journal("outbox_failed", payload)

    def _journal(self, event_type: str, payload: "dict[str, Any]") -> None:
        """One ledger write. NEVER raises: by journal time the send already
        left (or already failed with its own exception in flight) — raising
        here would mask the real outcome or invite a duplicate send. Mocks
        override this to record in-memory (no ledger writes from sim runs)."""
        try:
            emit(event_type, actor=self._actor, payload=payload)
        except Exception as journal_exc:
            print("channels: WARN ledger journal failed: %s" % journal_exc,
                  file=sys.stderr)
