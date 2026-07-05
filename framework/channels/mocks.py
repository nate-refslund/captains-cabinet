"""Mock channel adapters [AX-5] — the arena/sim stand-ins. NO live sends, ever.

Every shipped adapter has a mock mirroring its exact contract surface —
name, capabilities, undo_contract, action types are read off the REAL class
so the pair cannot drift (a parity test pins it). Mocks record sends
in-memory and perform ZERO IO: no network, no subprocess, and — by default —
no event-ledger writes either, so an arena/evolution experiment can never
pollute the durable audit ledger or reach a human. This is the
evolution-engine spec invariant restated by the axes spec §4: "Every adapter
ships with a mock for the arena/sim harness (no live sends in experiments)";
harnesses bind these mocks, never the live adapters.

`journal=True` opts back into contract journaling for harnesses that sandbox
CABINET_EVENT_LOG_DIR and want full-fidelity event traces.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.channels.contract import ChannelAdapter, ChannelDeleteError
from framework.channels.outlook import OutlookAdapter
from framework.channels.slack import SlackAdapter
from framework.channels.teams import TeamsAdapter


class MockChannelAdapter(ChannelAdapter):
    """In-memory adapter base: records sends on `self.sent`, deletes on
    `self.deleted`, deterministic `mock-<name>-<n>` artifact ids. Subclasses
    (one per real adapter) carry the mirrored contract attributes."""

    def __init__(
        self,
        org_domains: Optional[Iterable[str]] = None,
        root: str | Path | None = None,
        actor: str = "sim",
        journal: bool = False,
    ) -> None:
        super().__init__(org_domains=org_domains, root=root, actor=actor)
        self._journal_enabled = bool(journal)
        self.sent = []      # type: list[dict[str, Any]]
        self.deleted = []   # type: list[str]

    def _journal(self, event_type: str, payload: "dict[str, Any]") -> None:
        # Ledger writes are OPT-IN for mocks (module docstring): a sim run
        # must not write the durable audit ledger unless the harness
        # sandboxed it and asked.
        if self._journal_enabled:
            super()._journal(event_type, payload)

    def _dispatch_send(self, recipient: str, body: str,
                       thread_id: Optional[str]) -> str:
        artifact_id = "mock-%s-%d" % (self.name, len(self.sent) + 1)
        self.sent.append({
            "artifact_id": artifact_id,
            "recipient": recipient,
            "body": body,
            "thread_id": thread_id,
            "audience": self.classify(recipient),
            "action_type": self.action_type_for(recipient),
        })
        return artifact_id

    def delete(self, artifact_id: str) -> bool:
        """Pseudo-undo, capability-gated exactly like the real adapters."""
        self._require_capability("delete")
        if artifact_id not in {s["artifact_id"] for s in self.sent}:
            raise ChannelDeleteError(
                "mock %s: unknown artifact %r" % (self.name, artifact_id))
        if artifact_id not in self.deleted:
            self.deleted.append(artifact_id)
        return True


class MockTeamsAdapter(MockChannelAdapter):
    name = TeamsAdapter.name
    capabilities = TeamsAdapter.capabilities
    undo_contract = TeamsAdapter.undo_contract
    internal_action_type = TeamsAdapter.internal_action_type
    external_action_type = TeamsAdapter.external_action_type


class MockOutlookAdapter(MockChannelAdapter):
    name = OutlookAdapter.name
    capabilities = OutlookAdapter.capabilities
    undo_contract = OutlookAdapter.undo_contract
    internal_action_type = OutlookAdapter.internal_action_type
    external_action_type = OutlookAdapter.external_action_type


class MockSlackAdapter(MockChannelAdapter):
    name = SlackAdapter.name
    capabilities = SlackAdapter.capabilities
    undo_contract = SlackAdapter.undo_contract
    internal_action_type = SlackAdapter.internal_action_type
    external_action_type = SlackAdapter.external_action_type


# channel name -> mock class (harness binding surface).
MOCKS_BY_CHANNEL = {
    MockTeamsAdapter.name: MockTeamsAdapter,
    MockOutlookAdapter.name: MockOutlookAdapter,
    MockSlackAdapter.name: MockSlackAdapter,
}
