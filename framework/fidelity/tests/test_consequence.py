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
    UNSTAMPED_ACTION_TYPE,
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


from framework.authority.classifier import ACTION_TYPES


class TestActionTypeField:
    """T2 [FIX-1 steps 1-2]: action_type is a first-class OPTIONAL field on the
    consequence event — string (a member of the classifier's ACTION_TYPES enum)
    or null, additive, additionalProperties:false preserved. The brain-bridge
    emitter stamps it via the SAME classify_action() the gate uses; absent when
    not supplied."""

    def test_valid_action_type_passes(self):
        ev = _act_event(action_type="local_edit")
        assert validate_consequence(ev) is None

    def test_ceiling_action_type_passes(self):
        # a positively-classified ceiling value is a legal action_type
        ev = _act_event(action_type="external_message")
        assert validate_consequence(ev) is None

    def test_ambiguous_action_type_passes(self):
        # the visible propose-defaulting backstop is itself a legal value
        ev = _act_event(action_type="ambiguous")
        assert validate_consequence(ev) is None

    def test_action_type_may_be_null(self):
        ev = _act_event(action_type=None)
        assert validate_consequence(ev) is None

    def test_event_without_action_type_still_passes(self):
        # field is OPTIONAL — its absence is the unstamped default
        ev = _act_event()
        assert "action_type" not in ev
        assert validate_consequence(ev) is None

    def test_unknown_action_type_value_raises(self):
        ev = _act_event(action_type="nuke_prod")
        with pytest.raises(ConsequenceValidationError, match="action_type"):
            validate_consequence(ev)

    def test_non_string_action_type_raises(self):
        ev = _act_event(action_type=42)
        with pytest.raises(ConsequenceValidationError, match="action_type"):
            validate_consequence(ev)

    def test_additional_props_still_rejected_with_action_type_present(self):
        # adding the new known field does NOT loosen additionalProperties:false
        ev = _act_event(action_type="local_edit", surprise="boom")
        with pytest.raises(ConsequenceValidationError, match="additional"):
            validate_consequence(ev)

    def test_enum_is_sourced_from_classifier(self):
        # single source of truth: the schema enum must equal the classifier's
        # ACTION_TYPES (no drifting duplicated literal list).
        action_type_prop = SCHEMA["properties"]["action_type"]
        schema_values = {v for v in action_type_prop["enum"] if v is not None}
        assert schema_values == set(ACTION_TYPES)
        assert None in action_type_prop["enum"]  # null allowed

    def test_emit_persists_action_type(self, event_log_dir):
        ev = emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
            action_type="external_message",
        )
        assert ev["action_type"] == "external_message"
        events = read_ledger()
        assert len(events) == 1
        assert events[0]["action_type"] == "external_message"

    def test_emit_omits_action_type_when_none(self, event_log_dir):
        # same omit-when-None discipline as proposal/outcome/review: a None
        # action_type is DROPPED, never written as a literal null.
        ev = emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="polads", action="drafted-reply", subject="t1",
        )
        assert "action_type" not in ev
        events = read_ledger()
        assert "action_type" not in events[0]

    def test_emit_rejects_bad_action_type_before_writing(self, event_log_dir):
        with pytest.raises(ConsequenceValidationError, match="action_type"):
            emit_consequence(
                ts="2026-06-18T08:00:00+00:00",
                actor={"kind": "officer", "id": "cos"},
                lane="polads", action="drafted-reply", subject="t1",
                action_type="nuke_prod",
            )
        assert list(Path(event_log_dir).glob("consequence-events-*.jsonl")) == []


class TestComputeRatios:
    """T3 [FIX-1 steps 3-4]: cells are keyed on (actor_id, lane, ACTION_TYPE),
    not the free-text `action`. The free-text `action` is retained on the event
    as a descriptive field but is no longer the cell key. The matrix gate keys
    verdicts on the action_type enum, so the ledger must agree.

    Helper stamps a real action_type (default 'internal_message') AND a free-text
    `action`; the cell key uses the action_type, proving the re-key."""

    def _emit_decided(self, ts, subject, decision, status, verdict,
                      actor=None, lane="polads", action="drafted-reply",
                      action_type="internal_message"):
        actor = actor or {"kind": "officer", "id": "cos"}
        outcome = None
        if status is not None:
            outcome = {"status": status,
                       "evidence": None if status == "unknown" else "ev"}
        review = None
        if verdict is not None:
            # human-decided fixture rows (flavor-A split 2026-07-03): only
            # verdict_human confirms count toward review_confirmed_rate
            review = {"verdict": verdict, "source": "verdict_human"}
        emit_consequence(
            ts=ts, actor=actor, lane=lane, action=action, subject=subject,
            action_type=action_type,
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
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.sample_count == 4
        assert cell.approval_unchanged_rate == 0.5
        assert cell.approved == 2 and cell.edited == 1 and cell.rejected == 1

    def test_pending_and_expired_excluded_from_approval_denominator(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None)
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "expired", None, None)
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", None, None, None)  # pending
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.approval_unchanged_rate == 1.0  # 1 approved / 1 decided

    def test_outcome_held_rate(self, event_log_dir):
        # 3 ok, 1 failed, 1 unknown → 3/4 = 0.75 (unknown excluded)
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", None)
        self._emit_decided("2026-06-18T08:03:00+00:00", "d", "approved", "failed", None)
        self._emit_decided("2026-06-18T08:04:00+00:00", "e", "approved", "unknown", None)
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.outcome_held_rate == 0.75
        assert cell.ok == 3 and cell.failed == 1

    def test_flavor_a_split_judge_confirms_never_promote(self, event_log_dir):
        """Flavor-A CI pin (2026-07-03): promotion fuel (cell.confirmed) counts
        verdict_human ONLY. A judge/machine confirmed contributes nothing; a
        judge wrong still demotes; an unattributed legacy confirmed is
        fail-closed excluded."""
        def emit(subject, verdict, source):
            review = {"verdict": verdict}
            if source is not None:
                review["source"] = source
            emit_consequence(
                ts="2026-06-18T08:00:00+00:00",
                actor={"kind": "officer", "id": "cos"}, lane="polads",
                action=f"act-{subject}", subject=subject,
                action_type="internal_message",
                proposal={"required": True, "decision": "approved",
                          "decided_at": "2026-06-18T08:05:00+00:00"},
                outcome={"status": "ok", "evidence": "ev"}, review=review)
        emit("h1", "confirmed", "verdict_human")   # counts
        emit("j1", "confirmed", "verdict_judge")   # promotion-inert
        emit("l1", "confirmed", None)              # legacy/unattributed: inert
        emit("j2", "wrong", "verdict_judge")       # machine wrong DOES demote
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.confirmed == 1                 # only the human confirm
        assert cell.wrong == 1                     # judge wrong counted
        assert cell.review_confirmed_rate == 0.5

    def test_review_confirmed_rate(self, event_log_dir):
        # 1 confirmed, 1 wrong, 1 unknown → 1/2 = 0.5
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", "ok", "wrong")
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", "ok", "unknown")
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.review_confirmed_rate == 0.5
        assert cell.confirmed == 1 and cell.wrong == 1

    def test_unmeasured_cell_rates_are_none(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "pipe", "id": "x"}, lane=None,
            action="auto-closed-commitment", subject="cmt-1",
            action_type="task_status_move",
        )
        cell = compute_ratios()[("pipe:x", None, "task_status_move")]
        assert cell.approval_unchanged_rate is None
        assert cell.outcome_held_rate is None
        assert cell.review_confirmed_rate is None
        assert cell.sample_count == 1

    def test_cells_split_by_actor_lane_action_type(self, event_log_dir):
        # Same free-text action, DIFFERENT action_type → distinct cells (proves
        # the key is action_type, not the free-text action).
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None,
                           actor={"kind": "officer", "id": "cos"}, lane="polads",
                           action="drafted-reply", action_type="internal_message")
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None,
                           actor={"kind": "officer", "id": "cto"}, lane="stephie",
                           action="drafted-reply", action_type="internal_message")
        self._emit_decided("2026-06-18T08:02:00+00:00", "c", "approved", None, None,
                           actor={"kind": "officer", "id": "cos"}, lane="polads",
                           action="drafted-reply", action_type="board_status")
        cells = compute_ratios()
        assert ("officer:cos", "polads", "internal_message") in cells
        assert ("officer:cto", "stephie", "internal_message") in cells
        assert ("officer:cos", "polads", "board_status") in cells
        assert len(cells) == 3

    def test_same_action_type_different_free_text_action_merges(self, event_log_dir):
        # Two events with the SAME (actor, lane, action_type) but DIFFERENT
        # free-text action collapse into ONE cell — the free-text action is
        # descriptive only, not part of the key.
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", None, None,
                           action="drafted-reply-to-sean", action_type="internal_message")
        self._emit_decided("2026-06-18T08:01:00+00:00", "b", "approved", None, None,
                           action="drafted-reply-to-lisa", action_type="internal_message")
        cells = compute_ratios()
        assert list(cells.keys()) == [("officer:cos", "polads", "internal_message")]
        assert cells[("officer:cos", "polads", "internal_message")].sample_count == 2

    def test_dedup_applied_before_counting(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", None, None, None)
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        cell = compute_ratios()[("officer:cos", "polads", "internal_message")]
        assert cell.sample_count == 1
        assert cell.approval_unchanged_rate == 1.0
        assert cell.outcome_held_rate == 1.0
        assert cell.review_confirmed_rate == 1.0

    def test_compute_accepts_explicit_ledger(self, event_log_dir):
        self._emit_decided("2026-06-18T08:00:00+00:00", "a", "approved", "ok", "confirmed")
        ledger = read_ledger()
        cells = compute_ratios(ledger=ledger)
        assert cells[("officer:cos", "polads", "internal_message")].sample_count == 1


class TestComputeRatiosUnstampedSentinel:
    """T3 back-compat: a ledger row with NO action_type (the unstamped/legacy
    default — action_type is an OPTIONAL schema field) is keyed under the fixed
    VISIBLE sentinel UNSTAMPED_ACTION_TYPE, never under its free-text action.

    Fail-closed rationale: a free-text action could literally equal an
    action_type enum value (e.g. 'local_edit'); falling back to the free text
    would silently conflate an unstamped event into a MEASURED graduation cell
    and let a cell light up autonomy on unstamped noise. The sentinel keeps
    unstamped data in one visible bucket that can never graduate, preserving the
    fail-closed spine + no-silent-caps (the bucket is visible, not silently 0/1).
    """

    def test_unstamped_event_keyed_under_sentinel(self, event_log_dir):
        emit_consequence(
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "pipe", "id": "x"}, lane=None,
            action="auto-closed-commitment", subject="cmt-1",
        )  # no action_type → unstamped
        cells = compute_ratios()
        assert ("pipe:x", None, UNSTAMPED_ACTION_TYPE) in cells
        # and NOT keyed under the free-text action
        assert ("pipe:x", None, "auto-closed-commitment") not in cells
        assert cells[("pipe:x", None, UNSTAMPED_ACTION_TYPE)].sample_count == 1

    def test_unstamped_free_text_cannot_conflate_into_measured_cell(self, event_log_dir):
        # An unstamped event whose free-text action collides with an action_type
        # enum value ('local_edit') must NOT join the stamped 'local_edit' cell.
        emit_consequence(  # stamped local_edit
            ts="2026-06-18T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"}, lane="polads",
            action="edited-config", subject="s1", action_type="local_edit",
        )
        emit_consequence(  # unstamped, free text literally 'local_edit'
            ts="2026-06-18T08:01:00+00:00",
            actor={"kind": "officer", "id": "cos"}, lane="polads",
            action="local_edit", subject="s2",
        )
        cells = compute_ratios()
        # the stamped cell holds exactly its own event...
        assert cells[("officer:cos", "polads", "local_edit")].sample_count == 1
        # ...and the unstamped event lives in the sentinel bucket, NOT conflated
        assert cells[("officer:cos", "polads", UNSTAMPED_ACTION_TYPE)].sample_count == 1

    def test_sentinel_is_not_a_real_action_type(self, event_log_dir):
        # the sentinel must be disjoint from the classifier's enum so it can
        # never be mistaken for a measurable cell by the gate.
        assert UNSTAMPED_ACTION_TYPE not in ACTION_TYPES

    def test_unstamped_events_aggregate_into_one_visible_bucket(self, event_log_dir):
        for i, subj in enumerate(("a", "b", "c")):
            emit_consequence(
                ts=f"2026-06-18T08:0{i}:00+00:00",
                actor={"kind": "pipe", "id": "y"}, lane="polads",
                action=f"free-{subj}", subject=subj,
            )
        cells = compute_ratios()
        assert cells[("pipe:y", "polads", UNSTAMPED_ACTION_TYPE)].sample_count == 3


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
