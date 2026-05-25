#!/bin/bash
# test-org-roles.sh — hermetic durable adaptive role eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORG="$REPO_ROOT/cabinet/scripts/org-runtime.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/org-runtime.sqlite3"
export ORG_RUNTIME_DB="$DB"
export ORG_RUNTIME_PRODUCT="captains-cabinet"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

json_value() {
  jq -r "$1"
}

expect_fail() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    fail "$label"
  fi
  pass "$label"
}

echo "=== Durable adaptive role eval ==="

ROLE_JSON="$(python3 "$ORG" roles define \
  --role cos \
  --name "Chief of Staff" \
  --charter "Own outcome translation, mission orchestration, and Cabinet learning loops" \
  --current-focus "Durable adaptive role runtime" \
  --authority-level mission_orchestrator \
  --capability mission_compilation \
  --capability ovi_publication \
  --officer-session-slug cos \
  --actor cos)"
[ "$(printf '%s' "$ROLE_JSON" | json_value '.role_slug')" = "cos" ] \
  && pass "active CoS role entity defined" \
  || fail "CoS role definition missing"

python3 "$ORG" roles bind-memory \
  --role cos \
  --memory-path instance/memory/tier2/cos \
  --memory-kind tier2 \
  --actor cos >/dev/null
pass "role memory bound without touching officer markdown"

python3 "$ORG" roles define \
  --role observer \
  --name "Observer" \
  --charter "Inactive fixture role" \
  --state inactive \
  --actor cos >/dev/null
pass "inactive role fixture defined"

OUTCOME_JSON="$(python3 "$ORG" outcomes propose \
  --title "Make role identity durable across missions" \
  --metric-name verified_role_runtime_value \
  --target-value 10 \
  --actor cos)"
OUTCOME_ID="$(printf '%s' "$OUTCOME_JSON" | json_value '.outcome_id')"
python3 "$ORG" outcomes ratify "$OUTCOME_ID" --ratified-by captain --note "Role runtime fixture" >/dev/null
pass "role-runtime outcome ratified"

expect_fail "undefined owner role cannot compile a mission" \
  python3 "$ORG" missions compile "$OUTCOME_ID" \
    --title "Should fail" \
    --node-title "No missing role owners" \
    --owner-role missing-role \
    --actor cos

MISSION_JSON="$(python3 "$ORG" missions compile "$OUTCOME_ID" \
  --title "Durable adaptive role vertical slice" \
  --node-title "Record role evidence and evolution" \
  --owner-role cos \
  --actor cos)"
MISSION_ID="$(printf '%s' "$MISSION_JSON" | json_value '.mission_id')"
NODE_ID="$(printf '%s' "$MISSION_JSON" | json_value '.nodes[0].node_id')"
[ -n "$MISSION_ID" ] && [ -n "$NODE_ID" ] \
  && pass "active role owns mission/work graph" \
  || fail "mission compile missing ids"

MISSION_2_JSON="$(python3 "$ORG" missions compile "$OUTCOME_ID" \
  --title "Node mismatch guard fixture" \
  --node-title "Do not assign across missions" \
  --owner-role cos \
  --actor cos)"
NODE_2_ID="$(printf '%s' "$MISSION_2_JSON" | json_value '.nodes[0].node_id')"

expect_fail "mission hat assignment rejects nodes from another mission" \
  python3 "$ORG" roles assign-hat \
    --mission-id "$MISSION_ID" \
    --node-id "$NODE_2_ID" \
    --role cos \
    --hat-name "Cross Mission Bug" \
    --purpose "Should fail because the node belongs to another mission" \
    --actor cos

expect_fail "inactive role cannot receive a mission hat" \
  python3 "$ORG" roles assign-hat \
    --mission-id "$MISSION_ID" \
    --node-id "$NODE_ID" \
    --role observer \
    --hat-name "Dormant Auditor" \
    --purpose "Should fail because role is inactive" \
    --actor cos

ASSIGN_JSON="$(python3 "$ORG" roles assign-hat \
  --mission-id "$MISSION_ID" \
  --node-id "$NODE_ID" \
  --role cos \
  --hat-name "Adaptive Role Steward" \
  --purpose "Own role lineage and eval-driven evolution for this mission" \
  --actor cos)"
HAT_ID="$(printf '%s' "$ASSIGN_JSON" | json_value '.hat_id')"
[ -n "$HAT_ID" ] && pass "temporary role hat assigned" || fail "hat assignment missing id"

python3 "$ORG" missions complete "$NODE_ID" \
  --verified-value 10 \
  --verification-summary "Fixture verified role identity, memory binding, eval evidence, and evolution eventing" \
  --actor cos >/dev/null
pass "role-owned work graph node verified"

python3 "$ORG" roles record-eval \
  --role cos \
  --eval-name "hat-fit-pass-1" \
  --score 0.86 \
  --passed \
  --hat-id "$HAT_ID" \
  --mission-id "$MISSION_ID" \
  --evidence "Hat matched mission authority and preserved role memory" \
  --actor evaluator >/dev/null

python3 "$ORG" roles record-eval \
  --role cos \
  --eval-name "hat-fit-pass-2" \
  --score 0.91 \
  --passed \
  --hat-id "$HAT_ID" \
  --mission-id "$MISSION_ID" \
  --evidence "Second passing eval confirms repeatable value" \
  --actor evaluator >/dev/null
pass "role eval evidence recorded"

RECOMMEND_JSON="$(python3 "$ORG" roles recommend --role cos --actor evaluator)"
RECOMMENDATION_TYPE="$(printf '%s' "$RECOMMEND_JSON" | json_value '.recommendation_type')"
[ "$RECOMMENDATION_TYPE" = "promote_hat_to_capability" ] \
  && pass "deterministic recommendation promotes proven hat" \
  || fail "expected promote_hat_to_capability, got $RECOMMENDATION_TYPE"

expect_fail "role evolution requires Captain ratification" \
  python3 "$ORG" roles evolve \
    --role cos \
    --current-focus "Unratified change should fail" \
    --actor cos

python3 "$ORG" roles evolve \
  --role cos \
  --current-focus "Codify durable adaptive role runtime" \
  --add-capability adaptive_role_management \
  --ratified-by captain \
  --approval-note "Fixture ratifies role focus and capability update" \
  --actor cos >/dev/null
pass "Captain-ratified role evolution applied"

SHOW_JSON="$(python3 "$ORG" roles show --role cos)"
VERSION="$(printf '%s' "$SHOW_JSON" | json_value '.role.version')"
OFFICER_SESSION="$(printf '%s' "$SHOW_JSON" | json_value '.role.officer_session_slug')"
MEMORY_COUNT="$(printf '%s' "$SHOW_JSON" | json_value '.memory_bindings | length')"
EVAL_COUNT="$(printf '%s' "$SHOW_JSON" | json_value '.eval_results | length')"
HAS_CAPABILITY="$(printf '%s' "$SHOW_JSON" | jq 'any(.role.capabilities[]; . == "adaptive_role_management")')"
[ "$VERSION" = "2" ] \
  && [ "$OFFICER_SESSION" = "cos" ] \
  && [ "$MEMORY_COUNT" = "1" ] \
  && [ "$EVAL_COUNT" = "2" ] \
  && [ "$HAS_CAPABILITY" = "true" ] \
  && pass "role projection preserves officer mapping, memory, evals, and evolved capability" \
  || fail "role projection did not preserve expected durable state"

for idx in 1 2 3; do
  python3 "$ORG" roles record-eval \
    --role cos \
    --eval-name "latest-failure-$idx" \
    --score 0.2 \
    --failed \
    --evidence "Regression fixture failure $idx" \
    --actor evaluator >/dev/null
done
RETIRE_JSON="$(python3 "$ORG" roles recommend --role cos --actor evaluator)"
RETIRE_TYPE="$(printf '%s' "$RETIRE_JSON" | json_value '.recommendation_type')"
[ "$RETIRE_TYPE" = "retire_role_review" ] \
  && pass "retire-review recommendation wins after 3 latest failures with no active assignments" \
  || fail "expected retire_role_review, got $RETIRE_TYPE"

python3 - "$DB" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
missing_product = conn.execute(
    "SELECT COUNT(*) FROM role_lineage_events WHERE product_slug IS NULL OR product_slug = ''"
).fetchone()[0]
if missing_product:
    raise SystemExit(f"role lineage rows missing product_slug: {missing_product}")

checks = [
    "UPDATE role_lineage_events SET note='mutated'",
    "DELETE FROM role_lineage_events",
    "UPDATE role_memory_bindings SET memory_kind='mutated'",
    "DELETE FROM role_memory_bindings",
    "UPDATE role_eval_results SET evidence='mutated'",
    "DELETE FROM role_eval_results",
    "UPDATE role_evolution_recommendations SET basis='mutated'",
    "DELETE FROM role_evolution_recommendations",
]
for sql in checks:
    try:
        conn.execute(sql)
        conn.commit()
    except sqlite3.DatabaseError:
        conn.rollback()
        continue
    raise SystemExit(f"append-history guard failed for: {sql}")
PY
pass "role memory/eval/lineage/recommendation history rejects mutation"

EVENT_COUNT="$(python3 - "$DB" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM org_events").fetchone()[0])
PY
)"
[ "$EVENT_COUNT" -ge 18 ] \
  && pass "org_events captured durable role lifecycle ($EVENT_COUNT events)" \
  || fail "expected at least 18 org events, got $EVENT_COUNT"

echo "=== Durable adaptive role eval PASS ==="
