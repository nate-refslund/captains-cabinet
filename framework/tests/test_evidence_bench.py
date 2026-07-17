"""evidence-bench harness tests (Evidence Phase 2 Batch A, G3).

The bench (cabinet/scripts/evidence-bench.py) measures the recorder's
envelope — p95 append latency vs trial length (the O(n^2) whole-trial
re-verify per append), bytes/event growth, per-trial event-count
distribution, the store-wide watermark axis — and computes the recommended
enforced per-trial event cap. These tests pin its safety contract:

  * scratch-store only — it creates its own tempdir store, refuses anything
    resolving into instance/evidence or the recorder's default home, and
    cleans up after itself;
  * the CABINET_EVIDENCE_DIR env seam is never consulted (explicit store
    root always; a decoy env path stays untouched);
  * everything it writes verifies — the scratch store passes verify_store,
    so the harness itself proves it uses the sanctioned append API correctly.

House interpreter: python3.12 (CI runs `pytest framework/`).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from framework.evidence.recorder import TRIAL_CLASS_RE
from framework.evidence.verifier import verify_store

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_PATH = REPO_ROOT / "cabinet" / "scripts" / "evidence-bench.py"

_spec = importlib.util.spec_from_file_location("evidence_bench", BENCH_PATH)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

SMALL = dict(
    journeys=2,
    mirror_events=10,
    consequence_events=4,
    sweep_len=16,
    watermark_trials=6,
)
SMALL_TOTAL = 2 * 8 + 10 + 4 + 16 + 6


def test_small_run_report_shape_and_cleanup(tmp_path, monkeypatch):
    decoy = tmp_path / "decoy-live-store"
    monkeypatch.setenv("CABINET_EVIDENCE_DIR", str(decoy))
    report = bench.run_bench(base_dir=tmp_path, **SMALL)

    assert report["schema"] == "cabinet.evidence-bench-report/v1"
    assert report["events_total"] == SMALL_TOTAL
    overall = report["append_latency_ms"]["overall"]
    assert overall["n"] == SMALL_TOTAL
    assert 0 < overall["p50_ms"] <= overall["p95_ms"] <= overall["max_ms"]
    for shape in ("journey", "mirror", "consequence", "sweep", "watermark_axis"):
        assert report["append_latency_ms"]["by_shape"][shape]["n"] > 0
    assert report["sweep_latency_by_bucket"], "sweep buckets missing"
    for key in ("journey", "mirror", "sweep"):
        assert report["growth"]["bytes_per_event"][key] > 0
    assert report["growth"]["projections"], "growth projections missing"
    counts = report["per_trial_event_counts"]
    assert counts["journey"] == {"n": 2, "min": 8, "mean": 8.0, "p95": 8, "max": 8}
    assert counts["mirror_day"]["max"] == 10

    # everything the bench wrote verified before cleanup
    assert report["store"]["verify_store_ok"] is True
    # scratch store lived under base_dir and was removed (keep_store=False)
    assert report["store"]["root"].startswith(str(tmp_path))
    assert not Path(report["store"]["root"]).exists()
    # the env decoy was never consulted or created (A10: explicit root only)
    assert not decoy.exists()

    # JSON-serializable end to end
    json.dumps(report)


def test_cap_recommendation_has_measured_basis(tmp_path):
    report = bench.run_bench(base_dir=tmp_path, **SMALL)
    cap = report["cap_recommendation"]
    assert cap["recommended_max_trial_events"] in bench.CAP_CANDIDATES
    worst = cap["worst_simulated_day_trial_events"]
    assert worst == max(SMALL["mirror_events"], SMALL["consequence_events"])
    assert cap["recommended_max_trial_events"] >= worst * cap["headroom_factor"]
    assert cap["p95_append_ms_at_measured_depth"] > 0
    assert isinstance(cap["latency_within_budget"], bool)


def test_keep_store_verifies_and_uses_day_bounded_taxonomy(tmp_path):
    report = bench.run_bench(base_dir=tmp_path, keep_store=True, **SMALL)
    root = Path(report["store"]["root"])
    assert root.exists() and report["store"]["kept"] is True

    result = verify_store(root)
    assert result["ok"] is True
    assert result["trial_count"] == report["store"]["verify_store_trials"]

    trial_names = sorted(p.name for p in (root / "trials").iterdir() if p.is_dir())
    taxonomy = [name for name in trial_names if TRIAL_CLASS_RE.fullmatch(name)]
    # mirror + consequence + sweep + watermark trials are all day-bounded
    assert len(taxonomy) == 2 + 1 + SMALL["watermark_trials"]
    mirror = [n for n in taxonomy if n.startswith("evt-benchorgmirror-")]
    assert len(mirror) == 1
    ledger = root / "trials" / mirror[0] / "events.jsonl"
    lines = [line for line in ledger.read_text(encoding="utf-8").split("\n") if line.strip()]
    assert len(lines) == SMALL["mirror_events"]
    # fixed producer identity, never payload-derived
    row = json.loads(lines[0])
    assert row["actor"] == {"kind": "system", "id": "evidence-bench"}
    assert row["component"]["name"] == "evidence-bench"


def test_refuse_live_guard():
    with pytest.raises(ValueError):
        bench._refuse_live(Path("/anything/instance/evidence/v1"))
    with pytest.raises(ValueError):
        bench._refuse_live(
            Path("~/Library/Application Support/cabinet/evidence/v1").expanduser()
        )
    # a scratch path is fine
    bench._refuse_live(Path("/tmp"))


def test_cli_main_writes_report(tmp_path):
    out = tmp_path / "report.json"
    rc = bench.main([
        "--journeys", "1",
        "--mirror-events", "4",
        "--consequence-events", "2",
        "--sweep-len", "8",
        "--watermark-trials", "2",
        "--base-dir", str(tmp_path),
        "--output", str(out),
    ])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "cabinet.evidence-bench-report/v1"
    assert report["events_total"] == 1 * 8 + 4 + 2 + 8 + 2
    assert report["store"]["verify_store_ok"] is True
