"""Eval: CRO — event ledger replay filters correctly.

Tests the **memory** of the CRO role (the research+memory officer) — the
ability to scan history with precise filters. A failure signals
`missing_skill` (replay regression) or `quality_gap` (returns wrong events).
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
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"
    return {"tmp": tmp}


def _execute(ctx):
    from framework.events.emitter import emit, replay

    # Mix of event types
    emit("work_item_completed", actor="engineering", payload={"task_id": "t1"})
    emit("work_item_completed", actor="engineering", payload={"task_id": "t2"})
    emit("experience_recorded", actor="cro", payload={"lesson": "x"})
    emit("captain_decision_logged", actor="captain", payload={"decision": "y"})

    return {
        "all_events": replay(),
        "completions_only": replay(event_types=["work_item_completed"]),
        "by_actor_cro": replay(actor="cro"),
        "by_actor_captain": replay(actor="captain"),
    }


def _verify(ctx, results):
    return [
        ("all_events_count", len(results["all_events"]) == 4, "quality_gap"),
        ("completions_filtered", len(results["completions_only"]) == 2, "quality_gap"),
        ("cro_actor_filtered", len(results["by_actor_cro"]) == 1, "quality_gap"),
        ("captain_actor_filtered", len(results["by_actor_captain"]) == 1, "quality_gap"),
        ("all_completions_have_task_id",
         all((e.get("payload") or {}).get("task_id")
             for e in results["completions_only"]),
         "quality_gap"),
    ]


register(RoleEval(
    name="cro_event_replay",
    role_slug="cro",
    category="memory",
    description="CRO's event replay filters by event_type and actor correctly.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
