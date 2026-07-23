"""test_cog3_verdict_inbox.py — R1 THE VERDICT INBOX (WR rider, BACKLOG :1559 /
phase-4 contract §18): the cabinet/scripts/cog3-verdict-inbox.py battery.

ADDITIVE suite (the landed COG-3 corpus is immutable; this only ADDS). Every
graph here is built END-TO-END through the REAL rebuild CLI (subprocess
`cog3-rebuild.py` with tmp roots + workgraph/missions sources + a file-seeded
sibling cortex store — the test_cog3_exit_fixtures idiom, reused verbatim) and
every inbox run is the REAL CLI as a subprocess. Never a hand-built graph.

What is pinned:
  * VOI ranking order — the P5 (judge-capped, verdict-blocked-only) edge
    outranks the P4 (direction-contested) edge outranks the P6 (bare) edges;
    already-ruled edges (P3 via verdict_human) never appear; the brief caps at
    --top (default 3).
  * DETERMINISM — two subprocess runs under DISTINCT PYTHONHASHSEED produce
    byte-identical artifacts and identical --json rankings (the C-F3 idiom).
  * REFUSE-respecting behavior — a tampered graph row store, a counterfactual
    manifest, and a tampered/half-present predictions store each make the inbox
    refuse LOUDLY (exit 2, REFUSED on stderr) and write NO artifact: stale
    advice is never emitted.
  * Prediction pressure — an UNSCORED minted prediction (real
    counterfactual.mint_prediction) breaks a same-band tie toward its edge and
    surfaces as an open-forecast rider line; a SCORED prediction stops counting.
  * Captain register — the artifact carries the bijective Captain vocabulary
    (tested/refuted) and ZERO internal tokens (state enums, id field names,
    store filenames — the banned list is assembled from parts so THIS file
    never trips a token sweep itself).
  * Surface + discipline pins — the default artifact home is the existing
    research-briefs captain surface, and the CLI source never names the raw
    row-store file (serve_graph is the one read path).

S0: python3.12, file-seeded (no DSN), deterministic (declared canonical
timestamps, no clock), CI-fast (bounded worlds).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; WR rider R1.
"""
from __future__ import annotations

import importlib.util
import json
import os
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

_REBUILD = Path(_ROOT) / "cabinet" / "scripts" / "cog3-rebuild.py"
_INBOX = Path(_ROOT) / "cabinet" / "scripts" / "cog3-verdict-inbox.py"

CUTOFF = L.CUTOFF
TS = L.EVIDENCE_TS
NOW = "2026-07-23T06:00:00Z"                     # declared canonical now (no clock)
_ASSUMPTIONS = ["declared-confounder-and-selection"]


# ===========================================================================
# Harness — the exit-fixtures idiom: seed cortex, run the REAL rebuild CLI
# ===========================================================================

@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


def _write_json(path, obj):
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return Path(path)


def _seed_cortex(cortex_dir, events_dir, consequence_rows, obs_protos=()):
    if consequence_rows:
        L.seed_consequence_ledger(events_dir, consequence_rows)
    protos = (L.consequence_protos() if consequence_rows else []) + list(obs_protos)
    beliefs = L.fold_beliefs(protos)
    cortex_dir.mkdir(parents=True, exist_ok=True)
    L.persist_cortex_store(cortex_dir, beliefs)


def _task(task_id, action, subject, target, dimension, effect):
    return {"task_id": task_id, "actor": {"kind": "officer", "id": "cto"},
            "action": action, "subject": subject, "ts": TS,
            "target": target, "dimension": dimension,
            "expected_effect": effect, "assumptions": _ASSUMPTIONS}


# The five-edge world: one per §5.2 band the inbox ranks (+ one excluded P3).
#   tasks/101 tune cache-layer     -> outcome/page-speed  : judge CONFIRM  => P5
#   tasks/102 rewrite queue        -> outcome/throughput  : judge WRONG    => P4
#   tasks/103 split billing        -> outcome/error-rate  : no evidence    => P6
#   tasks/104 retrain model        -> outcome/accuracy    : no evidence    => P6
#   tasks/105 ship portal          -> outcome/signup-rate : human CONFIRM  => P3
_WORLD_TASKS = [
    _task(101, "tune", "cache-layer", "outcome/page-speed", "latency", "decrease"),
    _task(102, "rewrite", "queue", "outcome/throughput", "volume", "increase"),
    _task(103, "split", "billing", "outcome/error-rate", "quality", "decrease"),
    _task(104, "retrain", "model", "outcome/accuracy", "quality", "increase"),
    _task(105, "ship", "portal", "outcome/signup-rate", "growth", "increase"),
]
_WORLD_MISSIONS = [
    {"slug": "page-speed", "dimension": "latency"},
    {"slug": "throughput", "dimension": "volume"},
    {"slug": "error-rate", "dimension": "quality"},
    {"slug": "accuracy", "dimension": "quality"},
    {"slug": "signup-rate", "dimension": "growth"},
]
_WORLD_ROWS = [
    L.consequence_row("tune", "cache-layer", verdict="confirmed",
                      source="verdict_judge", actor_kind="officer",
                      actor_id="cto", ts=TS),
    L.consequence_row("rewrite", "queue", verdict="wrong",
                      source="verdict_judge", actor_kind="officer",
                      actor_id="cto", ts=TS),
    L.consequence_row("ship", "portal", verdict="confirmed",
                      source="verdict_human", actor_kind="officer",
                      actor_id="cto", ts=TS),
]


def _build_world(tmp_path, events_dir, *, tasks=None, missions=None, rows=None,
                 hashseed=0):
    """Seed the cortex + run the REAL rebuild CLI into tmp cache/objectives.
    Returns the objectives cache dir."""
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"
    _seed_cortex(cortex, events_dir, _WORLD_ROWS if rows is None else rows)
    roots = _write_json(tmp_path / "roots.yml", {
        "directions": {"velocity": {"statement": "ship value faster"}},
        "objectives": [{"slug": "faster-product", "root_ref": "velocity"}],
    })
    workgraph = _write_json(tmp_path / "workgraph.yml",
                            {"tasks": _WORLD_TASKS if tasks is None else tasks})
    missions_f = _write_json(tmp_path / "missions.yml",
                             {"missions": _WORLD_MISSIONS if missions is None
                              else missions})
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(hashseed)
    proc = subprocess.run(
        [sys.executable, str(_REBUILD), "--roots", str(roots), "--cache",
         str(objectives), "--cutoff", CUTOFF, "--workgraph", str(workgraph),
         "--missions", str(missions_f)],
        capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return objectives


def _run_inbox(cache, out, *, now=NOW, top=None, want_json=True, hashseed=None):
    argv = [sys.executable, str(_INBOX), "--cache", str(cache), "--now", now,
            "--out", str(out)]
    if top is not None:
        argv += ["--top", str(top)]
    if want_json:
        argv += ["--json"]
    env = dict(os.environ)
    if hashseed is not None:
        env["PYTHONHASHSEED"] = str(hashseed)
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def _candidates(proc):
    return json.loads(proc.stdout)["candidates"]


# ===========================================================================
# Ranking: bands, exclusions, cap
# ===========================================================================

def test_ranking_bands_exclusions_and_cap(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out = tmp_path / "inbox.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 0, proc.stderr

    cands = _candidates(proc)
    sources = [c["source"] for c in cands]
    # the already-human-ruled edge (P3) NEVER appears as a candidate.
    assert "tasks/105" not in sources
    # band order: P5 (only the verdict missing) > P4 (machine says no) > P6 x2.
    assert sources[0] == "tasks/101" and cands[0]["band"] == 1
    assert sources[1] == "tasks/102" and cands[1]["band"] == 2
    assert sorted(sources[2:]) == ["tasks/103", "tasks/104"]
    assert [c["band"] for c in cands[2:]] == [3, 3]
    # P6 tie with equal forecasts/degree breaks on the fixed lexicographic key.
    assert cands[2]["edge_id"] < cands[3]["edge_id"]

    # the artifact carries the TOP-3 only: the 4th candidate's work item is
    # absent, and the request sections are exactly three.
    body = out.read_text(encoding="utf-8")
    dropped = cands[3]["source"]
    assert dropped not in body
    assert body.count("## ") == 4                 # 3 requests + "How these were chosen"
    assert "## How these were chosen" in body
    assert "## 1. “tasks/101”" in body
    # the state-machine consequence rides each request in Captain words.
    assert "**tested**" in body and "**refuted**" in body
    # provenance footer: built-at cutoff + generated-at now, both declared.
    assert CUTOFF in body and NOW in body


def test_top_flag_caps_the_brief(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out = tmp_path / "inbox.md"
    proc = _run_inbox(cache, out, top=1)
    assert proc.returncode == 0, proc.stderr
    body = out.read_text(encoding="utf-8")
    assert body.count("## ") == 2                 # 1 request + the ranking note
    assert "tasks/102" not in body


# ===========================================================================
# Determinism (the C-F3 subprocess-seed idiom)
# ===========================================================================

def test_artifact_and_ranking_deterministic_across_hashseed(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out_a = tmp_path / "a.md"
    out_b = tmp_path / "b.md"
    proc_a = _run_inbox(cache, out_a, hashseed=0)
    proc_b = _run_inbox(cache, out_b, hashseed=12345)
    assert proc_a.returncode == 0, proc_a.stderr
    assert proc_b.returncode == 0, proc_b.stderr
    assert out_a.read_bytes() == out_b.read_bytes()
    # the machine-readable ranking is identical too (artifact path differs by
    # construction, so compare everything else).
    ja = json.loads(proc_a.stdout)
    jb = json.loads(proc_b.stdout)
    ja.pop("artifact"), jb.pop("artifact")
    assert ja == jb


# ===========================================================================
# REFUSE-respecting behavior: tampered/counterfactual stores never emit advice
# ===========================================================================

def test_tampered_graph_rows_refuse_loudly_and_write_nothing(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    store = cache / ("graph" + ".jsonl")          # assembled: no sweep self-trip
    tampered = store.read_text(encoding="utf-8").replace(
        '"hypothesized"', '"intervention_supported"', 1)
    assert '"intervention_supported"' in tampered
    store.write_text(tampered, encoding="utf-8")

    out = tmp_path / "tampered-inbox.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 2
    assert "REFUSED" in proc.stderr
    assert not out.exists(), "a refused run must write NO artifact"


def test_counterfactual_manifest_refuses(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    manifest_path = cache / "graph-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counterfactual"] = True
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2),
                             encoding="utf-8")
    out = tmp_path / "cf-inbox.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 2
    assert "REFUSED" in proc.stderr
    assert not out.exists()


def test_tampered_predictions_store_refuses(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    from framework.objectives import counterfactual  # test-side import (glob-allowlisted)
    out0 = tmp_path / "seed.md"
    proc0 = _run_inbox(cache, out0)
    edge_101 = next(c["edge_id"] for c in _candidates(proc0)
                    if c["source"] == "tasks/101")
    counterfactual.mint_prediction(str(cache), edge_101,
                                   {"assume": "cache stays warm"},
                                   CUTOFF, {"observed_effect": "decrease"})

    # (a) an appended row the manifest never chained => refuse, no artifact.
    store = cache / "predictions" / "predictions.jsonl"
    with open(store, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"record_kind": "prediction",
                                 "prediction_id": "pred-forged",
                                 "edge_id": edge_101}) + "\n")
    out = tmp_path / "pred-tampered.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 2
    assert "REFUSED" in proc.stderr
    assert not out.exists()

    # (b) a half-present store (manifest deleted) => refuse, no artifact.
    (cache / "predictions" / "predictions-manifest.json").unlink()
    out2 = tmp_path / "pred-half.md"
    proc2 = _run_inbox(cache, out2)
    assert proc2.returncode == 2
    assert "REFUSED" in proc2.stderr
    assert not out2.exists()


# ===========================================================================
# Prediction pressure: unscored forecasts pull rank; scored ones stop counting
# ===========================================================================

def test_open_forecasts_break_ties_and_scored_ones_do_not(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out0 = tmp_path / "before.md"
    proc0 = _run_inbox(cache, out0)
    cands0 = _candidates(proc0)
    loser = cands0[3]                              # the P6 edge the cap dropped
    assert loser["band"] == 3 and loser["open_forecasts"] == 0

    from framework.objectives import counterfactual  # test-side import
    pid = counterfactual.mint_prediction(str(cache), loser["edge_id"],
                                         {"assume": "load stays flat"}, CUTOFF,
                                         {"observed_effect": loser["expected_effect"]})

    out1 = tmp_path / "after-mint.md"
    proc1 = _run_inbox(cache, out1)
    cands1 = _candidates(proc1)
    # the open forecast pulls the former loser above its band-3 peer...
    assert cands1[2]["edge_id"] == loser["edge_id"]
    assert cands1[2]["open_forecasts"] == 1
    body = out1.read_text(encoding="utf-8")
    assert loser["source"] in body
    assert "open forecast" in body                # the rider line surfaces it

    # ...and SCORING the prediction makes it stop counting (uncertainty spent).
    counterfactual.score_prediction(str(cache), pid,
                                    {"observed_effect": "maintain"})
    out2 = tmp_path / "after-score.md"
    proc2 = _run_inbox(cache, out2)
    cands2 = _candidates(proc2)
    assert all(c["open_forecasts"] == 0 for c in cands2)
    # the tie reverts to the fixed lexicographic order.
    assert [c["edge_id"] for c in cands2] == [c["edge_id"] for c in cands0]


# ===========================================================================
# Empty pool + bad --now
# ===========================================================================

def test_empty_pool_writes_an_honest_empty_inbox(tmp_path, events_dir):
    cache = _build_world(
        tmp_path, events_dir,
        tasks=[_task(105, "ship", "portal", "outcome/signup-rate", "growth",
                     "increase")],
        missions=[{"slug": "signup-rate", "dimension": "growth"}],
        rows=[L.consequence_row("ship", "portal", verdict="confirmed",
                                source="verdict_human", actor_kind="officer",
                                actor_id="cto", ts=TS)])
    out = tmp_path / "empty.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["candidates"] == []
    body = out.read_text(encoding="utf-8")
    assert "Nothing needs your verdict right now" in body


def test_non_canonical_now_is_refused(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out = tmp_path / "bad-now.md"
    proc = _run_inbox(cache, out, now="2026-07-23T06:00:00+00:00")
    assert proc.returncode == 2
    assert not out.exists()


# ===========================================================================
# Captain register + surface/discipline pins
# ===========================================================================

def test_artifact_speaks_captain_register_only(tmp_path, events_dir):
    cache = _build_world(tmp_path, events_dir)
    out = tmp_path / "register.md"
    proc = _run_inbox(cache, out)
    assert proc.returncode == 0, proc.stderr
    body = out.read_text(encoding="utf-8")

    # banned internal tokens — ASSEMBLED from parts so this file never trips a
    # token sweep itself. State enums, id field names, store filenames, section
    # signs: none of the plumbing vocabulary may reach the Captain.
    banned = [
        "verdict" + "_human", "verdict" + "_judge",
        "observationally" + "_supported", "intervention" + "_supported",
        "direction" + "_contested", "edge" + "_id", "node" + "_id",
        "subject" + "_key", "graph" + ".jsonl", "Serve" + "Refused",
        "VOI", "§",
    ]
    for token in banned:
        assert token not in body, f"internal token leaked to the Captain: {token}"
    # the bijective Captain vocabulary IS the register (query.to_captain_word).
    assert "tested" in body and "refuted" in body and "observed" in body
    # the ranking function is declared in the artifact, honestly.
    assert "## How these were chosen" in body


def test_default_out_is_the_research_briefs_surface_and_serve_is_the_one_read():
    # import the CLI as a module (no run): pin the default surface + template.
    spec = importlib.util.spec_from_file_location("cog3_verdict_inbox", _INBOX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    brief_dir = Path(mod._BRIEF_DIR)
    assert brief_dir.parts[-3:] == ("shared", "interfaces", "research-briefs")
    assert mod._OUT_TEMPLATE == "{date}-verdict-inbox.md"
    # discipline tripwire: the CLI never names the raw row-store file — the
    # PUBLIC serve surface is its one graph read path (REFUSE limbs intact).
    source = _INBOX.read_text(encoding="utf-8")
    assert ("graph" + ".jsonl") not in source
    assert "serve_graph(" in source
