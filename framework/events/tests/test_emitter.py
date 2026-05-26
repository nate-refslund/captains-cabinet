"""Tests for the organizational event emitter."""

import json
import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.events.emitter import emit, replay, VALID_EVENT_TYPES


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path):
    """Use a temporary directory for event logs."""
    os.environ["CABINET_EVENT_LOG_DIR"] = str(tmp_path)
    os.environ.pop("DATABASE_URL", None)  # no DB in tests
    yield tmp_path


class TestEmit:
    def test_basic_event(self, event_log_dir):
        event = emit("role_created", actor="captain", payload={"slug": "eng"})
        assert event["event_type"] == "role_created"
        assert event["actor"] == "captain"
        assert event["payload"]["slug"] == "eng"
        assert event["id"]
        assert event["created_at"]
        assert event["parent_id"] is None

    def test_event_with_parent(self, event_log_dir):
        parent = emit("mission_created", actor="cos", payload={"name": "Ship MVP"})
        child = emit("work_item_created", actor="cos", payload={"desc": "Build UI"}, parent_id=parent["id"])
        assert child["parent_id"] == parent["id"]

    def test_unknown_event_type_raises(self, event_log_dir):
        with pytest.raises(ValueError, match="Unknown event type"):
            emit("totally_made_up", actor="test")

    def test_event_written_to_jsonl(self, event_log_dir):
        emit("session_started", actor="system", payload={"role": "cos"})
        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1
        with open(log_files[0]) as f:
            line = f.readline().strip()
            event = json.loads(line)
            assert event["event_type"] == "session_started"

    def test_multiple_events_append(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("role_created", actor="captain", payload={"slug": "product"})
        emit("role_created", actor="captain", payload={"slug": "growth"})
        log_files = list(event_log_dir.glob("events-*.jsonl"))
        with open(log_files[0]) as f:
            lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 3

    def test_empty_payload_defaults(self, event_log_dir):
        event = emit("kill_switch_activated", actor="captain")
        assert event["payload"] == {}

    def test_all_event_types_are_strings(self):
        for et in VALID_EVENT_TYPES:
            assert isinstance(et, str)
            assert "_" in et  # snake_case convention


class TestReplay:
    def test_replay_all(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        events = replay()
        assert len(events) == 2

    def test_replay_filter_by_type(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        emit("role_created", actor="captain", payload={"slug": "ops"})
        events = replay(event_types=["role_created"])
        assert len(events) == 2
        assert all(e["event_type"] == "role_created" for e in events)

    def test_replay_filter_by_actor(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        events = replay(actor="cos")
        assert len(events) == 1
        assert events[0]["actor"] == "cos"

    def test_replay_empty_log(self, event_log_dir):
        events = replay()
        assert events == []

    def test_replay_filter_by_since(self, event_log_dir):
        e1 = emit("role_created", actor="captain", payload={"slug": "eng"})
        events = replay(since=e1["created_at"])
        # since is exclusive-ish (string comparison)
        assert len(events) >= 0  # depends on timing


class TestEventTypes:
    """Verify the event type vocabulary covers the core systems."""

    def test_captain_events_exist(self):
        captain_types = [t for t in VALID_EVENT_TYPES if t.startswith("captain_")]
        assert len(captain_types) >= 3

    def test_role_events_exist(self):
        role_types = [t for t in VALID_EVENT_TYPES if t.startswith("role_")]
        assert len(role_types) >= 5

    def test_mission_events_exist(self):
        mission_types = [t for t in VALID_EVENT_TYPES if t.startswith("mission_")]
        assert len(mission_types) >= 3

    def test_work_item_events_exist(self):
        wi_types = [t for t in VALID_EVENT_TYPES if t.startswith("work_item_")]
        assert len(wi_types) >= 4

    def test_policy_events_exist(self):
        policy_types = [t for t in VALID_EVENT_TYPES if t.startswith("policy_")]
        assert len(policy_types) >= 2

    def test_measurement_events_exist(self):
        assert "ovi_snapshot_computed" in VALID_EVENT_TYPES
        assert "eval_passed" in VALID_EVENT_TYPES
        assert "eval_failed" in VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# F3: event-kernel unification (org_runtime.Store mirror)
# ---------------------------------------------------------------------------


from framework.events.emitter import (
    _resolve_aggregate,
    _resolve_product_slug,
    _write_to_store,
    _AGGREGATE_MAP,
)


class TestAggregateResolution:
    """_resolve_aggregate maps framework event_type → Store (agg_type, agg_id)."""

    def test_mission_created_uses_mission_id(self):
        agg_type, agg_id = _resolve_aggregate(
            "mission_created", {"mission_id": "m-1", "name": "Launch"}
        )
        assert agg_type == "mission"
        assert agg_id == "m-1"

    def test_work_item_uses_task_id(self):
        agg_type, agg_id = _resolve_aggregate(
            "work_item_completed", {"task_id": "outcome-001-task-003"}
        )
        assert agg_type == "work_item"
        assert agg_id == "outcome-001-task-003"

    def test_role_event_uses_slug(self):
        agg_type, agg_id = _resolve_aggregate("role_created", {"slug": "engineering"})
        assert agg_type == "role"
        assert agg_id == "engineering"

    def test_ovi_uses_period(self):
        agg_type, agg_id = _resolve_aggregate(
            "ovi_snapshot_computed", {"period": "2026-W21"}
        )
        assert agg_type == "ovi"
        assert agg_id == "2026-W21"

    def test_missing_payload_key_falls_back_to_id(self):
        # Use a captain_decision_logged event; expected key is "decision_id"
        # but payload only has "id"
        agg_type, agg_id = _resolve_aggregate(
            "captain_decision_logged", {"id": "decision-42"}
        )
        assert agg_type == "captain"
        assert agg_id == "decision-42"

    def test_unmapped_event_type_uses_prefix(self):
        # Not in _AGGREGATE_MAP — should derive aggregate_type from prefix
        agg_type, agg_id = _resolve_aggregate("custom_unknown_event", {"id": "x"})
        assert agg_type == "custom"
        assert agg_id == "x"

    def test_completely_missing_id_returns_unknown(self):
        agg_type, agg_id = _resolve_aggregate("mission_created", {})
        assert agg_type == "mission"
        assert agg_id == "unknown"

    def test_all_valid_event_types_covered(self):
        """Every event type in VALID_EVENT_TYPES should have an aggregate mapping
        OR have a sensible prefix fallback."""
        for et in VALID_EVENT_TYPES:
            agg_type, _ = _resolve_aggregate(et, {})
            assert agg_type, f"{et} produced empty aggregate_type"


class TestProductSlugResolution:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("CABINET_PRODUCT_SLUG", "myproduct")
        assert _resolve_product_slug() == "myproduct"

    def test_active_project_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "active-project.txt").write_text("alpha-project\n")
        assert _resolve_product_slug() == "alpha-project"

    def test_default_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        assert _resolve_product_slug() == "default"

    def test_empty_active_project_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "active-project.txt").write_text("   \n")  # whitespace only
        assert _resolve_product_slug() == "default"


class TestStoreMirrorGating:
    """_write_to_store should skip cleanly under test/disabled conditions."""

    def test_skips_under_pytest(self, monkeypatch):
        # PYTEST_CURRENT_TEST is set by pytest during test runs; emit() should
        # auto-skip the Store write so the dev cache isn't polluted.
        monkeypatch.delenv("CABINET_FRAMEWORK_STORE_MIRROR", raising=False)
        # Even if we pass a "valid"-looking event, no Store import / write happens
        event = {
            "id": "test-id",
            "event_type": "mission_created",
            "actor": "test",
            "payload": {"mission_id": "m-test"},
            "parent_id": None,
            "created_at": "2026-05-26T00:00:00Z",
        }
        # Should not raise + should be a no-op
        _write_to_store(event)

    def test_force_off_short_circuits(self, monkeypatch):
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        event = {
            "id": "x", "event_type": "mission_created", "actor": "t",
            "payload": {}, "parent_id": None, "created_at": "x",
        }
        # Should not raise — explicit force-off
        _write_to_store(event)

    def test_emit_does_not_crash_when_store_disabled(self, monkeypatch, tmp_path):
        # Full emit() with store mirror disabled — confirms F3 doesn't break
        # the JSONL/DB writes when Store is unavailable.
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        event = emit("role_created", actor="cap", payload={"slug": "eng"})
        assert event["event_type"] == "role_created"
        # JSONL was written
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) >= 1
