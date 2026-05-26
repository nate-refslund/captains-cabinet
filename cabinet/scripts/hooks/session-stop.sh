#!/bin/bash
# session-stop.sh — Fires when the Claude Code session ends (Stop hook)
# Emits session_ended event and logs to Redis for observability.
# Receives on stdin: { session_id, transcript_path, cwd, ... }

HOOK_INPUT=$(cat)
# Bug fix (R5): hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Log session end to Redis (24h TTL)
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SET "cabinet:session:ended:$OFFICER" "$TIMESTAMP" EX 86400 \
  > /dev/null 2>&1

# Emit session_ended event
python3 "$CABINET_ROOT/framework/events/emitter.py" \
  session_ended "$OFFICER" \
  "{\"session_id\": \"$SESSION_ID\", \"ended_at\": \"$TIMESTAMP\"}" \
  2>/dev/null || true

echo "session-stop: $OFFICER session ended at $TIMESTAMP" >&2

exit 0
