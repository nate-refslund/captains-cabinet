#!/bin/bash
# on-subagent-stop.sh — Fires when a subagent finishes (CC v2.1.150 SubagentStop hook)
# Replaces the legacy PostToolUse:Agent|Task matcher for the stop side of subagent lifecycle.
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, agent_type, agent_id }
#
# Event routing (g-hooks 2026-07-04): emits work_item_completed ONLY when
# agent_type encodes a genuine task ref (FW-*/PROD-*/TASK-*, a mission id, or a
# work-graph node id — attached as task_ref for mission/work-graph
# reconciliation); every other stop emits subagent_completed (lifecycle
# telemetry, the type lane-ledger registers). WHY: the old always-emit
# behavior wrote a work_item_completed row for EVERY helper subagent (code
# review, exploration, debugging) — 6,574 junk rows in the mission ledger,
# skewing every consumer that replays that type: OVI task_throughput +
# verification_pass_rate (framework/ovi/compute.py:58,66) and the mission
# compiler's DONE overlay (framework/missions/compiler.py:242).

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

AGENT_TYPE=$(echo "$HOOK_INPUT" | jq -r '.agent_type // "unknown"' 2>/dev/null)
AGENT_ID=$(echo "$HOOK_INPUT" | jq -r '.agent_id // "unknown"' 2>/dev/null)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Audit log to stderr
echo "on-subagent-stop: $OFFICER subagent type=$AGENT_TYPE id=$AGENT_ID completed at $TIMESTAMP" >&2

# Extract a genuine task ref from agent_type. Three shapes count — anything
# else is a generic helper agent, not work-graph work:
#   (FW|PROD|TASK)-N            — backlog/framework item refs (pre-existing
#                                 convention; TASK-N kept so no spawner regresses)
#   mission-<outcome>-<8 hex>   — mission ids (framework/missions/compiler.py:425)
#   <outcome>-task-NNN          — work-graph node ids (framework/missions/compiler.py:66)
# grep -oE output is charset-limited to [A-Za-z0-9_-] tokens, so TASK_REF is
# safe to embed in the hand-built JSON payload below. Known limit, accepted:
# POSIX leftmost-longest matching means a ref embedded mid-token with `-`
# joins (e.g. "fix-<node-id>") extracts with its prefix — spawners should set
# agent_type to the ref verbatim; exact-id reconciliation stays the job of
# cabinet/scripts/work-graph-complete.sh, the canonical completion path.
TASK_REF=$(echo "$AGENT_TYPE" | grep -oE '(FW|PROD|TASK)-[0-9]+|mission-[A-Za-z0-9_-]+-[0-9a-f]{8}|[A-Za-z0-9][A-Za-z0-9_-]*-task-[0-9]{3}' | head -1)

# Build the payload with jq --arg (N5, checkpoint review lane-germline-0705-cp1):
# AGENT_TYPE / AGENT_ID / SESSION_ID come from `jq -r` on arbitrary hook input
# and can carry quotes, backslashes, or newlines — hand-built JSON string
# interpolation would break or let a crafted agent_type inject payload keys.
# jq --arg escapes every value correctly. (TASK_REF was already charset-safe via
# the grep above; the others were not — this closes that gap uniformly.)
if [ -n "$TASK_REF" ]; then
  # Genuine task ref → this stop IS a work-graph completion. Keep the type
  # the mission supervisor/compiler reconcile on, ref attached.
  EVENT_TYPE="work_item_completed"
  PAYLOAD=$(jq -nc \
    --arg tr "$TASK_REF" --arg at "$AGENT_TYPE" --arg ai "$AGENT_ID" --arg si "$SESSION_ID" \
    '{task_ref:$tr, agent_type:$at, agent_id:$ai, session_id:$si, completed_by:"subagent"}' \
    2>/dev/null)
else
  # Generic helper agent → lifecycle telemetry only, never a work-item row.
  # subagent_completed is registered in VALID_EVENT_TYPES
  # (framework/events/emitter.py) by the lane-ledger change in this same
  # batch; if that registration were ever absent the emitter raises and the
  # `|| true` below swallows it — fail-quiet, no ledger pollution either way.
  EVENT_TYPE="subagent_completed"
  PAYLOAD=$(jq -nc \
    --arg at "$AGENT_TYPE" --arg ai "$AGENT_ID" --arg si "$SESSION_ID" \
    '{agent_type:$at, agent_id:$ai, session_id:$si, completed_by:"subagent"}' \
    2>/dev/null)
fi
# jq failure (malformed env, jq absent) → empty PAYLOAD → the emitter arg is
# empty → it errors → the `|| true` below swallows it. Fail-quiet, never a
# malformed ledger row.
[ -z "$PAYLOAD" ] && exit 0

python3 "$CABINET_ROOT/framework/events/emitter.py" \
  "$EVENT_TYPE" "$OFFICER" \
  "$PAYLOAD" \
  2>/dev/null || true

exit 0
