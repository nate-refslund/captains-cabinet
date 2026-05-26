#!/bin/bash
# on-subagent-stop.sh — Fires when a subagent finishes (CC v2.1.150 SubagentStop hook)
# Replaces the legacy PostToolUse:Agent|Task matcher for the stop side of subagent lifecycle.
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, agent_type, agent_id }
#
# Emits work_item_completed event. If agent_type encodes a task ref (FW-*, PROD-*,
# TASK-*), it's attached to the event payload for mission/work-graph reconciliation.

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

AGENT_TYPE=$(echo "$HOOK_INPUT" | jq -r '.agent_type // "unknown"' 2>/dev/null)
AGENT_ID=$(echo "$HOOK_INPUT" | jq -r '.agent_id // "unknown"' 2>/dev/null)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Audit log to stderr
echo "on-subagent-stop: $OFFICER subagent type=$AGENT_TYPE id=$AGENT_ID completed at $TIMESTAMP" >&2

# Extract task ref from agent_type
TASK_REF=$(echo "$AGENT_TYPE" | grep -oE '(FW|PROD|TASK)-[0-9]+' | head -1)

# Always emit work_item_completed for the subagent — the payload distinguishes
# task-tagged completions (work-graph nodes) from generic helper-agent completions
# (debugging, code review, etc.). Mission supervisor filters on task_ref.
if [ -n "$TASK_REF" ]; then
  PAYLOAD="{\"task_ref\": \"$TASK_REF\", \"agent_type\": \"$AGENT_TYPE\", \"agent_id\": \"$AGENT_ID\", \"session_id\": \"$SESSION_ID\", \"completed_by\": \"subagent\"}"
else
  PAYLOAD="{\"agent_type\": \"$AGENT_TYPE\", \"agent_id\": \"$AGENT_ID\", \"session_id\": \"$SESSION_ID\", \"completed_by\": \"subagent\"}"
fi

python3 "$CABINET_ROOT/framework/events/emitter.py" \
  work_item_completed "$OFFICER" \
  "$PAYLOAD" \
  2>/dev/null || true

exit 0
