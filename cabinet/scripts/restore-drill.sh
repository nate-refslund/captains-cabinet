#!/usr/bin/env bash
# restore-drill.sh — prove the Cabinet backups actually restore (lane-ops
# 2026-07-04, companion to cabinet/scripts/backup.sh / the com.cabinet.backup
# LaunchAgent).
#
# WHY THIS EXISTS: a backup nobody has restored is a hope, not a backup (the
# same "process green ≠ outcome true" lesson as the outcome-watchdog — the
# 2026-06-29 briefing ran clean while nothing was delivered). This drill takes
# the NEWEST snapshot under $BACKUP_DEST and performs a full restore into a
# throwaway temp dir, then verifies the restored tree carries the artifacts a
# real disaster recovery would need. A postgres.dump is restored into a fresh
# socket-only local PostgreSQL cluster; catalog inspection alone is not enough.
#
# HARD SAFETY CONTRACT (Corridor-reviewed posture, do not weaken):
#   * READ-ONLY against the backup, WRITE-ONLY into a fresh mktemp dir.
#   * NEVER writes to the live repo, ~/Library, Redis, or Postgres. There is
#     deliberately NO "--apply" mode — promoting a restored tree into the live
#     checkout is a human (Captain) action, by design.
#   * Exit 0 = drill PASSED; exit 1 = drill FAILED (missing/thin/corrupt
#     snapshot); exit 2 = usage error. The no-silent-cron watchdog picks up a
#     FAILED line via the "FATAL" marker if this ever runs under launchd.
#
# Usage:
#   bash cabinet/scripts/restore-drill.sh                      # newest snapshot
#   bash cabinet/scripts/restore-drill.sh --date 2026-07-04    # specific day
#   BACKUP_DEST=/Volumes/NAS/cabinet-backups bash cabinet/scripts/restore-drill.sh
#   CABINET_POSTGRES_BIN_DIR=/opt/homebrew/opt/postgresql@17/bin \
#     bash cabinet/scripts/restore-drill.sh                     # pin local server tools
#
# Run it after the first scheduled backup lands, and thereafter whenever the
# backup contents change shape (new state dirs, Postgres added, etc.).

set -uo pipefail

BACKUP_DEST="${BACKUP_DEST:-$HOME/Cabinet-Backups}"
WANT_DATE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --date) WANT_DATE="$2"; shift 2 ;;
    --date=*) WANT_DATE="${1#--date=}"; shift ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 0 ;;
    *) echo "restore-drill: unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAILS=0
fail() { echo "  ✗ FAIL: $1"; FAILS=$((FAILS + 1)); }
ok()   { echo "  ✓ $1"; }

REDIS_STATE_LUA='local keys=redis.call("KEYS","*"); table.sort(keys); local h={}; local expiries={}; for i,k in ipairs(keys) do local d=redis.call("DUMP",k); h[i]=redis.sha1hex(tostring(string.len(k))..":"..k..d); local ttl=redis.call("PTTL",k); if ttl >= 0 then local t=redis.call("TIME"); local now=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000); expiries[#expiries+1]=redis.sha1hex(k)..":"..string.format("%.0f",now+ttl); end; end; local out={tostring(#keys)..":"..redis.sha1hex(table.concat(h))}; for _,e in ipairs(expiries) do out[#out+1]=e; end; return out'
redis_state_fingerprint() {
  local output="$1"
  shift
  local -a client=("$@")
  local databases result first expiry db tmp="${output}.tmp.$$"
  databases=$("${client[@]}" --raw CONFIG GET databases 2>/dev/null | tail -1)
  case "$databases" in ''|*[!0-9]*) return 1 ;; esac
  [ "$databases" -gt 0 ] && [ "$databases" -le 1024 ] || return 1
  {
    printf 'FORMAT redis-dump-content-expiry-v2\n'
    printf 'DATABASES %s\n' "$databases"
    db=0
    while [ "$db" -lt "$databases" ]; do
      result=$("${client[@]}" -n "$db" --raw EVAL_RO "$REDIS_STATE_LUA" 0 2>/dev/null) || exit 1
      first=$(printf '%s\n' "$result" | sed -n '1p')
      printf '%s\n' "$first" | grep -Eq '^[0-9]+:[0-9a-f]{40}$' || exit 1
      printf 'DB %s %s\n' "$db" "$first"
      while IFS= read -r expiry; do
        [ -n "$expiry" ] || continue
        printf '%s\n' "$expiry" | grep -Eq '^[0-9a-f]{40}:[0-9]+$' || exit 1
        printf 'EXPIRY %s %s\n' "$db" "${expiry/:/ }"
      done <<EOF
$(printf '%s\n' "$result" | sed -n '2,$p')
EOF
      db=$((db + 1))
    done
  } > "$tmp" || { rm -f "$tmp"; return 1; }
  mv "$tmp" "$output"
}

redis_state_equal() {
  local expected="$1" actual="$2"
  # Keep the recovery check aligned with backup.sh's fixed 2s clock tolerance.
  python3.12 - "$expected" "$actual" 2000 <<'PY'
import sys
from pathlib import Path

def load(path: str):
    metadata = []
    expiries = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if parts and parts[0] == "EXPIRY" and len(parts) == 4:
            key = (parts[1], parts[2])
            if key in expiries:
                raise ValueError(f"duplicate expiry record: {key}")
            expiries[key] = int(parts[3])
        else:
            metadata.append(raw)
    return metadata, expiries

expected_meta, expected_expiry = load(sys.argv[1])
actual_meta, actual_expiry = load(sys.argv[2])
tolerance = int(sys.argv[3])
if expected_meta != actual_meta:
    raise SystemExit("Redis key/value digest differs")
if expected_expiry.keys() != actual_expiry.keys():
    raise SystemExit("Redis expiry key set differs")
for key, deadline in expected_expiry.items():
    delta = abs(deadline - actual_expiry[key])
    if delta > tolerance:
        raise SystemExit(f"Redis absolute expiry differs by {delta}ms for {key}")
PY
}

expected_redis_databases() {
  local state="$1" databases
  databases=$(sed -n 's/^DATABASES //p' "$state")
  case "$databases" in ''|*[!0-9]*) return 1 ;; esac
  [ "$databases" -gt 0 ] && [ "$databases" -le 1024 ] || return 1
  printf '%s\n' "$databases"
}

verify_restored_redis_state() {
  local socket="$1" expected="$2" actual="$RESTORE_DIR/redis-state-actual.txt"
  [ -f "$expected" ] || {
    fail "redis-state.txt is missing; source/restored equality cannot be proven"
    return 1
  }
  if ! redis_state_fingerprint "$actual" redis-cli -s "$socket"; then
    fail "could not fingerprint the disposable Redis state"
    return 1
  fi
  if redis_state_equal "$expected" "$actual"; then
    ok "restored Redis values and absolute expiries match the paused source"
    return 0
  fi
  fail "restored Redis state differs from redis-state.txt"
  return 1
}

# Emit a small, explicit candidate set only. We never scan arbitrary disks or
# trust a live DATABASE_URL. CABINET_POSTGRES_BIN_DIR is authoritative when set.
postgres_bin_candidates() {
  local configured="${CABINET_POSTGRES_BIN_DIR:-}" found="" config=""
  if [ -n "$configured" ]; then
    case "$configured" in
      /*) ;;
      *) return 1 ;;
    esac
    [ -d "$configured" ] || return 1
    (cd "$configured" && pwd -P)
    return
  fi
  found=$(command -v pg_restore 2>/dev/null || true)
  if [ -n "$found" ]; then dirname "$found"; fi
  config=$(command -v pg_config 2>/dev/null || true)
  if [ -n "$config" ]; then "$config" --bindir 2>/dev/null || true; fi
  local candidate
  for candidate in \
    /opt/homebrew/opt/postgresql@18/bin \
    /opt/homebrew/opt/postgresql@17/bin \
    /opt/homebrew/opt/postgresql@16/bin \
    /opt/homebrew/opt/postgresql@15/bin \
    /opt/homebrew/opt/postgresql@14/bin \
    /opt/homebrew/opt/postgresql/bin \
    /usr/local/opt/postgresql@18/bin \
    /usr/local/opt/postgresql@17/bin \
    /usr/local/opt/postgresql@16/bin \
    /usr/local/opt/postgresql@15/bin \
    /usr/local/opt/postgresql@14/bin \
    /usr/local/opt/postgresql/bin \
    /usr/lib/postgresql/18/bin \
    /usr/lib/postgresql/17/bin \
    /usr/lib/postgresql/16/bin \
    /usr/lib/postgresql/15/bin \
    /usr/lib/postgresql/14/bin \
    /Library/PostgreSQL/18/bin \
    /Library/PostgreSQL/17/bin \
    /Library/PostgreSQL/16/bin \
    /Applications/Postgres.app/Contents/Versions/latest/bin; do
    [ -d "$candidate" ] && printf '%s\n' "$candidate"
  done
}

find_pg_restore_bin() {
  local candidates candidate
  candidates=$(postgres_bin_candidates) || return 1
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if [ -x "$candidate/pg_restore" ]; then
      PG_RESTORE_BIN="$candidate/pg_restore"
      return 0
    fi
  done <<EOF
$candidates
EOF
  return 1
}

find_postgres_server_bin_dir() {
  local candidates candidate tool complete restore_major server_major
  candidates=$(postgres_bin_candidates) || return 1
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    complete=1
    for tool in pg_restore initdb pg_ctl createdb psql postgres; do
      [ -x "$candidate/$tool" ] || complete=0
    done
    if [ "$complete" = 1 ]; then
      restore_major=$("$candidate/pg_restore" --version 2>/dev/null \
        | sed -n 's/.*PostgreSQL[^0-9]*\([0-9][0-9]*\).*/\1/p')
      server_major=$("$candidate/postgres" --version 2>/dev/null \
        | sed -n 's/.*PostgreSQL[^0-9]*\([0-9][0-9]*\).*/\1/p')
      [ -n "$restore_major" ] && [ "$restore_major" = "$server_major" ] || complete=0
    fi
    if [ "$complete" = 1 ]; then
      POSTGRES_BIN_DIR="$candidate"
      return 0
    fi
  done <<EOF
$candidates
EOF
  return 1
}

# ── 1. Pick the snapshot ────────────────────────────────────────────────────
# Snapshot dirs are named YYYY-MM-DD by backup.sh; lexicographic sort == date
# sort, so `sort | tail -1` is the newest. A --date arg pins a specific day.
if [ ! -d "$BACKUP_DEST" ]; then
  echo "restore-drill FATAL: no backup destination at $BACKUP_DEST (has the"
  echo "com.cabinet.backup LaunchAgent ever run? see INSTALL-flip.md)"
  exit 1
fi
if [ -n "$WANT_DATE" ]; then
  SNAP="$BACKUP_DEST/$WANT_DATE"
else
  SNAP=$(find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' \
         2>/dev/null | sort | tail -1)
fi
if [ -z "${SNAP:-}" ] || [ ! -d "$SNAP" ]; then
  echo "restore-drill FATAL: no snapshot dir found under $BACKUP_DEST"
  exit 1
fi
echo "=== Restore drill: $SNAP ==="
if [ -f "$SNAP/INCOMPLETE" ]; then
  echo "restore-drill FATAL: snapshot is marked INCOMPLETE: $SNAP"
  exit 1
fi
if [ -f "$SNAP/SHA256SUMS" ]; then
  if (cd "$SNAP" && shasum -a 256 -c SHA256SUMS >/dev/null 2>&1); then
    ok "SHA256 manifest verifies"
  else
    fail "SHA256 manifest rejected the snapshot"
  fi
else
  fail "SHA256SUMS is missing (snapshot predates verified backup format)"
fi

# ── 2. Restore into a throwaway dir ─────────────────────────────────────────
# A real recovery would rsync cabinet-state/ back over the live checkout; the
# drill performs the IDENTICAL copy into a temp dir so the mechanics (perms,
# symlinks, partial writes) are exercised without touching anything live.
RESTORE_DIR=$(mktemp -d /tmp/cabinet-restore-drill.XXXXXX)
REDIS_VERIFY_SOCKET=""
POSTGRES_PG_CTL=""
POSTGRES_DATA=""
POSTGRES_RUNNING=0
cleanup_drill() {
  if [ "$POSTGRES_RUNNING" = 1 ] && [ -x "$POSTGRES_PG_CTL" ] && [ -d "$POSTGRES_DATA" ]; then
    "$POSTGRES_PG_CTL" -D "$POSTGRES_DATA" -m immediate -w stop >/dev/null 2>&1 || true
  fi
  if [ -n "$REDIS_VERIFY_SOCKET" ] && [ -S "$REDIS_VERIFY_SOCKET" ]; then
    redis-cli -s "$REDIS_VERIFY_SOCKET" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
  fi
  rm -f "$REDIS_VERIFY_SOCKET" 2>/dev/null || true
  rm -rf "$RESTORE_DIR"
}
trap cleanup_drill EXIT
if rsync -a "$SNAP/cabinet-state/" "$RESTORE_DIR/cabinet-state/" 2>/dev/null; then
  ok "rsync restore into $RESTORE_DIR/cabinet-state"
else
  fail "rsync restore errored (snapshot unreadable or cabinet-state/ missing)"
fi

# ── 3. Verify the restored tree ─────────────────────────────────────────────
# The three state roots retain their topology under cabinet-state/. We assert
# the copy is non-trivial and carries the recovery-critical artifacts.
FILE_COUNT=$(find "$RESTORE_DIR/cabinet-state" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "${FILE_COUNT:-0}" -ge 10 ]; then
  ok "restored file count: $FILE_COUNT (≥10)"
else
  fail "restored tree is thin ($FILE_COUNT files) — snapshot likely incomplete"
fi

# Recovery-critical paths. Accept the former flattened layout for older
# snapshots, but the current writer preserves shared/interfaces/ explicitly.
critical_any() {  # critical_any <label> <path...> — pass if ANY path exists
  local what="$1"; shift
  for p in "$@"; do
    if [ -e "$RESTORE_DIR/$p" ]; then ok "$what present ($p)"; return 0; fi
  done
  fail "$what missing (checked: $*)"
}
critical_any "captain decisions"  "cabinet-state/captain-decisions.md" \
                                  "cabinet-state/interfaces/captain-decisions.md" \
                                  "cabinet-state/shared/interfaces/captain-decisions.md"
critical_any "instance config"    "cabinet-state/instance/config" \
                                  "cabinet-state/config"
critical_any "officer memory"     "cabinet-state/memory" \
                                  "cabinet-state/instance/memory"

# ── 4. Redis dump integrity ─────────────────────────────────────────────────
# Both formats are checked structurally, loaded with truncation recovery
# disabled, and compared to the paused-source state digest recorded at backup
# time. Neither path touches the live server.
REDIS_MODE=$(cat "$SNAP/redis-backup-mode.txt" 2>/dev/null || true)
if [ -z "$REDIS_MODE" ] && [ -f "$SNAP/redis-dump.rdb" ]; then REDIS_MODE=rdb; fi
if [ "$REDIS_MODE" = rdb ] && [ -f "$SNAP/redis-dump.rdb" ]; then
  if ! command -v redis-check-rdb >/dev/null 2>&1; then
    fail "redis-check-rdb is missing; cannot validate redis-dump.rdb"
  elif ! redis-check-rdb "$SNAP/redis-dump.rdb" >/dev/null 2>&1; then
    fail "redis-dump.rdb is corrupt (redis-check-rdb rejected it)"
  elif ! command -v redis-server >/dev/null 2>&1 || ! command -v redis-cli >/dev/null 2>&1; then
    fail "redis-server/redis-cli missing; cannot restore-test redis-dump.rdb"
  else
    RDB_DIR="$RESTORE_DIR/redis-rdb"
    mkdir -p "$RDB_DIR"
    cp "$SNAP/redis-dump.rdb" "$RDB_DIR/dump.rdb"
    REDIS_DATABASES=$(expected_redis_databases "$SNAP/redis-state.txt" 2>/dev/null || true)
    if [ -z "$REDIS_DATABASES" ]; then
      fail "redis-state.txt has an invalid database count"
    else
      REDIS_VERIFY_SOCKET="/tmp/cabinet-restore-redis-$$.sock"
      rm -f "$REDIS_VERIFY_SOCKET"
      if ! redis-server --port 0 --unixsocket "$REDIS_VERIFY_SOCKET" --unixsocketperm 700 \
        --dir "$RDB_DIR" --dbfilename dump.rdb --databases "$REDIS_DATABASES" \
        --appendonly no --aof-load-truncated no --save '' --daemonize yes \
        --pidfile "$RDB_DIR/redis.pid" --logfile "$RDB_DIR/redis.log" >/dev/null 2>&1; then
        fail "disposable Redis could not start from redis-dump.rdb"
      else
        REDIS_READY=0
        for _i in $(seq 1 100); do
          if redis-cli -s "$REDIS_VERIFY_SOCKET" PING 2>/dev/null | grep -qx PONG; then
            REDIS_READY=1
            break
          fi
          sleep 0.1
        done
        if [ "$REDIS_READY" = 1 ]; then
          ok "redis-dump.rdb passes redis-check-rdb and loads with truncation recovery disabled"
          verify_restored_redis_state "$REDIS_VERIFY_SOCKET" "$SNAP/redis-state.txt" || true
        else
          fail "disposable Redis did not load redis-dump.rdb"
        fi
      fi
    fi
  fi
elif [ "$REDIS_MODE" = aof ] && [ -f "$SNAP/redis-aof.tgz" ]; then
  if ! command -v redis-check-aof >/dev/null 2>&1; then
    fail "redis-check-aof is missing; cannot validate redis-aof.tgz"
  elif ! command -v redis-server >/dev/null 2>&1 || ! command -v redis-cli >/dev/null 2>&1; then
    fail "redis-server/redis-cli missing; cannot restore-test redis-aof.tgz"
  else
    AOF_TOP=$(tar -tzf "$SNAP/redis-aof.tgz" 2>/dev/null | head -1 | cut -d/ -f1)
    case "$AOF_TOP" in
      ''|.|..|*/*) fail "redis-aof.tgz has an unsafe/missing top-level directory" ;;
      *)
        AOF_DIR="$RESTORE_DIR/redis-aof"
        mkdir -p "$AOF_DIR"
        if ! tar -C "$AOF_DIR" -xzf "$SNAP/redis-aof.tgz"; then
          fail "redis-aof.tgz cannot be extracted"
        else
          AOF_MANIFEST="$AOF_DIR/$AOF_TOP/appendonly.aof.manifest"
          REDIS_DATABASES=$(expected_redis_databases "$SNAP/redis-state.txt" 2>/dev/null || true)
          if [ ! -f "$AOF_MANIFEST" ]; then
            fail "redis-aof.tgz is missing appendonly.aof.manifest"
          elif ! redis-check-aof "$AOF_MANIFEST" >/dev/null 2>&1; then
            fail "redis-aof.tgz is corrupt or truncated (redis-check-aof rejected it)"
          elif [ -z "$REDIS_DATABASES" ]; then
            fail "redis-state.txt has an invalid database count"
          else
            REDIS_VERIFY_SOCKET="/tmp/cabinet-restore-redis-$$.sock"
            rm -f "$REDIS_VERIFY_SOCKET"
            if ! redis-server --port 0 --unixsocket "$REDIS_VERIFY_SOCKET" --unixsocketperm 700 \
              --dir "$AOF_DIR" --appendonly yes --appenddirname "$AOF_TOP" \
              --aof-load-truncated no --databases "$REDIS_DATABASES" --save '' \
              --daemonize yes --pidfile "$AOF_DIR/redis.pid" \
              --logfile "$AOF_DIR/redis.log" >/dev/null 2>&1; then
              fail "disposable Redis could not start from redis-aof.tgz"
            else
              REDIS_READY=0
              for _i in $(seq 1 100); do
                if redis-cli -s "$REDIS_VERIFY_SOCKET" PING 2>/dev/null | grep -qx PONG; then
                  REDIS_READY=1
                  break
                fi
                sleep 0.1
              done
              if [ "$REDIS_READY" = 1 ]; then
                ok "redis-aof.tgz passes redis-check-aof and loads with truncation recovery disabled"
                verify_restored_redis_state "$REDIS_VERIFY_SOCKET" "$SNAP/redis-state.txt" || true
              else
                fail "disposable Redis did not load redis-aof.tgz"
              fi
            fi
          fi
        fi
        ;;
    esac
  fi
else
  fail "no verified Redis RDB/AOF component in snapshot"
fi

# ── 5. Postgres dump integrity ──────────────────────────────────────────────
if [ -f "$SNAP/postgres.dump" ]; then
  PG_RESTORE_BIN=""
  POSTGRES_BIN_DIR=""
  if ! find_pg_restore_bin; then
    fail "pg_restore is missing; postgres.dump cannot be validated"
  elif ! LC_ALL=C "$PG_RESTORE_BIN" --list "$SNAP/postgres.dump" \
    > "$RESTORE_DIR/postgres-catalog.list" 2> "$RESTORE_DIR/postgres-list.log"; then
    fail "postgres.dump is corrupt or version-incompatible (pg_restore --list rejected it)"
  else
    ok "postgres.dump passes pg_restore --list"
    if ! find_postgres_server_bin_dir; then
      fail "no complete local PostgreSQL server toolchain is available for a disposable restore"
    else
      # If discovery selected a different complete installation, make that
      # installation prove it can parse the archive before initializing data.
      PG_RESTORE_BIN="$POSTGRES_BIN_DIR/pg_restore"
      if ! LC_ALL=C "$PG_RESTORE_BIN" --list "$SNAP/postgres.dump" \
        > "$RESTORE_DIR/postgres-catalog.list" 2> "$RESTORE_DIR/postgres-list.log"; then
        fail "the local PostgreSQL server version cannot read postgres.dump"
      else
        POSTGRES_DATA="$RESTORE_DIR/postgres-data"
        POSTGRES_SOCKET="$RESTORE_DIR/postgres-socket"
        POSTGRES_PORT=$((55000 + ($$ % 1000)))
        POSTGRES_DB="cabinet_restore_drill"
        POSTGRES_PG_CTL="$POSTGRES_BIN_DIR/pg_ctl"
        mkdir -p "$POSTGRES_SOCKET"
        chmod 700 "$POSTGRES_SOCKET"

        if ! LC_ALL=C "$POSTGRES_BIN_DIR/initdb" -D "$POSTGRES_DATA" \
          --username=postgres --auth=trust --no-locale --encoding=UTF8 --no-sync \
          > "$RESTORE_DIR/postgres-init.log" 2>&1; then
          fail "could not initialize the disposable PostgreSQL cluster"
        elif ! "$POSTGRES_PG_CTL" -D "$POSTGRES_DATA" -w -t 30 \
          -o "-F -h '' -k $POSTGRES_SOCKET -p $POSTGRES_PORT -c unix_socket_permissions=0700" \
          start > "$RESTORE_DIR/postgres-start.log" 2>&1; then
          # pg_ctl can time out after the postmaster has spawned; always make
          # cleanup attempt a stop even when the start command reports failure.
          POSTGRES_RUNNING=1
          fail "could not start the disposable socket-only PostgreSQL server"
        else
          POSTGRES_RUNNING=1
          if ! "$POSTGRES_BIN_DIR/createdb" --host="$POSTGRES_SOCKET" \
            --port="$POSTGRES_PORT" --username=postgres "$POSTGRES_DB" \
            > "$RESTORE_DIR/postgres-createdb.log" 2>&1; then
            fail "could not create the disposable restore database"
          elif ! LC_ALL=C "$PG_RESTORE_BIN" \
            --host="$POSTGRES_SOCKET" --port="$POSTGRES_PORT" --username=postgres \
            --dbname="$POSTGRES_DB" --no-owner --no-privileges --exit-on-error \
            "$SNAP/postgres.dump" > "$RESTORE_DIR/postgres-restore.log" 2>&1; then
            fail "postgres.dump failed during the disposable database restore"
          elif ! "$POSTGRES_BIN_DIR/psql" --host="$POSTGRES_SOCKET" \
            --port="$POSTGRES_PORT" --username=postgres --dbname="$POSTGRES_DB" \
            --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 \
            --command="SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast';" \
            > "$RESTORE_DIR/postgres-catalog-sanity.txt" 2> "$RESTORE_DIR/postgres-query.log"; then
            fail "the restored database failed its catalog sanity query"
          else
            POSTGRES_RELATIONS=$(tr -d '[:space:]' < "$RESTORE_DIR/postgres-catalog-sanity.txt")
            case "$POSTGRES_RELATIONS" in
              ''|*[!0-9]*) fail "the catalog sanity query returned a non-numeric result" ;;
              *)
                PG_VERSION=$("$POSTGRES_BIN_DIR/postgres" --version 2>/dev/null || echo "PostgreSQL version unknown")
                ok "postgres.dump restores into disposable PostgreSQL ($POSTGRES_RELATIONS user relations; $PG_VERSION)"
                ;;
            esac
          fi
          if "$POSTGRES_PG_CTL" -D "$POSTGRES_DATA" -m immediate -w stop \
            > "$RESTORE_DIR/postgres-stop.log" 2>&1; then
            POSTGRES_RUNNING=0
          else
            fail "disposable PostgreSQL could not be stopped cleanly"
          fi
        fi
      fi
    fi
  fi
else
  ok "no postgres.dump in snapshot (no configured work store or explicit --no-pg)"
fi

# ── 6. Verdict ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "RESTORE DRILL PASSED — $SNAP restores cleanly (drill dir discarded)."
  exit 0
fi
echo "restore-drill FATAL: $FAILS check(s) failed for $SNAP — the backup may"
echo "not survive a real recovery. Fix backup.sh / the snapshot before trusting it."
exit 1
