#!/bin/bash
# FW-A14 behavior eval — stop-hook context-guard (Captain pattern A14, msg 2605/2612/2614)
#
# Contracts:
#   (a) CABINET_STOP_GUARD_DISABLED=1 → guard skipped, exit 0, no block emitted
#   (b) CABINET_HOOK_TEST_MODE=1 → guard skipped, exit 0
#   (c) OFFICER=unknown → guard skipped, exit 0
#   (d) ctx_pct < threshold → exit 0, no block
#   (e) ctx_pct >= threshold but pending == 0 → exit 0, no block
#   (f) ctx_pct >= threshold AND pending > 0 → stdout contains `decision:block` JSON
#   (g) block cap: blocks_so_far >= GUARD_MAX_BLOCKS → exit 0 (allows stop)
#   (h) XPENDING not XLEN: ACK'd-only stream → PENDING_TRIGGERS=0, no block
#
# Requires: Redis accessible at REDIS_HOST:REDIS_PORT (default localhost:6379)
# Run in Docker: REDIS_HOST=redis bash memory/golden-evals/framework/fw-a14-stop-guard.sh
# Run on Mac:    ensure `redis-server` is running, then:
#                REDIS_HOST=localhost bash memory/golden-evals/framework/fw-a14-stop-guard.sh

set -euo pipefail

HOOK="/opt/founders-cabinet/cabinet/scripts/hooks/stop-hook.sh"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
TEST_OFFICER="test-a14-eval"
STREAM="cabinet:triggers:${TEST_OFFICER}"
GROUP="officer-${TEST_OFFICER}"
SESSION_ID="eval-session-001"
BLOCK_KEY="cabinet:stop-guard:blocks:${TEST_OFFICER}:${SESSION_ID}"

PASS=0
FAIL=0
FAIL_DETAILS=""

rc() {
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" > /dev/null 2>&1
}

rc_raw() {
  redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null
}

# -------------------------------------------------------
# Harness: run the guard section in isolation
# We pass empty HOOK_INPUT (no transcript_path) so sections
# 1/2/3 of stop-hook are no-ops. Only section 4 runs.
# -------------------------------------------------------
run() {
  local label="$1" ctx_pct="$2" expect_block="$3"
  shift 3
  local extra_env=("$@")

  # Plant ctx_pct in Redis
  rc HSET "cabinet:cost:tokens:${TEST_OFFICER}" last_context_pct "$ctx_pct"

  # Build env for the hook invocation
  local env_prefix=(
    "REDIS_HOST=$REDIS_HOST"
    "REDIS_PORT=$REDIS_PORT"
    "OFFICER_NAME=$TEST_OFFICER"
    "SESSION_ID=$SESSION_ID"
    "CABINET_HOOK_TEST_MODE=0"
    "CABINET_STOP_GUARD_DISABLED=0"
  )
  env_prefix+=("${extra_env[@]}")

  local out
  out=$(echo '{}' | env "${env_prefix[@]}" bash "$HOOK" 2>/dev/null)

  local got_block="false"
  if echo "$out" | jq -e '.decision == "block"' > /dev/null 2>&1; then
    got_block="true"
  fi

  local ok=1
  if [ "$got_block" != "$expect_block" ]; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS\n  [$label] expected block=$expect_block, got=$got_block; out='$(echo "$out" | head -c 200)'"
  fi

  if [ "$ok" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label"
  fi
}

# -------------------------------------------------------
# Setup helpers
# -------------------------------------------------------
clear_stream() {
  rc DEL "$STREAM"
  rc DEL "cabinet:cost:tokens:${TEST_OFFICER}"
  rc DEL "$BLOCK_KEY"
}

add_pending_trigger() {
  # Add a message to the stream, then deliver to consumer group (pending, not ACK'd)
  local msg_id
  msg_id=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" XADD "$STREAM" "*" type eval payload test 2>/dev/null)
  rc XGROUP CREATE "$STREAM" "$GROUP" 0 MKSTREAM
  # Read into the group to make it pending (do NOT ack)
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    XREADGROUP GROUP "$GROUP" "eval-consumer" COUNT 1 STREAMS "$STREAM" ">" > /dev/null 2>&1
  echo "$msg_id"
}

ack_all_pending() {
  # ACK all pending for the test consumer group
  local ids
  ids=$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" \
    XPENDING "$STREAM" "$GROUP" "-" "+" 100 2>/dev/null | awk 'NR%4==1 {print $1}')
  for id in $ids; do
    rc XACK "$STREAM" "$GROUP" "$id"
  done
}

cleanup() {
  rc DEL "$STREAM"
  rc DEL "cabinet:cost:tokens:${TEST_OFFICER}"
  rc DEL "$BLOCK_KEY"
  # Clean up all keys for this test officer
  for k in $(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "cabinet:*${TEST_OFFICER}*" 2>/dev/null); do
    rc DEL "$k"
  done
}
trap cleanup EXIT

echo "FW-A14 stop-hook context-guard eval"
echo "--------------------------------------"

# Verify Redis connectivity
if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
  echo "SKIP: Redis not available at $REDIS_HOST:$REDIS_PORT"
  echo "Run with: REDIS_HOST=redis bash $0 (inside Docker)"
  exit 0
fi

# -------------------------------------------------------
# AC (a): CABINET_STOP_GUARD_DISABLED=1 → no block even with high ctx + pending
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "disabled-guard" 85 "false" "CABINET_STOP_GUARD_DISABLED=1"

# -------------------------------------------------------
# AC (b): CABINET_HOOK_TEST_MODE=1 → no block
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "test-mode-skip" 85 "false" "CABINET_HOOK_TEST_MODE=1"

# -------------------------------------------------------
# AC (c): OFFICER=unknown → no block
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
# Override OFFICER_NAME to unknown
echo '{}' | REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  OFFICER_NAME="unknown" SESSION_ID="$SESSION_ID" \
  CABINET_HOOK_TEST_MODE=0 CABINET_STOP_GUARD_DISABLED=0 \
  bash "$HOOK" > /tmp/fw-a14-unknown-out.txt 2>/dev/null
if jq -e '.decision == "block"' /tmp/fw-a14-unknown-out.txt > /dev/null 2>&1; then
  FAIL=$((FAIL + 1))
  FAIL_DETAILS="$FAIL_DETAILS\n  [unknown-officer] block should NOT fire for officer=unknown"
  echo "  FAIL: unknown-officer"
else
  PASS=$((PASS + 1))
  echo "  PASS: unknown-officer"
fi
rm -f /tmp/fw-a14-unknown-out.txt

# -------------------------------------------------------
# AC (d): ctx_pct < threshold → no block (even with pending triggers)
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "ctx-below-threshold" 50 "false"

# -------------------------------------------------------
# AC (e): ctx_pct >= threshold but no pending triggers → no block
# -------------------------------------------------------
clear_stream
# Ensure stream exists but no pending (no XREADGROUP delivery)
rc XGROUP CREATE "$STREAM" "$GROUP" '$' MKSTREAM
run "high-ctx-no-pending" 80 "false"

# -------------------------------------------------------
# AC (f): ctx_pct >= threshold AND pending > 0 → decision:block emitted
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "fire-block" 80 "true"

# -------------------------------------------------------
# AC (g): block cap — blocks_so_far >= GUARD_MAX_BLOCKS → allow stop
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
# Pre-fill block counter to max (default 5)
rc SET "$BLOCK_KEY" 5
rc EXPIRE "$BLOCK_KEY" 86400
run "cap-allows-stop" 80 "false"

# -------------------------------------------------------
# AC (h): XPENDING not XLEN — ACK'd-only stream → no block
# -------------------------------------------------------
clear_stream
# Add message, deliver to group, then ACK it → XPENDING returns 0
add_pending_trigger > /dev/null
ack_all_pending
run "xpending-ackd-no-block" 80 "false"

# -------------------------------------------------------
# AC (i): custom threshold respected (CABINET_STOP_GUARD_CTX_PCT=90)
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
# ctx=80, threshold=90 → should NOT block
run "custom-threshold-skip" 80 "false" "CABINET_STOP_GUARD_CTX_PCT=90"

# -------------------------------------------------------
# AC (j): block JSON is valid JSON with decision + reason fields
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
rc HSET "cabinet:cost:tokens:${TEST_OFFICER}" last_context_pct 80
out=$(echo '{}' | REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  OFFICER_NAME="$TEST_OFFICER" SESSION_ID="$SESSION_ID" \
  CABINET_HOOK_TEST_MODE=0 CABINET_STOP_GUARD_DISABLED=0 \
  bash "$HOOK" 2>/dev/null)
if echo "$out" | jq -e '.decision == "block" and (.reason | type) == "string" and (.reason | length) > 0' > /dev/null 2>&1; then
  PASS=$((PASS + 1))
  echo "  PASS: block-json-valid"
else
  FAIL=$((FAIL + 1))
  FAIL_DETAILS="$FAIL_DETAILS\n  [block-json-valid] output not valid block JSON; got='$(echo "$out" | head -c 200)'"
  echo "  FAIL: block-json-valid"
fi

# -------------------------------------------------------
# Summary
# -------------------------------------------------------
echo "--------------------------------------"
TOTAL=$((PASS + FAIL))
echo "$PASS/$TOTAL tests passed"
if [ -n "$FAIL_DETAILS" ]; then
  echo -e "\nFailures:$FAIL_DETAILS"
  exit 1
fi
echo "All AC tests passed."
exit 0
