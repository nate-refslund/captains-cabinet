"""Tests for the F0.5 binder wire — mechanical verdict capture at the poller.

All dependencies injected: no Telegram, no redis, no live ledger, no sends.
The ledger contract under test: superseding event emitted BEFORE any delivery;
delivery only on approve/edit; every failure mode degrades to handled=False
(passthrough preserved)."""
from __future__ import annotations

import json

import pytest

from framework.acting import loop
from framework.frontdoor import binder_wire


def _proposal(subject="thread:kristoffer", ts="2026-07-02T10:00:00Z"):
    return loop.proposal_event(
        actor={"kind": "officer", "id": "officer:cos"},
        lane="send-1to1-reply", subject=subject, ts=ts,
    )


def _pid(prop):
    return loop.proposal_id(prop)


def _quoted_for(prop):
    return f"📝 Draft reply to K (email) … Reply: send/edit/skip ·{_pid(prop)}·"


class Recorder:
    def __init__(self):
        self.emitted = []
        self.delivered = []

    def emit(self, **ev):
        self.emitted.append(ev)

    def deliver(self, pid, override_text=""):
        self.delivered.append((pid, override_text))
        return {"ok": True, "via": "email", "dest": "k@example.com"}


def _redis_with_draft(prop, draft="Hej Kristoffer, ..."):
    key = f"cabinet:draft:{_pid(prop)}"
    store = {key: json.dumps({"draft": draft, "person": "K", "channel": "email"})}
    return lambda k: store.get(k, "")


def test_no_pid_passthrough():
    r = binder_wire.handle_captain_update("hello there", "just a normal message",
                                          pending_source=lambda: [], deliver=None,
                                          emit=lambda **e: None)
    assert r["handled"] is False and r["reason"] == "no-pid"


def test_pid_but_no_pending_match_passthrough():
    prop = _proposal()
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [],  # nothing pending
        deliver=None, emit=lambda **e: None)
    assert r["handled"] is False and r["reason"] == "no-pending-match"


def test_approve_records_then_delivers_stored_draft():
    prop = _proposal()
    rec = Recorder()
    order = []
    def emit(**ev):
        order.append("emit"); rec.emit(**ev)
    def deliver(pid, override_text=""):
        order.append("deliver"); return rec.deliver(pid, override_text)
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=deliver, emit=emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] is True and r["status"] == "decided"
    assert r["primary"] == "approve" and r["verdict"] == "confirmed"
    # THE fail-closed ordering: ledger write strictly before delivery.
    assert order == ["emit", "deliver"]
    assert rec.delivered == [(_pid(prop), "")]
    assert "DELIVERED" in r["summary"]


def test_edit_delivers_captains_text():
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "edit: Min egen version her", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["primary"] == "edit" and r["verdict"] == "wrong"
    assert rec.delivered == [(_pid(prop), "Min egen version her")]


def test_skip_records_and_never_delivers():
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "skip: allerede besvaret", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["primary"] == "skip" and r["verdict"] == "unknown"
    assert rec.delivered == []
    assert "nothing delivered" in r["summary"]


def test_hold_downgrade_never_delivers():
    # loop FIX A: "ok men vent — send ikke endnu" downgrades approve -> none.
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "ok men vent - send ikke endnu", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] is True
    assert rec.delivered == []          # nothing left the machine
    assert r["status"] == "expired"     # policy/instruction-only path


def test_already_decided_is_idempotent_no_delivery():
    prop = _proposal()
    prop["proposal"]["decision"] = "approved"  # already resolved
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["status"] == "already-decided"
    assert rec.emitted == [] and rec.delivered == []


def test_emit_failure_blocks_delivery():
    # No ledger write ⇒ no delivery (fail-closed) — and passthrough preserved.
    prop = _proposal()
    rec = Recorder()
    def bad_emit(**ev):
        raise RuntimeError("ledger disk full")
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=bad_emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] is False and "error" in r["reason"]
    assert rec.delivered == []


def test_delivery_failure_still_records_verdict():
    prop = _proposal()
    rec = Recorder()
    def bad_deliver(pid, override_text=""):
        return {"ok": False, "error": "no email for K"}
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=bad_deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["verdict"] == "confirmed"
    assert "delivery FAILED" in r["summary"] and "do NOT re-record" in r["summary"]
    assert len(rec.emitted) == 1        # the verdict landed exactly once


def test_missing_stored_draft_still_records_approve_no_draft_dispatch():
    # Draft key expired (7d TTL): verdict records; deliver still attempts pid
    # (deliver_draft itself returns a clean error on a missing key in prod).
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "send", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=lambda k: "")
    assert r["handled"] and r["primary"] == "approve"
    assert rec.delivered == [(_pid(prop), "")]


def test_pid_extractable_from_reply_text_itself():
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        f"send ·{_pid(prop)}·", "",
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["primary"] == "approve"
