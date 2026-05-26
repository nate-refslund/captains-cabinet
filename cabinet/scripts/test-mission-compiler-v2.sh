#!/bin/bash
# test-mission-compiler-v2.sh - hermetic Mission Compiler v2 eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORG="$REPO_ROOT/cabinet/scripts/org-runtime.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/mission-compiler-v2.sqlite3"
PLAN="$TMP_DIR/plan.json"
export ORG_RUNTIME_DB="$DB"
export ORG_RUNTIME_PRODUCT="captains-cabinet"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "=== Mission Compiler v2 eval ==="

for role in cos cto coo; do
  python3 "$ORG" roles define \
    --role "$role" \
    --name "$role" \
    --charter "Fixture role $role" \
    --authority-level mission_executor \
    --actor cos >/dev/null
done
pass "fixture roles defined"

OUTCOME_JSON="$(python3 "$ORG" outcomes propose \
  --title "Activate an existing project" \
  --metric-name verified_outcome_value \
  --target-value 3 \
  --actor cos)"
OUTCOME_ID="$(printf '%s' "$OUTCOME_JSON" | jq -r '.outcome_id')"
python3 "$ORG" outcomes ratify "$OUTCOME_ID" --ratified-by captain --note "Fixture approval" >/dev/null
pass "outcome ratified"

cat > "$PLAN" <<'JSON'
{
  "mission_id": "mission_activation_fixture",
  "title": "Activate project fixture",
  "nodes": [
    {
      "node_id": "node_activation_preflight",
      "title": "Run activation preflight",
      "owner_role": "cos",
      "acceptance_criteria": "Project config is created and active state is explicit",
      "evidence_required": "activate-project output and org event",
      "verifier_role": "coo",
      "risk_level": "low",
      "rollback_note": "Restore previous active-project.txt",
      "budget_note": "No external spend",
      "captain_attention_estimate": 1
    },
    {
      "node_id": "node_activation_verify",
      "title": "Verify project runtime",
      "owner_role": "cto",
      "acceptance_criteria": "Project repo is reachable from the configured mount path",
      "evidence_required": "repo status and config assembly output",
      "verifier_role": "coo",
      "risk_level": "medium",
      "rollback_note": "Switch back to previous project",
      "budget_note": "No external spend",
      "captain_attention_estimate": 2,
      "depends_on": ["node_activation_preflight"]
    }
  ]
}
JSON

MISSION_JSON="$(python3 "$ORG" missions compile-plan "$OUTCOME_ID" --plan-file "$PLAN" --actor cos)"
MISSION_ID="$(printf '%s' "$MISSION_JSON" | jq -r '.mission_id')"
[ "$MISSION_ID" = "mission_activation_fixture" ] \
  && pass "multi-node mission plan compiled" \
  || fail "unexpected mission id: $MISSION_ID"

COUNTS="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
nodes = conn.execute("SELECT COUNT(*) FROM work_graph_nodes").fetchone()[0]
edges = conn.execute("SELECT COUNT(*) FROM work_graph_edges").fetchone()[0]
criteria = conn.execute("SELECT acceptance_criteria FROM work_graph_nodes WHERE node_id='node_activation_verify'").fetchone()[0]
print(f"{nodes}|{edges}|{criteria}")
PY
)"
[ "$COUNTS" = "2|1|Project repo is reachable from the configured mount path" ] \
  && pass "nodes, edge, and acceptance metadata persisted" \
  || fail "mission graph persistence mismatch: $COUNTS"

PACKETS="$(python3 "$ORG" missions native-task-packets "$MISSION_ID")"
printf '%s' "$PACKETS" | jq -e '.task_packets | length == 2' >/dev/null \
  && pass "native task packets emitted per node" \
  || fail "expected two native task packets"
printf '%s' "$PACKETS" | jq -e '.task_packets[].task_description | contains("mission_id: mission_activation_fixture") and contains("evidence_required:") and contains("verifier_role: coo")' >/dev/null \
  && pass "native task packets include required Cabinet metadata" \
  || fail "native task packet metadata missing"

echo "=== Mission Compiler v2 eval PASS ==="
