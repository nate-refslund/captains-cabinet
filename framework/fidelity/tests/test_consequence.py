"""Tests for the F0 consequence-event emitter + ledger reader."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity.consequence import (
    SCHEMA,
    ConsequenceValidationError,
    validate_consequence,
    emit_consequence,
    _consequence_log_dir,
)


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Isolate the consequence ledger to a tmp dir; no DB in tests."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


def _act_event(**overrides):
    """A minimal valid 'Act'-phase consequence event (gate pending)."""
    base = {
        "ts": "2026-06-18T08:00:00+00:00",
        "actor": {"kind": "officer", "id": "cos"},
        "lane": "polads",
        "action": "drafted-reply",
        "subject": "thread-abc",
        "refs": ["msg-1"],
        "proposal": {"required": True, "decision": None, "decided_at": None},
    }
    base.update(overrides)
    return base


class TestSchemaLoad:
    def test_schema_is_the_real_consequence_schema(self):
        assert SCHEMA["title"] == "Consequence Event"
        assert SCHEMA["required"] == ["ts", "actor", "lane", "action", "subject"]
        assert SCHEMA["additionalProperties"] is False

    def test_log_dir_honors_env(self, event_log_dir):
        assert _consequence_log_dir() == Path(os.environ["CABINET_EVENT_LOG_DIR"])


class TestValidateStructure:
    def test_minimal_act_event_passes(self):
        assert validate_consequence(_act_event()) is None

    def test_full_lifecycle_event_passes(self):
        ev = _act_event(
            proposal={"required": True, "decision": "approved",
                      "decided_at": "2026-06-18T08:05:00+00:00"},
            outcome={"status": "ok", "evidence": "sent-msg-xyz"},
            review={"verdict": "confirmed", "reviewed_at":
                    "2026-06-18T09:00:00+00:00", "lesson_ref": None},
        )
        assert validate_consequence(ev) is None

    def test_lane_may_be_null(self):
        assert validate_consequence(_act_event(lane=None)) is None

    @pytest.mark.parametrize("missing", ["ts", "actor", "lane", "action", "subject"])
    def test_missing_required_field_raises(self, missing):
        ev = _act_event()
        del ev[missing]
        with pytest.raises(ConsequenceValidationError, match=missing):
            validate_consequence(ev)

    def test_unknown_top_level_field_raises(self):
        with pytest.raises(ConsequenceValidationError, match="additional"):
            validate_consequence(_act_event(surprise="boom"))

    def test_unknown_actor_field_raises(self):
        ev = _act_event(actor={"kind": "officer", "id": "cos", "rank": "admiral"})
        with pytest.raises(ConsequenceValidationError, match="actor"):
            validate_consequence(ev)

    def test_unknown_proposal_field_raises(self):
        ev = _act_event(proposal={"required": True, "veto": False})
        with pytest.raises(ConsequenceValidationError, match="proposal"):
            validate_consequence(ev)

    def test_bad_actor_kind_raises(self):
        ev = _act_event(actor={"kind": "alien", "id": "ufo"})
        with pytest.raises(ConsequenceValidationError, match="actor.kind"):
            validate_consequence(ev)

    def test_bad_proposal_decision_raises(self):
        ev = _act_event(proposal={"required": True, "decision": "aproved"})
        with pytest.raises(ConsequenceValidationError, match="proposal.decision"):
            validate_consequence(ev)

    def test_bad_outcome_status_raises(self):
        ev = _act_event(outcome={"status": "broke", "evidence": "x"})
        with pytest.raises(ConsequenceValidationError, match="outcome.status"):
            validate_consequence(ev)

    def test_bad_review_verdict_raises(self):
        ev = _act_event(review={"verdict": "right"})
        with pytest.raises(ConsequenceValidationError, match="review.verdict"):
            validate_consequence(ev)


class TestInvariants:
    def test_evidence_must_be_null_when_unknown(self):
        ev = _act_event(outcome={"status": "unknown", "evidence": "leaked"})
        with pytest.raises(ConsequenceValidationError, match="evidence"):
            validate_consequence(ev)

    def test_evidence_required_when_ok(self):
        ev = _act_event(outcome={"status": "ok", "evidence": None})
        with pytest.raises(ConsequenceValidationError, match="evidence"):
            validate_consequence(ev)

    def test_evidence_required_when_failed(self):
        ev = _act_event(outcome={"status": "failed"})
        with pytest.raises(ConsequenceValidationError, match="evidence"):
            validate_consequence(ev)

    def test_unknown_outcome_with_null_evidence_passes(self):
        ev = _act_event(outcome={"status": "unknown", "evidence": None})
        assert validate_consequence(ev) is None

    def test_decision_must_be_null_when_not_required(self):
        ev = _act_event(proposal={"required": False, "decision": "approved"})
        with pytest.raises(ConsequenceValidationError, match="decision"):
            validate_consequence(ev)

    def test_below_bar_action_required_false_passes(self):
        ev = _act_event(proposal={"required": False, "decision": None})
        assert validate_consequence(ev) is None

    def test_lesson_ref_only_when_wrong(self):
        ev = _act_event(review={"verdict": "confirmed",
                                "lesson_ref": "lessons.md#anchor"})
        with pytest.raises(ConsequenceValidationError, match="lesson_ref"):
            validate_consequence(ev)

    def test_lesson_ref_allowed_when_wrong(self):
        ev = _act_event(review={"verdict": "wrong",
                                "lesson_ref": "lessons.md#anchor"})
        assert validate_consequence(ev) is None


class TestEmit:
    def test_emit_returns_validated_event(self, event_log_dir):
        ev = emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads",
            action="drafted-reply",
            subject="thread-abc",
            refs=["msg-1"],
            proposal={"required": True, "decision": None, "decided_at": None},
        )
        assert ev["action"] == "drafted-reply"
        assert ev["actor"] == {"kind": "officer", "id": "cos"}

    def test_emit_defaults_refs_to_empty_list(self, event_log_dir):
        ev = emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "pipe", "id": "commitment-ledger"},
            lane=None,
            action="auto-closed-commitment",
            subject="cmt-1",
        )
        assert ev["refs"] == []

    def test_emit_omits_none_optional_objects(self, event_log_dir):
        ev = emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "pipe", "id": "x"},
            lane=None, action="a", subject="s",
        )
        assert "proposal" not in ev
        assert "outcome" not in ev
        assert "review" not in ev

    def test_emit_writes_to_consequence_events_file(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        emit_consequence(
            ts="2026-06-18T08:01:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t2",
        )
        files = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert len(files) == 1
        # must NOT collide with the org_events ledger filename family
        assert not list(Path(event_log_dir).glob("events-2*.jsonl"))
        with open(files[0]) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 2
        assert {l["subject"] for l in lines} == {"t1", "t2"}

    def test_emit_rejects_invalid_event_before_writing(self, event_log_dir):
        with pytest.raises(ConsequenceValidationError):
            emit_consequence(
                ts="2026-06-18T08:00:00+00:00",
                actor={"kind": "alien", "id": "ufo"},  # bad kind
                lane=None, action="a", subject="s",
            )
        assert list(Path(event_log_dir).glob("consequence-events-*.jsonl")) == []


from framework.fidelity.consequence import (
    _identity,
    read_ledger,
    compute_ratios,
    GraduationRatios,
)


class TestReadLedgerDedup:
    def test_identity_tuple_shape(self):
        ev = _act_event()
        assert _identity(ev) == (
            "officer:cos", "drafted-reply", "thread-abc",
            "2026-06-18T08:00:00+00:00",
        )

    def test_empty_log_returns_empty(self, event_log_dir):
        assert read_ledger() == []

    def test_enrichment_supersedes_same_identity(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="thread-abc",
            proposal={"required": True, "decision": None, "decided_at": None},
        )
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="thread-abc",
            proposal={"required": True, "decision": "approved",
                      "decided_at": "2026-06-18T08:05:00+00:00"},
            outcome={"status": "ok", "evidence": "sent-xyz"},
        )
        events = read_ledger()
        assert len(events) == 1  # collapsed to last write
        assert events[0]["proposal"]["decision"] == "approved"
        assert events[0]["outcome"]["status"] == "ok"

    def test_distinct_identities_not_collapsed(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t2",
        )
        assert len(read_ledger()) == 2

    def test_since_filter_inclusive(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T07:00:00+00:00",
            actor={"kind": "pipe", "id": "x"}, lane=None,
            action="a", subject="old",
        )
        emit_consequence(
            ts="2026-06-18T09:00:00+00:00",
            actor={"kind": "pipe", "id": "x"}, lane=None,
            action="a", subject="new",
        )
        events = read_ledger(since="2026-06-18T08:00:00+00:00")
        assert [e["subject"] for e in events] == ["new"]

    def test_ignores_colocated_org_events_row(self, event_log_dir):
        # A valid consequence row...
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        # ...and a hand-written org_events-shaped row (string actor) that
        # could only co-exist if the filenames collided. The reader must
        # skip it, not crash on actor.get('kind').
        bad = ('{"id":"e1","event_type":"mission_created",'
               '"actor":"captain","payload":{},"created_at":'
               '"2026-06-18T08:00:00+00:00"}')
        f = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))[0]
        with open(f, "a") as fh:
            fh.write(bad + "\n")
        events = read_ledger()
        assert len(events) == 1
        assert events[0]["subject"] == "t1"


class TestComputeRatios:
    def _emit_decided(self, ts, subject, decision, status, verdict,
                      actor=None, lane="polads", action="drafted-reply"):
        actor = actor or {"kind": "officer", "id": "cos"}
        outcome = None
        if status is not None:
            outcome = {"status": status,
                       "evidence": None if status == "unknown" else "ev"}
        review = None
        if verdict is not None:
            review = {"verdict": verdict}
        emit_consequence(
            ts=ts, actor=actor, lane=lane, action=action, subject=subject,
            proposal={"required": True, "decision": decision,
                      "decided_at": "2026-06-18T08:05:00+00:00"
                      if decision else None},
            outcome=outcome, review=review,
        )

    def test_approval_unchanged_rate(self, event_log_dir):
        # 2 approved, 1 edited, 1 rejected → 2/4 = 0.5
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None)
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None)
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "edited", None, None)
        self._emit_decided("2026-06-18T08:03:00+00:00", "d", "rejected", None, None)
        cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
        assert cell.sample_count == 4
        assert cell.approval_unchanged_rate == 0.5
        assert cell.approved == 2 and cell.edited == 1 and cell.rejected == 1

    def test_pending_and_expired_excluded_from_approval_denominator(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None)
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "expired", None, None)
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", None, None, None)  # pending
        cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
        assert cell.approval_unchanged_rate == 1.0  # 1 approved / 1 decided

    def test_outcome_held_rate(self, event_log_dir):
        # 3 ok, 1 failed, 1 unknown → 3/4 = 0.75 (unknown excluded)
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:03:00+00:00", "d", "approved", "failed", None)
        self._emit_decided("2026-06-18T08:04:00+00:00", "e", "approved", "unknown", None)
        cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
        assert cell.outcome_held_rate == 0.75
        assert cell.ok == 3 and cell.failed == 1

    def test_review_confirmed_rate(self, event_log_dir):
        # 1 confirmed, 1 wrong, 1 unknown → 1/2 = 0.5
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", "wrong")
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", "unknown")
        cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
        assert cell.review_confirmed_rate == 0.5
        assert cell.confirmed == 1 and cell.wrong == 1

    def test_unmeasured_cell_rates_are_none(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "pipe", "id": "x"}, lane=None,
            action="auto-closed-commitment", subject="cmt-1",
        )
        cell = compute_ratios()[("pipe:x", None, "auto-closed-commitment")]
        assert cell.approval_unchanged_rate is None
        assert cell.outcome_held_rate is None
        assert cell.review_confirmed_rate is None
        assert cell.sample_count == 1

    def test_cells_split_by_actor_lane_action(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None,
                           actor={"kind": "officer", "id": "cos"}, lane="polads")
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None,
                           actor={"kind": "officer", "id": "cto"}, lane="stephie")
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", None, None,
                           actor={"kind": "officer", "id": "cos"}, lane="polads",
                           action="triaged-board")
        cells = compute_ratios()
        assert ("officer:cos", "polads", "drafted-reply") in cells
        assert ("officer:cto", "stephie", "drafted-reply") in cells
        assert ("officer:cos", "polads", "triaged-board") in cells
        assert len(cells) == 3

    def test_dedup_applied_before_counting(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", None, None, None)
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        cell = compute_ratios()[("officer:cos", "polads", "drafted-reply")]
        assert cell.sample_count == 1
        assert cell.approval_unchanged_rate == 1.0
        assert cell.outcome_held_rate == 1.0
        assert cell.review_confirmed_rate == 1.0

    def test_compute_accepts_explicit_ledger(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        ledger = read_ledger()
        cells = compute_ratios(ledger=ledger)
        assert cells[("officer:cos", "polads", "drafted-reply")].sample_count == 1


class TestPathSafetyGuards:
    """Corridor guardrails folded into F0 (beyond the plan, minimal):
    (1) the write path anchors the ledger under the RESOLVED log dir;
    (2) the reader skips any consequence-events-*.jsonl symlink whose real
        path escapes the resolved log dir, rather than following it.
    """

    def test_write_lands_inside_resolved_log_dir(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        files = list(Path(event_log_dir).resolve().glob("consequence-events-*.jsonl"))
        assert len(files) == 1
        # the written file's real path is strictly under the resolved base
        base = Path(event_log_dir).resolve()
        assert base in files[0].resolve().parents

    def test_reader_skips_symlink_escaping_log_dir(self, event_log_dir, tmp_path):
        # event_log_dir IS tmp_path, so the "outside" target must live in a
        # genuinely separate dir to actually escape the fence.
        # A legitimate in-dir ledger row...
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        # ...and an outside-the-fence file that a planted symlink points at.
        outside_dir = tmp_path.parent / (tmp_path.name + "-outside")
        outside_dir.mkdir()
        outside = outside_dir / "outside-secret.jsonl"
        outside.write_text(
            '{"ts":"2026-06-18T09:00:00+00:00",'
            '"actor":{"kind":"officer","id":"evil"},'
            '"lane":null,"action":"exfil","subject":"leak","refs":[]}\n'
        )
        link = Path(event_log_dir) / "consequence-events-9999-99-99.jsonl"
        link.symlink_to(outside)

        events = read_ledger()
        # the symlink that escapes the resolved log dir is NOT followed
        assert [e["subject"] for e in events] == ["t1"]
        assert all(e["actor"]["id"] != "evil" for e in events)

    def test_reader_follows_symlink_that_stays_inside_log_dir(self, event_log_dir):
        # A symlink whose target is genuinely inside the fence is fine.
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="real",
        )
        real = list(Path(event_log_dir).glob("consequence-events-2*.jsonl"))[0]
        link = Path(event_log_dir) / "consequence-events-1111-11-11.jsonl"
        link.symlink_to(real.name)  # relative link, stays in-dir

        events = read_ledger()
        # both the real file and the in-dir symlink resolve to the same row;
        # identity dedup collapses them to one.
        assert [e["subject"] for e in events] == ["real"]
