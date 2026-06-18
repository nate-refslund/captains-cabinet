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
