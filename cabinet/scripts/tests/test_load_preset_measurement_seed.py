"""Audit #27 — load-preset.sh installs the measurement corpus seed.

The measurement runners discover ``instance/measurement/{role_evals,scenarios}``
(see framework/measurement/tests/test_measurement_seed.py for the discovery
half); load-preset.sh is the ONE step that copies the active preset's
measurement seed there. Before the fix nothing installed it, so the framework
dir stayed empty and the role-eval runner + scenario safety-gate were dead
sensors.

Pins: a preset carrying ``measurement/{role_evals,scenarios}`` lands both under
``instance/measurement/`` (idempotent on re-run); a preset with NO measurement
dir is a clean no-op (boot never fails). Hermetic scratch CABINET_ROOT,
mirroring test_load_preset_materialize.py.

Run: python3.12 -m pytest cabinet/scripts/tests/test_load_preset_measurement_seed.py -q
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_LOAD_PRESET = _SCRIPTS_DIR / "load-preset.sh"
_POSTURE_EXAMPLE = _REPO_ROOT / "instance" / "config" / "posture.yml.example"
_LADDER_EXAMPLE = _REPO_ROOT / "instance" / "config" / "trust-ladder.yml.example"


def _scratch_root(tmp_path: Path, with_measurement: bool = True) -> Path:
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    (root / "framework" / "constitution-base.md").write_text("# base\n")
    (root / "framework" / "safety-boundaries-base.md").write_text("# base\n")
    preset = root / "presets" / "work"
    preset.mkdir(parents=True)
    (preset / "preset.yml").write_text("name: work\n")
    if with_measurement:
        for kind in ("role_evals", "scenarios"):
            d = preset / "measurement" / kind
            d.mkdir(parents=True)
            (d / "probe.py").write_text("# seed probe\n")
            (d / "__init__.py").write_text("")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("work\n")
    shutil.copy(_POSTURE_EXAMPLE, cfg / "posture.yml.example")
    shutil.copy(_LADDER_EXAMPLE, cfg / "trust-ladder.yml.example")
    return root


def _run(root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(tmp_path / "runtime")
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL", "CABINET_ID", "CABINET_MODE"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(_LOAD_PRESET)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_measurement_seed_installed_from_preset(tmp_path):
    root = _scratch_root(tmp_path)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    for kind in ("role_evals", "scenarios"):
        dst = root / "instance" / "measurement" / kind / "probe.py"
        assert dst.is_file(), f"{kind} seed not installed:\n{p.stderr}"
    assert "Seeded measurement/role_evals" in p.stderr
    assert "Seeded measurement/scenarios" in p.stderr


def test_measurement_seed_is_idempotent(tmp_path):
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    p = _run(root, tmp_path)  # re-run
    assert p.returncode == 0, p.stderr
    for kind in ("role_evals", "scenarios"):
        assert (root / "instance" / "measurement" / kind / "probe.py").is_file()


def test_preset_without_measurement_is_clean_noop(tmp_path):
    root = _scratch_root(tmp_path, with_measurement=False)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert not (root / "instance" / "measurement").exists()
    assert "Seeded measurement" not in p.stderr
