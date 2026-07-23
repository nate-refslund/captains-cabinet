"""framework.objectives.adapters.product_spec — the product adapter (COG-3
contract rev-1 §2.2 + §4.2). Emits outcome + instrument nodes and the `indicates`
relational edges between them — a PURELY relational surface, no epistemic
machinery (§4.2: `indicates` is instrument -> outcome, dimension-pinned, never
promotable, never a causal edge).

Consumes product-record dicts, each `{slug, dimension?, instruments: [...]}` where
an instrument is a name string or a `{name, dimension?}` dict. Per product it
emits the outcome node (the product's goal), an instrument node per instrument
(deduped across products), and an `indicates` edge instrument -> outcome on the
pinned dimension. INDICATES_ALLOWED (model) is exactly (instrument, outcome), so
this adapter's edges land inside the fold's structural rule.

STDLIB-ONLY (§6.5): no import — plain dicts; subject_keys are prefix-namespaced
(`outcome/<slug>`, `instrument/<name>`), the fold owns the node-id digests.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations


def adapt(products):
    """Product-record list -> {outcomes, nodes, indicates_edges} fragment. Sorted
    deterministically; instrument nodes deduped by subject_key across products. A
    product with no slug, or an instrument with no name, is skipped."""
    outcomes = []
    nodes = []
    indicates_edges = []
    seen_instruments = set()
    for prod in products or []:
        slug = prod.get("slug")
        if slug is None:
            continue
        outcome_sk = "outcome/" + slug
        out = {"slug": slug}
        if prod.get("dimension") is not None:
            out["dimension"] = prod["dimension"]
        outcomes.append(out)
        for instr in prod.get("instruments", []) or []:
            if isinstance(instr, str):
                name, dimension = instr, prod.get("dimension")
            else:
                name = instr.get("name")
                dimension = instr.get("dimension", prod.get("dimension"))
            if name is None:
                continue
            instrument_sk = "instrument/" + name
            if instrument_sk not in seen_instruments:
                seen_instruments.add(instrument_sk)
                nodes.append({"kind": "instrument", "subject_key": instrument_sk})
            indicates_edges.append({"source": instrument_sk, "target": outcome_sk,
                                    "dimension": dimension})
    outcomes.sort(key=lambda o: o["slug"])
    nodes.sort(key=lambda n: n["subject_key"])
    indicates_edges.sort(key=lambda e: (e["source"], e["target"], e.get("dimension") or ""))
    return {"outcomes": outcomes, "nodes": nodes, "indicates_edges": indicates_edges}
