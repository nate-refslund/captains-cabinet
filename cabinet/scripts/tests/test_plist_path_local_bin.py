"""Officer plists can find the native-installer `claude` (fresh-hatch #60).

Claude Code's official native installer puts `claude` at ~/.local/bin/claude.
launchd does NOT expand $HOME, and the baked EnvironmentVariables.PATH
(generate-plists.py PATH_ENV) is a FIXED captain-agnostic ABSOLUTE literal that
is cross-pinned to the dependency-radar registry (which requires absolute
dirs) — so ~/.local/bin must NOT be baked into PATH_ENV. Instead the officer
WRAPPER prepends `$HOME/.local/bin` to PATH, where bash expands $HOME at boot.

Pins:
  * PATH_ENV stays a fixed absolute literal (no ~, no $HOME) — this is what
    keeps the dependency-radar cross-pin honest; and every segment is absolute;
  * every rendered plist's wrapper prepends $HOME/.local/bin to PATH before it
    execs the officer command — so `claude` resolves at boot.

Run: python3.12 -m pytest cabinet/scripts/tests/test_plist_path_local_bin.py -q
"""
from __future__ import annotations

import importlib.util
import os
import plistlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "cabinet" / "scripts" / "generate-plists.py"


def _load_module():
    # generate-plists.py guards its CLI behind `if __name__ == "__main__"`, so
    # importing it for the constant is side-effect-free (no plists written).
    spec = importlib.util.spec_from_file_location("generate_plists_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_path_env_stays_a_fixed_absolute_captain_agnostic_literal():
    mod = _load_module()
    # ~/.local/bin (per-user) must NOT be baked into the launchd literal — that
    # would drift the dependency-radar absolute-dirs cross-pin.
    assert "~" not in mod.PATH_ENV and "$HOME" not in mod.PATH_ENV, mod.PATH_ENV
    assert all(seg.startswith("/") for seg in mod.PATH_ENV.split(":") if seg), (
        f"every PATH_ENV segment must be absolute (radar cross-pin): {mod.PATH_ENV!r}")
    assert "/opt/homebrew/bin" in mod.PATH_ENV, mod.PATH_ENV


def test_rendered_plist_wrappers_prepend_local_bin(tmp_path):
    out = tmp_path / "out"
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(out)],
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    plists = sorted(out.glob("*.plist"))
    assert plists, f"no plists rendered:\n{proc.stdout}\n{proc.stderr}"
    for p in plists:
        with open(p, "rb") as fh:
            pl = plistlib.load(fh)
        args = pl.get("ProgramArguments", [])
        wrapper = args[-1] if args else ""
        # bash expands $HOME at boot -> the officer's runtime PATH leads with
        # ~/.local/bin, so native-installer `claude` resolves.
        assert 'export PATH="$HOME/.local/bin:$PATH"' in wrapper, (
            f"{p.name} wrapper does not prepend ~/.local/bin: {wrapper!r}")


def test_baked_launchd_path_is_unchanged_literal(tmp_path):
    # The EnvironmentVariables.PATH launchd actually sets stays the captain-
    # agnostic literal (belt-and-suspenders on the cross-pin): no ~ leaks in.
    mod = _load_module()
    out = tmp_path / "out"
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(out)],
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    for p in sorted(out.glob("*.plist")):
        with open(p, "rb") as fh:
            pl = plistlib.load(fh)
        assert pl.get("EnvironmentVariables", {}).get("PATH") == mod.PATH_ENV, p.name
