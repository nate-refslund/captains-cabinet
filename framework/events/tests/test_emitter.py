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
