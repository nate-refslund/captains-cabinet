"""framework.objectives.query — the U1 slices of the objectives view surface
(COG-3 contract rev-1 §5.2 / §4.4): the bijective Captain-vocabulary table, the
vector-scorecard shape, and the recommendation-record shape.

VECTOR-OR-NOTHING (N3/P12): the scorecard view returns the full per-dimension
vector and exposes NO scalar accessor — no __float__, no total/score/composite,
no aggregation to one number. One failed floor fails the whole vector regardless
of the others (no compensatory logic); an absent value is `unknown` and unknown
NEVER passes a floor. Confidence rides WHOLE inside a binding's source_trust
tuple, never as a bare number on the view (§5.5).

SERVE SURFACE (U2): the WHOLE surface binds through ONE loader (_load_bound) —
serve_graph, serve_objective, AND recommend — so no entry point serves unbound
rows (F1). It binds the manifest epoch and REFUSES on any of three C-F15 limbs
(§5.3/§5.4): a counterfactual manifest; a graph.jsonl that no longer reproduces
the manifest's recorded graph_rows_hash (tampered/partial rows); or a mixed-epoch
store (live cortex store hash != the manifest's recorded cortex_belief_store_hash
— including the built-without-store null hole). All raise the C-F15 ServeRefused
shape. serve_objective answers one objective (state + flags incl. orphaned);
recommend cites the full provenance triple and refuses "effective" without an
intervention_supported binding.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core) + U2 (serve).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from framework.objectives import graph, states
from framework.cortex.query import StoreCorruptError, load_beliefs_verified

# ===========================================================================
# The bijective internal <-> Captain vocabulary (§5.2 — ONE table, round-trip)
# ===========================================================================

_CAPTAIN_WORD = {
    states.STATE_UNKNOWN: "unknown",
    states.STATE_HYPOTHESIZED: "hypothesized",
    states.STATE_OBSERVATIONALLY_SUPPORTED: "observed",
    states.STATE_INTERVENTION_SUPPORTED: "tested",
    states.STATE_FALSIFIED: "refuted",
}
_INTERNAL_STATE = {word: internal for internal, word in _CAPTAIN_WORD.items()}


def to_captain_word(internal_state: str) -> str:
    """Map an internal derived state to its Captain vocabulary word (bijective)."""
    return _CAPTAIN_WORD[internal_state]


def to_internal_state(captain_word: str) -> str:
    """Map a Captain vocabulary word back to its internal derived state (the
    inverse of to_captain_word — a clean 5<->5 bijection)."""
    return _INTERNAL_STATE[captain_word]


# ===========================================================================
# The vector scorecard shape (§4.4) — full per-dimension vector, never a scalar
# ===========================================================================

@dataclass(frozen=True)
class ScorecardView:
    """The vector value surface. `states` is the full per-dimension mapping;
    `floors_met` is the vector-level pass. Deliberately carries NO scalar accessor
    (no __float__, no total/score) — the vector can never collapse to one number."""
    states: dict
    floors_met: bool


def scorecard_view(dimensions: dict) -> ScorecardView:
    """Build the vector view from a `{name: {value?, floor, evidence_binding_refs?}}`
    mapping (§4.4). An absent value => `unknown` (never a pass); a present value
    passes iff value >= floor. `floors_met` is True iff EVERY dimension passes —
    one failed (or unknown) floor fails the vector, no compensation."""
    per_dimension: dict = {}
    all_met = True
    for name, spec in dimensions.items():
        floor = spec.get("floor")
        has_value = spec.get("value") is not None
        value = spec.get("value") if has_value else None
        if not has_value:
            state, met = states.STATE_UNKNOWN, False   # unknown never passes (:239)
        elif floor is not None and value >= floor:
            # INTERNAL token only in data/persistence (§5.2 "no second drifting
            # enum") — the Captain word 'observed' lives ONLY in to_captain_word.
            state, met = states.STATE_OBSERVATIONALLY_SUPPORTED, True
        else:
            state, met = states.STATE_HYPOTHESIZED, False
        cell: dict = {"floor": floor, "state": state}
        if has_value:
            cell["value"] = value
        refs = spec.get("evidence_binding_refs")
        if refs is not None:
            cell["evidence_binding_refs"] = refs       # confidence rides WHOLE (§5.5)
        per_dimension[name] = cell
        if not met:
            all_met = False
    return ScorecardView(states=per_dimension, floors_met=all_met)


# ===========================================================================
# The recommendation record shape (§4.4 :180) — the full tuple, effective-gated
# ===========================================================================

def recommendation_record(objective_ref, evidence_refs, uncertainty, scorecard,
                          *, claim=None):
    """Build a recommendation record carrying the FULL tuple (objective_ref,
    evidence_refs, uncertainty, per-dimension scorecard). Dropping any required
    field is a structural rejection (a missing positional raises). The scorecard
    is the full per-dimension vector — a bare scalar is refused. A `claim` of
    'effective' is REFUSED unless an intervention_supported edge stands behind it
    (§5.2 P5 cap — a naked verdict is never emitted)."""
    if not isinstance(scorecard, dict):
        raise ValueError(
            "scorecard must be the full per-dimension vector (a mapping), never a "
            "bare scalar (§4.4/N3 — no collapse to one number)")
    for name, cell in scorecard.items():
        if not isinstance(cell, dict):
            raise ValueError(
                f"scorecard dimension {name!r} must be a per-dimension cell, never "
                "a scalar (§4.4)")
    if claim == "effective":
        seen = {ref.get("state") for ref in evidence_refs if isinstance(ref, dict)}
        if states.STATE_INTERVENTION_SUPPORTED not in seen:
            raise ValueError(
                "a recommendation may claim 'effective' ONLY with an "
                "intervention_supported edge behind it (§5.2 P5 cap; :180)")
    record = {
        "objective_ref": objective_ref,
        "evidence_refs": list(evidence_refs),
        "uncertainty": uncertainty,
        "scorecard": scorecard,
    }
    if claim is not None:
        record["claim"] = claim
    return record


# ===========================================================================
# The serve surface (§5.3/§5.4) — epoch-bound, REFUSE clauses, answer flags
# ===========================================================================

class ServeRefused(Exception):
    """The serve surface refuses to bind a graph (C-F15 StoreCorruptError-shape
    clone, §5.4): a manifest marked `counterfactual: true` (§5.3); a graph.jsonl
    that does not reproduce the manifest's `graph_rows_hash` (a tampered/partial
    row store); OR a mixed-epoch store whose live cortex belief-store hash != the
    manifest's recorded `cortex_belief_store_hash` (INCLUDING the built-without-
    store hole: the manifest recorded null yet a live store now exists). Mixed-epoch
    / unverified answers are the dishonesty §5.5 forbids — serve fails closed,
    never re-derives."""


@dataclass(frozen=True)
class Answer:
    """One served objective answer — the derived state + the answer FLAGS beside
    it (contested / direction_contested / orphaned, §5.2), never extra states."""
    state: str
    flags: frozenset


def _read_records(cache_dir):
    path = Path(cache_dir) / "graph.jsonl"
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _is_edge_record(record) -> bool:
    return "edge_id" in record or "relation" in record or "source_node_id" in record


def _live_store_hash(cortex_dir):
    """The LIVE verified cortex belief-store hash, or None when no store exists.
    Binds the store to its own fold manifest first (C-F15) so a tampered store is
    refused, then returns the manifest's belief_store_hash for the epoch compare."""
    cortex_dir = Path(cortex_dir)
    fold_manifest = cortex_dir / "fold-manifest.json"
    if not fold_manifest.exists():
        return None
    try:
        load_beliefs_verified(cortex_dir)                 # C-F15 bound read
    except StoreCorruptError as exc:
        raise ServeRefused(f"cortex store failed its hash binding: {exc}") from None
    manifest = json.loads(fold_manifest.read_text(encoding="utf-8"))
    return manifest.get("belief_store_hash") if isinstance(manifest, dict) else None


def _load_bound(cache_dir):
    """The ONE bound load path for the WHOLE serve surface — serve_graph,
    serve_objective, AND recommend route through here (F1), so no public entry
    point can serve unbound rows. Binds the manifest epoch and REFUSES (raises
    ServeRefused) on any of the three C-F15 limbs (§5.3/§5.4) BEFORE a single
    record is read for serving: a `counterfactual: true` manifest; a graph.jsonl
    that no longer reproduces the manifest's `graph_rows_hash` (tampered/partial
    rows — the manufactured-certainty class); or a mixed-epoch store whose live
    cortex hash != the manifest's `cortex_belief_store_hash`, INCLUDING the
    built-without-store hole (the manifest recorded no store hash yet a live store
    exists at serve time). Returns (epoch, records, manifest) — compile-time states
    labeled with the epoch; there is NO serve-time re-derivation."""
    d = Path(cache_dir)
    manifest = json.loads((d / "graph-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("counterfactual") is True:
        raise ServeRefused("refusing to bind a counterfactual manifest (§5.3)")
    # Rows-hash binding (C-F15 clone over the graph rows, §5.4): a tampered or
    # partial graph.jsonl no longer reproduces the recorded chain — refuse, never
    # serve unverified rows. Over the ROWS only; the manifest holds the expected.
    recorded_rows = manifest.get("graph_rows_hash")
    if recorded_rows is not None and graph.graph_rows_hash(d) != recorded_rows:
        raise ServeRefused(
            "graph rows-hash mismatch: graph.jsonl does not reproduce the "
            "manifest's graph_rows_hash (tampered/partial store) — refuse to "
            "serve (§5.4/C-F15)")
    epoch = manifest.get("epoch", {}) if isinstance(manifest, dict) else {}
    recorded = epoch.get("cortex_belief_store_hash")
    live = _live_store_hash(d.parent / "cortex")
    if recorded is None:
        # Built-without-store None-hole (§5.4): the epoch recorded no cortex store,
        # but a live store EXISTS at serve time — a mixed-epoch answer hides behind
        # the null. Refuse explicitly instead of skipping the compare.
        if live is not None:
            raise ServeRefused(
                "built-without-store: the graph epoch recorded no cortex store "
                "(cortex_belief_store_hash null) but a live cortex store exists at "
                "serve time — refuse mixed-epoch (§5.4)")
    elif live != recorded:
        raise ServeRefused(
            "mixed-epoch: live cortex store hash != the manifest's "
            "cortex_belief_store_hash — refuse to serve (§5.4)")
    return epoch, _read_records(d), manifest


def serve_graph(objectives_cache_dir):
    """Bind + serve the compiled graph through the shared bound loader
    (_load_bound). REFUSES (raises ServeRefused) on any of the three C-F15 limbs
    (§5.3/§5.4): a `counterfactual: true` manifest; a graph.jsonl that no longer
    reproduces the manifest's `graph_rows_hash` (tampered/partial rows); or a
    mixed-epoch store. Compile-time states are served labeled with the epoch —
    there is NO serve-time re-derivation."""
    epoch, records, manifest = _load_bound(objectives_cache_dir)
    return {"epoch": epoch, "records": records, "manifest": manifest}


def serve_objective(cache_dir, subject_key):
    """Answer one objective (§5.2/§9 r5): its compiled state + answer flags. Binds
    through the shared loader FIRST (F1 — the three C-F15 REFUSE limbs guard the
    per-objective surface too, never a bypass). An orphaned objective stays
    ANSWERABLE-with-flag (refusal would hide the Captain's own root-edit signal); a
    never-authored subject answers explicit `unknown`."""
    _epoch, records, _manifest = _load_bound(cache_dir)
    for record in records:
        if record.get("subject_key") == subject_key and not _is_edge_record(record):
            # the orphaned flag travels in record["flags"] (the fold writes it there,
            # graph.py:_compile) — there is no top-level `orphaned` key to consult.
            flags = set(record.get("flags") or [])
            return Answer(state=record.get("state", states.STATE_UNKNOWN),
                          flags=frozenset(flags))
    return Answer(state=states.STATE_UNKNOWN, flags=frozenset())


def recommend(objectives_cache_dir, objective_ref):
    """Build a recommendation for one objective from the compiled graph. Binds
    through the shared loader FIRST (F1 — the three C-F15 REFUSE limbs guard the
    recommendation surface too). Cites the full provenance triple (objective_ref,
    evidence_refs, uncertainty, per-dimension scorecard, :180) and REFUSES to call
    an outcome `effective` unless a causal edge reached intervention_supported
    (§4.4/§5.2 P5 cap) — never a naked verdict."""
    _epoch, records, _manifest = _load_bound(objectives_cache_dir)
    node = None
    causal_states = []
    for record in records:
        if _is_edge_record(record):
            if "state" in record and "target_kind" in record:
                causal_states.append(record["state"])
        elif record.get("subject_key") == objective_ref:
            node = record
    effective = states.STATE_INTERVENTION_SUPPORTED in causal_states
    evidence_refs = [{"state": s} for s in causal_states]
    return {
        "objective_ref": objective_ref,
        "evidence_refs": evidence_refs,
        "uncertainty": "unknown",
        "scorecard": {},
        "state": node.get("state") if node else states.STATE_UNKNOWN,
        "effective": effective,
    }
