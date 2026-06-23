#!/bin/bash
# run-frontdoor-briefing.sh — the launchd entry point for the cabinet's recurring
# unified briefing on the one channel (@NateHQChairBot).
#
# Pulls real signals into the front-door intake and runs ONE send-path pass:
#   morning_synthesis.enqueue_synthesis  →  run_frontdoor.run_send_path
#
# Secrets: the bot token lives ONLY in cabinet/.env (chmod 600). We read the two
# values we need into the process env here — never echoed, never written to the
# plist. Everything else (allow_sends gate, captain-only recipient) is enforced
# downstream in channel.send. Reversible: `launchctl unload` the plist.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/cabinet/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "run-frontdoor-briefing: missing $ENV_FILE" >&2
  exit 1
fi

# Read ONLY the two values needed for the send; do not source the whole file
# (avoids exporting empty optional keys that could shadow screenpipe's env).
export TELEGRAM_COS_TOKEN="$(grep '^TELEGRAM_COS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
export CAPTAIN_TELEGRAM_ID="$(grep '^CAPTAIN_TELEGRAM_ID=' "$ENV_FILE" | cut -d= -f2-)"

# Runtime so channel.send's allow_sends() gate opens; localhost Redis for intake.
export CABINET_ENV=runtime
export REDIS_HOST="${REDIS_HOST:-localhost}"

# launchd hands us a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that EXCLUDES
# Homebrew. The intake module's stdlib backend shells out to `redis-cli`, which
# lives in /opt/homebrew/bin — without this the briefing crashes at enqueue with
# `FileNotFoundError: redis-cli` and NO briefing reaches Nate (observed
# 2026-06-23 07:30). Prepend Homebrew bin so redis-cli (and the brew python)
# resolve. Matches this script's existing /opt/homebrew/bin/python3.12 default.
export PATH="/opt/homebrew/bin:$PATH"

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
exec "$PY" -m framework.frontdoor.run_briefing
