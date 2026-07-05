"""Outlook (email) channel adapter [AX-5] — transport-injectable, never direct.

This adapter NEVER calls Microsoft Graph or SMTP itself: per
`.claude/rules/brain-bridge.md` the ONLY sanctioned outbound path on personal
instances is the brain MCP `queue_draft` tool behind the Captain's approval
gate — "NEVER call email or Teams APIs directly (no Graph calls, no Make
webhooks, no SMTP, no chat POSTs)". The default transport is therefore
`contract.queue_draft_stub`, raising NotImplementedError pointing at that
bridge; a deployment with a different Captain-approved bridge injects its own
`send_transport` at construction. Refactoring the pre-axes Captain-specific
Outlook path onto this contract = binding that bridge as the injected
transport (axes spec docs/plans/cabinet-axes-spec-2026-07-05.md §4).

Email cannot be unsent: `undo_contract` is NONE (spec §4 — "email = none"),
so under the inverse-required rule this adapter's action_types can never
become act-first-eligible in any posture; external mail stays per-item
Captain-approved (ACT-AND-DRAFT ruling). No `delete` capability is declared.
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
    UndoContract,
    queue_draft_stub,
)

# send_transport(recipient, body, thread_id) -> artifact_id
SendTransport = Callable[[str, str, Optional[str]], str]


class OutlookAdapter(ChannelAdapter):
    name = "outlook"
    capabilities = frozenset({"send"})
    undo_contract = UndoContract.none()
    internal_action_type = "internal_email"
    external_action_type = "external_email"

    def __init__(
        self,
        send_transport: Optional[SendTransport] = None,
        org_domains: Optional[Iterable[str]] = None,
        root: str | Path | None = None,
        actor: str = "system",
    ) -> None:
        super().__init__(org_domains=org_domains, root=root, actor=actor)
        self._send_transport = send_transport or \
            queue_draft_stub(self.name, "send")

    def _dispatch_send(self, recipient: str, body: str,
                       thread_id: Optional[str]) -> str:
        return self._send_transport(recipient, body, thread_id)
