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

- **Roster-gated.** A task whose assigned_role is not in the active roster
  is never routed (and never marked assigned — that would black-hole it):
  it gets one deduped `work_item_unroutable` ledger event plus a stderr
  warning per pass, and resurfaces automatically once the role is created.

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
from framework.roles.lifecycle import list_roles


def _standing_missions_source(
    compile_actor: str,
    emit_mission_events: bool,
) -> list[dict[str, Any]]:
    """SECOND compile-source when sovereign [sovereign spec §4 SOV-8]:
    `shared/interfaces/standing-missions.yml`, written only by
    framework.missions.standing_pull (never the Captain's outcomes.yml).

    Guardian bit-identical: the posture resolve is lazy and any failure —
    module absent, posture unreadable, file missing/corrupt — answers [],
    so with no attested sovereign ruling this function does nothing at all.
    """
    try:
        from framework.authority.posture import resolve_posture
        if resolve_posture() != "sovereign":
            return []
        from framework.missions.standing_pull import standing_missions_path
        path = standing_missions_path()
        if not path.exists():
            return []
        return compile_from_yaml(
            path, actor=compile_actor, roles=None,
            emit_event=emit_mission_events,
        )
    except Exception:
        return []


def already_assigned_ids() -> set[str]:
    """Replay work_item_assigned events to collect task IDs already routed."""
    assigned: set[str] = set()
    for ev in replay(event_types=["work_item_assigned"]):
        tid = (ev.get("payload") or {}).get("task_id")
        if tid:
            assigned.add(tid)
    return assigned


def already_unroutable_ids() -> set[str]:
    """Replay work_item_unroutable events to collect task IDs already flagged.

    Same dedup pattern as already_assigned_ids: one ledger event per task,
    no matter how many supervisor passes observe the same ghost role.
    """
    flagged: set[str] = set()
    for ev in replay(event_types=["work_item_unroutable"]):
        tid = (ev.get("payload") or {}).get("task_id")
        if tid:
            flagged.add(tid)
    return flagged


def find_unassigned_ready_tasks(
    outcomes_path: str | Path | None = None,
    compile_actor: str = "mission_supervisor",
    emit_mission_events: bool = False,
) -> list[dict[str, Any]]:
    """Find work-graph tasks that are ready and not yet assigned.

    Args:
        outcomes_path: optional path to outcomes.yml
        compile_actor: actor label for the compile (and unroutable events)
        emit_mission_events: pass-through to compile_from_yaml(emit_event=…).
            Defaults False — this function is a projection. Only the real
            (non-dry-run) routing pass in route_pending_tasks sets it True,
            because that is the single compile whose missions are acted on.

    Returns:
        list of routing decisions:
            [{"task_id", "officer", "mission_id", "outcome_id", "description"}, ...]
        Empty if outcomes file is missing or no tasks are ready.
    """
    path = Path(outcomes_path) if outcomes_path else _outcomes_path()
    if not path.exists():
        # Sovereign may still route standing missions with no Captain
        # outcomes file at all (never-idle); guardian gets today's exact
        # empty answer because the second source is [] there.
        missions = _standing_missions_source(compile_actor, emit_mission_events)
        if not missions:
            return []
    else:
        try:
            missions = compile_from_yaml(
                path, actor=compile_actor, roles=None,
                emit_event=emit_mission_events,
            )
        except (FileNotFoundError, ValueError):
            return []

        # Sovereign-only second source (standing missions) — [] in guardian.
        missions = missions + _standing_missions_source(
            compile_actor, emit_mission_events)

    assigned = already_assigned_ids()
    flagged_unroutable = already_unroutable_ids()

    # Roster check: the compiler stamps an explicit owner_role verbatim with
    # no validation, so a typo'd or not-yet-created role would otherwise be
    # routed into a black hole (work_item_assigned is emitted before delivery
    # and already_assigned_ids() excludes the task forever after).
    active_slugs: set[str] = {
        role.get("slug") for role in list_roles(status="active") if role.get("slug")
    }

    decisions: list[dict[str, Any]] = []
    for mission in missions:
        graph = mission["work_graph"]
        for node in graph.ready_tasks():
            if not node.assigned_role:
                # No officer to route to — Captain may need to add a role
                # with matching capabilities. Surface that gap later via OVI;
                # silently skip for now.
                continue
            if node.assigned_role not in active_slugs:
                # Ghost role: skip WITHOUT emitting work_item_assigned so the
                # task resurfaces automatically once the role exists. Record
                # the gap once in the ledger (deduped by replay) and warn on
                # every pass while it persists — stderr only, never stdout
                # (the --json contract reserves stdout for routing decisions).
                print(
                    f"mission-supervisor: WARN task {node.id} is assigned to "
                    f"role '{node.assigned_role}' which is not in the active "
                    f"roster — skipping (create the role to route it)",
                    file=sys.stderr,
                )
                if node.id not in flagged_unroutable:
                    emit("work_item_unroutable", actor=compile_actor, payload={
                        "task_id": node.id,
                        "mission_id": mission["id"],
                        "outcome_id": mission["outcome_id"],
                        "assigned_role": node.assigned_role,
                        "description": node.description,
                    })
                    flagged_unroutable.add(node.id)
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
        # The real routing pass is the ONE compile that materializes
        # missions (its mission_ids land in durable work_item_assigned
        # events) — it keeps emitting mission_created. Dry-run is a pure
        # projection and stays silent.
        emit_mission_events=not dry_run,
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
