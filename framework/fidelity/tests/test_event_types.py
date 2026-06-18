from __future__ import annotations

import pytest

from framework.events import emitter


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)


class TestFidelityEventTypes:
    def test_case_evaluated_is_valid(self):
        assert "fidelity_case_evaluated" in emitter.VALID_EVENT_TYPES

    def test_leak_detected_is_valid(self):
        assert "fidelity_case_leak_detected" in emitter.VALID_EVENT_TYPES

    def test_emit_case_evaluated_does_not_raise(self):
        ev = emitter.emit("fidelity_case_evaluated", actor="chair",
                          payload={"case_id": "abc1234567"})
        assert ev["event_type"] == "fidelity_case_evaluated"
        assert ev["id"]

    def test_aggregate_resolves_to_fidelity_case(self):
        agg_type, agg_id = emitter._resolve_aggregate(
            "fidelity_case_evaluated", {"case_id": "abc1234567"})
        assert agg_type == "fidelity"
        assert agg_id == "abc1234567"

    def test_emit_unknown_fidelity_type_still_raises(self):
        with pytest.raises(ValueError):
            emitter.emit("fidelity_bogus", actor="chair", payload={})
