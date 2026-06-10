#!/bin/bash
# ovi-weekly.sh — Trigger weekly OVI publication for the active product.

set -euo pipefail

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
ACTIVE_FILE="$CABINET_ROOT/instance/config/active-project.txt"
PRODUCT_SLUG="$(tr -d '[:space:]' < "$ACTIVE_FILE" 2>/dev/null || true)"
PRODUCT_SLUG="${PRODUCT_SLUG:-captains-cabinet}"
TIMESTAMP="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"

TRIGGER_MSG="[$TIMESTAMP] Weekly OVI publication due for ${PRODUCT_SLUG}. Run the org runtime path: compute/publish OVI as value-per-burden, publish the sanitized learning digest, and record operational proof against the three-week trend window."

if [ ! -r "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh" ]; then
  echo "[$TIMESTAMP] ERROR: missing trigger library at $CABINET_ROOT/cabinet/scripts/lib/triggers.sh" >&2
  exit 1
fi

. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"
OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG"

echo "[$TIMESTAMP] Weekly OVI trigger pushed (${PRODUCT_SLUG})"
