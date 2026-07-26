#!/bin/bash
# FW-002 behavior eval — spending-limits gate in pre-tool-use.sh
#
# Contracts from shared/cabinet-framework-backlog.md FW-002:
#   (a) Every non-zero exit prints stderr reason (never silent-block)
#   (b) Telegram reply/react/group bypass cap, with an hourly sub-cap
#   (c) CoS gets 3x per-officer cap (coordinating_officer_multiplier)
#   (d) Platform.yml override; framework defaults fall through
# plus, since 2026-07-26, the Captain's uncapping ruling:
#   (e) `unlimited` (and a literal 0) means NO enforcement — a $1,000,000
#       officer and a $1,000,000 Cabinet both run.
#
# ---------------------------------------------------------------------------
# WHY THIS FILE WAS REWRITTEN (2026-07-27) — the sensor was testing nothing
# ---------------------------------------------------------------------------
# The previous version controlled the caps by writing them into the hook's
# ON-DISK config cache (/tmp/cabinet-spending-limits.tsv, rebased into a
# private tempdir) and relied on the hook's mtime staleness check to leave
# that planted file alone. Commit 77422706 deleted that mechanism: the hook
# now mktemps a FRESH cache per invocation, regenerates it from the real yaml
# on EVERY call, and deletes it before returning. From that commit on, every
# planted cap was ignored and test groups 2-4 silently read the LIVE
# instance/config/platform.yml. They kept passing only because the live cap
# happened to equal the planted one ($75). When the Captain uncapped spend the
# coincidence ended and the eval went red — which was luck, not detection: for
# weeks a green run had proved nothing about the caps it claimed to test.
#
# The ONLY config surface the current hook honours is the yaml it reads under
# $CABINET_ROOT. So every arm below builds a SYNTHETIC CABINET_ROOT holding
# just instance/config/platform.yml, framework/defaults/spending-limits.yml
# and a cabinet/mcp-scope.yml, and points the hook at it. The hook itself runs
# UNPATCHED and UNCOPIED — the sensor is wired to the live artifact, not to a
# sed-rewritten twin of it (the old copy-and-patch also meant a hook drift
# could silently change what was under test).
#
# MECHANISM PROBE (read this before adding an arm): a synthetic root that the
# hook silently ignored would make every "allow" arm below pass for the wrong
# reason — the classic sensor-not-wired failure. So the first thing this eval
# does is plant an ABSURD $0.000001 cap in a synthetic root and require a
# block. If that probe does not block, the eval fails CLOSED and no other
# result is reported. Any new arm must stay downstream of it.
#
# ISOLATION (2026-07-07, T2-arm-schedules review must-fix; kept intact): this
# eval runs UNATTENDED every 6h inside the self-improvement-loop validation
# gate on the LIVE Mac deployment, so it must be side-effect-free against the
# live fleet. It therefore:
#   * writes NO repo file and touches NO repo mtime — the caps under test live
#     in a private tempdir, never in instance/config/platform.yml.
#   * neutralises the typed-policy shadow BY CONSTRUCTION: POLICY_SHADOW
#     resolves under $CABINET_ROOT and no synthetic root contains
#     cabinet/scripts/policy-shadow.py, so no eval traffic can reach
#     org_events. The arm that pins the SHIPPED caps uses a root whose two
#     spend yamls are SYMLINKS to the real ones — the live values, without
#     the live side-effects.
#   * starts an EPHEMERAL redis-server on 127.0.0.1:<random high port> and
#     points both its own redis-cli calls and the hook at it, so no live key
#     is ever read or written. The one exception is an endpoint the CALLER
#     declares throwaway (CABINET_EVALS_REDIS_DISPOSABLE=1, as CI's redis:7
#     service container does — the GitHub runner image has redis-cli but no
#     redis-server, so it cannot sandbox); even then every field this eval
#     writes is saved before and restored after, and the emergency stop is
#     read but NEVER written (clearing a deliberately-armed killswitch is the
#     exact incident cabinet/scripts/lib/evals-redis-sandbox.sh exists for).
#   * deliberately does NOT source that sandbox library, which does the same
#     job for run-golden-evals.sh. This file is germline-locked and that
#     library is not: sourcing it would make this eval's "never touch the live
#     Redis" property depend on a file any officer can edit. Duplication is
#     the cheaper risk.
#
# SIGKILL-safety: the gate runner kills this shell after 120s WITHOUT running
# the EXIT trap, so a watcher subprocess reaps the ephemeral redis-server as
# soon as this shell dies (absolute ~300s bound either way) — fake data
# cannot outlive the eval even on a hard kill.
#
# Invocation:  bash memory/golden-evals/framework/fw-002-spending-limits.sh
# Exit 0 = all tests pass; exit 1 = test failure OR infra-fail (fail-closed;
# the validation gate must go loudly red, never silently green).
#
# set -u intentionally off — the hook we're testing sources itself in various
# environments where not every env var is guaranteed to be set; testing under
# -u gives false failures on edge cases the hook already handles.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
REAL_ROOT="$CABINET_ROOT"
HOOK="$REAL_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"

infra_fail() {
  echo "FW-002 INFRA-FAIL (gate stays closed): $*" >&2
  exit 1
}

[ -f "$HOOK" ] || infra_fail "hook under test not found: $HOOK"

# ---- Mechanism assertions --------------------------------------------------
# The arms below are only meaningful while the hook (1) honours an inherited
# CABINET_ROOT, (2) reads its caps from the two yaml paths under it, and
# (3) keeps no persisted cap cache a stale planted file could stand in for.
# If any of these drift, this eval must fail CLOSED rather than quietly test
# something else — which is exactly what the previous version did for weeks.
grep -qF 'CABINET_ROOT="${CABINET_ROOT:-' "$HOOK" \
  || infra_fail "hook no longer honours an inherited CABINET_ROOT (mechanism drift)"
grep -qF 'PLATFORM_YML="$CABINET_ROOT/instance/config/platform.yml"' "$HOOK" \
  || infra_fail "hook no longer reads instance/config/platform.yml under CABINET_ROOT"
grep -qF 'FRAMEWORK_DEFAULTS_YML="$CABINET_ROOT/framework/defaults/spending-limits.yml"' "$HOOK" \
  || infra_fail "hook no longer reads framework/defaults/spending-limits.yml under CABINET_ROOT"
grep -qF 'SPENDING_CONFIG_CACHE=$(mktemp ' "$HOOK" \
  || infra_fail "spending config cache is no longer a per-invocation mktemp — re-derive how caps are controlled before trusting this eval"

REAL_PLATFORM_YML="$REAL_ROOT/instance/config/platform.yml"
REAL_DEFAULTS_YML="$REAL_ROOT/framework/defaults/spending-limits.yml"
REAL_MCP_SCOPE="$REAL_ROOT/cabinet/mcp-scope.yml"
for _f in "$REAL_PLATFORM_YML" "$REAL_DEFAULTS_YML" "$REAL_MCP_SCOPE"; do
  [ -f "$_f" ] || infra_fail "required repo file not found: $_f"
done

TESTDIR=$(mktemp -d "${TMPDIR:-/tmp}/fw002.XXXXXX") || infra_fail "mktemp failed"

# ---- Redis: ephemeral, never the live instance -----------------------------
# Endpoint resolution mirrors the hook's own (REDIS_HOST/PORT win, REDIS_URL
# is the fallback) so a caller-declared disposable endpoint is the SAME one
# the hook will talk to.
REDIS_SANDBOXED=0
REDIS_PID=""
WATCHER_PID=""
if [ "${CABINET_EVALS_REDIS_DISPOSABLE:-}" = "1" ]; then
  if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
    REDIS_HOST="${REDIS_HOST:-127.0.0.1}"; REDIS_PORT="${REDIS_PORT:-6379}"
  elif [ -n "${REDIS_URL:-}" ]; then
    REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
    REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
    REDIS_HOST="${REDIS_HOST:-127.0.0.1}"; REDIS_PORT="${REDIS_PORT:-6379}"
  else
    REDIS_HOST="127.0.0.1"; REDIS_PORT="6379"
  fi
  command -v redis-cli > /dev/null 2>&1 \
    || { rm -rf "$TESTDIR"; infra_fail "redis-cli not found (endpoint declared disposable)"; }
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG \
    || { rm -rf "$TESTDIR"; infra_fail "declared-disposable redis at $REDIS_HOST:$REDIS_PORT did not answer PING"; }
  echo "fw-002: endpoint declared disposable — using $REDIS_HOST:$REDIS_PORT (fields saved + restored)"
else
  REDIS_SERVER_BIN="$(command -v redis-server 2>/dev/null)"
  if [ -z "$REDIS_SERVER_BIN" ]; then
    for _cand in /opt/homebrew/bin/redis-server /usr/local/bin/redis-server; do
      if [ -x "$_cand" ]; then REDIS_SERVER_BIN="$_cand"; break; fi
    done
  fi
  [ -n "$REDIS_SERVER_BIN" ] || { rm -rf "$TESTDIR"; infra_fail "redis-server binary not found (set CABINET_EVALS_REDIS_DISPOSABLE=1 ONLY if the endpoint is a throwaway, as CI's service container is)"; }
  PATH="$(dirname "$REDIS_SERVER_BIN"):$PATH"   # redis-cli ships alongside redis-server

  REDIS_HOST="127.0.0.1"
  REDIS_PORT=""
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
      # Our spawn must still be alive BEFORE a PONG is trusted: if the port was
      # already held, our server died on bind and the PONG would come from a
      # FOREIGN redis — pointing the hook at that would defeat the isolation.
      kill -0 "$_pid" 2>/dev/null || break
      if redis-cli -h 127.0.0.1 -p "$_port" ping > /dev/null 2>&1; then
        REDIS_PORT="$_port"; REDIS_PID="$_pid"; REDIS_SANDBOXED=1; break
      fi
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
fi

rcli() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"; }

TODAY=$(date -u +%Y-%m-%d)
KEY="cabinet:cost:tokens:daily:$TODAY"

# Synthetic officer slugs. `cos` is unavoidable for contract (c) — the hook
# hard-codes that slug — so its field is saved and restored like the rest.
OFF=fw002off
PEER=fw002peer
TOUCHED_FIELDS="${OFF}_cost_micro ${PEER}_cost_micro cos_cost_micro"

# SAVED_FIELDS is only meaningful once the save loop below has actually run.
# cleanup() therefore refuses to touch the hash until SAVE_DONE=1: an
# infra_fail between "trap installed" and "state saved" must not HDEL a field
# whose real value we never read (on a declared-disposable endpoint that would
# be destroying data to clean up after work we never did).
SAVED_FIELDS=""
SAVE_DONE=0

cleanup() {
  if [ "$SAVE_DONE" = "1" ]; then
    # Undo every field we wrote, restoring any pre-existing value.
    # shellcheck disable=SC2086
    rcli HDEL "$KEY" $TOUCHED_FIELDS > /dev/null 2>&1
    if [ -n "$SAVED_FIELDS" ]; then
      while IFS='=' read -r _sf _sv; do
        [ -z "$_sf" ] && continue
        rcli HSET "$KEY" "$_sf" "$_sv" > /dev/null 2>&1
      done <<EOF
$SAVED_FIELDS
EOF
    fi
    # Telegram sub-cap buckets belong to synthetic officers only.
    for _k in $(rcli --scan --pattern "cabinet:tg-whitelist:${OFF}:*" 2>/dev/null); do
      rcli DEL "$_k" > /dev/null 2>&1
    done
  fi
  [ -n "$REDIS_PID" ] && kill "$REDIS_PID" 2>/dev/null
  [ -n "$WATCHER_PID" ] && kill "$WATCHER_PID" 2>/dev/null
  wait "$REDIS_PID" "$WATCHER_PID" 2>/dev/null
  rm -rf "$TESTDIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# An armed emergency stop refuses every tool call, which would present as a
# dozen confusing arm failures. Read it (never write it) and say so plainly.
_ks=$(rcli GET cabinet:killswitch 2>/dev/null)
if [ -n "$_ks" ] && [ "$_ks" != "(nil)" ]; then
  infra_fail "cabinet:killswitch is set ('$_ks') on $REDIS_HOST:$REDIS_PORT — every hook call would be refused. This eval never clears it; clear it deliberately and re-run."
fi

# On a declared-disposable (shared) endpoint, remember what was there.
if [ "$REDIS_SANDBOXED" != "1" ]; then
  for _f in $TOUCHED_FIELDS; do
    _v=$(rcli HGET "$KEY" "$_f" 2>/dev/null)
    if [ -n "$_v" ] && [ "$_v" != "(nil)" ]; then
      SAVED_FIELDS="$SAVED_FIELDS$_f=$_v
"
    fi
  done
fi
SAVE_DONE=1

PASS=0
FAIL=0
FAIL_DETAILS=""

# ---- Synthetic CABINET_ROOT builder ----------------------------------------
# Builds a root holding ONLY what the spend gate and the section-9 MCP-scope
# gate read, and returns it in $ROOT_OUT (a global, not stdout: infra_fail
# inside a command substitution would only kill the subshell and the caller
# would sail on with an empty root).
#
#   make_root <name> <per_officer_usd|-|@live> <cabinet_wide_usd|-|@live> \
#             [cos_mult] [tg_hourly_cap]
#
# A cap given as `-` is OMITTED from platform.yml, so the value falls through
# from framework/defaults/spending-limits.yml — that fall-through IS contract
# (d) and it is only exercised when a key is genuinely missing.
# `@live` symlinks BOTH yamls to the real repo files, so the arm reads the
# SHIPPED caps (the other arguments are then ignored).
ROOT_N=0
ROOT_OUT=""
make_root() {
  local name="$1" per="$2" cab="$3" mult="${4:-3.0}" tgcap="${5:-10}"
  ROOT_N=$((ROOT_N + 1))
  local root="$TESTDIR/root-$ROOT_N-$name"
  mkdir -p "$root/instance/config" "$root/framework/defaults" "$root/cabinet" \
    || infra_fail "could not build synthetic root $root"

  if [ "$per" = "@live" ]; then
    ln -s "$REAL_PLATFORM_YML" "$root/instance/config/platform.yml" \
      || infra_fail "could not link the live platform.yml into $root"
    ln -s "$REAL_DEFAULTS_YML" "$root/framework/defaults/spending-limits.yml" \
      || infra_fail "could not link the live framework defaults into $root"
  else
    # Framework defaults: the real shipped floor a forker inherits.
    cat > "$root/framework/defaults/spending-limits.yml" <<'EOF'
spending_limits:
  daily_per_officer_usd: 75
  daily_cabinet_wide_usd: 300
  coordinating_officer_multiplier: 3.0
  telegram_whitelist_enabled: true
  telegram_whitelist_hourly_cap: 10
EOF
    {
      echo "spending_limits:"
      [ "$per" != "-" ] && echo "  daily_per_officer_usd: $per"
      [ "$cab" != "-" ] && echo "  daily_cabinet_wide_usd: $cab"
      echo "  coordinating_officer_multiplier: $mult"
      echo "  telegram_whitelist_enabled: true"
      echo "  telegram_whitelist_hourly_cap: $tgcap"
    } > "$root/instance/config/platform.yml"
  fi

  # MCP scope: the REAL file plus this eval's synthetic officers. The section-9
  # gate runs downstream of the spend gate and fails CLOSED on an unlisted
  # identity, so without this the Telegram arms would test identity
  # registration instead of contract (b) — a false RED that hid the whitelist
  # behaviour entirely.
  FW002_OFF="$OFF" FW002_PEER="$PEER" \
    python3 - "$REAL_MCP_SCOPE" "$root/cabinet/mcp-scope.yml" <<'PY' 2>/dev/null
import os, re, sys
src, dst = sys.argv[1], sys.argv[2]
out, inserted = [], False
for line in open(src).read().splitlines():
    out.append(line)
    if not inserted and re.match(r'^agents:\s*$', line):
        for slug in (os.environ["FW002_OFF"], os.environ["FW002_PEER"]):
            out.append("  %s:" % slug)
            out.append("    mcps: [telegram]")
        inserted = True
if not inserted:
    sys.exit(1)
open(dst, "w").write("\n".join(out) + "\n")
PY
  grep -q "^  $OFF:\$" "$root/cabinet/mcp-scope.yml" 2>/dev/null \
    || infra_fail "could not register $OFF in a synthetic mcp-scope.yml derived from $REAL_MCP_SCOPE (real file shape changed?)"

  ROOT_OUT="$root"
}

# Every hook invocation gets the ISOLATED data plane: our redis endpoint, the
# root under test, blank CABINET_ACTIVE_PROJECT (legacy field naming).
invoke_hook() {
  # usage: echo "$tool_json" | invoke_hook <officer> <root>
  local officer="$1" root="$2"
  OFFICER="$officer" OFFICER_NAME="$officer" \
    REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
    REDIS_URL="redis://$REDIS_HOST:$REDIS_PORT" \
    CABINET_ROOT="$root" CABINET_ACTIVE_PROJECT= \
    CABINET_AUTHORITY_ENFORCING=0 \
    bash "$HOOK"
}

# run <label> <root> <officer> <tool_json> <expect_exit> <stderr_must_contain> \
#     [<stderr_must_NOT_contain>]
#
# Costs are planted by the caller (set_cost) rather than inside run(), because
# the cabinet-wide arms need MORE THAN ONE officer's spend on the books at
# once — the old single-cost signature is a large part of why the
# cabinet-wide arm could never reach its own gate.
run() {
  local label="$1" root="$2" officer="$3" tool_json="$4"
  local expect_exit="$5" want="$6" unwanted="${7:-}"

  local err_file
  err_file=$(mktemp "$TESTDIR/err.XXXXXX")
  echo "$tool_json" | invoke_hook "$officer" "$root" 2>"$err_file" >/dev/null
  local got_exit=$?
  local got_stderr
  got_stderr=$(cat "$err_file")
  rm -f "$err_file"

  local ok=1
  if [ "$got_exit" != "$expect_exit" ]; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS\n  [$label] expected exit=$expect_exit, got=$got_exit; stderr='$got_stderr'"
  fi
  if [ -n "$want" ] && ! echo "$got_stderr" | grep -qF -- "$want"; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS\n  [$label] stderr did not contain '$want'; got='$got_stderr'"
  fi
  if [ -n "$unwanted" ] && echo "$got_stderr" | grep -qF -- "$unwanted"; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS\n  [$label] stderr contained '$unwanted', which this arm forbids (a block that should not have happened, or the wrong gate firing); got='$got_stderr'"
  fi
  if [ "$ok" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  PASS: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label"
  fi
}

set_cost() {  # set_cost <officer> <usd>
  rcli HSET "$KEY" "${1}_cost_micro" \
    "$(awk -v v="$2" 'BEGIN{printf "%.0f", v*1000000}')" >/dev/null 2>&1
}
clear_costs() {
  # shellcheck disable=SC2086
  rcli HDEL "$KEY" $TOUCHED_FIELDS >/dev/null 2>&1
}
clear_tg_buckets() {
  local k
  for k in $(rcli --scan --pattern "cabinet:tg-whitelist:${OFF}:*" 2>/dev/null); do
    rcli DEL "$k" > /dev/null 2>&1
  done
}

BASH_CALL='{"tool_name":"Bash","tool_input":{"command":"echo hi"}}'
TG_REPLY='{"tool_name":"mcp__plugin_telegram_telegram__reply","tool_input":{"chat_id":"1","text":"help"}}'
TG_REACT='{"tool_name":"mcp__plugin_telegram_telegram__react","tool_input":{"chat_id":"1","message_id":"1","emoji":"OK"}}'
NON_TG_MCP='{"tool_name":"mcp__plugin_telegram_telegram__delete_message","tool_input":{"chat_id":"1","message_id":"1"}}'

echo "=== FW-002 Spending Limits Gate — Golden Eval ==="
echo ""

# ---------------------------------------------------------------------------
# MECHANISM PROBE — is the synthetic root actually being read?
# Fails CLOSED. Every "allow" arm below is worthless if this one does not
# block: an ignored root would silently re-run all of them against whatever
# the live platform.yml happens to say (the exact failure that hid this
# eval's rot for weeks).
# ---------------------------------------------------------------------------
make_root probe 0.000001 0; PROBE_ROOT="$ROOT_OUT"
clear_costs
set_cost "$OFF" 1
_probe_err=$(echo "$BASH_CALL" | invoke_hook "$OFF" "$PROBE_ROOT" 2>&1 >/dev/null)
_probe_rc=$?
if [ "$_probe_rc" != "2" ] || ! echo "$_probe_err" | grep -qF "BLOCKED"; then
  infra_fail "the probe cap did not stop an over-cap call (cap \$0.000001 vs \$1 spend => exit=$_probe_rc, stderr='$_probe_err'). EITHER the synthetic CABINET_ROOT is not controlling the hook's caps — in which case every arm downstream would pass for the wrong reason — OR the per-officer block itself no longer fires. Check python3 availability, the hook's cap-parsing block, and the per-officer comparison before trusting any FW-002 result."
fi
echo "  (mechanism probe OK — the hook reads the synthetic root's caps)"
echo ""

# ---------------------------------------------------------------------------
# Group 1 — contract (e): the Captain's uncapping ruling (2026-07-26).
# This is the INVERSION of the old "must block" arm, which asserted the
# opposite against the live config. Both directions are now pinned: the
# `unlimited` sentinel must survive the hook's non-numeric coercion (delete
# _cap_is_unlimited and these go red, because `unlimited` would fall back to
# the $75/$300 framework floor and a $1M spend would block).
# ---------------------------------------------------------------------------
echo "-- Contract e: 'unlimited' means unlimited --"
make_root unlimited unlimited unlimited; UNCAPPED_ROOT="$ROOT_OUT"
clear_costs
set_cost "$OFF" 1000000
run "officer at \$1,000,000, cap=unlimited → allow" \
  "$UNCAPPED_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"
set_cost "$PEER" 1000000
run "cabinet-wide \$2,000,000, cap=unlimited → allow" \
  "$UNCAPPED_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"
set_cost "cos" 1000000
run "cos at \$1,000,000, cap=unlimited → allow" \
  "$UNCAPPED_ROOT" "cos" "$BASH_CALL" 0 "" "BLOCKED"
# The sentinel must be MATCHED, not merely survived: if `unlimited` ever falls
# through to the non-numeric coercion the hook warns and silently applies the
# $75/$300 floor. Exit 0 alone would still pass that if a future default
# happened to be 0 — the absence of the warning is what pins the sentinel.
run "cap=unlimited is understood, not coerced (no not-numeric warning)" \
  "$UNCAPPED_ROOT" "$OFF" "$BASH_CALL" 0 "" "is not numeric"

echo ""
echo "-- Contract e: a literal 0 still means unlimited --"
make_root zero 0 0; ZERO_ROOT="$ROOT_OUT"
run "officer at \$1,000,000, cap=0 → allow" \
  "$ZERO_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"
run "cabinet-wide \$3,000,000, cap=0 → allow" \
  "$ZERO_ROOT" "$PEER" "$BASH_CALL" 0 "" "BLOCKED"

echo ""
echo "-- Contract e: the SHIPPED config and the hook agree --"
# The one arm that reads the REAL instance/config/platform.yml (symlinked into
# a synthetic root so the typed-policy shadow still cannot see eval traffic).
# It asserts CONSISTENCY, not a particular cap: whatever the Captain has
# configured, the gate must behave that way. Written as a specific-value check
# it would false-RED the moment the Captain legitimately changes a cap.
_live_cap() {  # _live_cap <yaml>
  awk '/^spending_limits:/{f=1;next} f&&/^[^[:space:]]/{f=0}
       f&&/^[[:space:]]*daily_per_officer_usd:/{gsub(/#.*/,"");print $2;exit}' "$1" 2>/dev/null
}
LIVE_PER=$(_live_cap "$REAL_PLATFORM_YML")
[ -z "$LIVE_PER" ] && LIVE_PER=$(_live_cap "$REAL_DEFAULTS_YML")
make_root shipped @live @live; SHIPPED_ROOT="$ROOT_OUT"
clear_costs
case "$(printf '%s' "$LIVE_PER" | tr '[:upper:]' '[:lower:]')" in
  unlimited|none|off|infinite|inf|0|0.0)
    set_cost "$OFF" 1000000
    run "shipped platform.yml says '$LIVE_PER' → \$1,000,000 officer runs" \
      "$SHIPPED_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"
    run "the shipped cap is understood, not coerced" \
      "$SHIPPED_ROOT" "$OFF" "$BASH_CALL" 0 "" "is not numeric"
    ;;
  ''|*[!0-9.]*)
    FAIL=$((FAIL + 1))
    FAIL_DETAILS="$FAIL_DETAILS\n  [shipped platform.yml cap is unreadable] daily_per_officer_usd='$LIVE_PER' — neither a number nor an unlimited sentinel"
    echo "  FAIL: shipped platform.yml cap is unreadable ('$LIVE_PER')"
    ;;
  *)
    set_cost "$OFF" "$(awk -v v="$LIVE_PER" 'BEGIN{printf "%.6f", v+1}')"
    run "shipped platform.yml caps at \$$LIVE_PER → one dollar over blocks" \
      "$SHIPPED_ROOT" "$OFF" "$BASH_CALL" 2 "BLOCKED" ""
    ;;
esac

# ---------------------------------------------------------------------------
# Group 2 — the MACHINERY still works under an explicit numeric cap. This is
# what protects a forker (framework defaults ship $75/$300) and what keeps
# this eval capable of going red: break the block and these arms fail.
# ---------------------------------------------------------------------------
echo ""
echo "-- Contract a: an explicit numeric cap still blocks, with stderr --"
make_root cap75 75 0; CAP75_ROOT="$ROOT_OUT"
clear_costs
set_cost "$OFF" 76
run "officer over \$75 cap → block with stderr" \
  "$CAP75_ROOT" "$OFF" "$BASH_CALL" 2 "BLOCKED" ""
run "block names the officer and the effective cap" \
  "$CAP75_ROOT" "$OFF" "$BASH_CALL" 2 "officer=$OFF today=\$76.00 cap=\$75.00" ""
run "block stderr names the override path" \
  "$CAP75_ROOT" "$OFF" "$BASH_CALL" 2 "platform.yml" ""
set_cost "$OFF" 50
run "officer under \$75 cap → allow" \
  "$CAP75_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"

echo ""
echo "-- Contract d: framework defaults fall through when platform.yml is silent --"
# platform.yml omits both caps entirely; the $75 floor must come from
# framework/defaults/spending-limits.yml. A fall-through that quietly
# resolved to 0 would leave a forker with no ceiling at all.
make_root fallthrough - -; FALLTHRU_ROOT="$ROOT_OUT"
clear_costs
set_cost "$OFF" 76
run "platform.yml silent → framework \$75 default blocks" \
  "$FALLTHRU_ROOT" "$OFF" "$BASH_CALL" 2 "cap=\$75.00" ""
set_cost "$OFF" 50
run "platform.yml silent → under the framework default, allow" \
  "$FALLTHRU_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"

echo ""
echo "-- Contract c: CoS 3x multiplier --"
# cos at $76 with per_off_cap=$75 would normally block, but 3x → effective $225.
clear_costs
set_cost "cos" 76
run "cos at \$76 with 3x → allow (effective cap \$225)" \
  "$CAP75_ROOT" "cos" "$BASH_CALL" 0 "" "BLOCKED"
set_cost "cos" 226
run "cos at \$226 with 3x → block at the multiplied cap" \
  "$CAP75_ROOT" "cos" "$BASH_CALL" 2 "cap=\$225.00" ""
run "cos block mentions the coordinator multiplier" \
  "$CAP75_ROOT" "cos" "$BASH_CALL" 2 "coordinator multiplier" ""
# The carve-out must be CoS-only: the same $226 for a plain officer blocks at
# the unmultiplied cap.
clear_costs
set_cost "$OFF" 226
run "a non-cos officer gets no multiplier at \$226" \
  "$CAP75_ROOT" "$OFF" "$BASH_CALL" 2 "cap=\$75.00" "coordinator multiplier"

# ---------------------------------------------------------------------------
# Group 3 — the CABINET-WIDE gate, genuinely reached.
# The old arm set the per-officer cap in a cache the hook ignored, so it
# exited 2 off the PER-OFFICER gate: right exit code, wrong gate. Asserting
# only the exit code would have been a FALSE GREEN. Both arms below therefore
# require the distinguishing "cabinet-wide" wording AND forbid the per-officer
# wording, and the per-officer cap is arranged so it CANNOT fire first (once
# disabled, once enabled but far above the spend).
# ---------------------------------------------------------------------------
echo ""
echo "-- Contract a: cabinet-wide cap, per-officer unable to short-circuit --"
make_root cabonly 0 1000; CABONLY_ROOT="$ROOT_OUT"
clear_costs
set_cost "$OFF" 600
set_cost "$PEER" 600
run "cabinet-wide \$1200 > \$1000, per-officer OFF → cabinet-wide block" \
  "$CABONLY_ROOT" "$OFF" "$BASH_CALL" 2 "BLOCKED — cabinet-wide today=\$1200.00" "officer=$OFF"

make_root cabhigh 5000 1000; CABHIGH_ROOT="$ROOT_OUT"
run "cabinet-wide \$1200 > \$1000, per-officer \$5000 (unreached) → cabinet-wide block" \
  "$CABHIGH_ROOT" "$OFF" "$BASH_CALL" 2 "BLOCKED — cabinet-wide today=\$1200.00" "officer=$OFF"
run "the cabinet-wide block names its own override key" \
  "$CABHIGH_ROOT" "$OFF" "$BASH_CALL" 2 "daily_cabinet_wide_usd" ""

make_root cabroom 0 2000; CABROOM_ROOT="$ROOT_OUT"
run "cabinet-wide \$1200 under a \$2000 cap → allow" \
  "$CABROOM_ROOT" "$OFF" "$BASH_CALL" 0 "" "BLOCKED"

# ---------------------------------------------------------------------------
# Group 4 — contract (b): the Telegram door stays open for a capped officer.
# ---------------------------------------------------------------------------
echo ""
echo "-- Contract b: the Telegram whitelist bypasses the cap --"
clear_costs
clear_tg_buckets
set_cost "$OFF" 76
run "over-cap officer can still Telegram reply" \
  "$CAP75_ROOT" "$OFF" "$TG_REPLY" 0 "" "BLOCKED"
run "over-cap officer can still Telegram react" \
  "$CAP75_ROOT" "$OFF" "$TG_REACT" 0 "" "BLOCKED"
run "over-cap officer can still send-to-group.sh" \
  "$CAP75_ROOT" "$OFF" \
  "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash $REAL_ROOT/cabinet/scripts/send-to-group.sh hi\"}}" \
  0 "" "BLOCKED"
# The bypass must be NARROW: a non-whitelisted Telegram tool is still capped.
# (The spend gate runs before the section-9 MCP-scope gate, so the block that
# fires here is the spend one — asserted by its wording.)
run "a non-whitelisted MCP tool is still capped" \
  "$CAP75_ROOT" "$OFF" "$NON_TG_MCP" 2 "BLOCKED — officer=$OFF" ""

echo ""
echo "-- Contract b: the whitelist has an hourly sub-cap --"
# platform.yml sets the sub-cap to 3 (also proving contract (d) over a
# non-cap key), so the 4th whitelisted call in the hour must be refused —
# otherwise an over-cap officer could loop the door forever.
make_root tg3 75 0 3.0 3; TG3_ROOT="$ROOT_OUT"
clear_tg_buckets
set_cost "$OFF" 76
run "whitelisted call 1 of 3 → allow" "$TG3_ROOT" "$OFF" "$TG_REPLY" 0 "" "BLOCKED"
run "whitelisted call 2 of 3 → allow" "$TG3_ROOT" "$OFF" "$TG_REPLY" 0 "" "BLOCKED"
run "whitelisted call 3 of 3 → allow" "$TG3_ROOT" "$OFF" "$TG_REPLY" 0 "" "BLOCKED"
run "whitelisted call 4 → hourly sub-cap blocks" \
  "$TG3_ROOT" "$OFF" "$TG_REPLY" 2 "hourly sub-cap exceeded" ""

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  printf "%b\n" "$FAIL_DETAILS"
  exit 1
fi
exit 0
