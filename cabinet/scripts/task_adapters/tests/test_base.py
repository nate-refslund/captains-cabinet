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
    NoOpTaskAdapter,
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
    def test_missing_tasks_block_returns_noop(self):
        """A project with no tasks block is a clean no-op, never an error.

        The active captains-cabinet project has no tasks block BY DESIGN
        (plugin-routed lanes omit it); raising here crash-looped the 900s
        task-sync launchd job."""
        adapter = get_adapter({})
        assert isinstance(adapter, NoOpTaskAdapter)
        assert adapter.destination == "none"

    @pytest.mark.parametrize("system", ["none", "plugin", "dev-tasks", "plugin:dev-tasks"])
    def test_no_sync_systems_return_noop(self, system):
        adapter = get_adapter({"tasks": {"system": system}})
        assert isinstance(adapter, NoOpTaskAdapter)
        assert adapter.system == system

    def test_unknown_system_raises(self):
        with pytest.raises(ValueError, match="Unknown task system"):
            get_adapter({"tasks": {"system": "not-a-real-system"}})

    def test_github_issues_returns_adapter(self):
        adapter = get_adapter({
            "tasks": {"system": "github-issues", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"repo": "owner/repo"}}
        })
        assert adapter.destination == "github-issues"
        assert adapter.repo == "owner/repo"

    def test_monday_raises_with_dev_tasks_message(self):
        """The cabinet's Monday adapter was removed in favor of a
        dev-tasks-style Claude plugin. Officers use the plugin's
        mcp__dev-tasks tools directly. The factory must explicitly tell
        the operator to use the plugin instead."""
        with pytest.raises(ValueError, match="dev-tasks"):
            get_adapter({
                "tasks": {"system": "monday", "config": {"board_id": 1234567}}
            })

    def test_jira_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "jira", "ownership": "self",
             "authority_basis": "my own tracker", "config": {
                "domain": "co", "email": "user@co", "project_key": "X"
            }}
        })
        assert adapter.destination == "jira"

    def test_linear_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "linear", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"team_id": "abc"}}
        })
        assert adapter.destination == "linear"

    def test_asana_returns_skeleton(self):
        adapter = get_adapter({
            "tasks": {"system": "asana", "ownership": "self",
             "authority_basis": "my own tracker", "config": {
                "workspace_id": "w", "project_gid": "p"
            }}
        })
        assert adapter.destination == "asana"


class TestAdapterContract:
    """Verify every adapter implements the abstract methods."""

    @pytest.mark.parametrize("config", [
        {"tasks": {"system": "github-issues", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"repo": "o/r"}}},
        # monday excluded — see TestGetAdapter.test_monday_raises_with_dev_tasks_message
        {"tasks": {"system": "jira", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"domain": "c", "email": "e", "project_key": "P"}}},
        {"tasks": {"system": "linear", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"team_id": "t"}}},
        {"tasks": {"system": "asana", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"workspace_id": "w", "project_gid": "p"}}},
    ])
    def test_adapter_implements_abstract_methods(self, config):
        adapter = get_adapter(config)
        # Verify it's a TaskAdapter subclass
        assert isinstance(adapter, TaskAdapter)
        # All abstract methods must be present (even if NotImplementedError)
        for method_name in ("health_check", "pull", "push", "delete", "link"):
            assert hasattr(adapter, method_name)
            assert callable(getattr(adapter, method_name))


class TestNoOpAdapter:
    """The no-op adapter must be a complete, harmless TaskAdapter."""

    def test_contract_and_noop_behaviour(self):
        adapter = get_adapter({})
        assert isinstance(adapter, TaskAdapter)
        assert adapter.health_check() is True
        assert adapter.pull() == []
        assert adapter.push(CanonicalTask(canonical_id="x", title="t")) == ""
        assert adapter.delete("123") is None
        assert adapter.link("x", "123") is None

    def test_info_line_goes_to_stderr(self, capsys):
        get_adapter({})
        captured = capsys.readouterr()
        assert "no external task system" in captured.err
        assert captured.out == ""  # stdout stays clean for runner JSON


class TestRunnerNoOp:
    """task_sync_runner must return cleanly (exit 0) for no-sync projects."""

    def _seed_project(self, tmp_path, monkeypatch, project_yaml: str) -> None:
        config = tmp_path / "instance" / "config"
        (config / "projects").mkdir(parents=True)
        (config / "active-project.txt").write_text("test-proj\n")
        (config / "projects" / "test-proj.yml").write_text(project_yaml)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        monkeypatch.delenv("DATABASE_URL", raising=False)

    def test_runner_clean_for_missing_tasks_block(self, tmp_path, monkeypatch):
        """Current live shape: project config with NO tasks block at all."""
        self._seed_project(tmp_path, monkeypatch, "product:\n  name: Test Proj\n")
        from cabinet.scripts import task_sync_runner

        result = task_sync_runner.run_sync()
        assert result.errors == []
        assert result.pulled == 0
        assert result.destination == "none"

        assert task_sync_runner.main([]) == 0  # exit code 0, no crash-loop

    def test_runner_clean_for_plugin_system(self, tmp_path, monkeypatch):
        self._seed_project(
            tmp_path, monkeypatch,
            "product:\n  name: Test Proj\ntasks:\n  system: plugin\n",
        )
        from cabinet.scripts import task_sync_runner

        result = task_sync_runner.run_sync()
        assert result.errors == []
        assert task_sync_runner.main([]) == 0


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
            "tasks": {"system": "jira", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"domain": "c", "email": "e", "project_key": "P"}}
        })
        with pytest.raises(NotImplementedError):
            adapter.pull()

    def test_linear_push_raises_with_archive_warning(self):
        adapter = get_adapter({
            "tasks": {"system": "linear", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"team_id": "t"}}
        })
        with pytest.raises(NotImplementedError, match="read-only archive"):
            adapter.push(CanonicalTask(canonical_id="x", title="t"))

    def test_asana_delete_raises(self):
        adapter = get_adapter({
            "tasks": {"system": "asana", "ownership": "self",
             "authority_basis": "my own tracker", "config": {"workspace_id": "w", "project_gid": "p"}}
        })
        with pytest.raises(NotImplementedError):
            adapter.delete("123")
