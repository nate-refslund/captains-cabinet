#!/bin/bash
# start-dashboard.sh — run the Cabinet dashboard (Next.js) Mac-native.
#
# Serves on http://localhost:3100. The office wall-display lives at
# http://localhost:3100/display (read-only, unauthenticated by design).
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
PORT="${CABINET_DASHBOARD_PORT:-3100}"

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

echo "start-dashboard: serving on http://localhost:$PORT  (display: /display)"
exec npm start -- --port "$PORT"
