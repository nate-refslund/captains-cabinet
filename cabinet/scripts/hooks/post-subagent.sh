#!/bin/bash
# post-subagent.sh — Fires after Agent (subagent) tool completes (PostToolUse matcher: Agent)
# Logs subagent completion and emits work_item_completed if it was a mission task.
# Receives on stdin: { tool_name, tool_input, tool_response }

HOOK_INPUT=$(cat)
# Bug fix (R5): hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

TOOL_INPUT=$(echo "$HOOK_INPUT" | jq -c '.tool_input // {}' 2>/dev/null)
AGENT_PROMPT=$(echo "$TOOL_INPUT" | jq -r '.prompt // .task // "unknown"' 2>/dev/null)
AGENT_MODEL=$(echo "$TOOL_INPUT" | jq -r '.model // "default"' 2>/dev/null)

# Log subagent completion for visibility
echo "post-subagent: $OFFICER subagent completed (model=$AGENT_MODEL) at $TIMESTAMP" >&2

# If the subagent prompt references a mission task, emit work_item_completed
TASK_REF=$(echo "$AGENT_PROMPT" | grep -oP '(TASK|FW|PROD)-\d+' | head -1)
if [ -n "$TASK_REF" ]; then
  python3 "$CABINET_ROOT/framework/events/emitter.py" \
    work_item_completed "$OFFICER" \
    "{\"task_ref\": \"$TASK_REF\", \"completed_by\": \"subagent\", \"model\": \"$AGENT_MODEL\"}" \
    2>/dev/null || true
fi

exit 0
