"""R3 weekly shadow-dividend report — the rider's own battery (BACKLOG :1561,
COG-4 contract §18 WR lane).

DISCIPLINE (the COG-3 corpus idiom, reused):
  * FIXTURE-GRAPH: seed real cortex evidence via lib_cog3_fixtures, build a
    REAL graph through the production cog3-rebuild.py CLI (subprocess), then
    run the REAL cog3-shadow-dividend.py CLI (subprocess) against it — never a
    hand-built served view, never repo-default paths (every dir injected).
  * CONTENT: the report carries every promised section, the Captain
    vocabulary, the first-report / delta / no-change paths, the divergence and
    orphan dividends, the R1 cross-reference both ways, and NO internal jargon.
  * DETERMINISM: fixed inputs (cache + state + --now) reproduce the report
    BYTE-IDENTICAL across distinct PYTHONHASHSEED values.
  * REFUSAL: a tampered graph.jsonl is REFUSED loudly (exit 2) — no report
    written, state file byte-untouched (the R1 serve-surface discipline).
  * PURITY: the CLI source carries no clock read, no env read, no subprocess,
    no yaml — a source-scan ratchet, the house style.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; R3 rider (WR lane).
"""
from __future__ import annotations

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

_REBUILD_CLI = Path(_ROOT) / "cabinet" / "scripts" / "cog3-rebuild.py"
_REPORT_CLI = Path(_ROOT) / "cabinet" / "scripts" / "cog3-shadow-dividend.py"

CUTOFF = L.CUTOFF
TS = L.EVIDENCE_TS
NOW = "2026-07-23T06:00:00Z"
_ASSUMPTIONS = ["declared-confounder-and-selection"]


# ===========================================================================
# Fixture-graph harness (the exit-fixtures idiom, narrowed to this battery)
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


def _seed_cortex(cortex_dir, events_dir, consequence_rows, obs_protos):
    if consequence_rows:
        L.seed_consequence_ledger(events_dir, consequence_rows)
    protos = (L.consequence_protos() if consequence_rows else []) + list(obs_protos)
    beliefs = L.fold_beliefs(protos)
    cortex_dir.mkdir(parents=True, exist_ok=True)
    L.persist_cortex_store(cortex_dir, beliefs)
    return beliefs


def _rebuild(roots, cache, *, workgraph=None, missions=None, products=None,
             hashseed=0):
    argv = [sys.executable, str(_REBUILD_CLI), "--roots", str(roots),
            "--cache", str(cache), "--cutoff", CUTOFF]
    if workgraph is not None:
        argv += ["--workgraph", str(workgraph)]
    if missions is not None:
        argv += ["--missions", str(missions)]
    if products is not None:
        argv += ["--products", str(products)]
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(hashseed)
    proc = subprocess.run(argv, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc


def _report(now, cache, out_dir, state_dir, *, hashseed=0):
    """Run the REAL R3 CLI as a subprocess with every path injected."""
    argv = [sys.executable, str(_REPORT_CLI), "--now", now,
            "--cache", str(cache), "--out-dir", str(out_dir),
            "--state-dir", str(state_dir)]
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(hashseed)
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def _build_fixture_graph(tmp_path, events_dir, *, extra_objective=False):
    """The R3 fixture cabinet: one tested link (human confirm), one observed
    link (machine confirm — capped), an instrument-vs-outcome divergence, an
    ORPHANED objective (its direction edited away), a depends_on spine for the
    priority ordering, and a conflicts_with pair. Seed inputs, run the real
    substrate."""
    cache_root = tmp_path / "cache"
    cortex = cache_root / "cortex"
    objectives = cache_root / "objectives"

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

    objectives_list = [
        {"slug": "faster-checkout", "root_ref": "velocity",
         "depends_on": ["stable-platform"]},
        {"slug": "stable-platform", "root_ref": "velocity",
         "conflicts_with": ["cheap-hosting"]},
        {"slug": "cheap-hosting", "root_ref": "velocity"},
        # root_ref names a direction that does NOT exist => ORPHANED flag.
        {"slug": "lost-cause", "root_ref": "a-direction-that-was-deleted"},
    ]
    if extra_objective:
        objectives_list.append({"slug": "brand-new-goal", "root_ref": "velocity"})
    roots = _write_json(tmp_path / "roots.yml", {
        "directions": {"velocity": {"statement": "ship value faster"}},
        "objectives": objectives_list,
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
    _rebuild(roots, objectives, workgraph=workgraph, missions=missions,
             products=products)
    return cache_root, objectives


# ===========================================================================
# Content sections (the promised report surface)
# ===========================================================================

def test_report_carries_every_promised_section(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    state_dir = tmp_path / "state"

    proc = _report(NOW, objectives, out_dir, state_dir)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    report_path = Path(summary["report_path"])
    assert report_path == out_dir / "shadow-dividend-2026-07-23.md"
    assert report_path.exists()
    body = report_path.read_text(encoding="utf-8")

    # every promised section, in the Captain register
    assert "# Weekly shadow report" in body
    assert "## What the map believes right now" in body
    assert "## What changed since the last report" in body
    assert "## Where the numbers and the results disagree" in body
    assert "## What it would recommend" in body
    assert "## Waiting on a human verdict" in body
    assert "## What this report cannot claim" in body

    # believes-now: objectives + the Captain vocabulary words with glosses
    assert "faster-checkout" in body
    assert "stable-platform" in body
    assert "tested (a person confirmed it worked)" in body
    assert "observed (the numbers moved as hoped" in body

    # first report path (no prior state existed)
    assert summary["first_report"] is True
    assert "This is the first report" in body

    # the divergence dividend (instrument vs outcome opposition, plain words)
    assert "cache-hit-rate" in body and "page-render-time" in body
    assert "telling a different story" in body

    # the orphan dividend
    assert "lost-cause" in body
    assert "Re-anchor it or retire it" in body

    # recommendations: stands behind the human-confirmed link; watches the
    # machine-confirmed one without claiming success. Interventions render as
    # "<action> on <subject>" — never an internal task id.
    assert "refactor on checkout → checkout-latency" in body
    assert "cache on render → page-render-time" in body
    assert "Watching, but NOT claiming success yet:" in body
    assert "permits a" in body            # the recommend-surface check line

    # awaiting human verdicts: the observed link is listed, count in summary
    assert "Waiting on a human verdict" in body
    assert summary["awaiting_verdicts"] >= 1

    # honesty paragraph: the cutoff date + the no-manufactured-certainty law
    assert CUTOFF[:10] in body
    assert "does not prove" in body

    # state file written under the injected state dir
    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert state["schema"] == "shadow-dividend-state/v1"
    assert state["graph_rows_hash"]
    assert state["counts"]["objectives"] == 4


def test_priority_ordering_is_the_stated_dependency_rule(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    proc = _report(NOW, objectives, out_dir, tmp_path / "state")
    assert proc.returncode == 0, proc.stderr
    body = (out_dir / "shadow-dividend-2026-07-23.md").read_text(encoding="utf-8")
    # stable-platform (leaned on by faster-checkout) ranks first, and the
    # mechanical rule is STATED — never passed off as the Captain's priorities.
    assert body.index("1. stable-platform") < body.index("faster-checkout")
    assert "no hand-set priorities yet" in body
    assert "lean on it" in body


def test_captain_register_carries_no_internal_jargon(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    proc = _report(NOW, objectives, out_dir, tmp_path / "state")
    assert proc.returncode == 0, proc.stderr
    body = (out_dir / "shadow-dividend-2026-07-23.md").read_text(encoding="utf-8")
    # the Captain plain-English law: none of the internal vocabulary leaks
    for token in ("§", "schg", "germline", "FW-0", "C-F15", "CG-",
                  "graph_rows_hash", "jsonl", "manifest", "cortex", "epoch",
                  "subject_key", "node_id", "serve_graph",
                  "intervention_supported", "observationally_supported"):
        assert token not in body, f"jargon {token!r} leaked into the report"


# ===========================================================================
# Change tracking: no-change and delta paths (prior state present)
# ===========================================================================

def test_second_run_unchanged_graph_says_nothing_changed(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    state_dir = tmp_path / "state"
    first = _report(NOW, objectives, out_dir, state_dir)
    assert first.returncode == 0, first.stderr

    later = "2026-07-30T06:00:00Z"
    second = _report(later, objectives, out_dir, state_dir)
    assert second.returncode == 0, second.stderr
    summary = json.loads(second.stdout)
    assert summary["first_report"] is False
    assert summary["changed"] is False
    body = (out_dir / "shadow-dividend-2026-07-30.md").read_text(encoding="utf-8")
    assert "Nothing has changed since the last report (2026-07-23)." in body


def test_second_run_after_graph_change_reports_the_delta(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    state_dir = tmp_path / "state"
    first = _report(NOW, objectives, out_dir, state_dir)
    assert first.returncode == 0, first.stderr

    # the graph moves: a rebuild with one more objective
    _build_fixture_graph(tmp_path, events_dir, extra_objective=True)
    later = "2026-07-30T06:00:00Z"
    second = _report(later, objectives, out_dir, state_dir)
    assert second.returncode == 0, second.stderr
    summary = json.loads(second.stdout)
    assert summary["changed"] is True
    body = (out_dir / "shadow-dividend-2026-07-30.md").read_text(encoding="utf-8")
    assert "Since the last report (2026-07-23):" in body
    assert "- objectives: 4 → 5" in body


# ===========================================================================
# Determinism: fixed inputs => byte-identical report, hash-seed independent
# ===========================================================================

def test_report_bytes_deterministic_across_hash_seeds(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    bodies = []
    for seed in (0, 12345):
        out_dir = tmp_path / f"surface-{seed}"
        state_dir = tmp_path / f"state-{seed}"
        proc = _report(NOW, objectives, out_dir, state_dir, hashseed=seed)
        assert proc.returncode == 0, proc.stderr
        bodies.append(
            (out_dir / "shadow-dividend-2026-07-23.md").read_bytes())
    assert bodies[0] == bodies[1], (
        "fixed inputs must reproduce the report byte-identical across "
        "PYTHONHASHSEED values")


# ===========================================================================
# The refusal path (the R1 serve-surface discipline)
# ===========================================================================

def test_tampered_graph_is_refused_loudly_nothing_written(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    state_dir = tmp_path / "state"
    first = _report(NOW, objectives, out_dir, state_dir)
    assert first.returncode == 0, first.stderr
    state_before = (state_dir / "state.json").read_bytes()

    # tamper: append a row so graph.jsonl no longer reproduces the recorded
    # rows-hash (the manufactured-certainty class the surface refuses).
    with open(objectives / "graph.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"tampered": "row"}) + "\n")

    later = "2026-07-30T06:00:00Z"
    proc = _report(later, objectives, out_dir, state_dir)
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert "REFUSED" in proc.stderr
    assert "integrity" in proc.stderr
    # no report artifact for the refused run; prior artifact untouched
    assert not (out_dir / "shadow-dividend-2026-07-30.md").exists()
    assert (out_dir / "shadow-dividend-2026-07-23.md").exists()
    # state byte-untouched — a refused run never advances the comparison base
    assert (state_dir / "state.json").read_bytes() == state_before


def test_missing_graph_is_operator_error_never_a_blank_report(tmp_path):
    out_dir = tmp_path / "surface"
    proc = _report(NOW, tmp_path / "nowhere", out_dir, tmp_path / "state")
    assert proc.returncode == 3
    assert "no objectives map found" in proc.stderr
    assert not out_dir.exists() or not list(out_dir.iterdir())


def test_non_canonical_now_is_refused(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    proc = _report("2026-07-23T06:00:00+00:00", objectives,
                   tmp_path / "surface", tmp_path / "state")
    assert proc.returncode == 3
    assert "not canonical" in proc.stderr


# ===========================================================================
# R1 cross-reference (the verdict-inbox artifact beside this report)
# ===========================================================================

def test_r1_inbox_present_is_cross_referenced(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    out_dir.mkdir()
    (out_dir / "verdict-inbox.json").write_text(
        json.dumps({"items": [{"q": "did the refactor work?"},
                              {"q": "did caching work?"}]}),
        encoding="utf-8")
    proc = _report(NOW, objectives, out_dir, tmp_path / "state")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["verdict_inbox_present"] is True
    body = (out_dir / "shadow-dividend-2026-07-23.md").read_text(encoding="utf-8")
    assert "verdict-inbox.json" in body
    assert "(2 item(s) ranked there)" in body


def test_r1_inbox_absent_is_reported_honestly(tmp_path, events_dir):
    _cache_root, objectives = _build_fixture_graph(tmp_path, events_dir)
    out_dir = tmp_path / "surface"
    proc = _report(NOW, objectives, out_dir, tmp_path / "state")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["verdict_inbox_present"] is False
    body = (out_dir / "shadow-dividend-2026-07-23.md").read_text(encoding="utf-8")
    assert "The verdict-inbox report is not here yet" in body


# ===========================================================================
# Purity ratchet: no clock, no env, no subprocess, no yaml in the CLI source
# ===========================================================================

def test_cli_source_carries_no_clock_env_or_subprocess_reads():
    src = _REPORT_CLI.read_text(encoding="utf-8")
    for forbidden in ("datetime.now", "time.time", "os.environ", "getenv",
                      "subprocess", "import yaml", "urllib", "socket"):
        assert forbidden not in src, (
            f"{forbidden!r} in cog3-shadow-dividend.py — the report takes "
            "every input as a declared argument (the cog3-staleness purity "
            "idiom); no ambient reads")


def test_cli_reads_graph_only_through_the_serve_surface():
    """The serve-surface law (the R1 discipline): the CLI imports the public
    query surface and NEVER opens graph.jsonl / imports graph internals."""
    src = _REPORT_CLI.read_text(encoding="utf-8")
    assert "from framework.objectives.query import" in src
    assert "graph.jsonl" not in src         # the row store is never opened here
    assert "from framework.objectives import graph" not in src
    assert "from framework.objectives.graph" not in src
    assert "load_beliefs" not in src        # cortex rides INSIDE the surface
