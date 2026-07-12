#!/bin/bash
# start-dashboard.sh — run the Cabinet dashboard (Next.js) Mac-native.
#
# Serves on http://127.0.0.1:3100. The office wall-display lives at
# http://127.0.0.1:3100/display (read-only, unauthenticated by design).
#
# Port/bind config (Wave D app-feel, D4): CABINET_DASHBOARD_PORT (default
# 3100) and CABINET_DASHBOARD_HOST (default 127.0.0.1 — loopback-only; the
# CC-LOOP / OC-LOOPBACK ruling landed 2026-07-12 and flipped the previous
# 0.0.0.0 default). Explicit env (launchd plist) wins over cabinet/.env,
# which wins over the default — captured BEFORE the .env sourcing below so
# `set -a` cannot flip precedence. Remote reach: `tailscale serve` is the
# blessed path; tailnet/LAN opt-out = CABINET_DASHBOARD_HOST=0.0.0.0 in
# cabinet/.env (a live box that needs plain tailnet http reach sets it
# BEFORE this flip deploys — see cabinet/docs/mac-mini-deploy-runbook.md).
#
# Wrapped by the com.cabinet.dashboard LaunchAgent (KeepAlive). Sources
# cabinet/.env so the dashboard sees NEON_CONNECTION_STRING, DASHBOARD_PASSWORD,
# Telegram tokens, etc. Sets CABINET_RUNTIME_MODE=native so the docker.ts data
# layer runs commands locally (cwd = repo) instead of `docker exec`.
#
# First run builds the app (npm ci + npm run build); subsequent runs reuse the
# build. Re-build by deleting cabinet/dashboard/.next.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DASH_DIR="$CABINET_ROOT/cabinet/dashboard"
# Capture explicit-env values BEFORE cabinet/.env is sourced: the `set -a`
# sourcing below overwrites the environment, so a naive PORT= after it would
# let .env override the launchd plist env (precedence trap, D4a).
ENV_DASH_PORT="${CABINET_DASHBOARD_PORT:-}"
ENV_DASH_HOST="${CABINET_DASHBOARD_HOST:-}"

if [ ! -d "$DASH_DIR" ]; then
  echo "start-dashboard: $DASH_DIR not found" >&2
  exit 1
fi

# Load cabinet/.env into the environment (so Next.js server sees the secrets).
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi

# Precedence: explicit env (launchd plist) > cabinet/.env > default (D4a fix
# — previously PORT was resolved before the sourcing, so .env was ignored).
# HOST default 127.0.0.1 = loopback-only (CC-LOOP ruling 2026-07-12); remote
# reach via `tailscale serve` or the CABINET_DASHBOARD_HOST=0.0.0.0 opt-out —
# see the header.
PORT="${ENV_DASH_PORT:-${CABINET_DASHBOARD_PORT:-3100}}"
HOST="${ENV_DASH_HOST:-${CABINET_DASHBOARD_HOST:-127.0.0.1}}"

# Mac-native data layer + localhost Redis.
export CABINET_ROOT
export CABINET_RUNTIME_MODE="native"
export CABINET_ENV_PATH="$CABINET_ROOT/cabinet/.env"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export NODE_ENV="production"

cd "$DASH_DIR"

# Build on first run (or if .next was cleared).
if [ ! -d "$DASH_DIR/.next" ]; then
  echo "start-dashboard: no build found — building (first run, ~1-2 min)..."
  if [ ! -d "$DASH_DIR/node_modules" ]; then
    npm ci 2>&1 | tail -5 || { echo "start-dashboard: npm ci failed" >&2; exit 1; }
  fi
  npm run build 2>&1 | tail -10 || { echo "start-dashboard: build failed" >&2; exit 1; }
fi

echo "start-dashboard: serving on http://127.0.0.1:$PORT  (display: /display; bind: $HOST)"
exec npm start -- --port "$PORT" --hostname "$HOST"
