#!/bin/bash
# test-org-runtime.sh — hermetic org runtime vertical-slice eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORG="$REPO_ROOT/cabinet/scripts/org-runtime.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/org-runtime.sqlite3"
DIGEST_DIR="$TMP_DIR/digests"
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

echo "=== Org runtime vertical-slice eval ==="

# active-project.txt is deployment-local and absent on clean checkouts AND on
# the live hq deployment (verified 2026-07-02) — the runtime itself falls
# through to fail-safe lane resolution when it is missing. Mirror that:
# absent file = pass-with-note, never a hard fail. (This whole eval tests the
# org-runtime.py vertical slice, which is on the ratified kill list — the step
# retires with it; see docs/plans/ kill tracker.)
if [ -f "$REPO_ROOT/instance/config/active-project.txt" ]; then
  ACTIVE="$(tr -d '[:space:]' < "$REPO_ROOT/instance/config/active-project.txt")"
  [ "$ACTIVE" = "captains-cabinet" ] \
    && pass "active project is captains-cabinet" \
    || fail "active project expected captains-cabinet, got '$ACTIVE'"
else
  pass "active-project.txt absent (deployment-local) -> runtime fail-safe path"
fi

# Lane context files (instance/config/contexts/<lane>.yml) are instance-
# split (egg plan R124): they stay on a live deployment but leave the egg at
# packaging — only the generic contexts/_default.yml ships. Mirror the
# active-project.txt pattern above: no lane contexts = clean/egg checkout ->
# pass-with-note, never a hard fail. When present, the check is lane-
# agnostic (INSTANCE-SENSED-CLEANUP: foundation never names instance lanes):
# every lane declaration must carry an EXPLICIT `active: true|false` state —
# the fail-safe activation invariant the old per-lane checks asserted. An
# optional trailing `# comment` is tolerated; a glued `false# x` stays
# rejected (YAML reads that scalar as a string, not a boolean).
LANE_CONTEXTS=0
for LANE_FILE in "$REPO_ROOT"/instance/config/contexts/*.yml; do
  [ -e "$LANE_FILE" ] || continue            # unmatched glob (no contexts at all)
  case "$(basename "$LANE_FILE")" in
    _default.yml) continue ;;                # portfolio defaults — not a lane declaration
  esac
  LANE_CONTEXTS=$((LANE_CONTEXTS + 1))
  grep -Eq '^active:[[:space:]]*(true|false)([[:space:]]+#.*)?[[:space:]]*$' "$LANE_FILE" \
    && pass "lane context $(basename "$LANE_FILE") declares an explicit active state" \
    || fail "lane context $(basename "$LANE_FILE") must declare 'active: true|false' explicitly"
done
if [ "$LANE_CONTEXTS" -eq 0 ]; then
  pass "no lane contexts present (instance-split, leaves at packaging) -> runtime fail-safe path"
fi

python3 "$ORG" roles define \
  --role cos \
  --name "Chief of Staff" \
  --charter "Translate Captain-ratified outcomes into verified organizational execution" \
  --current-focus "Outcome-to-OVI vertical slice" \
  --authority-level mission_orchestrator \
  --capability mission_compilation \
  --capability ovi_publication \
  --officer-session-slug cos \
  --actor cos >/dev/null
pass "durable CoS role defined"

OUTCOME_JSON="$(python3 "$ORG" outcomes propose \
  --title "Improve Cabinet autonomy per Captain attention" \
  --metric-name verified_outcome_value \
  --target-value 12 \
  --unit points \
  --actor cos)"
OUTCOME_ID="$(printf '%s' "$OUTCOME_JSON" | json_value '.outcome_id')"
[ -n "$OUTCOME_ID" ] && pass "outcome proposed" || fail "outcome proposal produced no id"

python3 "$ORG" outcomes ratify "$OUTCOME_ID" --ratified-by captain --note "Branch fixture ratification" >/dev/null
pass "outcome ratified"

MISSION_JSON="$(python3 "$ORG" missions compile "$OUTCOME_ID" \
  --title "Outcome-to-OVI vertical slice" \
  --node-title "Publish verified OVI and digest" \
  --owner-role cos \
  --actor cos)"
MISSION_ID="$(printf '%s' "$MISSION_JSON" | json_value '.mission_id')"
NODE_ID="$(printf '%s' "$MISSION_JSON" | json_value '.nodes[0].node_id')"
[ -n "$MISSION_ID" ] && [ -n "$NODE_ID" ] && pass "mission/work graph compiled" || fail "mission compile missing ids"

python3 "$ORG" roles assign-hat \
  --mission-id "$MISSION_ID" \
  --node-id "$NODE_ID" \
  --role cos \
  --hat-name "Outcome Integrator" \
  --purpose "Own the first outcome-to-OVI runtime slice without restructuring the officer roster" \
  --actor cos >/dev/null
pass "role hat assigned to mission"

python3 "$ORG" missions complete "$NODE_ID" \
  --verified-value 12 \
  --verification-summary "Fixture verified the runtime event path end to end" \
  --actor cos >/dev/null
pass "work-graph node completed with verification"

python3 "$ORG" ovi publish \
  --week-start 2026-05-11 \
  --verified-value 6 \
  --captain-attention-minutes 30 \
  --captain-decisions 2 \
  --spend-usd 25 \
  --policy-violations 1 >/dev/null

OVI_JSON="$(python3 "$ORG" ovi publish \
  --week-start 2026-05-18 \
  --verified-value 12 \
  --captain-attention-minutes 30 \
  --captain-decisions 2 \
  --spend-usd 25 \
  --policy-violations 1)"
OVI="$(printf '%s' "$OVI_JSON" | json_value '.ovi')"
TREND="$(printf '%s' "$OVI_JSON" | json_value '.trend_vs_prior')"
[ "$OVI" = "2" ] || [ "$OVI" = "2.0" ] \
  && pass "OVI uses value-per-burden ratio" \
  || fail "expected OVI 2.0, got $OVI"
awk -v t="$TREND" 'BEGIN { exit !(t > 0) }' \
  && pass "OVI trend compares against prior published week" \
  || fail "expected positive OVI trend, got $TREND"

DIGEST_JSON="$(python3 "$ORG" digest publish-sanitized \
  --week-start 2026-05-18 \
  --title "Runtime learning digest" \
  --content "Sensed is legacy. Contact captain@example.com. Secret sk-testsecret123. See https://example.com/private." \
  --output-dir "$DIGEST_DIR")"
DIGEST_PATH="$(printf '%s' "$DIGEST_JSON" | json_value '.path')"
[ -f "$DIGEST_PATH" ] && pass "sanitized digest file published" || fail "digest file missing"
if grep -qiE 'Sensed|captain@example.com|sk-testsecret123|https://example.com' "$DIGEST_PATH"; then
  fail "digest leaked unsanitized sensitive or legacy product content"
else
  pass "digest redaction removed legacy product/private details"
fi

EVENT_COUNT="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM org_events").fetchone()[0])
PY
)"
[ "$EVENT_COUNT" -ge 9 ] \
  && pass "org_events captured every vertical-slice transition ($EVENT_COUNT events)" \
  || fail "expected at least 9 org_events, got $EVENT_COUNT"

python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
for sql in ("UPDATE org_events SET actor='mutated'", "DELETE FROM org_events"):
    try:
        conn.execute(sql)
        conn.commit()
    except sqlite3.DatabaseError:
        continue
    raise SystemExit(f"append-only guard failed for: {sql}")
PY
pass "org_events rejects update/delete mutation"

NULL_REFS="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
checks = [
    ("captain_outcomes", "proposed_event_id"),
    ("captain_outcomes", "ratified_event_id"),
    ("missions", "compiled_event_id"),
    ("work_graph_nodes", "completion_event_id"),
    ("mission_role_assignments", "assignment_event_id"),
    ("ovi_weeks", "published_event_id"),
    ("learning_digests", "published_event_id"),
]
total = 0
for table, col in checks:
    total += conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL").fetchone()[0]
print(total)
PY
)"
[ "$NULL_REFS" = "0" ] \
  && pass "projection rows retain source event lineage" \
  || fail "projection rows missing event lineage: $NULL_REFS"

echo "=== Org runtime eval PASS ==="
