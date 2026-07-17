"""Eval: CTO — work graph cycle detection works.

Tests the **capability** of the work_graph DAG primitives. A failure here
would signal `missing_skill` — the executor could deadlock on a malformed
mission.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.role_eval_runner import RoleEval, register


def _setup():
    return {}


def _execute(ctx):
    from cabinet.scripts.lib.work_graph import WorkGraph, WorkNode

    # Build a valid DAG: A → B → C
    # work_graph.validate() requires non-root nodes to have an assigned_role,
    # so seed all nodes with a role to focus this test on cycle/topo behaviour.
    valid = WorkGraph()
    for nid in ("A", "B", "C"):
        valid.add_node(WorkNode(id=nid, description=nid, assigned_role="engineering"))
    valid.add_edge("A", "B")
    valid.add_edge("B", "C")

    # Build an invalid cyclic graph: A → B → C → A
    cyclic = WorkGraph()
    for nid in ("A", "B", "C"):
        cyclic.add_node(WorkNode(id=nid, description=nid, assigned_role="engineering"))
    cyclic.add_edge("A", "B")
    cyclic.add_edge("B", "C")
    cyclic.add_edge("C", "A")

    return {
        "valid_errors": valid.validate(),
        "cyclic_errors": cyclic.validate(),
        "topo": valid.topological_sort(),
    }


def _verify(ctx, results):
    return [
        ("valid_dag_has_no_errors",
         results["valid_errors"] == [],
         "missing_skill"),
        ("cyclic_dag_detected",
         len(results["cyclic_errors"]) > 0,
         "missing_skill"),
        ("topo_sort_order_correct",
         results["topo"] == ["A", "B", "C"],
         "quality_gap"),
    ]


register(RoleEval(
    name="cto_dag_validates",
    role_slug="cto",
    category="capability",
    description="CTO's DAG primitives validate cycles and produce topo order.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
