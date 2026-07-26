"""The emergency stop must FAIL CLOSED — end-to-end, against a real Redis.

WHY THIS FILE EXISTS (2026-07-25 adversarial audit). Every killswitch reader
decided "the switch is clear" by testing ``answer == "active"``. Measured
against redis 8.8, ``redis-cli GET`` prints the ERROR TEXT ON STDOUT AND EXITS
0 for each of these, so ONE allowed command silently disabled the Captain's
emergency stop while every status surface reported INACTIVE:

    redis-cli CONFIG SET requirepass X   -> "NOAUTH Authentication required."
    redis-cli ACL SETUSER default -get   -> "NOPERM ... 'get' command"
    redis-cli LPUSH cabinet:killswitch x -> "WRONGTYPE Operation against ..."
    any restart replaying an AOF         -> "LOADING Redis is loading ..."

WHAT THESE TESTS ASSERT is the property the control exists to deliver — DOES
THE FLEET ACTUALLY STOP? — not an internal invariant. The subject is
``pre-tool-use.sh``: exit 2 means an officer's Bash was refused, exit 0 means
the officer ran it. Every arm also checks what the Captain is TOLD, because a
stop that halts the fleet while reporting "inactive" is still a defeat.

SAFETY: every test stands up its OWN redis-server on a free port and tears it
down. Nothing here may touch a live control plane, so the endpoint is injected
through REDIS_HOST/REDIS_PORT/REDIS_URL and the stop marker is redirected to a
tmp path via CABINET_ESTOP_MARKER.

NON-VACUITY: point CABINET_TEST_TARGET_ROOT at a checkout of the pre-fix
commit and every fail-closed arm below fails, which is how this file was
proven to test something.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(os.environ.get("CABINET_TEST_TARGET_ROOT")
            or Path(__file__).resolve().parents[3])
HOOK = REPO / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"
KILL_SWITCH = REPO / "cabinet" / "scripts" / "kill-switch.sh"

_REDIS_SERVER = shutil.which("redis-server") or next(
    (c for c in ("/opt/homebrew/bin/redis-server", "/usr/local/bin/redis-server")
     if os.path.exists(c)), None)
_REDIS_CLI = shutil.which("redis-cli") or next(
    (c for c in ("/opt/homebrew/bin/redis-cli", "/usr/local/bin/redis-cli")
     if os.path.exists(c)), None)

needs_redis = pytest.mark.skipif(
    not (_REDIS_SERVER and _REDIS_CLI),
    reason="redis-server/redis-cli not available — cannot stand up a private control plane")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Plane:
    """A private, throwaway control plane. Never the live one."""

    def __init__(self, port: int, marker: Path):
        self.port = port
        self.marker = marker

    def cli(self, *args: str, port: int | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([_REDIS_CLI, "-p", str(port or self.port), *args],
                              capture_output=True, text=True, timeout=15)

    def env(self, *, port: int | None = None, extra: dict | None = None) -> dict:
        p = str(port or self.port)
        e = dict(os.environ)
        e.update({
            "REDIS_HOST": "127.0.0.1", "REDIS_PORT": p,
            "REDIS_URL": f"redis://127.0.0.1:{p}",
            "CABINET_ROOT": str(REPO),
            "CABINET_ESTOP_MARKER": str(self.marker),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        e.pop("CABINET_AUTHORITY_ENFORCING", None)
        e.update(extra or {})
        return e

    # -- the subject under test -------------------------------------------
    def officer_bash(self, *, port: int | None = None, extra: dict | None = None) -> int:
        """Run ONE officer Bash tool call through the hook. 2 = refused."""
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "echo pwned"}})
        proc = subprocess.run(["bash", str(HOOK)], input=payload,
                              capture_output=True, text=True, timeout=120,
                              cwd=str(REPO), env=self.env(port=port, extra=extra))
        self.last_stderr = proc.stderr
        return proc.returncode

    def status(self, *, port: int | None = None, extra: dict | None = None):
        proc = subprocess.run(["bash", str(KILL_SWITCH), "status"],
                              capture_output=True, text=True, timeout=60,
                              cwd=str(REPO), env=self.env(port=port, extra=extra))
        return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture
def plane(tmp_path):
    """A fresh redis per test — the arms mutate auth/ACL/type state."""
    port = _free_port()
    data = tmp_path / "redis"
    data.mkdir()
    proc = subprocess.Popen(
        [_REDIS_SERVER, "--port", str(port), "--save", "", "--appendonly", "no",
         "--dir", str(data), "--logfile", str(data / "r.log")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p = Plane(port, tmp_path / "estop-marker")
    for _ in range(100):
        if p.cli("PING").stdout.strip() == "PONG":
            break
        time.sleep(0.05)
    else:  # pragma: no cover - environment failure
        proc.kill()
        pytest.skip("private redis did not come up")
    try:
        yield p
    finally:
        proc.kill()
        proc.wait(timeout=10)


def _stub_loading_cli(tmp_path: Path) -> str:
    """A redis-cli that reproduces the MEASURED -LOADING wire behaviour: the
    error text on STDOUT with EXIT 0. Inducing a real AOF replay is inherently
    racy; the bytes are the contract, and they are what defeated the reader."""
    d = tmp_path / "loadingbin"
    d.mkdir()
    stub = d / "redis-cli"
    stub.write_text('#!/bin/bash\necho "LOADING Redis is loading the dataset in memory"\nexit 0\n')
    stub.chmod(0o755)
    return str(d)


# =========================================================================
# THE DECISIVE ARMS — with the stop armed, does the fleet actually stop?
# =========================================================================

@needs_redis
def test_healthy_clear_switch_lets_the_fleet_work(plane):
    """THE ANTI-BRICK ARM. A verified-clear switch must NOT block — a
    fail-closed fix that refuses everything is not a fix, it is an outage."""
    plane.cli("DEL", "cabinet:killswitch")
    assert plane.officer_bash() == 0, (
        "a healthy, authenticated, genuinely-clear switch must permit action; "
        f"hook refused with: {plane.last_stderr}")
    rc, out = plane.status()
    assert rc == 0 and "INACTIVE" in out


@needs_redis
def test_armed_switch_stops_the_fleet(plane):
    plane.cli("SET", "cabinet:killswitch", "active")
    assert plane.officer_bash() == 2
    rc, out = plane.status()
    assert rc == 0 and "Kill switch: ACTIVE" in out


@needs_redis
def test_noauth_stops_the_fleet_and_never_reports_inactive(plane):
    """`redis-cli CONFIG SET requirepass X` — every later read answers
    'NOAUTH Authentication required.' with EXIT 0. Pre-fix that read as a
    clear switch AND the status verb printed INACTIVE (PING answers NOAUTH
    with exit 0 too, so the reachability probe passed)."""
    plane.cli("SET", "cabinet:killswitch", "active")
    plane.cli("CONFIG", "SET", "requirepass", "hunter2")
    assert plane.officer_bash() == 2, "NOAUTH must not read as a clear switch"
    rc, out = plane.status()
    assert rc != 0, "an unreadable switch must not exit 0"
    assert "INACTIVE" not in out
    assert "CANNOT VERIFY" in out and "STOPPED" in out


@needs_redis
def test_noperm_stops_the_fleet_and_never_reports_inactive(plane):
    """`ACL SETUSER default -get` — GET answers NOPERM with exit 0 while PING
    still answers PONG, so a reachability probe cannot see this at all."""
    plane.cli("SET", "cabinet:killswitch", "active")
    plane.cli("ACL", "SETUSER", "default", "-get")
    assert plane.officer_bash() == 2, "NOPERM must not read as a clear switch"
    rc, out = plane.status()
    assert rc != 0 and "INACTIVE" not in out
    assert "CANNOT VERIFY" in out


@needs_redis
def test_wrongtype_stops_the_fleet_and_never_reports_inactive(plane):
    """`LPUSH cabinet:killswitch x` — GET answers WRONGTYPE with exit 0."""
    plane.cli("DEL", "cabinet:killswitch")
    plane.cli("LPUSH", "cabinet:killswitch", "x")
    assert plane.officer_bash() == 2, "WRONGTYPE must not read as a clear switch"
    rc, out = plane.status()
    assert rc != 0 and "INACTIVE" not in out
    assert "CANNOT VERIFY" in out


@needs_redis
def test_loading_stops_the_fleet_and_never_reports_inactive(plane, tmp_path):
    """A restart replaying an AOF answers -LOADING for the whole replay."""
    stub_dir = _stub_loading_cli(tmp_path)
    extra = {"PATH": stub_dir + os.pathsep + os.environ["PATH"]}
    assert plane.officer_bash(extra=extra) == 2, "LOADING must not read as clear"
    rc, out = plane.status(extra=extra)
    assert rc != 0 and "INACTIVE" not in out
    assert "CANNOT VERIFY" in out


@needs_redis
def test_connection_refused_stops_the_fleet(plane):
    """The one failure mode the pre-fix reader DID catch — pinned so the
    inverted default cannot regress it."""
    dead = _free_port()
    assert plane.officer_bash(port=dead) == 2
    rc, out = plane.status(port=dead)
    assert rc != 0 and "INACTIVE" not in out


@needs_redis
def test_unrecognised_value_is_not_proof_of_clear(plane):
    """A value we do not recognise is the ABSENCE of evidence, not evidence of
    absence — it must not permit action."""
    plane.cli("SET", "cabinet:killswitch", "off")
    assert plane.officer_bash() == 2
    rc, out = plane.status()
    assert rc != 0 and "INACTIVE" not in out


# =========================================================================
# DEFECT 2 — the pre-armed clearing loop
# =========================================================================

@needs_redis
def test_stop_survives_a_del_loop_clearing_the_redis_key(plane):
    """`while :; do redis-cli DEL cabinet:killswitch; sleep 1; done` clears the
    Redis channel within a second of every arming. kill-switch.sh writes a
    filesystem marker BEFORE the Redis SET, and the loop never touches the
    filesystem — so the stop survives.

    The honest limit (registered as RES-016, whose declaration site is
    cabinet/scripts/kill-switch.sh): an adversary that also removes the marker
    defeats this. It is asserted below, deliberately, so the limit is on record.

    DEFECT 2 IS OPEN, DELIBERATELY. ``kill-switch.sh activate`` does NOT arm
    the marker yet — a durable latch changes what killswitch-watchdog.py is for
    (it exists to re-arm a switch a raw DEL cleared), which is a Captain call,
    not a bug fix. What is pinned here is that the MECHANISM works: with both
    channels carrying the stop, the loop cannot clear it. Arming it by default
    is the remaining step.
    """
    plane.marker.write_text("active\n")            # the second channel, by hand
    plane.cli("SET", "cabinet:killswitch", "active")

    plane.cli("DEL", "cabinet:killswitch")          # the loop wins the race
    assert plane.cli("GET", "cabinet:killswitch").stdout.strip() == ""

    assert plane.officer_bash() == 2, "the DEL loop must not clear a two-channel stop"
    rc, out = plane.status()
    assert rc == 0 and "Kill switch: ACTIVE" in out

    # The honest limit, pinned: remove BOTH channels and the fleet runs again.
    plane.marker.unlink()
    assert plane.officer_bash() == 0


# =========================================================================
# DEFECT 3 — the spend gate must never read an error as $0 / unlimited
# =========================================================================

def _spend_root(tmp_path: Path, name: str, per_officer: str, cabinet_wide: str) -> Path:
    """A synthetic CABINET_ROOT carrying only the caps under test.

    The hook rebuilds its cap table from the yaml under CABINET_ROOT on every
    call, so this is the only way to control the caps a probe runs against.
    Pointing at the repo root instead makes the test read whatever the Captain
    has configured that week — which is how the FW-002 golden eval came to
    spend weeks asserting nothing."""
    root = tmp_path / name
    (root / "instance/config").mkdir(parents=True, exist_ok=True)
    (root / "instance/config/platform.yml").write_text(
        "spending_limits:\n"
        f"  daily_per_officer_usd: {per_officer}\n"
        f"  daily_cabinet_wide_usd: {cabinet_wide}\n")
    return root


@needs_redis
def test_unreadable_spend_ledger_refuses_instead_of_reading_zero(plane, tmp_path):
    """`SET cabinet:cost:tokens:daily:<today> x` made the gate's HKEYS answer
    WRONGTYPE; the old capture read that as 'no cost fields', today's spend
    summed to $0, and the cap could not trip again all day.

    The cap is set EXPLICITLY here. Reading it from the repo's platform.yml
    would have made this arm evaporate the day the Captain uncapped spend
    (2026-07-26): with no cap to enforce the hook never reaches the ledger
    read at all, so the test would have been green on an unexercised
    fail-closed path — a disabled sensor, not a pass."""
    plane.cli("DEL", "cabinet:killswitch")
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True,
                           text=True).stdout.strip()
    plane.cli("SET", f"cabinet:cost:tokens:daily:{today}", "x")
    root = _spend_root(tmp_path, "capped", "75", "0")
    rc = plane.officer_bash(extra={"OFFICER": "cto", "CABINET_ROOT": str(root)})
    assert rc == 2, (
        "an unreadable spend ledger must not read as $0; "
        f"hook allowed the call. stderr: {plane.last_stderr}")
    assert "UNREADABLE" in plane.last_stderr


@needs_redis
def test_uncapped_cabinet_does_not_block_on_an_unreadable_ledger(plane, tmp_path):
    """The other half of the arm above, pinning the Captain's 2026-07-26
    ruling: with spend UNCAPPED there is no ceiling to enforce, so the hook
    must not read the ledger and must not refuse. If a future change makes an
    unreadable ledger block an uncapped Cabinet, every officer goes dark over
    a limit nobody set."""
    plane.cli("DEL", "cabinet:killswitch")
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True,
                           text=True).stdout.strip()
    plane.cli("SET", f"cabinet:cost:tokens:daily:{today}", "x")
    root = _spend_root(tmp_path, "uncapped", "unlimited", "unlimited")
    rc = plane.officer_bash(extra={"OFFICER": "cto", "CABINET_ROOT": str(root)})
    assert rc == 0, (
        "an uncapped Cabinet has no ceiling to enforce and must not refuse; "
        f"stderr: {plane.last_stderr}")
    assert "UNREADABLE" not in plane.last_stderr
    assert "BLOCKED" not in plane.last_stderr


@needs_redis
def test_garbage_cap_falls_back_to_the_framework_default_not_unlimited(plane, tmp_path):
    """A non-numeric cap used to coerce to 0, and 0 means UNLIMITED — so
    corrupting one line of platform.yml silently removed the spend ceiling.

    The officer below has spent $500 today. The per-officer cap is garbage and
    the cabinet-wide cap is an EXPLICIT 0 (a real, Captain-written 'unlimited',
    which must still be honoured) — so the per-officer coercion is the only
    thing that can stop this call. Pre-fix it coerced to 0 and the call ran."""
    plane.cli("DEL", "cabinet:killswitch")
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True,
                           text=True).stdout.strip()
    plane.cli("HSET", f"cabinet:cost:tokens:daily:{today}", "cto_cost_micro",
              str(500 * 1000 * 1000))

    fake_root = _spend_root(tmp_path, "garbage-cap", "not-a-number", "0")

    rc = plane.officer_bash(extra={"OFFICER": "cto", "CABINET_ROOT": str(fake_root)})
    assert rc == 2, (
        "a garbage per-officer cap must fall back to the $75 framework default, "
        f"not to 0 (= unlimited); hook allowed the call. stderr: {plane.last_stderr}")
    assert "cap=$75.00" in plane.last_stderr


def test_garbage_cap_coercion_is_not_unlimited():
    """Unit-pin the direction of the coercion, independent of any Redis."""
    src = (REPO / "cabinet/scripts/hooks/pre-tool-use.sh").read_text()
    assert "PER_OFF_CAP_USD=0 ;;" not in src, (
        "a non-numeric per-officer cap must not coerce to 0 (= unlimited)")
    assert "CABINET_CAP_USD=0 ;;" not in src, (
        "a non-numeric cabinet-wide cap must not coerce to 0 (= unlimited)")
    assert "PER_OFF_CAP_USD=75" in src and "CABINET_CAP_USD=300" in src


# =========================================================================
# ONE READER — the shell helper and the python classifier must agree
# =========================================================================

@needs_redis
@pytest.mark.parametrize("setup,expected", [
    ("clear", "CLEAR"),
    ("armed", "ACTIVE"),
    ("wrongtype", "INDETERMINATE"),
    ("noperm", "INDETERMINATE"),
    ("noauth", "INDETERMINATE"),
    ("bogus", "INDETERMINATE"),
])
def test_shell_and_python_readers_return_the_same_verdict(plane, setup, expected):
    """The shell helper (every hook/script) and action_exec's classifier (the
    action lane + the front door) are two implementations of one contract.
    A divergence is how a fixed gate and an unfixed gate end up shipping
    together, so it is pinned state by state."""
    if setup == "armed":
        plane.cli("SET", "cabinet:killswitch", "active")
    elif setup == "wrongtype":
        plane.cli("LPUSH", "cabinet:killswitch", "x")
    elif setup == "bogus":
        plane.cli("SET", "cabinet:killswitch", "off")
    elif setup == "noperm":
        plane.cli("ACL", "SETUSER", "default", "-get")
    elif setup == "noauth":
        plane.cli("CONFIG", "SET", "requirepass", "hunter2")

    helper = REPO / "cabinet/scripts/hooks/killswitch-read.sh"
    shell = subprocess.run(["bash", str(helper)], capture_output=True, text=True,
                           timeout=30, cwd=str(REPO), env=plane.env())
    shell_verdict = shell.stdout.split("\t", 1)[0].strip()

    py = subprocess.run(
        ["python3.12", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from framework.frontdoor import action_exec as ax;"
         "print(ax._killswitch_state(ax._redis_get_strict))",
         str(REPO)],
        capture_output=True, text=True, timeout=60, cwd=str(REPO), env=plane.env())
    py_verdict = {"active": "ACTIVE", "clear": "CLEAR",
                  "unreachable": "INDETERMINATE"}.get(py.stdout.strip(), py.stdout.strip())

    assert shell_verdict == expected, f"shell said {shell_verdict}: {shell.stdout}"
    assert py_verdict == expected, f"python said {py_verdict}: {py.stdout}{py.stderr}"


# =========================================================================
# COVERAGE — no reader may be left behind
# =========================================================================

def test_no_reader_compares_a_raw_get_to_active():
    """A missed reader is the whole bug again. Every shell surface that gates
    on the emergency stop must go through the shared helper, never its own
    `GET cabinet:killswitch` compared to the literal string."""
    out = subprocess.run(
        ["git", "grep", "-n", "-E", r"GET cabinet:killswitch", "--",
         "cabinet/scripts", "framework"],
        capture_output=True, text=True, cwd=str(REPO)).stdout
    offenders = []
    for line in out.splitlines():
        parts = line.split(":", 2)
        path, body = parts[0], (parts[2] if len(parts) > 2 else "")
        if path.endswith((".md", ".yml")) or "/tests/" in path or "test_" in path:
            continue
        # The shared helper IS the reader, and pre-tool-use.sh carries its
        # test-pinned inline twin (see the twin rationale in that file).
        if path.endswith(("hooks/killswitch-read.sh", "hooks/pre-tool-use.sh")):
            continue
        # Prose that NAMES the key (comments, docstrings) is not a reader.
        stripped = body.strip()
        if stripped.startswith(("#", "*", '"""', "'''", "//")):
            continue
        offenders.append(line)
    assert not offenders, (
        "these still read the switch themselves instead of using "
        "cabinet/scripts/hooks/killswitch-read.sh:\n" + "\n".join(offenders))
