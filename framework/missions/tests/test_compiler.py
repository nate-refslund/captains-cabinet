"""Tests for the mission compiler."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure framework root is importable
_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.missions.compiler import (
    compile_outcome,
    compile_from_yaml,
    _match_role_for_task,
    _infer_dependencies,
    _generate_task_id,
    _apply_status_from_events,
)
from framework.events.emitter import emit
from cabinet.scripts.lib.work_graph import WorkGraph, WorkNode, NodeStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Route event logs to a temp directory."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    # Ensure no DB writes
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
        {
            "slug": "operations",
            "title": "Chief Operations Officer",
            "capabilities": ["operations", "validates_deployments"],
        },
    ]


@pytest.fixture
def sample_outcome():
    """A basic outcome for testing."""
    return {
        "id": "outcome-001",
        "name": "Launch MVP",
        "description": "Ship the minimum viable product to first users",
        "measurable_criteria": [
            "Core API endpoints deployed and passing health checks",
            "User signup flow functional end-to-end",
            "Production database seeded with schema",
        ],
        "status": "active",
    }


@pytest.fixture
def outcomes_yaml_file(tmp_path):
    """Create a temporary outcomes YAML file."""
    content = """outcomes:
  - id: outcome-001
    name: Launch MVP
    measurable_criteria:
      - Core API endpoints deployed
      - User signup flow works
    status: active
  - id: outcome-002
    name: Research Competitors
    measurable_criteria:
      - Market analysis complete
      - Competitive brief published
    status: active
  - id: outcome-003
    name: Future Feature
    measurable_criteria:
      - Something cool
    status: draft
"""
    yaml_file = tmp_path / "outcomes.yml"
    yaml_file.write_text(content)
    return yaml_file


# ---------------------------------------------------------------------------
# Tests: compile_outcome
# ---------------------------------------------------------------------------


class TestCompileOutcome:
    def test_basic_compilation(self, sample_outcome, sample_roles):
        """compile_outcome returns a valid mission dict."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)

        assert "id" in mission
        assert mission["id"].startswith("mission-outcome-001-")
        assert mission["outcome_id"] == "outcome-001"
        assert mission["name"] == "Launch MVP"
        assert mission["status"] == "planning"
        assert isinstance(mission["work_graph"], WorkGraph)

    def test_task_count_matches_criteria(self, sample_outcome, sample_roles):
        """Each measurable criterion becomes a task node."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        assert len(graph.nodes) == 3

    def test_tasks_have_ids(self, sample_outcome, sample_roles):
        """Task IDs follow the deterministic pattern."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        expected_ids = [
            "outcome-001-task-000",
            "outcome-001-task-001",
            "outcome-001-task-002",
        ]
        assert sorted(graph.nodes.keys()) == sorted(expected_ids)

    def test_tasks_have_descriptions(self, sample_outcome, sample_roles):
        """Each task's description matches its criterion."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        for i, criterion in enumerate(sample_outcome["measurable_criteria"]):
            task_id = f"outcome-001-task-{i:03d}"
            assert graph.nodes[task_id].description == criterion

    def test_role_assignment(self, sample_outcome, sample_roles):
        """Tasks are assigned to roles based on capability matching."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        # "Core API endpoints deployed" should match engineering (deploy, api, endpoint)
        task_0 = graph.nodes["outcome-001-task-000"]
        assert task_0.assigned_role == "engineering"

        # "User signup flow" should match product (user, signup, flow)
        task_1 = graph.nodes["outcome-001-task-001"]
        assert task_1.assigned_role == "product"

        # "Production database seeded with schema" should match engineering (database, schema)
        task_2 = graph.nodes["outcome-001-task-002"]
        assert task_2.assigned_role == "engineering"

    def test_dependency_edges_exist(self, sample_outcome, sample_roles):
        """Dependencies are inferred between tasks."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        # Should have edges (sequential with reordering)
        assert len(graph.edges) == 2

    def test_graph_is_valid(self, sample_outcome, sample_roles):
        """The compiled work graph passes validation."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        # Validation requires non-root nodes to have assigned_role
        # Our test roles should cover assignments
        errors = graph.validate()
        assert errors == [], f"Graph validation errors: {errors}"

    def test_topological_sort_works(self, sample_outcome, sample_roles):
        """The compiled graph can be topologically sorted (no cycles)."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)
        graph = mission["work_graph"]

        order = graph.topological_sort()
        assert len(order) == 3

    def test_empty_criteria_raises(self, sample_roles):
        """Outcome with no criteria raises ValueError."""
        outcome = {
            "id": "outcome-empty",
            "name": "Empty",
            "measurable_criteria": [],
            "status": "active",
        }
        with pytest.raises(ValueError, match="no measurable_criteria"):
            compile_outcome(outcome, roles=sample_roles)

    def test_single_criterion(self, sample_roles):
        """Outcome with single criterion produces graph with one node, no edges."""
        outcome = {
            "id": "outcome-single",
            "name": "Single Task",
            "measurable_criteria": ["Deploy the thing"],
            "status": "active",
        }
        mission = compile_outcome(outcome, roles=sample_roles)
        graph = mission["work_graph"]

        assert len(graph.nodes) == 1
        assert len(graph.edges) == 0

    def test_event_emitted(self, sample_outcome, sample_roles, event_log_dir):
        """compile_outcome emits a mission_created event."""
        mission = compile_outcome(sample_outcome, roles=sample_roles)

        # Check that event log file was created
        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1

        events = []
        with open(log_files[0]) as f:
            for line in f:
                events.append(json.loads(line))

        assert len(events) == 1
        assert events[0]["event_type"] == "mission_created"
        assert events[0]["payload"]["mission_id"] == mission["id"]
        assert events[0]["payload"]["outcome_id"] == "outcome-001"
        assert events[0]["payload"]["task_count"] == 3

    def test_no_roles_available(self):
        """When no roles available, tasks get None assigned_role."""
        outcome = {
            "id": "outcome-noroles",
            "name": "No Roles",
            "measurable_criteria": ["Do something"],
            "status": "active",
        }
        mission = compile_outcome(outcome, roles=[])
        graph = mission["work_graph"]

        task = graph.nodes["outcome-noroles-task-000"]
        assert task.assigned_role is None


# ---------------------------------------------------------------------------
# Tests: compile_from_yaml
# ---------------------------------------------------------------------------


class TestCompileFromYaml:
    def test_compiles_active_outcomes(self, outcomes_yaml_file, sample_roles):
        """Only active outcomes are compiled."""
        missions = compile_from_yaml(outcomes_yaml_file, roles=sample_roles)

        # outcome-001 and outcome-002 are active, outcome-003 is draft
        assert len(missions) == 2

    def test_mission_ids_reference_outcomes(self, outcomes_yaml_file, sample_roles):
        """Each mission references its source outcome."""
        missions = compile_from_yaml(outcomes_yaml_file, roles=sample_roles)

        outcome_ids = {m["outcome_id"] for m in missions}
        assert outcome_ids == {"outcome-001", "outcome-002"}

    def test_file_not_found_raises(self, tmp_path, sample_roles):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            compile_from_yaml(tmp_path / "nonexistent.yml", roles=sample_roles)

    def test_invalid_yaml_raises(self, tmp_path, sample_roles):
        """YAML without outcomes key raises ValueError."""
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("something_else: true\n")
        with pytest.raises(ValueError, match="missing 'outcomes' key"):
            compile_from_yaml(bad_file, roles=sample_roles)

    def test_events_emitted_for_each(self, outcomes_yaml_file, sample_roles, event_log_dir):
        """Each compiled mission emits its own event."""
        missions = compile_from_yaml(outcomes_yaml_file, roles=sample_roles)

        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1

        events = []
        with open(log_files[0]) as f:
            for line in f:
                events.append(json.loads(line))

        assert len(events) == 2
        assert all(e["event_type"] == "mission_created" for e in events)


# ---------------------------------------------------------------------------
# Tests: helper functions
# ---------------------------------------------------------------------------


class TestMatchRoleForTask:
    def test_engineering_match(self, sample_roles):
        """API/deploy tasks match engineering role."""
        role = _match_role_for_task("Deploy API endpoints to production", sample_roles)
        assert role == "engineering"

    def test_product_match(self, sample_roles):
        """User-facing tasks match product role."""
        role = _match_role_for_task("User signup flow with onboarding", sample_roles)
        assert role == "product"

    def test_research_match(self, sample_roles):
        """Research tasks match research role."""
        role = _match_role_for_task("Complete competitive analysis brief", sample_roles)
        assert role == "research"

    def test_no_match_returns_none(self):
        """When no keywords match, returns None."""
        role = _match_role_for_task("Something very abstract", [])
        assert role is None


class TestInferDependencies:
    def test_empty_criteria(self):
        """No criteria means no dependencies."""
        assert _infer_dependencies([]) == []

    def test_single_criterion(self):
        """Single criterion means no dependencies."""
        assert _infer_dependencies(["Do one thing"]) == []

    def test_sequential_default(self):
        """Multiple criteria produce sequential dependencies."""
        criteria = ["Step one", "Step two", "Step three"]
        deps = _infer_dependencies(criteria)
        # All middle-phase, so sequential by original order
        assert len(deps) == 2

    def test_database_before_deploy(self):
        """Database tasks are ordered before deploy tasks."""
        criteria = [
            "Deploy to production",
            "Set up database schema",
            "Build the feature",
        ]
        deps = _infer_dependencies(criteria)
        # schema (phase 0) -> build (phase 1) -> deploy (phase 2)
        assert len(deps) == 2

        # The sorted order should put schema first, deploy last
        # deps are (from_idx, to_idx) in original index space
        # schema is index 1 (phase 0), feature is index 2 (phase 1), deploy is index 0 (phase 2)
        assert (1, 2) in deps  # schema -> build
        assert (2, 0) in deps  # build -> deploy


class TestGenerateTaskId:
    def test_deterministic(self):
        """IDs are deterministic from outcome + index."""
        assert _generate_task_id("outcome-001", 0) == "outcome-001-task-000"
        assert _generate_task_id("outcome-001", 5) == "outcome-001-task-005"
        assert _generate_task_id("outcome-abc", 99) == "outcome-abc-task-099"


# ---------------------------------------------------------------------------
# Phase 1.1: event-sourced status overlay
# ---------------------------------------------------------------------------


def _build_graph_with_tasks(outcome_id: str, count: int) -> WorkGraph:
    """Test helper: build a fresh in-memory graph with N pending tasks."""
    graph = WorkGraph()
    for i in range(count):
        graph.add_node(WorkNode(
            id=_generate_task_id(outcome_id, i),
            description=f"task {i}",
            assigned_role="engineering",
            status=NodeStatus.PENDING,
        ))
    return graph


class TestApplyStatusFromEvents:
    """Verify event-sourced overlay closes the per-session reset gap."""

    def test_no_events_no_change(self, event_log_dir):
        """With no events on disk, all nodes stay PENDING."""
        graph = _build_graph_with_tasks("outcome-x", 3)
        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 0
        for node in graph.nodes.values():
            assert node.status == NodeStatus.PENDING

    def test_completed_event_marks_done(self, event_log_dir):
        """work_item_completed event sets the node to DONE."""
        graph = _build_graph_with_tasks("outcome-x", 3)
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-x-task-001",
            "outcome_id": "outcome-x",
            "status": "done",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 1
        assert graph.nodes["outcome-x-task-000"].status == NodeStatus.PENDING
        assert graph.nodes["outcome-x-task-001"].status == NodeStatus.DONE
        assert graph.nodes["outcome-x-task-002"].status == NodeStatus.PENDING

    def test_failed_event_marks_failed(self, event_log_dir):
        """work_item_failed event sets the node to FAILED + verification_passed=False."""
        graph = _build_graph_with_tasks("outcome-x", 2)
        emit("work_item_failed", actor="engineering", payload={
            "task_id": "outcome-x-task-000",
            "outcome_id": "outcome-x",
            "status": "failed",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 1
        assert graph.nodes["outcome-x-task-000"].status == NodeStatus.FAILED
        assert graph.nodes["outcome-x-task-000"].verification_passed is False

    def test_verified_event_marks_done_and_verified(self, event_log_dir):
        """work_item_verified implies DONE + verification_passed=True."""
        graph = _build_graph_with_tasks("outcome-x", 2)
        emit("work_item_verified", actor="cos", payload={
            "task_id": "outcome-x-task-000",
            "outcome_id": "outcome-x",
            "status": "verified",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 1
        assert graph.nodes["outcome-x-task-000"].status == NodeStatus.DONE
        assert graph.nodes["outcome-x-task-000"].verification_passed is True

    def test_other_outcome_ignored(self, event_log_dir):
        """Events for a different outcome must not affect this graph."""
        graph = _build_graph_with_tasks("outcome-x", 2)
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-y-task-000",
            "outcome_id": "outcome-y",
            "status": "done",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 0
        for node in graph.nodes.values():
            assert node.status == NodeStatus.PENDING

    def test_unknown_task_id_skipped(self, event_log_dir):
        """An event referencing a task not in the graph is silently skipped."""
        graph = _build_graph_with_tasks("outcome-x", 2)
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-x-task-999",  # not in graph
            "outcome_id": "outcome-x",
            "status": "done",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        assert changed == 0

    def test_latest_event_wins(self, event_log_dir):
        """If failed then completed events arrive, latest (completed) wins."""
        graph = _build_graph_with_tasks("outcome-x", 1)
        emit("work_item_failed", actor="engineering", payload={
            "task_id": "outcome-x-task-000",
            "outcome_id": "outcome-x",
        })
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-x-task-000",
            "outcome_id": "outcome-x",
        })

        changed = _apply_status_from_events(graph, "outcome-x")
        # Two state changes: PENDING→FAILED then FAILED→DONE
        assert changed == 2
        assert graph.nodes["outcome-x-task-000"].status == NodeStatus.DONE

    def test_compile_outcome_integrates_overlay(self, event_log_dir, sample_roles):
        """compile_outcome must apply event-sourced status at the end."""
        outcome = {
            "id": "outcome-int",
            "name": "Integration",
            "measurable_criteria": [
                "Build API endpoints",
                "Deploy to production",
            ],
            "status": "active",
        }
        # Pre-emit a completion event for task 0
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-int-task-000",
            "outcome_id": "outcome-int",
        })

        mission = compile_outcome(outcome, roles=sample_roles)
        graph = mission["work_graph"]

        assert graph.nodes["outcome-int-task-000"].status == NodeStatus.DONE
        assert graph.nodes["outcome-int-task-001"].status == NodeStatus.PENDING
