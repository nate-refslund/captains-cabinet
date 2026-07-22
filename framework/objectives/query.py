"""framework.objectives.query — the U1 slices of the objectives view surface
(COG-3 contract rev-1 §5.2 / §4.4): the bijective Captain-vocabulary table, the
vector-scorecard shape, and the recommendation-record shape.

VECTOR-OR-NOTHING (N3/P12): the scorecard view returns the full per-dimension
vector and exposes NO scalar accessor — no __float__, no total/score/composite,
no aggregation to one number. One failed floor fails the whole vector regardless
of the others (no compensatory logic); an absent value is `unknown` and unknown
NEVER passes a floor. Confidence rides WHOLE inside a binding's source_trust
tuple, never as a bare number on the view (§5.5).

NOT BUILT HERE (U2): the serve/hash-binding surface — serve-time manifest-hash
REFUSE, counterfactual-manifest REFUSE, mixed-epoch REFUSE — lands with graph.py.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core).
"""
from __future__ import annotations

from dataclasses import dataclass

from framework.objectives import states

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
