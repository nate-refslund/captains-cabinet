#!/bin/bash
# FW-002 behavior eval — spending-limits gate in pre-tool-use.sh
#
# Contracts from shared/cabinet-framework-backlog.md FW-002:
#   (a) Every non-zero exit prints stderr reason (never silent-block)
#   (b) Telegram reply/react/group bypass cap with hourly sub-cap
#   (c) CoS gets 3x per-officer cap (coordinating_officer_multiplier)
#   (d) Platform.yml override; framework defaults fall through
#
# ISOLATION (2026-07-07, T2-arm-schedules review must-fix): this eval runs
# UNATTENDED every 6h inside the self-improvement-loop validation gate on the
# LIVE Mac deployment, so it must be side-effect-free against the live fleet.
# It therefore:
#   * copies the hook under test into a private tempdir and rebases ONLY two
#     config constants in the COPY: SPENDING_CONFIG_CACHE → a private cache
#     file (the real hook hardcodes /tmp/cabinet-spending-limits.tsv — the
#     shared cache EVERY live officer tool call reads; the old eval overwrote
#     it with fake caps and never cleaned it up), and POLICY_SHADOW → a
#     nonexistent path (the parity shadow appends to org_events; eval traffic
#     must not pollute the org ledger with fake-officer rows). Both patches
#     are ASSERTED after the copy — if the hook drifts and a patch stops
#     taking, the eval fails CLOSED (infra-fail) instead of silently
#     poisoning live state again.
#   * starts an EPHEMERAL redis-server on 127.0.0.1:<random high port> and
#     points its own redis-cli calls AND the hook invocation env at it. The
#     old eval HSET fake cost rows (cos at $226; two $600 phantom officers)
#     into the LIVE cabinet:cost:tokens:daily:<today> hash, and its trap
#     HDELed the wrong field name back out. Now no live Redis key is ever
#     touched; the "cos" multiplier contract is exercised without a real
#     officer slug ever reaching real state.
#   * never touches mtimes of real repo yaml files (the old GNU-`touch -d`
#     freeze calls are gone; cache staleness is controlled by touching the
#     PRIVATE cache, which is always newer than the repo yamls).
#
# SIGKILL-safety: the gate runner kills this shell after 120s WITHOUT running
# the EXIT trap, so a watcher subprocess reaps the ephemeral redis-server as
# soon as this shell dies (absolute ~300s bound either way) — fake data
# cannot outlive the eval even on a hard kill.
#
# Invocation (Mac-native deployment — the /opt/founders-cabinet Docker paths
# are extinct):  bash memory/golden-evals/framework/fw-002-spending-limits.sh
# Exit 0 = all tests pass; exit 1 = test failure OR infra-fail (fail-closed;
# the validation gate must go loudly red, never silently green).
#
# set -u intentionally off — the hook we're testing sources itself in various
# environments where not every env var is guaranteed to be set; testing under
# -u gives false failures on edge cases the hook already handles.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SRC_HOOK="$CABINET_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"

infra_fail() {
  echo "FW-002 INFRA-FAIL (gate stays closed): $*" >&2
  exit 1
}

[ -f "$SRC_HOOK" ] || infra_fail "hook under test not found: $SRC_HOOK"

TESTDIR=$(mktemp -d -t fw002-XXXXXX) || infra_fail "mktemp failed"
CACHE="$TESTDIR/spending-limits.tsv"
HOOK="$TESTDIR/pre-tool-use.under-test.sh"

# ---- Rebase the hook copy (see ISOLATION header) ---------------------------
sed -e "s|^SPENDING_CONFIG_CACHE=.*|SPENDING_CONFIG_CACHE=\"$CACHE\"|" \
    -e "s|^POLICY_SHADOW=.*|POLICY_SHADOW=\"/nonexistent/fw002-shadow-disabled\"|" \
    "$SRC_HOOK" > "$HOOK" \
  || { rm -rf "$TESTDIR"; infra_fail "hook copy/patch failed"; }
grep -qF "SPENDING_CONFIG_CACHE=\"$CACHE\"" "$HOOK" \
  || { rm -rf "$TESTDIR"; infra_fail "private-cache patch did not take (hook drift?)"; }
if grep -q '^SPENDING_CONFIG_CACHE="/tmp/' "$HOOK"; then
  rm -rf "$TESTDIR"; infra_fail "shared /tmp cache still assigned in hook copy"
fi
grep -q '^POLICY_SHADOW="/nonexistent/fw002-shadow-disabled"' "$HOOK" \
  || { rm -rf "$TESTDIR"; infra_fail "policy-shadow neutralization did not take (hook drift?)"; }

# ---- Ephemeral Redis (never the live instance) ------------------------------
REDIS_SERVER_BIN="$(command -v redis-server 2>/dev/null)"
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
    kill "$_pid" 2>/dev/null
    wait "$_pid" 2>/dev/null
  fi
done
if [ -z "$REDIS_PORT" ]; then
  tail -5 "$TESTDIR/redis-server.log" >&2 2>/dev/null
  rm -rf "$TESTDIR"
  infra_fail "could not start ephemeral redis-server"
fi

# Watcher: if this shell is SIGKILLed (gate-runner timeout), the EXIT trap
# never runs — the watcher notices the parent is gone and reaps the ephemeral
# server, bounded at ~300s absolute.
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
  kill "$REDIS_PID" 2>/dev/null
  kill "$WATCHER_PID" 2>/dev/null
  wait "$REDIS_PID" "$WATCHER_PID" 2>/dev/null
  rm -rf "$TESTDIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rcli() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"; }

TODAY=$(date -u +%Y-%m-%d)
KEY="cabinet:cost:tokens:daily:$TODAY"

PASS=0
FAIL=0
FAIL_DETAILS=""

# Every hook invocation gets the ISOLATED data plane: ephemeral Redis, real
# CABINET_ROOT (so the cap-=0 rebuild reads the REAL platform.yml — that is
# contract d), blank CABINET_ACTIVE_PROJECT (legacy field naming).
invoke_hook() {
  # usage: echo "$tool_json" | invoke_hook <officer> 2>err
  local officer="$1"
  OFFICER="$officer" OFFICER_NAME="$officer" \
    REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
    CABINET_ROOT="$CABINET_ROOT" CABINET_ACTIVE_PROJECT= \
    bash "$HOOK"
}

run() {
  # usage: run <label> <officer> <tool_json> <officer_cost_micro_opt> <expect_exit> <stderr_contains_or_empty>
  local label="$1" officer="$2" tool_json="$3" cost_micro="$4" expect_exit="$5" stderr_contains="$6"

  # Set the officer's cost in (ephemeral) redis, scoped to this test
  rcli HSET "$KEY" "${officer}_cost_micro" "$cost_micro" >/dev/null 2>&1

  # Invalidate the private cache so the hook re-reads the REAL yamls
  rm -f "$CACHE"

  # Capture stderr + exit
  local err_file
  err_file=$(mktemp "$TESTDIR/err.XXXXXX")
  echo "$tool_json" | invoke_hook "$officer" 2>"$err_file" >/dev/null
  local got_exit=$?
  local got_stderr
  got_stderr=$(cat "$err_file")
  rm -f "$err_file"

  local ok=1
  if [ "$got_exit" != "$expect_exit" ]; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS\n  [$label] expected exit=$expect_exit, got=$got_exit; stderr='$got_stderr'"
  fi
  if [ -n "$stderr_contains" ]; then
    if ! echo "$got_stderr" | grep -q "$stderr_contains"; then
      ok=0
      FAIL_DETAILS="$FAIL_DETAILS\n  [$label] stderr did not contain '$stderr_contains'; got='$got_stderr'"
    fi
  fi
  if [ "$ok" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label"
  fi
}

# Clear prior state for testofficer (fresh ephemeral instance, belt anyway)
rcli HDEL "$KEY" testofficer_cost_micro >/dev/null 2>&1

echo "=== FW-002 Spending Limits Gate — Golden Eval ==="
echo ""

# --- Test group 1: cap=0 (instance/config/platform.yml current state) ------
# This Cabinet's platform.yml has daily_per_officer_usd=0 and
# daily_cabinet_wide_usd=0. Every call should pass regardless of cost.
# (run() rm's the private cache, so the hook rebuilds it from the REAL
# platform.yml + framework defaults — contract d, exercised read-only.)
echo "-- Contract d: cap=0 means unlimited --"
run "cap=0 officer under cap → allow" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' 0 0 ""
run "cap=0 officer at \$1000 → still allow (unlimited)" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' "$((1000 * 1000000))" 0 ""

# --- Test group 2: simulate a fork's framework defaults by writing test caps
# directly into the PRIVATE cache. The cache is newer than both repo yamls
# (we just wrote it), so the hook's staleness check skips the rebuild and the
# enforcement branches run against our test caps — no repo file mtimes are
# touched. ------
echo ""
echo "-- Contract a: stderr on block when cap is enforced --"

# Simulate: per-officer cap $75, cabinet cap disabled
cat > "$CACHE" <<'EOF'
daily_per_officer_usd	75
daily_cabinet_wide_usd	0
coordinating_officer_multiplier	3.0
telegram_whitelist_enabled	true
telegram_whitelist_hourly_cap	10
EOF
touch "$CACHE"

# Wrap run to preserve cache across tests in this group
run_keep_cache() {
  local label="$1" officer="$2" tool_json="$3" cost_micro="$4" expect_exit="$5" stderr_contains="$6"
  rcli HSET "$KEY" "${officer}_cost_micro" "$cost_micro" >/dev/null 2>&1
  local err_file
  err_file=$(mktemp "$TESTDIR/err.XXXXXX")
  echo "$tool_json" | invoke_hook "$officer" 2>"$err_file" >/dev/null
  local got_exit=$?
  local got_stderr
  got_stderr=$(cat "$err_file")
  rm -f "$err_file"
  local ok=1
  [ "$got_exit" != "$expect_exit" ] && { ok=0; FAIL_DETAILS="$FAIL_DETAILS\n  [$label] expected exit=$expect_exit, got=$got_exit; stderr='$got_stderr'"; }
  if [ -n "$stderr_contains" ] && ! echo "$got_stderr" | grep -q "$stderr_contains"; then
    ok=0; FAIL_DETAILS="$FAIL_DETAILS\n  [$label] stderr missing '$stderr_contains'; got='$got_stderr'"
  fi
  if [ "$ok" = "1" ]; then PASS=$((PASS+1)); echo "  PASS: $label"; else FAIL=$((FAIL+1)); echo "  FAIL: $label"; fi
}

# 76 USD > 75 USD cap → BLOCK for non-cos officer
run_keep_cache "officer over \$75 cap → block with stderr" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' 76000000 2 "BLOCKED"
run_keep_cache "block stderr names the override path" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' 76000000 2 "platform.yml"
run_keep_cache "officer under \$75 cap → allow" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' 50000000 0 ""

echo ""
echo "-- Contract c: CoS 3x multiplier --"
# cos at $76 with per_off_cap=$75 would normally block, but 3x → effective $225.
# "cos" here is only a field name inside the EPHEMERAL instance — the live
# cabinet:cost:tokens:daily hash never sees it.
run_keep_cache "cos at \$76 with 3x → allow (effective cap \$225)" \
  "cos" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' 76000000 0 ""
# cos at $226 → BLOCK
run_keep_cache "cos at \$226 with 3x → block" \
  "cos" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' "$((226 * 1000000))" 2 "BLOCKED"
run_keep_cache "cos block mentions coordinator multiplier" \
  "cos" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' "$((226 * 1000000))" 2 "coordinator multiplier"
# Reset cos cost after cos tests so the cabinet-wide group below stays exact
rcli HDEL "$KEY" cos_cost_micro >/dev/null 2>&1

echo ""
echo "-- Contract b: Telegram whitelist bypasses cap --"
run_keep_cache "over-cap officer can still Telegram reply" \
  "testofficer" '{"tool_name":"mcp__plugin_telegram_telegram__reply","tool_input":{"chat_id":"1","text":"help"}}' 76000000 0 ""
run_keep_cache "over-cap officer can still Telegram react" \
  "testofficer" '{"tool_name":"mcp__plugin_telegram_telegram__react","tool_input":{"chat_id":"1","message_id":"1","emoji":"👍"}}' 76000000 0 ""
run_keep_cache "over-cap officer can still send-to-group.sh" \
  "testofficer" "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash $CABINET_ROOT/cabinet/scripts/send-to-group.sh hi\"}}" 76000000 0 ""

echo ""
echo "-- Contract a (reiterated): cabinet-wide cap with stderr --"
# Force cabinet-wide block: per-officer cap disabled, cabinet cap $1000,
# two officers at $600 each = $1200 > $1000 (all inside the ephemeral hash)
cat > "$CACHE" <<'EOF'
daily_per_officer_usd	0
daily_cabinet_wide_usd	1000
coordinating_officer_multiplier	3.0
telegram_whitelist_enabled	true
telegram_whitelist_hourly_cap	10
EOF
touch "$CACHE"
rcli HSET "$KEY" testofficer_cost_micro "$((600 * 1000000))" >/dev/null 2>&1
rcli HSET "$KEY" otherofficer_cost_micro "$((600 * 1000000))" >/dev/null 2>&1
run_keep_cache "cabinet-wide \$1200 > \$1000 → block" \
  "testofficer" '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' "$((600 * 1000000))" 2 "cabinet-wide"
rcli HDEL "$KEY" otherofficer_cost_micro testofficer_cost_micro >/dev/null 2>&1

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  printf "%b\n" "$FAIL_DETAILS"
  exit 1
fi
exit 0
