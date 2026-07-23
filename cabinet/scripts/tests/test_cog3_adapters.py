"""test_cog3_adapters.py — W4A: the blast-isolated source-record adapters
(COG-3 contract rev-1 §2.2 + §4) and the KEYSTONE end-to-end P6-deferral closure.

NEW additive suite (the landed corpus is immutable). It pins:
  * each adapter standalone — roots (direction_root + rooted objectives), workgraph
    (intervention join_spec + causal edge, or REFUSAL when direction is undeclared),
    mission_inputs (outcome/constraint floors), product_spec (instrument nodes +
    indicates edges);
  * blast isolation (§2.2) — a missing source is DECLARED-absent, never silent, and
    never perturbs the others (the missing-product-adapter foundry-sim shape);
  * assembly — one deterministic canonical input; a collision is a structural error;
  * the KEYSTONE (§ appendix addendum, the wave-4 deferral closer): adapters emit ->
    assemble -> build_graph -> serve, and a verdict_human confirm on a join that
    matches the workgraph task's join_spec derives `intervention_supported` THROUGH
    THE REAL PIPELINE (a verdict_judge confirm caps at observationally_supported; a
    human confirm with no assumptions lands at hypothesized per ruling R-A).

S0: python3.12, file-seeded (no DSN — §7.2), reuses lib_cog3_fixtures idioms.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; W4A (the adapters package).
"""
from __future__ import annotations

import json
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

from framework.objectives import graph, query                      # noqa: E402
from framework.objectives.adapters import (                        # noqa: E402
    assemble, AssemblyCollision, mission_inputs, product_spec, roots, workgraph)

_CLI = Path(_ROOT) / "cabinet" / "scripts" / "cog3-rebuild.py"


def _run_cli(roots_path, cache, *, products=None, workgraph_src=None, missions=None,
             cutoff=L.CUTOFF):
    """Run the real cog3-rebuild.py CLI (the production merge lane, §7.6) as a
    subprocess and return the CompletedProcess — the honest end-to-end surface the
    merge-boundary collision law must hold on."""
    argv = [sys.executable, str(_CLI), "--roots", str(roots_path),
            "--cache", str(cache), "--cutoff", cutoff]
    if products is not None:
        argv += ["--products", str(products)]
    if workgraph_src is not None:
        argv += ["--workgraph", str(workgraph_src)]
    if missions is not None:
        argv += ["--missions", str(missions)]
    return subprocess.run(argv, capture_output=True, text=True)


@pytest.fixture
def consequence_ledger(tmp_path, monkeypatch):
    """Isolated consequence-ledger dir via CABINET_EVENT_LOG_DIR (the D1 idiom)."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


# ===========================================================================
# (1) roots adapter — direction_root + rooted-objective emission (§4.1)
# ===========================================================================

def test_roots_adapter_emits_sorted_direction_roots_and_rooted_objectives():
    frag = roots.adapt([
        {"slug": "lane-b", "statement": "do B", "objectives": [{"slug": "obj-2"}]},
        {"slug": "lane-a", "statement": "do A", "objectives": ["obj-1"]},
    ])
    assert frag["directions"] == [{"slug": "lane-a", "statement": "do A"},
                                  {"slug": "lane-b", "statement": "do B"}]
    # every objective carries root_ref = its lane slug (§4.1 REQUIRED presence).
    assert {"slug": "obj-1", "root_ref": "lane-a"} in frag["objectives"]
    assert {"slug": "obj-2", "root_ref": "lane-b"} in frag["objectives"]
    assert all("root_ref" in o for o in frag["objectives"])


def test_roots_adapter_direction_statement_keys_on_statement_not_mission():
    # the direction_root digest reads `statement` (graph.py) — a lane carrying only
    # `mission` yields statement "" so the default rebuild identity is unchanged.
    frag = roots.adapt([{"slug": "polads", "mission": "a big mission"}])
    assert frag["directions"] == [{"slug": "polads", "statement": ""}]
    assert frag["objectives"] == []


# ===========================================================================
# (2) workgraph adapter — intervention join_spec + causal edge / REFUSAL (§4.1/§4.2)
# ===========================================================================

def _keystone_task(**over):
    task = {"task_id": 42, "actor": {"kind": "officer", "id": "cto"},
            "action": "ship", "subject": "feature-x", "ts": L.EVIDENCE_TS,
            "target": "outcome/feature-x", "dimension": L.DIMENSION,
            "expected_effect": "increase"}
    task.update(over)
    return task


def test_workgraph_emits_intervention_join_spec_and_bound_causal_edge():
    frag = workgraph.adapt([_keystone_task(assumptions=["a"])])
    node = frag["nodes"][0]
    assert node["kind"] == "intervention" and node["subject_key"] == "tasks/42"
    # join_spec flattens the actor to 'kind:id' — the consequence identity convention.
    assert node["join_spec"] == [["officer:cto", "ship", "feature-x"]]
    edge = frag["causal_edges"][0]
    assert edge["source"] == "tasks/42" and edge["target"] == "outcome/feature-x"
    assert edge["expected_effect"] == "increase"
    # the evidence subject NAMES the consequence row (recorder-digest identity).
    cons_sk = "consequence/" + L.belief.digest(
        ["officer:cto", "ship", "feature-x", L.EVIDENCE_TS])
    assert edge["evidence_subjects"] == [cons_sk]
    assert set(edge["admissible_subjects"]) == {"tasks/42", cons_sk}


def test_workgraph_refuses_a_causal_edge_when_direction_is_undeclared():
    # §4.2 / the wave brief: no `expected_effect` => the adapter emits the
    # intervention node but REFUSES the causal edge (direction never invented).
    frag = workgraph.adapt([{"task_id": 7, "actor": "cos", "action": "do",
                             "subject": "x", "target": "outcome/x"}])
    assert frag["causal_edges"] == []
    assert frag["nodes"][0]["subject_key"] == "tasks/7"
    assert frag["nodes"][0]["join_spec"] == [["cos:", "do", "x"]]


def test_workgraph_refuses_a_causal_edge_when_dimension_is_undeclared():
    # (nit a) a task with expected_effect + target but NO `dimension` would emit a
    # schema-invalid "dimension": None causal edge (the fold carries it into the
    # graph row). Treated like a missing direction: the adapter emits ONLY the
    # intervention node and REFUSES the causal edge — adapters never invent a
    # dimension, and no emitted causal edge carries a None dimension.
    frag = workgraph.adapt([_keystone_task(dimension=None)])
    assert frag["causal_edges"] == []
    assert frag["nodes"][0]["subject_key"] == "tasks/42"
    # discrimination: the SAME task WITH a dimension does emit the edge.
    ok = workgraph.adapt([_keystone_task()])
    assert len(ok["causal_edges"]) == 1
    assert ok["causal_edges"][0]["dimension"] == L.DIMENSION


# ===========================================================================
# (3) mission_inputs adapter — outcome/constraint floors (§4.1)
# ===========================================================================

def test_mission_inputs_emits_outcomes_and_constraint_floors():
    frag = mission_inputs.adapt([
        {"slug": "cost-goal", "dimension": "cost"},
        {"slug": "budget-cap", "kind": "constraint", "dimension": "cost",
         "floor": 0.5, "evidence_subjects": ["observation/x"]},
    ])
    assert frag["outcomes"] == [{"slug": "cost-goal", "dimension": "cost"}]
    c = frag["constraints"][0]
    assert c["slug"] == "budget-cap" and c["floor"] == 0.5 and c["dimension"] == "cost"
    assert c["evidence_subjects"] == ["observation/x"]


# ===========================================================================
# (4) product_spec adapter — instrument nodes + indicates edges (§4.2)
# ===========================================================================

def test_product_spec_emits_instruments_and_indicates_edges():
    frag = product_spec.adapt([{"slug": "goal", "dimension": "cost",
                                "instruments": ["proxy-metric",
                                                {"name": "lead-time", "dimension": "speed"}]}])
    assert {"slug": "goal", "dimension": "cost"} in frag["outcomes"]
    assert {"kind": "instrument", "subject_key": "instrument/proxy-metric"} in frag["nodes"]
    assert {"kind": "instrument", "subject_key": "instrument/lead-time"} in frag["nodes"]
    assert {"source": "instrument/proxy-metric", "target": "outcome/goal",
            "dimension": "cost"} in frag["indicates_edges"]
    assert {"source": "instrument/lead-time", "target": "outcome/goal",
            "dimension": "speed"} in frag["indicates_edges"]


# ===========================================================================
# (5) blast isolation (§2.2) — each standalone; a missing source is DECLARED
# ===========================================================================

def test_each_adapter_is_standalone_on_empty_input():
    assert roots.adapt([]) == {"directions": [], "objectives": []}
    assert workgraph.adapt([]) == {"nodes": [], "causal_edges": []}
    assert mission_inputs.adapt([]) == {"outcomes": [], "constraints": []}
    assert product_spec.adapt([]) == {"outcomes": [], "nodes": [], "indicates_edges": []}


def test_missing_product_adapter_is_declared_absent_never_silent(tmp_path):
    # the missing-product-adapter foundry sim (§2.2): assembling with NO product
    # source SUCCEEDS with the absence DECLARED, and the present adapters intact.
    merged = assemble({
        "roots": roots.adapt([{"slug": "lane", "statement": "s"}]),
        "workgraph": None,
        "mission_inputs": mission_inputs.adapt([{"slug": "o"}]),
        "product_spec": None,
    })
    assert merged["declared_absent"] == ["product_spec", "workgraph"]  # sorted, explicit
    assert merged["directions"] == [{"slug": "lane", "statement": "s"}]
    assert merged["outcomes"] == [{"slug": "o"}]

    # (nit d) declared_absent is durable in the objectives-input but was invisible at
    # serve; the build now copies it into graph-manifest.json (additive, OUTSIDE the
    # epoch tuple). Prove it survives the build into the served manifest.
    objectives = tmp_path / "cache" / "objectives"
    objectives.mkdir(parents=True)
    roots_path = tmp_path / "cache" / "objectives-input.json"
    roots_path.write_text(json.dumps(merged), encoding="utf-8")
    graph.build_graph(str(roots_path), str(objectives), L.SCOPE, L.CUTOFF)
    manifest = json.loads((objectives / "graph-manifest.json").read_text(encoding="utf-8"))
    assert manifest["declared_absent"] == ["product_spec", "workgraph"]


# ===========================================================================
# (6) assembly — one deterministic input; collision = structural error (item 7)
# ===========================================================================

def test_assemble_is_deterministic_and_order_independent():
    fa = roots.adapt([{"slug": "l", "statement": "s"}])
    fb = product_spec.adapt([{"slug": "g", "instruments": ["m"]}])
    one = assemble({"roots": fa, "product_spec": fb})
    two = assemble({"product_spec": fb, "roots": fa})
    assert one == two
    assert one["nodes"] == sorted(one["nodes"], key=lambda n: n["subject_key"])


def test_assemble_collision_is_a_structural_error():
    with pytest.raises(AssemblyCollision):
        assemble({"a": {"outcomes": [{"slug": "x", "dimension": "cost"}]},
                  "b": {"outcomes": [{"slug": "x", "dimension": "speed"}]}})


def test_assemble_dedups_identical_duplicates():
    merged = assemble({"a": {"outcomes": [{"slug": "x", "dimension": "cost"}]},
                       "b": {"outcomes": [{"slug": "x", "dimension": "cost"}]}})
    assert merged["outcomes"] == [{"slug": "x", "dimension": "cost"}]


# ===========================================================================
# (7) the KEYSTONE — adapters -> assemble -> build_graph -> serve (P6 deferral)
# ===========================================================================

def _run_keystone(tmp_path, log_dir, *, source, assumptions):
    """Seed one verdict consequence row matching the task's join, run the adapters,
    assemble, persist the cortex store, build the graph, serve, and return the ONE
    causal edge record."""
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)

    row = L.consequence_row("ship", "feature-x", verdict="confirmed", source=source,
                            actor_kind="officer", actor_id="cto", ts=L.EVIDENCE_TS)
    L.seed_consequence_ledger(log_dir, [row])
    beliefs = L.fold_beliefs(L.consequence_protos())
    L.persist_cortex_store(cortex, beliefs)

    task = _keystone_task()
    if assumptions:
        task["assumptions"] = ["declared-confounder-and-selection"]
    merged = assemble({
        "roots": None,
        "workgraph": workgraph.adapt([task]),
        "mission_inputs": mission_inputs.adapt([{"slug": "feature-x",
                                                 "dimension": L.DIMENSION}]),
        "product_spec": None,
    })
    roots_path = cache_root / "objectives-input.json"
    roots_path.write_text(json.dumps(merged), encoding="utf-8")

    graph.build_graph(str(roots_path), str(objectives), L.SCOPE, L.CUTOFF)
    served = query.serve_graph(str(objectives))
    edges = [r for r in served["records"] if r.get("target_kind") and "state" in r]
    assert len(edges) == 1, edges
    return edges[0]


def test_keystone_human_confirm_with_assumptions_is_intervention_supported(
        tmp_path, consequence_ledger):
    edge = _run_keystone(tmp_path, consequence_ledger,
                         source="verdict_human", assumptions=True)
    assert edge["state"] == L.STATE_INTERVENTION_SUPPORTED


def test_keystone_judge_confirm_caps_at_observationally_supported(
        tmp_path, consequence_ledger):
    edge = _run_keystone(tmp_path, consequence_ledger,
                         source="verdict_judge", assumptions=True)
    assert edge["state"] == L.STATE_OBSERVATIONALLY_SUPPORTED


def test_keystone_human_confirm_without_assumptions_is_hypothesized(
        tmp_path, consequence_ledger):
    # ruling R-A: P3 AND P5 require non-empty assumptions — a human confirm with
    # none lands at P6 hypothesized, never promoted.
    edge = _run_keystone(tmp_path, consequence_ledger,
                         source="verdict_human", assumptions=False)
    assert edge["state"] == L.STATE_HYPOTHESIZED


def test_keystone_is_deterministic_through_the_real_pipeline(
        tmp_path, consequence_ledger):
    # the build over the assembled input reproduces BYTE-IDENTICAL canonical
    # artifacts — graph.jsonl AND graph-manifest.json — not merely an equal served
    # edge. Two builds from ONE injected input into sibling out-dirs (shared cortex,
    # shared roots file so roots_path is identical) must be byte-for-byte equal
    # (§5.4 seed-independent chained hashing; A-M6 purity — no clock in the epoch).
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    row = L.consequence_row("ship", "feature-x", verdict="confirmed",
                            source="verdict_human", actor_kind="officer",
                            actor_id="cto", ts=L.EVIDENCE_TS)
    L.seed_consequence_ledger(consequence_ledger, [row])
    L.persist_cortex_store(cortex, L.fold_beliefs(L.consequence_protos()))

    task = _keystone_task(assumptions=["declared-confounder-and-selection"])
    merged = assemble({
        "roots": None,
        "workgraph": workgraph.adapt([task]),
        "mission_inputs": mission_inputs.adapt([{"slug": "feature-x",
                                                 "dimension": L.DIMENSION}]),
        "product_spec": None,
    })
    roots_path = cache_root / "objectives-input.json"
    roots_path.write_text(json.dumps(merged), encoding="utf-8")

    out_a, out_b = cache_root / "objectives_a", cache_root / "objectives_b"
    graph.build_graph(str(roots_path), str(out_a), L.SCOPE, L.CUTOFF)
    graph.build_graph(str(roots_path), str(out_b), L.SCOPE, L.CUTOFF)

    assert (out_a / "graph.jsonl").read_bytes() == (out_b / "graph.jsonl").read_bytes()
    assert (out_a / "graph-manifest.json").read_bytes() \
        == (out_b / "graph-manifest.json").read_bytes()
    # and the served edge still lands where the pipeline promises (P3: a human
    # confirm + assumptions) — the property the equal-edge check originally pinned.
    served = query.serve_graph(str(out_a))
    edges = [r for r in served["records"] if r.get("target_kind") and "state" in r]
    assert len(edges) == 1 and edges[0]["state"] == L.STATE_INTERVENTION_SUPPORTED


# ===========================================================================
# (8) roots + build_graph — a rooted objective builds and serves answerable
# ===========================================================================

def test_roots_objective_builds_and_serves_answerable(tmp_path):
    merged = assemble({
        "roots": roots.adapt([{"slug": "lane", "statement": "s",
                               "objectives": [{"slug": "obj-x"}]}]),
        "workgraph": None, "mission_inputs": None, "product_spec": None,
    })
    cache_root = tmp_path / "cache"
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    roots_path = cache_root / "objectives-input.json"
    roots_path.write_text(json.dumps(merged), encoding="utf-8")
    graph.build_graph(str(roots_path), str(objectives), L.SCOPE, L.CUTOFF)
    ans = query.serve_objective(str(objectives), "objective/obj-x")
    # the rooted objective built (root_ref resolved) — answerable, never orphaned.
    assert "orphaned" not in ans.flags


def test_product_indicates_edge_survives_the_build(tmp_path):
    merged = assemble({
        "product_spec": product_spec.adapt([{"slug": "goal", "dimension": L.DIMENSION,
                                             "instruments": ["proxy-metric"]}]),
        "roots": None, "workgraph": None, "mission_inputs": None,
    })
    cache_root = tmp_path / "cache"
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    roots_path = cache_root / "objectives-input.json"
    roots_path.write_text(json.dumps(merged), encoding="utf-8")
    graph.build_graph(str(roots_path), str(objectives), L.SCOPE, L.CUTOFF)
    rows = [json.loads(x) for x in
            (objectives / "graph.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert any(r.get("relation") == "indicates" for r in rows)
    assert any(r.get("kind") == "instrument" for r in rows)


# ===========================================================================
# (9) the CLI roots<->adapter merge boundary — the ONE assembly law (MUST-FIX)
# ===========================================================================
#
# The production merge lane is cog3-rebuild.py `_merge_adapter_sources`. Pre-fix it
# hand-concatenated the adapter fragments onto the roots-derived categories with NO
# collision check, so a roots-derived and an adapter-emitted item sharing one
# identity but disagreeing on content produced TWO graph.jsonl rows under ONE
# node_id at exit 0 — a silently corrupt canonical artifact. These pin the fix
# THROUGH THE REAL CLI SUBPROCESS: a conflict fails loud + non-zero with no artifact;
# an identical duplicate dedups to one row; and an operator-typo source key is a hard
# error, never a silent empty adapter.

def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_cli_merge_collision_between_roots_and_adapter_fails_loudly(tmp_path):
    # MUST-FIX repro: roots-derived outcome 'feature-x' (dimension speed) + --products
    # outcome 'feature-x' (dimension cost) => same slug, conflicting content. The
    # shared assembly law makes this a LOUD non-zero failure with a clear message and
    # NO corrupt graph.jsonl (pre-fix: exit 0, two rows under one node_id).
    roots_f = _write(tmp_path / "roots.yml",
                     'directions:\n  lane-a:\n    statement: "s"\n'
                     "outcomes:\n  - slug: feature-x\n    dimension: speed\n")
    products_f = _write(tmp_path / "products.yml",
                        "products:\n  - slug: feature-x\n    dimension: cost\n"
                        "    instruments: [lead-time]\n")
    cache = tmp_path / "cache" / "objectives"
    proc = _run_cli(roots_f, cache, products=products_f)
    assert proc.returncode != 0, f"expected non-zero on collision; stdout={proc.stdout!r}"
    assert "collision" in proc.stderr.lower(), proc.stderr
    assert "feature-x" in proc.stderr, proc.stderr
    # the corrupt canonical artifact was NEVER written (collision precedes the build).
    assert not (cache / "graph.jsonl").exists()


def test_cli_merge_identical_duplicate_builds_one_row(tmp_path):
    # MUST-FIX companion: an IDENTICAL roots/adapter outcome ('feature-x', cost on
    # both sides) is DEDUPED to ONE graph row, exit 0 — the same assembly law that
    # rejects a conflict accepts a true duplicate (pre-fix: two identical rows,
    # inflated node_count).
    roots_f = _write(tmp_path / "roots.yml",
                     'directions:\n  lane-a:\n    statement: "s"\n'
                     "outcomes:\n  - slug: feature-x\n    dimension: cost\n")
    products_f = _write(tmp_path / "products.yml",
                        "products:\n  - slug: feature-x\n    dimension: cost\n"
                        "    instruments: [lead-time]\n")
    cache = tmp_path / "cache" / "objectives"
    proc = _run_cli(roots_f, cache, products=products_f)
    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(x) for x in
            (cache / "graph.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    fx = [r for r in rows if r.get("subject_key") == "outcome/feature-x"]
    assert len(fx) == 1, fx                                   # deduped, not doubled
    # node_count is honest — no duplicate node_id inflating it.
    manifest = json.loads((cache / "graph-manifest.json").read_text(encoding="utf-8"))
    node_ids = [r["node_id"] for r in rows if r.get("kind")]
    assert len(node_ids) == len(set(node_ids)) == manifest["node_count"]


def test_cli_adapter_source_with_wrong_top_level_key_is_a_hard_error(tmp_path):
    # (nit b) a flag-passed source whose top-level key does not match (a `task:` vs
    # `tasks:` typo) previously yielded an empty adapter SILENTLY. It is operator
    # error: the CLI hard-errors non-zero, naming the expected key.
    roots_f = _write(tmp_path / "roots.yml",
                     'directions:\n  lane-a:\n    statement: "s"\n')
    bad = _write(tmp_path / "wg.yml",                         # 'task:' (typo) not 'tasks:'
                 "task:\n  - task_id: 1\n    action: do\n    subject: x\n")
    cache = tmp_path / "cache" / "objectives"
    proc = _run_cli(roots_f, cache, workgraph_src=bad)
    assert proc.returncode != 0, proc.stdout
    assert "tasks" in proc.stderr, proc.stderr
    assert not (cache / "graph.jsonl").exists()


def test_cli_default_no_flag_build_is_unchanged_and_omits_declared_absent(tmp_path):
    # backward-compat: the default no-flag lane never calls the merge path, so the
    # roots-only manifest carries NO declared_absent key (the additive field appears
    # ONLY when the adapter merge ran). Builds green on the real production roots.
    cache = tmp_path / "cache" / "objectives"
    proc = _run_cli(Path(_ROOT) / "instance" / "config" / "directions.yml", cache)
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((cache / "graph-manifest.json").read_text(encoding="utf-8"))
    assert "declared_absent" not in manifest
