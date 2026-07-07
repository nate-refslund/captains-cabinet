#!/bin/bash
# backlog-refine.sh — Triggers CPO to refine the backlog
# Runs every 12 hours via cron

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

REDIS_URL="${REDIS_URL:-redis://redis:6379}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)

TRIGGER_MSG="[$TIMESTAMP] Scheduled backlog refinement. Review /tasks for new items + status drift, incorporate recent research briefs from shared/interfaces/research-briefs/, update priorities in shared/backlog.md, and ensure top items have specs in shared/interfaces/product-specs/."

# Resolve CABINET_ROOT — env var wins, otherwise script-relative (cabinet/cron/.. = repo root)
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
TRIGGERS_LIB="$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"

# PRIMARY: Push to Redis Stream
if [ ! -f "$TRIGGERS_LIB" ]; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: triggers lib not found at $TRIGGERS_LIB (CABINET_ROOT=$CABINET_ROOT) — trigger NOT pushed" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$TRIGGERS_LIB"
if ! declare -f trigger_send > /dev/null; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: trigger_send not defined after sourcing $TRIGGERS_LIB — trigger NOT pushed" >&2
  exit 1
fi

# trigger_send writes to stderr on XADD failure; capture stderr so we can
# distinguish real success from silent-drop and refuse to print false-positive.
_send_err=$(OFFICER_NAME=cron trigger_send cpo "$TRIGGER_MSG" 2>&1 >/dev/null)
_send_rc=$?
if [ "$_send_rc" -ne 0 ] || [ -n "$_send_err" ]; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: trigger_send failed (rc=$_send_rc, err=${_send_err:-none}) — trigger NOT pushed" >&2
  exit 1
fi

echo "[$TIMESTAMP] Backlog refinement trigger pushed"
