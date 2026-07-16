#!/usr/bin/env bash
# backup.sh — Daily Cabinet state backup for Mac-native deployments.
#
# Phase 9 of the convergence plan. Backs up the three places Cabinet state
# lives:
#   1. Filesystem (captain triplet, role entities, evolved skills, experience
#      records, mission proposals — the durable runtime artifacts that aren't
#      git-tracked; since 2026-07-07 also .claude/agents/, the generated role
#      defs that CARRY LIVE Captain-approved amendments — lost once in the
#      cos-law incident, never again).
#   2. Redis snapshot (a bounded fresh `redis-cli --rdb` transfer; if Redis has
#      a stuck BGSAVE but healthy AOF, a write-paused and globally drained
#      multipart AOF copy is restored into a disposable Redis, known Streams
#      replay omissions are repaired from an identifier-only manifest, and the
#      exact result is converted to RDB and proved again before acceptance).
#      Acceptance uses a v3 SHA-256 logical-state proof: durable keys compare
#      exactly while an expiring key may be absent only after its recorded
#      absolute deadline.
#   3. Postgres pg_dump whenever DATABASE_URL or NEON_CONNECTION_STRING is
#      configured (disable explicitly with --no-pg).
#
# Each daily run goes into $BACKUP_DEST/<YYYY-MM-DD>/. Default destination is
# ~/Cabinet-Backups; override via BACKUP_DEST env var or --dest flag. Old
# backups beyond the retention window are pruned.
#
# SCHEDULED (lane-ops 2026-07-04): the `backup` row in cabinet/services.yml
# (daily 03:00 local) renders com.cabinet.backup.plist; the repo install copy
# lives at cabinet/launchd/com.cabinet.backup.plist (load steps in
# cabinet/launchd/INSTALL-flip.md). The outcome-watchdog derives a 26h
# freshness floor for it from the manifest. Prove restorability with the
# companion drill: `bash cabinet/scripts/restore-drill.sh` (temp-dir only,
# never touches live state).
#
# CAPTAIN-DECISIONS deliberately not wired here (see the services.yml backup row):
#   * Off-machine copy — a local snapshot dies with the disk; recommended:
#     post-backup rsync of $BACKUP_DEST to the UpCloud CPH box over Tailscale.
#   * Redis AOF is the live durability layer. The backup prefers a fresh RDB;
#     its fallback pauses writes, waits for the global append buffers to drain,
#     repairs replay-unstable Streams metadata in a disposable server, proves
#     exact v3 equality, converts to RDB, and proves that RDB a second time.
#
# Usage:
#   bash cabinet/scripts/backup.sh                       # auto-includes configured Postgres
#   bash cabinet/scripts/backup.sh --dest /Volumes/NAS/cabinet-backups
#   bash cabinet/scripts/backup.sh --pg                  # require configured Postgres backup
#   bash cabinet/scripts/backup.sh --no-pg               # explicit filesystem+Redis-only run
#   bash cabinet/scripts/backup.sh --retention-days 30   # prune older backups
#
# Idempotent within a day — re-running atomically replaces today's snapshot
# only after the replacement has been fully verified and synced to disk.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Bug fix (R5): script lives at cabinet/scripts/, so repo root is two levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# shellcheck source=lib/redis-state.sh
. "$SCRIPT_DIR/lib/redis-state.sh"

BACKUP_DEST="${BACKUP_DEST:-$HOME/Cabinet-Backups}"
RETENTION_DAYS=14
INCLUDE_PG=auto
umask 077

# Manual runs should have the same connection-name behavior as the generated
# LaunchAgent, but the dotenv file is data, not shell code. Read only the four
# settings this backup owns; never execute unrelated values.
dotenv_value() {
  local wanted="$1" file="$2" key value
  [ -f "$file" ] || return 0
  while IFS='=' read -r key value; do
    key="${key#export }"
    [ "$key" = "$wanted" ] || continue
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    printf '%s' "$value"
    return 0
  done < "$file"
}
for _backup_key in DATABASE_URL NEON_CONNECTION_STRING REDIS_HOST REDIS_PORT; do
  if [ -z "${!_backup_key:-}" ]; then
    _backup_value="$(dotenv_value "$_backup_key" "$CABINET_ROOT/cabinet/.env")"
    if [ -n "$_backup_value" ]; then printf -v "$_backup_key" '%s' "$_backup_value"; fi
  fi
done
unset _backup_key _backup_value

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) BACKUP_DEST="$2"; shift 2 ;;
    --dest=*) BACKUP_DEST="${1#--dest=}"; shift ;;
    --retention-days) RETENTION_DAYS="$2"; shift 2 ;;
    --pg) INCLUDE_PG=1; shift ;;
    --no-pg) INCLUDE_PG=0; shift ;;
    -h|--help)
      # Print through the stable marker instead of a brittle line count.
      sed -n '1,/^# Idempotent/p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "backup.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

DATE=$(date +%Y-%m-%d)
PUBLISHED_DIR="$BACKUP_DEST/$DATE"
LOCK_DIR="$BACKUP_DEST/.backup.lock"
DEST_DIR="$BACKUP_DEST/.${DATE}.staging.$$"
LOCK_HELD=0
PG_SERVICE=""
PUBLISH_STARTED=0
REDIS_CAPTURE_PAUSED=0
REDIS_CAPTURE_RDB_PID=""

mkdir -p "$BACKUP_DEST"
chmod 700 "$BACKUP_DEST" 2>/dev/null || true

cleanup_backup() {
  local rc=$?
  # RETURN traps do not run when the signal handlers below exit from inside a
  # capture function. Release the live write pause and stop any daemonized
  # disposable Redis processes here as an independent last line of cleanup.
  if [ "${REDIS_CAPTURE_PAUSED:-0}" = 1 ] && command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h "${REDIS_HOST_VALUE:-127.0.0.1}" -p "${REDIS_PORT_VALUE:-6379}" \
      CLIENT UNPAUSE >/dev/null 2>&1 || true
    REDIS_CAPTURE_PAUSED=0
  fi
  if command -v redis-cli >/dev/null 2>&1; then
    local socket
    for socket in \
      "/tmp/cabinet-redis-rdb-verify-$$.sock" \
      "/tmp/cabinet-redis-verify-$$.sock" \
      "/tmp/cabinet-redis-converted-verify-$$.sock"; do
      if [ -S "$socket" ]; then
        redis-cli -s "$socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
      fi
      rm -f "$socket"
    done
  fi
  case "${REDIS_CAPTURE_RDB_PID:-}" in
    ''|*[!0-9]*) ;;
    *)
      kill "$REDIS_CAPTURE_RDB_PID" >/dev/null 2>&1 || true
      wait "$REDIS_CAPTURE_RDB_PID" >/dev/null 2>&1 || true
      ;;
  esac
  REDIS_CAPTURE_RDB_PID=""
  local pidfile pid
  for pidfile in \
    "$DEST_DIR/.redis-rdb-verify.$$/redis.pid" \
    "$DEST_DIR/.redis-aof-verify.$$/redis.pid" \
    "$DEST_DIR/.redis-converted-rdb-verify.$$/redis.pid"; do
    pid=$(cat "$pidfile" 2>/dev/null || true)
    case "$pid" in
      ''|*[!0-9]*) ;;
      *)
        if kill -0 "$pid" >/dev/null 2>&1; then
          kill "$pid" >/dev/null 2>&1 || true
          for _cleanup_wait in $(seq 1 20); do
            kill -0 "$pid" >/dev/null 2>&1 || break
            sleep 0.05
          done
          if kill -0 "$pid" >/dev/null 2>&1; then
            kill -9 "$pid" >/dev/null 2>&1 || true
          fi
        fi
        ;;
    esac
  done
  [ -z "$PG_SERVICE" ] || rm -f "$PG_SERVICE"
  # Once an atomic exchange may have happened, this path can contain the prior
  # complete snapshot. Preserve it on any publication/fsync error for recovery.
  if [ -n "$DEST_DIR" ] && [ "$PUBLISH_STARTED" = 0 ]; then rm -rf "$DEST_DIR"; fi
  if [ "$LOCK_HELD" = 1 ]; then rm -rf "$LOCK_DIR"; fi
  exit "$rc"
}
trap cleanup_backup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# mkdir is the portable cross-process exclusion primitive on macOS. A live
# owner is never displaced. A dead owner may be reclaimed only when its pid is
# present; a missing pid refuses safely, avoiding the create-dir/write-pid race.
acquire_backup_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    LOCK_HELD=1
    return 0
  fi
  local owner=""
  owner=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
  case "$owner" in
    ''|*[!0-9]*)
      echo "backup.sh: another backup owns $LOCK_DIR (owner pid unavailable)" >&2
      return 1
      ;;
  esac
  if kill -0 "$owner" 2>/dev/null; then
    echo "backup.sh: another backup is already running (pid $owner)" >&2
    return 1
  fi
  local stale="$LOCK_DIR.stale.$$"
  if ! mv "$LOCK_DIR" "$stale" 2>/dev/null || ! mkdir "$LOCK_DIR" 2>/dev/null; then
    rm -rf "$stale"
    echo "backup.sh: backup lock changed while reclaiming a stale owner" >&2
    return 1
  fi
  rm -rf "$stale"
  printf '%s\n' "$$" > "$LOCK_DIR/pid"
  LOCK_HELD=1
}

fsync_snapshot_tree() {
  python3.12 - "$1" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
directories: list[Path] = []
for current, dirnames, filenames in os.walk(root):
    current_path = Path(current)
    directories.append(current_path)
    for name in filenames:
        path = current_path / name
        if path.is_symlink():
            continue
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
for path in reversed(directories):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
PY
}

# First publication is a single rename. Same-day replacement uses the native
# atomic directory-exchange primitive, so the previous complete snapshot is
# never absent or partially overwritten. Unsupported filesystems fail closed
# and leave the published snapshot untouched.
publish_snapshot() {
  python3.12 - "$1" "$2" <<'PY'
import ctypes
import os
import sys
from pathlib import Path

src = os.fsencode(sys.argv[1])
dst = os.fsencode(sys.argv[2])
parent = Path(sys.argv[2]).parent

if not os.path.lexists(dst):
    os.rename(src, dst)
else:
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        fn = libc.renamex_np
        fn.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rc = fn(src, dst, 0x00000002)  # RENAME_SWAP
    elif hasattr(libc, "renameat2"):
        fn = libc.renameat2
        fn.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_uint,
        )
        rc = fn(-100, src, -100, dst, 0x00000002)  # AT_FDCWD, RENAME_EXCHANGE
    else:
        raise SystemExit("atomic directory exchange is unavailable")
    if rc != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), os.fsdecode(dst))

fd = os.open(parent, os.O_RDONLY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

acquire_backup_lock
mkdir "$DEST_DIR"
chmod 700 "$DEST_DIR" 2>/dev/null || true
printf '%s\n' "backup started $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$DEST_DIR/INCOMPLETE"

FAILS=0
backup_fail() { echo "  → FAIL: $1" >&2; FAILS=$((FAILS + 1)); }

echo "=== Cabinet backup → $PUBLISHED_DIR ==="

# --- 1. Filesystem (Cabinet runtime artifacts) ---
echo "[1/3] Filesystem rsync..."
rm -rf "$DEST_DIR/cabinet-state"
mkdir -p "$DEST_DIR/cabinet-state/shared/interfaces" \
  "$DEST_DIR/cabinet-state/instance" "$DEST_DIR/cabinet-state/memory"
rsync -a --delete \
  --exclude='*.pyc' --exclude='__pycache__' \
  --exclude='.session-state.json' \
  "$CABINET_ROOT/shared/interfaces/" "$DEST_DIR/cabinet-state/shared/interfaces/"
rsync -a --delete \
  --exclude='*.pyc' --exclude='__pycache__' \
  --exclude='.session-state.json' \
  "$CABINET_ROOT/instance/" "$DEST_DIR/cabinet-state/instance/"
rsync -a --delete \
  --exclude='*.pyc' --exclude='__pycache__' \
  --exclude='.session-state.json' \
  "$CABINET_ROOT/memory/" "$DEST_DIR/cabinet-state/memory/"
# .claude/agents/ — gitignored GENERATED role defs that nevertheless carry
# LIVE Captain-approved amendments applied by CoS between regenerations
# (2026-07-07 cos-law loss: an amendment existed ONLY here and died with the
# file). Own destination subdir so its basenames (cos.md, cto.md, ...) can
# never collide with the contents-merged sources above.
if [ -d "$CABINET_ROOT/.claude/agents" ]; then
  rsync -a --delete \
    "$CABINET_ROOT/.claude/agents/" \
    "$DEST_DIR/cabinet-state/claude-agents/"
fi
FS_FILES=$(find "$DEST_DIR/cabinet-state" -type f 2>/dev/null | wc -l | tr -d ' ')
FS_SIZE=$(du -sh "$DEST_DIR/cabinet-state" 2>/dev/null | awk '{print $1}')
echo "  → $FS_FILES files, $FS_SIZE"

# --- 2. Redis snapshot (fresh transfer, never a stale server-side file) ---
echo "[2/3] Redis snapshot..."
REDIS_HOST_VALUE="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT_VALUE="${REDIS_PORT:-6379}"
RDB_TIMEOUT_TENTHS="${REDIS_RDB_TIMEOUT_TENTHS:-100}"
case "$RDB_TIMEOUT_TENTHS" in ''|*[!0-9]*) RDB_TIMEOUT_TENTHS=100 ;; esac
REDIS_WRITE_PAUSE_MS=60000
# Reserve five seconds for shell cleanup/unpause. The fingerprint helper checks
# this deadline before and after every database; one blocking EVAL still cannot
# be interrupted mid-database, so growth must stay comfortably below the cap.
REDIS_WRITE_PAUSE_BUDGET_SECONDS=55
REDIS_AOF_DRAIN_SECONDS="${REDIS_AOF_DRAIN_SECONDS:-10}"
case "$REDIS_AOF_DRAIN_SECONDS" in
  1|2|3|4|5|6|7|8|9|10) ;;
  *) echo "backup.sh: REDIS_AOF_DRAIN_SECONDS must be an integer from 1 through 10" >&2; exit 2 ;;
esac

redis_pause_deadline() {
  local now
  now=$(date +%s) || return 1
  printf '%s\n' "$((now + REDIS_WRITE_PAUSE_BUDGET_SECONDS))"
}

redis_pause_budget_ok() {
  local deadline="$1" now
  now=$(date +%s) || return 1
  [ "$now" -lt "$deadline" ]
}

# CLIENT PAUSE WRITE gives us a stable logical instant, but WAITAOF cannot be
# used as a global barrier from a new redis-cli connection: it covers only
# writes previously issued on that same connection. Poll the server-wide AOF
# queues instead. This is a bounded drain check, not a claim that every prior
# write received a new fsync; exact source/restored fingerprint equality remains
# the authoritative completeness proof.
redis_aof_wait_for_global_drain() {
  local pause_deadline="$1" info buffer pending status rewrite now drain_deadline
  now=$(date +%s) || return 1
  drain_deadline=$((now + REDIS_AOF_DRAIN_SECONDS))
  if [ "$drain_deadline" -gt "$pause_deadline" ]; then drain_deadline="$pause_deadline"; fi
  while redis_pause_budget_ok "$drain_deadline"; do
    info=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw INFO persistence) || return 1
    buffer=$(printf '%s\n' "$info" | sed -n 's/^aof_buffer_length:\([0-9]*\).*/\1/p')
    pending=$(printf '%s\n' "$info" | sed -n 's/^aof_pending_bio_fsync:\([0-9]*\).*/\1/p')
    status=$(printf '%s\n' "$info" | sed -n 's/^aof_last_write_status:\([^[:space:]]*\).*/\1/p')
    rewrite=$(printf '%s\n' "$info" | sed -n 's/^aof_rewrite_in_progress:\([0-9]*\).*/\1/p')
    if [ "$buffer" = 0 ] && [ "$pending" = 0 ] && [ "$status" = ok ] && [ "$rewrite" = 0 ]; then
      return 0
    fi
    sleep 0.1
  done
  echo "  → Redis AOF did not reach a healthy global drain before the write-pause deadline" >&2
  return 1
}

rm -f "$DEST_DIR/redis-dump.rdb" "$DEST_DIR/redis-aof.tgz" \
  "$DEST_DIR/redis-backup-mode.txt" "$DEST_DIR/redis-verify.txt" \
  "$DEST_DIR/redis-state.txt"

capture_rdb() {
  command -v redis-check-rdb >/dev/null 2>&1 || return 1
  command -v redis-server >/dev/null 2>&1 || return 1
  local paused=0 captured=0 rdb_pid="" pause_deadline=""
  local rdb_tmp="$DEST_DIR/.redis-dump.rdb.tmp"
  local source_state="$DEST_DIR/.redis-source-state.tmp"
  local restored_state="$DEST_DIR/.redis-restored-state.tmp"
  local verify_dir="$DEST_DIR/.redis-rdb-verify.$$"
  local verify_socket="/tmp/cabinet-redis-rdb-verify-$$.sock"
  cleanup_rdb_capture() {
    if [ -n "$rdb_pid" ] && kill -0 "$rdb_pid" 2>/dev/null; then
      kill "$rdb_pid" 2>/dev/null || true
      wait "$rdb_pid" 2>/dev/null || true
      REDIS_CAPTURE_RDB_PID=""
    fi
    if [ "$paused" = 1 ]; then
      redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" CLIENT UNPAUSE >/dev/null 2>&1 || true
      REDIS_CAPTURE_PAUSED=0
    fi
    redis-cli -s "$verify_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
    rm -rf "$verify_dir" "$verify_socket"
    rm -f "$rdb_tmp" "$source_state" "$restored_state"
    if [ "$captured" != 1 ]; then
      rm -f "$DEST_DIR/redis-dump.rdb" "$DEST_DIR/redis-backup-mode.txt" \
        "$DEST_DIR/redis-verify.txt" "$DEST_DIR/redis-state.txt"
    fi
  }
  trap cleanup_rdb_capture RETURN

  # Hold writes so the live-state digest and replication RDB describe the same
  # instant. Reads continue, and the pause is bounded by Redis itself.
  redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" \
    CLIENT PAUSE "$REDIS_WRITE_PAUSE_MS" WRITE >/dev/null || return 1
  paused=1
  REDIS_CAPTURE_PAUSED=1
  pause_deadline=$(redis_pause_deadline) || return 1
  redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" \
    --rdb "$rdb_tmp" >/dev/null 2>&1 &
  rdb_pid=$!
  REDIS_CAPTURE_RDB_PID="$rdb_pid"
  local rdb_ok=0
  for _i in $(seq 1 "$RDB_TIMEOUT_TENTHS"); do
    if ! kill -0 "$rdb_pid" 2>/dev/null; then
      if wait "$rdb_pid" && [ -s "$rdb_tmp" ]; then rdb_ok=1; fi
      rdb_pid=""
      REDIS_CAPTURE_RDB_PID=""
      break
    fi
    sleep 0.1
  done
  [ "$rdb_ok" = 1 ] || return 1
  redis-check-rdb "$rdb_tmp" > "$DEST_DIR/redis-verify.txt" 2>&1 || return 1
  REDIS_STATE_DEADLINE_EPOCH_SECONDS="$pause_deadline" \
    redis_state_fingerprint "$source_state" v3 \
    redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" || return 1
  redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" CLIENT UNPAUSE >/dev/null || return 1
  paused=0
  REDIS_CAPTURE_PAUSED=0

  mkdir "$verify_dir"
  cp "$rdb_tmp" "$verify_dir/dump.rdb"
  local databases
  databases=$(sed -n 's/^DATABASES //p' "$source_state")
  redis-server --port 0 --unixsocket "$verify_socket" --unixsocketperm 700 \
    --dir "$verify_dir" --dbfilename dump.rdb --databases "$databases" \
    --appendonly no --aof-load-truncated no --save '' --daemonize yes \
    --pidfile "$verify_dir/redis.pid" --logfile "$verify_dir/redis.log" >/dev/null || return 1
  local ready=0
  for _i in $(seq 1 100); do
    if redis-cli -s "$verify_socket" PING 2>/dev/null | grep -qx PONG; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [ "$ready" = 1 ] || return 1
  redis_state_fingerprint "$restored_state" v3 redis-cli -s "$verify_socket" || return 1
  redis_state_equal "$source_state" "$restored_state" || {
    echo "  → Redis RDB does not match recoverable source state at restore time" >&2
    return 1
  }
  redis-cli -s "$verify_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
  rm -rf "$verify_dir" "$verify_socket"

  mv "$rdb_tmp" "$DEST_DIR/redis-dump.rdb"
  mv "$source_state" "$DEST_DIR/redis-state.txt"
  rm -f "$restored_state"
  printf 'STATE_EQUALITY verified\n' >> "$DEST_DIR/redis-verify.txt"
  printf '%s\n' rdb > "$DEST_DIR/redis-backup-mode.txt"
  chmod 600 "$DEST_DIR/redis-dump.rdb" "$DEST_DIR/redis-state.txt" 2>/dev/null || true
  captured=1
  trap - RETURN
  echo "  → fresh verified redis-dump.rdb ($(du -h "$DEST_DIR/redis-dump.rdb" | awk '{print $1}'))"
  return 0
}

capture_aof_fallback() {
  command -v redis-server >/dev/null 2>&1 \
    && command -v redis-check-aof >/dev/null 2>&1 \
    && command -v redis-check-rdb >/dev/null 2>&1 || {
    echo "  → Redis AOF fallback unavailable: redis-server/redis-check-aof/redis-check-rdb is missing" >&2
    return 1
  }
  local appendonly rewrite status redis_dir appenddirname
  appendonly=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw CONFIG GET appendonly | tail -1)
  rewrite=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw INFO persistence | sed -n 's/^aof_rewrite_in_progress:\([0-9]*\).*/\1/p')
  status=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw INFO persistence | sed -n 's/^aof_last_write_status:\([^[:space:]]*\).*/\1/p')
  [ "$appendonly" = yes ] && [ "$rewrite" = 0 ] && [ "$status" = ok ] || {
    echo "  → Redis AOF fallback unavailable: append log is disabled, rewriting, or unhealthy" >&2
    return 1
  }
  redis_dir=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw CONFIG GET dir | tail -1)
  appenddirname=$(redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" --raw CONFIG GET appenddirname | tail -1)
  case "$appenddirname" in ''|.|..|*/*) echo "  → Redis returned an unsafe appenddirname" >&2; return 1 ;; esac
  [ -d "$redis_dir/$appenddirname" ] || {
    echo "  → Redis AOF fallback unavailable: append directory is missing" >&2
    return 1
  }

  local paused=0 verify_dir="$DEST_DIR/.redis-aof-verify.$$" pause_deadline=""
  local verify_socket="/tmp/cabinet-redis-verify-$$.sock"
  local converted_dir="$DEST_DIR/.redis-converted-rdb-verify.$$"
  local converted_socket="/tmp/cabinet-redis-converted-verify-$$.sock"
  local captured=0
  local archive_tmp="$DEST_DIR/.redis-aof.tgz.tmp"
  local source_state="$DEST_DIR/.redis-source-state.tmp"
  local restored_state="$DEST_DIR/.redis-restored-state.tmp"
  local converted_state="$DEST_DIR/.redis-converted-state.tmp"
  local repair_manifest="$DEST_DIR/.redis-stream-repair.tmp"
  local restored_repair_manifest="$DEST_DIR/.redis-restored-stream-repair.tmp"
  local mismatch_report="$DEST_DIR/.redis-state-diff.tmp"
  local converted_rdb="$verify_dir/dump.rdb"
  cleanup_redis_capture() {
    if [ "$paused" = 1 ]; then
      redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" CLIENT UNPAUSE >/dev/null 2>&1 || true
      REDIS_CAPTURE_PAUSED=0
    fi
    if [ -S "$verify_socket" ]; then
      redis-cli -s "$verify_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
    fi
    if [ -S "$converted_socket" ]; then
      redis-cli -s "$converted_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
    fi
    rm -rf "$verify_dir" "$converted_dir" "$verify_socket" "$converted_socket"
    rm -f "$archive_tmp" "$source_state" "$restored_state" "$converted_state" \
      "$repair_manifest" "$restored_repair_manifest" "$mismatch_report"
    if [ "$captured" != 1 ]; then
      rm -f "$DEST_DIR/redis-dump.rdb" "$DEST_DIR/redis-aof.tgz" "$DEST_DIR/redis-backup-mode.txt" \
        "$DEST_DIR/redis-verify.txt" "$DEST_DIR/redis-state.txt"
    fi
  }
  trap cleanup_redis_capture RETURN

  redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" \
    CLIENT PAUSE "$REDIS_WRITE_PAUSE_MS" WRITE >/dev/null || return 1
  paused=1
  REDIS_CAPTURE_PAUSED=1
  pause_deadline=$(redis_pause_deadline) || return 1
  redis_aof_wait_for_global_drain "$pause_deadline" || return 1
  REDIS_STATE_DEADLINE_EPOCH_SECONDS="$pause_deadline" \
    redis_state_fingerprint "$source_state" v3 \
    redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" || return 1
  REDIS_STATE_DEADLINE_EPOCH_SECONDS="$pause_deadline" \
    redis_stream_repair_manifest "$repair_manifest" "$(expected_redis_databases "$source_state")" \
    redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" || return 1
  tar -C "$redis_dir" -czf "$archive_tmp" "$appenddirname" || return 1
  if ! redis_pause_budget_ok "$pause_deadline"; then
    echo "  → Redis AOF capture exceeded the write-pause budget" >&2
    return 1
  fi
  redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" CLIENT UNPAUSE >/dev/null || return 1
  paused=0
  REDIS_CAPTURE_PAUSED=0

  mkdir -p "$verify_dir"
  tar -C "$verify_dir" -xzf "$archive_tmp" || return 1
  local aof_manifest="$verify_dir/$appenddirname/appendonly.aof.manifest"
  [ -f "$aof_manifest" ] || {
    echo "  → Redis AOF manifest is missing" >&2
    return 1
  }
  redis-check-aof "$aof_manifest" > "$DEST_DIR/redis-verify.txt" 2>&1 || {
    echo "  → redis-check-aof rejected the captured append log" >&2
    return 1
  }
  local databases
  databases=$(sed -n 's/^DATABASES //p' "$source_state")
  redis-server --port 0 --unixsocket "$verify_socket" --unixsocketperm 700 \
    --dir "$verify_dir" --appendonly yes --appenddirname "$appenddirname" \
    --aof-load-truncated no --databases "$databases" --save '' \
    --daemonize yes --pidfile "$verify_dir/redis.pid" \
    --logfile "$verify_dir/redis.log" >/dev/null || return 1
  local ready=0
  # A wedged source can accumulate a large incremental AOF before rescue. This
  # wait is after live writes are unpaused, so give replay a full minute without
  # consuming the 55-second source-capture budget.
  for _ in $(seq 1 600); do
    if redis-cli -s "$verify_socket" PING 2>/dev/null | grep -qx PONG; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [ "$ready" = 1 ] || {
    echo "  → disposable Redis could not restore the captured AOF" >&2
    return 1
  }
  redis_stream_repair_manifest "$restored_repair_manifest" \
    "$(expected_redis_databases "$source_state")" redis-cli -s "$verify_socket" || return 1
  redis_stream_repair_diff "$repair_manifest" "$restored_repair_manifest" \
    > "$mismatch_report" 2>/dev/null || true
  if ! redis_stream_repair_apply "$repair_manifest" redis-cli -s "$verify_socket"; then
    echo "  → Redis Streams replay repair was refused" >&2
    if [ -s "$mismatch_report" ]; then
      echo "  → privacy-safe pre-repair attribution:" >&2
      sed 's/^/    /' "$mismatch_report" >&2
    fi
    return 1
  fi
  redis_state_fingerprint "$restored_state" v3 redis-cli -s "$verify_socket" || return 1
  redis_state_equal "$source_state" "$restored_state" || {
    echo "  → Redis AOF does not match recoverable source state after Streams repair" >&2
    if [ -s "$mismatch_report" ]; then
      echo "  → privacy-safe pre-repair attribution (residual mismatch is aggregate-only):" >&2
      sed 's/^/    /' "$mismatch_report" >&2
    fi
    return 1
  }

  # Persist the repaired logical state as the recovery artifact. AOF replay is
  # used only inside this disposable conversion step; disaster restore receives
  # an exact RDB and therefore cannot repeat the replay omissions we just fixed.
  redis-cli -s "$verify_socket" SAVE >/dev/null || return 1
  [ -s "$converted_rdb" ] || {
    echo "  → disposable Redis did not produce a converted RDB" >&2
    return 1
  }
  redis-check-rdb "$converted_rdb" >> "$DEST_DIR/redis-verify.txt" 2>&1 || return 1
  redis-cli -s "$verify_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true

  mkdir "$converted_dir"
  cp "$converted_rdb" "$converted_dir/dump.rdb"
  local databases
  databases=$(expected_redis_databases "$source_state") || return 1
  redis-server --port 0 --unixsocket "$converted_socket" --unixsocketperm 700 \
    --dir "$converted_dir" --dbfilename dump.rdb --databases "$databases" \
    --appendonly no --aof-load-truncated no --save '' --daemonize yes \
    --pidfile "$converted_dir/redis.pid" --logfile "$converted_dir/redis.log" >/dev/null || return 1
  ready=0
  # Match the repaired AOF replay readiness bound. This second boot is outside
  # the live write pause too, and a production-sized converted RDB may need more
  # than the old ten-second cap even though its state is fully verified.
  for _ in $(seq 1 600); do
    if redis-cli -s "$converted_socket" PING 2>/dev/null | grep -qx PONG; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [ "$ready" = 1 ] || {
    echo "  → second disposable Redis could not restore the converted RDB" >&2
    return 1
  }
  redis_state_fingerprint "$converted_state" v3 redis-cli -s "$converted_socket" || return 1
  redis_state_equal "$source_state" "$converted_state" || {
    echo "  → converted Redis RDB does not match recoverable source state" >&2
    if [ -s "$mismatch_report" ]; then
      echo "  → privacy-safe pre-repair attribution (residual mismatch is aggregate-only):" >&2
      sed 's/^/    /' "$mismatch_report" >&2
    fi
    return 1
  }
  redis-cli -s "$converted_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true

  mv "$converted_rdb" "$DEST_DIR/redis-dump.rdb"
  mv "$source_state" "$DEST_DIR/redis-state.txt"
  rm -f "$archive_tmp" "$restored_state" "$converted_state" "$repair_manifest" \
    "$restored_repair_manifest"
  rm -rf "$verify_dir" "$converted_dir" "$verify_socket" "$converted_socket"
  printf 'PROVENANCE aof-converted\n' >> "$DEST_DIR/redis-verify.txt"
  if [ -s "$mismatch_report" ]; then
    printf 'STREAM_REPLAY_DIFFERENCES repaired\n' >> "$DEST_DIR/redis-verify.txt"
    sed 's/^/REPAIRED /' "$mismatch_report" >> "$DEST_DIR/redis-verify.txt"
  fi
  rm -f "$mismatch_report"
  printf 'STREAM_REPAIR verified\n' >> "$DEST_DIR/redis-verify.txt"
  printf 'STATE_EQUALITY verified\n' >> "$DEST_DIR/redis-verify.txt"
  printf 'RDB_CONVERSION verified\n' >> "$DEST_DIR/redis-verify.txt"
  printf '%s\n' rdb > "$DEST_DIR/redis-backup-mode.txt"
  chmod 600 "$DEST_DIR/redis-dump.rdb" "$DEST_DIR/redis-state.txt" 2>/dev/null || true
  captured=1
  trap - RETURN
  echo "  → fresh verified aof-converted redis-dump.rdb ($(du -h "$DEST_DIR/redis-dump.rdb" | awk '{print $1}'))"
  return 0
}

if command -v redis-cli >/dev/null 2>&1 && \
   redis-cli -h "$REDIS_HOST_VALUE" -p "$REDIS_PORT_VALUE" ping >/dev/null 2>&1; then
  if ! capture_rdb; then
    if ! capture_aof_fallback; then
      backup_fail "fresh Redis RDB/AOF capture failed; no older snapshot was published"
    fi
  fi
else
  backup_fail "Redis is unavailable; no trigger-state snapshot was produced"
fi

# --- 3. Postgres pg_dump (automatic when the Cabinet has a work store) ---
PG_URL="${DATABASE_URL:-${NEON_CONNECTION_STRING:-}}"
rm -f "$DEST_DIR/postgres.dump" "$DEST_DIR/postgres-verify.txt"
if [ "$INCLUDE_PG" = "auto" ]; then
  if [ -n "$PG_URL" ]; then INCLUDE_PG=1; else INCLUDE_PG=0; fi
fi
if [ "$INCLUDE_PG" = "1" ]; then
  echo "[3/3] Postgres pg_dump..."
  if [ -z "$PG_URL" ]; then
    backup_fail "--pg requested but neither DATABASE_URL nor NEON_CONNECTION_STRING is set"
  elif ! command -v pg_dump >/dev/null 2>&1; then
    backup_fail "pg_dump not installed (brew install libpq && brew link --force libpq)"
  elif ! command -v pg_restore >/dev/null 2>&1; then
    backup_fail "pg_restore not installed; a Postgres dump cannot be validated"
  else
    PG_TMP="$DEST_DIR/.postgres.dump.tmp"
    PG_SERVICE_DIR="${HOME}/Library/Caches/cabinet/backup"
    mkdir -p "$PG_SERVICE_DIR"
    chmod 700 "$PG_SERVICE_DIR"
    PG_SERVICE="$PG_SERVICE_DIR/pg-service.$$"
    rm -f "$PG_TMP"
    PG_SERVICE_OK=0
    if CABINET_BACKUP_PG_URL="$PG_URL" python3.12 - "$PG_SERVICE" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

uri = os.environ.pop("CABINET_BACKUP_PG_URL")
out = Path(sys.argv[1])
parts = urlsplit(uri)
if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
    raise SystemExit("invalid Postgres URI")
fields = {"host": parts.hostname, "port": str(parts.port or 5432),
          "dbname": unquote(parts.path.lstrip("/"))}
if parts.username is not None:
    fields["user"] = unquote(parts.username)
if parts.password is not None:
    fields["password"] = unquote(parts.password)
allowed = {"sslmode", "sslrootcert", "sslcert", "sslkey", "channel_binding",
           "connect_timeout", "application_name", "options"}
for key, value in parse_qsl(parts.query, keep_blank_values=True):
    if key in allowed:
        fields[key] = value
for key, value in fields.items():
    if not value or any(c in value for c in "\r\n"):
        raise SystemExit(f"invalid Postgres URI field: {key}")
with out.open("x", encoding="utf-8") as handle:
    handle.write("[backup]\n")
    for key, value in fields.items():
        handle.write(f"{key}={value}\n")
out.chmod(0o600)
PY
    then
      PG_SERVICE_OK=1
    fi
    if [ "$PG_SERVICE_OK" = 1 ] \
      && PGSERVICEFILE="$PG_SERVICE" pg_dump --format=custom --no-owner --no-privileges \
        --file="$PG_TMP" service=backup 2>/dev/null \
      && [ -s "$PG_TMP" ] \
      && pg_restore --list "$PG_TMP" > "$DEST_DIR/postgres-verify.txt" 2>&1; then
      chmod 600 "$PG_TMP" 2>/dev/null || true
      mv "$PG_TMP" "$DEST_DIR/postgres.dump"
      rm -f "$PG_SERVICE"
      PG_SERVICE=""
      PG_SIZE=$(du -h "$DEST_DIR/postgres.dump" | awk '{print $1}')
      echo "  → validated postgres.dump ($PG_SIZE)"
    else
      rm -f "$PG_TMP" "$PG_SERVICE"
      PG_SERVICE=""
      rm -f "$DEST_DIR/postgres-verify.txt"
      backup_fail "pg_dump failed, was empty, or pg_restore rejected the snapshot"
    fi
  fi
else
  echo "[3/3] Postgres: not configured (use --pg to require it, --no-pg to suppress)"
fi

if [ "$FAILS" -gt 0 ]; then
  echo "BACKUP FAILED: $FAILS required snapshot component(s) missing." >&2
  exit 1
fi

# A completed staging snapshot is self-verifying and durable before it becomes
# visible at the dated path. A failed rerun never touches the prior snapshot.
rm -f "$DEST_DIR/INCOMPLETE"
(
  cd "$DEST_DIR"
  find . -type f ! -name SHA256SUMS -print0 | sort -z \
    | xargs -0 shasum -a 256 > SHA256SUMS
  shasum -a 256 -c SHA256SUMS >/dev/null
)
chmod -R go-rwx "$DEST_DIR" 2>/dev/null || true
fsync_snapshot_tree "$DEST_DIR"
PUBLISH_STARTED=1
publish_snapshot "$DEST_DIR" "$PUBLISHED_DIR"

# After an atomic exchange DEST_DIR contains the prior complete snapshot; after
# a first publication it no longer exists. In either case the dated path already
# names the new fully-synced snapshot before this cleanup starts.
rm -rf "$DEST_DIR"
python3.12 - "$BACKUP_DEST" <<'PY'
import os
import sys

fd = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
DEST_DIR=""
PUBLISH_STARTED=0

# --- Prune older backups beyond retention ---
echo ""
echo "Pruning backups older than $RETENTION_DAYS days..."
if [ -d "$BACKUP_DEST" ]; then
  find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' \
       -mtime "+$RETENTION_DAYS" -exec rm -rf {} \; 2>/dev/null || true
fi

TOTAL_KEPT=$(find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' 2>/dev/null | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$BACKUP_DEST" 2>/dev/null | awk '{print $1}')
echo "Backup complete. Retained $TOTAL_KEPT daily snapshot(s), total $TOTAL_SIZE in $BACKUP_DEST."
