#!/bin/bash
# Evidence Recorder v1 officer-access boundary: raw evidence is neither a
# direct read nor write surface; the bounded projection command remains open.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
PASS=0
FAIL=0

probe() {
  local label="$1" payload="$2" expected="$3" result exit_code verdict
  result=$(printf '%s' "$payload" | CABINET_HOOK_TEST_MODE=1 OFFICER_NAME=cto bash "$HOOK" 2>/dev/null; echo "EXIT:$?")
  exit_code="${result##*EXIT:}"
  if [ "$exit_code" = "$expected" ]; then
    verdict=PASS; PASS=$((PASS+1))
  else
    verdict=FAIL; FAIL=$((FAIL+1))
  fi
  printf "%-6s | %-58s | exit=%s\n" "$verdict" "$label" "$exit_code"
}

probe "Read raw event" \
  '{"tool_name":"Read","tool_input":{"file_path":"instance/evidence/v1/trials/DOGFOOD-001/events.jsonl"}}' 2
probe "Grep raw trial" \
  '{"tool_name":"Grep","tool_input":{"path":"instance/evidence/v1/trials/DOGFOOD-001","pattern":"status"}}' 2
probe "Read app-support signing key" \
  '{"tool_name":"Read","tool_input":{"file_path":"/Users/captain/Library/Application Support/cabinet/evidence/v1/.signing-key"}}' 2
probe "Write app-support signing key" \
  '{"tool_name":"Write","tool_input":{"file_path":"/Users/captain/Library/Application Support/cabinet/evidence/v1/.signing-key","content":"forged"}}' 2
probe "Shell raw read" \
  '{"tool_name":"Bash","tool_input":{"command":"cat instance/evidence/v1/trials/DOGFOOD-001/events.jsonl"}}' 2
probe "Direct evidence CLI purge" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -m framework.evidence purge DOGFOOD-001 --confirmation PURGE"}}' 2
probe "Direct onboarding writer" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -m framework.onboarding.journey act"}}' 2
probe "Python import bypass" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -c '\''import framework.evidence'\''"}}' 2
probe "Escaped app-support delete" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf ~/Library/Application\\ Support/cabinet/evidence/v1"}}' 2
probe "Bounded projection" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001"}}' 0
probe "Projection compound rejected" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001; cat /etc/passwd"}}' 2
probe "Ordinary onboarding read" \
  '{"tool_name":"Read","tool_input":{"file_path":"docs/onboarding/onboarding-v2-first-window.md"}}' 0

echo "=== Summary: PASS=$PASS  FAIL=$FAIL ==="
exit "$FAIL"
