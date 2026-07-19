"""Audit #32 — the ACK-trim must never run AHEAD of the daily exhaust-archive.

``trigger_ack`` trims to the officer-ACK boundary (oldest-pending / last-
delivered), but ``exhaust-archive.py`` reads the stream via a per-stream cursor
on a DAILY 04:40 sweep. Between sweeps, an officer that ACKs a batch would trim
acked-but-unarchived entries before the archive ever saw them — the durable
"who was told what when" trail lost. The fix clamps the trim boundary to the
archive's durable cursor (``CABINET_EXHAUST_STATE`` overrides the path); an
unknown/corrupt cursor fails SAFE (retain all); ``CABINET_TRIGGER_TRIM_IGNORE_
ARCHIVE=1`` opts out.

Pins (isolated Redis): with the archive cursor at trigger #5, ACKing all 30
trims only #1-4 and #6-30 SURVIVE; no state file -> nothing trimmed; the
opt-out env trims to the officer boundary. A MUTANT that drops the clamp trims
to #30 and erases #6-30, turning the first test red.

Run: python3.12 -m pytest cabinet/scripts/tests/test_triggers_archive_clamp.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_ID_RE = re.compile(r"^\d+-\d+$")


@pytest.fixture
def redis_port(tmp_path: Path):
    if not shutil.which("redis-server") or not shutil.which("redis-cli"):
        pytest.skip("redis-server and redis-cli are required")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    proc = subprocess.Popen(
        ["redis-server", "--bind", "127.0.0.1", "--port", str(port),
         "--protected-mode", "no", "--save", "", "--appendonly", "no",
         "--dir", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            if _cli(port, "PING").stdout.strip() == "PONG":
                break
            if proc.poll() is not None:
                pytest.fail(f"redis-server exited early: {proc.stderr.read()}")
            time.sleep(0.02)
        else:
            pytest.fail("isolated redis-server did not become ready")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def _cli(port: int, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["redis-cli", "--raw", "-h", "127.0.0.1", "-p", str(port), *args],
        text=True, capture_output=True, check=False)


def _shell(port: int, body: str, **extra_env: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(CABINET_ROOT=str(REPO), REDIS_HOST="127.0.0.1",
               REDIS_PORT=str(port), OFFICER_NAME="archive-clamp-test")
    env.update(extra_env)
    return subprocess.run(
        ["bash", "-c",
         '. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"\n'
         "trigger_wake_officer() { :; }\n" + body],
        text=True, capture_output=True, env=env, check=False, timeout=45)


def _stream_ids(port: int, stream: str) -> list[str]:
    out = _cli(port, "XRANGE", stream, "-", "+").stdout
    return [ln for ln in out.splitlines() if _ID_RE.match(ln)]


def _survived_msgs(port: int, stream: str) -> set[int]:
    """The exact set of surviving message numbers (greedy \\d+ so `msg-1` never
    matches `msg-10`)."""
    out = _cli(port, "XRANGE", stream, "-", "+").stdout
    return {int(m.group(1)) for m in re.finditer(r"msg-(\d+)", out)}


def _send_30(port: int, target: str) -> None:
    r = _shell(port, f"""
target={target!r}
for i in $(seq 1 30); do trigger_send "$target" "msg-$i" || exit 20; done
""")
    assert r.returncode == 0, r.stderr


def _read_and_ack_all(port: int, target: str, **env: str) -> subprocess.CompletedProcess:
    return _shell(port, f"""
target={target!r}
trigger_read "$target" >/dev/null || exit 21
ids_file=$(trigger_ids_path "$target") || exit 22
trigger_ack "$target" "$(cat "$ids_file")"
""", **env)


def test_ack_trim_clamped_to_archive_cursor(redis_port, tmp_path):
    target = f"archclamp{uuid.uuid4().hex[:8]}"
    stream = f"cabinet:triggers:{target}"
    _send_30(redis_port, target)

    ids = _stream_ids(redis_port, stream)
    assert len(ids) == 30
    fifth = ids[4]
    state = tmp_path / "exhaust-archive.json"
    state.write_text(json.dumps({"last_ids": {stream: fifth}}))

    r = _read_and_ack_all(redis_port, target, CABINET_EXHAUST_STATE=str(state))
    assert r.returncode == 0, r.stderr

    # MINID = archive cursor (#5) retains #5..#30, trims only #1..#4. A MUTANT
    # that drops the clamp trims to the officer boundary (#30) and erases #6..#30.
    survived = _survived_msgs(redis_port, stream)
    assert survived == set(range(5, 31)), f"unexpected survivors: {sorted(survived)}"


def test_missing_archive_state_retains_everything(redis_port, tmp_path):
    target = f"archnostate{uuid.uuid4().hex[:8]}"
    stream = f"cabinet:triggers:{target}"
    _send_30(redis_port, target)
    r = _read_and_ack_all(redis_port, target,
                          CABINET_EXHAUST_STATE=str(tmp_path / "does-not-exist.json"))
    assert r.returncode == 0, r.stderr
    assert _survived_msgs(redis_port, stream) == set(range(1, 31)), \
        "entries trimmed despite an unknown archive cursor (must retain all)"


def test_ignore_archive_env_trims_to_officer_boundary(redis_port, tmp_path):
    """The documented opt-out: a deployment without the archive can still keep
    streams lean — trims to the officer boundary (all acked -> last-delivered)."""
    target = f"archignore{uuid.uuid4().hex[:8]}"
    stream = f"cabinet:triggers:{target}"
    _send_30(redis_port, target)
    # a state file EXISTS with an early cursor, but the opt-out must ignore it
    state = tmp_path / "exhaust-archive.json"
    state.write_text(json.dumps({"last_ids": {stream: _stream_ids(redis_port, stream)[4]}}))
    r = _read_and_ack_all(redis_port, target,
                          CABINET_EXHAUST_STATE=str(state),
                          CABINET_TRIGGER_TRIM_IGNORE_ARCHIVE="1")
    assert r.returncode == 0, r.stderr
    # boundary = last-delivered (#30); MINID #30 retains only #30
    assert len(_stream_ids(redis_port, stream)) == 1
    assert _survived_msgs(redis_port, stream) == {30}
