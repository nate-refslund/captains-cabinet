#!/bin/bash
# eval-org-005: Policy engine — typed policies block/allow correctly
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
ENGINE="$CABINET_ROOT/cabinet/scripts/lib/policy_engine.py"

if [ ! -f "$ENGINE" ]; then
    echo "FAIL: policy_engine.py not found at $ENGINE"
    exit 1
fi

FAILURES=0

# Helper: run engine with given tool input, expect block (exit 2)
expect_block() {
    local DESC="$1"
    local TOOL_NAME="$2"
    local TOOL_INPUT="$3"
    local OFFICER="${4:-cto}"
    local RESULT
    RESULT=$(echo "{\"tool_name\": \"$TOOL_NAME\", \"tool_input\": $TOOL_INPUT}" \
        | OFFICER="$OFFICER" CABINET_ROOT="$CABINET_ROOT" python3 "$ENGINE" 2>&1)
    local EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 2 ]; then
        echo "  OK (block): $DESC"
    else
        echo "  FAIL (expected block, got exit=$EXIT_CODE): $DESC"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: run engine with given tool input, expect allow (exit 0)
expect_allow() {
    local DESC="$1"
    local TOOL_NAME="$2"
    local TOOL_INPUT="$3"
    local OFFICER="${4:-cto}"
    local RESULT
    RESULT=$(echo "{\"tool_name\": \"$TOOL_NAME\", \"tool_input\": $TOOL_INPUT}" \
        | OFFICER="$OFFICER" CABINET_ROOT="$CABINET_ROOT" python3 "$ENGINE" 2>&1)
    local EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "  OK (allow): $DESC"
    else
        echo "  FAIL (expected allow, got exit=$EXIT_CODE): $DESC"
        echo "    stderr: $RESULT"
        FAILURES=$((FAILURES + 1))
    fi
}

echo "=== Prohibited Binary Blocks ==="
expect_block "sudo ls" "Bash" '{"command": "sudo ls"}'
expect_block "docker run" "Bash" '{"command": "docker run hello"}'
expect_block "systemctl restart" "Bash" '{"command": "systemctl restart nginx"}'
expect_block "shutdown -h now" "Bash" '{"command": "shutdown -h now"}'
expect_block "reboot" "Bash" '{"command": "reboot"}'
expect_block "halt" "Bash" '{"command": "halt"}'

echo ""
echo "=== Bypass Pattern Blocks (v3.x adversary patterns) ==="
expect_block "eval sudo" "Bash" '{"command": "eval '\''sudo ls'\''"}'
expect_block "bash -c sudo" "Bash" '{"command": "bash -c '\''sudo ls'\''"}'
expect_block "env sudo" "Bash" '{"command": "env sudo ls"}'
expect_block "/usr/bin/sudo" "Bash" '{"command": "/usr/bin/sudo ls"}'
expect_block "nohup sudo" "Bash" '{"command": "nohup sudo ls"}'
expect_block "exec sudo" "Bash" '{"command": "exec sudo ls"}'
expect_block "compound sudo" "Bash" '{"command": "echo ok; sudo ls"}'
expect_block "chain sudo" "Bash" '{"command": "true && sudo ls"}'

echo ""
echo "=== Destructive Operations ==="
expect_block "rm -rf /" "Bash" '{"command": "rm -rf /"}'
expect_block "rm -fr /" "Bash" '{"command": "rm -fr /"}'
expect_block "DROP TABLE" "Bash" '{"command": "psql -c '\''DROP TABLE users'\''"}'
expect_block "vercel deploy" "Bash" '{"command": "vercel deploy --prod"}'

echo ""
echo "=== False Positive Guards (must allow) ==="
expect_allow "grep sudo" "Bash" '{"command": "grep -E '\''sudo|docker'\'' file.txt"}'
expect_allow "echo sudo" "Bash" '{"command": "echo '\''sudo ls'\''"}'
expect_allow "ls docker-compose" "Bash" '{"command": "ls docker-compose.yml"}'
expect_allow "rm file (non-recursive)" "Bash" '{"command": "rm /tmp/test.txt"}'
expect_allow "cat product code" "Bash" '{"command": "cat /workspace/product/README.md"}' "cto"
expect_allow "normal git" "Bash" '{"command": "git status"}'

echo ""
echo "=== Path Blocks ==="
expect_block "edit constitution" "Edit" '{"file_path": "/opt/founders-cabinet/constitution/CONSTITUTION.md"}'
expect_block "write .env" "Write" '{"file_path": "/opt/founders-cabinet/.env"}'

echo ""
echo "=== Codebase Ownership ==="
expect_block "CPO edits product" "Edit" '{"file_path": "/workspace/product/src/app.tsx"}' "cpo"
expect_allow "CTO edits product" "Edit" '{"file_path": "/workspace/product/src/app.tsx"}' "cto"

if [ "$FAILURES" -gt 0 ]; then
    echo ""
    echo "FAIL: $FAILURES policy engine checks failed"
    exit 1
fi

echo ""
echo "OK: Policy engine verified"
exit 0
