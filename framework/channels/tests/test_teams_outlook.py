"""AX-5 — Teams + Outlook adapters: transport-injectable, never-direct
(default = queue_draft bridge stub), email undo=none."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import contract as C
from framework.channels.outlook import OutlookAdapter
from framework.channels.teams import DELETE_WINDOW_SECONDS, TeamsAdapter
from framework.events.emitter import replay

ORG = frozenset({"acme.com"})


class RecordingTransport:
    def __init__(self, outcome="msg-1"):
        self.calls = []
        self.outcome = outcome

    def __call__(self, *args):
        self.calls.append(args)
        return self.outcome


# ---------------------------------------------------------------------------
# Default transport = the queue_draft bridge stub (never Graph/SMTP)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [TeamsAdapter, OutlookAdapter])
def test_default_send_transport_is_the_queue_draft_stub(cls):
    adapter = cls(org_domains=ORG)
    with pytest.raises(NotImplementedError) as ei:
        adapter.send("bob@acme.com", "hi")
    msg = str(ei.value)
    assert "queue_draft" in msg
    assert "brain-bridge.md" in msg
    # the refused attempt is still journaled (audit)
    failed = replay(event_types=["outbox_failed"])
    assert len(failed) == 1
    assert failed[0]["payload"]["channel"] == cls.name
    assert failed[0]["payload"]["error"].startswith("NotImplementedError")


def test_teams_default_delete_transport_is_the_stub_too():
    adapter = TeamsAdapter(org_domains=ORG)
    with pytest.raises(NotImplementedError, match="queue_draft"):
        adapter.delete("19:abc")


# ---------------------------------------------------------------------------
# Injected transports
# ---------------------------------------------------------------------------

def test_teams_injected_send_transport_dispatches_and_journals():
    transport = RecordingTransport(outcome="teams-msg-1")
    adapter = TeamsAdapter(send_transport=transport, org_domains=ORG,
                           actor="cos")
    art = adapter.send("bob@acme.com", "hello", thread_id="19:thread")
    assert art == "teams-msg-1"
    assert transport.calls == [("bob@acme.com", "hello", "19:thread")]
    events = replay(event_types=["outbox_dispatched"])
    assert len(events) == 1
    p = events[0]["payload"]
    assert p["channel"] == "teams"
    assert p["action_type"] == "internal_message"
    assert p["undo_contract"] == "delete_window(%d)" % DELETE_WINDOW_SECONDS

def test_outlook_injected_send_transport_stamps_email_action_types():
    transport = RecordingTransport(outcome="mail-1")
    adapter = OutlookAdapter(send_transport=transport, org_domains=ORG)
    adapter.send("bob@acme.com", "hello")
    adapter.send("eve@other.com", "hello")
    types = [e["payload"]["action_type"]
             for e in replay(event_types=["outbox_dispatched"])]
    assert types == ["internal_email", "external_email"]


def test_teams_delete_via_injected_transport():
    deletes = RecordingTransport(outcome=True)
    adapter = TeamsAdapter(send_transport=RecordingTransport(),
                           delete_transport=deletes, org_domains=ORG)
    assert adapter.delete("teams-msg-1") is True
    assert deletes.calls == [("teams-msg-1",)]


def test_teams_delete_rejects_empty_artifact():
    adapter = TeamsAdapter(delete_transport=RecordingTransport(),
                           org_domains=ORG)
    with pytest.raises(C.ChannelDeleteError):
        adapter.delete("")


# ---------------------------------------------------------------------------
# Contract surfaces
# ---------------------------------------------------------------------------

def test_teams_contract_surface():
    assert TeamsAdapter.name == "teams"
    assert TeamsAdapter.capabilities == frozenset({"send", "delete"})
    assert str(TeamsAdapter.undo_contract) == "delete_window(172800)"
    assert TeamsAdapter.undo_contract.undoable


def test_outlook_contract_surface_email_undo_none():
    assert OutlookAdapter.name == "outlook"
    assert OutlookAdapter.capabilities == frozenset({"send"})
    assert str(OutlookAdapter.undo_contract) == "none"
    assert not OutlookAdapter.undo_contract.undoable


def test_outlook_has_no_delete():
    adapter = OutlookAdapter(send_transport=RecordingTransport(),
                             org_domains=ORG)
    with pytest.raises(C.ChannelCapabilityError):
        adapter.delete("mail-1")


def test_teams_opaque_chat_ids_classify_external():
    # A Teams thread handle is not an org-domain email — conservative ceiling.
    adapter = TeamsAdapter(org_domains=ORG)
    assert adapter.classify("19:abc123@thread.tacv2") == C.EXTERNAL
    assert adapter.classify("meeting-chat-0042") == C.EXTERNAL
    assert adapter.classify("bob@acme.com") == C.INTERNAL
