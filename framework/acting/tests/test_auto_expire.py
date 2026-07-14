"""FIX 2 — stale-OPEN draft proposals must AUTO-EXPIRE so they stop suppressing
future genuinely-new inbound.

Root cause this covers: when Ada replies to the counterparty HIMSELF, his reply
bypasses the approve gate, so the open proposal is never decided. It dangles
pending forever, and the recency-aware dedup then swallows every later message on
that thread (it compares new inbound against the OLD pending proposal's ts —
which is now older than everything). run_draft_lane._auto_expire_self_replied()
reconciles those proposals at the top of each run, BEFORE the open/decided maps
are read, so a just-expired proposal no longer appears in open_subject_ts() and a
genuinely-new message resurfaces.

These exercise the real ledger (isolated to a tmp dir via CABINET_EVENT_LOG_DIR),
the pure lane_dedup dedup helpers, and the real loop.expire_event / read_ledger
paths; only the screenpipe-backed self-reply detector (the bound source's
captain_replied_since — the T1 protocol name; the Flavor-A impl stays the
re-homed acting.nate_replied_since, reached via get_source()) is stubbed, since
its own logic is covered in test_acting.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# run_draft_lane reads these at import time; set harmless dummies BEFORE importing
# so the module loads in the unit suite without real Telegram credentials.
os.environ.setdefault("TELEGRAM_COS_TOKEN", "test-token")
os.environ.setdefault("CAPTAIN_TELEGRAM_ID", "0")

from framework.acting import run_draft_lane as rdl  # noqa: E402
from framework.acting import lane_dedup as ld  # noqa: E402
from framework.acting import loop  # noqa: E402
from framework.fidelity.consequence import emit_consequence, read_ledger  # noqa: E402
from framework.sources import get_source  # noqa: E402


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Isolate the consequence ledger to a tmp dir; no DB in tests."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


ACTOR = {"kind": "officer", "id": "cos"}


def _emit_open(subject, ts):
    """Write a real PENDING proposal to the ledger (what the lane emits when it
    presents a draft)."""
    return emit_consequence(
        ts=ts, actor=ACTOR, lane="send-1to1-reply", action="draft-reply",
        subject=subject, proposal={"required": True, "decision": None})


def _open_subjects():
    """The set of subjects with an OPEN proposal, read fresh from the ledger —
    the same map the lane's dedup uses to suppress a thread."""
    return set(ld.open_subject_ts(rows=read_ledger()).keys())


class TestAutoExpireSelfReplied:
    def test_self_reply_expires_open_proposal(self, monkeypatch):
        _emit_open("milo-archer", "2026-06-25T14:53:00+00:00")
        assert "milo-archer" in _open_subjects()  # open before the sweep
        # Ada replied himself after the proposal -> precise detector says True.
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: True)

        n = rdl._auto_expire_self_replied()

        assert n == 1
        # The proposal is now EXPIRED (decided), so it no longer suppresses the
        # thread: open_subject_ts drops it entirely.
        assert "milo-archer" not in _open_subjects()
        # And the superseding row is a clean expiry (decision='expired', no outcome).
        row = next(e for e in read_ledger() if e.get("subject") == "milo-archer")
        assert row["proposal"]["decision"] == "expired"
        assert "outcome" not in row
        assert row["review"]["verdict"] == "unknown"

    def test_expiry_unblocks_a_later_new_message(self, monkeypatch):
        # The end-to-end point of the fix: a proposal that auto-expires must stop
        # suppressing a genuinely-new inbound. Before expiry the open proposal
        # (14:53) would block a newer message via open_proposal_blocks; after
        # expiry the subject is gone from open_ts, so the new message re-presents.
        _emit_open("milo-archer", "2026-06-25T14:53:00+00:00")
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: True)
        rdl._auto_expire_self_replied()

        open_ts = ld.open_subject_ts(rows=read_ledger())
        newer = {"slug": "milo-archer",
                 "last": {"date": "2026-06-25T17:05:00+00:00", "text": "new!"}}
        # No open proposal remains for the subject -> the recency gate does not block.
        assert ld.open_proposal_blocks(newer, open_ts) is False

    def test_expire_decided_at_is_proposal_ts_not_now(self, monkeypatch):
        # Clock-poisoning regression (the Casper UAT-TEST-#3 miss): the
        # auto-expire's decided_at (the SUPPRESSION clock that
        # decided_subjects/already_handled read) MUST be the proposal's own ts —
        # the moment the draft was made — NOT the (hours-later) wall-clock moment
        # the sweep fires. Otherwise a genuinely-new inbound that arrived BEFORE
        # the sweep is wrongly judged already-handled and the lane never drafts it.
        #
        # Proposal created at 10:08. Ada replies himself -> it dangles. The sweep
        # fires now (well after 10:08) and expires it. We then assert the recorded
        # decided_at is 10:08 (the proposal ts), and prove the consequence via
        # already_handled: a 19:40 inbound (NEWER than 10:08) re-presents, while a
        # 09:00 inbound (OLDER than 10:08, covered by that proposal) stays handled.
        _emit_open("Casper", "2026-06-25T10:08:55+00:00")
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: True)

        rdl._auto_expire_self_replied()

        decided = ld.decided_subjects(rows=read_ledger())
        # decided_at is the PROPOSAL ts (10:08), NOT the wall-clock expiry moment.
        assert decided["Casper"] == ld.parse_dt("2026-06-25T10:08:55+00:00")

        # A genuinely-new inbound newer than the proposal ts -> NOT handled (drafts).
        new_thread = {"slug": "Casper", "person": "Casper",
                      "last": {"date": "2026-06-25T19:40:01+00:00",
                               "text": "UAT TEST #3", "source": "teams"}}
        assert ld.already_handled(new_thread, decided) is False

        # An older inbound (covered by that proposal) -> still handled (no
        # over-correction; the fix does not resurrect already-covered messages).
        old_thread = {"slug": "Casper", "person": "Casper",
                      "last": {"date": "2026-06-25T09:00:00+00:00",
                               "text": "older", "source": "teams"}}
        assert ld.already_handled(old_thread, decided) is True

    def test_no_self_reply_keeps_proposal_open(self, monkeypatch):
        # Detector says False (Ada has NOT replied since) and the proposal is
        # fresh -> the backstop does not fire -> it stays open (awaiting decision).
        _emit_open("lena", "2026-06-25T14:53:00+00:00")
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: False)
        # Pin "now" close to the proposal so the age backstop can't trip.
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 36.0)

        n = rdl._auto_expire_self_replied()

        assert n == 0
        assert "lena" in _open_subjects()

    def test_stale_proposal_expires_via_time_backstop(self, monkeypatch):
        # Detector can't tell (None) but the proposal is older than the backstop
        # window -> expire anyway so a stale draft never dangles forever.
        _emit_open("otto", "2026-06-20T09:00:00+00:00")  # days old
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: None)
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 36.0)

        n = rdl._auto_expire_self_replied()

        assert n == 1
        assert "otto" not in _open_subjects()

    def test_false_detection_blocks_time_backstop(self, monkeypatch):
        # Even a STALE proposal is kept open when the detector POSITIVELY says
        # 'Ada has not replied' (False) — he genuinely still owes a reply, so the
        # draft should remain his to decide, not be silently expired by age.
        _emit_open("otto", "2026-06-20T09:00:00+00:00")  # days old
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: False)
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 36.0)

        n = rdl._auto_expire_self_replied()

        assert n == 0
        assert "otto" in _open_subjects()

    def test_backstop_disabled_when_age_zero(self, monkeypatch):
        # PROPOSAL_MAX_AGE_H <= 0 disables the time backstop (precise-only): a
        # stale proposal with an undeterminable detector stays open.
        _emit_open("otto", "2026-06-20T09:00:00+00:00")
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: None)
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 0.0)

        n = rdl._auto_expire_self_replied()

        assert n == 0
        assert "otto" in _open_subjects()

    def test_decided_proposals_are_untouched(self, monkeypatch):
        # A DECIDED proposal is not "open" -> the sweep ignores it (no double
        # write); only PENDING proposals are reconciled here.
        emit_consequence(
            ts="2026-06-25T14:53:00+00:00", actor=ACTOR, lane="send-1to1-reply",
            action="draft-reply", subject="grace",
            proposal={"required": True, "decision": "approved",
                      "decided_at": "2026-06-25T15:00:00+00:00"},
            outcome={"status": "ok", "evidence": "shipped"},
            review={"verdict": "confirmed"})
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: True)

        n = rdl._auto_expire_self_replied()

        assert n == 0  # nothing OPEN to expire

    def test_no_open_proposals_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(get_source(), "captain_replied_since", lambda slug, when: True)
        assert rdl._auto_expire_self_replied() == 0

    def test_ledger_unreadable_is_safe(self, monkeypatch):
        # A ledger read failure must not break the drafting run -> expire nothing.
        def _boom():
            raise RuntimeError("ledger gone")
        monkeypatch.setattr(loop, "pending_proposals", _boom)
        assert rdl._auto_expire_self_replied() == 0
