"""T3 — intent fields carried on the consequence event + intent_match_rate.

Audit finding #1 (the measurement-validity blocker), the NON-germline part:
the F4 scoring path computes intent_composite / intent_verdict /
decision_verdict in scorer.CaseScore, but the consequence event the scoring
path emits did NOT carry them — so graduation (which reads ONLY the consequence
ledger) could never measure intent, and review.verdict was hardcoded 'unknown'
so review_confirmed_rate was forever None (cells stuck `unmeasured`).

These tests assert the SAFE scaffolding:
  1. the schema + hand-rolled validator accept the new OPTIONAL fields
     (action_type already existed; decision_verdict / intent_verdict /
     intent_composite / endorsement are added) and still reject unknown fields
     (additionalProperties:false holds);
  2. the F4 scoring-path emit (fidelity_events.build_case_scored /
     emit_case_scored) POPULATES those fields from a CaseScore AND maps
     review.verdict from the intent verdict
     (intent-aligned->confirmed, intent-divergent->wrong,
     intent-partial/error/""->unknown), so an intent-based
     review_confirmed_rate becomes available to the bar;
  3. GraduationRatios exposes intent_match_rate
     = intent-aligned / (intent-aligned + intent-divergent), None when the
     denominator is 0, computed from the new event fields in compute_ratios.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity import fidelity_events
from framework.fidelity.consequence import (
    ConsequenceValidationError,
    SCHEMA,
    compute_ratios,
    emit_consequence,
    read_ledger,
    validate_consequence,
)
from framework.fidelity.scorer import CaseScore


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


def _base(**overrides):
    """A minimal valid consequence event."""
    base = {
        "ts": "2026-06-19T08:00:00+00:00",
        "actor": {"kind": "officer", "id": "cos"},
        "lane": "bakery",
        "action": "fidelity-case-scored",
        "subject": "case-abc",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# 1. Schema + validator accept the new optional fields; reject unknown.
# --------------------------------------------------------------------------

class TestSchemaIntentFields:
    def test_schema_declares_the_new_optional_fields(self):
        props = SCHEMA["properties"]
        for f in ("decision_verdict", "intent_verdict",
                  "intent_composite", "endorsement"):
            assert f in props, f"schema missing optional field {f}"
        # still additionalProperties:false at root.
        assert SCHEMA.get("additionalProperties") is False

    def test_new_fields_are_not_required(self):
        # absent is fine — the unmeasured default.
        validate_consequence(_base())

    def test_decision_verdict_enum_accepted(self):
        for v in ("match", "partial", "divergent", "error", "skipped"):
            validate_consequence(_base(decision_verdict=v))

    def test_bad_decision_verdict_rejected(self):
        with pytest.raises(ConsequenceValidationError, match="decision_verdict"):
            validate_consequence(_base(decision_verdict="nuke"))

    def test_intent_verdict_enum_accepted(self):
        for v in ("intent-aligned", "intent-partial", "intent-divergent",
                  "error", ""):
            validate_consequence(_base(intent_verdict=v))

    def test_intent_verdict_may_be_null(self):
        validate_consequence(_base(intent_verdict=None))

    def test_bad_intent_verdict_rejected(self):
        with pytest.raises(ConsequenceValidationError, match="intent_verdict"):
            validate_consequence(_base(intent_verdict="aligned"))

    def test_intent_composite_number_accepted(self):
        validate_consequence(_base(intent_composite=0.0))
        validate_consequence(_base(intent_composite=1.0))
        validate_consequence(_base(intent_composite=0.5))

    def test_intent_composite_may_be_null(self):
        validate_consequence(_base(intent_composite=None))

    def test_intent_composite_out_of_range_rejected(self):
        with pytest.raises(ConsequenceValidationError, match="intent_composite"):
            validate_consequence(_base(intent_composite=1.5))
        with pytest.raises(ConsequenceValidationError, match="intent_composite"):
            validate_consequence(_base(intent_composite=-0.1))

    def test_intent_composite_non_number_rejected(self):
        with pytest.raises(ConsequenceValidationError, match="intent_composite"):
            validate_consequence(_base(intent_composite="high"))

    def test_endorsement_string_accepted(self):
        for v in ("unknown", "regretted", "constrained", "corrected"):
            validate_consequence(_base(endorsement=v))

    def test_endorsement_may_be_null(self):
        validate_consequence(_base(endorsement=None))

    def test_empty_endorsement_rejected(self):
        with pytest.raises(ConsequenceValidationError, match="endorsement"):
            validate_consequence(_base(endorsement=""))

    def test_unknown_field_still_rejected_with_intent_fields_present(self):
        ev = _base(decision_verdict="match", intent_verdict="intent-aligned",
                   intent_composite=1.0, endorsement="unknown", surprise="boom")
        with pytest.raises(ConsequenceValidationError):
            validate_consequence(ev)

    def test_emit_persists_intent_fields(self, event_log_dir):
        emit_consequence(
            ts="2026-06-19T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="bakery", action="fidelity-case-scored", subject="case-1",
            action_type="internal_message",
            decision_verdict="divergent", intent_verdict="intent-aligned",
            intent_composite=1.0, endorsement="unknown",
            review={"verdict": "confirmed", "source": "verdict_human"},
        )
        events = read_ledger()
        assert len(events) == 1
        ev = events[0]
        assert ev["decision_verdict"] == "divergent"
        assert ev["intent_verdict"] == "intent-aligned"
        assert ev["intent_composite"] == 1.0
        assert ev["endorsement"] == "unknown"

    def test_emit_omits_none_intent_fields(self, event_log_dir):
        # None optional scalars are dropped, never written as literal null.
        emit_consequence(
            ts="2026-06-19T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"},
            lane="bakery", action="x", subject="s",
        )
        ev = read_ledger()[0]
        for f in ("decision_verdict", "intent_verdict",
                  "intent_composite", "endorsement"):
            assert f not in ev


# --------------------------------------------------------------------------
# 2. F4 scoring-path emit populates fields + maps review.verdict from intent.
# --------------------------------------------------------------------------

def _case_score(**overrides):
    base = dict(
        case_id="case-abc",
        style_win=True,
        decision_verdict="divergent",
        mechanics_flags=[],
        endorsement_adjusted=False,
        composite=0.0,
        raw={},
        intent_verdict="intent-aligned",
        intent_grounded_fact="From Bo at 2026-06-10: roadmap",
        intent_composite=1.0,
    )
    base.update(overrides)
    return CaseScore(**base)


class TestBuildCaseScored:
    def test_build_carries_intent_fields(self):
        ev = fidelity_events.build_case_scored(
            _case_score(), officer="cos", lane="bakery", endorsement="unknown")
        fidelity_events.validate_event(ev)  # must not raise
        assert ev["action"] == "fidelity-case-scored"
        assert ev["subject"] == "case-abc"
        assert ev["actor"] == {"kind": "officer", "id": "cos"}
        assert ev["decision_verdict"] == "divergent"
        assert ev["intent_verdict"] == "intent-aligned"
        assert ev["intent_composite"] == 1.0
        assert ev["endorsement"] == "unknown"

    def test_review_verdict_aligned_maps_to_confirmed(self):
        ev = fidelity_events.build_case_scored(
            _case_score(intent_verdict="intent-aligned"),
            officer="cos", lane="bakery")
        assert ev["review"]["verdict"] == "confirmed"

    def test_review_verdict_divergent_maps_to_wrong(self):
        ev = fidelity_events.build_case_scored(
            _case_score(intent_verdict="intent-divergent", intent_composite=0.0),
            officer="cos", lane="bakery")
        assert ev["review"]["verdict"] == "wrong"

    @pytest.mark.parametrize("iv", ["intent-partial", "error", ""])
    def test_review_verdict_partial_error_empty_map_to_unknown(self, iv):
        ev = fidelity_events.build_case_scored(
            _case_score(intent_verdict=iv, intent_composite=0.5),
            officer="cos", lane="bakery")
        assert ev["review"]["verdict"] == "unknown"

    def test_endorsement_defaults_from_case_score(self):
        # when caller passes no endorsement, the scorer's endorsement_adjusted
        # state still produces a valid, present endorsement string.
        ev = fidelity_events.build_case_scored(
            _case_score(), officer="cos", lane="bakery")
        assert isinstance(ev.get("endorsement"), str) and ev["endorsement"]

    def test_emit_case_scored_writes_consequence_ledger(self, event_log_dir):
        out = fidelity_events.emit_case_scored(
            _case_score(), officer="cos", lane="bakery", endorsement="unknown")
        assert out["action"] == "fidelity-case-scored"
        cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert cfiles, "no consequence ledger file written"
        ofiles = list(Path(event_log_dir).glob("events-2*.jsonl"))
        assert ofiles, "no org-event ledger file written"

    def test_emit_case_scored_review_confirmed_rate_now_measurable(
            self, event_log_dir):
        # T3 x flavor-A (2026-07-03): an intent-aligned scored case emits
        # review.verdict=confirmed with source=verdict_judge — the intent axis
        # becomes measurable, but a JUDGE confirmed is NOT promotion fuel, so
        # cell.confirmed stays 0 (review_confirmed_rate None from judge rows).
        # A judge 'wrong' (divergent case) DOES count — machines may demote.
        fidelity_events.emit_case_scored(
            _case_score(intent_verdict="intent-aligned"),
            officer="cos", lane="bakery", action_type="internal_message",
            endorsement="unknown")
        cell = compute_ratios()[("officer:cos", "bakery", "internal_message")]
        assert cell.intent_match_rate == 1.0          # measurable intent axis
        assert cell.confirmed == 0 and cell.wrong == 0  # zero promotion fuel
        assert cell.review_confirmed_rate is None


# --------------------------------------------------------------------------
# 3. GraduationRatios.intent_match_rate from compute_ratios.
# --------------------------------------------------------------------------

class TestIntentMatchRate:
    def _emit_scored(self, ts, subject, intent_verdict,
                     action_type="internal_message"):
        review = {"verdict": "unknown"}
        if intent_verdict == "intent-aligned":
            review = {"verdict": "confirmed", "source": "verdict_human"}
        elif intent_verdict == "intent-divergent":
            review = {"verdict": "wrong"}
        emit_consequence(
            ts=ts, actor={"kind": "officer", "id": "cos"}, lane="bakery",
            action="fidelity-case-scored", subject=subject,
            action_type=action_type,
            decision_verdict="divergent", intent_verdict=intent_verdict,
            intent_composite=1.0 if intent_verdict == "intent-aligned" else 0.0,
            review=review,
        )

    def test_intent_match_rate(self, event_log_dir):
        # 2 aligned, 1 divergent, 1 partial → 2 / (2+1) = 0.6667 (partial
        # excluded from the denominator, like unknown verdicts are for review).
        self._emit_scored("2026-06-19T08:00:00+00:00", "a", "intent-aligned")
        self._emit_scored("2026-06-19T08:01:00+00:00", "b", "intent-aligned")
        self._emit_scored("2026-06-19T08:02:00+00:00", "c", "intent-divergent")
        self._emit_scored("2026-06-19T08:03:00+00:00", "d", "intent-partial")
        cell = compute_ratios()[("officer:cos", "bakery", "internal_message")]
        assert cell.intent_aligned == 2
        assert cell.intent_divergent == 1
        assert round(cell.intent_match_rate, 4) == 0.6667

    def test_intent_match_rate_none_when_no_signal(self, event_log_dir):
        # only partial / error / unknown → denominator 0 → None (visible
        # unmeasured, never a silent 0.0/1.0).
        self._emit_scored("2026-06-19T08:00:00+00:00", "a", "intent-partial")
        self._emit_scored("2026-06-19T08:01:00+00:00", "b", "error")
        cell = compute_ratios()[("officer:cos", "bakery", "internal_message")]
        assert cell.intent_match_rate is None

    def test_intent_match_rate_absent_field_is_none(self, event_log_dir):
        # A legacy row with no intent_verdict contributes nothing to the intent
        # denominator → None.
        emit_consequence(
            ts="2026-06-19T08:00:00+00:00",
            actor={"kind": "officer", "id": "cos"}, lane="bakery",
            action="drafted-reply", subject="s",
            action_type="internal_message",
            proposal={"required": True, "decision": "approved",
                      "decided_at": "2026-06-19T08:05:00+00:00"},
        )
        cell = compute_ratios()[("officer:cos", "bakery", "internal_message")]
        assert cell.intent_match_rate is None
        assert cell.intent_aligned == 0 and cell.intent_divergent == 0
