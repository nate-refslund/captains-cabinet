"""Rec 3.4 (2026-07-09) — per-model golden-eval scalar series.

The eval BODIES in memory/golden-evals/ are germline-locked; the runner
script is not. These tests exercise the sourceable emission lib directly
(the full suite toggles the live killswitch and cannot run under pytest)
and pin the runner's wiring statically:

  * golden_scalar_emit appends {ts, date, model, pass, fail, skip, scalar}
    with scalar = pass/(pass+fail), null when nothing scored — an honest
    unmeasured, never a fake 0;
  * append-only (two runs = two lines), model id carried verbatim
    (brackets and all — 'claude-opus-4-8[1m]' is the fleet default);
  * non-numeric counts refuse loudly (return 1 + stderr WARN) without
    touching the series;
  * runner wiring: --model / CABINET_EVAL_MODEL parametrization, the lib
    source line, the emit call, and the REPORT-ONLY / defer-captain note
    (the scalar must never become a gate without a Captain ruling).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_LIB = _REPO / "cabinet" / "scripts" / "lib" / "golden-scalar.sh"
_RUNNER = _REPO / "cabinet" / "scripts" / "run-golden-evals.sh"


def _emit(*args: str) -> subprocess.CompletedProcess:
    quoted = " ".join(f"'{a}'" for a in args)
    return subprocess.run(
        ["bash", "-c", f"source '{_LIB}' && golden_scalar_emit {quoted}"],
        capture_output=True, text=True, timeout=15)


class TestEmit:
    def test_appends_scalar_line(self, tmp_path):
        series = tmp_path / "s.jsonl"
        r = _emit("claude-opus-4-8[1m]", "40", "2", "1", str(series))
        assert r.returncode == 0
        row = json.loads(series.read_text())
        assert row["model"] == "claude-opus-4-8[1m]"   # verbatim, brackets kept
        assert row["pass"] == 40 and row["fail"] == 2 and row["skip"] == 1
        assert row["scalar"] == 0.9524
        assert row["date"] and row["ts"]

    def test_nothing_scored_is_null_not_zero(self, tmp_path):
        series = tmp_path / "s.jsonl"
        _emit("m", "0", "0", "3", str(series))
        assert json.loads(series.read_text())["scalar"] is None

    def test_append_only_two_runs_two_lines(self, tmp_path):
        series = tmp_path / "s.jsonl"
        _emit("m1", "1", "0", "0", str(series))
        _emit("m2", "2", "0", "0", str(series))
        rows = [json.loads(l) for l in series.read_text().splitlines()]
        assert [r["model"] for r in rows] == ["m1", "m2"]

    def test_non_numeric_counts_refuse_loudly(self, tmp_path):
        series = tmp_path / "s.jsonl"
        r = _emit("m", "40; rm -rf /", "0", "0", str(series))
        assert r.returncode != 0
        assert "WARN" in r.stderr
        assert not series.exists()          # series untouched

    def test_creates_parent_dir(self, tmp_path):
        series = tmp_path / "deep" / "nested" / "s.jsonl"
        assert _emit("m", "1", "0", "0", str(series)).returncode == 0
        assert series.exists()


class TestRunnerWiring:
    def test_runner_parses_model_and_sources_lib(self):
        text = _RUNNER.read_text()
        assert "--model" in text
        assert "CABINET_EVAL_MODEL" in text
        assert "golden-scalar.sh" in text
        assert "golden_scalar_emit" in text
        assert "GOLDEN_SCALAR_SERIES" in text

    def test_report_only_defer_captain_note_present(self):
        # the scalar must not silently become promotion mechanics
        assert "defer-captain" in _RUNNER.read_text()
        assert "defer-captain" in _LIB.read_text()

    def test_runner_and_lib_are_valid_bash(self):
        for f in (_RUNNER, _LIB):
            r = subprocess.run(["bash", "-n", str(f)],
                               capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
