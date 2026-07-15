"""Real, isolated RDB/AOF replay proofs for Redis logical fingerprints."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "cabinet/scripts/lib/redis_state.py"
SHELL_LIB = ROOT / "cabinet/scripts/lib/redis-state.sh"
SPEC = importlib.util.spec_from_file_location("cabinet_redis_state_replay", TOOL)
assert SPEC and SPEC.loader
redis_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redis_state
SPEC.loader.exec_module(redis_state)

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("redis-server", "redis-cli")),
    reason="Redis binaries are unavailable",
)


class IsolatedRedis:
    def __init__(self, data: Path, *, appendonly: bool):
        self.data = data
        self.appendonly = appendonly
        self.socket = Path(
            f"/tmp/cabinet-redis-state-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
        )
        self.starts = 0

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["redis-cli", "-s", str(self.socket), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )

    def start(self) -> None:
        self.starts += 1
        command = [
            "redis-server", "--port", "0", "--unixsocket", str(self.socket),
            "--unixsocketperm", "700", "--dir", str(self.data),
            "--appendonly", "yes" if self.appendonly else "no",
            "--appenddirname", "appendonlydir", "--save", "", "--daemonize", "yes",
            "--pidfile", str(self.data / f"redis-{self.starts}.pid"),
            "--logfile", str(self.data / f"redis-{self.starts}.log"),
        ]
        subprocess.run(command, check=True, timeout=20)
        for _ in range(100):
            try:
                if self.cli("PING").stdout.strip() == "PONG":
                    return
            except subprocess.SubprocessError:
                pass
            time.sleep(0.05)
        raise AssertionError("disposable Redis did not start")

    def stop(self) -> None:
        subprocess.run(
            ["redis-cli", "-s", str(self.socket), "SHUTDOWN", "NOSAVE"],
            capture_output=True,
            timeout=10,
        )
        self.socket.unlink(missing_ok=True)

    def fingerprint(self, path: Path, *, deadline: int | None = None) -> None:
        command = (
            f'. "{SHELL_LIB}"; '
            f'redis_state_fingerprint "{path}" v3 redis-cli -s "{self.socket}"'
        )
        env = dict(os.environ)
        if deadline is not None:
            env["REDIS_STATE_DEADLINE_EPOCH_SECONDS"] = str(deadline)
        subprocess.run(
            ["/bin/bash", "-c", command],
            check=True,
            timeout=60,
            env=env,
        )


@pytest.fixture
def redis_factory(tmp_path: Path):
    instances: list[IsolatedRedis] = []

    def factory(*, appendonly: bool) -> IsolatedRedis:
        data = tmp_path / f"redis-{len(instances)}"
        data.mkdir()
        instance = IsolatedRedis(data, appendonly=appendonly)
        instances.append(instance)
        instance.start()
        return instance

    yield factory
    for instance in instances:
        instance.stop()


def _populate_complex(redis: IsolatedRedis) -> None:
    redis.cli("SET", "string", "value")
    redis.cli("RPUSH", "list", *[str(index) for index in range(100)])
    for index in range(200):
        redis.cli("SADD", "set", f"member-{index}")
        redis.cli("HSET", "hash", f"field-{index}", f"value-{index}")
        redis.cli("ZADD", "zset", str(index), f"member-{index}")
    redis.cli("XADD", "stream", "*", "field", "one")
    deleted = redis.cli("XADD", "stream", "*", "field", "two").stdout.strip()
    redis.cli("XADD", "stream", "*", "field", "three")
    redis.cli("XDEL", "stream", deleted)
    redis.cli("XGROUP", "CREATE", "stream", "workers", "0")
    redis.cli("XGROUP", "CREATECONSUMER", "stream", "workers", "idle-consumer")
    redis.cli(
        "XREADGROUP", "GROUP", "workers", "active-consumer", "COUNT", "1",
        "STREAMS", "stream", ">",
    )
    redis.cli(
        "XREADGROUP", "GROUP", "workers", "active-consumer", "COUNT", "1",
        "STREAMS", "stream", "0",
    )


def _assert_equal(before: Path, after: Path) -> None:
    redis_state.compare(redis_state.parse(before), redis_state.parse(after))


def _finish_persistence(redis: IsolatedRedis) -> None:
    if redis.appendonly:
        redis.cli("BGREWRITEAOF")
        for _ in range(400):
            info = redis.cli("--raw", "INFO", "persistence").stdout
            if "aof_rewrite_in_progress:0" in info:
                return
            time.sleep(0.05)
        raise AssertionError("AOF rewrite did not finish")
    redis.cli("SAVE")


def test_v3_uses_real_sha256_without_exposing_key_or_value(
    tmp_path: Path, redis_factory
):
    redis = redis_factory(appendonly=False)
    redis.cli("SET", "durable-key", "durable-value")
    redis.cli("SET", "volatile-key", "volatile-value", "PX", "600000")
    state = tmp_path / "sha256.state"
    redis.fingerprint(state)
    parsed = redis_state.parse(state)

    def component(value: str) -> str:
        return f"{len(value)}:{value}"

    durable_content = hashlib.sha256(
        (component("string") + component("durable-value")).encode()
    ).hexdigest()
    durable_identity = hashlib.sha256(
        (component("durable-key") + component(durable_content)).encode()
    ).hexdigest()
    durable_db = hashlib.sha256(durable_identity.encode()).hexdigest()
    volatile_content = hashlib.sha256(
        (component("string") + component("volatile-value")).encode()
    ).hexdigest()
    volatile_key = hashlib.sha256(b"volatile-key").hexdigest()

    assert parsed.db[0].durable_digest == durable_db
    assert parsed.volatile[(0, volatile_key)].content_digest == volatile_content
    text = state.read_text()
    assert "durable-key" not in text and "durable-value" not in text
    assert "volatile-key" not in text and "volatile-value" not in text


def test_v3_sha256_handles_production_sized_values_without_lua_stack_overflow(
    tmp_path: Path, redis_factory
):
    redis = redis_factory(appendonly=False)
    key = "large-secret-key"
    value = "x" * (512 * 1024)
    redis.cli("SET", key, value)
    state = tmp_path / "large.state"
    redis.fingerprint(state)

    rendered = state.read_text()
    assert "FORMAT redis-logical-content-expiry-v3" in rendered
    assert key not in rendered
    assert value[:128] not in rendered


def test_v3_fingerprint_refuses_an_expired_caller_deadline(
    tmp_path: Path, redis_factory
):
    redis = redis_factory(appendonly=False)
    redis.cli("SET", "secret-key", "secret-value")
    state = tmp_path / "expired-deadline.state"

    with pytest.raises(subprocess.CalledProcessError):
        redis.fingerprint(state, deadline=1)

    assert not state.exists()


def test_v3_logical_digest_survives_complex_rdb_round_trip(
    tmp_path: Path, redis_factory
):
    redis = redis_factory(appendonly=False)
    _populate_complex(redis)
    before = tmp_path / "rdb-before.state"
    redis.fingerprint(before)
    _finish_persistence(redis)
    redis.stop()
    redis.start()
    after = tmp_path / "rdb-after.state"
    redis.fingerprint(after)
    _assert_equal(before, after)


def test_v3_logical_digest_survives_complex_aof_rewrite_and_replay(
    tmp_path: Path, redis_factory
):
    """Set/hash/stream DUMP bytes are unstable; logical recovery state is not."""
    redis = redis_factory(appendonly=True)
    _populate_complex(redis)
    before = tmp_path / "aof-before.state"
    redis.fingerprint(before)
    _finish_persistence(redis)
    redis.stop()
    redis.start()
    after = tmp_path / "aof-after.state"
    redis.fingerprint(after)
    _assert_equal(before, after)


@pytest.mark.parametrize("appendonly", [False, True], ids=["rdb", "aof"])
def test_v3_redis_8_array_sparse_state_survives_replay(
    tmp_path: Path, redis_factory, appendonly: bool
):
    redis = redis_factory(appendonly=appendonly)
    info = redis.cli("--json", "COMMAND", "INFO", "ARSET").stdout
    if info.strip() in {"[null]", "[]"}:
        pytest.skip("Redis built-in array type requires Redis 8.8+")
    redis.cli("ARSET", "array", "0", "zero", "one", "two")
    redis.cli("ARDEL", "array", "1")
    redis.cli("ARSET", "array", "10000", "sparse")
    redis.cli("ARINSERT", "array", "cursor-value")
    before = tmp_path / f"array-{appendonly}-before.state"
    redis.fingerprint(before)
    _finish_persistence(redis)
    redis.stop()
    redis.start()
    after = tmp_path / f"array-{appendonly}-after.state"
    redis.fingerprint(after)
    _assert_equal(before, after)


def test_v3_capture_has_no_dump_and_rejects_unknown_types_by_construction():
    source = SHELL_LIB.read_text(encoding="utf-8")
    v3 = source.split("-- cabinet-redis-state-v3", 1)[1]
    v3 = v3.split("redis_state_fingerprint()", 1)[0]
    assert 'redis.call("DUMP"' not in v3
    assert "unsupported Redis value type" in v3
