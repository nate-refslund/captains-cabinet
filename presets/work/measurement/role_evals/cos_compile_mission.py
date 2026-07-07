"""Eval: CoS — given a Captain outcome, compile it into a valid mission.

Tests the **capability** of the CoS role to drive the goal-to-mission pipeline.
A failure here typically signals `missing_skill` (compiler logic regression)
or `quality_gap` (graph isn't well-formed).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.role_eval_runner import RoleEval, register


def _setup():
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"
    (Path(tmp) / "instance" / "roles" / "active").mkdir(parents=True)

    from framework.roles.lifecycle import create_role
    create_role("engineering", "Engineering", "Build product code",
                capabilities=["engineering", "deploys_code"])
    create_role("product", "Product", "Define product surface",
                capabilities=["product", "writes_specs"])

    return {
        "outcome": {
            "id": "eval-outcome-cos-001",
            "name": "Ship the auth API",
            "description": "Backend auth endpoints behind the user signup flow",
            "measurable_criteria": [
                "Backend api endpoint compiles and runs",
                "User signup flow integrated end-to-end",
                "Deploy to production passes health check",
            ],
            "status": "active",
            "captain_ratified": True,
        }
    }


def _execute(ctx):
    from framework.missions.compiler import compile_outcome
    mission = compile_outcome(ctx["outcome"], actor="cos_eval")
    return {"mission": mission}


def _verify(ctx, results):
    mission = results.get("mission")
    if mission is None:
        return [("mission_compiled", False, "missing_skill")]

    graph = mission.get("work_graph")
    nodes = list(graph.nodes.values()) if graph else []

    return [
        ("mission_compiled", mission is not None, "n/a"),
        ("has_work_graph", graph is not None, "missing_skill" if not graph else "n/a"),
        ("has_nodes", len(nodes) > 0, "quality_gap" if not nodes else "n/a"),
        ("graph_no_cycles", graph is not None and len(graph.validate()) == 0, "quality_gap"),
        ("all_nodes_assigned",
         all(n.assigned_role for n in nodes),
         "quality_gap"),
        ("status_planning", mission.get("status") == "planning", "n/a"),
    ]


register(RoleEval(
    name="cos_compile_mission",
    role_slug="cos",
    category="capability",
    description="CoS compiles a Captain outcome into a valid, role-assigned mission DAG.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
