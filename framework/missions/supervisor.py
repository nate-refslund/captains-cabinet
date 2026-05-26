"""Mission supervisor: event-sourced router for ready work-graph tasks.

Phase 1.2 of the convergence plan. Closes the outer mission loop: scans
compiled missions, identifies ready tasks not yet assigned (via
`work_item_assigned` event replay), and returns routing decisions for a
shell wrapper to push as Redis Stream triggers.

Design choices:

- **No Postgres required.** The event ledger is the source of truth for
  both completion (`work_item_completed/failed/verified`) and assignment
  (`work_item_assigned`). The compiler already overlays completion status;
  this module adds the assignment-idempotency layer.

- **Idempotent.** Re-running the supervisor never re-routes a task that
  has already been assigned. Safe to schedule every minute.

- **Separation of concerns.** This module returns *routing decisions* as
  plain dicts. The shell wrapper in `cabinet/cron/mission-supervisor.sh`
  calls `trigger_send` to push Redis Stream messages. Tests can exercise
  the Python here without needing Redis.

Usage:
    from framework.missions.supervisor import route_pending_tasks
    routed = route_pending_tasks()  # emits work_item_assigned + returns list

    # CLI (for the shell wrapper):
    python3 -m framework.missions.supervisor --json
    python3 -m framework.missions.supervisor --json --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay
from framework.missions.compiler import compile_from_yaml
from framework.missions.session_bridge import _outcomes_path


def already_assigned_ids() -> set[str]:
    """Replay work_item_assigned events to collect task IDs already routed."""
    assigned: set[str] = set()
    for ev in replay(event_types=["work_item_assigned"]):
        tid = (ev.get("payload") or {}).get("task_id")
        if tid:
            assigned.add(tid)
    return assigned


def find_unassigned_ready_tasks(
    outcomes_path: str | Path | None = None,
    compile_actor: str = "mission_supervisor",
) -> list[dict[str, Any]]:
    """Find work-graph tasks that are ready and not yet assigned.

    Returns:
        list of routing decisions:
            [{"task_id", "officer", "mission_id", "outcome_id", "description"}, ...]
        Empty if outcomes file is missing or no tasks are ready.
    """
    path = Path(outcomes_path) if outcomes_path else _outcomes_path()
    if not path.exists():
        return []

    try:
        missions = compile_from_yaml(path, actor=compile_actor, roles=None)
    except (FileNotFoundError, ValueError):
        return []

    assigned = already_assigned_ids()

    decisions: list[dict[str, Any]] = []
    for mission in missions:
        graph = mission["work_graph"]
        for node in graph.ready_tasks():
            if not node.assigned_role:
                # No officer to route to — Captain may need to add a role
                # with matching capabilities. Surface that gap later via OVI;
                # silently skip for now.
                continue
            if node.id in assigned:
                continue
            decisions.append({
                "task_id": node.id,
                "officer": node.assigned_role,
                "mission_id": mission["id"],
                "outcome_id": mission["outcome_id"],
                "description": node.description,
            })

    return decisions


def route_pending_tasks(
    outcomes_path: str | Path | None = None,
    dry_run: bool = False,
    actor: str = "mission_supervisor",
) -> list[dict[str, Any]]:
    """Find unassigned ready tasks and emit work_item_assigned events.

    Args:
        outcomes_path: optional path to outcomes.yml
        dry_run: if True, return decisions without emitting events
        actor: actor label for emitted events

    Returns:
        list of routing decisions (same shape as find_unassigned_ready_tasks).
    """
    decisions = find_unassigned_ready_tasks(
        outcomes_path=outcomes_path,
        compile_actor=actor,
    )

    if dry_run:
        return decisions

    for d in decisions:
        emit("work_item_assigned", actor=actor, payload={
            "task_id": d["task_id"],
            "mission_id": d["mission_id"],
            "outcome_id": d["outcome_id"],
            "assigned_role": d["officer"],
            "description": d["description"],
        })

    return decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mission supervisor — route ready tasks to officers."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print routing decisions as JSON array on stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Identify routing decisions but do not emit events",
    )
    parser.add_argument(
        "--outcomes",
        type=str,
        default=None,
        help="Path to outcomes.yml (defaults to instance/config/outcomes.yml)",
    )
    args = parser.parse_args(argv)

    decisions = route_pending_tasks(
        outcomes_path=args.outcomes,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(decisions))
    else:
        print(f"mission-supervisor: {len(decisions)} task(s) "
              f"{'identified' if args.dry_run else 'routed'}")
        for d in decisions:
            print(f"  → {d['officer']}: {d['task_id']} ({d['description']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
