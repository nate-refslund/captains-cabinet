"""Real-Redis end-to-end proof for the backup AOF repair path.

This test deliberately drives ``backup.sh`` through its production fallback:
an isolated TCP Redis has a BGSAVE held open, while its multipart AOF contains
the two Streams states that native AOF replay does not reproduce exactly.  The
published, repaired RDB is then exercised by the real restore drill.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BACKUP = ROOT / "cabinet/scripts/backup.sh"
RESTORE = ROOT / "cabinet/scripts/restore-drill.sh"
REQUIRED_REDIS_TOOLS = (
    "redis-server",
    "redis-cli",
    "redis-check-aof",
    "redis-check-rdb",
)

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in REQUIRED_REDIS_TOOLS),
    reason="required Redis backup binaries are unavailable",
)


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class IsolatedTcpRedis:
    def __init__(self, data: Path):
        self.data = data
        self.port = _unused_tcp_port()
        self.process: subprocess.Popen[bytes] | None = None
        self.log = None

    def cli(
        self,
        *args: str,
        check: bool = True,
        timeout: float = 20,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["redis-cli", "-h", "127.0.0.1", "-p", str(self.port), *args],
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

    def start(self) -> None:
        self.data.mkdir()
        self.log = (self.data / "redis.log").open("wb")
        self.process = subprocess.Popen(
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--protected-mode",
                "yes",
                "--dir",
                str(self.data),
                "--dbfilename",
                "dump.rdb",
                "--appendonly",
                "yes",
                "--appenddirname",
                "appendonlydir",
                "--appendfsync",
                "everysec",
                "--save",
                "",
                "--daemonize",
                "no",
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        for _ in range(200):
            if self.process.poll() is not None:
                raise AssertionError(
                    f"isolated Redis exited during startup; see {self.data / 'redis.log'}"
                )
            try:
                if self.cli("PING", timeout=1).stdout.strip() == "PONG":
                    return
            except subprocess.SubprocessError:
                pass
            time.sleep(0.05)
        raise AssertionError("isolated TCP Redis did not become ready")

    def stop(self) -> None:
        process = self.process
        if process is None:
            if self.log is not None:
                self.log.close()
            return
        # Shorten any test-owned delayed BGSAVE before asking the parent down.
        try:
            self.cli(
                "CONFIG", "SET", "rdb-key-save-delay", "0", check=False, timeout=2
            )
            self.cli("SHUTDOWN", "NOSAVE", check=False, timeout=5)
        except subprocess.SubprocessError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        # BGSAVE is a forked child in the same test-owned process group.  Ensure
        # an interrupted assertion cannot strand it after the server exits.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        if self.log is not None:
            self.log.close()
        self.process = None

    def persistence(self) -> dict[str, str]:
        info = self.cli("--raw", "INFO", "persistence").stdout
        return {
            key: value
            for line in info.splitlines()
            if ":" in line
            for key, value in [line.split(":", 1)]
        }

    def wait_for_aof_drain(self) -> None:
        for _ in range(300):
            info = self.persistence()
            if (
                info.get("aof_rewrite_in_progress") == "0"
                and info.get("aof_buffer_length") == "0"
                and info.get("aof_pending_bio_fsync") == "0"
                and info.get("aof_last_write_status") == "ok"
            ):
                return
            time.sleep(0.05)
        raise AssertionError("isolated Redis AOF did not drain")

    def hold_bgsave_open(self) -> None:
        configured = self.cli(
            "CONFIG", "SET", "rdb-key-save-delay", "1000000", check=False
        )
        if configured.returncode != 0 or configured.stdout.strip() != "OK":
            pytest.skip("Redis rdb-key-save-delay test knob is unavailable")
        started = self.cli("BGSAVE", check=False)
        assert started.returncode == 0, started.stderr
        for _ in range(100):
            if self.persistence().get("rdb_bgsave_in_progress") == "1":
                return
            time.sleep(0.02)
        raise AssertionError("test BGSAVE did not remain in progress")


def _fixture_cabinet(tmp_path: Path) -> Path:
    root = tmp_path / "cabinet-root"
    for relative in ("shared/interfaces", "instance/config", "memory", "cabinet"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "shared/interfaces/captain-decisions.md").write_text(
        "fixture decision\n", encoding="utf-8"
    )
    (root / "instance/config/platform.yml").write_text(
        "captain_name: Fixture\n", encoding="utf-8"
    )
    # The restore drill intentionally rejects suspiciously thin filesystem
    # snapshots, so exercise it with a non-trivial but entirely synthetic tree.
    for index in range(12):
        (root / f"memory/note-{index}.md").write_text(
            f"fixture {index}\n", encoding="utf-8"
        )
    return root


def _seed_replay_anomalies(redis: IsolatedTcpRedis) -> tuple[str, ...]:
    identifiers = (
        "e2e-private-stream",
        "e2e-private-workers",
        "e2e-private-owner",
        "e2e-private-empty-group",
        "e2e-private-empty-consumer",
        "e2e-private-dangling-stream",
        "e2e-private-dangling-group",
        "e2e-private-dangling-owner",
    )
    (
        stream,
        workers,
        owner,
        empty_group,
        empty_consumer,
        dangling_stream,
        dangling_group,
        dangling_owner,
    ) = identifiers
    for index in range(20):
        redis.cli("SET", f"fixture-key-{index}", f"fixture-value-{index}")
    redis.cli("XADD", stream, "*", "field", "value")
    redis.cli("XGROUP", "CREATE", stream, workers, "0")
    redis.cli(
        "XREADGROUP",
        "GROUP",
        workers,
        owner,
        "COUNT",
        "1",
        "STREAMS",
        stream,
        ">",
    )
    # Reading pending history again increments the PEL delivery count.  Native
    # AOF replay reconstructs the entry but not that exact retry history.
    redis.cli(
        "XREADGROUP",
        "GROUP",
        workers,
        owner,
        "COUNT",
        "1",
        "STREAMS",
        stream,
        "0",
    )
    redis.cli("XGROUP", "CREATE", stream, empty_group, "$")
    # XAUTOCLAIM creates the consumer even when there is nothing to claim; that
    # zero-pending consumer identity is the second known replay omission.
    redis.cli(
        "XAUTOCLAIM",
        stream,
        empty_group,
        empty_consumer,
        "0",
        "0-0",
        "COUNT",
        "1",
    )
    # A pending entry can outlive its stream entry after XDEL/XTRIM. Native AOF
    # replay and RDB both preserve this tombstoned PEL. Repair must recognize an
    # already-matching dangling entry without issuing destructive XCLAIM.
    dangling_id = redis.cli(
        "--raw", "XADD", dangling_stream, "*", "field", "value"
    ).stdout.strip()
    redis.cli("XGROUP", "CREATE", dangling_stream, dangling_group, "0")
    redis.cli(
        "XREADGROUP", "GROUP", dangling_group, dangling_owner, "COUNT", "1",
        "STREAMS", dangling_stream, ">",
    )
    redis.cli("XDEL", dangling_stream, dangling_id)
    redis.wait_for_aof_drain()
    return identifiers


def test_backup_repairs_real_aof_replay_and_publishes_exact_rdb(tmp_path: Path):
    redis = IsolatedTcpRedis(tmp_path / "redis")
    try:
        redis.start()
        private_identifiers = _seed_replay_anomalies(redis)
        redis.hold_bgsave_open()

        cabinet_root = _fixture_cabinet(tmp_path)
        backup_dest = tmp_path / "backups"
        env = dict(os.environ)
        env.update(
            {
                "CABINET_ROOT": str(cabinet_root),
                "BACKUP_DEST": str(backup_dest),
                "HOME": str(tmp_path / "home"),
                "REDIS_HOST": "127.0.0.1",
                "REDIS_PORT": str(redis.port),
                # The held BGSAVE must force the real AOF fallback promptly.
                "REDIS_RDB_TIMEOUT_TENTHS": "2",
            }
        )
        env.pop("DATABASE_URL", None)
        env.pop("NEON_CONNECTION_STRING", None)
        completed = subprocess.run(
            ["/bin/bash", str(BACKUP), "--no-pg"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, (completed.stdout, completed.stderr)

        snapshots = list(backup_dest.glob("20??-??-??"))
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert (snapshot / "redis-backup-mode.txt").read_text().strip() == "rdb"
        assert (snapshot / "redis-dump.rdb").stat().st_size > 0
        assert not (snapshot / "redis-aof.tgz").exists()

        verification = (snapshot / "redis-verify.txt").read_text(encoding="utf-8")
        for evidence in (
            "PROVENANCE aof-converted",
            "STREAM_REPLAY_DIFFERENCES repaired",
            "STREAM_REPAIR verified",
            "STATE_EQUALITY verified",
            "RDB_CONVERSION verified",
        ):
            assert evidence in verification
        assert "COMPONENT consumer_identity" in verification
        assert "COMPONENT pel_delivery_count" in verification

        proof = b"\n".join(
            (snapshot / name).read_bytes()
            for name in (
                "redis-state.txt",
                "redis-verify.txt",
                "redis-backup-mode.txt",
                "SHA256SUMS",
            )
        )
        for identifier in private_identifiers:
            assert identifier.encode() not in proof

        drill = subprocess.run(
            ["/bin/bash", str(RESTORE), "--date", snapshot.name],
            env={**env, "BACKUP_DEST": str(backup_dest)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert drill.returncode == 0, (drill.stdout, drill.stderr)
        assert "restored Redis recoverable state matches at restore time" in drill.stdout
        assert "RESTORE DRILL PASSED" in drill.stdout
    finally:
        redis.stop()
