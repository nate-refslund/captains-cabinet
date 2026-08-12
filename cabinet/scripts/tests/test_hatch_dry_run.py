"""Tests for cabinet/scripts/hatch.sh (v0 — the thin hatch orchestrator).

hatch.sh ORCHESTRATES the rehearsed chain and reimplements nothing
(docs/plans/world-onboarding-hatching-2026-07-09.md §7.3); these tests pin
the v0 acceptance surface WITHOUT running the chain: syntax, --help,
--dry-run plan fidelity (executes nothing, exits 0), flag conflicts, and
the germline discipline (errand notes instead of writes).

Run: python3.12 -m pytest cabinet/scripts/tests/test_hatch_dry_run.py -q
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_HATCH = _SCRIPTS_DIR / "hatch.sh"
_LIB_DIR = _SCRIPTS_DIR / "hatch-lib"


def _run(args, home: Path | None = None):
    env = dict(os.environ)
    # pin the clean-room port assert against ambient overrides
    env.pop("HATCH_CLEANROOM_REDIS_PORT", None)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(_HATCH), *args],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Syntax — bash -n clean on the orchestrator and every lib file
# ---------------------------------------------------------------------------

def test_bash_syntax_clean():
    targets = [_HATCH, *sorted(_LIB_DIR.glob("*.sh"))]
    assert len(targets) >= 3, "expected hatch.sh + at least two hatch-lib files"
    for t in targets:
        p = subprocess.run(["bash", "-n", str(t)], capture_output=True, text=True)
        assert p.returncode == 0, f"bash -n failed for {t}: {p.stderr}"


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------

def test_help_exits_zero_and_documents_flags():
    p = _run(["--help"])
    assert p.returncode == 0, p.stderr
    for flag in ("--defaults", "--clean-room", "--dry-run", "--with-launchd",
                 "--with-drill", "--flight-log"):
        assert flag in p.stdout, f"--help does not document {flag}"


# ---------------------------------------------------------------------------
# --dry-run: full plan, errand notes, zero execution, exit 0
# ---------------------------------------------------------------------------

def test_dry_run_defaults_prints_plan_and_exits_zero(tmp_path):
    p = _run(["--dry-run", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    # the chain, in runbook order
    assert "HATCH PLAN v0" in out
    assert "setup-mac.sh --fast" in out
    assert "generate-instance.py --defaults" in out
    assert "--adopt" in out  # the rehearsed adoption path is in the plan
    assert "bootstrap-roles.sh --roster instance/config/roster.yml" in out
    assert "load-preset.sh" in out
    assert "null-hatch.sh" in out
    assert "test_no_screenpipe_in_core.py" in out
    assert "start-officer-mac.sh cos --dry-run" in out
    assert "deploy-mac.sh --officer cos --dry-run" in out
    assert "first-briefing.sh --local" in out
    # Wave B: the demo-receipt step rides the plan right after the first receipt
    assert "emit-demo-receipt.sh" in out
    assert out.index("first-briefing.sh --local") < out.index("emit-demo-receipt.sh")
    # flight-recorder stamps are part of the printed plan
    assert "HATCH_PROOFS_DONE" in out
    assert "FIRST_RECEIPT_DONE" in out
    assert "TTFR" in out
    # the human-only checklist is present and numbered, in plain words
    # (renamed from "ERRAND NOTES" 2026-08-12 — nobody double-clicking an app
    # knows what an errand note is)
    assert "YOUR CHECKLIST" in out
    assert "\n  1. " in out, "the checklist must number its items"
    assert "ERRAND" not in out, (
        "the operator-facing copy must not carry this codebase's vocabulary"
    )
    assert "mcp-scope.yml" in out
    assert "officer-capabilities.conf" in out
    # v0 default: move-in deferred, not run
    assert "DEFERRED" in out
    assert "nothing was executed" in out


def test_dry_run_executes_nothing(tmp_path):
    """No log dir, no writes — dry-run with a redirected HOME leaves it empty."""
    p = _run(["--dry-run", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert list(tmp_path.iterdir()) == [], "dry-run must create nothing under HOME"


def test_dry_run_clean_room_swaps_setup_and_redis(tmp_path):
    p = _run(["--dry-run", "--clean-room", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "setup-mac.sh --check" in p.stdout
    assert "setup-mac.sh --fast" not in p.stdout
    assert "REDIS_PORT=6399" in p.stdout  # load-preset marks -> unused port


def test_dry_run_with_drill_and_launchd_in_plan(tmp_path):
    p = _run(["--dry-run", "--defaults", "--with-drill", "--with-launchd"],
             home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "kill-switch drill" in p.stdout
    assert "generate-plists.py" in p.stdout
    assert "health-check.sh" in p.stdout
    # the move-in plan advertises the idempotent bootout-first idiom
    assert "bootout" in p.stdout


# ---------------------------------------------------------------------------
# Flag discipline — repo convention: usage errors exit 64
# ---------------------------------------------------------------------------

def test_unknown_flag_exits_64():
    p = _run(["--bogus"])
    assert p.returncode == 64
    assert "unknown flag" in p.stderr


def test_clean_room_refuses_launchd_and_drill():
    for combo in (["--clean-room", "--with-launchd"],
                  ["--clean-room", "--with-drill"]):
        p = _run(combo)
        assert p.returncode == 64, f"{combo} should exit 64"
        assert "refuses" in p.stderr


# ---------------------------------------------------------------------------
# Auto-adopt trigger — do_generate_instance greps the step log for the
# generator's refusal cue. Pin (a) both sides of that wording contract so
# drift breaks loudly, and (b) that the cue discriminates a real refusal
# from argparse usage noise (a failing run whose log is only usage/errors
# must NOT trigger adoption).
# ---------------------------------------------------------------------------

_ADOPT_CUE = "REFUSING to overwrite"


def test_adopt_cue_pins_the_generator_wording_contract():
    hatch_text = _HATCH.read_text(encoding="utf-8")
    grep_lines = [
        ln for ln in hatch_text.splitlines()
        if "grep" in ln and _ADOPT_CUE in ln
    ]
    assert grep_lines, f"hatch.sh no longer greps the adopt cue {_ADOPT_CUE!r}"
    gen_text = (_SCRIPTS_DIR / "generate-instance.py").read_text(encoding="utf-8")
    assert _ADOPT_CUE in gen_text, (
        "generate-instance.py no longer emits the adopt cue — update the "
        "hatch.sh auto-adopt trigger to the generator's new refusal wording"
    )


def test_adopt_cue_ignores_argparse_usage_noise(tmp_path):
    noise = tmp_path / "step-gen-noise.log"
    noise.write_text(
        "usage: generate-instance.py [-h] [--defaults] [--adopt]\n"
        "generate-instance.py: error: unrecognized arguments: --bogus\n",
        encoding="utf-8",
    )
    refusal = tmp_path / "step-gen-refusal.log"
    refusal.write_text(
        "REFUSING to overwrite instance/config/platform.yml: it already has "
        "an org definition.\n",
        encoding="utf-8",
    )
    gate = lambda log: subprocess.run(  # noqa: E731 — the exact gate idiom
        ["grep", "-q", _ADOPT_CUE, str(log)], capture_output=True
    ).returncode
    assert gate(noise) != 0, "usage noise must not trigger auto-adopt"
    assert gate(refusal) == 0, "a real refusal must trigger auto-adopt"


# ---------------------------------------------------------------------------
# Germline discipline — hatch.sh never writes germline files; it prints
# errand notes. Pin the absence of write constructs against those paths.
# ---------------------------------------------------------------------------

def test_no_germline_write_constructs():
    text = _HATCH.read_text(encoding="utf-8")
    for lib in sorted(_LIB_DIR.glob("*.sh")):
        text += lib.read_text(encoding="utf-8")
    for germ in ("mcp-scope.yml", "officer-capabilities.conf"):
        for line in text.splitlines():
            if germ in line:
                # mentions must be prose/errand lines, never redirections or
                # copies into the germline path
                assert f"> cabinet/{germ}" not in line
                assert f">> cabinet/{germ}" not in line
                assert not line.strip().startswith(("cp ", "mv ", "tee ")), (
                    f"germline file {germ} appears in a write position: {line!r}"
                )
