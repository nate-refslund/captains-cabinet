"""framework.objectives.adapters.roots — the Captain-direction adapter (COG-3
contract rev-1 §2.2 + §4.1).

Consumes the PRE-PARSED, lane-normalized entry structure the CLI produces
(cog3-rebuild.py `_normalize_roots`: `directions` reshaped from the lane-keyed
mapping into a LIST of {slug, statement?/mission?, objectives?, …} entries, in
sorted-by-lane order). Emits the `directions` + `objectives` fragment of the
canonical objectives-input: one direction_root per entry, and one objective per
declared objective under an entry, each carrying `root_ref` = its lane slug
(§4.1: root_ref REQUIRED on objective nodes). The fold (graph.py) turns these into
direction_root/objective NODES and authenticates the root_ref — this adapter only
shapes the input, pinned per §7.6 (framework carries no yaml, no instance literal;
the CLI owns file reading).

STDLIB-ONLY (§6.5): no import at all — the fragment is plain dicts; the fold owns
node-id digests. Statement keys on `statement` (the digest field graph.py reads),
NEVER on `mission`, so the direction_root identity matches the fold's existing
`{slug, statement}` digest and the default rebuild output is unchanged.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations


def adapt(entries):
    """Normalized lane-entry list -> {directions, objectives} fragment. Each entry
    -> a direction_root; each objective declared under `entry['objectives']`
    (a slug string or a {slug, …} dict) -> an objective rooted at that lane. Sorted
    deterministically; an entry with no slug (or an objective with no slug) is
    skipped, never invented."""
    directions = []
    objectives = []
    for entry in entries or []:
        slug = entry.get("slug")
        if slug is None:
            continue
        directions.append({"slug": slug, "statement": entry.get("statement", "")})
        for obj in entry.get("objectives", []) or []:
            oslug = obj if isinstance(obj, str) else obj.get("slug")
            if oslug is None:
                continue
            objectives.append({"slug": oslug, "root_ref": slug})
    directions.sort(key=lambda d: d["slug"])
    objectives.sort(key=lambda o: (o["slug"], o["root_ref"]))
    return {"directions": directions, "objectives": objectives}
