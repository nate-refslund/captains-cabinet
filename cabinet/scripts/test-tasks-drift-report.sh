#!/bin/bash
# test-tasks-drift-report.sh - read-only /tasks drift projection eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORG="$REPO_ROOT/cabinet/scripts/org-runtime.py"
BRIDGE="$REPO_ROOT/cabinet/scripts/claude-task-bridge.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/tasks-drift.sqlite3"
PLAN="$TMP_DIR/plan.json"
export ORG_RUNTIME_DB="$DB"
export ORG_RUNTIME_PRODUCT="captains-cabinet"
export OFFICER_NAME="cto"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "=== Tasks drift report eval ==="

for role in cos cto coo; do
  python3 "$ORG" roles define --role "$role" --name "$role" --charter "Fixture $role" --actor cos >/dev/null
done
OUTCOME_ID="$(python3 "$ORG" outcomes propose --title "Drift fixture" --metric-name verified_outcome_value --target-value 2 --actor cos | jq -r '.outcome_id')"
python3 "$ORG" outcomes ratify "$OUTCOME_ID" --ratified-by captain >/dev/null
cat > "$PLAN" <<'JSON'
{
  "mission_id": "mission_drift_fixture",
  "title": "Drift fixture",
  "nodes": [
    {
      "node_id": "node_has_claude",
      "title": "Node with Claude task",
      "owner_role": "cto",
      "acceptance_criteria": "Claude task exists",
      "evidence_required": "drift output",
      "verifier_role": "coo",
      "risk_level": "low"
    },
    {
      "node_id": "node_missing_claude",
      "title": "Node missing Claude task",
      "owner_role": "cto",
      "acceptance_criteria": "Reported as missing",
      "evidence_required": "drift output",
      "verifier_role": "coo",
      "risk_level": "low"
    }
  ]
}
JSON
python3 "$ORG" missions compile-plan "$OUTCOME_ID" --plan-file "$PLAN" --actor cos >/dev/null

python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("""
CREATE TABLE officer_tasks (
  id INTEGER PRIMARY KEY,
  title TEXT,
  status TEXT,
  officer_slug TEXT,
  context_slug TEXT,
  linked_kind TEXT,
  linked_id TEXT
)
""")
conn.execute("INSERT INTO officer_tasks VALUES (1,'Legacy linked','queue','cto','captains-cabinet','work_graph_node','node_has_claude')")
conn.execute("INSERT INTO officer_tasks VALUES (2,'Legacy orphan','queue','cto','captains-cabinet',NULL,NULL)")
conn.commit()
PY

DESCRIPTION=$'mission_id: mission_drift_fixture\nnode_id: node_has_claude\nowner_role: cto\nacceptance_criteria: Claude task exists\nevidence_required: drift output\nverifier_role: coo\nrisk_level: low'
jq -nc --arg description "$DESCRIPTION" '{
  hook_event_name: "TaskCreated",
  task_id: "task_has_claude",
  task_subject: "Node with Claude task",
  task_description: $description
}' | python3 "$BRIDGE" >/dev/null

REPORT="$(python3 "$ORG" tasks drift-report)"
printf '%s' "$REPORT" | jq -e '.work_nodes_without_claude_task == ["node_missing_claude"]' >/dev/null \
  && pass "drift report finds work nodes without Claude task" \
  || fail "work node drift mismatch: $REPORT"
printf '%s' "$REPORT" | jq -e '.legacy_tasks_without_work_node_link | length == 1' >/dev/null \
  && pass "drift report finds legacy task without work node link" \
  || fail "legacy drift mismatch: $REPORT"

echo "=== Tasks drift report eval PASS ==="
