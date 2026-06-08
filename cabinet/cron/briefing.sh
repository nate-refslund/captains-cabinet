#!/bin/bash
# briefing.sh — Triggers CoS to produce a daily briefing
# Runs at 07:00 and 19:00 CET via cron
[ -f /etc/environment.cabinet ] && source /etc/environment.cabinet
#
# Delivery mechanism:
#   1. Redis RPUSH → post-tool-use hook surfaces it to Officer (RELIABLE)
#   2. Inbox file append → backup audit trail (PASSIVE)

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
BRIEFING_TYPE="${1:-morning}"

REDIS_URL="${REDIS_URL:-redis://redis:6379}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)

TRIGGER_MSG="[$TIMESTAMP] Daily $BRIEFING_TYPE briefing due. Compile status from all Officers and send briefing to Warroom Telegram group. Include: progress since last briefing, current blockers, upcoming priorities, decisions needed from Captain. CAPABILITY GAPS: run 'python3 cabinet/scripts/org-runtime.py gaps list' — if any gaps are status=pending_captain, surface them in the decisions-needed section as 'N capability proposal(s) awaiting your approve/decline at /gaps' with each need + proposed approach + any hard-ceiling touches; also note how many gaps were auto-resolved as skills since the last briefing. Omit the section entirely if there are zero gaps."

# Resolve CABINET_ROOT — env var wins, otherwise script-relative (cabinet/cron/.. = repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
TRIGGERS_LIB="$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"

# PRIMARY: Push to Redis Stream — surfaced by post-tool-use hook, crash-safe
if [ ! -f "$TRIGGERS_LIB" ]; then
  echo "[$TIMESTAMP] briefing.sh FATAL: triggers lib not found at $TRIGGERS_LIB (CABINET_ROOT=$CABINET_ROOT) — trigger NOT pushed" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$TRIGGERS_LIB"
if ! declare -f trigger_send > /dev/null; then
  echo "[$TIMESTAMP] briefing.sh FATAL: trigger_send not defined after sourcing $TRIGGERS_LIB — trigger NOT pushed" >&2
  exit 1
fi

# trigger_send writes to stderr on XADD failure; capture stderr so we can
# distinguish real success from silent-drop and refuse to print false-positive.
_send_err=$(OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG" 2>&1 >/dev/null)
_send_rc=$?
if [ "$_send_rc" -ne 0 ] || [ -n "$_send_err" ]; then
  echo "[$TIMESTAMP] briefing.sh FATAL: trigger_send failed (rc=$_send_rc, err=${_send_err:-none}) — trigger NOT pushed" >&2
  exit 1
fi

echo "[$TIMESTAMP] Briefing trigger pushed ($BRIEFING_TYPE)"
