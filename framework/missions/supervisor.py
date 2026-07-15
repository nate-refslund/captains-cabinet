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

- **Delivery-before-assignment.** This module first returns *routing
  decisions* as plain dicts. The shell wrapper pushes Redis Stream messages,
  then confirms the successfully delivered decisions back here. Only that
  confirmation emits ``work_item_assigned``. A Redis failure therefore leaves
  the task routable rather than black-holing it behind a premature event.

Usage:
    from framework.missions.supervisor import route_pending_tasks
    projected = route_pending_tasks()  # projection only; emits no assignment
    # Deliver each projected row, then acknowledge only the rows Redis accepted:
    confirmed = confirm_delivered_assignments(delivered_rows)

    # CLI (for the shell wrapper):
    python3 -m framework.missions.supervisor --json --dry-run
    printf '[...]' | python3 -m framework.missions.supervisor --confirm-stdin --json
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


def _adopted_missions_source(
    compile_actor: str,
    emit_mission_events: bool,
) -> list[dict[str, Any]]:
    """THIRD compile-source when sovereign [SOV-4]:
    `shared/interfaces/adopted-missions.yml`, the action-lane's OWN artifact
    (written by action_exec._exec_mission_adopt) — SEPARATE from standing_pull's
    standing-missions.yml so neither writer clobbers the other; the supervisor
    merges both. Same guardian-bit-identical guard as the standing source:
    non-sovereign / module absent / file missing / corrupt → [], so with no
    attested sovereign ruling this does nothing at all.
    """
    try:
        from framework.authority.posture import resolve_posture
        if resolve_posture() != "sovereign":
            return []
        from framework.frontdoor.action_exec import _adopted_missions_path
        path = _adopted_missions_path()
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
            Defaults False — ordinary discovery is a projection. Delivery
            confirmation is the only caller that sets it True, because that
            is the single compile whose missions are durably assigned.

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
        missions = (_standing_missions_source(compile_actor, emit_mission_events)
                    + _adopted_missions_source(compile_actor, emit_mission_events))
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

        # Sovereign-only extra sources (standing pull + action-lane adopt) —
        # both [] in guardian, so guardian stays bit-identical.
        missions = (missions
                    + _standing_missions_source(compile_actor, emit_mission_events)
                    + _adopted_missions_source(compile_actor, emit_mission_events))

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
    dry_run: bool = True,
    actor: str = "mission_supervisor",
) -> list[dict[str, Any]]:
    """Project unassigned ready tasks without recording an assignment.

    Assignment is deliberately impossible through this API.  A caller must
    first deliver the projected rows and pass only the successful deliveries
    to :func:`confirm_delivered_assignments`.  Keeping ``dry_run`` as a
    compatibility keyword lets older callers fail loudly instead of silently
    restoring the pre-delivery black-hole bug.

    Args:
        outcomes_path: optional path to outcomes.yml
        dry_run: must be True; False is refused
        actor: actor label used while compiling the projection

    Returns:
        list of routing decisions (same shape as find_unassigned_ready_tasks).
    """
    if not dry_run:
        raise ValueError(
            "direct assignment recording is disabled; deliver the projection "
            "and call confirm_delivered_assignments"
        )

    return find_unassigned_ready_tasks(
        outcomes_path=outcomes_path,
        compile_actor=actor,
        emit_mission_events=False,
    )


def confirm_delivered_assignments(
    delivered: list[dict[str, Any]],
    outcomes_path: str | Path | None = None,
    actor: str = "mission_supervisor",
) -> list[dict[str, Any]]:
    """Emit assignments only for decisions already delivered to Redis.

    Every caller-supplied row must still match the current compiled ready set;
    this makes stdin an acknowledgement, not an authority-bearing routing
    source. Already-confirmed task ids are idempotent no-ops. If the process
    crashes after Redis delivery but before this confirmation, the next pass
    may deliver a duplicate trigger, but it can never silently lose the task.
    """
    if not isinstance(delivered, list):
        raise ValueError("delivered assignments must be a list")
    if len(delivered) > 1000:
        raise ValueError("too many delivered assignments")

    assigned_before = already_assigned_ids()
    # This is the one materializing compile. It happens only after the wrapper
    # has proved delivery of the rows it is about to acknowledge.
    pending = find_unassigned_ready_tasks(
        outcomes_path=outcomes_path,
        compile_actor=actor,
        emit_mission_events=True,
    )
    by_id = {str(row["task_id"]): row for row in pending}
    confirmed: list[dict[str, Any]] = []
    seen: set[str] = set()
    required = {"task_id", "officer", "mission_id", "outcome_id", "description"}
    stable = {"task_id", "officer", "outcome_id", "description"}
    for supplied in delivered:
        if not isinstance(supplied, dict) or set(supplied) != required:
            raise ValueError("delivered assignment shape is invalid")
        task_id = str(supplied["task_id"])
        if task_id in seen:
            continue
        seen.add(task_id)
        if task_id in assigned_before:
            continue
        current = by_id.get(task_id)
        # mission_id is minted during compilation and therefore changes on a
        # projection/confirmation recompile. Validate the stable routing
        # identity; use the materializing compile's mission_id in the event.
        if current is None or any(supplied[key] != current[key] for key in stable):
            raise ValueError(f"delivered assignment is stale or does not match current routing: {task_id}")
        emit("work_item_assigned", actor=actor, payload={
            "task_id": current["task_id"],
            "mission_id": current["mission_id"],
            "outcome_id": current["outcome_id"],
            "assigned_role": current["officer"],
            "description": current["description"],
            "delivery": "redis_stream_confirmed",
        })
        confirmed.append(current)
    return confirmed


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
    parser.add_argument(
        "--confirm-stdin",
        action="store_true",
        help="Read delivered decision rows from stdin and emit assignments only after validating them against the current ready set",
    )
    args = parser.parse_args(argv)

    if args.confirm_stdin and args.dry_run:
        parser.error("--confirm-stdin and --dry-run are mutually exclusive")
    if args.confirm_stdin:
        raw = sys.stdin.read(1_048_577)
        if len(raw) > 1_048_576:
            parser.error("confirmation payload is too large")
        try:
            delivered = json.loads(raw or "[]")
            decisions = confirm_delivered_assignments(
                delivered, outcomes_path=args.outcomes,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            parser.error(str(exc))
    else:
        decisions = route_pending_tasks(outcomes_path=args.outcomes)

    if args.json:
        print(json.dumps(decisions))
    else:
        state = "confirmed" if args.confirm_stdin else "identified"
        print(f"mission-supervisor: {len(decisions)} task(s) {state}")
        for d in decisions:
            print(f"  → {d['officer']}: {d['task_id']} ({d['description']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
