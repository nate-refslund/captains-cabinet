#!/bin/bash
# FW-A14 behavior eval — Stop-hook never-stop guard (Captain pattern A14,
# msg 2605/2612/2614; Captain directive 2026-06-23 "NEVER stop mid-task")
#
# RETARGETED 2026-07-25 — THIS EVAL WAS JUDGING A DEAD FILE.
#   It previously tested cabinet/scripts/hooks/stop-hook.sh, which is wired to
#   NO hook event: .claude/settings.json routes "Stop" to session-stop.sh, and
#   nothing anywhere invokes stop-hook.sh (verified across settings*.json, all
#   39 launchd plists, CI, installers and the egg manifest). The tell was in
#   this file's own isolation note: it had to REWRITE the file under test
#   (rebasing /opt/founders-cabinet) before the guard could fire at all —
#   a test that must patch its subject to make it runnable is testing something
#   the runtime never executes.
#
#   Worse, contracts (d)/(e)/(i) asserted a `ctx_pct >= threshold` guard THAT
#   DOES NOT EXIST IN THE LIVE HOOK. session-stop.sh gates on
#   `cabinet:active-task:<officer>` OR pending triggers and is explicitly
#   "Independent of context %" — it only ever WRITES last_context_pct (as cost
#   telemetry) and never reads it as a gate. So the eval was green on a
#   mechanism that had already been designed out.
#
#   The contracts below now assert what the live hook actually promises.
#   Nothing was relaxed: (d)/(e)/(i) were replaced with the real signals, and
#   (i) now positively asserts the design property that context is NEVER a
#   stop reason — the exact behaviour the old (d)/(e)/(i) contradicted.
#
# Contracts (against the LIVE Stop hook, cabinet/scripts/hooks/session-stop.sh):
#   (a) CABINET_STOP_GUARD_DISABLED=1 → guard skipped, exit 0, no block emitted
#   (b) CABINET_HOOK_TEST_MODE=1 → guard skipped, exit 0
#   (c) OFFICER=unknown → guard skipped, exit 0
#   (d) no active-task AND no pending triggers → exit 0, no block
#   (e) active-task set (no pending triggers) → decision:block emitted
#   (f) pending triggers > 0 (no active-task) → decision:block emitted
#   (g) block cap: blocks_so_far >= GUARD_MAX_BLOCKS → exit 0 (pinned via env)
#   (g2) the DEFAULT cap is 12: blocks at 11, allows at 12, no env override
#   (h) XPENDING not XLEN: ACK'd-only stream → PENDING_TRIGGERS=0, no block
#   (i) context % is NOT a stop signal: a high last_context_pct with no active
#       task and no pending triggers must NOT block
#   (j) block JSON is valid, with decision + non-empty reason
#
# ISOLATION (2026-07-07, T2-arm-schedules review): this eval runs UNATTENDED
# every 6h inside the self-improvement-loop validation gate on the LIVE Mac
# deployment. It therefore:
#   * starts an EPHEMERAL redis-server on 127.0.0.1:<random high port> and
#     points both its own redis-cli calls and the hook invocation env at it —
#     no live Redis key is ever read, written, or KEYS-scanned;
#   * copies the hook under test into a private tempdir and asserts no
#     container-era /opt/founders-cabinet prefix survives. The live
#     session-stop.sh resolves CABINET_ROOT relative to its own location and
#     carries no Docker paths, so the rebase is now a DRIFT CHECK rather than a
#     repair — if a Docker path ever reappears, this fails closed instead of
#     silently patching it away. The live file is never modified.
#     With session_id-only stdin (no transcript_path) the cost-ledger section
#     is a no-op, so the copy touches nothing on disk either.
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
# The LIVE Stop hook. Do not point this back at stop-hook.sh — that file is
# wired to no event, so this eval would judge behaviour the runtime never runs.
SRC_HOOK="$CABINET_ROOT/cabinet/scripts/hooks/session-stop.sh"
SETTINGS_JSON="$CABINET_ROOT/.claude/settings.json"

infra_fail() {
  echo "FW-A14 INFRA-FAIL (gate stays closed): $*" >&2
  exit 1
}

[ -f "$SRC_HOOK" ] || infra_fail "hook under test not found: $SRC_HOOK"

# Guard the retarget: if the Stop wiring moves, fail closed rather than keep
# judging a file the runtime no longer calls. This is the check whose absence
# let the eval run against a dead twin for weeks.
if [ -f "$SETTINGS_JSON" ] && ! grep -q 'hooks/session-stop.sh' "$SETTINGS_JSON"; then
  infra_fail "Stop wiring drift: .claude/settings.json no longer routes hooks/session-stop.sh — this eval may be judging a file the runtime does not call"
fi

TESTDIR=$(mktemp -d -t fwa14-XXXXXX) || infra_fail "mktemp failed"
HOOK="$TESTDIR/session-stop.under-test.sh"

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

# run <label> <active_task_value|""> <expect_block true|false> [extra env...]
#
# The second parameter used to be a context percentage. The live guard has no
# context threshold — it fires on the self-directed active-task flag or pending
# triggers — so the parameter now plants THAT signal. Pass "" for no active task.
run() {
  local label="$1" active_task="$2" expect_block="$3"
  shift 3
  local extra_env=("$@")

  # Plant the live guard's actual signal in (ephemeral) Redis.
  if [ -n "$active_task" ]; then
    rc SET "cabinet:active-task:${TEST_OFFICER}" "$active_task"
  else
    rc DEL "cabinet:active-task:${TEST_OFFICER}"
  fi

  # Build env for the hook invocation.
  # CABINET_ROOT is passed EXPLICITLY: the hook under test is a copy in a
  # tempdir, and session-stop.sh resolves its root from BASH_SOURCE
  # (../../.. of its own location). Without this the copy resolves to a parent
  # of TESTDIR, cabinet/scripts/lib/triggers.sh is unreadable, PENDING_TRIGGERS
  # is stuck at 0 and the pending-trigger leg of the guard can never fire —
  # silently, since the lookup is `[ -r ... ]` guarded. The dead hook this eval
  # used to target hid the same requirement behind its hardcoded Docker prefix,
  # which the sed rebase happened to fix.
  #
  # CABINET_EVENT_LOG_DIR is passed for the same reason the ephemeral Redis
  # exists, and it is NOT optional. session-stop.sh's section 2 calls
  # framework/events/emitter.py, which — unlike the dead hook this eval used to
  # target — appends a session_ended row to a DURABLE ledger under
  # ~/Library/Application Support/cabinet/events/ whenever this var is unset
  # (emitter.py:344,354). This eval runs unattended every 6h, so without the
  # redirect it would inject ~24 junk "test-a14-eval" rows a day into the real
  # event history, forever. Isolating Redis alone is not enough: the retarget
  # brought a second, file-backed production sink with it.
  local env_prefix=(
    "REDIS_HOST=$REDIS_HOST"
    "REDIS_PORT=$REDIS_PORT"
    "CABINET_ROOT=$CABINET_ROOT"
    "CABINET_EVENT_LOG_DIR=$TESTDIR/events"
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
  rc DEL "cabinet:active-task:${TEST_OFFICER}"
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

echo "FW-A14 never-stop guard eval (LIVE hook: cabinet/scripts/hooks/session-stop.sh)"
echo "--------------------------------------"

# -------------------------------------------------------
# AC (a): CABINET_STOP_GUARD_DISABLED=1 → no block even with work outstanding
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "disabled-guard" "task-in-flight" "false" "CABINET_STOP_GUARD_DISABLED=1"

# -------------------------------------------------------
# AC (b): CABINET_HOOK_TEST_MODE=1 → no block
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "test-mode-skip" "task-in-flight" "false" "CABINET_HOOK_TEST_MODE=1"

# -------------------------------------------------------
# AC (c): OFFICER=unknown → no block
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
rc SET "cabinet:active-task:${TEST_OFFICER}" "task-in-flight"
# Override OFFICER_NAME to unknown
echo "$HOOK_STDIN" | env REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  CABINET_ROOT="$CABINET_ROOT" CABINET_EVENT_LOG_DIR="$TESTDIR/events" OFFICER_NAME="unknown" SESSION_ID="$SESSION_ID" \
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
# AC (d): no active task AND no pending triggers → no block.
# The stream exists but nothing was delivered to the group.
# -------------------------------------------------------
clear_stream
rc XGROUP CREATE "$STREAM" "$GROUP" '$' MKSTREAM
run "idle-no-work-no-block" "" "false"

# -------------------------------------------------------
# AC (e): active task set, NO pending triggers → block.
# This is the live guard's primary signal and the one the previous eval never
# exercised: the officer's own self-directed task flag holds the stop open.
# -------------------------------------------------------
clear_stream
rc XGROUP CREATE "$STREAM" "$GROUP" '$' MKSTREAM
run "active-task-blocks-stop" "shipping the wave" "true"

# -------------------------------------------------------
# AC (f): pending triggers > 0, NO active task → block.
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
run "pending-triggers-block-stop" "" "true"

# -------------------------------------------------------
# AC (g): block cap — blocks_so_far >= GUARD_MAX_BLOCKS → allow stop
# (stuck-safety). The cap is pinned explicitly rather than relying on the
# default so the probe stays deterministic if the default is retuned.
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
rc SET "$BLOCK_KEY" 3
rc EXPIRE "$BLOCK_KEY" 86400
run "cap-allows-stop" "shipping the wave" "false" "CABINET_STOP_GUARD_MAX_BLOCKS=3"

# -------------------------------------------------------
# AC (g2): the DEFAULT cap is 12 — asserted with no env override, since (g)
# pins the variable and would stay green if the default silently changed.
# Below the default it must still block; at the default it must allow.
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
rc SET "$BLOCK_KEY" 11
rc EXPIRE "$BLOCK_KEY" 86400
run "default-cap-12-still-blocks-at-11" "shipping the wave" "true"

clear_stream
add_pending_trigger > /dev/null
rc SET "$BLOCK_KEY" 12
rc EXPIRE "$BLOCK_KEY" 86400
run "default-cap-12-allows-at-12" "shipping the wave" "false"

# -------------------------------------------------------
# AC (h): XPENDING not XLEN — ACK'd-only stream → no block
# -------------------------------------------------------
clear_stream
# Add message, deliver to group, then ACK it → XPENDING returns 0
add_pending_trigger > /dev/null
ack_all_pending
run "xpending-ackd-no-block" "" "false"

# -------------------------------------------------------
# AC (i): context % is NOT a stop signal.
# The live guard is explicitly "Independent of context %" — it only WRITES
# last_context_pct as cost telemetry and never reads it as a gate. A near-full
# context with no outstanding work must NOT block. This positively asserts the
# design property that the retired ctx_pct contracts contradicted.
# -------------------------------------------------------
clear_stream
rc XGROUP CREATE "$STREAM" "$GROUP" '$' MKSTREAM
rc HSET "cabinet:cost:tokens:${TEST_OFFICER}" last_context_pct 99
run "context-pct-is-not-a-stop-signal" "" "false"

# -------------------------------------------------------
# AC (j): block JSON is valid JSON with decision + reason fields
# -------------------------------------------------------
clear_stream
add_pending_trigger > /dev/null
rc SET "cabinet:active-task:${TEST_OFFICER}" "shipping the wave"
out=$(echo "$HOOK_STDIN" | env REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
  CABINET_ROOT="$CABINET_ROOT" CABINET_EVENT_LOG_DIR="$TESTDIR/events" OFFICER_NAME="$TEST_OFFICER" SESSION_ID="$SESSION_ID" \
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
