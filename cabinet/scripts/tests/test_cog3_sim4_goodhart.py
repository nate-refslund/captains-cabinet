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
  * `instrument` is never a causal target — enforced at BOTH limbs: the edge
    SCHEMA (edge.v1.json) rejects an instrument-targeted causal edge, AND
    build_graph fails STRUCTURALLY on one — while `indicates` (instrument→outcome)
    is a VALID non-causal trend edge.
  * the §5.6 divergence_report carries the seeded instrument-vs-outcome opposition
    (over an outcome that ALSO TERMINATES A CAUSAL EDGE — the §5.6 join
    precondition; the seed carries an intervention→outcome causal edge).
  * a recommendation cites (objective, evidence, uncertainty) and REFUSES
    "effective" without an intervention (tested) binding.
  * the mismatched-join verdict seed NEVER promotes (verified-join, §5.2b).

NEGATIVE-CONTROL MUTANTS these cells fail (contract §11 row 4):
  volume-promotes state machine (the volume + Simpson cells); instrument-as-
  causal-target accepted (BOTH limbs — the edge-schema cell + the build cell);
  assumption-free promotion
  above hypothesized (the assumption-free cell — never mints `tested`); naked-
  verdict recommendation (the recommendation cell); out-of-`admissible_subjects`
  binding builds successfully (the build-failure cell — must be structural);
  mismatched-join binding promotes (the join cell).

FAILURE SIGNATURE (tests-first — `framework/objectives/` does NOT exist): every
contract cell that drives the runtime imports `framework.objectives.*` FIRST in
its body, so today it fails with `ModuleNotFoundError: No module named
'framework.objectives'`. The edge-schema cell instead reads the (absent)
objectives edge schema => FileNotFoundError — the same tests-first absence
signature at the schema layer. The `TestSim4SeedsAreReal` self-checks carry NO
objectives import and PASS today.

PINNED API (narrowest plausible; flagged for the T4 implementer):
  states.derive_edge_state(edge, bound_views, cutoff) -> EdgeState(state, flags),
        raising states.BuildFailure on the structural binding cells (reused, T3).
  model.assert_legal_causal_target(target_kind) : raises states.BuildFailure for
        "instrument" (a causal edge may terminate only on outcome/constraint,
        §4.2); model.INDICATES_ALLOWED (instrument→outcome) is a legal relational
        pair. The implementer may instead enforce this in graph.build_graph — the
        test pins the OBSERVABLE (a structured failure); BuildFailure is the one
        shared structural-failure class (re-exported from states — T3 layering note).
  framework/schemas/domains/objectives/edge.v1.json (registry PATH; full
        Draft-2020-12, enum/pattern-bearing) : REJECTS a causal-edge row whose
        target kind is `instrument` — validated with jsonschema.Draft202012Validator
        (the cortex schema-test cross-check idiom). And graph.build_graph over a
        roots fixture expressing such an edge raises states.BuildFailure (the build
        limb) — the two limbs of the instrument-as-causal-target mutant.
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
# The intervention whose CAUSAL edge terminates at the outcome — the §5.6 join
# precondition ("the outcome ALSO terminates causal edges"); nit-aligned seed.
_INTERVENTION_SK = "intervention/the-lever"

# The objectives domain schemas (contract §8, registry PATH). Absent today
# (tests-first) => reading one raises FileNotFoundError = the honest absence
# signature. THE PIN: they are full Draft-2020-12 documents (enum/pattern-bearing),
# validated with the reference engine (the cortex schema-test cross-check idiom).
_OBJECTIVES_SCHEMA_DIR = Path(_ROOT) / "framework" / "schemas" / "domains" / "objectives"


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
    promote on the correlation. Returns (edge, bound_views).

    `assumptions` is NON-EMPTY (ruling R-A, §4.2): observationally_supported (P5)
    is above hypothesized and requires declared assumptions, so the P5 cap is
    demonstrated AT P5 — an assumptionless edge would derive P6 and mask the
    Simpson-promotes mutant."""
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
        authored=True, expected_effect="increase",
        assumptions=("declared-confounder-and-selection",),   # R-A: P5 needs assumptions
        admissible_subjects=frozenset(admissible), join_spec=(),
        evidence_bindings=tuple(bindings))
    return edge, tuple(views)


def _divergence_store(cache_root):
    """Persist a cortex store under cache_root/cortex seeding the §5.6 opposition:
    the instrument's head INCREASES while the outcome's head DECREASES on the
    shared dimension. An INTERVENTION observation is ALSO seeded (nit / §5.6 join
    precondition): §5.6 only reports over an outcome that ALSO TERMINATES A CAUSAL
    EDGE, so the seed carries the intervention whose causal edge terminates at the
    outcome (the edge itself is adapter-authored from _divergence_roots). Returns
    (cortex_dir, objectives_dir)."""
    protos = [
        L.observation_proto(_INSTRUMENT_SK, L.DIMENSION,
                            claim=L.observed_effect_claim("increase"),
                            seq=0, event_suffix="instr"),
        L.observation_proto(_OUTCOME_SK, L.DIMENSION,
                            claim=L.observed_effect_claim("decrease"),
                            seq=0, event_suffix="outc"),
        L.observation_proto(_INTERVENTION_SK, L.DIMENSION,
                            claim=L.observed_effect_claim("increase"),
                            seq=0, event_suffix="interv"),
    ]
    beliefs = L.fold_beliefs(protos)
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    L.persist_cortex_store(cortex, beliefs)
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    return cortex, objectives


def _divergence_roots(dir_path):
    """A PROVISIONAL roots fixture for the §5.6 divergence seed: an objective
    (hit-the-goal → the outcome), an INSTRUMENT with an `indicates` edge to the
    outcome (the trend link §5.6 iterates), and an INTERVENTION with a CAUSAL edge
    TERMINATING at the outcome (so the outcome ALSO terminates a causal edge — the
    §5.6 join precondition; nit). The roots-adapter schema is provisional
    (lib_cog3_fixtures.write_roots_yml note), so this local helper expresses the
    nodes/edges directly. ADAPTER-DEPENDENT: T4 aligns the SEED to the final
    adapter surface; the FIRM contract is the reported opposition over a
    causal-terminating outcome. Plain text (no yaml dependency), import-inert."""
    text = (
        "# fixture divergence roots (COG-3 §5.6, provisional shape)\n"
        "directions:\n"
        "  - slug: hit-the-goal\n"
        '    statement: "move the real outcome"\n'
        "objectives:\n"
        "  - slug: hit-the-goal\n"
        f"    outcome: {_OUTCOME_SK}\n"
        "nodes:\n"
        f"  - {{kind: instrument, subject_key: {_INSTRUMENT_SK}}}\n"
        f"  - {{kind: intervention, subject_key: {_INTERVENTION_SK}}}\n"
        f"  - {{kind: outcome, subject_key: {_OUTCOME_SK}}}\n"
        "indicates_edges:\n"
        f"  - {{source: {_INSTRUMENT_SK}, target: {_OUTCOME_SK}, dimension: {L.DIMENSION}}}\n"
        "causal_edges:\n"
        f"  - source: {_INTERVENTION_SK}\n"
        f"    target: {_OUTCOME_SK}          # causal edge TERMINATES at the outcome\n"
        f"    dimension: {L.DIMENSION}\n"
        "    expected_effect: increase\n")
    path = Path(dir_path) / "directions.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _roots_with_instrument_causal_target(dir_path):
    """A PROVISIONAL roots fixture expressing an ILLEGAL causal edge whose TARGET
    is an instrument (§4.2: causal edges terminate on outcome/constraint ONLY).
    ADAPTER-DEPENDENT (same disposition as _divergence_roots): T4 aligns the SEED;
    the FIRM contract is that build_graph fails STRUCTURALLY on this edge."""
    text = (
        "# fixture roots with an ILLEGAL causal-to-instrument edge (COG-3 §4.2)\n"
        "directions:\n"
        "  - slug: hit-the-goal\n"
        '    statement: "move the real outcome"\n'
        "nodes:\n"
        f"  - {{kind: instrument, subject_key: {_INSTRUMENT_SK}}}\n"
        f"  - {{kind: intervention, subject_key: {_INTERVENTION_SK}}}\n"
        "causal_edges:\n"
        f"  - source: {_INTERVENTION_SK}\n"
        f"    target: {_INSTRUMENT_SK}     # ILLEGAL: causal target is an instrument\n"
        f"    dimension: {L.DIMENSION}\n"
        "    expected_effect: increase\n")
    path = Path(dir_path) / "directions.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _instrument_targeted_causal_edge_row():
    """A §4.2 causal-edge RECORD whose target node kind is `instrument` — the
    illegal shape a correct edge.v1.json must reject (causal edges terminate on
    outcome/constraint ONLY). Best-effort per §4.2; the FIRM contract is the
    rejection on the instrument target (the schema is absent today, so the exact
    field shape does not affect the absence signature). Documented pin."""
    return {
        "edge_id": L.belief.digest(["edge", "instrument-target"]),
        "source_node_id": L.belief.digest(["node", "intervention", "the-lever"]),
        "target_node_id": L.belief.digest(["node", "instrument", "proxy-metric"]),
        "target_kind": "instrument",           # <- the illegal causal target
        "dimension": L.DIMENSION,
        "expected_effect": "increase",
        "admissible_subjects": [],
        "evidence_bindings": [],
        "assumptions": ["declared-confounder-and-selection"],
        "uncertainty": "unknown",
    }


# ===========================================================================
# CONTRACT CELLS — import framework.objectives FIRST => absence signature today.
# ===========================================================================

def test_no_observational_volume_promotes_the_causal_edge(consequence_ledger):
    # §5.2 P5 cap (SIM-4 volume mutant): 100 direction-supporting observations
    # stay observationally_supported — no VOLUME of observations mints
    # intervention_supported. Bites the volume-promotes state machine. The edge
    # DECLARES assumptions (ruling R-A, §4.2 "assumptions REQUIRED non-empty for
    # any edge deriving above hypothesized"), so the cap is demonstrated AT P5 —
    # an assumptionless edge would derive P6 and hide the volume mutant.
    states = _import_states()
    cell = L.EdgeCell(expected_effect="increase", assumptions=True,
                      bindings=_VOL_SUPPORTING)
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


def test_edge_schema_rejects_an_instrument_causal_target():
    # §4.2 / §11 row-4 mutant ('instrument-as-causal-target edge accepted'), SCHEMA
    # limb: edge.v1.json must REJECT a causal edge terminating on an instrument.
    # The helper-pin cell above only pins model.assert_legal_causal_target; the
    # mutant survives if build_graph never calls the helper AND the schema doesn't
    # gate target kinds — this cell + the build cell below close BOTH limbs.
    # Validated with the reference Draft-2020-12 engine (the jsonschema cross-check
    # idiom the cortex/registry schema tests use, framework/triggers/tests/
    # test_schema_registry.py:301-354), loaded by the schema's registry PATH.
    # Absent today => FileNotFoundError = the tests-first absence signature.
    schema = json.loads(
        (_OBJECTIVES_SCHEMA_DIR / "edge.v1.json").read_text(encoding="utf-8"))
    jsonschema = pytest.importorskip("jsonschema")
    row = _instrument_targeted_causal_edge_row()
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(row))
    assert errors, \
        "§4.2: edge.v1.json must reject a causal edge whose target is an instrument"


def test_build_rejects_an_instrument_targeted_causal_edge(tmp_path):
    # §4.2 / §11 row-4 mutant, BUILD limb: build_graph over a fixture expressing a
    # causal edge that TERMINATES on an instrument is a STRUCTURAL build failure
    # (states.BuildFailure — the one shared structural-failure class), never a
    # silent skip. Closes the second limb (build_graph never calls
    # model.assert_legal_causal_target).
    # [ADAPTER-DEPENDENT: the illegal edge is expressed through the roots/adapter
    #  surface; if the final adapter schema differs, T4 aligns the SEED — the FIRM
    #  contract is the structural failure. Flagged like the divergence cell.]
    graph = _import_graph()
    states = _import_states()
    _cortex, objectives = _divergence_store(tmp_path / "cache")
    roots = _roots_with_instrument_causal_target(tmp_path)
    with pytest.raises(states.BuildFailure):
        graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)


def test_divergence_report_is_a_display_only_manifest_surface(tmp_path):
    # §5.6: the build emits a `divergence_report` in graph-manifest.json — a FLAG
    # surface (list), display-only, NO state change, NO score. This pins the
    # surface EXISTS and is structurally a list (a no-divergence-surface mutant
    # emits no such key). Content is asserted in the ADAPTER-DEPENDENT cell below.
    graph = _import_graph()
    cortex, objectives = _divergence_store(tmp_path / "cache")
    roots = _divergence_roots(tmp_path)   # nit: outcome terminates a causal edge (§5.6)
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
    roots = _divergence_roots(tmp_path)   # nit: outcome terminates a causal edge (§5.6)
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
        # nit: the intervention seed (§5.6 join precondition — the outcome ALSO
        # terminates a causal edge) is real substrate too.
        assert _INTERVENTION_SK in by_sub

    def test_objectives_edge_schema_is_absent_today(self):
        # documents the tests-first signature for the edge-schema cell: the
        # objectives edge schema does not exist yet, so that cell fails on the
        # absent schema file (FileNotFoundError).
        assert not (_OBJECTIVES_SCHEMA_DIR / "edge.v1.json").exists()
