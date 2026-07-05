"""AX-5 — sim mocks: exact contract parity with the real adapters, in-memory
only, no ledger writes by default (no live sends in experiments — the
evolution-engine invariant)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import contract as C
from framework.channels.mocks import (
    MOCKS_BY_CHANNEL,
    MockChannelAdapter,
    MockOutlookAdapter,
    MockSlackAdapter,
    MockTeamsAdapter,
)
from framework.channels.outlook import OutlookAdapter
from framework.channels.slack import SlackAdapter
from framework.channels.teams import TeamsAdapter
from framework.events.emitter import replay

ORG = frozenset({"acme.com"})

PAIRS = [
    (TeamsAdapter, MockTeamsAdapter),
    (OutlookAdapter, MockOutlookAdapter),
    (SlackAdapter, MockSlackAdapter),
]


@pytest.mark.parametrize("real,mock", PAIRS)
def test_mock_mirrors_the_real_contract_surface(real, mock):
    assert mock.name == real.name
    assert mock.capabilities == real.capabilities
    assert mock.undo_contract == real.undo_contract
    assert str(mock.undo_contract) == str(real.undo_contract)
    assert mock.internal_action_type == real.internal_action_type
    assert mock.external_action_type == real.external_action_type


def test_every_shipped_adapter_has_a_mock():
    assert set(MOCKS_BY_CHANNEL) == {r.name for r, _ in PAIRS}
    for real, mock in PAIRS:
        assert MOCKS_BY_CHANNEL[real.name] is mock


def test_mock_send_records_in_memory_with_deterministic_ids():
    m = MockTeamsAdapter(org_domains=ORG)
    a1 = m.send("bob@acme.com", "hello", thread_id="t-1")
    a2 = m.send("eve@other.com", "again")
    assert (a1, a2) == ("mock-teams-1", "mock-teams-2")
    assert [s["recipient"] for s in m.sent] == ["bob@acme.com", "eve@other.com"]
    assert m.sent[0]["audience"] == C.INTERNAL
    assert m.sent[0]["action_type"] == "internal_message"
    assert m.sent[1]["audience"] == C.EXTERNAL
    assert m.sent[1]["thread_id"] is None


def test_mock_sends_write_no_ledger_events_by_default():
    m = MockSlackAdapter(org_domains=ORG)
    m.send("C123", "hello")
    with pytest.raises(C.ChannelDeleteError):
        m.delete("mock-slack-999")
    assert replay(event_types=["outbox_dispatched", "outbox_failed"]) == []


def test_mock_journal_opt_in_restores_contract_journaling():
    m = MockSlackAdapter(org_domains=ORG, journal=True, actor="harness")
    m.send("C123", "hello")
    events = replay(event_types=["outbox_dispatched"])
    assert len(events) == 1
    assert events[0]["actor"] == "harness"
    assert events[0]["payload"]["kind"] == "channel_send"


def test_mock_delete_is_capability_gated_and_tracked():
    m = MockSlackAdapter(org_domains=ORG)
    art = m.send("C123", "hello")
    assert m.delete(art) is True
    assert m.deleted == [art]
    assert m.delete(art) is True  # idempotent pseudo-undo
    assert m.deleted == [art]
    with pytest.raises(C.ChannelDeleteError, match="unknown artifact"):
        m.delete("mock-slack-404")


def test_mock_outlook_refuses_delete_like_the_real_one():
    m = MockOutlookAdapter(org_domains=ORG)
    art = m.send("bob@acme.com", "hello")
    with pytest.raises(C.ChannelCapabilityError):
        m.delete(art)


def test_mock_base_requires_a_name_fail_closed():
    with pytest.raises(C.ChannelConfigError, match="name"):
        MockChannelAdapter(org_domains=ORG)


def test_mocks_module_imports_no_io_capable_modules():
    """The no-IO property, pinned: mocks.py may import only the package's own
    modules + typing/pathlib/sys plumbing — no urllib, sockets, subprocess,
    http, requests, anything."""
    allowed = {"sys", "pathlib", "typing", "__future__", "framework"}
    src = (_REPO_ROOT / "framework" / "channels" / "mocks.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= allowed, imported - allowed
