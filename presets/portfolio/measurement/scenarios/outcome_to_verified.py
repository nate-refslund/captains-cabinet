"""Scenario: Captain declares an outcome → officers execute → validator verifies → OVI updates.

The end-to-end Phase 1 closure test. This is the scenario the convergence
plan's Phase 1 gate cites by name:

  Captain outcome → mission compiled → officer completes → validator verifies
  → OVI components reflect the change.

If this scenario passes, the inner mission loop is closed: completion events
are durable in the ledger, the compiler replays them on the next session,
the OVI engine sees real activity instead of zeros.

This scenario does NOT require Postgres/Redis — it exercises the in-memory
work graph + event ledger + OVI compute path entirely. Phase 1.2 will add
the supervisor cron that persists to Postgres; this scenario is independent
of that infrastructure.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Clean environment with roles + a Captain-ratified outcome."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"

    # Wipe any cross-scenario state from prior test runs in the same process.
    # Roles + lineage are filesystem-backed under CABINET_ROOT; the tmp dir
    # is fresh, so no carry-over.

    from framework.roles.lifecycle import create_role
    create_role(
        "engineering", "Engineering", "Build and ship product code",
        capabilities=["writes_code", "deploys_code", "reviews_implementations"],
    )
    create_role(
        "product", "Product", "Define what to build and why",
        capabilities=["writes_specs", "product"],
    )
    create_role(
        "operations", "Operations", "Keep systems running reliably",
        capabilities=["monitors_systems", "manages_infra", "validates_deployments"],
    )
    # 2026-07-26 (branch fix/self-verification-hole): separation of duties is now
    # ENFORCED — the status overlay refuses to credit a verification whose actor
    # owns the node. `operations` OWNS the email-verification node below, so
    # verifying as `operations` was a self-verification. This role is the
    # independent validator the scenario has always described; its slug and
    # capability are absent from compiler._CAPABILITY_KEYWORDS, so it scores 0
    # in _match_role_for_task and can never win ownership of a node.
    create_role(
        "quality", "Quality", "Independently verify work owned by other roles",
        capabilities=["independent_verification"],
    )

    outcome = {
        "id": "test-outcome-verified-001",
        "name": "Ship the auth flow",
        "description": "Users can sign up and verify their email end-to-end",
        "measurable_criteria": [
            "Database schema migrated for users + sessions",
            "Sign-up API endpoint returns 201 with valid email",
            "Email verification link routes correctly",
            "Deploy to production health check passes",
        ],
        "status": "active",
        "captain_ratified": True,
    }

    return {"outcome": outcome, "tmp": tmp}


def _execute(context):
    """Compile the mission, complete + verify every node, then recompile to
    observe the overlay, then compute OVI from the event ledger.
    """
    from framework.missions.compiler import compile_outcome
    from framework.events.emitter import emit
    from framework.ovi.compute import gather_from_events, compute_ovi

    outcome = context["outcome"]

    # 1. Compile the mission (in-memory work graph, no status overlay yet).
    mission_v1 = compile_outcome(outcome)
    graph_v1 = mission_v1["work_graph"]
    task_ids = sorted(graph_v1.nodes.keys())  # deterministic order

    # 2. Simulate each officer completing their assigned task. Emits a
    #    work_item_completed event per node.
    for task_id in task_ids:
        node = graph_v1.nodes[task_id]
        emit(
            "work_item_completed",
            actor=node.assigned_role or "system",
            payload={
                "task_id": task_id,
                "outcome_id": outcome["id"],
                "status": "done",
                "evidence_text": f"Simulated completion of: {node.description}",
            },
        )

    # 3. Simulate the validator officer verifying each completed task.
    #    Emits work_item_verified, which the compiler also treats as DONE
    #    but with verification_passed=True.
    #    2026-07-26 (branch fix/self-verification-hole): the validator is now
    #    `quality`, a role that owns none of these nodes. This used to verify as
    #    `operations`, which OWNS the email-verification node — a
    #    self-verification the overlay now deliberately refuses to credit.
    for task_id in task_ids:
        emit(
            "work_item_verified",
            actor="quality",
            payload={
                "task_id": task_id,
                "outcome_id": outcome["id"],
                "status": "verified",
            },
        )

    # 4. Recompile the outcome. The event-sourced status overlay should
    #    apply DONE + verification_passed=True to every node.
    mission_v2 = compile_outcome(outcome)
    graph_v2 = mission_v2["work_graph"]

    # 5. Compute OVI from the event ledger. With 4 completions + 4
    #    verifications, the OVI should show non-zero throughput and
    #    100% verification pass rate.
    raw = gather_from_events()
    ovi = compute_ovi(raw, emit_event=False)

    return {
        "mission_v1": mission_v1,
        "mission_v2": mission_v2,
        "task_ids": task_ids,
        "ovi": ovi,
        "raw": raw,
    }


def _verify(context, results):
    """Assert the full loop closed: mission valid → events emitted →
    overlay applied → OVI reflects real activity."""
    from framework.events.emitter import replay
    from cabinet.scripts.lib.work_graph import NodeStatus

    assertions = []
    mission_v1 = results.get("mission_v1")
    mission_v2 = results.get("mission_v2")
    task_ids = results.get("task_ids", [])
    ovi = results.get("ovi")
    raw = results.get("raw")

    # --- mission validity ---
    assertions.append(("mission_v1_compiled", mission_v1 is not None))
    assertions.append(("mission_v2_compiled", mission_v2 is not None))
    if not (mission_v1 and mission_v2):
        return assertions

    # --- event-sourced status overlay applied to v2 ---
    graph_v2 = mission_v2["work_graph"]
    overlay_correct = all(
        graph_v2.nodes[tid].status == NodeStatus.DONE
        for tid in task_ids
    )
    assertions.append(("all_nodes_done_after_overlay", overlay_correct))

    verified_correct = all(
        graph_v2.nodes[tid].verification_passed is True
        for tid in task_ids
    )
    assertions.append(("all_nodes_verified_after_overlay", verified_correct))

    # --- events emitted (one of each type per task) ---
    completed_events = replay(event_types=["work_item_completed"])
    verified_events = replay(event_types=["work_item_verified"])
    expected = len(task_ids)
    assertions.append((
        "completed_events_emitted",
        len(completed_events) == expected,
    ))
    assertions.append((
        "verified_events_emitted",
        len(verified_events) == expected,
    ))

    # --- session bridge would now find no ready tasks ---
    # (proves the per-session reset is closed)
    graph_v1 = mission_v1["work_graph"]
    ready_after_completion = [
        n for n in graph_v2.ready_tasks()
        if n.assigned_role  # ignore unassigned nodes
    ]
    assertions.append((
        "no_ready_tasks_after_completion",
        len(ready_after_completion) == 0,
    ))
    # v1 (before overlay) DID have ready tasks (sanity)
    assertions.append((
        "v1_had_ready_tasks",
        len(graph_v1.ready_tasks()) > 0,
    ))

    # --- OVI reflects the activity ---
    assertions.append(("ovi_computed", ovi is not None))
    if ovi:
        # composite must be in [0,1]
        score = ovi.get("composite_score", -1)
        assertions.append(("ovi_score_in_range", 0.0 <= score <= 1.0))
        # raw task_throughput equals number of completion events
        assertions.append((
            "ovi_task_throughput_matches",
            raw["task_throughput"] == float(expected),
        ))
        # verification pass rate is 100% (every completion was also verified)
        assertions.append((
            "ovi_verification_rate_100pct",
            raw["verification_pass_rate"] == 1.0,
        ))
        # outcome progress is 100% (1 outcome touched, 1 progressed)
        assertions.append((
            "ovi_outcome_progress_100pct",
            raw["outcome_progress"] == 1.0,
        ))

    return assertions


register(Scenario(
    name="outcome_to_verified",
    description=(
        "End-to-end mission loop: Captain outcome → compile → officer completes "
        "→ validator verifies → recompile shows overlay → OVI reflects activity."
    ),
    category="mission",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
