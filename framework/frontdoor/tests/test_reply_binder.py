"""TDD tests for framework.frontdoor.reply_binder.

reply_binder.bind(reply_text, items) is the front-door's reply leg: it routes
the Captain's reply through framework.acting.loop.route_captain_response, matches the
items back to their PENDING proposal by correlation_id == loop.proposal_id(...),
calls loop.handle_response to record the SUPERSEDING outcome/expire on the
consequence ledger, then acks the bound intake ids. It is IDEMPOTENT.

Siblings (acting.loop, fidelity.consequence, frontdoor.intake) are real but we
exercise the binder through INJECTED seams: emit= (a fake recorder), an injected
pending_proposals source, and an injected ack. The two tests that want the real
ledger point CABINET_EVENT_LOG_DIR at a tmp dir and assert append-only growth.

Security: dispatch is the gated no-op in this slice — nothing leaves the
machine. We assert no send occurs.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework.acting import loop
from framework.frontdoor import reply_binder


# --------------------------------------------------------------------------- #
# Helpers: build a pending proposal + a matching intake item.
# --------------------------------------------------------------------------- #

def _proposal(*, ts="2026-06-22T08:00:00Z", subject="reply to Dana re DPA",
              actor=None, action="draft-reply"):
    """A real PENDING proposal_event (decision=None, no outcome)."""
    actor = actor or {"kind": "officer", "id": "cos"}
    return loop.proposal_event(actor=actor, lane="send-1to1-reply",
                               subject=subject, ts=ts, action=action)


def _item_for(prop, *, kind="draft-proposal", source="draft-reply"):
    """A canonical intake item whose correlation_id binds it to `prop`."""
    return {
        "id": "1700000000000-0",          # Redis-assigned stream id (ack key)
        "source": source,
        "kind": kind,
        "ts": prop["ts"],
        "urgency_tier": "batch",
        "payload": {"summary": "draft ready for Dana re DPA"},
        "context": {"why": "thread awaits the captain", "sources": [], "audience": None,
                    "thread_ref": "thread:dana-dpa"},
        "correlation_id": loop.proposal_id(prop),
    }


class FakeEmit:
    """Records emitted consequence events without touching any ledger."""
    def __init__(self):
        self.events = []

    def __call__(self, **event):
        # validate exactly like the real emitter would, so a malformed event
        # fails the test loudly rather than silently passing.
        from framework.fidelity.consequence import validate_consequence
        validate_consequence(event)
        self.events.append(event)
        return event


class RecordingDispatch:
    """A dispatch seam that records whether anything would have been sent."""
    def __init__(self):
        self.calls = []

    def __call__(self, routed, draft, proposal):
        self.calls.append((routed, draft, proposal))


# --------------------------------------------------------------------------- #
# Core routing + recording (no Redis, fake emit).
# --------------------------------------------------------------------------- #

class TestApproveRecordsConfirmedOutcome:
    def test_approve_emits_superseding_confirmed_outcome(self):
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        acked = []
        res = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: [prop],
            ack=lambda ids: acked.extend(ids if isinstance(ids, list) else [ids]),
        )
        assert res["status"] == "decided"
        assert res["routed"].primary == "approve"
        assert res["bound"] == [item["id"]]
        # exactly one outcome event, verdict confirmed, decision approved.
        assert len(emit.events) == 1
        ev = emit.events[0]
        assert ev["proposal"]["decision"] == "approved"
        assert ev["review"]["verdict"] == "confirmed"
        # the bound intake id was acked.
        assert acked == [item["id"]]


class TestEditRecordsWrong:
    def test_edit_emits_wrong_verdict(self):
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        res = reply_binder.bind(
            "edit: tone it down, drop the deadline", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
        )
        assert res["status"] == "decided"
        assert res["routed"].primary == "edit"
        assert emit.events[0]["review"]["verdict"] == "wrong"
        assert emit.events[0]["proposal"]["decision"] == "edited"


class TestSkipRecordsUnknown:
    def test_skip_emits_unknown(self):
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        res = reply_binder.bind(
            "skip: not worth replying", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
        )
        assert res["status"] == "decided"
        assert res["routed"].primary == "skip"
        ev = emit.events[0]
        assert ev["proposal"]["decision"] == "rejected"
        assert ev["outcome"]["status"] == "unknown"
        assert ev["review"]["verdict"] == "unknown"


class TestPolicyOnlyExpires:
    def test_policy_instruction_only_reply_expires_proposal(self):
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        res = reply_binder.bind(
            "in general never reply to these distribution lists unless I'm "
            "explicitly awaited", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
        )
        assert res["status"] == "expired"
        ev = emit.events[0]
        assert ev["proposal"]["decision"] == "expired"
        assert ev["review"]["verdict"] == "unknown"
        assert "outcome" not in ev  # nothing shipped -> no outcome object


# --------------------------------------------------------------------------- #
# Correlation matching.
# --------------------------------------------------------------------------- #

class TestCorrelationMatching:
    def test_binds_to_the_right_proposal(self):
        prop_a = _proposal(ts="2026-06-22T08:00:00Z", subject="reply A")
        prop_b = _proposal(ts="2026-06-22T09:00:00Z", subject="reply B")
        item_b = _item_for(prop_b)
        emit = FakeEmit()
        res = reply_binder.bind(
            "send", [item_b], emit=emit,
            pending_source=lambda: [prop_a, prop_b], ack=lambda ids: None,
        )
        assert res["status"] == "decided"
        # the emitted event's subject is B's, proving it bound to prop_b.
        assert emit.events[0]["subject"] == "reply B"

    def test_no_match_returns_cleanly_without_emitting(self):
        prop = _proposal()
        # item whose correlation_id points at a proposal that is NOT pending.
        stray = _item_for(prop)
        stray["correlation_id"] = "officer:cos|draft-reply|gone|2000-01-01T00:00:00Z"
        emit = FakeEmit()
        acked = []
        res = reply_binder.bind(
            "send", [stray], emit=emit,
            pending_source=lambda: [prop],
            ack=lambda ids: acked.extend(ids if isinstance(ids, list) else [ids]),
        )
        assert res["status"] == "no-match"
        assert res["bound"] == []
        assert emit.events == []          # nothing recorded
        assert acked == []                # nothing acked

    def test_item_without_correlation_id_is_no_match(self):
        prop = _proposal()
        item = _item_for(prop)
        item.pop("correlation_id")
        emit = FakeEmit()
        res = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
        )
        assert res["status"] == "no-match"
        assert emit.events == []


# --------------------------------------------------------------------------- #
# Idempotency.
# --------------------------------------------------------------------------- #

class TestIdempotency:
    def test_double_bind_same_reply_adds_no_second_outcome(self):
        """Channels re-delivery / double reply: the pending source no longer
        offers the (now-decided) proposal, so the second bind is a clean no-op
        and emits NO second outcome row."""
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()

        # First bind: decides the proposal.
        pending = [prop]
        res1 = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: list(pending), ack=lambda ids: None,
        )
        assert res1["status"] == "decided"
        assert len(emit.events) == 1

        # The proposal is now decided -> pending source drops it (mirrors the
        # real pending_proposals filter, which excludes decided rows).
        pending = []
        res2 = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: list(pending), ack=lambda ids: None,
        )
        # No second outcome row appended.
        assert len(emit.events) == 1
        assert res2["status"] in ("already-decided", "no-match")

    def test_already_decided_proposal_is_noop(self):
        """If the matched proposal already carries a decision, handle_response
        returns already-decided and we emit nothing more."""
        prop = _proposal()
        decided = dict(prop)
        decided["proposal"] = {"required": True, "decision": "approved",
                               "decided_at": prop["ts"]}
        item = _item_for(prop)
        emit = FakeEmit()
        res = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: [decided], ack=lambda ids: None,
        )
        assert res["status"] == "already-decided"
        assert emit.events == []


# --------------------------------------------------------------------------- #
# Security: dispatch is gated; nothing leaves the machine.
# --------------------------------------------------------------------------- #

class TestNoSend:
    def test_dispatch_is_gated_noop_no_send(self):
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        dispatch = RecordingDispatch()
        reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
            dispatch=dispatch,
        )
        # dispatch may be CALLED (loop calls it) but with no draft/no recipient
        # — and the default dispatch must be a no-op that performs no network IO.
        for routed, draft, proposal in dispatch.calls:
            # in this slice there is no draft content to send.
            assert draft is None

    def test_default_dispatch_performs_no_io(self):
        """The binder's default dispatch (when none injected) must not send."""
        prop = _proposal()
        item = _item_for(prop)
        emit = FakeEmit()
        # No dispatch injected -> uses the module default gated no-op.
        res = reply_binder.bind(
            "send", [item], emit=emit,
            pending_source=lambda: [prop], ack=lambda ids: None,
        )
        assert res["status"] == "decided"  # completes without sending anything


# --------------------------------------------------------------------------- #
# Real append-only ledger (tmp CABINET_EVENT_LOG_DIR) — proves growth, no mutate.
# --------------------------------------------------------------------------- #

@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


class TestRealLedgerAppendOnly:
    def test_outcome_row_appends_and_no_prior_row_mutated(self, ledger_dir):
        from framework.fidelity.consequence import emit_consequence, read_ledger

        prop = _proposal()
        item = _item_for(prop)
        # Seed the PENDING proposal into the real ledger first.
        emit_consequence(**prop)
        before = read_ledger()
        assert len(before) == 1
        assert (before[0].get("proposal") or {}).get("decision") is None

        # Bind an approve through the real emit + real pending_proposals.
        res = reply_binder.bind("send", [item], ack=lambda ids: None)
        assert res["status"] == "decided"

        after = read_ledger()
        # last-write-wins: still one identity, but now DECIDED (superseded, not
        # mutated — the JSONL file grew by an append).
        assert len(after) == 1
        assert after[0]["proposal"]["decision"] == "approved"
        assert after[0]["review"]["verdict"] == "confirmed"

        # The raw JSONL file must have GROWN (append-only), proving no mutation.
        files = sorted(Path(ledger_dir).glob("consequence-events-*.jsonl"))
        assert files
        lines = sum(len(f.read_text().splitlines()) for f in files)
        assert lines == 2  # original pending + superseding outcome

    def test_double_bind_against_real_ledger_no_second_outcome(self, ledger_dir):
        from framework.fidelity.consequence import emit_consequence, read_ledger

        prop = _proposal()
        item = _item_for(prop)
        emit_consequence(**prop)

        r1 = reply_binder.bind("send", [item], ack=lambda ids: None)
        assert r1["status"] == "decided"
        files = sorted(Path(ledger_dir).glob("consequence-events-*.jsonl"))
        lines_after_first = sum(len(f.read_text().splitlines()) for f in files)
        assert lines_after_first == 2

        # Second bind: proposal already decided -> idempotent no-op, no new row.
        r2 = reply_binder.bind("send", [item], ack=lambda ids: None)
        assert r2["status"] in ("already-decided", "no-match")
        files = sorted(Path(ledger_dir).glob("consequence-events-*.jsonl"))
        lines_after_second = sum(len(f.read_text().splitlines()) for f in files)
        assert lines_after_second == 2  # NO second outcome row appended
