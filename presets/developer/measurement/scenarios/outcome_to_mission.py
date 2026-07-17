"""Scenario: Captain declares an outcome → Cabinet produces a valid mission.

Tests: Can the org runtime compile a vague goal into an executable work graph?
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Set up a clean environment with roles available."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"

    # Create roles that the mission compiler can assign to
    from framework.roles.lifecycle import create_role
    create_role("engineering", "Engineering", "Build and ship product code",
                capabilities=["writes_code", "deploys_code", "reviews_code"])
    create_role("product", "Product", "Define what to build and why",
                capabilities=["writes_specs", "manages_backlog", "user_research"])
    create_role("operations", "Operations", "Keep systems running reliably",
                capabilities=["monitors_systems", "manages_infra", "validates_deployments"])

    outcome = {
        "id": "test-outcome-001",
        "name": "Ship user onboarding flow",
        "description": "New users can sign up, complete profile, and reach the main dashboard",
        "measurable_criteria": [
            "User signup flow functional end-to-end",
            "Profile completion ux flow functional",
            "Dashboard loads for new users",
            "Frontend code build deploys to production",
        ],
        "status": "active",
        "captain_ratified": True,
    }

    return {"outcome": outcome, "tmp": tmp}


def _execute(context):
    """Compile the outcome into a mission."""
    from framework.missions.compiler import compile_outcome
    outcome = context["outcome"]
    mission = compile_outcome(outcome)
    return {"mission": mission}


def _verify(context, results):
    """Verify the mission is valid and complete."""
    mission = results.get("mission")
    assertions = []

    # Mission exists
    assertions.append(("mission_created", mission is not None))
    if mission is None:
        return assertions

    # Mission has correct metadata
    assertions.append(("has_name", bool(mission.get("name"))))
    assertions.append(("has_outcome_id", mission.get("outcome_id") == context["outcome"]["id"]))
    assertions.append(("status_is_planning", mission.get("status") == "planning"))

    # Work graph exists and is valid
    graph = mission.get("work_graph")
    assertions.append(("has_work_graph", graph is not None))

    if graph:
        nodes = list(graph.nodes.values())
        assertions.append(("has_nodes", len(nodes) > 0))
        assertions.append(("nodes_match_criteria",
                          len(nodes) >= len(context["outcome"]["measurable_criteria"])))

        # All nodes have assigned roles
        assigned = [n for n in nodes if n.assigned_role]
        assertions.append(("all_nodes_assigned", len(assigned) == len(nodes)))

        # No cycles in graph (validate returns empty list if valid)
        assertions.append(("no_cycles", len(graph.validate()) == 0))

        # All assigned roles actually exist
        from framework.roles.lifecycle import load_role
        valid_roles = all(
            load_role(n.assigned_role) is not None
            for n in nodes if n.assigned_role
        )
        assertions.append(("assigned_roles_exist", valid_roles))

    # Event was emitted
    from framework.events.emitter import replay
    events = replay(event_types=["mission_created"])
    assertions.append(("event_emitted", len(events) >= 1))

    return assertions


register(Scenario(
    name="outcome_to_mission",
    description="Captain declares an outcome, Cabinet compiles it into a valid mission with work graph",
    category="mission",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
