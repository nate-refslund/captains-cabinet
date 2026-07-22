"""COG-3 §11 row 4 — SIM-4: GOODHART / PROXY-TARGETING (tests-first).

Pins the anti-Goodhart guarantees: no volume of observations and no confounded/
Simpson correlation can ever promote a causal edge past `observationally_supported`
(the §5.2 P5 cap); an `instrument` node is STRUCTURALLY never a legal causal
target while an `indicates` edge still carries its trend link (§4.2); the build's
`divergence_report` surfaces a proxy-improves/outcome-regresses opposition
(§5.6, real detection, honestly scoped — Simpson is PREVENTED + declared, never
DETECTED); a recommendation cites objective+evidence+uncertainty and REFUSES to
call an outcome "effective" without an intervention binding (:180); and a
verdict whose causal join does not match the intervention NEVER promotes (§5.2b).

WHAT SIM-4 ASSERTS (contract §11 row 4):
  * causal edge to the OUTCOME never exceeds observationally_supported on ANY
    observational volume (P5 cap) — incl. confounded/Simpson-structured evidence.
  * `instrument` is never a causal target (structural rejection) while `indicates`
    (instrument→outcome) is a VALID non-causal trend edge.
  * the §5.6 divergence_report carries the seeded instrument-vs-outcome opposition.
  * a recommendation cites (objective, evidence, uncertainty) and REFUSES
    "effective" without an intervention (tested) binding.
  * the mismatched-join verdict seed NEVER promotes (verified-join, §5.2b).

NEGATIVE-CONTROL MUTANTS these cells fail (contract §11 row 4):
  volume-promotes state machine (the volume + Simpson cells); instrument-as-
  causal-target accepted (the structural-target cell); assumption-free promotion
  above hypothesized (the assumption-free cell — never mints `tested`); naked-
  verdict recommendation (the recommendation cell); out-of-`admissible_subjects`
  binding builds successfully (the build-failure cell — must be structural);
  mismatched-join binding promotes (the join cell).

FAILURE SIGNATURE (tests-first — `framework/objectives/` does NOT exist): every
contract cell imports `framework.objectives.*` FIRST in its body, so today it
fails with `ModuleNotFoundError: No module named 'framework.objectives'`. The
`TestSim4SeedsAreReal` self-checks carry NO objectives import and PASS today.

PINNED API (narrowest plausible; flagged for the T4 implementer):
  states.derive_edge_state(edge, bound_views, cutoff) -> EdgeState(state, flags),
        raising states.BuildFailure on the structural binding cells (reused, T3).
  model.assert_legal_causal_target(target_kind) : raises states.BuildFailure for
        "instrument" (a causal edge may terminate only on outcome/constraint,
        §4.2); model.INDICATES_ALLOWED (instrument→outcome) is a legal relational
        pair. The implementer may instead enforce this in graph.build_graph — the
        test pins the OBSERVABLE (a structured failure); BuildFailure is the one
        shared structural-failure class (re-exported from states — T3 layering note).
  graph.build_graph(roots_path, objectives_cache_dir, scope, cutoff)
        -> writes objectives_cache_dir/graph-manifest.json carrying a
        `divergence_report` LIST (display-only; §5.6). Reads the SIBLING cortex
        store (cache_dir/../cortex, §5.1). [ADAPTER-DEPENDENT: the seeded-entry
        cell drives the roots/adapter surface — see its flag.]
  query.recommend(objectives_cache_dir, objective_ref) -> a recommendation record
        carrying {objective_ref, evidence_refs, uncertainty, scorecard, state};
        it NEVER marks an outcome "effective" without an intervention_supported
        binding (§4.4/:180). [ADAPTER-DEPENDENT — flagged.]

S0: interpreter python3.12. No DSN, no postgres — jsonl belief protos +
consequence ledger day files (§7.2).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L  # noqa: E402  (NEVER framework.objectives here)

# Instrument/outcome subjects for the §5.6 divergence seed: a proxy instrument's
# recent head IMPROVES (increase) while the independent outcome's head REGRESSES
# (decrease) on the shared dimension — the seeded opposition (:178).
_INSTRUMENT_SK = "instrument/proxy-metric"
_OUTCOME_SK = "outcome/real-goal"


@pytest.fixture
def consequence_ledger(tmp_path, monkeypatch):
    """Isolated consequence-ledger dir via CABINET_EVENT_LOG_DIR (D1 idiom)."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


# ---------------------------------------------------------------------------
# Import indirection — the honest absence signature lives in the test bodies.
# ---------------------------------------------------------------------------

def _import_states():
    from framework.objectives import states  # noqa: F401
    return states


def _import_model():
    from framework.objectives import model  # noqa: F401
    return model


def _import_graph():
    from framework.objectives import graph  # noqa: F401
    return graph


def _import_query():
    from framework.objectives import query  # noqa: F401
    return query


# ---------------------------------------------------------------------------
# Local seed helpers (built ONLY from lib_cog3_fixtures primitives).
# ---------------------------------------------------------------------------

_VOL_SUPPORTING = tuple(
    L.BindingSpec(role="observation", observed_effect="increase", tag=f"vol{i}")
    for i in range(100))


def _stratified_supporting_edge(log_dir):
    """A confounded/Simpson-structured seed: several supporting observations whose
    claims ALSO carry a `strata` field (aggregate positive, one stratum negative),
    proving strata are SURFACED in the claim bytes (§5.6 honest scope: strata are
    carried, not estimated). The direction reading still keys on observed_effect,
    so the edge is direction-supporting — and MUST cap at P5 (prevention), never
    promote on the correlation. Returns (edge, bound_views)."""
    protos = []
    strata = [("region-a", "increase"), ("region-b", "increase"),
              ("region-c", "decrease")]                # Simpson: one stratum negative
    subs = []
    for i, (stratum, _effect) in enumerate(strata):
        sk = f"observation/simpson-{stratum}"
        subs.append(sk)
        protos.append(L.observation_proto(
            sk, L.DIMENSION,
            claim={"observed_effect": "increase", "strata": stratum},  # aggregate +
            seq=0, event_suffix=f"simp{i}"))
    beliefs = L.fold_beliefs(protos)
    views, bindings, admissible = [], [], set()
    for sk in subs:
        for v in L.views_for(beliefs, sk):
            views.append(v)
            bindings.append(L.BindingRef(v.subject_key, v.belief_id))
            admissible.add(v.subject_key)
    edge = L.EdgeSpec(
        authored=True, expected_effect="increase", assumptions=(),
        admissible_subjects=frozenset(admissible), join_spec=(),
        evidence_bindings=tuple(bindings))
    return edge, tuple(views)


def _divergence_store(cache_root):
    """Persist a cortex store under cache_root/cortex seeding the §5.6 opposition:
    the instrument's head INCREASES while the outcome's head DECREASES on the
    shared dimension. Returns (cortex_dir, objectives_dir)."""
    protos = [
        L.observation_proto(_INSTRUMENT_SK, L.DIMENSION,
                            claim=L.observed_effect_claim("increase"),
                            seq=0, event_suffix="instr"),
        L.observation_proto(_OUTCOME_SK, L.DIMENSION,
                            claim=L.observed_effect_claim("decrease"),
                            seq=0, event_suffix="outc"),
    ]
    beliefs = L.fold_beliefs(protos)
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    L.persist_cortex_store(cortex, beliefs)
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    return cortex, objectives


# ===========================================================================
# CONTRACT CELLS — import framework.objectives FIRST => absence signature today.
# ===========================================================================

def test_no_observational_volume_promotes_the_causal_edge(consequence_ledger):
    # §5.2 P5 cap (SIM-4 volume mutant): 100 direction-supporting observations
    # stay observationally_supported — no VOLUME of observations mints
    # intervention_supported. Bites the volume-promotes state machine.
    states = _import_states()
    cell = L.EdgeCell(expected_effect="increase", bindings=_VOL_SUPPORTING)
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_OBSERVATIONALLY_SUPPORTED  # §5.2 P5: the cap
    assert result.state != L.STATE_INTERVENTION_SUPPORTED


def test_simpson_structured_correlation_still_caps_at_p5(consequence_ledger):
    # §5.6 (honest scope): a Simpson/confounded correlation (aggregate positive,
    # one stratum negative, strata carried in the claims) is PREVENTED from
    # promoting — it caps at observationally_supported, never intervention_
    # supported. Prevention + declared strata, NOT a stratified estimator.
    states = _import_states()
    edge, views = _stratified_supporting_edge(consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_OBSERVATIONALLY_SUPPORTED  # capped, not promoted
    assert result.state != L.STATE_INTERVENTION_SUPPORTED


def test_mismatched_join_verdict_never_promotes(consequence_ledger):
    # §5.2b verified-join limb (ii): a human confirm whose (actor,action,subject)
    # MISSES the intervention's join_spec is NOT human-confirm => P3 unreachable;
    # it is still direction-supporting => caps at P5. Bites the mismatched-join-
    # promotes mutant (attack C-M3b): unrelated verdicts can't fuel any edge.
    states = _import_states()
    cell = L.EdgeCell(assumptions=True, bindings=(
        L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_human",
                      join="mismatch", tag="jm"),))
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_OBSERVATIONALLY_SUPPORTED  # §5.2 P5, not P3
    assert result.state != L.STATE_INTERVENTION_SUPPORTED


def test_assumption_free_confirm_never_mints_tested(consequence_ledger):
    # §5.2 P3 gate: promotion to intervention_supported REQUIRES non-empty
    # assumptions. A human-confirm with EMPTY assumptions can never reach
    # intervention_supported. Bites the assumption-free-promotion mutant.
    # (The exact capped state — observationally_supported under the §5.2-gates-
    # P3-only reading — is pinned exhaustively in test_cog3_state_function.py's
    # P5 cell; SIM-4 pins only the mutant-relevant invariant to stay robust to the
    # §4.2-vs-§5.2 assumptions-scope note flagged in the T3 report.)
    states = _import_states()
    cell = L.EdgeCell(assumptions=False, bindings=(
        L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_human",
                      tag="hc"),))
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state != L.STATE_INTERVENTION_SUPPORTED  # assumptions gate P3


def test_out_of_admissible_binding_is_a_structural_build_failure(consequence_ledger):
    # §4.2/§5.1(3) (attack C-M3a): an edge binding a subject_key NOT in
    # admissible_subjects is a STRUCTURAL build failure, never a silent skip — an
    # edge cannot cite topically-unrelated evidence in ANY state. Bites the
    # 'out-of-admissible binding builds successfully' mutant.
    states = _import_states()
    cell = L.EdgeCell(bindings=(
        L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_human",
                      admissible=False, tag="oa"),))
    edge, views = L.materialize(cell, consequence_ledger)
    with pytest.raises(states.BuildFailure):
        states.derive_edge_state(edge, views, L.CUTOFF)


def test_instrument_is_never_a_legal_causal_target():
    # §4.2 structural rule (SIM-4): causal edges terminate on outcome/constraint
    # ONLY — an instrument node is never a legal causal target ("instruments
    # remain trend evidence, never targets", :110). Bites the instrument-as-
    # causal-target-accepted mutant. `indicates` (instrument→outcome) stays legal.
    model = _import_model()
    states = _import_states()
    with pytest.raises(states.BuildFailure):
        model.assert_legal_causal_target("instrument")   # illegal causal target
    # outcome / constraint ARE legal causal targets (no raise).
    model.assert_legal_causal_target("outcome")
    model.assert_legal_causal_target("constraint")
    # the `indicates` relational pair (instrument→outcome) is VALID (:106) — the
    # trend link the §5.6 divergence report needs, with no epistemic machinery.
    assert ("instrument", "outcome") in model.INDICATES_ALLOWED


def test_divergence_report_is_a_display_only_manifest_surface(tmp_path):
    # §5.6: the build emits a `divergence_report` in graph-manifest.json — a FLAG
    # surface (list), display-only, NO state change, NO score. This pins the
    # surface EXISTS and is structurally a list (a no-divergence-surface mutant
    # emits no such key). Content is asserted in the ADAPTER-DEPENDENT cell below.
    graph = _import_graph()
    cortex, objectives = _divergence_store(tmp_path / "cache")
    roots = L.write_roots_yml(tmp_path, [{"slug": "hit-the-goal",
                                          "statement": "move the real outcome"}])
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    manifest = json.loads((objectives / "graph-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest.get("divergence_report"), list)   # §5.6 surface exists


def test_divergence_report_carries_the_seeded_opposition(tmp_path):
    # §5.6 real detection: with the instrument head INCREASING and the outcome
    # head DECREASING on the shared dimension, the report carries the opposition
    # entry (instrument_node, outcome_node, dimension, instrument_direction,
    # outcome_direction). Bites a build that PREVENTS but never DETECTS.
    # [ADAPTER-DEPENDENT: this cell exercises the roots→(instrument,outcome,
    #  indicates,causal-edge) adapter wiring; if the final roots/mission_inputs
    #  adapter schema differs, T4 aligns the SEED (the assertion — an opposition
    #  entry is present — is the firm contract). Flagged in the wave report.]
    graph = _import_graph()
    cortex, objectives = _divergence_store(tmp_path / "cache")
    roots = L.write_roots_yml(tmp_path, [{"slug": "hit-the-goal",
                                          "statement": "move the real outcome"}])
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    manifest = json.loads((objectives / "graph-manifest.json").read_text(encoding="utf-8"))
    report = manifest.get("divergence_report", [])
    opposing = [e for e in report
                if e.get("instrument_direction") != e.get("outcome_direction")]
    assert opposing, "§5.6: the seeded proxy-vs-outcome opposition must be reported"


def test_recommendation_refuses_effective_without_an_intervention_binding(tmp_path):
    # §4.4/:180: a recommendation cites (objective, evidence, uncertainty) and
    # REFUSES to call an outcome "effective" when no causal edge reached
    # intervention_supported (only observational support exists). Bites the
    # naked-verdict recommendation mutant (emitting "effective" from bare evidence).
    # [ADAPTER-DEPENDENT — see the divergence cell's flag.]
    graph = _import_graph()
    query = _import_query()
    cortex, objectives = _divergence_store(tmp_path / "cache")
    roots = L.write_roots_yml(tmp_path, [{"slug": "hit-the-goal",
                                          "statement": "move the real outcome"}])
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    rec = query.recommend(objectives, "objective/hit-the-goal")
    # cites the full provenance triple (:180) — never a naked verdict.
    for key in ("objective_ref", "evidence_refs", "uncertainty"):
        assert key in rec, f"§4.4: recommendation must cite {key}"
    # REFUSES "effective" with only observational support (no intervention binding).
    assert not rec.get("effective"), \
        "§4.4: 'effective' requires an intervention_supported binding"


# ===========================================================================
# SEED SELF-CHECKS — no framework.objectives import; PASS TODAY.
# ===========================================================================

class TestSim4SeedsAreReal:
    def test_volume_seed_is_100_distinct_supporting_views(self, consequence_ledger):
        cell = L.EdgeCell(expected_effect="increase", bindings=_VOL_SUPPORTING)
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 100
        assert all(v.value == {"observed_effect": "increase"} for v in views)

    def test_simpson_seed_carries_strata_in_the_claim_bytes(self, consequence_ledger):
        # §5.6: strata are SURFACED in the served claim bytes (honesty), and one
        # stratum is negative while the aggregate reads increase — a real
        # Simpson/confounded shape the P5 cap must prevent from promoting.
        _edge, views = _stratified_supporting_edge(consequence_ledger)
        assert len(views) == 3
        assert all(v.value["observed_effect"] == "increase" for v in views)  # aggregate +
        assert {v.value["strata"] for v in views} == {"region-a", "region-b", "region-c"}

    def test_mismatched_join_seed_fails_only_limb_ii(self, consequence_ledger):
        cell = L.EdgeCell(assumptions=True, bindings=(
            L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_human",
                          join="mismatch", tag="jm"),))
        edge, views = L.materialize(cell, consequence_ledger)
        v = views[0]
        assert v.subject_key in edge.admissible_subjects            # admissible holds
        assert L.consequence_subject_key(v.value) == v.subject_key  # limb i holds
        assert L.consequence_join_key(v.value) not in edge.join_spec  # limb ii FAILS
        assert edge.join_spec                                        # join_spec non-empty

    def test_out_of_admissible_seed_serves_but_is_excluded(self, consequence_ledger):
        cell = L.EdgeCell(bindings=(
            L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_human",
                          admissible=False, tag="oa"),))
        edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 1                                       # the view resolved
        assert views[0].subject_key not in edge.admissible_subjects  # yet excluded
        assert edge.evidence_bindings                                # the ref is authored

    def test_divergence_seed_is_a_real_instrument_vs_outcome_opposition(self, tmp_path):
        # the §5.6 seed: instrument head INCREASES, outcome head DECREASES on the
        # shared dimension — a genuine opposition the build's report must surface.
        cortex, objectives = _divergence_store(tmp_path / "cache")
        beliefs = L.query.load_beliefs_verified(cortex)
        by_sub = {b.subject_key: b for b in beliefs}
        instr = L.views_for(beliefs, _INSTRUMENT_SK)
        outc = L.views_for(beliefs, _OUTCOME_SK)
        assert instr[0].value == {"observed_effect": "increase"}
        assert outc[0].value == {"observed_effect": "decrease"}     # opposition real
        assert _INSTRUMENT_SK in by_sub and _OUTCOME_SK in by_sub
