"""framework.objectives.adapters.workgraph — the tasks/intervention adapter
(COG-3 contract rev-1 §2.2 + §4.1 + §4.2). THE unit that closes the wave-4
P6-deferral: it emits the join_spec + admissible_subjects + evidence bindings the
fold resolves into a real edge state.

Consumes task-record dicts (the officer-tasks shape — `framework.cortex.adapters`
keys a task belief on `tasks/<task_id>` and flattens actor 'kind:id'; this adapter
mirrors that identity convention). Per task it emits:
  * an `intervention` node keyed `tasks/<task_id>` carrying `join_spec` — the
    adapter-derived (actor 'kind:id', action, subject) matcher(s) for consequence
    evidence ABOUT this intervention (§4.1), derived from the task's OWN fields;
  * a causal edge intervention -> outcome (§4.2) with `expected_effect` taken from
    the task's DECLARED direction field, `assumptions` carried from the record
    (empty => the edge derives P6, honest), `admissible_subjects` = the task's own
    subject_key + its consequence-identity subject, and `evidence_subjects` = that
    consequence subject (the fold resolves it through the ONE cortex read path).

DIRECTION IS NEVER INVENTED (§4.2 / the wave brief): if the task carries no
`expected_effect` (or no `target`), the adapter emits the intervention node but
REFUSES the causal edge — a causal claim with no declared direction would be
manufactured, so it is withheld rather than defaulted per-edge.

CONSEQUENCE IDENTITY (§5.2b): the consequence subject_key is
`consequence/<recorder-digest of (actor 'kind:id', action, subject, ts)>`,
recomputed with `model.digest` (byte-identical to the cortex recorder dialect), so
the emitted evidence subject NAMES exactly the ledger row the fold's verified-join
limb (i) recomputes. `model` is the ONLY import (internal — §6.5 permits it).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations

from framework.objectives import model


def _actor_id(actor):
    """Flatten an actor to 'kind:id' exactly as the consequence identity does
    (`framework.cortex.adapters._consequence_identity`): a dict -> 'kind:id', a
    bare token -> 'token:' (the non-dict fallback that never collides)."""
    if isinstance(actor, dict):
        return f"{actor.get('kind')}:{actor.get('id')}"
    return f"{actor}:"


def adapt(tasks):
    """Task-record list -> {nodes, causal_edges} fragment. Deterministic sorted
    order; a task with no `task_id` is skipped. A causal edge is emitted ONLY when
    the task declares BOTH a direction (`expected_effect`) and a `target` outcome —
    otherwise just the intervention node (direction never invented, §4.2)."""
    nodes = []
    causal_edges = []
    for task in tasks or []:
        task_id = task.get("task_id")
        if task_id is None:
            continue
        subject_key = f"tasks/{task_id}"
        actor_id = _actor_id(task.get("actor"))
        action = task.get("action", "")
        subject = task.get("subject", "")
        ts = task.get("ts", "")
        nodes.append({"kind": "intervention", "subject_key": subject_key,
                      "join_spec": [[actor_id, action, subject]]})
        effect = task.get("expected_effect")
        target = task.get("target")
        if effect is None or target is None:
            continue                           # REFUSE a directionless causal edge
        consequence_sk = "consequence/" + model.digest([actor_id, action, subject, ts])
        causal_edges.append({
            "source": subject_key,
            "target": target,
            "dimension": task.get("dimension"),
            "expected_effect": effect,
            "assumptions": list(task.get("assumptions", []) or []),
            "admissible_subjects": sorted({subject_key, consequence_sk}),
            "evidence_subjects": [consequence_sk],
        })
    nodes.sort(key=lambda n: n["subject_key"])
    causal_edges.sort(key=lambda e: (e["source"], e["target"], e.get("dimension") or ""))
    return {"nodes": nodes, "causal_edges": causal_edges}
