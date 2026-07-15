"""Tests for the mission supervisor routing logic."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.missions.supervisor import (
    find_unassigned_ready_tasks,
    route_pending_tasks,
    already_assigned_ids,
    already_unroutable_ids,
    confirm_delivered_assignments,
)
from framework.events.emitter import emit, replay


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Route every test to a fresh event log and instance dir."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / "instance" / "config").mkdir(parents=True)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)


@pytest.fixture
def outcomes_yml(tmp_path):
    """Write a small outcomes.yml with one active outcome → 3 ready tasks."""
    yml = tmp_path / "instance" / "config" / "outcomes.yml"
    yml.write_text("""outcomes:
  - id: outcome-test
    name: Test outcome
    description: For supervisor tests
    measurable_criteria:
      - Engineering code builds and deploys
      - User signup flow functional
      - Frontend ux flow polished
    status: active
    captain_ratified: true
""")
    return yml


@pytest.fixture
def seeded_roles(tmp_path):
    """Create three active roles with capabilities the compiler can match."""
    from framework.roles.lifecycle import create_role
    create_role("engineering", "Engineering", "Build and ship code",
                capabilities=["engineering", "deploys_code"])
    create_role("product", "Product", "Design user flows",
                capabilities=["product", "writes_specs"])
    create_role("operations", "Operations", "Run reliable infra",
                capabilities=["validates_deployments", "monitors_systems"])


@pytest.fixture
def ghost_outcomes_yml(tmp_path):
    """Outcome with one ghost-role task and one in-roster control task.

    `depends_on: []` on the first criterion switches the compiler to
    explicit-deps mode, so no sequential edges are inferred and BOTH tasks
    are immediately ready.
    """
    yml = tmp_path / "instance" / "config" / "outcomes.yml"
    yml.write_text("""outcomes:
  - id: outcome-ghost
    name: Ghost routing
    description: For ghost-role supervisor tests
    measurable_criteria:
      - node_id: ghost-task
        title: Task owned by a role that does not exist
        owner_role: ghost-role
        depends_on: []
      - node_id: control-task
        title: Task owned by an in-roster role
        owner_role: engineering
    status: active
    captain_ratified: true
""")
    return yml


# ---------------------------------------------------------------------------
# Already-assigned IDs
# ---------------------------------------------------------------------------


class TestAlreadyAssigned:
    def test_empty_log_returns_empty_set(self):
        assert already_assigned_ids() == set()

    def test_collects_task_ids_from_events(self):
        emit("work_item_assigned", actor="supervisor", payload={
            "task_id": "outcome-x-task-001",
            "mission_id": "m1",
            "outcome_id": "outcome-x",
            "assigned_role": "engineering",
            "description": "...",
        })
        emit("work_item_assigned", actor="supervisor", payload={
            "task_id": "outcome-x-task-002",
            "mission_id": "m1",
            "outcome_id": "outcome-x",
            "assigned_role": "engineering",
            "description": "...",
        })
        assert already_assigned_ids() == {
            "outcome-x-task-001",
            "outcome-x-task-002",
        }

    def test_ignores_other_event_types(self):
        emit("work_item_completed", actor="engineering", payload={
            "task_id": "outcome-x-task-001",
            "outcome_id": "outcome-x",
        })
        # completed events are NOT assignments
        assert already_assigned_ids() == set()


# ---------------------------------------------------------------------------
# find_unassigned_ready_tasks
# ---------------------------------------------------------------------------


class TestFindUnassignedReady:
    def test_missing_outcomes_file_returns_empty(self):
        assert find_unassigned_ready_tasks() == []

    def test_returns_ready_tasks_with_assigned_roles(
        self, outcomes_yml, seeded_roles,
    ):
        decisions = find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert len(decisions) >= 1  # at least the first ready task per dep order
        for d in decisions:
            assert d["officer"]  # role assigned
            assert d["task_id"].startswith("outcome-test-task-")
            assert d["outcome_id"] == "outcome-test"

    def test_skips_already_assigned(self, outcomes_yml, seeded_roles):
        # First pass: find a ready task
        first_pass = find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert len(first_pass) >= 1
        first_task = first_pass[0]

        # Manually emit assignment to simulate prior routing
        emit("work_item_assigned", actor="supervisor", payload={
            "task_id": first_task["task_id"],
            "mission_id": first_task["mission_id"],
            "outcome_id": first_task["outcome_id"],
            "assigned_role": first_task["officer"],
            "description": first_task["description"],
        })

        # Second pass should not include that task
        second_pass = find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert first_task["task_id"] not in [d["task_id"] for d in second_pass]

    def test_completed_task_doesnt_appear(self, outcomes_yml, seeded_roles):
        """work_item_completed events also short-circuit routing (via compiler overlay)."""
        # Identify the first ready task
        decisions = find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert decisions, "need at least one ready task to test against"
        first = decisions[0]

        # Mark it completed via the event ledger
        emit("work_item_completed", actor="engineering", payload={
            "task_id": first["task_id"],
            "outcome_id": first["outcome_id"],
            "status": "done",
        })

        # Next pass should not include the completed task
        next_pass = find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert first["task_id"] not in [d["task_id"] for d in next_pass]


# ---------------------------------------------------------------------------
# route_pending_tasks (projection only)
# ---------------------------------------------------------------------------


class TestRoutePendingTasks:
    def test_default_is_projection_only(self, outcomes_yml, seeded_roles):
        decisions = route_pending_tasks(outcomes_path=outcomes_yml)
        assert len(decisions) >= 1
        assert replay(event_types=["work_item_assigned"]) == []

    def test_dry_run_returns_decisions_without_emitting(
        self, outcomes_yml, seeded_roles,
    ):
        decisions = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        assert len(decisions) >= 1
        # No assignment events should have been written
        events = replay(event_types=["work_item_assigned"])
        assert events == []

    def test_projection_repeats_until_delivery_is_confirmed(
        self, outcomes_yml, seeded_roles,
    ):
        first = route_pending_tasks(outcomes_path=outcomes_yml)
        assert len(first) >= 1
        assert route_pending_tasks(outcomes_path=outcomes_yml)
        confirm_delivered_assignments(first, outcomes_path=outcomes_yml)
        assert route_pending_tasks(outcomes_path=outcomes_yml) == []

    def test_direct_assignment_mode_is_refused(self, outcomes_yml, seeded_roles):
        with pytest.raises(ValueError, match="direct assignment recording is disabled"):
            route_pending_tasks(outcomes_path=outcomes_yml, dry_run=False)

    def test_unmatched_roles_skip_silently(self, outcomes_yml):
        """When no roles match the criteria, no routing happens; no crash."""
        # No seeded_roles fixture this time — instance/roles/active is empty.
        decisions = route_pending_tasks(outcomes_path=outcomes_yml)
        # All nodes will have assigned_role = None, so nothing to route
        assert decisions == []


class TestDeliveryConfirmation:
    def test_projection_then_confirmation_emits_assignment(
        self, outcomes_yml, seeded_roles,
    ):
        delivered = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        assert delivered
        assert replay(event_types=["work_item_assigned"]) == []
        confirmed = confirm_delivered_assignments(
            delivered, outcomes_path=outcomes_yml,
        )
        assert [row["task_id"] for row in confirmed] == [row["task_id"] for row in delivered]
        assigned = replay(event_types=["work_item_assigned"])
        assert {e["payload"]["task_id"] for e in assigned} == {
            row["task_id"] for row in delivered
        }
        assert all(e["payload"]["delivery"] == "redis_stream_confirmed" for e in assigned)

    def test_failed_delivery_path_leaves_task_routable(
        self, outcomes_yml, seeded_roles,
    ):
        projected = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        # Simulate Redis failure: no confirmation call.
        assert replay(event_types=["work_item_assigned"]) == []
        rerouted = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        stable = lambda row: {k: row[k] for k in ("task_id", "officer", "outcome_id", "description")}
        assert [stable(row) for row in rerouted] == [stable(row) for row in projected]

    def test_confirmation_refuses_forged_or_stale_decision(
        self, outcomes_yml, seeded_roles,
    ):
        projected = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        forged = [dict(projected[0], officer="ghost-role")]
        with pytest.raises(ValueError, match="stale or does not match"):
            confirm_delivered_assignments(forged, outcomes_path=outcomes_yml)
        assert replay(event_types=["work_item_assigned"]) == []

    def test_confirmation_is_idempotent(self, outcomes_yml, seeded_roles):
        projected = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        assert confirm_delivered_assignments(projected, outcomes_path=outcomes_yml)
        assert confirm_delivered_assignments(projected, outcomes_path=outcomes_yml) == []
        assert len(replay(event_types=["work_item_assigned"])) == len(projected)


# ---------------------------------------------------------------------------
# mission_created emission policy (projection vs materialization)
# ---------------------------------------------------------------------------


class TestMissionEventEmission:
    def test_dry_run_emits_zero_mission_created(self, outcomes_yml, seeded_roles):
        """--dry-run is a pure projection — zero ledger spam."""
        decisions = route_pending_tasks(outcomes_path=outcomes_yml, dry_run=True)
        assert len(decisions) >= 1  # the projection still finds work
        assert replay(event_types=["mission_created"]) == []

    def test_find_unassigned_defaults_to_projection(self, outcomes_yml, seeded_roles):
        find_unassigned_ready_tasks(outcomes_path=outcomes_yml)
        assert replay(event_types=["mission_created"]) == []

    def test_confirmation_materializes_mission_created(
        self, outcomes_yml, seeded_roles,
    ):
        """Only delivery confirmation is the materializing compile."""
        projected = route_pending_tasks(outcomes_path=outcomes_yml)
        confirm_delivered_assignments(projected, outcomes_path=outcomes_yml)
        events = replay(event_types=["mission_created"])
        assert len(events) == 1  # one active outcome in the fixture
        assert events[0]["payload"]["outcome_id"] == "outcome-test"


# ---------------------------------------------------------------------------
# Ghost roles (assigned_role not in the active roster)
# ---------------------------------------------------------------------------


class TestGhostRoleRouting:
    def test_ghost_role_skipped_and_unroutable_emitted(
        self, ghost_outcomes_yml, seeded_roles, capsys,
    ):
        decisions = route_pending_tasks(outcomes_path=ghost_outcomes_yml)
        routed_ids = [d["task_id"] for d in decisions]

        # In-roster control routes; ghost-role task is skipped
        assert "control-task" in routed_ids
        assert "ghost-task" not in routed_ids

        # No work_item_assigned for the ghost task — it must stay routable
        assigned = replay(event_types=["work_item_assigned"])
        assert "ghost-task" not in {
            (e.get("payload") or {}).get("task_id") for e in assigned
        }

        # Exactly one work_item_unroutable event, carrying the ghost role
        unroutable = replay(event_types=["work_item_unroutable"])
        assert len(unroutable) == 1
        payload = unroutable[0]["payload"]
        assert payload["task_id"] == "ghost-task"
        assert payload["assigned_role"] == "ghost-role"
        assert payload["outcome_id"] == "outcome-ghost"

        # Warning goes to stderr, never stdout (--json contract)
        captured = capsys.readouterr()
        assert "ghost-role" in captured.err
        assert "ghost-role" not in captured.out

    def test_unroutable_emission_idempotent_on_rerun(
        self, ghost_outcomes_yml, seeded_roles,
    ):
        route_pending_tasks(outcomes_path=ghost_outcomes_yml)
        route_pending_tasks(outcomes_path=ghost_outcomes_yml)
        route_pending_tasks(outcomes_path=ghost_outcomes_yml)

        unroutable = replay(event_types=["work_item_unroutable"])
        assert len(unroutable) == 1  # deduped via replay, like already_assigned_ids
        assert already_unroutable_ids() == {"ghost-task"}

    def test_skipped_task_routes_after_role_is_seeded(
        self, ghost_outcomes_yml, seeded_roles,
    ):
        first = route_pending_tasks(outcomes_path=ghost_outcomes_yml)
        assert "ghost-task" not in [d["task_id"] for d in first]
        confirm_delivered_assignments(first, outcomes_path=ghost_outcomes_yml)

        # Captain creates the missing role — the task must resurface
        from framework.roles.lifecycle import create_role
        create_role("ghost-role", "Ghost", "Now exists",
                    capabilities=["engineering"])

        second = route_pending_tasks(outcomes_path=ghost_outcomes_yml)
        routed = {d["task_id"]: d["officer"] for d in second}
        assert routed.get("ghost-task") == "ghost-role"

        confirm_delivered_assignments(second, outcomes_path=ghost_outcomes_yml)

        assigned = replay(event_types=["work_item_assigned"])
        assert "ghost-task" in {
            (e.get("payload") or {}).get("task_id") for e in assigned
        }


# ---------------------------------------------------------------------------
# CLI shape (smoke test the JSON output)
# ---------------------------------------------------------------------------


class TestCli:
    def test_main_prints_json(
        self, outcomes_yml, seeded_roles, capsys, monkeypatch,
    ):
        from framework.missions.supervisor import main

        # Point the module's _outcomes_path() lookup at our test file by
        # overriding CABINET_ROOT (already done in isolated_env).
        main(["--json", "--dry-run", "--outcomes", str(outcomes_yml)])
        captured = capsys.readouterr()
        decisions = json.loads(captured.out.strip())
        assert isinstance(decisions, list)
        # dry-run with no prior assignments — should have at least one decision
        assert len(decisions) >= 1
        assert all("task_id" in d for d in decisions)
