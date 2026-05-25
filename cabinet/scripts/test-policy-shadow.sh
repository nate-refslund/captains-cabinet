#!/bin/bash
# test-policy-shadow.sh — typed policy shadow/parity fixture eval.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
SHADOW="$REPO_ROOT/cabinet/scripts/policy-shadow.py"
TMP_DIR="$(mktemp -d)"
DB="$TMP_DIR/policy-shadow.sqlite3"
export ORG_RUNTIME_DB="$DB"
export ORG_RUNTIME_PRODUCT="captains-cabinet"
export ORG_POLICY_SHADOW_RECORD=1
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

hook_decision() {
  local officer="$1"
  local payload="$2"
  local rc
  set +e
  printf '%s' "$payload" | OFFICER_NAME="$officer" bash "$HOOK" >/dev/null 2>"$TMP_DIR/hook.err"
  rc=$?
  set -e
  if [ "$rc" -eq 2 ]; then
    echo "block"
  else
    echo "allow"
  fi
}

shadow_decision() {
  local officer="$1"
  local payload="$2"
  printf '%s' "$payload" | OFFICER_NAME="$officer" python3 "$SHADOW" | jq -r '.decision'
}

assert_parity() {
  local name="$1"
  local officer="$2"
  local payload="$3"
  local expected="$4"
  local live shadow
  live="$(hook_decision "$officer" "$payload")"
  shadow="$(shadow_decision "$officer" "$payload")"
  [ "$live" = "$expected" ] || fail "$name live hook expected $expected got $live"
  [ "$shadow" = "$expected" ] || fail "$name shadow expected $expected got $shadow"
  pass "$name parity: $expected"
}

echo "=== Typed policy shadow parity eval ==="

assert_parity \
  "allow benign bash" \
  "cos" \
  '{"tool_name":"Bash","tool_input":{"command":"echo hello"}}' \
  "allow"

assert_parity \
  "block production deploy" \
  "cto" \
  '{"tool_name":"Bash","tool_input":{"command":"vercel deploy --prod"}}' \
  "block"

assert_parity \
  "block constitution edit" \
  "cos" \
  '{"tool_name":"Edit","tool_input":{"file_path":"/opt/founders-cabinet/constitution/CONSTITUTION.md"}}' \
  "block"

assert_parity \
  "block non-CTO product write" \
  "cpo" \
  '{"tool_name":"Edit","tool_input":{"file_path":"/workspace/captains-cabinet/src/runtime.ts"}}' \
  "block"

assert_parity \
  "allow non-product edit" \
  "cpo" \
  '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/cabinet-note.md"}}' \
  "allow"

EVENT_COUNT="$(python3 - "$DB" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute("SELECT COUNT(*) FROM org_events WHERE event_type='policy.shadow_decision'").fetchone()[0])
PY
)"
[ "$EVENT_COUNT" -ge 5 ] \
  && pass "policy shadow decisions recorded to org_events" \
  || fail "expected policy shadow org_events, got $EVENT_COUNT"

echo "=== Typed policy shadow eval PASS ==="
