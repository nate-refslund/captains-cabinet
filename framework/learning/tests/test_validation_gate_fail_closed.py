"""Audit #21 — the self-improvement validation gate must fail CLOSED.

Two coupled defects let auto-apply proceed with ZERO safety-shell coverage:
(1) ``_run_golden_eval_shells`` returned ``(True, [])`` when the golden-evals
dir was absent/empty — a "no shells → pass" no-op; (2) ``_validation_gate``
ran the golden shells INSIDE the try where a scenario eval's setup had
repointed ``CABINET_ROOT`` at an empty ``mkdtemp``, so the shells globbed that
empty root, found nothing, and the gate validated clean.

Pins: ``shells_run=0`` fails closed (absent OR empty dir); a real shell that
exits non-zero fails the gate; and ``_validation_gate`` restores
``CABINET_ROOT`` BEFORE the golden shells so they glob the REAL root. A MUTANT
that reverts either half turns these red.

Run: python3.12 -m pytest framework/learning/tests/test_validation_gate_fail_closed.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import framework.learning.self_improvement_loop as sil  # noqa: E402


def test_zero_shells_fails_closed(tmp_path, monkeypatch):
    """An empty OR absent golden-evals dir -> (False, shells_run=0)."""
    empty = tmp_path / "golden-evals" / "framework"
    empty.mkdir(parents=True)  # exists but has no *.sh
    monkeypatch.setattr(sil, "_golden_evals_dir", lambda: empty)
    ok, results = sil._run_golden_eval_shells()
    assert ok is False
    assert results and results[0]["shells_run"] == 0

    monkeypatch.setattr(sil, "_golden_evals_dir", lambda: tmp_path / "nope")
    ok2, results2 = sil._run_golden_eval_shells()
    assert ok2 is False and results2[0]["shells_run"] == 0


def test_present_passing_shell_runs_green(tmp_path, monkeypatch):
    gdir = tmp_path / "golden-evals" / "framework"
    gdir.mkdir(parents=True)
    (gdir / "ok.sh").write_text("#!/bin/bash\nexit 0\n")
    monkeypatch.setattr(sil, "_golden_evals_dir", lambda: gdir)
    ok, results = sil._run_golden_eval_shells()
    assert ok is True
    assert any(r.get("script") == "ok.sh" and r["passed"] for r in results)


def test_red_shell_fails_gate(tmp_path, monkeypatch):
    """MUTANT teeth: a genuinely broken safety shell must fail the gate."""
    gdir = tmp_path / "golden-evals" / "framework"
    gdir.mkdir(parents=True)
    (gdir / "broken.sh").write_text("#!/bin/bash\nexit 1\n")
    monkeypatch.setattr(sil, "_golden_evals_dir", lambda: gdir)
    ok, results = sil._run_golden_eval_shells()
    assert ok is False
    assert any(r.get("script") == "broken.sh" and not r["passed"] for r in results)


def test_validation_gate_restores_env_before_golden_shells(tmp_path, monkeypatch):
    """The gate must restore CABINET_ROOT BEFORE running the golden shells, so
    a scenario eval that repointed CABINET_ROOT at an empty temp can't make the
    shells glob the wrong (empty) root and validate vacuously."""
    real_root = str(tmp_path / "real-root")
    monkeypatch.setenv("CABINET_ROOT", real_root)
    leaked = str(tmp_path / "leaked-temp")

    def fake_scenarios():
        # a scenario setup repoints CABINET_ROOT and (as the real ones do)
        # leaves it mutated on return
        os.environ["CABINET_ROOT"] = leaked
        return True, []

    seen: dict = {}

    def fake_golden():
        seen["root"] = os.environ.get("CABINET_ROOT")
        return True, [{"script": "x", "passed": True}]

    monkeypatch.setattr(sil, "_run_scenario_evals_for_validation", fake_scenarios)
    monkeypatch.setattr(sil, "_run_golden_eval_shells", fake_golden)

    ok, detail = sil._validation_gate()
    assert seen["root"] == real_root, (
        "golden shells ran against the scenario's leaked CABINET_ROOT — env "
        "was not restored before the shells (audit #21)")
    assert os.environ.get("CABINET_ROOT") == real_root  # gate leaves env clean
    assert ok is True


def test_validation_gate_blocks_on_zero_shells(tmp_path, monkeypatch):
    """End-to-end: scenarios pass, but an empty golden dir -> gate False."""
    monkeypatch.setattr(sil, "_run_scenario_evals_for_validation",
                        lambda: (True, []))
    empty = tmp_path / "golden-evals" / "framework"
    empty.mkdir(parents=True)
    monkeypatch.setattr(sil, "_golden_evals_dir", lambda: empty)
    ok, detail = sil._validation_gate()
    assert ok is False
    assert detail["golden_passed"] is False
