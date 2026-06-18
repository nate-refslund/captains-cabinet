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
