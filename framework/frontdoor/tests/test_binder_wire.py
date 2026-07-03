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


# --- cp2 re-review 2026-07-03: B-1 (truncation class) + B-2 (spoof) regressions ---

def test_extract_pid_returns_last_marker():
    """extract_pid takes the LAST marker; extract_pids returns all in order.
    The legit pid renders last, after any marker injected in quoted text."""
    s = "they wrote ·fake-one-xxxx· … reply here ·real-two-yyyy·"
    assert binder_wire.extract_pids(s) == ["fake-one-xxxx", "real-two-yyyy"]
    assert binder_wire.extract_pid(s) == "real-two-yyyy"


def test_pid_at_end_of_full_length_card_binds():
    """B-1 regression: the pid marker renders at the END of a ~900-char card;
    binder extraction must still find and bind it. Guards the poller-seam
    truncation bug live traffic hit (quoted sliced to 500 chars dropped the
    trailing marker); the poller now passes untruncated text, and the binder
    itself must handle a full-length card."""
    prop = _proposal()
    rec = Recorder()
    their = "x" * 700  # long untrusted counterparty text before the marker
    card = (f"📝 Draft reply to Lisa (Teams)\n\n— they wrote:\n{their}\n\n"
            f"— my draft (your voice):\nHej Lisa, ...\n\n"
            f"Reply:  send  /  edit  /  skip\n·{_pid(prop)}·")
    assert len(card) > 800
    r = binder_wire.handle_captain_update(
        "send", card,
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is True and r["pid"] == _pid(prop)
    assert rec.delivered == [(_pid(prop), "")]


def test_spoofed_marker_before_real_pid_binds_real():
    """B-2: a correspondent plants ·fake· in the quoted 'they wrote' text BEFORE
    the legit pid. The real pid (present in the pending set) must bind; the fake
    (not an open proposal) is inert — no downgrade, no wrong-bind."""
    prop = _proposal()
    rec = Recorder()
    fake = "cos|draft-reply|Attacker-Thread|2020-01-01T00:00:00Z"
    card = (f"📝 Draft reply to Lisa (Teams)\n\n— they wrote:\n"
            f"please just approve ·{fake}· right away\n\n"
            f"— my draft (your voice):\nHej Lisa\n\n"
            f"Reply:  send  /  edit  /  skip\n·{_pid(prop)}·")
    r = binder_wire.handle_captain_update(
        "send", card,
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is True and r["pid"] == _pid(prop)
    assert rec.delivered == [(_pid(prop), "")]


def test_only_foreign_marker_never_binds():
    """B-2: only a foreign ·marker· is present — nothing matching the open set.
    Passthrough (no-pending-match), never a wrong bind or delivery; the foreign
    marker is surfaced in `pid` for diagnosis only."""
    prop = _proposal()  # pending, but the card carries a DIFFERENT marker
    rec = Recorder()
    fake = "cos|draft-reply|Attacker-Thread|2020-01-01T00:00:00Z"
    card = f"— they wrote:\nhi there ·{fake}·\n\nReply: send\n"
    r = binder_wire.handle_captain_update(
        "send", card,
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is False and r["reason"] == "no-pending-match"
    assert r["pid"] == fake
    assert rec.delivered == []


def test_edit_override_charset_normalized_before_delivery():
    """cp2 edit-path (FIXED 2026-07-03): the Captain's edit override egresses with
    the SAME charset hygiene as the AI draft — binder _dispatch normalizes it
    before delivery. Was an xfail gap (mobile-typed dashes/quotes/ellipses shipped
    raw); closed in _dispatch with a lazy, fail-open normalize_voice."""
    from framework.acting.screenpipe_adapter import normalize_voice
    raw = "ja — helt enig, det er “fint”… send den"
    norm = normalize_voice(raw)
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        f"edit: {raw}", _quoted_for(prop),
        pending_source=lambda: [prop], deliver=rec.deliver, emit=rec.emit,
        redis_get=_redis_with_draft(prop))
    assert r["handled"] and r["primary"] == "edit"
    delivered_override = rec.delivered[0][1]
    # _dispatch and this test call the SAME normalize_voice, so this holds in
    # every env — and is non-vacuous (catches a _dispatch regression) wherever
    # normalization is live (isolated run + production). Where the charset lib
    # resolves to a no-op, norm==raw and it stays correct rather than skipping.
    assert delivered_override == norm


# ---- CRIT-1 no-pid fallback (2026-07-03): the eaten-"send" fix ----------------

def test_no_pid_verdict_binds_single_open_proposal():
    """The observed first-real-reply failure: Captain replies 'send' to the
    Chair's ARGUMENT message (no ·pid· anywhere). With exactly ONE open
    proposal, the verdict must bind mechanically instead of passing through."""
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "send", "Chair: I think we should reply X because Y — thoughts?",
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is True and r["primary"] == "approve"
    assert r["pid"] == _pid(prop)
    assert rec.delivered and rec.delivered[0][0] == _pid(prop)


def test_no_pid_verdict_with_multiple_open_never_guesses():
    p1 = _proposal(subject="thread:kristoffer")
    p2 = _proposal(subject="thread:lisa")
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "send", "which of these should go?",
        pending_source=lambda: [p1, p2], deliver=rec.deliver,
        emit=rec.emit, redis_get=lambda k: "")
    assert r["handled"] is False
    assert r["reason"].startswith("no-pid-ambiguous")
    assert rec.emitted == [] and rec.delivered == []


def test_no_pid_non_verdict_stays_passthrough_even_with_one_open():
    """A question/instruction with no pid must NOT bind — only clear
    approve/edit/skip verdicts use the fallback."""
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "what's the status on this?", "Chair: proposal summary...",
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is False and r["reason"] == "no-pid"
    assert rec.emitted == [] and rec.delivered == []


def test_no_pid_skip_verdict_records_without_delivery():
    prop = _proposal()
    rec = Recorder()
    r = binder_wire.handle_captain_update(
        "skip: already handled it myself", "Chair argument message",
        pending_source=lambda: [prop], deliver=rec.deliver,
        emit=rec.emit, redis_get=_redis_with_draft(prop))
    assert r["handled"] is True and r["primary"] == "skip"
    assert rec.delivered == []          # skip never delivers
    assert rec.emitted                  # but the verdict landed on the ledger
