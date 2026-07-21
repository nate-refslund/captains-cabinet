"""Tests for the killswitch send-path eval harness (EVAL-002) + its wiring.

The harness is the mechanical PASS/FAIL law for the KILLSWITCH SEND-PATH golden
eval (body: memory/golden-evals/eval-002-killswitch-send-path.md): when the
Captain's emergency stop is armed OR the control plane is unreachable, every
front-door send is refused (fail-closed), and the front door reuses the one
SEC-3 killswitch reader. These tests pin:
  * the shipped harness self-test exits 0 (exactly what the golden-eval runner
    invokes on every master push);
  * teeth — defeating the channel gate makes the harness exit non-zero;
  * the PAIRING: eval body + harness + runner section stay wired (an eval
    silently unplugged from run-golden-evals.sh is itself a failure).
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS = REPO_ROOT / "cabinet" / "evals" / "killswitch-send" / "harness.py"
BODY = REPO_ROOT / "memory" / "golden-evals" / "eval-002-killswitch-send-path.md"
RUNNER = REPO_ROOT / "cabinet" / "scripts" / "run-golden-evals.sh"

spec = importlib.util.spec_from_file_location("killswitch_send_harness", HARNESS)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_shipped_harness_self_test_is_green():
    """What the runner invokes: `harness.py --self-test` exits 0 and reports PASS."""
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "--self-test", "--repo-root", str(REPO_ROOT)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"harness RED:\n{proc.stdout}\n{proc.stderr}"
    assert "KILLSWITCH-SEND-EVAL: PASS" in proc.stdout


def test_harness_has_teeth_when_gate_defeated(monkeypatch):
    """If the channel gate is neutralized, the harness must FAIL (exit non-zero)
    — proof the eval actually exercises the gate rather than passing vacuously."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import framework.frontdoor.channel as channel
    monkeypatch.setattr(channel, "_killswitch_halted", lambda: None)
    assert harness.run_self_test(REPO_ROOT) == 1


def test_eval_body_present():
    assert BODY.is_file(), f"eval body missing at {BODY}"
    text = BODY.read_text()
    assert "Kill Switch" in text and "front-door" in text.lower()


def test_pairing_body_harness_and_runner_stay_wired():
    """Body + harness + runner section are all present and cross-referenced."""
    assert HARNESS.is_file()
    assert BODY.is_file()
    runner = RUNNER.read_text()
    assert "EVAL-002-KILLSWITCH-SEND" in runner, "runner section unplugged"
    assert "cabinet/evals/killswitch-send/harness.py" in runner, "runner does not invoke the harness"
    assert "KILLSWITCH-SEND-EVAL:" in runner, "runner does not parse the harness summary"
