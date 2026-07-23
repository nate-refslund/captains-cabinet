"""framework.objectives.adapters.mission_inputs — the mission/outcome adapter
(COG-3 contract rev-1 §2.2 + §4.1). Emits the `outcomes` + `constraints` fragment
from mission records.

Consumes mission-record dicts, each `{slug, kind?, dimension?, floor?,
evidence_subjects?}`:
  * kind == "constraint" -> a constraint node carrying its named scorecard floor
    (`dimension` + `floor` — §4.1: floors on outcome/constraint) and any
    `evidence_subjects` the fold binds + marks (a constraint is retained + marked,
    never dropped — §11 sim1);
  * otherwise -> an outcome node (the causal-edge target space), dimension-pinned.

The fold (graph.py) turns these into outcome/constraint NODES and reads the floor
into its `{dimension: floor}` scorecard shape. STDLIB-ONLY (§6.5): no import — the
fragment is plain dicts; `floor` is a per-dimension floor value, never a weight
(the no-scalar ratchet keys on weight identifiers, not floors).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations


def adapt(records):
    """Mission-record list -> {outcomes, constraints} fragment. Sorted
    deterministically; a record with no slug is skipped. Absent `kind` defaults to
    an outcome (the common case); `constraint` routes to the floor-bearing home."""
    outcomes = []
    constraints = []
    for rec in records or []:
        slug = rec.get("slug")
        if slug is None:
            continue
        if rec.get("kind") == "constraint":
            out = {"slug": slug}
            if rec.get("dimension") is not None:
                out["dimension"] = rec["dimension"]
            if rec.get("floor") is not None:
                out["floor"] = rec["floor"]
            if rec.get("evidence_subjects"):
                out["evidence_subjects"] = list(rec["evidence_subjects"])
            constraints.append(out)
        else:
            out = {"slug": slug}
            if rec.get("dimension") is not None:
                out["dimension"] = rec["dimension"]
            outcomes.append(out)
    outcomes.sort(key=lambda o: o["slug"])
    constraints.sort(key=lambda c: c["slug"])
    return {"outcomes": outcomes, "constraints": constraints}
