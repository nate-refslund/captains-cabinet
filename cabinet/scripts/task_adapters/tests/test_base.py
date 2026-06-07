"""Tests for the task adapter base interface + factory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from cabinet.scripts.task_adapters.base import (
    CanonicalTask,
    TaskAdapter,
    SyncResult,
    get_adapter,
)


class TestCanonicalTask:
    def test_minimal_construction(self):
        t = CanonicalTask(canonical_id="x-task-001", title="Hello")
        assert t.canonical_id == "x-task-001"
        assert t.title == "Hello"
        assert t.status == "open"
        assert t.priority == "normal"
        assert t.tags == []
        assert t.metadata == {}

    def test_full_construction(self):
        t = CanonicalTask(
            canonical_id="x-task-002",
            title="Test",
            description="Body",
            status="in_progress",
            assigned_role="engineering",
            priority="high",
            due_at="2026-06-01T00:00:00Z",
            tags=["bug", "p1"],
            external_id="42",
            external_url="https://example.com/42",
            metadata={"created_by": "captain"},
        )
        assert t.status == "in_progress"
        assert t.tags == ["bug", "p1"]
        assert t.metadata["created_by"] == "captain"


class TestSyncResult:
    def test_default_construction(self):
        r = SyncResult(destination="github-issues")
        assert r.destination == "github-issues"
        assert r.pulled == 0
        assert r.pushed == 0
        assert r.conflicts == 0
        assert r.errors == []


class TestGetAdapter:
    def test_missing_system_raises(self):
        with pytest.raises(ValueError, match="missing tasks.system"):
            get_adapter({})

    def test_unknown_system_raises(self):
        with pytest.raises(ValueError, match="Unknown task system"):
            get_adapter({"tasks": {"system": "not-a-real-system"}})

    def test_github_issues_returns_adapter(self):
        adapter = get_adapter({
            "tasks": {"system": "github-issues", "config": {"repo": "owner/repo"}}
        })
        assert adapter.destination == "github-issues"
        assert adapter.repo == "owner/repo"

    def test_monday_raises_with_dev_tasks_message(self):
        """The cabinet's Monday adapter was removed in favor of the
        STEP-Network/dev-tasks Claude plugin. Officers use the plugin's
        mcp__dev-tasks tools directly. The factory must explicitly tell
        the operator to use the plugin instead."""
        with pytest.raises(ValueError, match="dev-tasks"):
            get_adapter({
                "tasks": {"system": "monday", "config": {"board_id": 1234567}}
            })

    def test_jira_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "jira", "config": {
                "domain": "co", "email": "user@co", "project_key": "X"
            }}
        })
        assert adapter.destination == "jira"

    def test_linear_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "linear", "config": {"team_id": "abc"}}
        })
        assert adapter.destination == "linear"

    def test_asana_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "asana", "config": {
                "workspace_id": "w", "project_gid": "p"
            }}
        })
        assert adapter.destination == "asana"


class TestAdapterContract:
    """Verify every adapter implements the abstract methods."""

    @pytest.mark.parametrize("config", [
        {"tasks": {"system": "github-issues", "config": {"repo": "o/r"}}},
        # monday excluded — see TestGetAdapter.test_monday_raises_with_dev_tasks_message
        {"tasks": {"system": "jira", "config": {"domain": "c", "email": "e", "project_key": "P"}}},
        {"tasks": {"system": "linear", "config": {"team_id": "t"}}},
        {"tasks": {"system": "asana", "config": {"workspace_id": "w", "project_gid": "p"}}},
    ])
    def test_adapter_implements_abstract_methods(self, config):
        adapter = get_adapter(config)
        # Verify it's a TaskAdapter subclass
        assert isinstance(adapter, TaskAdapter)
        # All abstract methods must be present (even if NotImplementedError)
        for method_name in ("health_check", "pull", "push", "delete", "link"):
            assert hasattr(adapter, method_name)
            assert callable(getattr(adapter, method_name))


class TestSkeletonsRaiseNotImplemented:
    """Skeleton adapters should explicitly NotImplementedError on the write path."""

    def test_monday_factory_raises_value_error(self):
        """Monday adapter is removed entirely; factory raises ValueError
        directing the operator to the dev-tasks plugin."""
        with pytest.raises(ValueError, match="dev-tasks"):
            get_adapter({
                "tasks": {"system": "monday", "config": {"board_id": 1}}
            })

    def test_jira_pull_raises(self):
        adapter = get_adapter({
            "tasks": {"system": "jira", "config": {"domain": "c", "email": "e", "project_key": "P"}}
        })
        with pytest.raises(NotImplementedError):
            adapter.pull()

    def test_linear_push_raises_with_archive_warning(self):
        adapter = get_adapter({
            "tasks": {"system": "linear", "config": {"team_id": "t"}}
        })
        with pytest.raises(NotImplementedError, match="read-only archive"):
            adapter.push(CanonicalTask(canonical_id="x", title="t"))

    def test_asana_delete_raises(self):
        adapter = get_adapter({
            "tasks": {"system": "asana", "config": {"workspace_id": "w", "project_gid": "p"}}
        })
        with pytest.raises(NotImplementedError):
            adapter.delete("123")
