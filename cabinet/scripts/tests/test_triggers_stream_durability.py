"""Adversarial delivery tests for the Redis trigger stream.

The trigger library is shell code, so these tests exercise it against an
isolated real Redis process.  They pin the two guarantees a routing caller
depends on: acknowledging one message cannot evict another pending payload,
and a failed XADD is a failed trigger_send (with no false wake).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import uuid

import pytest


REPO = Path(__file__).resolve().parents[3]


def _redis_cli(port: int, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["redis-cli", "--raw", "-h", "127.0.0.1", "-p", str(port), *args],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def redis_port(tmp_path: Path):
    if not shutil.which("redis-server") or not shutil.which("redis-cli"):
        pytest.skip("redis-server and redis-cli are required")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    process = subprocess.Popen(
        [
            "redis-server",
            "--bind", "127.0.0.1",
            "--port", str(port),
            "--protected-mode", "no",
            "--save", "",
            "--appendonly", "no",
            "--dir", str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            if _redis_cli(port, "PING").stdout.strip() == "PONG":
                break
            if process.poll() is not None:
                pytest.fail(f"redis-server exited early: {process.stderr.read()}")
            time.sleep(0.02)
        else:
            pytest.fail("isolated redis-server did not become ready")
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _run_trigger_shell(port: int, body: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        CABINET_ROOT=str(REPO),
        REDIS_HOST="127.0.0.1",
        REDIS_PORT=str(port),
        OFFICER_NAME="durability-test",
    )
    env.update(extra_env)
    return subprocess.run(
        [
            "bash",
            "-c",
            '. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"\n'
            "trigger_wake_officer() { :; }\n"
            + body,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )


def test_ack_trim_preserves_oldest_pending_payload_after_large_backlog(redis_port: int):
    target = f"durability{uuid.uuid4().hex[:8]}"
    result = _run_trigger_shell(
        redis_port,
        f"""
target={target!r}
for i in $(seq 1 500); do
  trigger_send "$target" "message-$i" || exit 20
done
trigger_read "$target" >/dev/null || exit 21
ids_file=$(trigger_ids_path "$target") || exit 22
read -r -a ids < "$ids_file"
[ "${{#ids[@]}}" -eq 50 ] || exit 23
oldest="${{ids[0]}}"
# ACK a later delivery while the oldest one remains pending.  The retired
# MAXLEN~100 trim deleted that oldest payload once the backlog exceeded 100.
trigger_ack "$target" "${{ids[49]}}"
printf '%s\n' "$oldest"
""",
    )
    assert result.returncode == 0, result.stderr
    oldest = result.stdout.strip().splitlines()[-1]
    stream = f"cabinet:triggers:{target}"
    group = f"officer-{target}"

    payload = _redis_cli(redis_port, "XRANGE", stream, oldest, oldest)
    assert payload.returncode == 0, payload.stderr
    assert oldest in payload.stdout
    assert "message-1" in payload.stdout

    pending = _redis_cli(redis_port, "XPENDING", stream, group, "-", "+", "100")
    assert pending.returncode == 0, pending.stderr
    assert oldest in pending.stdout


def test_ack_with_empty_pending_list_is_set_e_safe_and_keeps_boundary(redis_port: int):
    target = f"emptyipel{uuid.uuid4().hex[:8]}"
    result = _run_trigger_shell(
        redis_port,
        f"""
set -euo pipefail
target={target!r}
trigger_send "$target" "only-message"
trigger_read "$target" >/dev/null
ids_file=$(trigger_ids_path "$target")
ids=$(cat "$ids_file")
trigger_ack "$target" "$ids"
printf 'survived-set-e\\n'
""",
    )
    assert result.returncode == 0, result.stderr
    assert "survived-set-e" in result.stdout

    stream = f"cabinet:triggers:{target}"
    rows = _redis_cli(redis_port, "XRANGE", stream, "-", "+")
    assert rows.returncode == 0, rows.stderr
    # MINID retains the last-delivered boundary itself; an unread/pending item
    # can never be on the removed side of that boundary.
    assert "only-message" in rows.stdout


def test_observe_receipt_ack_clears_only_its_officer_pending_entry(redis_port: int):
    target = f"observeack{uuid.uuid4().hex[:8]}"
    delivered = _run_trigger_shell(
        redis_port,
        f"""
target={target!r}
trigger_send "$target" "observe-message" || exit 40
trigger_read "$target" >/dev/null || exit 41
cat "$(trigger_ids_path "$target")"
""",
        OFFICER_NAME=target,
    )
    assert delivered.returncode == 0, delivered.stderr
    receipt = delivered.stdout.strip().splitlines()[-1].strip()
    assert receipt and " " not in receipt

    env = os.environ.copy()
    env.update(
        CABINET_ROOT=str(REPO),
        CABINET_OBSERVE_ONLY="1",
        OFFICER_NAME=target,
        REDIS_HOST="127.0.0.1",
        REDIS_PORT=str(redis_port),
    )
    first = subprocess.run(
        ["/bin/bash", str(REPO / "cabinet/scripts/hooks/observe-ack.sh"), receipt],
        env=env, text=True, capture_output=True, check=False, timeout=10,
    )
    assert first.returncode == 0, first.stderr
    assert "newly_acknowledged=1" in first.stdout
    pending = _redis_cli(
        redis_port, "XPENDING", f"cabinet:triggers:{target}", f"officer-{target}",
    )
    assert pending.stdout.strip().splitlines()[0] == "0"

    repeat = subprocess.run(
        ["/bin/bash", str(REPO / "cabinet/scripts/hooks/observe-ack.sh"), receipt],
        env=env, text=True, capture_output=True, check=False, timeout=10,
    )
    assert repeat.returncode == 0, repeat.stderr
    assert "already_clear=1" in repeat.stdout


def test_trim_fails_safe_when_a_second_group_has_unread_payloads(redis_port: int):
    target = f"multigroup{uuid.uuid4().hex[:8]}"
    observer = f"observer-{target}"
    result = _run_trigger_shell(
        redis_port,
        f"""
target={target!r}
stream="cabinet:triggers:$target"
for i in $(seq 1 150); do
  trigger_send "$target" "message-$i" || exit 30
done
redis-cli -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
  XGROUP CREATE "$stream" {observer!r} 0 >/dev/null || exit 31
for _batch in 1 2 3; do
  trigger_read "$target" >/dev/null || exit 32
  ids_file=$(trigger_ids_path "$target") || exit 33
  ids=$(cat "$ids_file")
  trigger_ack "$target" "$ids"
done
""",
    )
    assert result.returncode == 0, result.stderr
    stream = f"cabinet:triggers:{target}"
    assert _redis_cli(redis_port, "XLEN", stream).stdout.strip() == "150"

    unread = _redis_cli(
        redis_port,
        "XREADGROUP", "GROUP", observer, "observer-worker", "COUNT", "1",
        "STREAMS", stream, ">",
    )
    assert unread.returncode == 0, unread.stderr
    assert "message-1" in unread.stdout


def test_xadd_failure_returns_nonzero_and_does_not_wake(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_redis = fake_bin / "redis-cli"
    fake_redis.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" XADD \"*) echo 'simulated XADD failure' >&2; exit 1 ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    fake_redis.chmod(0o700)
    wake_log = tmp_path / "wake.log"
    env = os.environ.copy()
    env.update(
        CABINET_ROOT=str(REPO),
        REDIS_HOST="127.0.0.1",
        REDIS_PORT="6379",
        OFFICER_NAME="durability-test",
        WAKE_LOG=str(wake_log),
        PATH=f"{fake_bin}:{env['PATH']}",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            '. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"\n'
            'trigger_wake_officer() { printf "woke\\n" >> "$WAKE_LOG"; }\n'
            'trigger_send "cos" "must-not-disappear"\n',
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "trigger NOT queued" in result.stderr
    assert not wake_log.exists()


def test_restart_keeps_same_consumer_pending_recoverable_and_delconsumer_has_teeth(
    redis_port: int,
):
    """AUD-12-R1 (2026-07-16 corrective amendment): proves both halves of the
    trigger-retention fix in one isolated Redis instance — (1) the retained
    stable `channel` consumer identity lets a restarted reader recover its own
    still-pending entry via ID `0` and ACK it exactly once, and (2) as a
    negative control, the retired `XGROUP DELCONSUMER` cleanup this replaces
    really does destroy that recoverability (proving the assertion above has
    teeth, not just that Redis can re-deliver)."""
    token = uuid.uuid4().hex[:8]
    stream = f"cabinet:triggers:restart-{token}"
    group = f"officer-restart-{token}"
    message_id = _redis_cli(
        redis_port, "XADD", stream, "*", "message", "survives-restart"
    ).stdout.strip()
    assert _redis_cli(redis_port, "XGROUP", "CREATE", stream, group, "0").returncode == 0

    first = _redis_cli(
        redis_port, "XREADGROUP", "GROUP", group, "channel", "COUNT", "1",
        "STREAMS", stream, ">",
    )
    assert message_id in first.stdout
    before = _redis_cli(redis_port, "XPENDING", stream, group, "-", "+", "10")
    assert before.stdout.strip().splitlines()[-1] == "1"

    # Replacement process, same stable consumer: index.ts processPending()
    # reads ID 0 before new entries. Redis re-delivers the owned receipt.
    restarted = _redis_cli(
        redis_port, "XREADGROUP", "GROUP", group, "channel", "COUNT", "1",
        "STREAMS", stream, "0",
    )
    assert message_id in restarted.stdout
    assert "survives-restart" in restarted.stdout
    after = _redis_cli(redis_port, "XPENDING", stream, group, "-", "+", "10")
    assert after.stdout.strip().splitlines()[-1] == "2"
    assert _redis_cli(redis_port, "XACK", stream, group, message_id).stdout.strip() == "1"
    assert _redis_cli(redis_port, "XACK", stream, group, message_id).stdout.strip() == "0"

    # Negative control: the retired launcher command destroys ownership.
    doomed_stream = f"cabinet:triggers:doomed-{token}"
    doomed_group = f"officer-doomed-{token}"
    doomed_id = _redis_cli(
        redis_port, "XADD", doomed_stream, "*", "message", "doomed-by-delete"
    ).stdout.strip()
    assert _redis_cli(
        redis_port, "XGROUP", "CREATE", doomed_stream, doomed_group, "0"
    ).returncode == 0
    assert doomed_id in _redis_cli(
        redis_port, "XREADGROUP", "GROUP", doomed_group, "channel", "COUNT", "1",
        "STREAMS", doomed_stream, ">",
    ).stdout
    assert _redis_cli(
        redis_port, "XGROUP", "DELCONSUMER", doomed_stream, doomed_group, "channel"
    ).stdout.strip() == "1"
    cannot_recover = _redis_cli(
        redis_port, "XREADGROUP", "GROUP", doomed_group, "channel", "COUNT", "1",
        "STREAMS", doomed_stream, "0",
    )
    assert doomed_id not in cannot_recover.stdout
    assert _redis_cli(redis_port, "XPENDING", doomed_stream, doomed_group).stdout.splitlines()[0] == "0"
    assert doomed_id in _redis_cli(
        redis_port, "XRANGE", doomed_stream, doomed_id, doomed_id
    ).stdout
