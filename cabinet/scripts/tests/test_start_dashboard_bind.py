"""Tests for start-dashboard.sh port/bind config (Wave D app-feel, D4).

D4a (the shipped fix): CABINET_DASHBOARD_PORT used to be resolved BEFORE the
`set -a` cabinet/.env sourcing, so a port in cabinet/.env was silently
ignored; naively moving the resolution below the sourcing would flip
precedence the other way (.env would override the launchd plist env). The
fix captures explicit-env values FIRST and composes after the sourcing:
explicit env (launchd plist) > cabinet/.env > default. Same commit lands the
CABINET_DASHBOARD_HOST plumbing with the DEFAULT KEPT at 0.0.0.0 (current
all-interfaces behavior — the live box is reached over Tailscale); flipping
the default to loopback is captain-gated (CC-LOOP / OC-LOOPBACK).

Pins: wiring order (capture before sourcing, composition after), the exact
composition literals incl. the 0.0.0.0 default, the 127.0.0.1 echo origin,
the --hostname plumbing on the exec line, a FUNCTIONAL precedence probe
(scratch CABINET_ROOT + npm shim — the real script runs end-to-end, no
server started), and the program-wide dead-name gate: the two retired
spellings of the bind var (the *_BIND / *_HOSTNAME variants — see
_DEAD_NAMES below, built from split strings so this file can never trip the
gate itself) appear nowhere under cabinet/scripts, cabinet/docs,
docs/runbooks.

Run: python3.12 -m pytest cabinet/scripts/tests/test_start_dashboard_bind.py -q
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_SCRIPT = _SCRIPTS_DIR / "start-dashboard.sh"

_CAPTURE_PORT = 'ENV_DASH_PORT="${CABINET_DASHBOARD_PORT:-}"'
_CAPTURE_HOST = 'ENV_DASH_HOST="${CABINET_DASHBOARD_HOST:-}"'
_COMPOSE_PORT = 'PORT="${ENV_DASH_PORT:-${CABINET_DASHBOARD_PORT:-3100}}"'
_COMPOSE_HOST = 'HOST="${ENV_DASH_HOST:-${CABINET_DASHBOARD_HOST:-0.0.0.0}}"'
_EXEC_LINE = 'exec npm start -- --port "$PORT" --hostname "$HOST"'

# Built from fragments so the dead-name gate (and the program-wide
# acceptance grep) can never match THIS file's own source.
_DEAD_NAMES = ["CABINET_DASHBOARD_" + "BIND", "CABINET_DASHBOARD_" + "HOSTNAME"]


def test_bash_syntax_clean():
    p = subprocess.run(["bash", "-n", str(_SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, f"bash -n failed: {p.stderr}"


# ---------------------------------------------------------------------------
# Wiring — capture before the .env sourcing, composition after it
# ---------------------------------------------------------------------------

def test_capture_before_sourcing_and_composition_after():
    text = _SCRIPT.read_text(encoding="utf-8")
    # anchor the sourcing CONSTRUCT (indented statements), not prose mentions
    sourcing_open = text.index("\n  set -a\n")
    sourcing_close = text.index("\n  set +a\n")
    for literal in (_CAPTURE_PORT, _CAPTURE_HOST):
        assert literal in text, f"missing capture line: {literal}"
        assert text.index(literal) < sourcing_open, (
            f"{literal} must run BEFORE the cabinet/.env sourcing — set -a "
            "overwrites the environment and would flip precedence"
        )
    for literal in (_COMPOSE_PORT, _COMPOSE_HOST):
        assert literal in text, f"missing composition line: {literal}"
        assert text.index(literal) > sourcing_close, (
            f"{literal} must compose AFTER the sourcing so cabinet/.env can "
            "fill in when no explicit env was set (the D4a bug)"
        )


def test_default_bind_stays_all_interfaces_and_exec_carries_hostname():
    """Standing constraint (OC-LOOPBACK pending): the bind DEFAULT stays
    0.0.0.0 — plumbing ships, the flip is captain-gated. The composition
    literal above pins the default; the exec line pins the mechanism."""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert _COMPOSE_HOST in text  # 0.0.0.0 default, exact
    assert _EXEC_LINE in text, "exec line lost the --port/--hostname plumbing"
    assert "captain-gated" in text, (
        "the header must say plainly that flipping the default is gated"
    )


def test_echo_prints_loopback_origin():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "http://127.0.0.1:$PORT" in text, (
        "the printed URL must use 127.0.0.1 (one cookie origin everywhere)"
    )
    assert "http://localhost" not in text, (
        "localhost is a DIFFERENT origin than 127.0.0.1 — printed URLs "
        "standardize on 127.0.0.1"
    )


# ---------------------------------------------------------------------------
# Functional precedence probe — the real script under a scratch CABINET_ROOT
# with an npm shim; no server, no build, no cabinet/.env of the repo.
# ---------------------------------------------------------------------------

def _probe(tmp_path: Path, env_file: str, explicit: dict) -> str:
    root = tmp_path / "root"
    dash = root / "cabinet" / "dashboard"
    (dash / ".next").mkdir(parents=True)         # skip the build branch
    (dash / "node_modules").mkdir()              # skip npm ci
    (root / "cabinet" / ".env").write_text(env_file, encoding="utf-8")
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    npm = shim_dir / "npm"
    npm.write_text('#!/bin/bash\necho "npm-argv: $@"\n', encoding="utf-8")
    npm.chmod(0o755)

    env = dict(os.environ)
    for k in ("CABINET_DASHBOARD_PORT", "CABINET_DASHBOARD_HOST",
              "CABINET_ROOT"):
        env.pop(k, None)
    env.update(explicit)
    env["CABINET_ROOT"] = str(root)
    env["PATH"] = f"{shim_dir}:{env['PATH']}"
    p = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert p.returncode == 0, (p.stdout, p.stderr)
    return p.stdout


def test_explicit_env_beats_dotenv(tmp_path):
    out = _probe(tmp_path,
                 "CABINET_DASHBOARD_PORT=4111\n",
                 {"CABINET_DASHBOARD_PORT": "4222"})
    assert "npm-argv: start -- --port 4222 --hostname 0.0.0.0" in out, out


def test_dotenv_used_when_no_explicit_env(tmp_path):
    """THE D4a bug: before the fix, a port in cabinet/.env was ignored."""
    out = _probe(tmp_path,
                 "CABINET_DASHBOARD_PORT=4111\n"
                 "CABINET_DASHBOARD_HOST=127.0.0.1\n",
                 {})
    assert "npm-argv: start -- --port 4111 --hostname 127.0.0.1" in out, out


def test_defaults_when_nothing_configured(tmp_path):
    out = _probe(tmp_path, "SOME_OTHER_VAR=1\n", {})
    assert "npm-argv: start -- --port 3100 --hostname 0.0.0.0" in out, out
    assert "http://127.0.0.1:3100" in out, out


# ---------------------------------------------------------------------------
# Dead-name gate — program-wide (Wave D ownership contract): the loopback
# surface has ONE canonical var; the dead spellings appear NOWHERE.
# ---------------------------------------------------------------------------

def test_dead_var_names_appear_nowhere():
    scan_roots = [
        _REPO_ROOT / "cabinet" / "scripts",
        _REPO_ROOT / "cabinet" / "docs",
        _REPO_ROOT / "docs" / "runbooks",
    ]
    offenders: list[str] = []
    for root in scan_roots:
        assert root.is_dir(), f"scan root missing: {root}"
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for dead in _DEAD_NAMES:
                if dead in text:
                    offenders.append(f"{path}: {dead}")
    assert offenders == [], (
        "retired var spellings found — the canonical name is "
        "CABINET_DASHBOARD_HOST: " + "; ".join(offenders)
    )
