"""Focused, isolated proofs for the Redis Streams exact-state sidecar."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "cabinet/scripts/lib/redis_state.py"
SHELL_LIB = ROOT / "cabinet/scripts/lib/redis-state.sh"
SPEC = importlib.util.spec_from_file_location("cabinet_redis_stream_repair", TOOL)
assert SPEC and SPEC.loader
redis_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redis_state
SPEC.loader.exec_module(redis_state)


def _hex(value: bytes) -> str:
    return value.hex()


def _manifest(*records: str, databases: int = 1) -> str:
    return "\n".join(
        ["FORMAT redis-stream-repair-v1", f"DATABASES {databases}", *records, ""]
    )


def test_stream_repair_parser_is_strict_and_privacy_safe(tmp_path: Path):
    key = b"stream secret\x00\xff"
    group = b"group secret\x00"
    consumer = b"consumer secret\xff"
    stream_id = b"1700" + b"000000000-4"
    path = tmp_path / "repair.manifest"
    path.write_text(
        _manifest(
            f"CONSUMER 0 {_hex(key)} {_hex(group)} {_hex(consumer)}",
            f"PEL 0 {_hex(key)} {_hex(group)} {_hex(stream_id)} {_hex(consumer)} 9",
        ),
        encoding="ascii",
    )

    parsed = redis_state.parse_stream_repair(path)

    assert parsed.databases == 1
    assert len(parsed.consumers) == 1
    assert len(parsed.pel) == 1
    rendered = path.read_text(encoding="ascii")
    assert "stream secret" not in rendered
    assert "group secret" not in rendered
    assert "consumer secret" not in rendered


def test_stream_repair_parser_preserves_empty_binary_identifiers(tmp_path: Path):
    path = tmp_path / "empty.manifest"
    path.write_text(_manifest("CONSUMER 0   "), encoding="ascii")

    parsed = redis_state.parse_stream_repair(path)

    assert parsed.consumers == frozenset(
        {redis_state.StreamConsumer(0, "", "", "")}
    )


@pytest.mark.parametrize(
    "record",
    [
        "CONSUMER 0 0 00 00",  # odd-length hex
        "CONSUMER 0 AA 00 00",  # uppercase hex
        "PEL 0 00 00 6e6f742d616e2d6964 00 1",  # non-stream id
        "PEL 0 00 00 312d30 01 1",  # owner missing from consumers
        "PEL 0 00 00 312d30 00 -1",  # negative delivery count
    ],
)
def test_stream_repair_parser_rejects_malformed_or_incomplete_records(
    tmp_path: Path, record: str
):
    path = tmp_path / "bad.manifest"
    path.write_text(_manifest(record), encoding="ascii")

    with pytest.raises(redis_state.FingerprintError):
        redis_state.parse_stream_repair(path)


def test_stream_repair_diff_discloses_only_component_and_hashed_key(tmp_path: Path):
    key = b"private-stream-name"
    group = b"private-group"
    owner = b"private-owner"
    idle = b"private-idle"
    stream_id = b"1-0"
    expected_path = tmp_path / "expected"
    actual_path = tmp_path / "actual"
    expected_path.write_text(
        _manifest(
            f"CONSUMER 0 {_hex(key)} {_hex(group)} {_hex(owner)}",
            f"CONSUMER 0 {_hex(key)} {_hex(group)} {_hex(idle)}",
            f"PEL 0 {_hex(key)} {_hex(group)} {_hex(stream_id)} {_hex(owner)} 7",
        ),
        encoding="ascii",
    )
    actual_path.write_text(
        _manifest(
            f"CONSUMER 0 {_hex(key)} {_hex(group)} {_hex(owner)}",
            f"PEL 0 {_hex(key)} {_hex(group)} {_hex(stream_id)} {_hex(owner)} 2",
        ),
        encoding="ascii",
    )

    differences = redis_state.diff_stream_repair(
        redis_state.parse_stream_repair(expected_path),
        redis_state.parse_stream_repair(actual_path),
    )

    assert differences == [
        "DB 0 TYPE stream COMPONENT consumer_identity KEY_SHA256 "
        + hashlib.sha256(key).hexdigest(),
        "DB 0 TYPE stream COMPONENT pel_delivery_count KEY_SHA256 "
        + hashlib.sha256(key).hexdigest(),
    ]
    output = "\n".join(differences)
    assert "private-stream-name" not in output
    assert "private-group" not in output
    assert "private-owner" not in output

    equal = subprocess.run(
        [
            "python3.12",
            str(TOOL),
            "stream-repair-diff",
            str(expected_path),
            str(expected_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert equal.returncode == 0
    assert equal.stdout == ""

    malformed = tmp_path / "malformed"
    malformed.write_text("not a manifest\n", encoding="ascii")
    refused = subprocess.run(
        [
            "python3.12",
            str(TOOL),
            "stream-repair-diff",
            str(expected_path),
            str(malformed),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused.returncode == 1
    assert refused.stdout == ""


pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("redis-server", "redis-cli")),
    reason="Redis binaries are unavailable",
)


class IsolatedRedis:
    def __init__(self, data: Path):
        self.data = data
        self.socket = Path(
            f"/tmp/cabinet-redis-stream-repair-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
        )

    def start(self) -> None:
        subprocess.run(
            [
                "redis-server",
                "--port",
                "0",
                "--unixsocket",
                str(self.socket),
                "--unixsocketperm",
                "700",
                "--dir",
                str(self.data),
                "--save",
                "",
                "--appendonly",
                "no",
                "--daemonize",
                "yes",
                "--pidfile",
                str(self.data / "redis.pid"),
                "--logfile",
                str(self.data / "redis.log"),
            ],
            check=True,
            timeout=20,
        )
        for _ in range(100):
            ping = subprocess.run(
                ["redis-cli", "-s", str(self.socket), "PING"],
                capture_output=True,
                timeout=2,
            )
            if ping.returncode == 0 and ping.stdout.strip() == b"PONG":
                return
            time.sleep(0.05)
        raise AssertionError("isolated Redis did not start")

    def stop(self) -> None:
        subprocess.run(
            ["redis-cli", "-s", str(self.socket), "SHUTDOWN", "NOSAVE"],
            capture_output=True,
            timeout=10,
        )
        self.socket.unlink(missing_ok=True)

    def eval_hex(self, script: str, *arguments: str) -> None:
        completed = subprocess.run(
            [
                "redis-cli",
                "-s",
                str(self.socket),
                "--raw",
                "EVAL",
                script,
                "0",
                *arguments,
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        assert completed.stdout.strip() == b"1"

    def shell(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "-c", f'. "{SHELL_LIB}"; {command}'],
            capture_output=True,
            text=True,
            timeout=60,
        )


_SEED_LUA = r'''
local function unhex(value)
  return (string.gsub(value, "..", function(pair) return string.char(tonumber(pair, 16)) end))
end
local key, group, owner, idle = unhex(ARGV[1]), unhex(ARGV[2]), unhex(ARGV[3]), unhex(ARGV[4])
redis.call("XADD", key, "1-0", unhex("6600ff"), unhex("7600ff"))
redis.call("XGROUP", "CREATE", key, group, "0")
redis.call("XGROUP", "CREATECONSUMER", key, group, idle)
redis.call("XGROUP", "CREATECONSUMER", key, group, owner)
redis.call("XREADGROUP", "GROUP", group, owner, "COUNT", 1, "STREAMS", key, ">")
redis.call("XCLAIM", key, group, owner, 0, "1-0", "JUSTID", "RETRYCOUNT", 7)
return 1
'''.strip()

_DRIFT_LUA = r'''
local function unhex(value)
  return (string.gsub(value, "..", function(pair) return string.char(tonumber(pair, 16)) end))
end
local key, group, owner, idle = unhex(ARGV[1]), unhex(ARGV[2]), unhex(ARGV[3]), unhex(ARGV[4])
redis.call("XGROUP", "DELCONSUMER", key, group, idle)
local claimed = redis.call("XCLAIM", key, group, owner, 0, "1-0", "JUSTID", "RETRYCOUNT", 2)
if #claimed ~= 1 then return redis.error_reply("test drift failed") end
return 1
'''.strip()

_DELETE_STREAM_ENTRY_LUA = r'''
local function unhex(value)
  return (string.gsub(value, "..", function(pair) return string.char(tonumber(pair, 16)) end))
end
local key = unhex(ARGV[1])
if redis.call("XDEL", key, "1-0") ~= 1 then
  return redis.error_reply("test stream entry deletion failed")
end
return 1
'''.strip()


def test_shell_sidecar_repairs_binary_consumers_and_exact_pel_idempotently(
    tmp_path: Path,
):
    redis = IsolatedRedis(tmp_path)
    redis.start()
    key = b"stream key\x00\xff"
    group = b"group\x00\xff"
    owner = b"owner\x00\xff"
    idle = b"idle\x00\xff"
    client = f'redis-cli -s "{redis.socket}"'
    source = tmp_path / "stream-repair.manifest"
    drifted = tmp_path / "drifted.manifest"
    try:
        redis.eval_hex(_SEED_LUA, _hex(key), _hex(group), _hex(owner), _hex(idle))
        expired = tmp_path / "expired.manifest"
        expired_capture = subprocess.run(
            [
                "/bin/bash",
                "-c",
                f'. "{SHELL_LIB}"; redis_stream_repair_manifest "{expired}" 1 {client}',
            ],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "REDIS_STATE_DEADLINE_EPOCH_SECONDS": "1"},
        )
        assert expired_capture.returncode != 0
        assert not expired.exists()

        captured = redis.shell(
            f'redis_stream_repair_manifest "{source}" 1 {client}'
        )
        assert captured.returncode == 0, captured.stderr
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        rendered = source.read_text(encoding="ascii")
        assert "stream key" not in rendered
        assert "group" not in rendered
        assert "owner" not in rendered
        assert "idle" not in rendered

        redis.eval_hex(_DRIFT_LUA, _hex(key), _hex(group), _hex(owner), _hex(idle))
        observed = redis.shell(
            f'redis_stream_repair_manifest "{drifted}" 1 {client}'
        )
        assert observed.returncode == 0, observed.stderr
        differences = redis.shell(
            f'redis_stream_repair_diff "{source}" "{drifted}"'
        )
        assert differences.returncode == 1
        assert "COMPONENT consumer_identity" in differences.stdout
        assert "COMPONENT pel_delivery_count" in differences.stdout
        assert "stream key" not in differences.stdout

        first = redis.shell(f'redis_stream_repair_apply "{source}" {client}')
        assert first.returncode == 0, first.stderr
        second = redis.shell(f'redis_stream_repair_apply "{source}" {client}')
        assert second.returncode == 0, second.stderr
    finally:
        redis.stop()


def test_stream_repair_preserves_matching_dangling_pel_unchanged(tmp_path: Path):
    redis = IsolatedRedis(tmp_path)
    redis.start()
    key = b"dangling stream key\x00\xff"
    group = b"dangling group\x00\xff"
    owner = b"dangling owner\x00\xff"
    idle = b"dangling idle\x00\xff"
    client = f'redis-cli -s "{redis.socket}"'
    before = tmp_path / "dangling-before.manifest"
    after = tmp_path / "dangling-after.manifest"
    try:
        redis.eval_hex(_SEED_LUA, _hex(key), _hex(group), _hex(owner), _hex(idle))
        redis.eval_hex(_DELETE_STREAM_ENTRY_LUA, _hex(key))
        captured = redis.shell(
            f'redis_stream_repair_manifest "{before}" 1 {client}'
        )
        assert captured.returncode == 0, captured.stderr

        applied = redis.shell(f'redis_stream_repair_apply "{before}" {client}')
        assert applied.returncode == 0, applied.stderr

        recaptured = redis.shell(
            f'redis_stream_repair_manifest "{after}" 1 {client}'
        )
        assert recaptured.returncode == 0, recaptured.stderr
        redis_state.compare_stream_repair(
            redis_state.parse_stream_repair(before),
            redis_state.parse_stream_repair(after),
        )
        assert before.read_bytes() == after.read_bytes()
    finally:
        redis.stop()


@pytest.mark.parametrize("mismatch", ["owner", "delivery_count"])
def test_stream_repair_refuses_mismatched_dangling_pel_without_mutation(
    tmp_path: Path, mismatch: str
):
    redis = IsolatedRedis(tmp_path)
    redis.start()
    key = b"private dangling stream\x00\xff"
    group = b"private dangling group\x00\xff"
    owner = b"private dangling owner\x00\xff"
    idle = b"private dangling idle\x00\xff"
    client = f'redis-cli -s "{redis.socket}"'
    before = tmp_path / "actual-before.manifest"
    requested = tmp_path / "mismatched-request.manifest"
    after = tmp_path / "actual-after.manifest"
    try:
        redis.eval_hex(_SEED_LUA, _hex(key), _hex(group), _hex(owner), _hex(idle))
        redis.eval_hex(_DELETE_STREAM_ENTRY_LUA, _hex(key))
        captured = redis.shell(
            f'redis_stream_repair_manifest "{before}" 1 {client}'
        )
        assert captured.returncode == 0, captured.stderr

        source = before.read_text(encoding="ascii")
        if mismatch == "owner":
            source = source.replace(
                f" {_hex(owner)} 7\n", f" {_hex(idle)} 7\n", 1
            )
        else:
            source = source.replace(f" {_hex(owner)} 7\n", f" {_hex(owner)} 8\n", 1)
        assert source != before.read_text(encoding="ascii")
        requested.write_text(source, encoding="ascii")

        refused = redis.shell(
            f'redis_stream_repair_apply "{requested}" {client}'
        )
        assert refused.returncode != 0
        assert hashlib.sha256(key).hexdigest() in refused.stderr
        assert "private dangling stream" not in refused.stderr
        assert "private dangling group" not in refused.stderr
        assert "private dangling owner" not in refused.stderr

        recaptured = redis.shell(
            f'redis_stream_repair_manifest "{after}" 1 {client}'
        )
        assert recaptured.returncode == 0, recaptured.stderr
        redis_state.compare_stream_repair(
            redis_state.parse_stream_repair(before),
            redis_state.parse_stream_repair(after),
        )
        assert before.read_bytes() == after.read_bytes()
    finally:
        redis.stop()
