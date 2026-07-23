"""framework.objectives.adapters — the blast-isolated source-record adapters
(COG-3 contract rev-1 §2.2 + §4). Each adapter turns ONE source-record shape into
a fragment of the canonical objectives-input build_graph consumes; `assemble`
merges the fragments into ONE deterministic input. This closes the declared
wave-4 deferral (§ appendix addendum): build-path causal edges now carry
adapter-emitted evidence bindings, so they derive above P6 through the fold.

IMPORT-INERT BY DESIGN (contract §6.5): this package root imports NOTHING at
module load — `assemble` and its collision type are defined with builtins only
(dict equality is the content comparison), so importing the package pulls no
framework or third-party module. The four adapters (roots / workgraph /
mission_inputs / product_spec) are imported explicitly by callers.

BLAST ISOLATION (§2.2): every adapter is standalone — a missing/failing source
for one NEVER affects the others' emission. `assemble` takes a name->fragment map
where a `None` fragment is a DECLARED absence (recorded in `declared_absent`,
never silent — the missing-product-adapter foundry sim shape).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations

# The merge categories, in the canonical objectives-input the fold reads (graph.py
# _compile). Every adapter fragment contributes a subset; assemble concatenates +
# dedups per category. Ordered so the merged dict is itself deterministic.
_CATEGORIES = ("directions", "objectives", "outcomes", "constraints",
               "nodes", "indicates_edges", "causal_edges")


class AssemblyCollision(Exception):
    """A structural assembly error (§2.2 / item 7): two adapter fragments emit the
    SAME identity (a node subject_key, an edge (source,target,dimension), or a
    node slug) with DIFFERENT content. Never a silent last-writer-wins — a
    collision means two adapters disagree about one graph element and the cabinet
    input is ill-formed. (An IDENTICAL duplicate is deduped, not a collision.)"""


def _identity(category, item):
    """The per-category collision identity of one emitted item."""
    if category == "nodes":
        return item.get("subject_key")
    if category in ("indicates_edges", "causal_edges"):
        return (item.get("source"), item.get("target"), item.get("dimension"))
    return item.get("slug")                    # directions/objectives/outcomes/constraints


def _sort_key(category, item):
    if category == "nodes":
        return (item.get("subject_key") or "",)
    if category in ("indicates_edges", "causal_edges"):
        return (item.get("source") or "", item.get("target") or "",
                item.get("dimension") or "")
    return (item.get("slug") or "",)


def assemble(fragments):
    """Merge adapter fragments into ONE canonical objectives-input (§2.2 item 7).

    `fragments` is a mapping {adapter_name: fragment_dict | None}. A `None` value is
    a DECLARED-ABSENT source (blast isolation) — its name lands in the returned
    `declared_absent` list, never silent. Present fragments are merged per category;
    an identical duplicate is deduped; a conflicting duplicate (same identity,
    different content) raises AssemblyCollision. Every category is sorted, so the
    merged input is byte-deterministic regardless of adapter order."""
    merged = {c: [] for c in _CATEGORIES}
    seen = {c: {} for c in _CATEGORIES}
    declared_absent = []
    for name in sorted(fragments):
        frag = fragments[name]
        if frag is None:
            declared_absent.append(name)
            continue
        for category in _CATEGORIES:
            for item in frag.get(category, []) or []:
                ident = _identity(category, item)
                if ident in seen[category]:
                    if seen[category][ident] != item:
                        raise AssemblyCollision(
                            f"{name}: {category} identity {ident!r} collides with a "
                            "different item already emitted by another adapter "
                            "(§2.2 — collision is a structural error, never LWW)")
                    continue                   # identical duplicate: dedup, not a collision
                seen[category][ident] = item
                merged[category].append(item)
    for category in _CATEGORIES:
        merged[category].sort(key=lambda it, c=category: _sort_key(c, it))
    merged["declared_absent"] = declared_absent
    return merged
