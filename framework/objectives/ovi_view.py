"""framework.objectives.ovi_view — the PER-INSTRUMENT OVI projection (COG-3
contract rev-1 §6.6 P10 / N6, attack C-M4).

The legacy OVI is a weighted composite scalar (framework/ovi/compute.py, outside
this tree, byte-untouched). This view projects each instrument SEPARATELY and
structurally REFUSES any composite/aggregate: the projection is per-instrument,
and neither this module nor its output carries a composite score or an aggregate
of any kind (the P12 ratchet's OVI mutant pins that a composite emission is RED).
Per-instrument measures are NOT the forbidden aggregate — the ratchet forbids
aggregation-to-one, never a per-instrument value.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core).
"""
from __future__ import annotations


def project(instruments: dict) -> dict:
    """Project each instrument SEPARATELY: `{name: measure}` -> `{name: {value:
    measure}}`. Every instrument keeps its OWN projection; no composite, no
    aggregate, ever (N3/N6). Returns a plain dict (JSON-serializable)."""
    return {name: {"value": measure} for name, measure in instruments.items()}
