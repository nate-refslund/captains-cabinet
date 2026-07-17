"""Eval: CoS — re-running the supervisor never re-routes an assigned task.

Tests the **quality** of the supervisor's idempotency. A failure here signals
`quality_gap` — duplicate Redis pushes would spam officers with stale tasks.
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
    (Path(tmp) / "instance" / "config").mkdir(parents=True)

    # Roles to assign against
    from framework.roles.lifecycle import create_role
    create_role("engineering", "Engineering", "Build code",
                capabilities=["engineering", "deploys_code"])

    # Outcomes file with one outcome → multiple tasks
    (Path(tmp) / "instance" / "config" / "outcomes.yml").write_text(
        "outcomes:\n"
        "  - id: eval-outcome-cos-route\n"
        "    name: Idempotency check\n"
        "    measurable_criteria:\n"
        "      - Engineering deploys code endpoint\n"
        "      - Frontend code build deploys to production\n"
        "    status: active\n"
        "    captain_ratified: true\n"
    )
    return {"tmp": tmp}


def _execute(ctx):
    from framework.missions.supervisor import (
        confirm_delivered_assignments,
        route_pending_tasks,
    )

    first = route_pending_tasks()
    confirm_delivered_assignments(first)
    second = route_pending_tasks()
    third = route_pending_tasks()

    return {
        "first_count": len(first),
        "second_count": len(second),
        "third_count": len(third),
    }


def _verify(ctx, results):
    return [
        ("first_pass_routes_at_least_one", results["first_count"] >= 1, "quality_gap"),
        ("second_pass_routes_zero", results["second_count"] == 0, "quality_gap"),
        ("third_pass_routes_zero", results["third_count"] == 0, "quality_gap"),
    ]


register(RoleEval(
    name="cos_route_idempotent",
    role_slug="cos",
    category="quality",
    description="Mission supervisor is idempotent across repeated runs.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
