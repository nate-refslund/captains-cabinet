"""COG-3 §11 row 3 — SIM-3: COUNTERFACTUALS + PREDICTION WALLS (tests-first).

Pins the two guarantees that keep counterfactual reasoning out of the evidence
plane: (1) a prediction is NEVER admissible as evidence — THREE independent walls
(schema / store-resolution / producer, §4.3), so no volume of predictions and no
self-confirming loop can change any epistemic state; and (2) a counterfactual is
pure recomputation in its OWN home — branch output lands ONLY under
`counterfactuals/<digest>/`, the canonical `graph.jsonl`/`graph-manifest.json`
stay byte-identical, replay is byte-deterministic per branch, and the serve
surface REFUSES any manifest marked `counterfactual: true` (§5.3/§5.4).

WHAT SIM-3 ASSERTS (contract §11 row 3):
  * prediction NEVER admissible as evidence — each wall tested INDEPENDENTLY:
      (a) schema — the `pred-` id pattern is disjoint from the belief-id pattern.
      (b) store-resolution — a `pred-` ref resolves in NO verified cortex store,
          so binding it is a structural build failure.
      (c) producer/stream — a minted prediction lands ONLY in its own store,
          never the cortex store; `prediction` is not a belief kind (G-F4).
  * state / canonical graph unchanged by ANY prediction volume (N1 excludes them).
  * the belief-vs-prediction id disjointness is pinned AT THE SCHEMAS
    (edge.v1.json + prediction.v1.json jsonschema `pattern`s), not only the model
    regexes (wall a strengthened).
  * prediction SCORING lands ONLY in the predictions store (accuracy record; the
    predictions-manifest chain grows; cortex + canonical graph bytes UNCHANGED);
    a scored-accurate prediction NEVER changes an edge state on rebuild (the
    scored→auto-evidence leg of the self-confirming loop); the accuracy record
    keeps the pred- namespace (structurally unciteable as a belief).
  * counterfactual output lands ONLY under counterfactuals/<digest>/; canonical
    graph.jsonl + graph-manifest.json byte-identical after any branch build.
  * replay byte-reproduces per branch under the same epoch inputs.
  * serve REFUSES a `counterfactual: true` manifest.

NEGATIVE-CONTROL MUTANTS these cells fail (contract §11 row 3):
  builder admitting a prediction into evidence_bindings (walls a+b); self-
  confirming loop / prediction→scored→auto-evidence (the prediction-volume cell);
  adapter stream accepting a prediction-kind row (wall c); branch build clobbering
  the canonical graph (the home-isolation cell); serve binding a counterfactual
  manifest (the serve-REFUSE cell).

FAILURE SIGNATURE (tests-first — `framework/objectives/` does NOT exist): every
contract cell that drives the runtime imports `framework.objectives.*` FIRST in
its body, so today it fails with `ModuleNotFoundError: No module named
'framework.objectives'`. The schema-disjointness cell instead reads the objectives
domain schemas (absent today) => FileNotFoundError — the same tests-first absence
signature at the schema layer. The `TestSim3SeedsAreReal` self-checks carry NO
objectives import and PASS today.

PINNED API (narrowest plausible; flagged for the T4 implementer):
  model.BELIEF_ID_RE / model.PREDICTION_ID_RE — the two DISJOINT id patterns
        (`^[0-9a-f]{64}$` vs `^pred-[0-9a-f]{64}$`, §4.3) baked into the schemas.
  states.derive_edge_state(edge, bound_views, cutoff), raising states.BuildFailure
        on a binding ref that resolves in no served view (reused, T3).
  graph.build_graph(roots_path, objectives_cache_dir, scope, cutoff) — pure,
        deterministic; writes objectives_cache_dir/{graph.jsonl,graph-manifest.json};
        reads the SIBLING cortex store (cache_dir/../cortex, §5.1).
  counterfactual.mint_prediction(objectives_cache_dir, edge_id, assumption_set,
        cutoff, predicted_claim) -> a `pred-<digest>` id; appends to
        objectives_cache_dir/predictions/predictions.jsonl (§4.3), NEVER the
        cortex store.
  counterfactual.score_prediction(objectives_cache_dir, prediction_id,
        outcome_view) -> an accuracy record dict {accuracy_id (a `pred-<digest>`
        id — the pred- namespace), prediction_id, …} APPENDED to
        predictions/predictions.jsonl + advancing predictions-manifest.json (§4.3);
        NEVER the cortex store, NEVER auto-promoted to evidence (the self-
        confirming-loop wall). THIS is the pinned scoring surface (cache-dir first,
        matching mint_prediction; outcome_view = the realized-outcome claim/view
        the forecast is scored against).
  counterfactual.build_branch(roots_path, objectives_cache_dir, scope, cutoff,
        assumption_overrides) -> the branch dir objectives_cache_dir/
        counterfactuals/<digest>/ (digest = recorder digest of (cutoff,
        assumption_overrides)); writes a `counterfactual: true` manifest there;
        NEVER writes the canonical root (§5.3).
  query.serve_graph(dir) -> served graph; RAISES query.ServeRefused when the
        manifest is `counterfactual: true` (§5.3/§5.4 second REFUSE clause).

S0: interpreter python3.12. No DSN, no postgres — jsonl belief protos (§7.2).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L  # noqa: E402  (NEVER framework.objectives here)

# The two disjoint id patterns (§4.3) — asserted structurally in a self-check and
# pinned against the objectives model's own constants in the contract cell.
_BELIEF_ID_RE = r"^[0-9a-f]{64}$"
_PREDICTION_ID_RE = r"^pred-[0-9a-f]{64}$"
_SYNTH_EDGE_ID = L.belief.digest(["edge", "counterfactual", "E"])   # 64-hex synthetic

# The objectives domain schemas (contract §8, registry PATH). Absent today
# (tests-first) => reading one raises FileNotFoundError = the honest absence
# signature. THE PIN (documented once): the objectives id-namespace disjointness
# (§4.2:81 / §4.3) is baked into these schema FILES as jsonschema `pattern`s —
# edge.v1.json types evidence-binding ids to the belief-id pattern,
# prediction.v1.json types its id to the pred- pattern — so the disjointness is
# pinned AT THE SCHEMAS, not only the model regexes (wall a).
_OBJECTIVES_SCHEMA_DIR = Path(_ROOT) / "framework" / "schemas" / "domains" / "objectives"


def _schema_pattern_strings(schema):
    """Every jsonschema `pattern` value anywhere in a schema doc (recursive), so
    the disjointness assertion is robust to where the id typing is nested."""
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "pattern" and isinstance(val, str):
                    found.add(val)
                walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return found


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


def _import_counterfactual():
    from framework.objectives import counterfactual  # noqa: F401
    return counterfactual


def _import_query():
    from framework.objectives import query  # noqa: F401
    return query


# ---------------------------------------------------------------------------
# Local seed helpers (built ONLY from lib_cog3_fixtures primitives).
# ---------------------------------------------------------------------------

def _seed_cache(cache_root):
    """Persist a minimal (non-empty) cortex store under cache_root/cortex and a
    roots file, returning (cortex_dir, objectives_dir, roots_path). One
    direction-supporting observation keeps the store valid + non-trivial without
    depending on any adapter input format (the byte-identity/home/serve asserts
    are input-AGNOSTIC structural facts)."""
    proto = L.observation_proto("observation/seed", L.DIMENSION,
                                claim=L.observed_effect_claim("increase"),
                                seq=0, event_suffix="cf-seed")
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    L.persist_cortex_store(cortex, L.fold_beliefs([proto]))
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    roots = L.write_roots_yml(cache_root, [{"slug": "ship-fast",
                                            "statement": "ship reliably"}])
    return cortex, objectives, roots


def _canonical_bytes(objectives_dir):
    """The canonical graph's on-disk bytes (the N1 rebuild-determinism surface —
    graph.jsonl + graph-manifest.json; predictions/ + counterfactuals/ excluded
    BY NAME, §1 N1)."""
    return ((objectives_dir / "graph.jsonl").read_bytes(),
            (objectives_dir / "graph-manifest.json").read_bytes())


# ===========================================================================
# CONTRACT CELLS — import framework.objectives FIRST => absence signature today.
# ===========================================================================

def test_wall_schema_prediction_id_is_structurally_uncitable():
    # WALL (a) SCHEMA (§4.3): the belief-id pattern and the prediction-id pattern
    # are DISJOINT by construction — a `pred-` id can never validate as an
    # evidence_bindings.belief_id. Bites a schema that reuses one id space.
    model = _import_model()
    sample = L.belief.digest(["edge", "pred", "sample"])            # a 64-hex digest
    pred_id = "pred-" + sample
    assert re.fullmatch(model.PREDICTION_ID_RE, pred_id)           # prediction validates
    assert not re.fullmatch(model.BELIEF_ID_RE, pred_id)           # but NOT as a belief id
    assert re.fullmatch(model.BELIEF_ID_RE, sample)               # a real belief id does


def test_schemas_bake_in_the_disjoint_id_namespaces():
    # NIT / wall (a) STRENGTHENED (§4.2:81 / §4.3): the belief-vs-prediction id
    # disjointness is pinned AT THE SCHEMAS, not only the model regexes above.
    # edge.v1.json types evidence-binding ids to the belief-id pattern
    # (^[0-9a-f]{64}$); prediction.v1.json types its id to the pred- pattern
    # (^pred-[0-9a-f]{64}$). Schemas absent today => FileNotFoundError = the
    # tests-first absence signature at the schema layer.
    edge_schema = json.loads(
        (_OBJECTIVES_SCHEMA_DIR / "edge.v1.json").read_text(encoding="utf-8"))
    pred_schema = json.loads(
        (_OBJECTIVES_SCHEMA_DIR / "prediction.v1.json").read_text(encoding="utf-8"))
    edge_patterns = _schema_pattern_strings(edge_schema)
    pred_patterns = _schema_pattern_strings(pred_schema)
    assert _BELIEF_ID_RE in edge_patterns, \
        "§4.2: edge.v1.json must type evidence-binding ids to the belief-id pattern"
    assert _PREDICTION_ID_RE in pred_patterns, \
        "§4.3: prediction.v1.json must type its id to the pred- pattern"
    # disjoint by construction: the pred- pattern never types a belief-id slot.
    assert _PREDICTION_ID_RE not in edge_patterns, \
        "§4.2/§4.3: a pred- id must be structurally unciteable as evidence"


def test_wall_store_resolution_prediction_ref_is_a_structural_build_failure(tmp_path):
    # WALL (b) STORE-RESOLUTION (§4.3/§5.1(3)): a `pred-` ref resolves in NO
    # verified cortex store's as_of closure, so an edge binding it is a structural
    # build failure — never a silent skip. Bites a builder admitting a prediction
    # into evidence_bindings. (Distinct from wall (a): this rejects the RESOLUTION,
    # not the id SHAPE.)
    states = _import_states()
    pred_id = "pred-" + L.belief.digest(["laundered", "prediction"])
    edge = L.EdgeSpec(
        authored=True, expected_effect="increase", assumptions=(),
        admissible_subjects=frozenset({"observation/seed"}),
        join_spec=(),
        evidence_bindings=(L.BindingRef("observation/seed", pred_id),))
    with pytest.raises(states.BuildFailure):
        states.derive_edge_state(edge, (), L.CUTOFF)  # no view resolves the pred- ref


def test_wall_producer_minted_prediction_never_enters_the_cortex_store(tmp_path):
    # WALL (c) PRODUCER/STREAM (§4.3 G-F4): a minted prediction lands ONLY in its
    # own predictions store with a `pred-` id, NEVER in the cortex belief store;
    # `prediction` is not a belief KIND, so no adapter stream can carry it. Bites
    # an adapter stream accepting a prediction-kind row / a laundered forecast.
    counterfactual = _import_counterfactual()
    cortex, objectives, _roots = _seed_cache(tmp_path / "cache")
    cortex_before = (cortex / "beliefs.jsonl").read_bytes()

    pred_id = counterfactual.mint_prediction(
        objectives, _SYNTH_EDGE_ID, {"assume": "no-confounding"},
        L.CUTOFF, L.observed_effect_claim("increase"))

    assert re.fullmatch(_PREDICTION_ID_RE, pred_id)               # a pred- id, not a belief id
    pred_store = objectives / "predictions" / "predictions.jsonl"
    assert pred_store.exists()                                    # its OWN store (§4.3)
    assert pred_id in pred_store.read_text(encoding="utf-8")
    assert (cortex / "beliefs.jsonl").read_bytes() == cortex_before  # cortex UNTOUCHED
    assert "prediction" not in L.belief.KINDS                     # never a belief kind


def test_prediction_volume_never_changes_the_canonical_graph(tmp_path):
    # §4.3/N1: predictions are ORIGINAL records EXCLUDED from N1 by name — no
    # volume of predictions changes the canonical graph (or any derived state).
    # Bites the self-confirming loop (prediction → scored → auto-evidence).
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")

    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    before = _canonical_bytes(objectives)

    for i in range(100):                                          # a VOLUME of forecasts
        counterfactual.mint_prediction(
            objectives, _SYNTH_EDGE_ID, {"n": i}, L.CUTOFF,
            L.observed_effect_claim("increase"))
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)       # rebuild

    assert _canonical_bytes(objectives) == before                # byte-identical


def test_scoring_a_prediction_lands_only_in_the_predictions_store(tmp_path):
    # §4.3 / §11 row 3 ("prediction scoring lands in the prediction store only"):
    # scoring a minted prediction appends an ACCURACY record to the predictions
    # store (its chain grows) and touches NOTHING else — the cortex store bytes and
    # the canonical graph bytes are unchanged. Bites a scorer that writes accuracy
    # back into the cortex/evidence plane.
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    canonical_before = _canonical_bytes(objectives)
    cortex_before = (cortex / "beliefs.jsonl").read_bytes()

    pred_id = counterfactual.mint_prediction(
        objectives, _SYNTH_EDGE_ID, {"assume": "no-confounding"},
        L.CUTOFF, L.observed_effect_claim("increase"))
    pred_store = objectives / "predictions" / "predictions.jsonl"
    pred_manifest = objectives / "predictions" / "predictions-manifest.json"
    lines_before = pred_store.read_text(encoding="utf-8").count("\n")
    chain_before = pred_manifest.read_bytes() if pred_manifest.exists() else b""

    counterfactual.score_prediction(objectives, pred_id,
                                    L.observed_effect_claim("increase"))

    # the accuracy record landed in the predictions store (the chain grew).
    assert pred_store.read_text(encoding="utf-8").count("\n") > lines_before
    assert pred_id in pred_store.read_text(encoding="utf-8")
    assert pred_manifest.exists() and pred_manifest.read_bytes() != chain_before
    # nothing else moved: cortex store + canonical graph byte-identical (§4.3/N1).
    assert (cortex / "beliefs.jsonl").read_bytes() == cortex_before
    assert _canonical_bytes(objectives) == canonical_before


def test_scored_prediction_never_changes_edge_state_on_rebuild(tmp_path):
    # §4.3 / §11 row 3 self-confirming-loop mutant (prediction → scored → auto-
    # evidence → promotion): a scored-ACCURATE prediction must NEVER feed back as
    # evidence. Epistemic state is compiled INTO the canonical graph (§5.4), so a
    # rebuild after scoring that leaves the canonical bytes byte-identical proves
    # no edge state changed. Bites the scored→auto-evidence leg directly (the
    # prediction-volume cell above only MINTS; this one SCORES then rebuilds).
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    before = _canonical_bytes(objectives)

    pred_id = counterfactual.mint_prediction(
        objectives, _SYNTH_EDGE_ID, {"assume": "x"}, L.CUTOFF,
        L.observed_effect_claim("increase"))
    counterfactual.score_prediction(objectives, pred_id,
                                    L.observed_effect_claim("increase"))   # ACCURATE
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)                # rebuild after scoring

    assert _canonical_bytes(objectives) == before   # states identical — no auto-evidence


def test_scored_accuracy_record_is_not_belief_shaped(tmp_path):
    # §4.3 wall (a)+(c) tie-in: the accuracy record keeps the pred- namespace — it
    # matches the prediction-id pattern and NOT the belief-id pattern, so it is
    # structurally unciteable as evidence; scoring never writes the cortex store;
    # and `prediction`/`accuracy` are not belief KINDS (no adapter stream carries
    # them). Bites laundering the accuracy record back as a belief.
    counterfactual = _import_counterfactual()
    cortex, objectives, _roots = _seed_cache(tmp_path / "cache")
    cortex_before = (cortex / "beliefs.jsonl").read_bytes()

    pred_id = counterfactual.mint_prediction(
        objectives, _SYNTH_EDGE_ID, {"assume": "x"}, L.CUTOFF,
        L.observed_effect_claim("increase"))
    record = counterfactual.score_prediction(objectives, pred_id,
                                             L.observed_effect_claim("increase"))

    acc_id = record["accuracy_id"]
    assert re.fullmatch(_PREDICTION_ID_RE, acc_id)        # pred- namespace
    assert not re.fullmatch(_BELIEF_ID_RE, acc_id)        # NOT a belief id (wall a)
    assert record["prediction_id"] == pred_id             # bound to its forecast
    assert (cortex / "beliefs.jsonl").read_bytes() == cortex_before   # cortex untouched
    assert "prediction" not in L.belief.KINDS and "accuracy" not in L.belief.KINDS  # wall c


def test_counterfactual_branch_isolates_output_and_leaves_canonical_byte_identical(tmp_path):
    # §5.3 (attack A-M5): a counterfactual branch writes ONLY under
    # counterfactuals/<digest>/ with its own `counterfactual: true` manifest; the
    # canonical root is NEVER written by a branch build. Bites the clobber mutant.
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")

    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)
    before = _canonical_bytes(objectives)

    branch = counterfactual.build_branch(
        roots, objectives, L.SCOPE, "2026-07-19T00:00:00Z",       # alternative cutoff
        {"assume": "no-confounding"})

    # canonical untouched (byte-identical) — the clobber mutant fails HERE.
    assert _canonical_bytes(objectives) == before
    # branch output is namespaced under counterfactuals/<digest>/ ONLY.
    branch = Path(branch)
    assert branch.parent == objectives / "counterfactuals"
    b_manifest = json.loads((branch / "graph-manifest.json").read_text(encoding="utf-8"))
    assert b_manifest.get("counterfactual") is True               # §5.3 marker
    assert (branch / "graph.jsonl").exists()


def test_counterfactual_branch_replay_is_byte_deterministic(tmp_path):
    # §5.3: replay is byte-deterministic per branch under the same epoch inputs —
    # same (cutoff, assumption_overrides) => same <digest> dir + byte-identical
    # graph.jsonl. (N1 excludes counterfactuals/ from the canonical hash; each
    # branch is separately replay-deterministic.)
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)

    args = (roots, objectives, L.SCOPE, "2026-07-19T00:00:00Z", {"assume": "x"})
    first = Path(counterfactual.build_branch(*args))
    first_bytes = (first / "graph.jsonl").read_bytes()
    second = Path(counterfactual.build_branch(*args))             # same inputs => replay
    assert second == first                                        # same <digest> dir
    assert (second / "graph.jsonl").read_bytes() == first_bytes   # byte-identical


def test_serve_refuses_a_counterfactual_manifest(tmp_path):
    # §5.3/§5.4: the serve surface REFUSES to bind any manifest marked
    # `counterfactual: true` — a counterfactual graph can never masquerade as the
    # canonical one. Bites the serve-binds-a-counterfactual-manifest mutant.
    graph = _import_graph()
    counterfactual = _import_counterfactual()
    query = _import_query()
    cortex, objectives, roots = _seed_cache(tmp_path / "cache")
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)

    branch = Path(counterfactual.build_branch(
        roots, objectives, L.SCOPE, "2026-07-19T00:00:00Z", {"assume": "x"}))
    with pytest.raises(query.ServeRefused):
        query.serve_graph(branch)                                 # counterfactual REFUSE


# ===========================================================================
# SEED SELF-CHECKS — no framework.objectives import; PASS TODAY.
# ===========================================================================

class TestSim3SeedsAreReal:
    def test_belief_and_prediction_id_patterns_are_disjoint(self):
        # wall (a) premise: a real belief id is 64-hex; a `pred-` id is NOT — the
        # patterns are disjoint by construction (§4.3), so a prediction ref can
        # never validate as an evidence binding id.
        real = L.belief.digest(["a", "b", "c"])
        assert re.fullmatch(_BELIEF_ID_RE, real)                  # real belief id: 64-hex
        assert not re.fullmatch(_BELIEF_ID_RE, "pred-" + real)    # pred- id: NOT a belief id
        assert re.fullmatch(_PREDICTION_ID_RE, "pred-" + real)    # pred- id: a prediction id

    def test_prediction_is_not_a_belief_kind(self):
        # wall (c) premise: `prediction` is not in the cortex belief KINDS, so no
        # adapter stream can carry a prediction-kind row (G-F4 laundering wall).
        assert "prediction" not in L.belief.KINDS

    def test_seed_cache_store_roundtrips_through_the_one_read_path(self, tmp_path):
        # the build-input seed is real: the store persists + reloads via the ONE
        # cortex read path (load_beliefs_verified, §5.1), and the objectives cache
        # + roots file exist — so build_graph has a valid, non-empty input.
        cortex, objectives, roots = _seed_cache(tmp_path / "cache")
        reloaded = L.query.load_beliefs_verified(cortex)
        assert len(reloaded) == 1
        assert (cortex / "beliefs.jsonl").exists()
        assert objectives.is_dir() and roots.exists()
        assert "ship-fast" in roots.read_text(encoding="utf-8")

    def test_synthetic_edge_id_is_a_wellformed_belief_shaped_digest(self):
        # the prediction cells reference a synthetic edge id (predictions are
        # forecasts; the store does not require the edge to exist in the graph).
        assert re.fullmatch(_BELIEF_ID_RE, _SYNTH_EDGE_ID)

    def test_scoring_outcome_view_seed_is_a_real_observed_effect_claim(self):
        # the scoring cells score a forecast against a realized-outcome claim; that
        # claim is the SAME observed_effect shape the cortex store seeds, so the
        # scoring cells fail today ONLY for the absent implementation.
        assert L.observed_effect_claim("increase") == {"observed_effect": "increase"}

    def test_objectives_schema_dir_is_absent_today(self):
        # documents the tests-first signature for the schema-disjointness cell: the
        # objectives domain schemas do not exist yet, so that cell fails on the
        # absent schema files (FileNotFoundError).
        assert not _OBJECTIVES_SCHEMA_DIR.exists()
