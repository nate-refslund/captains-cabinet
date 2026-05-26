#!/bin/bash
# on-subagent-start.sh — Fires when a subagent is spawned (CC v2.1.150 SubagentStart hook)
# Replaces the legacy PostToolUse:Agent|Task matcher for the start side of subagent lifecycle.
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, agent_type, agent_id }
#
# Emits work_item_started if the spawn payload references a known task ref (FW-*, PROD-*, TASK-*).
# Otherwise logs an audit line — never blocks the spawn.

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

AGENT_TYPE=$(echo "$HOOK_INPUT" | jq -r '.agent_type // "unknown"' 2>/dev/null)
AGENT_ID=$(echo "$HOOK_INPUT" | jq -r '.agent_id // "unknown"' 2>/dev/null)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Audit log to stderr (visible in transcript)
echo "on-subagent-start: $OFFICER spawned subagent type=$AGENT_TYPE id=$AGENT_ID at $TIMESTAMP" >&2

# Extract task ref from agent_type or any embedded payload; the spawn prompt
# is not present in SubagentStart stdin (per docs), so only emit work_item_started
# when the agent_type itself encodes a task tag (e.g. "fw-114-impl").
TASK_REF=$(echo "$AGENT_TYPE" | grep -oE '(FW|PROD|TASK)-[0-9]+' | head -1)
if [ -n "$TASK_REF" ]; then
  python3 "$CABINET_ROOT/framework/events/emitter.py" \
    work_item_started "$OFFICER" \
    "{\"task_ref\": \"$TASK_REF\", \"agent_type\": \"$AGENT_TYPE\", \"agent_id\": \"$AGENT_ID\", \"session_id\": \"$SESSION_ID\"}" \
    2>/dev/null || true
fi

# G4 standardization: emit silent hookSpecificOutput so transcripts get a
# structured marker. SubagentStart supports additionalContext per docs.
jq -n --arg agent "$AGENT_TYPE" --arg id "$AGENT_ID" '{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStart",
    "additionalContext": ("Subagent started: type=" + $agent + " id=" + $id)
  }
}' 2>/dev/null || true

exit 0
