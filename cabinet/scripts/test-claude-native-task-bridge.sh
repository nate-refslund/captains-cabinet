#!/bin/bash
# test-claude-native-task-bridge.sh - hermetic Claude Code task hook bridge eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRIDGE="$REPO_ROOT/cabinet/scripts/claude-task-bridge.py"
ORG="$REPO_ROOT/cabinet/scripts/org-runtime.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/claude-native-task-bridge.sqlite3"
export ORG_RUNTIME_DB="$DB"
export ORG_RUNTIME_PRODUCT="captains-cabinet"
export CABINET_TASK_BRIDGE_MODE="warn"
export CABINET_TASK_BRIDGE_STRICT="1"
export OFFICER_NAME="cto"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "=== Claude native task bridge eval ==="

MISSING_PAYLOAD="$(jq -nc '{
  hook_event_name: "TaskCreated",
  session_id: "sess_missing",
  task_id: "task_missing_1",
  task_subject: "Investigate native bridge",
  task_description: "No Cabinet metadata yet",
  cwd: "/tmp"
}')"
MISSING_OUT="$(printf '%s' "$MISSING_PAYLOAD" | python3 "$BRIDGE")"
printf '%s' "$MISSING_OUT" | jq -e '.systemMessage | contains("mission_id")' >/dev/null \
  && pass "missing metadata produces Claude-native reminder" \
  || fail "missing metadata reminder did not mention mission_id"

MISSING_STATUS="$(python3 "$ORG" claude-tasks show task_missing_1 | jq -r '.task.status')"
[ "$MISSING_STATUS" = "created" ] \
  && pass "task with missing metadata is still recorded in warn mode" \
  || fail "expected missing-metadata task to be recorded, got status '$MISSING_STATUS'"

FULL_DESCRIPTION=$'mission_id: mission_alpha\nnode_id: node_alpha\nowner_role: cto\nacceptance_criteria: event is written\nevidence_required: test output\nverifier_role: coo\nrisk_level: low'
FULL_PAYLOAD="$(jq -nc --arg description "$FULL_DESCRIPTION" '{
  hook_event_name: "TaskCreated",
  session_id: "sess_native",
  transcript_path: "/tmp/transcript.jsonl",
  cwd: "/tmp/captains-cabinet",
  task_id: "task_native_1",
  task_subject: "Wire task bridge",
  task_description: $description,
  teammate_name: "cto",
  team_name: "captains-cabinet"
}')"
FULL_OUT="$(printf '%s' "$FULL_PAYLOAD" | python3 "$BRIDGE")"
[ -z "$FULL_OUT" ] \
  && pass "complete metadata creates no reminder" \
  || fail "expected no reminder for complete metadata, got: $FULL_OUT"

TASK_JSON="$(python3 "$ORG" claude-tasks show task_native_1)"
MISSION_ID="$(printf '%s' "$TASK_JSON" | jq -r '.task.mission_id')"
NODE_ID="$(printf '%s' "$TASK_JSON" | jq -r '.task.node_id')"
OWNER_ROLE="$(printf '%s' "$TASK_JSON" | jq -r '.task.owner_role')"
[ "$MISSION_ID" = "mission_alpha" ] && [ "$NODE_ID" = "node_alpha" ] && [ "$OWNER_ROLE" = "cto" ] \
  && pass "metadata projected onto claude_native_tasks" \
  || fail "metadata projection mismatch: mission=$MISSION_ID node=$NODE_ID role=$OWNER_ROLE"

COMPLETED_PAYLOAD="$(jq -nc '{
  hook_event_name: "TaskCompleted",
  session_id: "sess_native",
  task_id: "task_native_1",
  task_subject: "Wire task bridge"
}')"
printf '%s' "$COMPLETED_PAYLOAD" | python3 "$BRIDGE" >/dev/null
COMPLETED_JSON="$(python3 "$ORG" claude-tasks show task_native_1)"
STATUS="$(printf '%s' "$COMPLETED_JSON" | jq -r '.task.status')"
COMPLETED_EVENT_ID="$(printf '%s' "$COMPLETED_JSON" | jq -r '.task.completed_event_id')"
[ "$STATUS" = "completed" ] && [ "$COMPLETED_EVENT_ID" != "null" ] \
  && pass "TaskCompleted updates projection with event lineage" \
  || fail "completion projection mismatch: status=$STATUS event=$COMPLETED_EVENT_ID"

EVENT_COUNT="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM org_events WHERE aggregate_type='claude_native_task'").fetchone()[0])
PY
)"
[ "$EVENT_COUNT" = "3" ] \
  && pass "Claude native task lifecycle emitted org_events" \
  || fail "expected 3 Claude task events, got $EVENT_COUNT"

echo "=== Claude native task bridge eval PASS ==="
