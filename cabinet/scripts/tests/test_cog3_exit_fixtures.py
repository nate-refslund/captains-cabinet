"""test_cog3_exit_fixtures.py — W4C: the exit-gate fixture battery (COG-3 contract
rev-1 §11 tail + §2.4 + §9 r14).

NEW additive suite (the landed corpus is immutable; this suite only ADDS). It rides
the last two foundry-required sims declared for the exit gate (§2.4: "the two
remaining foundry sims — missing product adapter and generic non-software Cabinet —
ride the exit-gate fixture battery"), plus the software fixture, plus the §9 r14
objectives-scoped product-token grep.

THREE heterogeneous fixture Cabinets, EACH exercised END-TO-END through the REAL
CLI (subprocess `cog3-rebuild.py` with tmp roots + adapter source files + a
file-seeded sibling cortex store) — never a hand-built graph, never a direct
build_graph shortcut: the CLI merge+adapter path IS each fixture's point. Every
assertion is over the PUBLIC surface (serve_graph / serve_objective / the served
manifest), never internals.

  1. SOFTWARE-PRODUCT cabinet — product outcomes, speed/quality dimensions, tasks
     with consequences, instruments with `indicates` edges. A verdict_human confirm
     matching a task join_spec (assumptions declared) promotes ITS edge to
     `intervention_supported`; a non-verdict_human (machine/judge) confirm caps at
     `observationally_supported` (§5.2 P5 — the ceiling for all non-human-verdict
     evidence, incl. observation volume); the manifest divergence_report carries a
     seeded instrument-vs-outcome opposition; and N1 (delete cache → rebuild →
     identical chained graph hash, roots_path held fixed) holds across two distinct
     PYTHONHASHSEED subprocess builds.

  2. NON-SOFTWARE OPERATIONS cabinet — a community-garden + delivery operation with
     ZERO software vocabulary. A human-confirmed intervention promotes; conflicting
     objectives are stored symmetric + canonical (never LWW), both retained; a root
     edit orphans the dependent objectives at rebuild (answerable-with-flag) — the
     same framework layer proven DOMAIN-AGNOSTIC.

  3. MISSING-PRODUCT-ADAPTER cabinet — roots + workgraph + missions sources but NO
     products source: the build SUCCEEDS with `product_spec` DECLARED-absent in the
     objectives-input AND (the w4a-fix) copied into the served manifest; the graph
     serves; nothing is silently invented (no instrument nodes, no indicates edges).

PLUS the §9 r14 token test: framework/objectives/** (incl. adapters) carries ZERO
instance/product literals (the token list is assembled from parts so THIS file
never itself trips a product-token sweep); fixture vocabulary lives ONLY here.

S0: python3.12, file-seeded (no DSN — §7.2), reuses lib_cog3_fixtures idioms
(consequence seeding, proto folding, cortex persistence). Deterministic — canonical
cutoffs are constants, no clock. CI-fast — bounded sizes.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4C (the exit-gate fixture battery).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L  # noqa: E402

from framework.objectives import model, query, states  # noqa: E402

_CLI = Path(_ROOT) / "cabinet" / "scripts" / "cog3-rebuild.py"

# Canonical build constants (§5.1(2) — one cutoff per build; no clock read).
CUTOFF = L.CUTOFF
TS = L.EVIDENCE_TS
_ASSUMPTIONS = ["declared-confounder-and-selection"]   # non-empty => P3/P5 eligible (R-A)


# ===========================================================================
# End-to-end CLI + cortex-seeding harness (the REAL production merge lane, §7.6)
# ===========================================================================

@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    """Isolated consequence-ledger dir via CABINET_EVENT_LOG_DIR (the D1 idiom the
    corpus reuses). Only the TEST process folds the ledger; the CLI subprocess
    reads the PERSISTED cortex store, never the ledger."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


def _write_json(path, obj):
    """Write a source file as JSON. JSON is valid YAML, so the CLI's yaml.safe_load
    consumes it — and a JSON-quoted timestamp stays a STRING (an unquoted YAML
    timestamp would autotype to a datetime and break the consequence-identity
    digest join). Every adapter/roots source here is written this way."""
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return Path(path)


def _seed_cortex(cortex_dir, events_dir, consequence_rows, obs_protos):
    """Seed consequence-ledger rows + observation protos, fold through the REAL
    engine, and persist beliefs.jsonl + fold-manifest.json under cortex_dir — the
    ONE sibling cortex read path the build binds (§5.1). Seed inputs, run the real
    substrate — never a hand-built view."""
    if consequence_rows:
        L.seed_consequence_ledger(events_dir, consequence_rows)
    protos = (L.consequence_protos() if consequence_rows else []) + list(obs_protos)
    beliefs = L.fold_beliefs(protos)
    cortex_dir.mkdir(parents=True, exist_ok=True)
    L.persist_cortex_store(cortex_dir, beliefs)
    return beliefs


def _run_cli(roots, cache, *, workgraph=None, missions=None, products=None,
             cutoff=CUTOFF, want_json=False, hashseed=None):
    """Run the real cog3-rebuild.py CLI as a subprocess (the honest end-to-end
    surface). `cache` is the objectives cache; the build reads the SIBLING cortex
    at cache/../cortex. A distinct PYTHONHASHSEED proves the chained hash is
    seed-independent (§5.4 / C-F3)."""
    argv = [sys.executable, str(_CLI), "--roots", str(roots), "--cache", str(cache),
            "--cutoff", cutoff]
    if workgraph is not None:
        argv += ["--workgraph", str(workgraph)]
    if missions is not None:
        argv += ["--missions", str(missions)]
    if products is not None:
        argv += ["--products", str(products)]
    if want_json:
        argv += ["--json"]
    env = dict(os.environ)
    if hashseed is not None:
        env["PYTHONHASHSEED"] = str(hashseed)
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def _rows(objectives_dir):
    return [json.loads(x) for x
            in (Path(objectives_dir) / "graph.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def _manifest(objectives_dir):
    return json.loads((Path(objectives_dir) / "graph-manifest.json").read_text(encoding="utf-8"))


def _causal_edges(served):
    """The served causal-edge records (the ones carrying a derived state)."""
    return [r for r in served["records"] if r.get("target_kind") and "state" in r]


# ===========================================================================
# FIXTURE 1 — SOFTWARE-PRODUCT cabinet (the software exit fixture)
# ===========================================================================

def test_fixture_software_product_cabinet(tmp_path, events_dir):
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"

    # Cortex evidence: (a) a verdict_human confirm on the refactor task's join;
    # (b) a verdict_judge (machine) confirm on the caching task's join — the
    # non-human-verdict evidence that caps at P5; (c) a proxy instrument head that
    # IMPROVES while the outcome head REGRESSES on the shared dimension (§5.6).
    rows = [
        L.consequence_row("refactor", "checkout", verdict="confirmed",
                          source="verdict_human", actor_kind="officer",
                          actor_id="cto", ts=TS),
        L.consequence_row("cache", "render", verdict="confirmed",
                          source="verdict_judge", actor_kind="officer",
                          actor_id="cto", ts=TS),
    ]
    obs = [
        L.observation_proto("instrument/cache-hit-rate", "latency",
                            claim=L.observed_effect_claim("increase"),
                            seq=0, event_suffix="instr"),
        L.observation_proto("outcome/page-render-time", "latency",
                            claim=L.observed_effect_claim("decrease"),
                            seq=0, event_suffix="outc"),
    ]
    _seed_cortex(cortex, events_dir, rows, obs)

    roots = _write_json(tmp_path / "roots.yml", {
        "directions": {"velocity": {"statement": "ship value faster"},
                       "reliability": {"statement": "fewer defects in production"}},
        "objectives": [{"slug": "faster-checkout", "root_ref": "velocity"}],
    })
    workgraph = _write_json(tmp_path / "workgraph.yml", {"tasks": [
        {"task_id": 1, "actor": {"kind": "officer", "id": "cto"},
         "action": "refactor", "subject": "checkout", "ts": TS,
         "target": "outcome/checkout-latency", "dimension": "latency",
         "expected_effect": "decrease", "assumptions": _ASSUMPTIONS},
        {"task_id": 2, "actor": {"kind": "officer", "id": "cto"},
         "action": "cache", "subject": "render", "ts": TS,
         "target": "outcome/page-render-time", "dimension": "latency",
         "expected_effect": "decrease", "assumptions": _ASSUMPTIONS},
    ]})
    missions = _write_json(tmp_path / "missions.yml", {"missions": [
        {"slug": "checkout-latency", "dimension": "latency"},
    ]})
    products = _write_json(tmp_path / "products.yml", {"products": [
        {"slug": "page-render-time", "dimension": "latency",
         "instruments": ["cache-hit-rate"]},
    ]})

    proc = _run_cli(roots, objectives, workgraph=workgraph, missions=missions,
                    products=products, want_json=True, hashseed=0)
    assert proc.returncode == 0, proc.stderr
    hash1 = json.loads(proc.stdout)["graph_hash"]

    # Serve the compiled graph (the public surface) and read the derived states.
    served = query.serve_graph(str(objectives))
    state_by_target = {r["target_node_id"]: r["state"] for r in _causal_edges(served)}
    id_checkout = model.node_id("outcome", "outcome/checkout-latency")
    id_render = model.node_id("outcome", "outcome/page-render-time")
    # the verdict_human + assumptions edge PROMOTES (§5.2 P3).
    assert state_by_target[id_checkout] == states.STATE_INTERVENTION_SUPPORTED
    # the machine/judge (non-human) verdict edge CAPS at the P5 ceiling — no
    # non-verdict_human evidence ever mints intervention_supported (§5.2 P5).
    assert state_by_target[id_render] == states.STATE_OBSERVATIONALLY_SUPPORTED

    # the §5.6 divergence report carries the seeded instrument-vs-outcome opposition.
    manifest = _manifest(objectives)
    opposing = [e for e in manifest["divergence_report"]
                if e["instrument_direction"] != e["outcome_direction"]]
    assert opposing, manifest["divergence_report"]
    assert opposing[0]["instrument_node"] == model.node_id("instrument",
                                                           "instrument/cache-hit-rate")
    assert opposing[0]["outcome_node"] == id_render

    # N1 (rebuild determinism): delete the cache → rebuild from zero under a DISTINCT
    # PYTHONHASHSEED with the roots_path held fixed → identical chained graph hash.
    shutil.rmtree(objectives)
    proc2 = _run_cli(roots, objectives, workgraph=workgraph, missions=missions,
                     products=products, want_json=True, hashseed=12345)
    assert proc2.returncode == 0, proc2.stderr
    hash2 = json.loads(proc2.stdout)["graph_hash"]
    assert hash1 == hash2, "N1: delete→rebuild-from-zero must reproduce the graph hash"


# ===========================================================================
# FIXTURE 2 — NON-SOFTWARE OPERATIONS cabinet (the generic-cabinet foundry sim)
# ===========================================================================

def test_fixture_nonsoftware_operations_cabinet(tmp_path, events_dir):
    # A community-garden + delivery operation. ZERO software vocabulary anywhere —
    # proving the framework layer is domain-agnostic (§1 N1 / §2.4).
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"

    rows = [L.consequence_row("replan", "routes", verdict="confirmed",
                              source="verdict_human", actor_kind="steward",
                              actor_id="market", ts=TS)]
    _seed_cortex(cortex, events_dir, rows, [])

    roots_obj = {
        "directions": {"harvest": {"statement": "grow more food each season"},
                       "logistics": {"statement": "deliver every basket on time"}},
        # two objectives under harvest that pull against each other; only ONE side
        # declares the conflict — the build must store it SYMMETRIC, never LWW.
        "objectives": [
            {"slug": "maximize-yield", "root_ref": "harvest",
             "conflicts_with": ["reduce-waste"]},
            {"slug": "reduce-waste", "root_ref": "harvest"},
        ],
    }
    roots = _write_json(tmp_path / "roots.yml", roots_obj)
    workgraph = _write_json(tmp_path / "workgraph.yml", {"tasks": [
        {"task_id": 1, "actor": {"kind": "steward", "id": "market"},
         "action": "replan", "subject": "routes", "ts": TS,
         "target": "outcome/delivery-punctuality", "dimension": "punctuality",
         "expected_effect": "increase", "assumptions": _ASSUMPTIONS},
    ]})
    missions = _write_json(tmp_path / "missions.yml", {"missions": [
        {"slug": "delivery-punctuality", "dimension": "punctuality"},
    ]})

    proc = _run_cli(roots, objectives, workgraph=workgraph, missions=missions,
                    hashseed=0)
    assert proc.returncode == 0, proc.stderr

    served = query.serve_graph(str(objectives))
    edges = _causal_edges(served)
    # a human-confirmed intervention PROMOTES, exactly as in the software cabinet —
    # the derivation is identical across domains.
    assert len(edges) == 1 and edges[0]["state"] == states.STATE_INTERVENTION_SUPPORTED

    # the rooted objectives are answerable and NOT orphaned (harvest resolves).
    assert "orphaned" not in query.serve_objective(str(objectives),
                                                   "objective/maximize-yield").flags

    # conflicts stored SYMMETRIC + CANONICAL (source = the smaller subject_key),
    # both objective nodes retained, exactly ONE edge (deduped, never LWW).
    id_yield = model.node_id("objective", "objective/maximize-yield")
    id_waste = model.node_id("objective", "objective/reduce-waste")
    rows_all = _rows(objectives)
    conflict_edges = [r for r in rows_all if r.get("relation") == "conflicts_with"]
    assert len(conflict_edges) == 1, conflict_edges
    ce = conflict_edges[0]
    sk_a, sk_b = sorted(["objective/maximize-yield", "objective/reduce-waste"])
    assert ce["source_node_id"] == model.node_id("objective", sk_a)   # canonical order
    assert ce["target_node_id"] == model.node_id("objective", sk_b)
    assert {ce["source_node_id"], ce["target_node_id"]} == {id_yield, id_waste}
    node_ids = {r["node_id"] for r in rows_all if r.get("kind") == "objective"}
    assert {id_yield, id_waste} <= node_ids                           # BOTH retained

    # Root edit: rebuild with the `harvest` direction REMOVED → the dependent
    # objectives ORPHAN at rebuild (never silently retained under the old root,
    # never dropped); the orphaned subtree stays ANSWERABLE with the flag (§9 r5).
    roots2 = _write_json(tmp_path / "roots.yml", {
        "directions": {"logistics": {"statement": "deliver every basket on time"}},
        "objectives": roots_obj["objectives"],
    })
    objectives2 = cache_root / "objectives2"
    proc2 = _run_cli(roots2, objectives2, workgraph=workgraph, missions=missions,
                     hashseed=0)
    assert proc2.returncode == 0, proc2.stderr
    ans = query.serve_objective(str(objectives2), "objective/maximize-yield")
    assert "orphaned" in ans.flags, "a root edit must orphan the dependent objective"


# ===========================================================================
# FIXTURE 3 — MISSING-PRODUCT-ADAPTER cabinet (the second foundry sim)
# ===========================================================================

def test_fixture_missing_product_adapter_cabinet(tmp_path, events_dir):
    # roots + workgraph + missions, but NO products source. The build SUCCEEDS with
    # the absence DECLARED (never silent); the graph serves; nothing is invented.
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"

    rows = [L.consequence_row("switch", "supplier", verdict="confirmed",
                              source="verdict_human", actor_kind="baker",
                              actor_id="lead", ts=TS)]
    _seed_cortex(cortex, events_dir, rows, [])

    roots = _write_json(tmp_path / "roots.yml", {
        "directions": {"bake": {"statement": "bake fresh loaves every morning"}},
        "objectives": [{"slug": "fresh-loaves", "root_ref": "bake"}],
    })
    workgraph = _write_json(tmp_path / "workgraph.yml", {"tasks": [
        {"task_id": 1, "actor": {"kind": "baker", "id": "lead"},
         "action": "switch", "subject": "supplier", "ts": TS,
         "target": "outcome/flour-quality", "dimension": "quality",
         "expected_effect": "increase", "assumptions": _ASSUMPTIONS},
    ]})
    missions = _write_json(tmp_path / "missions.yml", {"missions": [
        {"slug": "flour-quality", "dimension": "quality"},
    ]})

    # NO --products flag: product_spec is the missing adapter.
    proc = _run_cli(roots, objectives, workgraph=workgraph, missions=missions,
                    products=None, hashseed=0)
    assert proc.returncode == 0, proc.stderr

    # declared_absent carries product_spec in BOTH the objectives-input AND (the
    # w4a-fix) the served manifest — the absence is durable, never silent.
    objectives_input = json.loads(
        (objectives / "objectives-input.json").read_text(encoding="utf-8"))
    assert "product_spec" in objectives_input["declared_absent"]
    manifest = _manifest(objectives)
    assert "product_spec" in manifest["declared_absent"]

    # the graph SERVES; nothing silently invented (no product => no instrument
    # nodes, no indicates edges), yet the present adapters build intact.
    served = query.serve_graph(str(objectives))
    assert not any(r.get("kind") == "instrument" for r in served["records"])
    assert not any(r.get("relation") == "indicates" for r in served["records"])
    # the human-confirmed intervention still promotes — the missing product adapter
    # never perturbs the others (§2.2 blast isolation).
    edges = _causal_edges(served)
    assert len(edges) == 1 and edges[0]["state"] == states.STATE_INTERVENTION_SUPPORTED
    # the rooted objective serves answerable.
    assert "orphaned" not in query.serve_objective(str(objectives),
                                                   "objective/fresh-loaves").flags


# ===========================================================================
# §9 r14 — the objectives-scoped product-token grep (CLOSED LOCALLY)
# ===========================================================================

def test_objectives_framework_carries_no_instance_product_tokens():
    # §9 r14: the framework layer never hardcodes an instance/product literal. Grep
    # framework/objectives/** (incl. the adapters package) for the known product
    # tokens == 0. The token list is ASSEMBLED FROM PARTS so this test file never
    # itself trips a product-token sweep; fixture vocabulary lives ONLY in the
    # fixtures above. The GLOBAL product-token gap stays known debt OUTSIDE this
    # phase (§9 r14 disposition) — this is the local closure.
    tokens = ["pol" + "ads", "step" + "hie", "job" + "danmark", "ref" + "slund"]
    # Reviewer nit closed at wave-4 integration (2026-07-23): the sweep also
    # covers the phase's schema surface (framework/schemas/domains/objectives).
    sweep_dirs = [
        Path(_ROOT) / "framework" / "objectives",
        Path(_ROOT) / "framework" / "schemas" / "domains" / "objectives",
    ]
    hits = []
    for objdir in sweep_dirs:
        for path in sorted(objdir.rglob("*")):
            if path.suffix not in {".py", ".json"} or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for tok in tokens:
                if tok in text:
                    hits.append((str(path.relative_to(_ROOT)), tok))
    assert hits == [], f"§9 r14: product tokens leaked into the objectives surface: {hits}"


# ===========================================================================
# SERVE-SURFACE UNIFORMITY (F1) — the WHOLE query surface binds + refuses
# ===========================================================================
#
# F1 (COG-3 frozen-review ship-blocker): serve_objective and recommend read
# graph.jsonl DIRECTLY, bypassing the three C-F15 REFUSE limbs that serve_graph
# enforces — the fresh-context panel PROVED both ANSWERED on a counterfactual
# manifest and on a rows-tampered cache. The fix routes ALL THREE public serve
# functions through the ONE bound loader (query._load_bound); the module docstring
# and §5.4/§5.3 pin serve-time binding on the WHOLE objectives query surface.
#
# This suite is the regression wall: for EACH of the three refusal limbs (tampered
# rows / counterfactual manifest / mixed-epoch store) ALL THREE public serve
# functions (serve_graph, serve_objective, recommend) must REFUSE. The fixture-1
# software cache is BUILT ONCE end-to-end through the REAL CLI and REUSED — each
# case works on an isolated COPY so a per-limb tamper never bleeds across. The
# tamper setups mirror the panel's probes and the corpus idioms (sim2's cortex
# refold for mixed-epoch, sim3's counterfactual manifest, the §5.4 rows-hash
# binding for tampered rows). A pristine-cache positive control proves every serve
# fn ANSWERS when bound — the refusals below are caused by the limb, not a broken
# build (an always-red suite would prove nothing).

# The fixture-1 objective the serve fns answer on a CLEAN cache — so the pre-fix
# bypass ANSWERED here (returned a state / a record) and the fix turns it to a
# refusal; a subject that would answer isolates the binding as the refusal cause.
_F1_SUBJECT = "objective/faster-checkout"

_SERVE_FNS = {
    "serve_graph": lambda objectives: query.serve_graph(str(objectives)),
    "serve_objective": lambda objectives: query.serve_objective(str(objectives), _F1_SUBJECT),
    "recommend": lambda objectives: query.recommend(str(objectives), _F1_SUBJECT),
}


def _build_software_cache(cache_root, events_dir):
    """Build the FIXTURE-1 software-product cache (sibling cortex + objectives)
    end-to-end through the real cog3-rebuild.py CLI — the SAME seed as
    test_fixture_software_product_cabinet. Returns cache_root (holding cortex/ +
    objectives/)."""
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"
    base = cache_root.parent
    rows = [
        L.consequence_row("refactor", "checkout", verdict="confirmed",
                          source="verdict_human", actor_kind="officer",
                          actor_id="cto", ts=TS),
        L.consequence_row("cache", "render", verdict="confirmed",
                          source="verdict_judge", actor_kind="officer",
                          actor_id="cto", ts=TS),
    ]
    obs = [
        L.observation_proto("instrument/cache-hit-rate", "latency",
                            claim=L.observed_effect_claim("increase"),
                            seq=0, event_suffix="instr"),
        L.observation_proto("outcome/page-render-time", "latency",
                            claim=L.observed_effect_claim("decrease"),
                            seq=0, event_suffix="outc"),
    ]
    _seed_cortex(cortex, events_dir, rows, obs)
    roots = _write_json(base / "roots.yml", {
        "directions": {"velocity": {"statement": "ship value faster"},
                       "reliability": {"statement": "fewer defects in production"}},
        "objectives": [{"slug": "faster-checkout", "root_ref": "velocity"}],
    })
    workgraph = _write_json(base / "workgraph.yml", {"tasks": [
        {"task_id": 1, "actor": {"kind": "officer", "id": "cto"},
         "action": "refactor", "subject": "checkout", "ts": TS,
         "target": "outcome/checkout-latency", "dimension": "latency",
         "expected_effect": "decrease", "assumptions": _ASSUMPTIONS},
        {"task_id": 2, "actor": {"kind": "officer", "id": "cto"},
         "action": "cache", "subject": "render", "ts": TS,
         "target": "outcome/page-render-time", "dimension": "latency",
         "expected_effect": "decrease", "assumptions": _ASSUMPTIONS},
    ]})
    missions = _write_json(base / "missions.yml", {"missions": [
        {"slug": "checkout-latency", "dimension": "latency"},
    ]})
    products = _write_json(base / "products.yml", {"products": [
        {"slug": "page-render-time", "dimension": "latency",
         "instruments": ["cache-hit-rate"]},
    ]})
    proc = _run_cli(roots, objectives, workgraph=workgraph, missions=missions,
                    products=products, hashseed=0)
    assert proc.returncode == 0, proc.stderr
    return cache_root


@pytest.fixture(scope="module")
def software_cache_pristine(tmp_path_factory):
    """Build the fixture-1 software cache ONCE for the whole uniformity class
    (F1 — "reuse the fixture-1 built cache"). tmp_path_factory is session-scoped so
    it composes with this module-scoped fixture; the cortex seed reads
    CABINET_EVENT_LOG_DIR only in THIS process (the CLI subprocess reads the
    PERSISTED store), so we set it (and clear CABINET_SIM_MODE, matching events_dir)
    around the build and restore the prior environment after."""
    root = tmp_path_factory.mktemp("f1_uniformity")
    cache_root = root / "cache"
    events = root / "events"
    events.mkdir()
    saved = {k: os.environ.get(k) for k in ("CABINET_EVENT_LOG_DIR", "CABINET_SIM_MODE")}
    os.environ["CABINET_EVENT_LOG_DIR"] = str(events)
    os.environ.pop("CABINET_SIM_MODE", None)
    try:
        _build_software_cache(cache_root, events)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return cache_root


def _apply_uniformity_tamper(cache_root, limb):
    """Reproduce the panel's F1 probe for ONE C-F15 limb on a COPY of the fixture-1
    cache, and return the objectives dir the serve fns bind:

      * "tampered_rows"  — append a row so graph.jsonl no longer reproduces the
                           manifest's recorded graph_rows_hash (§5.4 rows-hash
                           binding; the manufactured-certainty class).
      * "counterfactual" — flip the served manifest's `counterfactual` flag true
                           (the distinguishing mark of a counterfactual BRANCH
                           manifest, §5.3 — serve refuses to bind it as canonical).
      * "mixed_epoch"    — re-persist the SIBLING cortex with a DIFFERENT belief
                           set so the live store hash != the manifest's recorded
                           cortex_belief_store_hash (the sim2 refold idiom, §5.4)."""
    objectives = cache_root / "objectives"
    if limb == "tampered_rows":
        with open(objectives / "graph.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"tampered": "row"}) + "\n")
    elif limb == "counterfactual":
        man_path = objectives / "graph-manifest.json"
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        manifest["counterfactual"] = True
        man_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif limb == "mixed_epoch":
        drift = L.observation_proto("observation/f1-epoch-drift", L.DIMENSION,
                                    claim=L.observed_effect_claim("increase"),
                                    seq=0, event_suffix="f1-epoch-drift")
        L.persist_cortex_store(cache_root / "cortex", L.fold_beliefs([drift]))
    else:                                              # pragma: no cover — typo guard
        raise ValueError(f"unknown limb {limb!r}")
    return objectives


class TestServeSurfaceUniformity:
    """F1 regression wall: EVERY public serve entry point binds the manifest and
    REFUSES on EVERY C-F15 limb — no per-objective / recommendation bypass."""

    @pytest.mark.parametrize("fn_name", ["serve_graph", "serve_objective", "recommend"])
    def test_serve_fn_answers_on_the_clean_bound_cache(
            self, tmp_path, software_cache_pristine, fn_name):
        # anti-no-op positive control: on the PRISTINE fixture-1 cache every serve
        # fn BINDS and ANSWERS (never raises) — so the refusals below are caused by
        # the limb, never a broken build. This is exactly the state the pre-fix
        # bypass ANSWERED in for serve_objective / recommend.
        work = tmp_path / "cache"
        shutil.copytree(software_cache_pristine, work)
        result = _SERVE_FNS[fn_name](work / "objectives")
        assert result is not None

    @pytest.mark.parametrize("limb", ["tampered_rows", "counterfactual", "mixed_epoch"])
    @pytest.mark.parametrize("fn_name", ["serve_graph", "serve_objective", "recommend"])
    def test_serve_fn_refuses_every_limb(
            self, tmp_path, software_cache_pristine, limb, fn_name):
        # THE F1 assertion: for each of the three C-F15 refusal limbs, EACH of the
        # three public serve fns must raise ServeRefused. Pre-fix, serve_objective
        # and recommend ANSWERED here (read graph.jsonl unbound) — the ship-blocker.
        work = tmp_path / "cache"
        shutil.copytree(software_cache_pristine, work)
        objectives = _apply_uniformity_tamper(work, limb)
        with pytest.raises(query.ServeRefused):
            _SERVE_FNS[fn_name](objectives)
