#!/bin/bash
# on-session-end.sh — Fires when the CC v2.1.150 session terminates (SessionEnd hook)
# Modern replacement for the legacy Stop hook (session-stop.sh) which is now
# reserved for "Claude finished responding" within a session.
#
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, reason }
# Reason matcher values: clear, resume, logout, prompt_input_exit,
#                       bypass_permissions_disabled, other
#
# Responsibilities:
#   1. Emit session_ended event
#   2. Flush the transactional outbox if anything is pending (best-effort)
#   3. Stamp Redis with session-end timestamp for the supervisor

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
REASON=$(echo "$HOOK_INPUT" | jq -r '.reason // "other"' 2>/dev/null)

echo "on-session-end: $OFFICER session=$SESSION_ID reason=$REASON at $TIMESTAMP" >&2

# Stamp Redis (24h TTL) so the supervisor can distinguish "ended cleanly" from "crashed"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SET "cabinet:session:terminated:$OFFICER" "$TIMESTAMP|reason=$REASON" EX 86400 \
  > /dev/null 2>&1 || true

# Emit session_ended event
python3 "$CABINET_ROOT/framework/events/emitter.py" \
  session_ended "$OFFICER" \
  "{\"session_id\": \"$SESSION_ID\", \"reason\": \"$REASON\", \"ended_at\": \"$TIMESTAMP\"}" \
  2>/dev/null || true

# Best-effort outbox flush. The outbox relay normally runs on cron, but at
# clean session exit we get a free chance to drain anything pending so
# downstream systems see updates before the officer goes idle.
OUTBOX_RELAY="$CABINET_ROOT/cabinet/scripts/outbox-relay.py"
if [ -x "$OUTBOX_RELAY" ] || [ -f "$OUTBOX_RELAY" ]; then
  timeout 10s python3 "$OUTBOX_RELAY" --once 2>/dev/null || true
fi

exit 0
