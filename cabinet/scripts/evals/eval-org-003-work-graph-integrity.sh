#!/bin/bash
# eval-org-003: Work graph integrity — no cycles, all nodes reachable, roles assigned
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

python3 - "$CABINET_ROOT" << 'PY'
import sys, os

cabinet_root = sys.argv[1]
sys.path.insert(0, os.path.join(cabinet_root, 'cabinet/scripts/lib'))

from work_graph import WorkGraph, WorkNode, NodeStatus

errors = []

# Test 1: Valid linear DAG
g = WorkGraph()
g.add_node(WorkNode(id="a", description="Task A", assigned_role="cto"))
g.add_node(WorkNode(id="b", description="Task B", assigned_role="cto"))
g.add_node(WorkNode(id="c", description="Task C", assigned_role="cpo"))
g.add_edge("a", "b")
g.add_edge("b", "c")
errs = g.validate()
if errs:
    errors.append(f"Valid linear DAG reported errors: {errs}")

# Test 2: Cycle detection
g2 = WorkGraph()
g2.add_node(WorkNode(id="x", description="X", assigned_role="cto"))
g2.add_node(WorkNode(id="y", description="Y", assigned_role="cto"))
g2.add_node(WorkNode(id="z", description="Z", assigned_role="cto"))
g2.add_edge("x", "y")
g2.add_edge("y", "z")
g2.add_edge("z", "x")
errs2 = g2.validate()
cycle_found = any("cycle" in e.lower() for e in errs2)
if not cycle_found:
    errors.append("Cycle not detected in cyclic graph")

# Test 3: Ready tasks
g3 = WorkGraph()
g3.add_node(WorkNode(id="r1", description="Root 1", assigned_role="cto"))
g3.add_node(WorkNode(id="r2", description="Root 2", assigned_role="cpo"))
g3.add_node(WorkNode(id="leaf", description="Leaf", assigned_role="cto"))
g3.add_edge("r1", "leaf")
g3.add_edge("r2", "leaf")
ready = g3.ready_tasks()
ready_ids = {n.id for n in ready}
if ready_ids != {"r1", "r2"}:
    errors.append(f"Ready tasks should be {{r1, r2}} but got {ready_ids}")

# Test 4: Complete task updates readiness
g3.complete_task("r1")
ready2 = g3.ready_tasks()
ready2_ids = {n.id for n in ready2}
if "leaf" in ready2_ids:
    errors.append("Leaf should not be ready (r2 still pending)")
if "r2" not in ready2_ids:
    errors.append("r2 should still be ready")
g3.complete_task("r2")
ready3 = g3.ready_tasks()
ready3_ids = {n.id for n in ready3}
if "leaf" not in ready3_ids:
    errors.append("Leaf should be ready after both deps complete")

# Test 5: JSON round-trip
g4 = WorkGraph()
g4.add_node(WorkNode(id="a", description="A", assigned_role="cos"))
g4.add_node(WorkNode(id="b", description="B", assigned_role="cto"))
g4.add_edge("a", "b")
json_str = g4.to_json()
g5 = WorkGraph.from_json(json_str)
if set(g5.nodes.keys()) != {"a", "b"}:
    errors.append("JSON round-trip lost nodes")
if len(g5.edges) != 1:
    errors.append("JSON round-trip lost edges")

# Test 6: Topological sort
order = g.topological_sort()
if order.index("a") > order.index("b") or order.index("b") > order.index("c"):
    errors.append(f"Topological sort wrong: {order}")

if errors:
    for e in errors:
        print(f"  FAIL: {e}")
    print(f"FAIL: {len(errors)} work graph integrity errors")
    sys.exit(1)

print("OK: Work graph integrity verified (6 checks)")
PY
