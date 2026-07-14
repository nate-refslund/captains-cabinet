#!/bin/bash
# retrospective.sh — Triggers CoS to run a Cabinet retrospective
# Runs every 3 days via cron

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# Source cabinet/.env (Telegram tokens etc.) if present — launchd/cron runs
# get no login environment, so without this every Telegram send dies
# token-less. set -a exports the vars to child scripts (send-to-group.sh /
# send-to-warroom.sh and helpers).
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# B4 Mac portability (matches research-sweep.sh + lib/triggers.sh): an
# explicit REDIS_HOST (the generated launchd wrapper sets localhost) WINS;
# REDIS_URL is the fallback for docker deployments that set it in the compose
# env. The old unconditional derive clobbered the caller's REDIS_HOST with the
# docker-era `redis` hostname → FATAL on every Mac-native run.
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
REDIS_HOST="${REDIS_HOST:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)}"
REDIS_PORT="${REDIS_PORT:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)}"

TRIGGER_MSG="[$TIMESTAMP] Scheduled Cabinet retrospective. Run the Reflection Loop: 1) Review all experience records since last retro, 2) Identify recurring patterns (note at 2x, propose change at 3x), 3) Draft improvement proposals, 4) Validate against known-good scenarios, 5) Submit proposals to Captain via Telegram, 6) Update skill library."

# PRIMARY: Push to Redis Stream. Source the triggers lib via CABINET_ROOT
# (the old hardcoded /opt/founders-cabinet path never exists on Mac, leaving
# trigger_send undefined while the script still printed success) and fail
# FATAL — loudly, non-zero — if the lib or the function is missing (mirrors
# briefing.sh / research-sweep.sh).
TRIGGERS_LIB="$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"
if [ ! -f "$TRIGGERS_LIB" ]; then
  echo "[$TIMESTAMP] retrospective.sh FATAL: triggers lib not found at $TRIGGERS_LIB (CABINET_ROOT=$CABINET_ROOT) — trigger NOT pushed" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$TRIGGERS_LIB"
if ! declare -f trigger_send > /dev/null; then
  echo "[$TIMESTAMP] retrospective.sh FATAL: trigger_send not defined after sourcing $TRIGGERS_LIB — trigger NOT pushed" >&2
  exit 1
fi

# trigger_send writes to stderr on XADD failure; capture stderr so we can
# distinguish real success from silent-drop and refuse to print false-positive.
_send_err=$(OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG" 2>&1 >/dev/null)
_send_rc=$?
if [ "$_send_rc" -ne 0 ] || [ -n "$_send_err" ]; then
  echo "[$TIMESTAMP] retrospective.sh FATAL: trigger_send failed (rc=$_send_rc, err=${_send_err:-none}) — trigger NOT pushed" >&2
  exit 1
fi

echo "[$TIMESTAMP] Retrospective trigger pushed"
