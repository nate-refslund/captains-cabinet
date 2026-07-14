#!/bin/bash
# start-inbound-poller.sh — launch the Captain inbound Telegram poller for an officer.
#
# Invoked by the officer's inbound LaunchAgent (com.cabinet.officer.<officer>-inbound).
# Sources cabinet/.env for the bot token + CAPTAIN_TELEGRAM_ID (never echoed), sets the
# officer's TELEGRAM_STATE_DIR (same path the officer uses, for the offset file), and
# runs officer-inbound-poller.py. See that script's header for why this exists (the
# telegram Channels plugin doesn't deliver to an idle officer session).
set -uo pipefail

OFFICER="${1:?Usage: start-inbound-poller.sh <officer>}"
REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"

cd "$REPO_ROOT" || exit 1

# Secrets: bot token + Captain id live in cabinet/.env (gitignored), sourced here.
if [ -f "cabinet/.env" ]; then
  set -a; source cabinet/.env; set +a
else
  echo "[start-inbound-poller] WARN: cabinet/.env not found — poller will lack the bot token" >&2
fi

# Same state dir the officer's telegram plugin/launcher uses (offset file lives here).
export TELEGRAM_STATE_DIR="${TELEGRAM_STATE_DIR:-$HOME/Library/Application Support/cabinet/telegram-state/$OFFICER}"
mkdir -p "$TELEGRAM_STATE_DIR"

# Captain timezone for the poller's MECHANICAL tap handling (tap_wire →
# pacing next-briefing horizons) — without it the defer math falls back to
# UTC and parks cards ~2h past the briefing the Captain meant (observed live
# 2026-07-11: ride_briefing_until 19:30Z instead of 17:30Z). Same one-line
# read as surface-pin-tick.sh; never source the config.
CAPTAIN_TZ_LINE="$(grep '^captain_timezone:' "$REPO_ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')"
export CABINET_CAPTAIN_TZ="${CABINET_CAPTAIN_TZ:-${CAPTAIN_TZ_LINE:-Europe/Berlin}}"

# Localhost Redis for the gate's briefing-route enqueue when a tap re-tick
# routes a card to the briefing (the intake backend's baked default is the
# docker-era host `redis`, unreachable on the Mac — same fix as
# surface-pin-tick.sh). The poller's own redis-cli calls already default to
# localhost; this aligns the in-process framework path with them.
export REDIS_HOST="${REDIS_HOST:-localhost}"

exec "$PY" "$REPO_ROOT/cabinet/scripts/officer-inbound-poller.py" "$OFFICER"
