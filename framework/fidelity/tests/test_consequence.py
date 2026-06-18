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
