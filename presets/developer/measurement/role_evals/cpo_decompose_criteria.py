"""Eval: CPO — an N-criterion outcome compiles to ≥N work nodes.

Tests the **capability** of the CPO role to translate measurable criteria
into actionable work. A failure signals `quality_gap` — criteria getting
collapsed or dropped during compilation.
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
    create_role("product", "Product", "Define product",
                capabilities=["product", "writes_specs"])
    create_role("engineering", "Engineering", "Build code",
                capabilities=["engineering", "deploys_code"])

    return {
        "outcome": {
            "id": "eval-cpo-decompose",
            "name": "Onboarding redesign",
            "description": "Three concrete improvements",
            "measurable_criteria": [
                "User signup flow ux polished",
                "Profile completion product flow live",
                "Onboarding flow code deploys to production",
                "Welcome ux email automated",
                "Activation feature metrics dashboard product live",
            ],
            "status": "active",
        }
    }


def _execute(ctx):
    from framework.missions.compiler import compile_outcome
    mission = compile_outcome(ctx["outcome"], actor="cpo_eval")
    graph = mission.get("work_graph")
    return {
        "node_count": len(graph.nodes) if graph else 0,
        "criteria_count": len(ctx["outcome"]["measurable_criteria"]),
    }


def _verify(ctx, results):
    return [
        ("nodes_at_least_criteria",
         results["node_count"] >= results["criteria_count"],
         "quality_gap"),
        ("nodes_not_zero", results["node_count"] > 0, "missing_skill"),
    ]


register(RoleEval(
    name="cpo_decompose_criteria",
    role_slug="cpo",
    category="capability",
    description="CPO outcome with N criteria compiles to ≥N work nodes.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
