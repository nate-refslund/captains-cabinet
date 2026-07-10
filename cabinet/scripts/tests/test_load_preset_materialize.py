"""Tests for the load-preset.sh governance-twin materialize step (Perfect
Cabinet Wave B, day-1 legibility).

load-preset.sh — the ONE step both hatch.sh (step 6) and the manual runbook
path run — materializes instance/config/posture.yml + trust-ladder.yml from
their shipped .example twins ONLY when the target is absent. These tests pin:

  * bash -n syntax on load-preset.sh + emit-demo-receipt.sh;
  * materialize-when-absent (both twins land, content == the examples);
  * idempotency + NEVER-overwrite (a Captain-edited target survives re-runs
    byte-identically — the target may be schg-locked on a ruled deployment,
    so the copy must be absent-only by construction);
  * the materialized posture.yml is the consent-safe guardian default and
    schema-valid per framework.authority.posture.validation_error;
  * the materialized trust-ladder.yml parses to the conservative floor
    (a single would-like-to rung granting nothing).

Hermetic: the script runs against a scratch CABINET_ROOT fixture tree with
CABINET_RUNTIME_DIR pointed into tmp (never the live /tmp/cabinet-runtime),
no NEON_CONNECTION_STRING/DATABASE_URL (schema apply skipped), and a preset
with no agents/ dir (the Redis expected-active marking block never runs).

Run: python3.12 -m pytest cabinet/scripts/tests/test_load_preset_materialize.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_LOAD_PRESET = _SCRIPTS_DIR / "load-preset.sh"
_EMIT_DEMO = _SCRIPTS_DIR / "emit-demo-receipt.sh"

_POSTURE_EXAMPLE = _REPO_ROOT / "instance" / "config" / "posture.yml.example"
_LADDER_EXAMPLE = _REPO_ROOT / "instance" / "config" / "trust-ladder.yml.example"


def _scratch_root(tmp_path: Path) -> Path:
    """A minimal CABINET_ROOT tree load-preset.sh can run against: framework
    bases, one populated preset (NO agents/ dir -> no Redis marking), the
    active-preset selector, and the REAL shipped .example twins."""
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    (root / "framework" / "constitution-base.md").write_text(
        "# Constitution base (fixture)\n", encoding="utf-8")
    (root / "framework" / "safety-boundaries-base.md").write_text(
        "# Safety base (fixture)\n", encoding="utf-8")
    preset = root / "presets" / "work"
    preset.mkdir(parents=True)
    (preset / "preset.yml").write_text("name: work\n", encoding="utf-8")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("work\n", encoding="utf-8")
    shutil.copy(_POSTURE_EXAMPLE, cfg / "posture.yml.example")
    shutil.copy(_LADDER_EXAMPLE, cfg / "trust-ladder.yml.example")
    return root


def _run(root: Path, tmp_path: Path):
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(tmp_path / "runtime")  # never the live dir
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL",
              "CABINET_ID", "CABINET_MODE"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(_LOAD_PRESET)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Syntax — bash -n clean on both Wave-B scripts
# ---------------------------------------------------------------------------

def test_bash_syntax_clean():
    for t in (_LOAD_PRESET, _EMIT_DEMO):
        p = subprocess.run(["bash", "-n", str(t)], capture_output=True, text=True)
        assert p.returncode == 0, f"bash -n failed for {t}: {p.stderr}"


# ---------------------------------------------------------------------------
# Materialize-when-absent
# ---------------------------------------------------------------------------

def test_materializes_both_twins_when_absent(tmp_path):
    root = _scratch_root(tmp_path)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    posture = root / "instance" / "config" / "posture.yml"
    ladder = root / "instance" / "config" / "trust-ladder.yml"
    assert posture.is_file(), "posture.yml was not materialized"
    assert ladder.is_file(), "trust-ladder.yml was not materialized"
    assert posture.read_text() == _POSTURE_EXAMPLE.read_text()
    assert ladder.read_text() == _LADDER_EXAMPLE.read_text()
    assert "Materialized posture.yml" in p.stderr
    assert "Materialized trust-ladder.yml" in p.stderr


def test_missing_examples_warn_but_never_fail_the_boot(tmp_path):
    root = _scratch_root(tmp_path)
    (root / "instance" / "config" / "posture.yml.example").unlink()
    (root / "instance" / "config" / "trust-ladder.yml.example").unlink()
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr        # absent examples = safe default in code
    assert not (root / "instance" / "config" / "posture.yml").exists()
    assert "nothing to materialize" in p.stderr


# ---------------------------------------------------------------------------
# Idempotency + NEVER-overwrite (the target may be schg-locked on a ruled box)
# ---------------------------------------------------------------------------

def test_existing_targets_are_never_overwritten(tmp_path):
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    posture = root / "instance" / "config" / "posture.yml"
    ladder = root / "instance" / "config" / "trust-ladder.yml"
    # The Captain tunes both files; a re-run must leave them byte-identical.
    posture_sentinel = "# CAPTAIN-EDITED SENTINEL\nversion: 1\n"
    ladder_sentinel = "# CAPTAIN-EDITED LADDER SENTINEL\nrungs: []\n"
    posture.write_text(posture_sentinel, encoding="utf-8")
    ladder.write_text(ladder_sentinel, encoding="utf-8")
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert posture.read_text() == posture_sentinel, "posture.yml was overwritten"
    assert ladder.read_text() == ladder_sentinel, "trust-ladder.yml was overwritten"
    assert "never overwritten" in p.stderr


def test_dangling_symlink_target_is_never_written_through(tmp_path):
    """A DANGLING symlink pre-planted at posture.yml fails `-e` but must still
    count as present: cp would otherwise create the file THROUGH the link at a
    symlink-chosen destination (review nit 2026-07-10). The other twin still
    materializes normally."""
    root = _scratch_root(tmp_path)
    posture = root / "instance" / "config" / "posture.yml"
    lure = tmp_path / "elsewhere" / "lured-posture.yml"   # does not exist
    posture.symlink_to(lure)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert posture.is_symlink(), "the planted symlink must be left untouched"
    assert not lure.exists(), "nothing may be created through the symlink"
    assert not posture.exists()                            # still dangling
    assert (root / "instance" / "config" / "trust-ladder.yml").is_file()
    assert "Governance path present, untouched: posture.yml" in p.stderr


# ---------------------------------------------------------------------------
# The materialized content is the consent-safe default
# ---------------------------------------------------------------------------

def test_materialized_posture_is_schema_valid_guardian(tmp_path):
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    check = subprocess.run(
        [sys.executable, "-c",
         "import sys, yaml\n"
         "sys.path.insert(0, sys.argv[2])\n"
         "from framework.authority import posture as P\n"
         "data = yaml.safe_load(open(sys.argv[1]).read())\n"
         "err = P.validation_error(data)\n"
         "assert err is None, f'materialized posture.yml invalid: {err}'\n"
         "assert data['posture'] == 'guardian', data['posture']\n"
         "assert data['deployment'] == 'main', data['deployment']\n"
         "print('OK')\n",
         str(root / "instance" / "config" / "posture.yml"), str(_REPO_ROOT)],
        capture_output=True, text=True, timeout=60,
    )
    assert check.returncode == 0, check.stderr
    assert "OK" in check.stdout


def test_materialized_ladder_parses_to_the_floor(tmp_path):
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    check = subprocess.run(
        [sys.executable, "-c",
         "import sys\n"
         "sys.path.insert(0, sys.argv[2])\n"
         "from framework.learning import trust_ladder as T\n"
         "rungs = T.load_ladder(sys.argv[1])\n"
         "assert [r.name for r in rungs] == [T.BASE_RUNG], rungs\n"
         "assert rungs[0].grants == [], rungs[0].grants\n"
         "print('OK')\n",
         str(root), str(_REPO_ROOT)],
        capture_output=True, text=True, timeout=60,
    )
    assert check.returncode == 0, check.stderr
    assert "OK" in check.stdout
