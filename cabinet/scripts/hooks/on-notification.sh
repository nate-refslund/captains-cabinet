#!/bin/bash
# on-notification.sh — Fires when Claude Code receives a notification (Notification hook)
# Logs notification receipt and emits a session_started event (notification = new context).
# Receives on stdin: { notification payload }

HOOK_INPUT=$(cat)
# Bug fix (R5): hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

NOTIFICATION_TYPE=$(echo "$HOOK_INPUT" | jq -r '.type // "unknown"' 2>/dev/null)
NOTIFICATION_TITLE=$(echo "$HOOK_INPUT" | jq -r '.title // .message // "no-title"' 2>/dev/null | head -c 200)

# Log notification receipt
echo "on-notification: $OFFICER received notification type=$NOTIFICATION_TYPE at $TIMESTAMP" >&2

# Emit session event for audit trail
python3 "$CABINET_ROOT/framework/events/emitter.py" \
  session_started "$OFFICER" \
  "{\"trigger\": \"notification\", \"notification_type\": \"$NOTIFICATION_TYPE\"}" \
  2>/dev/null || true

exit 0
