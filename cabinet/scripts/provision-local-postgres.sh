#!/bin/bash
# provision-local-postgres.sh — local work store: PostgreSQL 16 + pgvector.
#
# De-cloud doctrine (2026-07-09): the Cabinet boots with NO cloud account.
# The work store (org_events ledger, cabinet_memory pgvector, mission/role
# state, the local officer_tasks board) defaults to a LOCAL PostgreSQL 16
# with the pgvector extension: installed via Homebrew, bound to localhost,
# credentialed with the auto-generated POSTGRES_PASSWORD from cabinet/.env,
# and exposed to every existing consumer by writing NEON_CONNECTION_STRING
# (the historical env NAME every reader already resolves) into the
# gitignored cabinet/.env. Neon remains the documented CLOUD ALTERNATIVE:
# paste your own NEON_CONNECTION_STRING via setup-env.sh and this script
# no-ops — it NEVER overwrites an existing connection string.
#
# Idempotent; called by setup-mac.sh Step 3.5; safe to run standalone.
#
# Usage: provision-local-postgres.sh [--check|--help]
#   (no args)  Provision: brew install postgresql@16 + pgvector (if absent),
#              start the service, create role + db, enable pgvector, write
#              the connection string to cabinet/.env (chmod 600).
#   --check    Read-only verification, no installs, no writes, no network
#              beyond a local pg_isready probe. Exit 0 = work store
#              configured (connection string present; local strings also
#              probed for liveness — at the host:port EMBEDDED in the
#              stored string — when pg_isready is available). Exit 1 =
#              not provisioned.
#   --help,-h  Print this header.
#
# Env overrides: CABINET_LOCAL_PG_PORT (default 5432),
#                CABINET_LOCAL_PG_DB / CABINET_LOCAL_PG_ROLE (default cabinet).
#
# Secrets doctrine: the password is read from / written to cabinet/.env only;
# it travels to psql via stdin SQL + PGPASSWORD env (never argv), and every
# log line masks it (postgresql://cabinet:***@...).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at cabinet/scripts/, so repo root is TWO levels up (R4/R5 pattern).
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"
ENV_EXAMPLE="$CABINET_ROOT/cabinet/.env.example"

PG_FORMULA="postgresql@16"
PG_PORT="${CABINET_LOCAL_PG_PORT:-5432}"
PG_DB="${CABINET_LOCAL_PG_DB:-cabinet}"
PG_ROLE="${CABINET_LOCAL_PG_ROLE:-cabinet}"

MODE="provision"
case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  # Self-maintaining help: print the leading comment block only (a numeric
  # sed range drifts when the header grows and leaks code lines).
  --help|-h) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
  *) echo "provision-local-postgres: unknown arg: $1" >&2; exit 64 ;;
esac

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

# Identifiers are interpolated into SQL — hard-restrict their shape so no
# quoting gymnastics are ever needed (defense in depth; both default to
# "cabinet" and only change via env override).
ident_ok() { printf '%s' "$1" | grep -Eq '^[a-z_][a-z0-9_]{0,62}$'; }
if ! ident_ok "$PG_DB" || ! ident_ok "$PG_ROLE"; then
  fail "invalid db/role identifier (want ^[a-z_][a-z0-9_]*$): db=$PG_DB role=$PG_ROLE"
  exit 64
fi
case "$PG_PORT" in
  ''|*[!0-9]*) fail "invalid port: $PG_PORT"; exit 64 ;;
esac

# --- .env value quoting (a value here is `source`d by bash in 30+ scripts) ---
# _env_quote emits provably-literal values BARE (the common case: tokens, ids,
# keys round-trip byte-for-byte) and SINGLE-QUOTES anything else (' -> '\''), so
# `FOO=$(rm -rf ~)` becomes inert text on source instead of a command run at
# assignment. _env_unquote inverts it for reads that parse the value's TEXT.
# sed does the ' escaping (bash 3.2's ${//} replacement mishandles it).
_env_quote() {
  case "$1" in
    '') printf '%s' "$1" ;;
    *[!A-Za-z0-9_.:/=+@%,-]*)
      printf "'"; printf '%s' "$1" | sed "s/'/'\\\\''/g"; printf "'" ;;
    *) printf '%s' "$1" ;;
  esac
}
_env_unquote() {
  local v="$1"
  case "$v" in
    "'"*"'") v="${v#\'}"; v="${v%\'}"; v="$(printf '%s' "$v" | sed "s/'\\\\''/'/g")" ;;
    '"'*'"') v="${v#\"}"; v="${v%\"}" ;;
  esac
  printf '%s' "$v"
}

# Read current value of KEY=... from .env. Empty string if unset. Decodes a
# safe-quoted value back to its logical string (the same as `source` would).
current_value() {
  local key="$1" line
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1)"
  [ -n "$line" ] || return 0
  _env_unquote "${line#"${key}="}"
}

# Update KEY=value in .env (adds the line if KEY absent). Same quoting as
# setup-env.sh so both writers behave identically — the value is written
# through _env_quote so it can never execute when cabinet/.env is sourced.
set_env_key() {
  local key="$1" value="$2" qval
  qval="$(_env_quote "$value")"
  local tmp; tmp="$(mktemp)"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # awk reads the quoted value from the ENVIRON (never -v: -v processes the
    # backslashes in '\''); FS/OFS "=" keeps the match on the key alone.
    qval="$qval" awk -v k="$key" \
      'BEGIN { FS="="; OFS="="; q=ENVIRON["qval"] } $1 == k { print k "=" q; next } { print }' \
      "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    printf '%s\n' "${key}=${qval}" >> "$tmp"
  fi
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

MASKED_LOCAL_URL="postgresql://${PG_ROLE}:***@127.0.0.1:${PG_PORT}/${PG_DB}"

# ---------------------------------------------------------------------------
# Mode: --check (read-only)
# ---------------------------------------------------------------------------
if [ "$MODE" = "check" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    fail "no cabinet/.env — run: bash cabinet/scripts/setup-env.sh --defaults"
    exit 1
  fi
  conn="$(current_value "NEON_CONNECTION_STRING")"
  if [ -z "$conn" ]; then
    fail "work store not configured (NEON_CONNECTION_STRING empty) — run: bash cabinet/scripts/provision-local-postgres.sh"
    exit 1
  fi
  # Local strings get a liveness probe when pg_isready is on PATH; remote
  # (cloud-alternative) strings are accepted without a network call.
  case "$conn" in
    *127.0.0.1*|*localhost*)
      # Probe the host:port EMBEDDED in the stored string — a provision run
      # under CABINET_LOCAL_PG_PORT=5433 must later --check 5433 without
      # needing the same override. Parse after the LAST '@' (our writer
      # URL-encodes credentials, so '@' in a password is %40).
      chk_hostport="${conn##*@}"; chk_hostport="${chk_hostport%%/*}"
      chk_host="${chk_hostport%%:*}"
      chk_port="$PG_PORT"
      case "$chk_hostport" in
        *:*)
          case "${chk_hostport##*:}" in
            ''|*[!0-9]*) warn "could not parse a port from the stored connection string — probing default :$PG_PORT" ;;
            *) chk_port="${chk_hostport##*:}" ;;
          esac
          ;;
      esac
      # Belt: host rides pg_isready argv — restrict to sane hostname chars.
      case "$chk_host" in
        ''|*[!A-Za-z0-9._-]*) chk_host="127.0.0.1" ;;
      esac
      if command -v pg_isready >/dev/null 2>&1; then
        if pg_isready -q -h "$chk_host" -p "$chk_port"; then
          ok "work store configured: local PostgreSQL reachable (postgresql://***@${chk_host}:${chk_port})"
          exit 0
        fi
        fail "connection string points local but PostgreSQL is not accepting connections on ${chk_host}:${chk_port}"
        exit 1
      fi
      warn "pg_isready not on PATH — cannot probe; connection string is present"
      ok "work store configured (unprobed local string)"
      exit 0
      ;;
    *)
      ok "work store configured (remote/cloud connection string present — not probed)"
      exit 0
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# Mode: provision
# ---------------------------------------------------------------------------
echo "==========================================="
echo "  Local work store — PostgreSQL 16 + pgvector"
echo "==========================================="

# Ensure .env exists (same template bootstrap as setup-env.sh).
if [ ! -f "$ENV_FILE" ]; then
  if [ ! -f "$ENV_EXAMPLE" ]; then
    fail "$ENV_EXAMPLE not found — cannot create cabinet/.env"
    exit 1
  fi
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "Created $ENV_FILE from template"
fi
chmod 600 "$ENV_FILE"

# Never clobber an existing connection string (Neon cloud alternative, or a
# previous provisioning run).
existing_conn="$(current_value "NEON_CONNECTION_STRING")"
if [ -n "$existing_conn" ]; then
  ok "NEON_CONNECTION_STRING already set — nothing to do (value not shown)"
  exit 0
fi

if ! command -v brew >/dev/null 2>&1; then
  fail "Homebrew required for local PostgreSQL. Install from https://brew.sh — or paste a Neon string via setup-env.sh"
  exit 1
fi

# 1) Install postgresql@16 + pgvector (idempotent).
if brew list --versions "$PG_FORMULA" >/dev/null 2>&1; then
  ok "$PG_FORMULA already installed"
else
  echo "  Installing $PG_FORMULA via Homebrew..."
  if brew install "$PG_FORMULA" >/dev/null 2>&1; then
    ok "$PG_FORMULA installed"
  else
    fail "brew install $PG_FORMULA failed — run manually: brew install $PG_FORMULA"
    exit 1
  fi
fi
if brew list --versions pgvector >/dev/null 2>&1; then
  ok "pgvector already installed"
else
  echo "  Installing pgvector via Homebrew..."
  if brew install pgvector >/dev/null 2>&1; then
    ok "pgvector installed"
  else
    # Fail-soft (EMBED-SEAM precedent): the work store is still fully usable
    # without the semantic layer; CREATE EXTENSION below will warn honestly.
    warn "brew install pgvector failed — semantic memory DDL will be unavailable until fixed"
  fi
fi

# postgresql@16 is keg-only: resolve its bin dir instead of relying on PATH.
PGBIN="$(brew --prefix "$PG_FORMULA" 2>/dev/null)/bin"
if [ ! -x "$PGBIN/psql" ]; then
  if command -v psql >/dev/null 2>&1; then
    PGBIN="$(dirname "$(command -v psql)")"
    warn "using psql from PATH ($PGBIN) — $PG_FORMULA keg bin not found"
  else
    fail "psql not found (looked in $PGBIN and PATH)"
    exit 1
  fi
fi

# 2) Start the server (Homebrew default config listens on localhost only).
if "$PGBIN/pg_isready" -q -h 127.0.0.1 -p "$PG_PORT" 2>/dev/null; then
  ok "PostgreSQL already accepting connections on 127.0.0.1:$PG_PORT"
else
  echo "  Starting $PG_FORMULA via Homebrew services..."
  brew services start "$PG_FORMULA" >/dev/null 2>&1 || true
  tries=0
  until "$PGBIN/pg_isready" -q -h 127.0.0.1 -p "$PG_PORT" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -ge 15 ]; then
      fail "PostgreSQL did not come up on 127.0.0.1:$PG_PORT after 15s — check: brew services info $PG_FORMULA"
      exit 1
    fi
    sleep 1
  done
  ok "PostgreSQL started"
fi

# 3) Ensure POSTGRES_PASSWORD (auto-generated by setup-env.sh; generate here
#    too so standalone runs work). Alphanumeric-only output.
pg_password="$(current_value "POSTGRES_PASSWORD")"
if [ -z "$pg_password" ]; then
  pg_password="$(openssl rand -base64 32 2>/dev/null | tr -d '/+=' | head -c 32)"
  if [ -z "$pg_password" ]; then
    fail "could not auto-generate POSTGRES_PASSWORD (openssl missing?)"
    exit 1
  fi
  set_env_key "POSTGRES_PASSWORD" "$pg_password"
  ok "POSTGRES_PASSWORD auto-generated (32 chars) and saved to cabinet/.env"
else
  ok "POSTGRES_PASSWORD already set (reusing)"
fi

# Admin connection: the Homebrew install makes the current macOS user the
# superuser with local trust auth. Fixed argv; SQL always via stdin.
admin_psql() {
  "$PGBIN/psql" -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$PG_PORT" -d "$1" -q -tA -f -
}

# Honesty check: whatever server answers on the port is what we provision
# into. If another PostgreSQL major already holds 127.0.0.1:$PG_PORT, say so
# instead of claiming "PostgreSQL 16" (pgvector DDL then depends on THAT
# server's extensions; the fail-soft below covers the gap).
server_version="$(printf "SHOW server_version;\n" | admin_psql postgres 2>/dev/null || true)"
case "$server_version" in
  16.*|16)
    ok "server on 127.0.0.1:$PG_PORT is PostgreSQL $server_version" ;;
  "")
    warn "could not read server_version — continuing" ;;
  *)
    warn "server on 127.0.0.1:$PG_PORT is PostgreSQL $server_version, NOT the $PG_FORMULA keg — provisioning into the server that holds the port"
    warn "  (want the @16 keg instead? stop the other server, or set CABINET_LOCAL_PG_PORT to a free port and re-run)"
    ;;
esac

# 4) Role: create if absent, then converge the password to cabinet/.env
#    (single quotes doubled — SQL string escape; password never in argv).
#    The doubling rides a $sq variable ON PURPOSE: the backslash form
#    "${x//\'/\'\'}" keeps its backslashes on /bin/bash 3.2 (the fresh-Mac
#    bash), which corrupts the statement AND the stored password.
sq="'"
pwd_sql="${pg_password//$sq/$sq$sq}"
role_exists="$(printf "SELECT 1 FROM pg_roles WHERE rolname = '%s';\n" "$PG_ROLE" | admin_psql postgres 2>/dev/null || true)"
if [ "$role_exists" = "1" ]; then
  if printf "ALTER ROLE %s WITH LOGIN PASSWORD '%s';\n" "$PG_ROLE" "$pwd_sql" | admin_psql postgres >/dev/null 2>&1; then
    ok "role '$PG_ROLE' present (password synced to cabinet/.env)"
  else
    warn "could not sync role password (continuing — local trust auth still works)"
  fi
else
  if printf "CREATE ROLE %s WITH LOGIN PASSWORD '%s';\n" "$PG_ROLE" "$pwd_sql" | admin_psql postgres >/dev/null 2>&1; then
    ok "role '$PG_ROLE' created"
  else
    fail "could not create role '$PG_ROLE' — check server logs (brew services info $PG_FORMULA)"
    exit 1
  fi
fi

# 5) Database owned by the role.
db_exists="$(printf "SELECT 1 FROM pg_database WHERE datname = '%s';\n" "$PG_DB" | admin_psql postgres 2>/dev/null || true)"
if [ "$db_exists" = "1" ]; then
  ok "database '$PG_DB' present"
else
  if printf "CREATE DATABASE %s OWNER %s;\n" "$PG_DB" "$PG_ROLE" | admin_psql postgres >/dev/null 2>&1; then
    ok "database '$PG_DB' created (owner $PG_ROLE)"
  else
    fail "could not create database '$PG_DB'"
    exit 1
  fi
fi

# 6) pgvector extension (superuser action, per-database). Fail-soft: without
#    it the ledger / tasks / roles all work; only semantic-memory DDL waits.
if printf "CREATE EXTENSION IF NOT EXISTS vector;\n" | admin_psql "$PG_DB" >/dev/null 2>&1; then
  ok "pgvector extension enabled in '$PG_DB'"
else
  warn "CREATE EXTENSION vector failed — semantic memory degraded to keyword-only until fixed."
  warn "  Likely cause: Homebrew pgvector built against a different PG major."
  warn "  Fix: brew reinstall pgvector (or use the Neon cloud alternative via setup-env.sh)"
fi

# 7) Verify the bind stays localhost-only (Homebrew default). Warn-only —
#    we never edit postgresql.conf from here.
listen="$(printf "SHOW listen_addresses;\n" | admin_psql postgres 2>/dev/null || true)"
case "$listen" in
  ""|localhost|127.0.0.1*|::1*)
    ok "listen_addresses is localhost-only (${listen:-unreadable})"
    ;;
  *)
    warn "listen_addresses='$listen' is wider than localhost — tighten postgresql.conf (the cabinet work store must not be network-exposed)"
    ;;
esac

# 8) Verify the role can actually connect over TCP (what the connection
#    string will do). PGPASSWORD via env, never argv.
if PGPASSWORD="$pg_password" "$PGBIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_ROLE" -d "$PG_DB" -qtAc "SELECT 1" 2>/dev/null | grep -q '^1$'; then
  ok "role '$PG_ROLE' connects over 127.0.0.1:$PG_PORT"
else
  fail "role '$PG_ROLE' cannot connect over TCP — check pg_hba.conf (need: host $PG_DB $PG_ROLE 127.0.0.1/32 scram-sha-256 or trust)"
  exit 1
fi

# 9) Write the connection string (password URL-encoded; env-passed to python).
enc_password="$(CABINET_PG_PWD="$pg_password" python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["CABINET_PG_PWD"], safe=""))' 2>/dev/null)"
if [ -z "$enc_password" ]; then
  fail "python3 URL-encode failed — connection string not written"
  exit 1
fi
set_env_key "NEON_CONNECTION_STRING" "postgresql://${PG_ROLE}:${enc_password}@127.0.0.1:${PG_PORT}/${PG_DB}"
ok "connection string written to cabinet/.env: $MASKED_LOCAL_URL"
ok "(env NAME stays NEON_CONNECTION_STRING — the name every consumer already reads; the VALUE is your local server. Prefer managed cloud? Paste a Neon string via setup-env.sh --force)"

echo ""
echo "  Local work store ready. Schemas apply on the next preset load"
echo "  (setup-mac.sh Step 5 / cabinet/scripts/load-preset.sh)."
echo "==========================================="
