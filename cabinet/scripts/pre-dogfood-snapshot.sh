#!/usr/bin/env bash
# Capture a verified local recovery point before reconciling a live Cabinet.
# Secret values are never printed. The destination is mode 700.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: pre-dogfood-snapshot.sh [--root PATH] [--dest PATH]

Defaults:
  --root  repository root containing this script
  --dest  ~/.cabinet-recovery/pre-dogfood-<UTC timestamp>

Environment:
  REDIS_HOST / REDIS_PORT  Redis endpoint (defaults 127.0.0.1:6379)

Postgres is required when DATABASE_URL or NEON_CONNECTION_STRING is present
in cabinet/.env. A configured database that cannot be dumped or validated
makes the snapshot fail closed.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) ROOT="${2:?--root requires a path}"; shift 2 ;;
    --dest) DEST="${2:?--dest requires a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "pre-dogfood-snapshot: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

ROOT="$(cd "$ROOT" && pwd -P)"
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null
if [ -z "$DEST" ]; then
  DEST="$HOME/.cabinet-recovery/pre-dogfood-$(date -u +%Y%m%dT%H%M%SZ)"
fi
case "$DEST" in
  /*) ;;
  *) DEST="$PWD/$DEST" ;;
esac

umask 077
mkdir -p "$DEST"
chmod 700 "$DEST"
if [ -n "$(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  echo "pre-dogfood-snapshot: destination must be empty: $DEST" >&2
  exit 65
fi

fail() {
  printf 'pre-dogfood-snapshot: FAILED: %s\n' "$*" >&2
  printf '%s\n' "$*" > "$DEST/FAILED"
  exit 1
}

status_manifest() {
  local out="$1"
  {
    git -C "$ROOT" status --porcelain=v2 --branch
    printf 'HEAD %s\n' "$(git -C "$ROOT" rev-parse HEAD)"
    if git -C "$ROOT" rev-parse --verify origin/master >/dev/null 2>&1; then
      printf 'ORIGIN_MASTER %s\n' "$(git -C "$ROOT" rev-parse origin/master)"
      printf 'DIVERGENCE %s\n' "$(git -C "$ROOT" rev-list --left-right --count HEAD...origin/master)"
    fi
  } > "$out"
}

status_manifest "$DEST/worktree-before.txt"

# Preserve every ref plus exact staged, unstaged, modified, and untracked data.
git -C "$ROOT" bundle create "$DEST/repository.bundle" --all
git -C "$ROOT" bundle verify "$DEST/repository.bundle" > "$DEST/bundle-verify.txt" 2>&1 \
  || fail "Git bundle verification failed"
git -C "$ROOT" diff --binary --full-index HEAD -- > "$DEST/tracked-from-head.patch"
git -C "$ROOT" diff --cached --binary --full-index -- > "$DEST/staged.patch"
git -C "$ROOT" ls-files --deleted -z > "$DEST/deleted-files.zlist"
git -C "$ROOT" ls-files --modified --others --exclude-standard -z > "$DEST/dirty-files.zlist"
if [ -s "$DEST/dirty-files.zlist" ]; then
  tar -C "$ROOT" --null -T "$DEST/dirty-files.zlist" -czf "$DEST/dirty-files.tgz"
else
  tar -czf "$DEST/dirty-files.tgz" --files-from /dev/null
fi

# Ignored runtime secrets are local rollback material, never shareable evidence.
find "$ROOT/cabinet" -maxdepth 3 -type f \
  \( -name '.env' -o -name '.env.local' -o -name '.env.production' -o -name '.env.development' \) \
  -print0 > "$DEST/runtime-secret-files.zlist"
if [ -s "$DEST/runtime-secret-files.zlist" ]; then
  tar --null -T "$DEST/runtime-secret-files.zlist" -czf "$DEST/runtime-secrets.tgz"
else
  tar -czf "$DEST/runtime-secrets.tgz" --files-from /dev/null
fi

# redis-cli --rdb requests and writes a fresh replication snapshot.
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
command -v redis-cli >/dev/null 2>&1 || fail "redis-cli is unavailable"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING 2>/dev/null | grep -qx PONG \
  || fail "Redis is unreachable"

redis_rdb_ok=0
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --rdb "$DEST/redis.rdb.tmp" >/dev/null &
redis_rdb_pid=$!
for _ in $(seq 1 100); do
  if ! kill -0 "$redis_rdb_pid" 2>/dev/null; then
    if wait "$redis_rdb_pid"; then redis_rdb_ok=1; fi
    break
  fi
  sleep 0.1
done
if kill -0 "$redis_rdb_pid" 2>/dev/null; then
  kill "$redis_rdb_pid" 2>/dev/null || true
  wait "$redis_rdb_pid" 2>/dev/null || true
fi

if [ "$redis_rdb_ok" -eq 1 ]; then
  command -v redis-check-rdb >/dev/null 2>&1 || fail "redis-check-rdb is unavailable"
  mv "$DEST/redis.rdb.tmp" "$DEST/redis.rdb"
  redis-check-rdb "$DEST/redis.rdb" > "$DEST/redis-verify.txt" 2>&1 \
    || fail "Redis snapshot validation failed"
  printf '%s\n' rdb > "$DEST/redis-backup-mode.txt"
else
  rm -f "$DEST/redis.rdb.tmp"
  # A stuck server-side BGSAVE must not make recovery impossible. When AOF is
  # healthy, briefly pause writes, wait for the local append log to fsync, and
  # copy the complete multipart AOF set. Reads continue during the pause.
  command -v redis-server >/dev/null 2>&1 || fail "fresh RDB timed out and redis-server is unavailable for AOF validation"
  appendonly="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw CONFIG GET appendonly | tail -1)"
  aof_rewrite="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw INFO persistence | sed -n 's/^aof_rewrite_in_progress:\([0-9]*\).*/\1/p')"
  aof_status="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw INFO persistence | sed -n 's/^aof_last_write_status:\([^[:space:]]*\).*/\1/p')"
  [ "$appendonly" = yes ] || fail "fresh RDB timed out and Redis AOF is disabled"
  [ "$aof_rewrite" = 0 ] || fail "fresh RDB timed out while an AOF rewrite is active"
  [ "$aof_status" = ok ] || fail "fresh RDB timed out and AOF write status is not healthy"
  redis_dir="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw CONFIG GET dir | tail -1)"
  appenddirname="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw CONFIG GET appenddirname | tail -1)"
  [ -d "$redis_dir/$appenddirname" ] || fail "Redis AOF directory is missing"

  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CLIENT PAUSE 60000 WRITE >/dev/null \
    || fail "could not pause Redis writes for AOF capture"
  redis_paused=1
  trap 'if [ "${redis_paused:-0}" = 1 ]; then redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" CLIENT UNPAUSE >/dev/null 2>&1 || true; fi; rm -f "${PG_SERVICE:-}"' EXIT
  waitaof="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --raw WAITAOF 1 0 5000 | head -1)"
  if [ "$waitaof" != 1 ]; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CLIENT UNPAUSE >/dev/null 2>&1 || true
    redis_paused=0
    fail "Redis AOF did not fsync before capture"
  fi
  tar -C "$redis_dir" -czf "$DEST/redis-aof.tgz.tmp" "$appenddirname"
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CLIENT UNPAUSE >/dev/null \
    || fail "Redis write pause could not be released"
  redis_paused=0
  mv "$DEST/redis-aof.tgz.tmp" "$DEST/redis-aof.tgz"

  redis_verify_dir="$DEST/.redis-verify"
  mkdir -p "$redis_verify_dir"
  tar -C "$redis_verify_dir" -xzf "$DEST/redis-aof.tgz"
  redis_verify_socket="$redis_verify_dir/redis.sock"
  redis-server --port 0 --unixsocket "$redis_verify_socket" --unixsocketperm 700 \
    --dir "$redis_verify_dir" --appendonly yes --appenddirname "$appenddirname" \
    --daemonize yes --pidfile "$redis_verify_dir/redis.pid" \
    --logfile "$redis_verify_dir/redis.log" >/dev/null \
    || fail "disposable Redis AOF validation server failed to start"
  redis_verify_ready=0
  for _ in $(seq 1 100); do
    if redis-cli -s "$redis_verify_socket" PING 2>/dev/null | grep -qx PONG; then
      redis_verify_ready=1
      break
    fi
    sleep 0.1
  done
  if [ "$redis_verify_ready" != 1 ]; then
    fail "Redis AOF validation server could not load the captured data"
  fi
  {
    printf 'PING PONG\n'
    printf 'DBSIZE %s\n' "$(redis-cli -s "$redis_verify_socket" DBSIZE)"
  } > "$DEST/redis-verify.txt"
  redis-cli -s "$redis_verify_socket" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
  rm -rf "$redis_verify_dir"
  printf '%s\n' aof > "$DEST/redis-backup-mode.txt"
fi

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

PG_URL="$(dotenv_value DATABASE_URL "$ROOT/cabinet/.env")"
if [ -z "$PG_URL" ]; then
  PG_URL="$(dotenv_value NEON_CONNECTION_STRING "$ROOT/cabinet/.env")"
fi
if [ -n "$PG_URL" ]; then
  command -v pg_dump >/dev/null 2>&1 || fail "Postgres is configured but pg_dump is unavailable"
  command -v pg_restore >/dev/null 2>&1 || fail "Postgres is configured but pg_restore is unavailable"
  # Keep the connection string out of argv. Convert the URI into a private
  # libpq service file without evaluating shell syntax; remove it on every
  # exit path. (libpq does not URI-expand a dbname= value in a service file.)
  PG_SERVICE="$DEST/.pg_service.conf"
  CABINET_SNAPSHOT_PG_URL="$PG_URL" python3.12 - "$PG_SERVICE" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

uri = os.environ.pop("CABINET_SNAPSHOT_PG_URL")
out = Path(sys.argv[1])
parts = urlsplit(uri)
if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
    raise SystemExit("invalid Postgres URI")
fields = {
    "host": parts.hostname,
    "port": str(parts.port or 5432),
    "dbname": unquote(parts.path.lstrip("/")),
}
if parts.username is not None:
    fields["user"] = unquote(parts.username)
if parts.password is not None:
    fields["password"] = unquote(parts.password)
allowed_query = {
    "sslmode", "sslrootcert", "sslcert", "sslkey", "channel_binding",
    "connect_timeout", "application_name", "options",
}
for key, value in parse_qsl(parts.query, keep_blank_values=True):
    if key in allowed_query:
        fields[key] = value
for key, value in fields.items():
    if not value or any(c in value for c in "\r\n"):
        raise SystemExit(f"invalid Postgres URI field: {key}")
with out.open("x", encoding="utf-8") as handle:
    handle.write("[recovery]\n")
    for key, value in fields.items():
        handle.write(f"{key}={value}\n")
out.chmod(0o600)
PY
  trap 'rm -f "${PG_SERVICE:-}"' EXIT
  PGSERVICEFILE="$PG_SERVICE" pg_dump --format=custom --no-owner --no-privileges \
    --file="$DEST/postgres.dump.tmp" service=recovery \
    || fail "Postgres dump failed"
  mv "$DEST/postgres.dump.tmp" "$DEST/postgres.dump"
  pg_restore --list "$DEST/postgres.dump" > "$DEST/postgres-verify.txt" \
    || fail "Postgres dump validation failed"
  rm -f "$PG_SERVICE"
  trap - EXIT
else
  printf '%s\n' 'Postgres not configured in cabinet/.env at snapshot time.' \
    > "$DEST/postgres-not-configured.txt"
fi

status_manifest "$DEST/worktree-after.txt"
cmp -s "$DEST/worktree-before.txt" "$DEST/worktree-after.txt" \
  || fail "worktree changed during capture; retry from a quiescent state"

(
  cd "$DEST"
  find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name FAILED -print0 \
    | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  shasum -a 256 -c SHA256SUMS > checksum-verify.txt
)
chmod -R go-rwx "$DEST"

printf 'pre-dogfood-snapshot: VERIFIED %s\n' "$DEST"
