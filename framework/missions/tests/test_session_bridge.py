"""Tests for the session-to-mission bridge."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure framework root is importable
_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.missions.session_bridge import get_next_task, format_task_for_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Route event logs to a temp directory so emitter doesn't fail."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path / "events"


@pytest.fixture
def sample_roles():
    """Sample role definitions for testing."""
    return [
        {
            "slug": "engineering",
            "title": "Chief Technology Officer",
            "capabilities": ["deploys_code", "engineering", "reviews_implementations"],
        },
        {
            "slug": "product",
            "title": "Chief Product Officer",
            "capabilities": ["product", "reviews_specs"],
        },
        {
            "slug": "research",
            "title": "Chief Research Officer",
            "capabilities": ["research", "reviews_research"],
        },
    ]


@pytest.fixture
def outcomes_dir(tmp_path):
    """Create a temporary cabinet root with an outcomes file."""
    config_dir = tmp_path / "instance" / "config"
    config_dir.mkdir(parents=True)
    return tmp_path


def _write_outcomes(outcomes_dir: Path, content: str) -> Path:
    """Write outcomes YAML and return the cabinet root."""
    outcomes_file = outcomes_dir / "instance" / "config" / "outcomes.yml"
    outcomes_file.write_text(content)
    return outcomes_dir


# ---------------------------------------------------------------------------
# Tests: get_next_task
# ---------------------------------------------------------------------------


class TestGetNextTask:
    def test_no_outcomes_file_returns_none(self, tmp_path):
        """When outcomes.yml does not exist, returns None."""
        result = get_next_task("engineering", cabinet_root=str(tmp_path))
        assert result is None

    def test_matching_role_returns_task(self, outcomes_dir, sample_roles, monkeypatch):
        """When outcomes exist and role matches, returns a task dict."""
        # Use "database schema" (early-phase keyword) so the engineering task
        # is a root node in the work graph and therefore ready immediately.
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
      - "User signup flow functional end-to-end"
    status: active
""")
        # Patch list_roles so the compiler finds our test roles
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))

        assert task is not None
        assert task["mission_name"] == "Ship MVP"
        assert task["assigned_role"] == "engineering"
        assert "task_description" in task
        assert "verification_criteria" in task
        assert isinstance(task["dependencies_met"], list)

    def test_no_matching_role_returns_none(self, outcomes_dir, sample_roles, monkeypatch):
        """When outcomes exist but no tasks match the role, returns None."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-002
    name: "Research Phase"
    measurable_criteria:
      - "Complete competitive analysis brief"
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        # "operations" role has no matching tasks in this outcome
        task = get_next_task("operations", cabinet_root=str(cabinet_root))
        assert task is None

    def test_draft_outcomes_ignored(self, outcomes_dir, sample_roles, monkeypatch):
        """Draft outcomes are not compiled, so no tasks are returned."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-draft
    name: "Future Work"
    measurable_criteria:
      - "Build API endpoints"
    status: draft
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is None

    def test_invalid_yaml_returns_none(self, outcomes_dir):
        """Malformed outcomes file returns None (no crash)."""
        cabinet_root = _write_outcomes(outcomes_dir, "not_valid: true\n")

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is None

    def test_projection_compile_emits_no_mission_created(
        self, outcomes_dir, sample_roles, monkeypatch, event_log_dir,
    ):
        """get_next_task is a projection — it must never spam the ledger.

        This runs from session hooks every few minutes; before the
        emit_event flag it wrote mission_created on every invocation.
        """
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is not None  # the projection itself still works

        # ...but zero events were written to the ledger
        assert list(event_log_dir.glob("events-*.jsonl")) == []


# ---------------------------------------------------------------------------
# Tests: format_task_for_session
# ---------------------------------------------------------------------------


class TestFormatTaskForSession:
    def test_produces_readable_string(self):
        """Formatted output contains mission name, task, role, and criteria."""
        task = {
            "mission_name": "Ship MVP",
            "task_id": "outcome-001-task-000",
            "task_description": "Core API endpoints deployed",
            "verification_criteria": ["API returns 200 on /health"],
            "dependencies_met": ["Database schema created"],
            "assigned_role": "engineering",
        }
        result = format_task_for_session(task)

        assert "Ship MVP" in result
        assert "Core API endpoints deployed" in result
        assert "engineering" in result
        assert "API returns 200 on /health" in result
        assert "Database schema created" in result

    def test_empty_dependencies(self):
        """Works correctly when no dependencies are met (root task)."""
        task = {
            "mission_name": "Research Phase",
            "task_id": "outcome-002-task-000",
            "task_description": "Competitive analysis",
            "verification_criteria": ["Brief published"],
            "dependencies_met": [],
            "assigned_role": "research",
        }
        result = format_task_for_session(task)

        assert "Research Phase" in result
        assert "Competitive analysis" in result
        assert "Completed dependencies" not in result

    def test_multiple_criteria(self):
        """Multiple verification criteria are all listed."""
        task = {
            "mission_name": "Launch",
            "task_id": "outcome-001-task-001",
            "task_description": "Deploy to production",
            "verification_criteria": [
                "Health check passes",
                "No errors in logs",
                "Response time under 200ms",
            ],
            "dependencies_met": [],
            "assigned_role": "engineering",
        }
        result = format_task_for_session(task)

        assert "Health check passes" in result
        assert "No errors in logs" in result
        assert "Response time under 200ms" in result
