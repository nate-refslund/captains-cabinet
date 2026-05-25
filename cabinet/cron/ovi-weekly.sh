#!/bin/bash
# ovi-weekly.sh — Trigger weekly OVI publication for the active product.

set -uo pipefail

[ -f /etc/environment.cabinet ] && source /etc/environment.cabinet

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
ACTIVE_FILE="$CABINET_ROOT/instance/config/active-project.txt"
PRODUCT_SLUG="$(cat "$ACTIVE_FILE" 2>/dev/null | tr -d '[:space:]')"
PRODUCT_SLUG="${PRODUCT_SLUG:-captains-cabinet}"
TIMESTAMP="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"

TRIGGER_MSG="[$TIMESTAMP] Weekly OVI publication due for ${PRODUCT_SLUG}. Run the org runtime path: compute/publish OVI as value-per-burden, publish the sanitized learning digest, and record operational proof against the three-week trend window."

. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"
OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG"

echo "[$TIMESTAMP] Weekly OVI trigger pushed (${PRODUCT_SLUG})"
