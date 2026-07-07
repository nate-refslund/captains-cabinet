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
# ISOLATION (2026-07-07, T2-arm-schedules review): this eval runs UNATTENDED
# every 6h inside the self-improvement-loop validation gate on the LIVE Mac
# deployment. It therefore:
#   * starts an EPHEMERAL redis-server on 127.0.0.1:<random high port> and
#     points both its own redis-cli calls and the hook invocation env at it —
#     no live Redis key is ever read, written, or KEYS-scanned;
#   * copies the hook under test into a private tempdir and rebases the
#     extinct /opt/founders-cabinet Docker prefix to $CABINET_ROOT in the
#     COPY (the live stop-hook.sh still carries the Docker paths — with them
#     the guard's trigger_count leg can never fire on Mac, so the guard LOGIC
#     is exercised against the path-rebased copy; the live file is untouched).
#     The rebase is ASSERTED: any surviving Docker path is an infra-fail.
#     With empty stdin (no transcript_path) sections 1–3 of the hook are
#     no-ops, so the rebased copy touches nothing on disk either.
#
# SIGKILL-safety: the gate runner kills this shell after 120s WITHOUT running
# the EXIT trap; a watcher subprocess reaps the ephemeral redis-server when
# this shell dies (absolute ~300s bound either way).
#
# Invocation (Mac-native deployment):
#   bash memory/golden-evals/framework/fw-a14-stop-guard.sh
# Exit 0 = all pass; non-zero = test failure or infra-fail (fail-closed —
# the validation gate must go loudly red, never silently green).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SRC_HOOK="$CABINET_ROOT/cabinet/scripts/hooks/stop-hook.sh"

infra_fail() {
  echo "FW-A14 INFRA-FAIL (gate stays closed): $*" >&2
  exit 1
}

[ -f "$SRC_HOOK" ] || infra_fail "hook under test not found: $SRC_HOOK"

TESTDIR=$(mktemp -d -t fwa14-XXXXXX) || infra_fail "mktemp failed"
HOOK="$TESTDIR/stop-hook.under-test.sh"

# ---- Rebase the hook copy (see ISOLATION header) ---------------------------
sed "s|/opt/founders-cabinet|$CABINET_ROOT|g" "$SRC_HOOK" > "$HOOK" \
  || { rm -rf "$TESTDIR"; infra_fail "hook copy/rebase failed"; }
if grep -q '/opt/founders-cabinet' "$HOOK"; then
  rm -rf "$TESTDIR"; infra_fail "Docker path survived the rebase (hook drift?)"
fi

# ---- Ephemeral Redis (never the live instance) ------------------------------
REDIS_SERVER_BIN="$(command -v redis-server 2>/dev/null || true)"
if [ -z "$REDIS_SERVER_BIN" ]; then
  for _cand in /opt/homebrew/bin/redis-server /usr/local/bin/redis-server; do
    if [ -x "$_cand" ]; then REDIS_SERVER_BIN="$_cand"; break; fi
  done
fi
[ -n "$REDIS_SERVER_BIN" ] || { rm -rf "$TESTDIR"; infra_fail "redis-server binary not found"; }
PATH="$(dirname "$REDIS_SERVER_BIN"):$PATH"   # redis-cli ships alongside redis-server

REDIS_HOST="127.0.0.1"
REDIS_PORT=""
REDIS_PID=""
_attempt=0
while [ -z "$REDIS_PORT" ] && [ "$_attempt" -lt 5 ]; do
  _attempt=$((_attempt + 1))
  _port=$((20000 + RANDOM % 40000))
  # stdout/stderr to files, NEVER inherited — an inherited pipe would keep the
  # gate runner's capture open after this shell exits and hang the gate.
  "$REDIS_SERVER_BIN" --port "$_port" --bind 127.0.0.1 --save '' \
      --appendonly no --dir "$TESTDIR" \
      > "$TESTDIR/redis-server.log" 2>&1 &
  _pid=$!
  _w=0
  while [ "$_w" -lt 25 ]; do
    _w=$((_w + 1))
    if redis-cli -h 127.0.0.1 -p "$_port" ping > /dev/null 2>&1; then
      REDIS_PORT="$_port"; REDIS_PID="$_pid"; break
    fi
    kill -0 "$_pid" 2>/dev/null || break   # server died early (port in use)
    sleep 0.2
  done
  if [ -z "$REDIS_PORT" ]; then
    kill "$_pid" 2>/dev/null || true
    wait "$_pid" 2>/dev/null || true
  fi
done
if [ -z "$REDIS_PORT" ]; then
  tail -5 "$TESTDIR/redis-server.log" >&2 2>/dev/null || true
  rm -rf "$TESTDIR"
  infra_fail "could not start ephemeral redis-server"
fi

# Watcher: reaps the ephemeral server if this shell is SIGKILLed (gate-runner
# timeout skips the EXIT trap), bounded at ~300s absolute.
EVAL_PID=$$
(
  _i=0
  while [ "$_i" -lt 300 ]; do
    kill -0 "$EVAL_PID" 2>/dev/null || break
    sleep 1
    _i=$((_i + 1))
  done
  kill "$REDIS_PID" 2>/dev/null
) > /dev/null 2>&1 &
WATCHER_PID=$!

cleanup() {
  kill "$REDIS_PID" 2>/dev/null || true
  kill "$WATCHER_PID" 2>/dev/null || true
  wait "$REDIS_PID" "$WATCHER_PID" 2>/dev/null || true
  rm -rf "$TESTDIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
# We pass session_id-only HOOK_INPUT (no transcript_path) so
# sections 1/2/3 of stop-hook are no-ops. Only section 4 runs.
# session_id MUST ride the stdin JSON: the hook overwrites the
# SESSION_ID env from `.session_id // empty` (that is where
# Claude Code provides it), so an env-only SESSION_ID silently
# keyed the block counter under ":nosession" — which is how the
# original AC (g) pre-fill missed the hook's key and only ever
# looked green via counter residue in the shared Docker redis.
# CABINET_ACTIVE_PROJECT is blanked so the triggers lib
# resolves the legacy stream/group names planted below.
# -------------------------------------------------------
HOOK_STDIN="{\"session_id\":\"$SESSION_ID\"}"

run() {
  local label="$1" ctx_pct="$2" expect_block="$3"
  shift 3
  local extra_env=("$@")

  # Plant ctx_pct in (ephemeral) Redis
  rc HSET "cabinet:cost:tokens:${TEST_OFFICER}" last_context_pct "$ctx_pct"

  # Build env for the hook invocation
  local env_prefix=(
    "REDIS_HOST=$REDIS_HOST"
    "REDIS_PORT=$REDIS_PORT"
    "OFFICER_NAME=$TEST_OFFICER"
    "SESSION_ID=$SESSION_ID"
    "CABINET_HOOK_TEST_MODE=0"
    "CABINET_STOP_GUARD_DISABLED=0"
    "CABINET_ACTIVE_PROJECT="
  )
  # bash-3.2-safe empty-array expansion: the gate invokes evals with
  # /bin/bash (macOS 3.2), where "${arr[@]}" on an empty array trips set -u.
  env_prefix+=(${extra_env[@]+"${extra_env[@]}"})

  local out
  out=$(echo "$HOOK_STDIN" | env "${env_prefix[@]}" bash "$HOOK" 2>/dev/null)

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
  # Belt: the key the hook uses when stdin carries no session_id — keeps
  # every AC independent even if an invocation regresses to empty input.
  rc DEL "cabinet:stop-guard:blocks:${TEST_OFFICER}:nosession"
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

echo "FW-A14 stop-hook context-guard eval"
echo "--------------------------------------"

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
echo "$HOOK_STDIN" | env REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  OFFICER_NAME="unknown" SESSION_ID="$SESSION_ID" \
  CABINET_HOOK_TEST_MODE=0 CABINET_STOP_GUARD_DISABLED=0 \
  CABINET_ACTIVE_PROJECT= \
  bash "$HOOK" > "$TESTDIR/unknown-out.txt" 2>/dev/null
if jq -e '.decision == "block"' "$TESTDIR/unknown-out.txt" > /dev/null 2>&1; then
  FAIL=$((FAIL + 1))
  FAIL_DETAILS="$FAIL_DETAILS\n  [unknown-officer] block should NOT fire for officer=unknown"
  echo "  FAIL: unknown-officer"
else
  PASS=$((PASS + 1))
  echo "  PASS: unknown-officer"
fi
rm -f "$TESTDIR/unknown-out.txt"

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
out=$(echo "$HOOK_STDIN" | env REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  OFFICER_NAME="$TEST_OFFICER" SESSION_ID="$SESSION_ID" \
  CABINET_HOOK_TEST_MODE=0 CABINET_STOP_GUARD_DISABLED=0 \
  CABINET_ACTIVE_PROJECT= \
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
