"""COG-3 SIM-6 — no-scalar-promotion (contract §11 row 6, §4.4, N3, §6.6),
tests-first, no DSN.

Foundry required-sim (:226-239/:180): the value surface is a vector that can NEVER
collapse to a scalar. This suite pins the RUNTIME/BEHAVIORAL half of that law over
the future scorecard + ovi_view surface (the SOURCE-level ratchet mutants —
total_value()/composite_score/numeric-edge-weight scanners — are owned by the
landed test_cog3_no_scalar_ratchet.py + lib_cog3_no_scalar.py; this suite REUSES
those helpers for the standing green-over-the-real-tree tie-in rather than
duplicating them):

  * VECTOR-OR-NOTHING — the scorecard view returns the full per-dimension vector
    and exposes NO scalar accessor (no __float__/total/score) (§4.4, N3);
  * FLOORS INDEPENDENT — ONE failed floor fails the vector regardless of the
    others; no compensatory / weighted-average logic (§4.4 "one failed floor
    fails the vector regardless of the others");
  * UNKNOWN NEVER PASSES A FLOOR — an absent value is `unknown`, never success
    (:239 "missing evidence is unknown, never success");
  * CONFIDENCE ONLY BESIDE source_trust — no bare confidence scalar on the view
    (query.py:89-91 extended; §5.5 carried-whole);
  * OVI PER-INSTRUMENT ONLY — ovi_view projects each instrument separately and
    structurally REFUSES a composite/weights (attack C-M4, §6.6 P10, N6).

FAILURE SIGNATURE (tests-first, §12.2 step 2): every test raises
`ModuleNotFoundError: No module named 'framework.objectives'` at the
`_objectives()` guard in its body. The reuse-ratchet tie-in is GATED behind that
guard on purpose — the ratchet is green-by-vacuity while the package is absent, so
gating it makes it fail-for-absence today (the no-scalar law is meaningfully
checkable only once there is code to scan) rather than passing vacuously. No skip;
no module-level framework.objectives import → no collection error. The T4
implementation must satisfy these UNMODIFIED.

T1-PINNED SURFACE (flagged for T4; integration reconciles names):
  query.scorecard_view(dimensions) -> view — the vector view (§4.4 / §8 query.py).
      `dimensions` = {name: {value?, floor, evidence_binding_refs?}}. The view
      exposes the full per-dimension vector (`states`) + a vector-level
      `floors_met` bool, and NO scalar accessor (float(view) raises; no
      total/score). Per-dimension numeric value/floor are per-instrument measures
      (NOT the forbidden aggregate) — the ratchet forbids AGGREGATION-to-one, not
      a per-dimension floor test.
  ovi_view.project(instruments) -> per-instrument mapping (NO composite/weights).
Integration points: (a) attr-vs-method on the view (read via a tolerant getter);
(b) the value/floor comparison semantics (natural `value >= floor`; ordinal grades
would repoint the seed values, not the structural asserts); (c) the instruments
input shape for ovi_view.project.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_no_scalar as R          # noqa: E402  (REUSE the landed P12 ratchet)


def _objectives():
    """Import indirection (contract §8). Raises ModuleNotFoundError today — the
    honest tests-first absence signature; called first in every test body."""
    from framework.objectives import ovi_view, query
    return query, ovi_view


_MISSING = object()


def _get(obj, name, default=_MISSING):
    """Tolerant read: an attribute or a zero-arg method (integration point (a))."""
    val = getattr(obj, name, default)
    if callable(val):
        val = val()
    return val


def _dims(*, excellent=(), below=(), unknown=(), floor=0.5):
    """A scorecard dimension mapping (§4.4 `{value?, floor, …}`). `excellent`
    dims clear the floor, `below` dims fail it, `unknown` dims carry NO value."""
    d = {}
    for n in excellent:
        d[n] = {"value": 0.95, "floor": floor}
    for n in below:
        d[n] = {"value": 0.05, "floor": floor}
    for n in unknown:
        d[n] = {"floor": floor}                     # absent value => unknown (:239)
    return d


# ===========================================================================
# 1. Vector-or-nothing — full vector returned, NO scalar accessor
# ===========================================================================

class TestVectorOrNothing:
    def test_full_vector_returned(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        dims = _dims(excellent=("cost", "reach"), unknown=("risk",))
        view = query.scorecard_view(dims)
        states = _get(view, "states")
        # §4.4: the query surface returns the FULL vector — every named dimension
        # present, never a collapsed summary.
        assert set(states.keys()) == {"cost", "reach", "risk"}

    def test_view_has_no_scalar_float_accessor(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        view = query.scorecard_view(_dims(excellent=("cost",)))
        # §4.4/N3: no __float__ — the vector can never collapse to a scalar.
        with pytest.raises(TypeError):
            float(view)

    def test_view_has_no_total_or_score_scalar(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        view = query.scorecard_view(_dims(excellent=("cost", "reach")))
        # §4.4/N3: no aggregation-to-one accessor returns a bare number.
        for name in ("total", "total_value", "score", "composite", "overall"):
            val = _get(view, name, None)
            assert not isinstance(val, (int, float)), f"{name} returned a scalar"

    def test_real_objectives_tree_is_scalar_free_when_present(self, tmp_path):
        # REUSE of the landed P12 ratchet (lib_cog3_no_scalar) as SIM-6's standing
        # "vector-or-nothing, permanent CI" tie-in (§11 sim6 / N3). GATED behind
        # the guard so it fails-for-absence today (the ratchet is green-by-vacuity
        # while framework/objectives/ is absent — gating it is the honest signal
        # that the law is not yet SATISFIABLE, only vacuous). Post-impl this
        # asserts the REAL objectives tree carries no scalar leakage.
        _query, _ovi = _objectives()                # guard
        assert R.ratchet_violations(_REPO) == []    # §6.6 P12 permanent ratchet


# ===========================================================================
# 2. Floors independent — one failed floor fails the vector (no compensation)
# ===========================================================================

class TestFloorsIndependent:
    def test_all_floors_met_passes_the_vector(self, tmp_path):
        # baseline so the failure cases below are meaningful, not constant-False.
        query, _ovi = _objectives()                 # guard
        view = query.scorecard_view(_dims(excellent=("cost", "reach", "risk")))
        assert _get(view, "floors_met") is True     # §4.4 all floors met => pass

    def test_one_below_floor_fails_the_whole_vector(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        # one dimension below floor, all others EXCELLENT (§11 sim6 seed).
        view = query.scorecard_view(_dims(excellent=("cost", "reach"), below=("risk",)))
        # §4.4: "one failed floor fails the vector regardless of the others".
        assert _get(view, "floors_met") is False

    def test_compensatory_weighted_average_floor_logic_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim6 mutant "compensatory/weighted-average floor
        # logic"): one dimension at the FLOOR-of-the-floor (0.0) while every other
        # is maximal (1.0). A compensatory/averaging vector would let the excellent
        # dims outweigh the failure and pass. §4.4 "no compensatory logic".
        query, _ovi = _objectives()                 # guard
        dims = {"a": {"value": 0.0, "floor": 0.5},
                "b": {"value": 1.0, "floor": 0.5},
                "c": {"value": 1.0, "floor": 0.5},
                "d": {"value": 1.0, "floor": 0.5}}
        view = query.scorecard_view(dims)
        assert _get(view, "floors_met") is False    # excellent dims never compensate


# ===========================================================================
# 3. Unknown never passes a floor (:239 "missing evidence is unknown, never
#    success")
# ===========================================================================

class TestUnknownNeverPasses:
    def test_unknown_dimension_state_is_unknown(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        view = query.scorecard_view(_dims(excellent=("cost",), unknown=("risk",)))
        state = _get(view, "states")["risk"]
        # :239 — an absent value is `unknown`, not a pass.
        assert "unknown" in str(state).lower()

    def test_unknown_dimension_fails_its_floor_and_the_vector(self, tmp_path):
        query, _ovi = _objectives()                 # guard
        # everything else excellent; only `risk` is unknown.
        view = query.scorecard_view(_dims(excellent=("cost", "reach"), unknown=("risk",)))
        # :239: unknown never passes a floor => the vector does not pass.
        assert _get(view, "floors_met") is False

    def test_unknown_counts_as_pass_is_caught(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim6 mutant "unknown-counts-as-pass floor"): a
        # floor that treats missing evidence as success would pass an all-else-
        # excellent scorecard with one unknown dim. Asserting the vector FAILS
        # kills it (:239).
        query, _ovi = _objectives()                 # guard
        view = query.scorecard_view(_dims(excellent=("cost", "reach"), unknown=("risk",)))
        assert _get(view, "floors_met") is not True   # unknown is never success


# ===========================================================================
# 4. Confidence only beside source_trust — no bare confidence scalar
# ===========================================================================

class TestConfidenceOnlyBesideSourceTrust:
    def test_view_exposes_no_bare_confidence_scalar(self, tmp_path):
        # NEGATIVE CONTROL (§11 sim6 mutant "bare-confidence accessor"): confidence
        # is carried WHOLE inside the binding's source_trust tuple (§4.2/§5.5;
        # query.py:89-91), never as a standalone number on the view.
        query, _ovi = _objectives()                 # guard
        dims = {"cost": {"value": 0.9, "floor": 0.5, "evidence_binding_refs": [
            {"subject_key": "observation/x", "belief_id": "a" * 64,
             "confidence": 0.8,
             "source_trust": {"table_version": 1, "producer_key": "cortex/obs-a"}}]}}
        view = query.scorecard_view(dims)
        conf = _get(view, "confidence", None)
        assert not isinstance(conf, (int, float)), \
            "view exposes a bare confidence scalar (§4.2/§5.5/query.py:89-91)"

    def test_binding_confidence_rides_with_source_trust(self, tmp_path):
        # POSITIVE (§5.5 carried-whole): where a binding carries confidence it also
        # carries its source_trust tuple {table_version, producer_key} — the two
        # are never split. Asserted over the view's serialized bindings, tolerant
        # of exposure shape.
        query, _ovi = _objectives()                 # guard
        dims = {"cost": {"value": 0.9, "floor": 0.5, "evidence_binding_refs": [
            {"subject_key": "observation/x", "belief_id": "a" * 64,
             "confidence": 0.8,
             "source_trust": {"table_version": 1, "producer_key": "cortex/obs-a"}}]}}
        view = query.scorecard_view(dims)
        blob = json.dumps(_get(view, "states"), default=str)
        if "confidence" in blob:                     # confidence surfaced => must ride source_trust
            assert "source_trust" in blob, \
                "confidence surfaced without its source_trust tuple (§5.5)"


# ===========================================================================
# 5. OVI view — per-instrument only, composite structurally REFUSED (C-M4)
# ===========================================================================

class TestOviViewPerInstrumentOnly:
    def test_ovi_projection_is_per_instrument(self, tmp_path):
        _query, ovi = _objectives()                 # guard
        instruments = {"lead_latency": 0.4, "lag_regressions": 0.7}
        result = ovi.project(instruments)
        # §6.6 P10 / N6: each instrument keeps its OWN projection (per-instrument).
        assert isinstance(result, dict)
        for name in instruments:
            assert name in result, f"instrument {name} missing from the projection"

    def test_ovi_projection_refuses_composite_and_weights(self, tmp_path):
        # THE C-M4 shape (§6.6 P10 / N3): the per-instrument view structurally
        # REFUSES any composite_score / weights aggregate.
        _query, ovi = _objectives()                 # guard
        instruments = {"lead_latency": 0.4, "lag_regressions": 0.7}
        result = ovi.project(instruments)
        blob = json.dumps(result, default=str).lower()
        for forbidden in ("composite_score", "composite", "weights", "weight"):
            assert forbidden not in blob, \
                f"ovi_view emitted a forbidden aggregate: {forbidden} (attack C-M4)"


# ===========================================================================
# 6. Recommendation-record SHAPE (§4.4 :180 / §6.6 P12 "recommendation shape
#    test" / §11 sim6 + row-4 SHAPE side). This is the record-shape assert the
#    contract NAMES for SIM-6 (§4.4 "shape-tested (SIM-6, :180)") and was absent
#    from the whole corpus. Every recommendation record carries the FULL tuple
#    (objective_ref, evidence_refs, uncertainty, per-dimension scorecard); a
#    MISSING field is a structural rejection; the scorecard element is the full
#    vector (never a scalar); and an "effective" claim is REFUSED unless an
#    intervention_supported edge stands behind it.
#
#    COORDINATION (2026-07-23): §11 row 4's recommendation assert has two sides —
#    T2's SIM-4 asserts the REFUSAL side over the built graph ("recommendation
#    emitting a naked verdict" mutant / REFUSES 'effective' without an
#    intervention binding); THIS is the record-SHAPE side. Wording kept parallel.
# ===========================================================================

class TestRecommendationRecordShape:
    """T1-PINNED SURFACE (flagged for T4 — THE API for a recommendation record):
        query.recommendation_record(objective_ref, evidence_refs, uncertainty,
                                    scorecard, *, claim=None) -> record
    the narrowest plausible surface on the already-pinned query view (§4.4 / §8
    query.py). A "structural rejection" is pinned as "raises SOME exception,
    never returns a partial record" — the exact exception type is an integration
    point (schema ValidationError / ValueError / TypeError all qualify), read via
    pytest.raises(Exception) exactly as SIM-5's `_raises` does. Integration
    points: (a) attr-vs-key exposure of the record (read via json blob); (b) how
    effectiveness is asserted (a `claim`/verdict kwarg) — the STRUCTURAL pin is
    'effective' ⇒ an intervention_supported edge must stand behind it."""

    # evidence refs carry the derived edge state (§5.2); the default set reaches
    # intervention_supported (the ONLY 'effective'-grade state, §5.2 P3).
    _REFS = [{"subject_key": "tasks/t-1", "belief_id": "a" * 64,
              "state": "intervention_supported"}]
    _SCORECARD = {"cost": {"value": 0.9, "floor": 0.5, "state": "observed"},
                  "reach": {"value": 0.8, "floor": 0.5, "state": "observed"}}

    def _kwargs(self):
        return {"objective_ref": "objective/alpha",
                "evidence_refs": [dict(r) for r in self._REFS],
                "uncertainty": 0.3,
                "scorecard": {k: dict(v) for k, v in self._SCORECARD.items()}}

    def _rec(self, query, **over):
        kw = self._kwargs()
        kw.update(over)
        return query.recommendation_record(**kw)

    def test_complete_record_is_accepted_and_carries_the_full_tuple(self, tmp_path):
        # baseline so the rejection cases below are meaningful, not constant-raise:
        # a COMPLETE record is accepted and carries every §4.4 :180 element.
        query, _ovi = _objectives()                 # guard
        rec = self._rec(query)
        blob = json.dumps(rec, default=str)
        for token in ("objective", "evidence", "uncertainty", "cost", "reach"):
            assert token in blob, \
                f"recommendation record dropped {token!r} from the (objective_ref, " \
                f"evidence_refs, uncertainty, per-dimension scorecard) tuple (§4.4 :180)"

    @pytest.mark.parametrize("drop", ["objective_ref", "evidence_refs",
                                      "uncertainty", "scorecard"])
    def test_missing_any_field_is_structural_rejection(self, tmp_path, drop):
        # §4.4 :180: a recommendation record carries ALL of (objective_ref,
        # evidence_refs, uncertainty, per-dimension scorecard). Dropping ANY one is
        # a STRUCTURAL rejection — never a silently-partial record.
        query, _ovi = _objectives()                 # guard
        kw = self._kwargs()
        kw.pop(drop)
        with pytest.raises(Exception):              # noqa: PT011 — type is an integration point
            query.recommendation_record(**kw)

    def test_scorecard_element_is_the_full_vector_not_a_scalar(self, tmp_path):
        # §4.4/N3: the scorecard element is the FULL per-dimension vector — a bare
        # scalar scorecard is a structural rejection (no collapse-to-one-number).
        query, _ovi = _objectives()                 # guard
        with pytest.raises(Exception):              # noqa: PT011
            self._rec(query, scorecard=0.86)        # a bare number is never a scorecard

    def test_effective_claim_refused_without_intervention_supported_edge(self, tmp_path):
        # §11 row 4 (SHAPE side; T2 SIM-4 owns the graph-refusal side): a record
        # may claim "effective" ONLY with an intervention_supported edge behind it.
        # Evidence that never reaches intervention_supported => the effective claim
        # is REFUSED (structural), never a naked verdict (:180 / §5.2 P5 cap).
        query, _ovi = _objectives()                 # guard
        weak_refs = [{"subject_key": "tasks/t-1", "belief_id": "a" * 64,
                      "state": "observationally_supported"}]
        with pytest.raises(Exception):              # noqa: PT011
            self._rec(query, evidence_refs=weak_refs, claim="effective")

    def test_effective_claim_accepted_with_intervention_supported_edge(self, tmp_path):
        # POSITIVE control (so the refusal above is the missing-edge discriminator,
        # NOT a constant-raise on any `claim`): the SAME "effective" claim is
        # ACCEPTED when an intervention_supported edge stands behind it (§5.2 P3).
        query, _ovi = _objectives()                 # guard
        rec = self._rec(query, claim="effective")   # _REFS carry intervention_supported
        assert rec is not None
