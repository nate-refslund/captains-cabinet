"""COG-1 W3 — cabinet/cron/outbox-relay.sh preflight + python3.12 pin (§8.2).

The wrapper must:
  * pin python3.12 (the old bare `python3` exec is banned — launchd/cron shells
    resolve a different major);
  * when the COG-1 table drain is ARMED (flag or COG1_DRAIN_TASKS_OUTBOX=1),
    FAIL LOUD if the Postgres driver is missing from the pinned interpreter or
    the authority pointer file exists-but-is-unreadable — an unarmed/broken
    drain must never masquerade as a running one;
  * leave the LEGACY path (no drain flag) preflight-free and green.

Shells the real wrapper. Skips where bash is unavailable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WRAPPER = REPO / "cabinet" / "cron" / "outbox-relay.sh"

_BASH = shutil.which("bash")
_PY312 = shutil.which("python3.12") or "/opt/homebrew/bin/python3.12"
_pytestmark_bash = pytest.mark.skipif(_BASH is None, reason="bash unavailable")


def _clean_env(**over) -> dict:
    """A subprocess env with every work-store/redis DSN scrubbed so the drain
    can never resolve a live endpoint from the test host."""
    env = dict(os.environ)
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL", "COG1_OUTBOX_DSN",
              "COG1_DRAIN_TASKS_OUTBOX", "CABINET_PYTHON", "CABINET_COG1_AUTHORITY"):
        env.pop(k, None)
    env["CABINET_ROOT"] = str(REPO)
    env.update(over)
    return env


def _run(args, env, tmp):
    env = dict(env)
    env.setdefault("CABINET_EVENT_LOG_DIR", str(tmp / "events"))
    return subprocess.run([_BASH, str(WRAPPER), *args],
                          capture_output=True, text=True, env=env, timeout=60)


def _fake_py_no_psycopg2(tmp: Path) -> Path:
    """A stand-in 'python3.12' that reports version 3.12 but has no psycopg2 —
    exercises the driver-missing fail-loud without uninstalling anything."""
    p = tmp / "fakepy"
    p.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "-c" ]; then\n'
        '  case "$2" in\n'
        "    *version_info*) exit 0 ;;\n"
        "    *psycopg2*) exit 1 ;;\n"
        "  esac\n"
        "fi\n"
        f'exec "{_PY312}" "$@"\n')
    p.chmod(0o755)
    return p


# ---------------------------------------------------------------------------
# Static contract
# ---------------------------------------------------------------------------

class TestWrapperStatic:
    def test_pins_python312_not_bare_python3(self):
        text = WRAPPER.read_text()
        assert "python3.12" in text
        # the old bare exec must be gone
        assert "exec python3 -m framework.outbox.relay" not in text
        assert "framework.outbox.relay" in text

    def test_has_drain_preflight_markers(self):
        text = WRAPPER.read_text()
        assert "--drain-tasks-outbox" in text
        assert "import psycopg2" in text
        assert "COG1_DRAIN_TASKS_OUTBOX" in text
        assert "cog1-authority" in text


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------

@_pytestmark_bash
class TestWrapperBehaviour:
    def test_legacy_path_needs_no_preflight(self, tmp_path):
        r = _run(["--list-pending"], _clean_env(), tmp_path)
        assert r.returncode == 0, r.stderr
        assert "pending" in r.stdout

    def test_drain_armed_missing_driver_fails_loud(self, tmp_path):
        fake = _fake_py_no_psycopg2(tmp_path)
        r = _run(["--drain-tasks-outbox"],
                 _clean_env(CABINET_PYTHON=str(fake)), tmp_path)
        assert r.returncode == 71, (r.returncode, r.stdout, r.stderr)
        assert "psycopg2" in r.stderr

    def test_env_arm_injects_flag_and_preflights(self, tmp_path):
        # armed via env, flag NOT passed -> the wrapper still preflights (and
        # here the driver stub is missing -> fail loud, proving the env armed it)
        fake = _fake_py_no_psycopg2(tmp_path)
        r = _run([], _clean_env(CABINET_PYTHON=str(fake),
                                COG1_DRAIN_TASKS_OUTBOX="1"), tmp_path)
        assert r.returncode == 71, (r.returncode, r.stdout, r.stderr)

    def test_drain_armed_unreadable_pointer_fails_loud(self, tmp_path):
        ptr = tmp_path / "cog1-authority"
        ptr.write_text("outbox\n")
        ptr.chmod(0o000)
        try:
            r = _run(["--drain-tasks-outbox"],
                     _clean_env(CABINET_COG1_AUTHORITY=str(ptr)), tmp_path)
        finally:
            ptr.chmod(0o644)
        # running as root would bypass the unreadable check — skip that env
        if os.geteuid() == 0:
            pytest.skip("running as root bypasses file-permission checks")
        assert r.returncode == 72, (r.returncode, r.stdout, r.stderr)
        assert "unreadable" in r.stderr

    def test_drain_armed_preflight_passes_hands_off_to_relay(self, tmp_path):
        # real interpreter (psycopg2 present), pointer ABSENT (fail-safe OK),
        # no DSN -> preflight passes and the relay main refuses for lack of a
        # DSN (exit 2): proves the preflight let it through under python3.12.
        missing_ptr = tmp_path / "nope" / "cog1-authority"
        r = _run(["--drain-tasks-outbox"],
                 _clean_env(CABINET_COG1_AUTHORITY=str(missing_ptr)), tmp_path)
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert "dsn" in (r.stdout + r.stderr).lower()
