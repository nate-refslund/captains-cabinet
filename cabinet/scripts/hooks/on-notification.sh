#!/bin/bash
# on-notification.sh — Fires when Claude Code receives a notification (Notification hook)
# Logs notification receipt and emits a notification_received event.
# Receives on stdin: { session_id, transcript_path, cwd, hook_event_name, message, title? }
#
# Audit #20 (germline window 2, 2026-07-07): the Notification payload has NO
# `.type` field — the old `jq '.type'` always resolved "unknown", and each
# notification was miscounted as a `session_started` org event (a
# notification is not a new context). Now: classify on `.message` content
# and emit `notification_received` with the classification.

HOOK_INPUT=$(cat)
# Bug fix (R5): hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

NOTIFICATION_MSG=$(echo "$HOOK_INPUT" | jq -r '.message // empty' 2>/dev/null | head -c 300)
NOTIFICATION_TITLE=$(echo "$HOOK_INPUT" | jq -r '.title // empty' 2>/dev/null | head -c 200)

# Classify from message content (best-effort, lowercase match). Buckets map
# to the notification texts the CLI actually emits: permission prompts,
# idle/waiting-for-input nudges, everything else generic.
MSG_LC=$(printf '%s' "$NOTIFICATION_MSG" | tr '[:upper:]' '[:lower:]')
case "$MSG_LC" in
  *permission*|*approval*|*"needs your"*)
    NOTIFICATION_CLASS="permission_request" ;;
  *"waiting for your input"*|*idle*)
    NOTIFICATION_CLASS="idle_prompt" ;;
  "")
    NOTIFICATION_CLASS="empty" ;;
  *)
    NOTIFICATION_CLASS="generic" ;;
esac

# Log notification receipt
echo "on-notification: $OFFICER received notification class=$NOTIFICATION_CLASS at $TIMESTAMP" >&2

# Emit org event for the audit trail (notification_received, NOT
# session_started — see header). Message excerpt is JSON-escaped via jq.
# NB: fallback via plain assignment — an inline ${VAR:-{...}} brace default
# mis-parses in bash and leaks a trailing '}' into the JSON argv.
DETAILS=$(jq -cn \
  --arg class "$NOTIFICATION_CLASS" \
  --arg msg "$NOTIFICATION_MSG" \
  --arg title "$NOTIFICATION_TITLE" \
  '{trigger: "notification", class: $class, message: $msg, title: $title}' 2>/dev/null)
[ -n "$DETAILS" ] || DETAILS='{"trigger": "notification"}'
python3 "$CABINET_ROOT/framework/events/emitter.py" \
  notification_received "$OFFICER" \
  "$DETAILS" \
  2>/dev/null || true

exit 0
