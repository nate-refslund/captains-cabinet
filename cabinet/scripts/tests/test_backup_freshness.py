"""Durable backup publication and restore-integrity regressions."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BACKUP = ROOT / "cabinet" / "scripts" / "backup.sh"
RESTORE = ROOT / "cabinet" / "scripts" / "restore-drill.sh"
DIGEST = "0:" + ("a" * 64)
V2_DIGEST = "0:" + ("a" * 40)
KEY_DIGEST = "b" * 64
CONTENT_DIGEST = "c" * 64
CHANGED_DIGEST = "d" * 64


def _exe(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _instance(tmp_path: Path) -> Path:
    root = tmp_path / "cabinet-root"
    for rel in ("shared/interfaces", "instance/config", "memory", "cabinet"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "shared/interfaces/captain-decisions.md").write_text("decision\n")
    (root / "instance/config/platform.yml").write_text("captain_name: Ada\n")
    (root / "memory/note.md").write_text("note\n")
    return root


def _env(tmp_path: Path, root: Path, fakebin: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "CABINET_ROOT": str(root),
        "BACKUP_DEST": str(tmp_path / "backups"),
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fakebin}:{Path(sys.executable).parent}:/opt/homebrew/bin:/usr/bin:/bin",
    })
    for key in (
        "DATABASE_URL", "NEON_CONNECTION_STRING", "FAIL_RDB", "FAKE_TTL_MODE",
        "FAKE_STATE_MODE", "FAKE_V2_MISMATCH",
    ):
        env.pop(key, None)
    return env


def _fake_redis(fakebin: Path, aof_root: Path | None = None) -> None:
    aof = ""
    if aof_root is not None:
        aof = f'''\
  *" CONFIG GET appendonly "*) echo appendonly; echo yes ;;
  *" INFO persistence "*) echo aof_rewrite_in_progress:0; echo aof_last_write_status:ok ;;
  *" CONFIG GET dir "*) echo dir; echo {aof_root!s} ;;
  *" CONFIG GET appenddirname "*) echo appenddirname; echo appendonlydir ;;
  *" WAITAOF "*) echo 1; echo 0 ;;
'''
    else:
        aof = '  *" CONFIG GET appendonly "*) echo appendonly; echo no ;;\n'
    _exe(fakebin / "redis-cli", f'''\
args=" $* "
case "$args" in
  *" --rdb "*)
    [ "${{FAIL_RDB:-0}}" != 1 ] || exit 1
    want=0
    for arg in "$@"; do
      if [ "$want" = 1 ]; then echo -n REDIS-FRESH > "$arg"; exit 0; fi
      [ "$arg" = "--rdb" ] && want=1
    done
    exit 1 ;;
  *" CONFIG GET databases "*) echo databases; echo 2 ;;
  *" EVAL_RO "*)
    case "$args" in
      *"cabinet-redis-state-v2"*)
        if [ "${{FAKE_V2_MISMATCH:-0}}" = 1 ]; then
          case "$args" in *" -s "*) echo 0:{'d' * 40} ;; *) echo {V2_DIGEST} ;; esac
        else
          echo {V2_DIGEST}
        fi
        ;;
      *)
        case "$args" in *" -s "*) restored=1; echo 2000000 ;; *) restored=0; echo 1000000 ;; esac
        if [ "${{FAKE_STATE_MODE:-}}" = durable_mismatch ] && [ "$restored" = 1 ]; then
          echo 0:{CHANGED_DIGEST}
        else
          echo {DIGEST}
        fi
        case "${{FAKE_TTL_MODE:-${{FAKE_STATE_MODE:-}}}}:$restored" in
          within:0) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3000000 ;;
          within:1) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3002000 ;;
          outside:0) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3000000 ;;
          outside:1) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3002001 ;;
          expired:0) echo {KEY_DIGEST}:{CONTENT_DIGEST}:1500000 ;;
          future_missing:0) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3000000 ;;
          changed:0) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3000000 ;;
          changed:1) echo {KEY_DIGEST}:{CHANGED_DIGEST}:3000000 ;;
          unexpected:1) echo {KEY_DIGEST}:{CONTENT_DIGEST}:3000000 ;;
        esac
        ;;
    esac
    ;;
{aof}  *" CLIENT PAUSE "*|*" CLIENT UNPAUSE "*) echo OK ;;
  *" SHUTDOWN NOSAVE "*) exit 0 ;;
  *" PING "*|*" ping "*) echo PONG ;;
  *) echo OK ;;
esac
''')
    _exe(fakebin / "redis-check-rdb", 'test -s "$1"\ngrep -q REDIS-FRESH "$1"\necho "RDB valid"\n')
    _exe(fakebin / "redis-server", "exit 0\n")
    if aof_root is not None:
        _exe(fakebin / "redis-check-aof", '''\
manifest="$1"
test -s "$manifest"
if grep -R -q TRUNCATED "$(dirname "$manifest")"; then exit 1; fi
grep -q '^file ' "$manifest"
echo 'AOF valid'
''')


def _valid_postgres(fakebin: Path) -> None:
    _exe(fakebin / "pg_dump", '''\
out=""
for arg in "$@"; do case "$arg" in --file=*) out="${arg#--file=}";; esac; done
test -n "$out"
echo PGDMP > "$out"
echo VALID-CUSTOM-ARCHIVE >> "$out"
''')
    _exe(fakebin / "pg_restore", '''\
test "$1" = "--list"
test "$(head -c 5 "$2")" = "PGDMP"
echo 'stub archive catalog validated'
''')


def _run(tmp_path: Path, root: Path, fakebin: Path, *args: str,
         extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = _env(tmp_path, root, fakebin)
    env.update(extra or {})
    return subprocess.run(
        ["/bin/bash", str(BACKUP), *args], env=env, capture_output=True,
        text=True, timeout=30,
    )


def _snapshot(tmp_path: Path) -> Path:
    found = list((tmp_path / "backups").glob("20??-??-??"))
    assert len(found) == 1
    return found[0]


def test_backup_validates_redis_and_auto_neon_dump(tmp_path: Path):
    root = _instance(tmp_path)
    (root / "cabinet/.env").write_text(
        "NEON_CONNECTION_STRING=postgresql://fixture.invalid/cabinet\n"
    )
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    _valid_postgres(fakebin)

    result = _run(tmp_path, root, fakebin)

    assert result.returncode == 0, (result.stdout, result.stderr)
    snap = _snapshot(tmp_path)
    assert (snap / "redis-dump.rdb").read_bytes() == b"REDIS-FRESH"
    assert "STATE_EQUALITY verified" in (snap / "redis-verify.txt").read_text()
    assert (snap / "redis-state.txt").read_text().startswith(
        "FORMAT redis-logical-content-expiry-v3\n"
    )
    assert (snap / "redis-state.txt").read_text().count("\nDB ") == 2
    assert (snap / "postgres.dump").read_bytes().startswith(b"PGDMP")
    assert "catalog validated" in (snap / "postgres-verify.txt").read_text()
    assert "postgresql://" not in result.stdout + result.stderr
    assert not [path for path in snap.rglob("*") if ".tmp" in path.name]


def test_backup_rejects_non_archive_pg_dump(tmp_path: Path):
    root = _instance(tmp_path)
    (root / "cabinet/.env").write_text("DATABASE_URL=postgresql://fixture.invalid/db\n")
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    _exe(fakebin / "pg_dump", '''\
for arg in "$@"; do case "$arg" in --file=*) out="${arg#--file=}";; esac; done
echo NOT-A-DUMP > "$out"
''')
    _exe(fakebin / "pg_restore", "exit 1\n")

    result = _run(tmp_path, root, fakebin)

    assert result.returncode == 1
    assert "pg_restore rejected" in result.stderr
    assert not list((tmp_path / "backups").glob("20??-??-??"))


def test_failed_first_backup_never_publishes_staging(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = _run(tmp_path, root, fakebin, "--no-pg", extra={"FAIL_RDB": "1"})

    assert result.returncode == 1
    assert "no older snapshot was published" in result.stderr
    assert not list((tmp_path / "backups").glob("20??-??-??"))
    assert not list((tmp_path / "backups").glob(".*.staging.*"))


def test_failed_same_day_rerun_preserves_last_good_snapshot(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    first = _run(tmp_path, root, fakebin, "--no-pg")
    assert first.returncode == 0, (first.stdout, first.stderr)
    snap = _snapshot(tmp_path)
    before_manifest = (snap / "SHA256SUMS").read_bytes()
    before_note = (snap / "cabinet-state/memory/note.md").read_bytes()
    (root / "memory/note.md").write_text("unpublished replacement\n")

    second = _run(tmp_path, root, fakebin, "--no-pg", extra={"FAIL_RDB": "1"})

    assert second.returncode == 1
    assert (snap / "SHA256SUMS").read_bytes() == before_manifest
    assert (snap / "cabinet-state/memory/note.md").read_bytes() == before_note
    assert not list((tmp_path / "backups").glob(".*.staging.*"))
    assert not (tmp_path / "backups/.backup.lock").exists()


def test_successful_same_day_rerun_atomically_replaces_snapshot(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    first = _run(tmp_path, root, fakebin, "--no-pg")
    assert first.returncode == 0, (first.stdout, first.stderr)
    (root / "memory/note.md").write_text("replacement\n")

    second = _run(tmp_path, root, fakebin, "--no-pg")

    assert second.returncode == 0, (second.stdout, second.stderr)
    snap = _snapshot(tmp_path)
    assert (snap / "cabinet-state/memory/note.md").read_text() == "replacement\n"
    assert not list((tmp_path / "backups").glob(".*.staging.*"))


def test_live_process_lock_refuses_concurrent_backup(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    lock = tmp_path / "backups/.backup.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{os.getpid()}\n")

    result = _run(tmp_path, root, fakebin, "--no-pg")

    assert result.returncode == 1
    assert "already running" in result.stderr
    assert (lock / "pid").read_text().strip() == str(os.getpid())


def test_redis_absolute_expiry_allows_bounded_restore_clock_skew(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = _run(
        tmp_path, root, fakebin, "--no-pg", extra={"FAKE_TTL_MODE": "within"}
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    state = (_snapshot(tmp_path) / "redis-state.txt").read_text()
    assert f"VOLATILE 0 {KEY_DIGEST} {CONTENT_DIGEST} 3000000" in state


def test_redis_absolute_expiry_refuses_out_of_tolerance_restore(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = _run(
        tmp_path, root, fakebin, "--no-pg", extra={"FAKE_TTL_MODE": "outside"}
    )

    assert result.returncode == 1
    assert "does not match recoverable source state at restore time" in result.stderr
    assert not list((tmp_path / "backups").glob("20??-??-??"))


def test_rdb_capture_allows_volatile_key_expired_before_restore_check(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = _run(
        tmp_path, root, fakebin, "--no-pg", extra={"FAKE_STATE_MODE": "expired"}
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    state = (_snapshot(tmp_path) / "redis-state.txt").read_text()
    assert f"VOLATILE 0 {KEY_DIGEST} {CONTENT_DIGEST} 1500000" in state


def _aof_source(tmp_path: Path, truncated: bool = False) -> Path:
    root = tmp_path / "redis-data"
    folder = root / "appendonlydir"
    folder.mkdir(parents=True)
    payload = b"VALID-AOF\n" + (b"TRUNCATED" if truncated else b"COMPLETE\n")
    (folder / "appendonly.aof.1.incr.aof").write_bytes(payload)
    (folder / "appendonly.aof.manifest").write_text(
        "file appendonly.aof.1.incr.aof seq 1 type i\n"
    )
    return root


@pytest.mark.parametrize("capture_mode", ["rdb", "aof"])
@pytest.mark.parametrize(
    "state_mode", ["durable_mismatch", "future_missing", "changed", "unexpected"]
)
def test_rdb_and_aof_capture_reject_all_nonexpiry_state_drift(
    tmp_path: Path, capture_mode: str, state_mode: str
):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    if capture_mode == "aof":
        _fake_redis(fakebin, _aof_source(tmp_path))
    else:
        _fake_redis(fakebin)
    extra = {"FAKE_STATE_MODE": state_mode}
    if capture_mode == "aof":
        extra["FAIL_RDB"] = "1"

    result = _run(tmp_path, root, fakebin, "--no-pg", extra=extra)

    assert result.returncode == 1
    assert "does not match recoverable source state at restore time" in result.stderr
    assert not list((tmp_path / "backups").glob("20??-??-??"))


def test_backup_accepts_checked_nontruncated_equal_aof(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin, _aof_source(tmp_path))

    result = _run(tmp_path, root, fakebin, "--no-pg", extra={"FAIL_RDB": "1"})

    assert result.returncode == 0, (result.stdout, result.stderr)
    snap = _snapshot(tmp_path)
    assert (snap / "redis-backup-mode.txt").read_text().strip() == "aof"
    assert "AOF valid" in (snap / "redis-verify.txt").read_text()
    assert "STATE_EQUALITY verified" in (snap / "redis-verify.txt").read_text()


def test_aof_capture_allows_volatile_key_expired_during_replay(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin, _aof_source(tmp_path))

    result = _run(
        tmp_path,
        root,
        fakebin,
        "--no-pg",
        extra={"FAIL_RDB": "1", "FAKE_STATE_MODE": "expired"},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (_snapshot(tmp_path) / "redis-backup-mode.txt").read_text().strip() == "aof"


def test_backup_refuses_truncated_aof(tmp_path: Path):
    root = _instance(tmp_path)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    _fake_redis(fakebin, _aof_source(tmp_path, truncated=True))

    result = _run(tmp_path, root, fakebin, "--no-pg", extra={"FAIL_RDB": "1"})

    assert result.returncode == 1
    assert "redis-check-aof rejected" in result.stderr
    assert not list((tmp_path / "backups").glob("20??-??-??"))


def _state_text(
    *,
    format: str = "v3",
    volatile_deadline: int | None = None,
) -> str:
    if format == "v2":
        return (
            "FORMAT redis-dump-content-expiry-v2\n"
            "DATABASES 2\n"
            f"DB 0 {V2_DIGEST}\n"
            f"DB 1 {V2_DIGEST}\n"
        )
    lines = [
        "FORMAT redis-logical-content-expiry-v3",
        "DATABASES 2",
        f"DB 0 1000000 {DIGEST.replace(':', ' ')}",
        f"DB 1 1000000 {DIGEST.replace(':', ' ')}",
    ]
    if volatile_deadline is not None:
        for database in range(2):
            lines.append(
                f"VOLATILE {database} {KEY_DIGEST} {CONTENT_DIGEST} {volatile_deadline}"
            )
    return "\n".join(lines) + "\n"


def _manifest(snapshot: Path) -> None:
    lines = []
    files = (path for path in snapshot.rglob("*") if path.is_file())
    for path in sorted(files):
        if path.name == "SHA256SUMS":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  ./{path.relative_to(snapshot)}\n")
    (snapshot / "SHA256SUMS").write_text("".join(lines))


def _restore_snapshot(tmp_path: Path, mode: str, *, postgres: bool = False,
                      truncated: bool = False, state_text: str | None = None) -> Path:
    snap = tmp_path / "restore-backups/2026-07-15"
    (snap / "cabinet-state/shared/interfaces").mkdir(parents=True)
    (snap / "cabinet-state/instance/config").mkdir(parents=True)
    (snap / "cabinet-state/memory").mkdir(parents=True)
    (snap / "cabinet-state/shared/interfaces/captain-decisions.md").write_text("d\n")
    (snap / "cabinet-state/instance/config/platform.yml").write_text("c\n")
    for index in range(8):
        (snap / f"cabinet-state/memory/note-{index}.md").write_text(f"{index}\n")
    (snap / "redis-backup-mode.txt").write_text(mode + "\n")
    (snap / "redis-state.txt").write_text(state_text or _state_text())
    if mode == "rdb":
        (snap / "redis-dump.rdb").write_bytes(b"REDIS-FRESH")
    else:
        source = tmp_path / "restore-aof/appendonlydir"
        source.mkdir(parents=True)
        (source / "appendonly.aof.1.incr.aof").write_bytes(
            b"TRUNCATED" if truncated else b"COMPLETE"
        )
        (source / "appendonly.aof.manifest").write_text(
            "file appendonly.aof.1.incr.aof seq 1 type i\n"
        )
        with tarfile.open(snap / "redis-aof.tgz", "w:gz") as archive:
            archive.add(source, arcname="appendonlydir")
    if postgres:
        (snap / "postgres.dump").write_bytes(b"PGDMP\nVALID-CUSTOM-ARCHIVE\n")
    _manifest(snap)
    return snap


def _restore_env(fakebin: Path, snapshot: Path) -> dict[str, str]:
    return {
        **os.environ,
        "BACKUP_DEST": str(snapshot.parent),
        # Excludes Homebrew, where pg_restore lives on the development Mac.
        "PATH": f"{fakebin}:{Path(sys.executable).parent}:/usr/bin:/bin",
    }


def _fake_postgres_toolchain(fakebin: Path) -> None:
    _exe(fakebin / "pg_restore", '''\
if [ "${1:-}" = "--version" ]; then echo 'pg_restore (PostgreSQL) 17.5'; exit 0; fi
if [ "${1:-}" = "--list" ]; then
  echo list >> "$PG_TRACE"
  test "$(head -c 5 "$2")" = PGDMP
  echo 'stub catalog'
  exit 0
fi
echo restore >> "$PG_TRACE"
printf '%s\n' "$@" > "$PG_ARGS"
[ "${FAIL_PG_RESTORE:-0}" != 1 ]
''')
    _exe(fakebin / "initdb", '''\
while [ "$#" -gt 0 ]; do
  if [ "$1" = -D ]; then mkdir -p "$2"; exit 0; fi
  shift
done
exit 1
''')
    _exe(fakebin / "pg_ctl", '''\
case " $* " in *" start "*) echo start >> "$PG_TRACE";; *" stop "*) echo stop >> "$PG_TRACE";; esac
exit 0
''')
    _exe(fakebin / "createdb", 'echo createdb >> "$PG_TRACE"\n')
    _exe(fakebin / "psql", 'echo query >> "$PG_TRACE"\necho 7\n')
    _exe(fakebin / "postgres", "echo 'postgres (PostgreSQL) 17.5'\n")


def test_restore_drill_accepts_expected_volatile_that_expired_by_capture(tmp_path: Path):
    snap = _restore_snapshot(
        tmp_path,
        "rdb",
        state_text=_state_text(volatile_deadline=1_500_000),
    )
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    env = _restore_env(fakebin, snap)
    env["FAKE_STATE_MODE"] = "expired"

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "restored Redis recoverable state matches at restore time" in result.stdout


@pytest.mark.parametrize(
    ("state_mode", "expected_error"),
    [
        ("durable_mismatch", "durable state differs"),
        ("future_missing", "before its deadline"),
        ("changed", "content differs"),
        ("unexpected", "unexpected volatile"),
    ],
)
def test_restore_drill_rejects_durable_future_changed_and_extra_state(
    tmp_path: Path, state_mode: str, expected_error: str
):
    expected_volatile = state_mode in {"future_missing", "changed"}
    snap = _restore_snapshot(
        tmp_path,
        "rdb",
        state_text=_state_text(
            volatile_deadline=3_000_000 if expected_volatile else None
        ),
    )
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    env = _restore_env(fakebin, snap)
    env["FAKE_STATE_MODE"] = state_mode

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "restored Redis state differs" in result.stdout
    assert expected_error in result.stderr


def test_restore_drill_keeps_v2_exact_and_fail_closed(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", state_text=_state_text(format="v2"))
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=_restore_env(fakebin, snap),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_restore_drill_v2_mismatch_fails_with_fresh_v3_message(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", state_text=_state_text(format="v2"))
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    env = _restore_env(fakebin, snap)
    env["FAKE_V2_MISMATCH"] = "1"

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "fresh v3 backup" in result.stderr


def test_restore_drill_rejects_duplicate_state_records(tmp_path: Path):
    malformed = _state_text() + f"DB 0 1000000 {DIGEST.replace(':', ' ')}\n"
    snap = _restore_snapshot(tmp_path, "rdb", state_text=malformed)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=_restore_env(fakebin, snap),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "invalid database count" in result.stdout


def test_restore_drill_fails_when_pg_restore_is_missing(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", postgres=True)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=_restore_env(fakebin, snap), capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 1
    assert "pg_restore is missing" in result.stdout


def test_restore_drill_fails_when_server_toolchain_is_incomplete(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", postgres=True)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    _exe(fakebin / "pg_restore", '''\
test "$1" = --list
test "$(head -c 5 "$2")" = PGDMP
echo 'stub catalog'
''')
    env = _restore_env(fakebin, snap)
    env["CABINET_POSTGRES_BIN_DIR"] = str(fakebin)

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 1
    assert "no complete local PostgreSQL server toolchain" in result.stdout


def test_restore_drill_restores_postgres_into_disposable_cluster(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", postgres=True)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    _fake_postgres_toolchain(fakebin)
    trace = tmp_path / "pg-trace"
    args = tmp_path / "pg-args"
    env = _restore_env(fakebin, snap)
    env.update({
        "CABINET_POSTGRES_BIN_DIR": str(fakebin),
        "PG_TRACE": str(trace),
        "PG_ARGS": str(args),
    })

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "restores into disposable PostgreSQL (7 user relations" in result.stdout
    events = trace.read_text().splitlines()
    assert events[:2] == ["list", "list"]
    assert events.index("restore") > events.index("list")
    assert events[-1] == "stop"
    restore_args = args.read_text()
    assert "--no-owner" in restore_args
    assert "--no-privileges" in restore_args
    assert "--exit-on-error" in restore_args
    assert "postgres-socket" in restore_args


def test_restore_drill_fails_on_disposable_postgres_restore_error(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "rdb", postgres=True)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin)
    _fake_postgres_toolchain(fakebin)
    trace = tmp_path / "pg-trace"
    env = _restore_env(fakebin, snap)
    env.update({
        "CABINET_POSTGRES_BIN_DIR": str(fakebin),
        "PG_TRACE": str(trace),
        "PG_ARGS": str(tmp_path / "pg-args"),
        "FAIL_PG_RESTORE": "1",
    })

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=env, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 1
    assert "failed during the disposable database restore" in result.stdout
    events = trace.read_text().splitlines()
    assert events[:2] == ["list", "list"]
    assert "restore" in events
    assert events[-1] == "stop"


def test_restore_drill_rejects_truncated_aof_before_boot(tmp_path: Path):
    snap = _restore_snapshot(tmp_path, "aof", truncated=True)
    fakebin = tmp_path / "restore-bin"
    fakebin.mkdir()
    _fake_redis(fakebin, tmp_path / "unused-aof")
    started = tmp_path / "redis-started"
    _exe(fakebin / "redis-server", f"touch {started!s}\nexit 0\n")

    result = subprocess.run(
        ["/bin/bash", str(RESTORE), "--date", snap.name],
        env=_restore_env(fakebin, snap), capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 1
    assert "corrupt or truncated" in result.stdout
    assert not started.exists()
