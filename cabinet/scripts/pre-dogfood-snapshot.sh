#!/usr/bin/env bash
# Capture a verified local recovery point before reconciling a live Cabinet.
# This script owns checkout/secret/Postgres recovery only. Redis recovery is
# deliberately delegated to backup.sh + restore-drill.sh so there is one
# reviewed capture, replay, and equality-proof path. Secret values are never
# printed. The destination is mode 700.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: pre-dogfood-snapshot.sh [--root PATH] [--dest PATH]

Defaults:
  --root  repository root containing this script
  --dest  ~/.cabinet-recovery/pre-dogfood-<UTC timestamp>

Postgres is required when DATABASE_URL or NEON_CONNECTION_STRING is present
in cabinet/.env. A configured database that cannot be dumped or validated
makes the snapshot fail closed.

Redis is intentionally excluded. Before reconciliation or a dogfood soak,
run both `bash cabinet/scripts/backup.sh` and
`bash cabinet/scripts/restore-drill.sh`; that separate green restore drill is
the mandatory Redis T0 gate. This command's VERIFIED verdict does not cover
Redis.
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

# Redis recovery intentionally has no implementation here. The daily backup
# path owns all Redis capture and validation, including replay-unstable Streams
# state. Duplicating a weaker path here previously allowed a fresh-connection
# WAITAOF no-op, a raw AOF publication, and a PING+DBSIZE-only "verification"
# to masquerade as a recovery proof. Keep the scope exclusion in the artifact
# itself so this script's VERIFIED line cannot be read as a whole-Cabinet gate.
cat > "$DEST/redis-excluded.txt" <<'EOF'
Redis is intentionally excluded from this checkout/Postgres recovery snapshot.

Mandatory Redis T0 gate before reconciliation or a dogfood soak:
  bash cabinet/scripts/backup.sh
  bash cabinet/scripts/restore-drill.sh

Only a green restore drill from the reviewed daily backup path proves Redis
recovery. The pre-dogfood-snapshot.sh VERIFIED verdict does not cover Redis.
EOF

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
