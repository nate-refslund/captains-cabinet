"""Tests for cabinet/scripts/lib/evals-redis-sandbox.sh (2026-07-17).

The golden-eval suite SETs/DELs ``cabinet:killswitch`` — with the resolved
default endpoint (127.0.0.1:6379 = the LIVE Redis on the Mac) every FW-025
pre-push run armed and then silently cleared the fleet emergency stop. The
sandbox lib makes the suite spawn an ephemeral localhost redis-server and
re-point the FULL endpoint triple (REDIS_HOST/REDIS_PORT **and** REDIS_URL —
pre/post-tool-use derive from the URL) at it, unless the caller explicitly
declares the endpoint disposable (CI's throwaway service container).

The teeth test here is the canary: a stand-in "live" Redis with an armed
killswitch must come through a full sandbox start→write→stop cycle
untouched. Behavioral tests skip when redis-server/redis-cli are absent
(same idiom as test_redis_state_replay.py); the source-contract pins run
everywhere.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "evals-redis-sandbox.sh"
_SUITE = Path(__file__).resolve().parents[2] / "run-golden-evals.sh"

_HAVE_REDIS = all(shutil.which(t) for t in ("redis-server", "redis-cli"))


def _bash(script: str, env_extra: dict | None = None):
    env = dict(os.environ)
    env.pop("CABINET_EVALS_REDIS_DISPOSABLE", None)
    for var in ("REDIS_HOST", "REDIS_PORT", "REDIS_URL"):
        env.pop(var, None)
    env.update(env_extra or {})
    return subprocess.run(["bash", "-c", script], env=env,
                          capture_output=True, text=True, timeout=60)


# --- source-contract pins (no redis needed) -----------------------------------

def test_suite_sources_the_sandbox_and_refuses_without_it():
    """run-golden-evals.sh must gate on the sandbox: source + start-or-die.
    If this pin fails, the suite can once again reach a live Redis."""
    text = _SUITE.read_text(encoding="utf-8")
    assert "evals-redis-sandbox.sh" in text
    assert "evals_redis_sandbox_start" in text
    assert "evals_redis_sandbox_stop" in text
    # The refusal is a hard exit, not a warning: within the gate's if-block
    # (start-call line through the next LINE-anchored `fi`), an `exit 1`
    # must appear. Line-anchored so a word merely containing "fi" in a
    # future echo can't truncate the scanned block.
    lines = text.splitlines()
    start_idx = next(i for i, ln in enumerate(lines)
                     if "evals_redis_sandbox_start" in ln and "||" in ln)
    block = []
    for ln in lines[start_idx:]:
        block.append(ln)
        if ln.strip() == "fi":
            break
    assert any("exit 1" in ln for ln in block), (
        "the sandbox-failure branch no longer hard-exits")


def test_ci_declares_its_service_container_disposable():
    wf = (Path(__file__).resolve().parents[4]
          / ".github" / "workflows" / "cabinet-ci.yml")
    text = wf.read_text(encoding="utf-8")
    assert 'CABINET_EVALS_REDIS_DISPOSABLE: "1"' in text


# --- behavioral (skip without redis binaries) ----------------------------------

pytestmark_redis = pytest.mark.skipif(
    not _HAVE_REDIS, reason="redis-server/redis-cli not on PATH")


@pytestmark_redis
def test_start_exports_triple_and_stop_kills(tmp_path):
    r = _bash(
        f'source "{_LIB}" && evals_redis_sandbox_start && '
        'PID_SAVED=$_EVALS_SANDBOX_PID && '
        'echo "H=$REDIS_HOST P=$REDIS_PORT U=$REDIS_URL PID=$PID_SAVED" && '
        'redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET probe ok > /dev/null && '
        'redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET probe && '
        'evals_redis_sandbox_stop && '
        'sleep 0.3 && (kill -0 "$PID_SAVED" 2>/dev/null || echo DEAD)')
    assert r.returncode == 0, r.stderr
    assert "H=127.0.0.1" in r.stdout
    assert "U=redis://127.0.0.1:" in r.stdout
    assert "ok" in r.stdout
    # The kill-verification must have TEETH: the saved pid is dead after
    # stop (a prior draft probed pid 0 — always-true — the B4 class).
    assert "DEAD" in r.stdout, "sandbox server still alive after stop"


@pytestmark_redis
def test_disposable_flag_skips_spawn_and_keeps_endpoint():
    r = _bash(
        f'source "{_LIB}" && evals_redis_sandbox_start && '
        'echo "H=$REDIS_HOST P=$REDIS_PORT PID=[$_EVALS_SANDBOX_PID]"',
        env_extra={"CABINET_EVALS_REDIS_DISPOSABLE": "1",
                   "REDIS_HOST": "10.9.9.9", "REDIS_PORT": "7777"})
    assert r.returncode == 0, r.stderr
    assert "H=10.9.9.9 P=7777" in r.stdout
    assert "PID=[]" in r.stdout  # nothing spawned
    assert "declared disposable" in r.stdout


def test_missing_binary_refuses_without_exporting(tmp_path):
    # Empty PATH dir + only bash/coreutils shims: command -v redis-server
    # fails -> start returns non-zero and must NOT export an endpoint.
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    for tool in ("bash", "grep", "mktemp", "rm", "sleep", "kill", "echo"):
        real = shutil.which(tool)
        if real:
            (fakebin / tool).symlink_to(real)
    r = _bash(
        f'source "{_LIB}"; evals_redis_sandbox_start; rc=$?; '
        'echo "rc=$rc H=[${REDIS_HOST:-}]"; exit 0',
        env_extra={"PATH": str(fakebin)})
    assert "rc=1" in r.stdout
    assert "H=[]" in r.stdout


@pytestmark_redis
def test_canary_live_standin_untouched_by_sandbox_cycle(tmp_path):
    """THE teeth: an armed killswitch on the resolved ('live') endpoint
    survives a full sandbox start -> killswitch write -> stop cycle."""
    port = None
    proc = None
    for candidate in range(24000, 24020):
        proc = subprocess.Popen(
            ["redis-server", "--port", str(candidate), "--bind", "127.0.0.1",
             "--save", "", "--appendonly", "no", "--dir", str(tmp_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            ping = subprocess.run(
                ["redis-cli", "-p", str(candidate), "PING"],
                capture_output=True, text=True)
            if "PONG" in ping.stdout:
                port = candidate
                break
            time.sleep(0.1)
        if port:
            break
        proc.kill()
    assert port, "could not start the stand-in redis"
    try:
        subprocess.run(["redis-cli", "-p", str(port), "SET",
                        "cabinet:killswitch", "active-canary"], check=True,
                       capture_output=True)
        r = _bash(
            f'source "{_LIB}" && evals_redis_sandbox_start && '
            'redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET cabinet:killswitch sandbox-write > /dev/null && '
            'redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL cabinet:killswitch > /dev/null && '
            'evals_redis_sandbox_stop',
            env_extra={"REDIS_HOST": "127.0.0.1", "REDIS_PORT": str(port)})
        assert r.returncode == 0, r.stderr
        canary = subprocess.run(
            ["redis-cli", "-p", str(port), "GET", "cabinet:killswitch"],
            capture_output=True, text=True)
        assert canary.stdout.strip() == "active-canary", (
            "sandbox cycle touched the stand-in live redis: "
            f"{canary.stdout!r}")
    finally:
        proc.kill()
