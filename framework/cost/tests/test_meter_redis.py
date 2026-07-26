"""The cost meter against a REAL Redis — every path test_meter.py cannot reach.

WHY THIS FILE EXISTS (2026-07-27). `test_meter.py` is pure-unit: it prices
tokens and parses transcripts, and it passes IDENTICALLY with `REDIS_PORT`
pointed at nothing. Every Redis-touching path in `framework/cost` —
``record_session_turn``, ``write_watermark``/``read_watermark``,
``_redis_atomic``, ``record_lane``, ``hgetall``'s line-pair parser and
``record_turn.main()`` itself — had ZERO coverage. That is the "the sensor
tests something other than the control" failure: 21 green tests over a meter
whose entire persistence layer was unobserved.

WHAT THESE ARMS ASSERT is the property the meter exists to deliver — DOES THE
SPEND ACTUALLY LAND, EXACTLY ONCE, AND DOES A FAILURE KEEP IT RE-BILLABLE? —
not an internal invariant. The meter is a WATCH, not a gate (the Captain
removed every spend cap on 2026-07-26), so its two failure modes are
"under-report" (fatal: the watch goes blind) and "never break the officer's
turn" (fatal the other way: a metering bug must not cost a turn). Both are
pinned here.

THE NON-OBVIOUS ONE, measured on redis 8.x and pinned by
``test_stdin_mode_exit0_empty_stdout_must_read_as_failure``: `redis-cli`
reading commands from STDIN exits **0 with EMPTY STDOUT** when the server is
down — it prints "Could not connect" to STDERR once per command and returns
success. An exit-code-only check therefore reports a total connection failure
as a successful ledger write, advances the watermark, and drops the spend with
a green log line. ``_redis_atomic`` uses POSITIVE CONFIRMATION instead
(MULTI's `OK`, one `QUEUED` per command, clean stderr); the stub-cli arms below
fail the moment anyone reverts it to `return cp.returncode == 0`.

SAFETY: every test stands up its OWN redis-server on a free port and tears it
down. Nothing here may touch the live control plane, so the endpoint is
injected through REDIS_HOST/REDIS_PORT and the fixture REFUSES port 6379.
CI sets `REDIS_HOST: localhost` for the framework suite — every arm overrides
both variables explicitly rather than inheriting them.

NON-VACUITY: each failure arm has a paired positive control on the same
mechanism (a healthy plane, or a stub cli emitting the healthy wire bytes), so
an arm cannot pass by refusing everything.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from framework.cost import meter, record_turn

REPO = Path(__file__).resolve().parents[3]

_REDIS_SERVER = shutil.which("redis-server") or next(
    (c for c in ("/opt/homebrew/bin/redis-server", "/usr/local/bin/redis-server")
     if os.path.exists(c)), None)
_REDIS_CLI = shutil.which("redis-cli") or next(
    (c for c in ("/opt/homebrew/bin/redis-cli", "/usr/local/bin/redis-cli")
     if os.path.exists(c)), None)

needs_redis = pytest.mark.skipif(
    not (_REDIS_SERVER and _REDIS_CLI),
    reason="redis-server/redis-cli not available — cannot stand up a private "
           "cost ledger; these arms must SKIP, never silently pass")

LIVE_PORT = 6379  # never, under any circumstance, the endpoint of a test here


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Plane:
    """A private, throwaway cost ledger. Never the live one."""

    def __init__(self, port: int):
        self.port = port

    # -- raw access, used only to set up and to read back ------------------
    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([_REDIS_CLI, "-p", str(self.port), *args],
                              capture_output=True, text=True, timeout=15)

    def keys(self, pattern: str) -> list:
        out = self.cli("--scan", "--pattern", pattern).stdout.strip()
        return sorted(k for k in out.split("\n") if k)

    def hget(self, key: str, field: str):
        cp = self.cli("HGET", key, field)
        v = cp.stdout.strip()
        return v or None

    def ledger_field(self, field: str) -> int:
        """Sum one field across every daily officer ledger on this plane.

        Summed across keys rather than read from ``daily_token_key()`` because
        TIME IS AN INPUT: a run that straddles UTC midnight would otherwise
        split the spend over two keys and fail for a reason that is not a bug.
        The plane is private and fresh, so the sum is exact.
        """
        total = 0
        for k in self.keys("cabinet:cost:tokens:daily:*"):
            v = self.hget(k, field)
            if v is not None:
                total += int(v)
        return total

    def env(self, **extra) -> dict:
        e = dict(os.environ)
        e.update({
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(self.port),
            "PYTHONPATH": str(REPO),
            "PYTHONDONTWRITEBYTECODE": "1",
            "CONTEXT_WINDOW_SIZE": "1000000",
        })
        e.update({k: str(v) for k, v in extra.items()})
        return e


def _point_meter_at(monkeypatch, port) -> None:
    """Make in-process meter calls talk to `port` — never the ambient endpoint.

    CI exports REDIS_HOST=localhost for the whole framework suite; inheriting
    it would aim these writes at the runner's shared service container.
    """
    assert int(port) != LIVE_PORT, "a test must never write the live cost ledger"
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", str(port))
    monkeypatch.setenv("CONTEXT_WINDOW_SIZE", "1000000")


@pytest.fixture(autouse=True)
def _never_the_live_store(monkeypatch):
    """Belt-and-suspenders: default every arm's endpoint to a dead port.

    `meter._redis_argv()` falls back to REDIS_PORT=6379 — the LIVE cabinet
    control plane — whenever the variable is unset, and CI exports
    REDIS_HOST=localhost for the whole framework suite. An arm that forgets to
    point itself at its private plane must fail loudly, not quietly write the
    fleet's real cost ledger. Tests override this with `_point_meter_at`.
    """
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "1")
    monkeypatch.setenv("CONTEXT_WINDOW_SIZE", "1000000")


@pytest.fixture
def plane():
    """A fresh redis per test — arms poison key types and kill the server."""
    port = _free_port()
    assert port != LIVE_PORT
    import tempfile
    data = tempfile.mkdtemp(prefix="cost-meter-redis-")
    proc = subprocess.Popen(
        [_REDIS_SERVER, "--port", str(port), "--save", "", "--appendonly", "no",
         "--dir", data, "--logfile", os.path.join(data, "r.log")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p = Plane(port)
    for _ in range(200):
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
        shutil.rmtree(data, ignore_errors=True)


@pytest.fixture
def dead_port():
    """A port with NOTHING listening. Bound, read, then released."""
    port = _free_port()
    assert port != LIVE_PORT
    return port


# ─────────────────────────────────────────────────────────────────────────────
# Transcript fixtures. Token counts are round numbers so every expected dollar
# figure below is a HAND-COMPUTED literal, not a second call to price() —
# a test that recomputes the answer with the code under test proves nothing.
#
#   opus   $15 in / $75 out per MTok      haiku  $1 in / $5 out
#   sonnet  $3 in / $15 out               cache read = 0.10x in, 1h write = 2.0x in
# ─────────────────────────────────────────────────────────────────────────────
def _assistant(mid, model="claude-opus-4-8", **usage):
    u = {"input_tokens": 0, "output_tokens": 0,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    u.update(usage)
    return {"type": "assistant", "message": {"id": mid, "model": model, "usage": u}}


# r1 100_000 in  x $15  = 1_500_000  +  10_000 out x $75 =   750_000
R1 = _assistant("msg_r1", input_tokens=100_000, output_tokens=10_000)
R1_MICRO = 2_250_000
# r2 1_000_000 cache_read x $15 x 0.10
R2 = _assistant("msg_r2", cache_read_input_tokens=1_000_000)
R2_MICRO = 1_500_000
# r3 100_000 1h cache write x $15 x 2.00
R3 = {"type": "assistant", "message": {
    "id": "msg_r3", "model": "claude-opus-4-8", "usage": {
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 100_000, "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_1h_input_tokens": 100_000,
                           "ephemeral_5m_input_tokens": 0}}}}
R3_MICRO = 3_000_000
FIRST_SLICE_MICRO = R1_MICRO + R2_MICRO + R3_MICRO          # 6_750_000

# r4 1_000_000 sonnet in x $3
R4 = _assistant("msg_r4", model="claude-sonnet-4-5", input_tokens=1_000_000)
R4_MICRO = 3_000_000
# r5 200_000 haiku in x $1  +  1_000_000 out x $5
R5 = _assistant("msg_r5", model="claude-haiku-4-5",
                input_tokens=200_000, output_tokens=1_000_000)
R5_MICRO = 5_200_000
SECOND_SLICE_MICRO = R4_MICRO + R5_MICRO                    # 8_200_000
ALL_MICRO = FIRST_SLICE_MICRO + SECOND_SLICE_MICRO          # 14_950_000


def _write(path: Path, entries) -> None:
    with open(path, "w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _append(path: Path, entries) -> None:
    with open(path, "a") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _run_cli(plane_or_port, transcript, *, officer="cos", session="sess-1",
             project="", extra_env=None):
    """Run the meter the way the Stop hook does: as a subprocess."""
    port = getattr(plane_or_port, "port", plane_or_port)
    env = dict(os.environ)
    env.update({
        "REDIS_HOST": "127.0.0.1", "REDIS_PORT": str(port),
        "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
        "CONTEXT_WINDOW_SIZE": "1000000",
    })
    env.update(extra_env or {})
    argv = [sys.executable, "-m", "framework.cost.record_turn",
            "--transcript", str(transcript), "--session", session,
            "--officer", officer]
    if project:
        argv += ["--project", project]
    return subprocess.run(argv, capture_output=True, text=True, timeout=120,
                          cwd=str(REPO), env=env)


# =========================================================================
# 1. THE WATERMARK — every API response billed EXACTLY once
# =========================================================================

@needs_redis
def test_two_consecutive_stops_bill_every_response_exactly_once(plane, tmp_path, monkeypatch):
    """The load-bearing property of the whole rewrite.

    Nothing re-billed (the naive "sum the file each Stop" bug) and nothing
    dropped (the shipped `tail -1` bug, measured at 4.4x of a 16.0x total
    under-report). Three consecutive Stops over a growing transcript.
    """
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "transcript.jsonl"
    # R1 repeated: Claude Code writes one assistant entry per CONTENT BLOCK.
    _write(t, [{"type": "user", "message": {"content": "go"}},
               R1, R1, R1, R2, R3])

    assert record_turn.main(["--transcript", str(t), "--session", "sess-A",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == FIRST_SLICE_MICRO
    wm1 = meter.read_watermark("sess-A")
    assert wm1 == 6, "watermark must be the LINE COUNT of the file just read"

    _append(t, [R4, R5, R5])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-A",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == ALL_MICRO, (
        "second Stop must add exactly the NEW responses — no re-bill of the "
        "first slice, no drop of the appended ones")
    assert meter.read_watermark("sess-A") == 9

    # Third Stop, nothing appended: the ledger must not move at all.
    assert record_turn.main(["--transcript", str(t), "--session", "sess-A",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == ALL_MICRO
    assert meter.read_watermark("sess-A") == 9

    # Token dimensions, summed by hand across all five responses.
    assert plane.ledger_field("cos_input") == 1_300_000
    assert plane.ledger_field("cos_output") == 1_010_000
    assert plane.ledger_field("cos_cache_write") == 100_000
    assert plane.ledger_field("cos_cache_read") == 1_000_000


@needs_redis
def test_last_turn_hash_is_the_latest_response_not_a_running_sum(plane, tmp_path, monkeypatch):
    """`cabinet:cost:tokens:<officer>` is a LATEST-turn snapshot.

    The health dashboard, list-officers.sh, org-health-audit.sh and the fw-a14
    stop-guard eval read `last_context_pct` from it. Summing would report a
    context window many times over 100%.
    """
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1, R2, R3, R4, R5])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-B",
                             "--officer", "cos"]) == 0

    h = meter.hgetall("cabinet:cost:tokens:cos")
    assert h is not None
    assert h["last_cost_micro"] == str(R5_MICRO)      # r5 only, not ALL_MICRO
    assert h["last_input"] == "200000"
    assert h["last_output"] == "1000000"
    assert h["last_model"] == "claude-haiku-4-5"
    assert h["last_context_tokens"] == "200000"
    assert h["last_context_pct"] == "20"              # 200k of a 1M window
    assert h["last_updated"].endswith("Z")
    assert 0 < int(plane.cli("TTL", "cabinet:cost:tokens:cos").stdout.strip()) <= 86400


@needs_redis
def test_watermarks_are_per_session_and_never_shared(plane, tmp_path, monkeypatch):
    """One shared watermark would let a long session's high mark silently
    suppress billing for a short one — the reason ``record_turn`` refuses to
    let the literal `unknown` session id through."""
    _point_meter_at(monkeypatch, plane.port)
    long_t, short_t = tmp_path / "long.jsonl", tmp_path / "short.jsonl"
    _write(long_t, [R1, R2, R3, R4, R5])
    _write(short_t, [R1])

    assert record_turn.main(["--transcript", str(long_t), "--session", "sess-long",
                             "--officer", "cos"]) == 0
    assert record_turn.main(["--transcript", str(short_t), "--session", "sess-short",
                             "--officer", "cos"]) == 0
    assert meter.read_watermark("sess-long") == 5
    assert meter.read_watermark("sess-short") == 1
    assert plane.ledger_field("cos_cost_micro") == ALL_MICRO + R1_MICRO


@needs_redis
def test_unusable_session_id_falls_back_to_the_officer_watermark(plane, tmp_path, monkeypatch):
    """The Stop payload defaults `session_id` to the literal "unknown"."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1])
    assert record_turn.main(["--transcript", str(t), "--session", "unknown",
                             "--officer", "cos"]) == 0
    assert meter.read_watermark("cos") == 1
    assert plane.keys("cabinet:cost:wm:*") == ["cabinet:cost:wm:cos"]
    assert meter.watermark_key("unknown") is None


# =========================================================================
# 2. A POISONED LEDGER MUST NOT ADVANCE THE WATERMARK
# =========================================================================

@needs_redis
def test_wrongtype_ledger_holds_the_watermark_and_stays_re_billable(plane, tmp_path, monkeypatch):
    """A daily key holding a STRING makes every HINCRBY answer WRONGTYPE.

    `redis-cli` reports it INSIDE the EXEC reply with exit 0, so an exit-code
    check calls this a successful write. It must instead report failure and
    hold the watermark, or the turn's spend is gone for good.
    """
    _point_meter_at(monkeypatch, plane.port)
    # Poison today's AND tomorrow's key: a run straddling UTC midnight would
    # otherwise write into a clean key and pass for the wrong reason.
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc)
    for d in (today, today + _dt.timedelta(days=1)):
        plane.cli("SET", meter.daily_token_key(d.strftime("%Y-%m-%d")), "i-am-a-string")

    t = tmp_path / "t.jsonl"
    _write(t, [R1, R2, R3])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-P",
                             "--officer", "cos"]) == 0, "a metering failure must not break the turn"

    assert meter.read_watermark("sess-P") == 0, (
        "the watermark must NOT advance over a failed ledger write — the spend "
        "has to be re-billable on the next Stop")
    assert plane.keys("cabinet:cost:wm:*") == []
    assert meter.record_session_turn("cos", meter.parse_transcript(str(t))) is False

    # NON-VACUITY / the recovery half: clear the poison and the SAME spend lands.
    for k in plane.keys("cabinet:cost:tokens:daily:*"):
        plane.cli("DEL", k)
    assert record_turn.main(["--transcript", str(t), "--session", "sess-P",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == FIRST_SLICE_MICRO
    assert meter.read_watermark("sess-P") == 3


@needs_redis
def test_wrongtype_is_reported_on_stdout_as_a_held_watermark(plane, tmp_path):
    """Silent failure is the thing this meter exists to stop. The CLI has to
    SAY the write failed, or a dead ledger looks exactly like a quiet day."""
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc)
    for d in (today, today + _dt.timedelta(days=1)):
        plane.cli("SET", meter.daily_token_key(d.strftime("%Y-%m-%d")), "poison")
    t = tmp_path / "t.jsonl"
    _write(t, [R1])
    cp = _run_cli(plane, t, session="sess-Q")
    assert cp.returncode == 0
    assert "WARN ledger write failed" in cp.stdout
    assert "will re-bill" in cp.stdout


# =========================================================================
# 3. REDIS UNREACHABLE — the exit-0/empty-stdout trap
# =========================================================================

@needs_redis
def test_unreachable_redis_reports_failure_and_holds_the_watermark(dead_port, tmp_path, monkeypatch):
    _point_meter_at(monkeypatch, dead_port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1, R2, R3])

    sl = meter.parse_transcript(str(t))
    assert sl.responses_billed == 3
    assert meter.record_session_turn("cos", sl) is False, (
        "a total connection failure must never report a successful ledger write")
    assert meter.write_watermark("sess-D", 3) is False
    assert meter.read_watermark("sess-D") == 0
    assert record_turn.main(["--transcript", str(t), "--session", "sess-D",
                             "--officer", "cos"]) == 0


def _stub_cli(tmp_path: Path, name: str, body: str) -> str:
    """A fake `redis-cli` on PATH. Pins the WIRE CONTRACT independently of the
    installed redis version — the measured bytes are the thing that defeated
    an exit-code-only reader, and a future redis-cli must not quietly rewrite
    what these arms are testing."""
    d = tmp_path / name
    d.mkdir()
    stub = d / "redis-cli"
    stub.write_text(body)
    stub.chmod(0o755)
    return str(d)


DOWN_BODY = (
    '#!/bin/bash\n'
    '# MEASURED redis-cli behaviour with the server down, stdin/pipe mode:\n'
    '# nothing on stdout, one connect error per command on stderr, EXIT 0.\n'
    'cat > /dev/null\n'
    'echo "Could not connect to Redis at 127.0.0.1:9: Connection refused" >&2\n'
    'echo "Could not connect to Redis at 127.0.0.1:9: Connection refused" >&2\n'
    'exit 0\n'
)
HEALTHY_BODY = (
    '#!/bin/bash\n'
    '# The healthy wire shape: MULTI -> OK, one QUEUED per command, EXEC -> results.\n'
    'n=$(cat | grep -c .)\n'
    'echo OK\n'
    'i=2\n'
    'while [ "$i" -lt "$n" ]; do echo QUEUED; i=$((i+1)); done\n'
    'echo 1\n'
    'exit 0\n'
)


@needs_redis
def test_stdin_mode_exit0_empty_stdout_must_read_as_failure(tmp_path, monkeypatch):
    """THE DECISIVE ARM for the positive-confirmation rule.

    With a stub `redis-cli` reproducing the measured down-server bytes
    (exit 0, empty stdout, errors on stderr), a reader that checks only the
    exit code returns True — the watermark advances and the spend is silently
    lost. ``_redis_atomic`` must return False here.
    """
    stub_dir = _stub_cli(tmp_path, "downbin", DOWN_BODY)
    # PREMISE, verified rather than assumed: the stub really does exit 0 with
    # empty stdout. If this ever stops being true the arm below is vacuous.
    probe = subprocess.run([os.path.join(stub_dir, "redis-cli")], input="MULTI\nEXEC\n",
                           capture_output=True, text=True, timeout=15)
    assert probe.returncode == 0 and probe.stdout == "" and probe.stderr.strip()

    monkeypatch.setenv("PATH", stub_dir + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "9")
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"]]) is False
    assert meter.record_lane("advisor", "cos", cost_micro=1) is False

    sl = meter.TranscriptSlice(cost_micro=1, input_tokens=1, responses_billed=1,
                               last={"input": 1, "output": 0, "cache_write": 0,
                                     "cache_read": 0, "cost_micro": 1,
                                     "model": "claude-opus-4-8", "context_tokens": 1})
    assert meter.record_session_turn("cos", sl) is False


@needs_redis
def test_healthy_wire_bytes_still_confirm_a_write(tmp_path, monkeypatch):
    """NON-VACUITY twin of the arm above: the positive-confirmation check must
    not simply refuse everything. Same stub mechanism, healthy bytes."""
    stub_dir = _stub_cli(tmp_path, "okbin", HEALTHY_BODY)
    monkeypatch.setenv("PATH", stub_dir + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "9")
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"]]) is True
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"],
                                ["EXPIRE", "k", "10"]]) is True


@needs_redis
def test_dirty_stderr_is_a_failure_even_when_stdout_looks_healthy(tmp_path, monkeypatch):
    """The stderr layer, isolated.

    Found 2026-07-27 while proving these arms both ways: with the server fully
    down, stdout is EMPTY, so the `lines[0] != "OK"` check already catches it
    and deleting the stderr check changed nothing — the layer was there but
    unfalsifiable. Its own failure mode is a connection that dies PART WAY
    through the script: redis-cli has already printed OK/QUEUED, the reply
    stream looks complete, and the only evidence of loss is on stderr.
    """
    body = ('#!/bin/bash\ncat > /dev/null\necho OK\necho QUEUED\necho 1\n'
            'echo "Error: Server closed the connection" >&2\nexit 0\n')
    stub_dir = _stub_cli(tmp_path, "dirtybin", body)
    monkeypatch.setenv("PATH", stub_dir + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "9")
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"]]) is False, (
        "a healthy-LOOKING reply stream with errors on stderr must not confirm "
        "a write — the watermark would advance over spend that never landed")


@needs_redis
def test_a_short_queued_reply_is_a_failure_not_a_success(tmp_path, monkeypatch):
    """One QUEUED for two commands = a command was rejected. Counting the
    QUEUEDs is what makes a partial MULTI visible at all."""
    body = ('#!/bin/bash\ncat > /dev/null\necho OK\necho QUEUED\necho 1\nexit 0\n')
    stub_dir = _stub_cli(tmp_path, "shortbin", body)
    monkeypatch.setenv("PATH", stub_dir + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "9")
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"]]) is True     # 1 cmd, 1 QUEUED
    assert meter._redis_atomic([["HINCRBY", "k", "f", "1"],
                                ["EXPIRE", "k", "10"]]) is False        # 2 cmds, 1 QUEUED


# =========================================================================
# 4. A SHORTER TRANSCRIPT MUST SELF-HEAL, NOT GO DARK
# =========================================================================

@needs_redis
def test_rotated_transcript_self_heals_instead_of_going_permanently_dark(plane, tmp_path, monkeypatch):
    """A rotated/replaced/truncated transcript is now SHORTER than its
    watermark. Without the reset every later Stop is skipped forever, because
    `from_line` can never be reached again — a silent, permanent blackout for
    that officer."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1, R2, R3])
    assert meter.write_watermark("sess-R", 5000) is True

    assert record_turn.main(["--transcript", str(t), "--session", "sess-R",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == FIRST_SLICE_MICRO, (
        "a stale high watermark must not swallow the whole file")
    assert meter.read_watermark("sess-R") == 3, "the watermark must be REPAIRED"

    # And the repaired mark behaves normally from there on.
    _append(t, [R4])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-R",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == FIRST_SLICE_MICRO + R4_MICRO


@needs_redis
def test_rotated_transcript_with_nothing_billable_still_repairs_the_mark(plane, tmp_path, monkeypatch):
    """The zero-response branch: nothing to bill, but the mark still has to be
    fixed or the session stays dark until the file grows past the stale mark."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [{"type": "user", "message": {"content": "hi"}}])
    assert meter.write_watermark("sess-S", 900) is True

    cp = _run_cli(plane, t, session="sess-S")
    assert cp.returncode == 0
    assert "watermark reset" in cp.stdout
    assert meter.read_watermark("sess-S") == 1
    assert plane.keys("cabinet:cost:tokens:daily:*") == []


# =========================================================================
# 5. THE STOP-HOOK CONTRACT — exit 0, and stdout that cannot corrupt the
#    `{"decision":"block"}` JSON protocol
# =========================================================================

@needs_redis
@pytest.mark.parametrize("case", [
    "redis_down", "missing_transcript", "malformed_json",
    "non_numeric_tokens", "unattributable_officer", "healthy",
])
def test_cli_always_exits_zero_with_protocol_safe_stdout(case, plane, dead_port, tmp_path):
    """Every failure mode the Stop hook can hand this thing.

    Two properties, both fatal to lose: the officer's turn must survive a
    metering failure (exit 0, always), and stdout must never carry anything a
    JSON-reading Stop protocol could mistake for a decision object.
    """
    t = tmp_path / "t.jsonl"
    port, officer = plane.port, "cos"
    if case == "redis_down":
        _write(t, [R1]); port = dead_port
    elif case == "missing_transcript":
        t = tmp_path / "does-not-exist.jsonl"
    elif case == "malformed_json":
        with open(t, "w") as fh:
            fh.write("not json at all\n")
            fh.write('{"unterminated\n')
            fh.write(json.dumps(R1) + "\n")
    elif case == "non_numeric_tokens":
        with open(t, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {
                "id": "bad", "model": "claude-opus-4-8",
                "usage": {"input_tokens": "quite a lot", "output_tokens": 0,
                          "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0}}}) + "\n")
            fh.write(json.dumps(R1) + "\n")
    elif case == "unattributable_officer":
        _write(t, [R1]); officer = "cos; rm -rf /"
    else:
        _write(t, [R1])

    cp = _run_cli(port, t, officer=officer, session="sess-%s" % case)

    assert cp.returncode == 0, (
        "a metering failure must never break the officer's turn; stderr=%r" % cp.stderr)
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        assert line.startswith("cost-meter: "), (
            "every stdout line must be an identifiable meter line: %r" % line)
        # The JSON-shaped forms only: a future meter line is allowed to use
        # these words in prose, it is not allowed to emit the protocol.
        assert '"decision"' not in line
        assert '"continue"' not in line and '"block"' not in line
    assert not cp.stdout.lstrip().startswith("{")
    with pytest.raises(ValueError):
        json.loads(cp.stdout or "")


@needs_redis
def test_a_poison_usage_line_does_not_wedge_the_session(plane, tmp_path, monkeypatch):
    """Before the guard, a non-numeric token count raised out of the parse
    loop: the watermark never advanced and every later Stop re-read the same
    poison line. The good response AFTER it must still be billed and the mark
    must move past it."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    with open(t, "w") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {
            "id": "bad", "model": "claude-opus-4-8",
            "usage": {"input_tokens": {"nested": "junk"}, "output_tokens": 0,
                      "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}}}) + "\n")
        fh.write(json.dumps(R1) + "\n")

    assert record_turn.main(["--transcript", str(t), "--session", "sess-W",
                             "--officer", "cos"]) == 0
    assert plane.ledger_field("cos_cost_micro") == R1_MICRO
    assert meter.read_watermark("sess-W") == 2


@needs_redis
def test_unattributable_officer_writes_no_ledger_at_all(plane, tmp_path, monkeypatch):
    """Spend we cannot attribute is still spend, but writing it against a
    bogus field would corrupt per-officer accounting. Refuse, loudly."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1])
    cp = _run_cli(plane, t, officer="", session="sess-U")
    assert cp.returncode == 0
    assert "SKIP" in cp.stdout and "NOT metered" in cp.stdout
    assert plane.keys("cabinet:cost:*") == []
    assert meter.record_session_turn("Robert'); DROP TABLE", meter.parse_transcript(str(t))) is False
    assert plane.keys("cabinet:cost:*") == []


@needs_redis
def test_project_scoped_officers_get_their_own_field_prefix(plane, tmp_path, monkeypatch):
    """FW-072 pool-mode field shape: `<officer>_<project>_<dim>`."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [R1])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-X",
                             "--officer", "cos", "--project", "widgets"]) == 0
    assert plane.ledger_field("cos_widgets_cost_micro") == R1_MICRO
    assert plane.ledger_field("cos_cost_micro") == 0
    # The latest-turn hash stays keyed on the OFFICER — the dashboard reads it
    # by officer, not by officer+project.
    assert meter.hgetall("cabinet:cost:tokens:cos") is not None


@needs_redis
def test_a_hostile_model_string_cannot_desync_the_hgetall_parser(plane, tmp_path, monkeypatch):
    """`hgetall` parses redis-cli output as LINE PAIRS. A newline or space in
    the model name would shift every later field by one and silently rename
    the whole hash."""
    _point_meter_at(monkeypatch, plane.port)
    t = tmp_path / "t.jsonl"
    _write(t, [_assistant("m1", model="claude-opus-4-8\nlast_context_pct\n999",
                          input_tokens=100_000)])
    assert record_turn.main(["--transcript", str(t), "--session", "sess-Y",
                             "--officer", "cos"]) == 0
    h = meter.hgetall("cabinet:cost:tokens:cos")
    assert h is not None
    assert set(h) == {"last_input", "last_output", "last_cache_write",
                      "last_cache_read", "last_cost_micro", "last_model",
                      "last_context_tokens", "last_context_pct", "last_updated"}
    assert "\n" not in h["last_model"] and " " not in h["last_model"]
    assert h["last_context_pct"] == "10"   # 100k of a 1M window, not 999


# =========================================================================
# 6. hgetall's TRI-STATE — None (could not look) vs {} (looked, empty)
# =========================================================================

@needs_redis
def test_hgetall_tri_state_never_collapses(plane, dead_port, monkeypatch):
    """Load-bearing for the `meter-silent` watchdog row: `None` SKIPS (no
    observation available) while `{}` with officers who worked today is the
    ALARM. Collapsing them either way silences a dead meter or cries wolf on
    every Redis blip."""
    _point_meter_at(monkeypatch, plane.port)
    assert meter.hgetall("cabinet:cost:tokens:daily:1970-01-01") == {}

    plane.cli("HSET", "cabinet:cost:tokens:daily:1970-01-01", "cos_cost_micro", "42")
    assert meter.hgetall("cabinet:cost:tokens:daily:1970-01-01") == {"cos_cost_micro": "42"}

    _point_meter_at(monkeypatch, dead_port)
    assert meter.hgetall("cabinet:cost:tokens:daily:1970-01-01") is None


@needs_redis
def test_hgetall_parses_multi_field_hashes_in_order(plane, monkeypatch):
    _point_meter_at(monkeypatch, plane.port)
    k = "cabinet:cost:tokens:daily:1970-01-02"
    plane.cli("HSET", k, "cos_input", "1", "cos_output", "2",
              "cos_cost_micro", "3", "cto_cost_micro", "4")
    h = meter.hgetall(k)
    assert h == {"cos_input": "1", "cos_output": "2",
                 "cos_cost_micro": "3", "cto_cost_micro": "4"}
    assert meter.sum_cost_micro(h.keys(), h) == 7


# =========================================================================
# 7. THE LANE LEDGER
# =========================================================================

@needs_redis
def test_record_lane_writes_the_documented_field_shape(plane, monkeypatch):
    _point_meter_at(monkeypatch, plane.port)
    assert meter.record_lane("advisor", "cos", cost_micro=1234, units=7, calls=2) is True

    key = meter.daily_lane_key()
    h = meter.hgetall(key)
    assert h == {
        "advisor_calls": "2",
        "advisor_units": "7",
        "advisor__cos_calls": "2",
        "advisor_cost_micro": "1234",
        "advisor__cos_cost_micro": "1234",
    }
    assert 0 < int(plane.cli("TTL", key).stdout.strip()) <= 691200

    # Lanes are a SEPARATE ledger: folding them into the officer hash would
    # change what `*_cost_micro` means for any fork still running a cap.
    assert plane.keys("cabinet:cost:tokens:daily:*") == []
    assert meter.record_lane("advisor", "cos", cost_micro=1, calls=1) is True
    assert meter.hgetall(key)["advisor_calls"] == "3"


@needs_redis
def test_unpriced_lane_records_calls_and_never_a_dollar_figure(plane, monkeypatch):
    """"1,240 calls (unpriced)" is true; "$0.00" is a lie, and this meter
    exists because of a lie like that."""
    _point_meter_at(monkeypatch, plane.port)
    assert meter.record_lane("embeddings", "svc:brain", units=5000, calls=3) is True
    h = meter.hgetall(meter.daily_lane_key())
    assert h == {"embeddings_calls": "3", "embeddings_units": "5000",
                 "embeddings__svc:brain_calls": "3"}
    assert not [f for f in h if f.endswith("_cost_micro")], (
        "an unpriced lane must not materialize a cost field at all — a 0 there "
        "renders as $0.00 and reads as 'this lane is free'")


@needs_redis
def test_unknown_lane_is_refused_and_writes_nothing(plane, monkeypatch):
    _point_meter_at(monkeypatch, plane.port)
    for bad in ("not-a-lane", "", "advisor; FLUSHALL", "ADVISOR"):
        assert meter.record_lane(bad, "cos", cost_micro=999) is False, bad
    assert plane.keys("cabinet:cost:*") == []


@needs_redis
def test_lane_principal_is_sanitized_before_it_becomes_a_field_name(plane, monkeypatch):
    """The principal reaches a redis-cli argv and becomes a hash FIELD NAME,
    and it arrives from an environment variable."""
    _point_meter_at(monkeypatch, plane.port)
    assert meter.record_lane("api_direct", "cos\nFLUSHALL", calls=1, cost_micro=5) is True
    h = meter.hgetall(meter.daily_lane_key())
    assert "api_direct__unattributed_calls" in h
    assert h["api_direct_cost_micro"] == "5"
    assert not any("FLUSHALL" in f for f in h)
