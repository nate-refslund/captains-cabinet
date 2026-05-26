"""Session-to-mission bridge: connects officer sessions to the mission work graph.

Reads the active outcomes, compiles them via the mission compiler, and finds
the next ready task for the current officer's role.  This lets hooks inject
mission context into officer sessions so they know what to work on.

Usage:
    from framework.missions.session_bridge import get_next_task, format_task_for_session

    task = get_next_task("engineering", cabinet_root="/opt/founders-cabinet")
    if task:
        print(format_task_for_session(task))
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from cabinet.scripts.lib.work_graph import WorkGraph, NodeStatus
from framework.missions.compiler import compile_from_yaml


def _outcomes_path(cabinet_root: str | None = None) -> Path:
    """Resolve the path to the outcomes YAML file."""
    if cabinet_root is None:
        cabinet_root = os.environ.get(
            "CABINET_ROOT",
            str(Path(__file__).parent.parent.parent),
        )
    return Path(cabinet_root) / "instance" / "config" / "outcomes.yml"


def _dependencies_met(graph: WorkGraph, node_id: str) -> list[str]:
    """Return descriptions of completed dependencies for a node."""
    dep_ids = graph._deps.get(node_id, set())
    return [
        graph.nodes[d].description
        for d in dep_ids
        if graph.nodes[d].status == NodeStatus.DONE
    ]


def get_next_task(
    officer_slug: str,
    cabinet_root: str | None = None,
) -> dict[str, Any] | None:
    """Get the next ready task for this officer from active missions.

    Looks for ``instance/config/outcomes.yml``, compiles active outcomes into
    missions, then searches the resulting work graphs for tasks that are ready
    (all dependencies met) and assigned to *officer_slug*.

    Returns a task dict or ``None`` if nothing is ready.
    """
    outcomes_file = _outcomes_path(cabinet_root)
    if not outcomes_file.exists():
        return None

    try:
        missions = compile_from_yaml(outcomes_file, actor="session_bridge", roles=None)
    except (FileNotFoundError, ValueError):
        return None

    for mission in missions:
        graph: WorkGraph = mission["work_graph"]
        ready_nodes = graph.ready_tasks()

        for node in ready_nodes:
            if node.assigned_role == officer_slug:
                return {
                    "mission_name": mission["name"],
                    "task_id": node.id,
                    "task_description": node.description,
                    "verification_criteria": node.verification_criteria,
                    "dependencies_met": _dependencies_met(graph, node.id),
                    "assigned_role": node.assigned_role,
                }

    return None


def format_task_for_session(task: dict[str, Any]) -> str:
    """Format a task dict as a human-readable context string for injection."""
    lines = [
        f"Mission: {task['mission_name']}",
        f"Task: {task['task_description']}",
        f"Role: {task['assigned_role']}",
    ]

    if task.get("verification_criteria"):
        lines.append("Verification criteria:")
        for criterion in task["verification_criteria"]:
            lines.append(f"  - {criterion}")

    if task.get("dependencies_met"):
        lines.append("Completed dependencies:")
        for dep in task["dependencies_met"]:
            lines.append(f"  - {dep}")

    return "\n".join(lines)
