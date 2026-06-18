from __future__ import annotations

from pathlib import Path

import pytest

from framework.fidelity import fidelity_events
from framework.fidelity.consequence import ConsequenceValidationError
from framework.fidelity.types import OfficerDecision


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


class TestBuilders:
    def test_case_evaluated_is_valid(self):
        d = OfficerDecision(decision="draft", rationale="why", chain=[])
        ev = fidelity_events.build_case_evaluated(
            "abc1234567", "chair", "send-1to1-reply", d, evidence="chainhash:deadbeef")
        fidelity_events.validate_event(ev)  # must not raise
        assert ev["actor"] == {"kind": "officer", "id": "chair"}
        assert ev["action"] == "fidelity-case-evaluated"
        assert ev["subject"] == "abc1234567"
        assert ev["proposal"] == {"required": False}
        assert ev["outcome"]["status"] == "ok"
        assert ev["outcome"]["evidence"] == "chainhash:deadbeef"
        assert ev["review"]["verdict"] == "unknown"
        assert ev["refs"] == ["abc1234567"]

    def test_case_leaked_is_valid_and_failed(self):
        ev = fidelity_events.build_case_leaked(
            "abc1234567", "chair", "send-1to1-reply", ["2026-06-11T09:00:00+00:00"])
        fidelity_events.validate_event(ev)
        assert ev["action"] == "fidelity-case-leak-detected"
        assert ev["outcome"]["status"] == "failed"
        assert "2026-06-11" in ev["outcome"]["evidence"]

    def test_additional_property_rejected(self):
        ev = fidelity_events.build_case_evaluated(
            "x1", "chair", "lane", OfficerDecision("d", "r", []), evidence="e")
        ev["bogus"] = 1
        with pytest.raises(ConsequenceValidationError):
            fidelity_events.validate_event(ev)


class TestEmit:
    def test_emit_case_evaluated_writes_consequence_ledger(self, event_log_dir):
        d = OfficerDecision(decision="draft", rationale="why", chain=[])
        out = fidelity_events.emit_case_evaluated(
            "abc1234567", "chair", "send-1to1-reply", d, evidence="h:1")
        assert out["action"] == "fidelity-case-evaluated"
        cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert cfiles, "no consequence ledger file written"
        ofiles = list(Path(event_log_dir).glob("events-2*.jsonl"))
        assert ofiles, "no org-event ledger file written"

    def test_emit_case_leaked_status_failed(self, event_log_dir):
        out = fidelity_events.emit_case_leaked(
            "abc1234567", "chair", "send-1to1-reply", ["leaksig"])
        assert out["outcome"]["status"] == "failed"
