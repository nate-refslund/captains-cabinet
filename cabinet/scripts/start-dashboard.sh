#!/bin/bash
# start-dashboard.sh — run the Cabinet dashboard (Next.js) Mac-native.
#
# Serves on http://127.0.0.1:<CABINET_DASHBOARD_PORT> (default 3100). The
# office wall-display lives at /display (read-only, unauthenticated by design).
# The port is CONFIG, not a constant: everything that probes or links to the
# dashboard reads the same recorded value (cabinet/scripts/lib/dashboard.sh).
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

# WHICH CABINET this process serves, and WHICH BUILD it is serving. Two facts,
# two variables, and the update health gate reads them as two different legs:
#
#   CABINET_SOURCE_COMMIT        the installed identity, resolved HERE, at every
#                                start. An installed Cabinet is gitless, so the
#                                answer comes from the export's own manifest —
#                                which an update rewrites before it restarts
#                                this process. /api/health reports it at request
#                                time, so a process that was never restarted
#                                still answers with the identity it was started
#                                with, and the gate sees that.
#   CABINET_BUILD_SOURCE_COMMIT  the commit the BUILD was made from, inlined by
#                                `next build`. It only changes when something
#                                rebuilds, which is exactly the fact the gate
#                                wants from it. Defaults to the identity above,
#                                so a first-run build here stamps itself
#                                correctly.
#
# Absent on both ⇒ empty, and the update health gate then refuses rather than
# passing an unidentifiable process.
if [ -z "${CABINET_SOURCE_COMMIT:-}" ]; then
  if [ -f "$CABINET_ROOT/egg-manifest.json" ]; then
    CABINET_SOURCE_COMMIT="$(sed -n 's/.*"source_commit"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' "$CABINET_ROOT/egg-manifest.json" | head -1)"
  fi
  if [ -z "${CABINET_SOURCE_COMMIT:-}" ] && [ -d "$CABINET_ROOT/.git" ]; then
    CABINET_SOURCE_COMMIT="$(git -C "$CABINET_ROOT" rev-parse HEAD 2>/dev/null || true)"
  fi
fi
export CABINET_SOURCE_COMMIT="${CABINET_SOURCE_COMMIT:-}"
export CABINET_BUILD_SOURCE_COMMIT="${CABINET_BUILD_SOURCE_COMMIT:-$CABINET_SOURCE_COMMIT}"

# Build on first run (or if .next was cleared).
if [ ! -d "$DASH_DIR/.next" ]; then
  echo "start-dashboard: no build found — building (first run, ~1-2 min)..."
  if [ ! -d "$DASH_DIR/node_modules" ]; then
    # --include=dev is LOAD-BEARING. NODE_ENV=production is exported above
    # because the SERVER needs it, and npm honors that by OMITTING
    # devDependencies — where the entire build toolchain lives
    # (@tailwindcss/postcss, tailwindcss, typescript). A plain `npm ci` here
    # installs 201 of 244 packages and the build below then dies with
    # "Cannot find module '@tailwindcss/postcss'". Latent since this script
    # was written: nothing ran the first-run branch unattended until hatch.sh
    # started the dashboard for the operator, and the bind tests pre-created
    # node_modules/.next precisely to skip it (measured 2026-08-02, on a real
    # `git archive HEAD` export).
    npm ci --include=dev 2>&1 | tail -5 || { echo "start-dashboard: npm ci failed" >&2; exit 1; }
  fi
  # tail -30, not -10: this now runs unattended at the end of a hatch, and a
  # 10-line tail cut the actual "Cannot find module" line off the top of the
  # turbopack trace, leaving an operator with "build failed" and nothing else.
  npm run build 2>&1 | tail -30 || { echo "start-dashboard: build failed" >&2; exit 1; }
fi

echo "start-dashboard: serving on http://127.0.0.1:$PORT  (display: /display; bind: $HOST)"
exec npm start -- --port "$PORT" --hostname "$HOST"
