"""Contract tests for deploy-mac.sh --stop (Wave D / D2 — DESIGN-companion-2026-07-10 §3/§11).

--stop acts on RUNTIME truth: the com.cabinet.*.plist files actually installed
in ~/Library/LaunchAgents — never services.yml or the roster (drift-immune,
companion spec OC-6). It reuses the deploy leg's idempotent bootout primitive
and NEVER bootstraps; plist files stay on disk so a redeploy restarts things.

Hermetic by construction: every run points HOME at a pytest tmp dir seeded
with fake plists, and only the --dry-run and refusal paths execute — the
refusal paths exit before any launchctl invocation, so no real launchd state
is ever read or touched (same read-only posture as the sibling script tests).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "deploy-mac.sh"


def _run(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HOME": str(home),
        # pin BOTH root spellings so an ambient CABINET_SOURCE_REPO can never
        # redirect the script at a different checkout
        "CABINET_ROOT": str(REPO),
        "CABINET_SOURCE_REPO": str(REPO),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    la = tmp_path / "Library" / "LaunchAgents"
    la.mkdir(parents=True)
    (la / "com.cabinet.officer.cos.plist").write_text("<plist/>\n")
    (la / "com.cabinet.dashboard.plist").write_text("<plist/>\n")
    # non-cabinet agent: --stop all must never touch it
    (la / "com.other.vendor.plist").write_text("<plist/>\n")
    return tmp_path


def test_stop_all_dry_run_prints_bootout_only_plan(fake_home: Path):
    proc = _run(["--stop", "all", "--dry-run"], fake_home)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "=== WOULD-BOOTOUT com.cabinet.dashboard ===" in out
    assert "=== WOULD-BOOTOUT com.cabinet.officer.cos ===" in out
    # runtime-truth scope: only com.cabinet.* is enumerated
    assert "com.other.vendor" not in out + proc.stderr
    # bootout-ONLY plan: --stop never bootstraps, never writes plists
    combined = (out + proc.stderr).lower()
    assert "bootstrap" not in combined, "--stop must never bootstrap"
    assert "would-write" not in combined
    assert "deployed:" not in combined


def test_stop_single_name_resolves_both_plist_spellings(fake_home: Path):
    daemon = _run(["--stop", "dashboard", "--dry-run"], fake_home)
    assert daemon.returncode == 0, daemon.stderr
    assert "=== WOULD-BOOTOUT com.cabinet.dashboard ===" in daemon.stdout

    officer = _run(["--stop", "cos", "--dry-run"], fake_home)
    assert officer.returncode == 0, officer.stderr
    assert "=== WOULD-BOOTOUT com.cabinet.officer.cos ===" in officer.stdout
    # exactly one target per single-name stop
    assert officer.stdout.count("WOULD-BOOTOUT") == 1


def test_stop_unknown_name_exits_nonzero_before_any_action(fake_home: Path):
    # real (non-dry) run: the refusal exits before any launchctl call
    proc = _run(["--stop", "definitely-not-installed"], fake_home)
    assert proc.returncode == 2
    assert "definitely-not-installed" in proc.stderr
    assert "nothing was changed" in proc.stderr
    assert "stopped:" not in proc.stdout


def test_stop_all_with_nothing_installed_is_honest_noop(tmp_path: Path):
    proc = _run(["--stop", "all", "--dry-run"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "nothing to stop" in proc.stdout
    assert "WOULD-BOOTOUT" not in proc.stdout


def test_stop_refuses_deploy_selector_combos(fake_home: Path):
    for combo in (["--stop", "all", "--all"],
                  ["--stop", "all", "--officer", "cos"],
                  ["--stop", "all", "--daemon", "dashboard"]):
        proc = _run(combo, fake_home)
        assert proc.returncode == 64, combo
        assert "--stop cannot be combined" in proc.stderr, combo


def test_stop_leg_source_never_calls_bootstrap():
    """Source pin for the never-bootstraps contract: the stop functions must
    not reference launchctl bootstrap or the deploy_plist writer."""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("stop_one()")
    end = text.index('if [ "$ALL" = true ]; then')
    stop_leg = text[start:end]
    assert "bootstrap" not in stop_leg
    assert "deploy_plist" not in stop_leg
    assert "launchctl bootout" in stop_leg
