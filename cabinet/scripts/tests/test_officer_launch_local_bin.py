"""Audit #60 — the officer launcher must carry ~/.local/bin in the officer PATH.

start-officer-mac.sh starts each officer via
``tmux new-session ... /usr/bin/env -i ... PATH="..."``. ``env -i`` scrubs the
environment, so PATH must explicitly include ~/.local/bin: Claude Code's native
installer puts ``claude`` there and launchd's baked service PATH (which the
launcher inherits when itself run under a plist) omits it. Without it the officer
boots and then fails at move-in because it cannot find ``claude``.

The daemon PLISTS fix this in their own wrapper
(test_plist_path_local_bin.py); this is the OFFICER-launch twin. A mutant that
drops ``$HOME/.local/bin:`` from the launch PATH turns this red.

Run: python3.12 -m pytest cabinet/scripts/tests/test_officer_launch_local_bin.py -q
"""
from __future__ import annotations

from pathlib import Path

_LAUNCHER = Path(__file__).resolve().parent.parent / "start-officer-mac.sh"


def test_officer_env_prepends_local_bin() -> None:
    src = _LAUNCHER.read_text()
    launch_lines = [ln for ln in src.splitlines() if "/usr/bin/env -i" in ln]
    assert launch_lines, "no `/usr/bin/env -i` officer launch line in start-officer-mac.sh"
    assert any('PATH="$HOME/.local/bin:$PATH"' in ln for ln in launch_lines), (
        "the officer `env -i` launch PATH must PREPEND ~/.local/bin so the "
        "native-installer `claude` resolves under launchd's minimal service "
        "PATH (audit #60); found: "
        + "; ".join(ln.strip() for ln in launch_lines))
