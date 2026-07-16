from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cabinet" / "scripts" / "pre-dogfood-snapshot.sh"


def _write_exe(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\nset -e\n" + body)
    path.chmod(0o755)


@pytest.mark.skipif(shutil.which("git") is None, reason="git unavailable")
def test_snapshot_preserves_dirty_git_and_validates_postgres_without_redis(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "cabinet").mkdir()
    (repo / "cabinet/.env").write_text("NEON_CONNECTION_STRING=postgresql://fixture.invalid/db\n")
    (repo / "tracked.txt").write_text("before\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("after\n")
    (repo / "untracked.txt").write_text("new\n")

    fake = tmp_path / "bin"
    fake.mkdir()
    redis_called = tmp_path / "redis-called"
    _write_exe(
        fake / "redis-cli",
        f'printf called > "{redis_called}"\nexit 99\n',
    )
    _write_exe(
        fake / "pg_dump",
        'for arg in "$@"; do case "$arg" in --file=*) out="${arg#--file=}";; esac; done\n'
        'test -n "$PGSERVICEFILE"\nprintf POSTGRES-FRESH > "$out"\n',
    )
    _write_exe(fake / "pg_restore", 'test "$1" = "--list"\ngrep -q POSTGRES-FRESH "$2"\n')

    dest = tmp_path / "snapshot"
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--root", str(repo), "--dest", str(dest)],
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "VERIFIED" in result.stdout
    assert (dest / "repository.bundle").is_file()
    assert (dest / "dirty-files.tgz").is_file()
    assert (dest / "runtime-secrets.tgz").is_file()
    assert not redis_called.exists()
    redis_exclusion = (dest / "redis-excluded.txt").read_text()
    assert "backup.sh" in redis_exclusion
    assert "restore-drill.sh" in redis_exclusion
    assert "VERIFIED verdict does not cover Redis" in redis_exclusion
    assert not (dest / "redis.rdb").exists()
    assert not (dest / "redis-aof.tgz").exists()
    assert not (dest / "redis-backup-mode.txt").exists()
    assert (dest / "postgres.dump").read_bytes() == b"POSTGRES-FRESH"
    assert (dest / "worktree-before.txt").read_bytes() == (dest / "worktree-after.txt").read_bytes()
    assert (dest.stat().st_mode & 0o077) == 0
    assert not (dest / ".pg_service.conf").exists()


def test_snapshot_refuses_nonempty_destination(tmp_path: Path):
    dest = tmp_path / "snapshot"
    dest.mkdir()
    (dest / "existing").write_text("keep")
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--root", str(ROOT), "--dest", str(dest)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 65
    assert (dest / "existing").read_text() == "keep"
