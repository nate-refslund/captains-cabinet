#!/bin/bash
# retrospective.sh — Triggers CoS to run a Cabinet retrospective
# Runs every 3 days via cron
[ -f /etc/environment.cabinet ] && source /etc/environment.cabinet

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

REDIS_URL="${REDIS_URL:-redis://redis:6379}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)

TRIGGER_MSG="[$TIMESTAMP] Scheduled Cabinet retrospective. Run the Reflection Loop: 1) Review all experience records since last retro, 2) Identify recurring patterns (note at 2x, propose change at 3x), 3) Draft improvement proposals, 4) Validate against known-good scenarios, 5) Submit proposals to Captain via Telegram, 6) Update skill library."

# PRIMARY: Push to Redis Stream
. /opt/founders-cabinet/cabinet/scripts/lib/triggers.sh
OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG"

echo "[$TIMESTAMP] Retrospective trigger pushed"
