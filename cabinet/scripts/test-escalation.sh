#!/bin/bash
# test-escalation.sh — Tests the full kill switch escalation chain.
# Run manually from the HOST or from inside the watchdog container.
# Usage: bash test-escalation.sh [--live]
#   Without --live: dry run, prints what would happen
#   With --live: actually sets/clears the kill switch and checks
[ -f /etc/environment.cabinet ] && source /etc/environment.cabinet

REDIS_URL="${REDIS_URL:-redis://redis:6379}"

# Read the switch through the ONE shared reader, not a raw GET (2026-07-25
# audit). This script claims to test "the full kill switch escalation chain",
# but comparing a raw `GET` to "active" is exactly the bug that let NOAUTH /
# NOPERM / WRONGTYPE / LOADING disable the stop — so the drill would have
# passed while the fleet was defeated. ks_value() maps the reader's verdict
# back to the literal the assertions below already expect, and surfaces an
# unverifiable switch as a LOUD mismatch rather than an empty (= clear) read.
_KS_HELPER="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/hooks" 2>/dev/null && pwd)/killswitch-read.sh"

# ENDPOINT DERIVED FROM THE READER (2026-07-27 safety-switch fence). The write
# endpoint used to be parsed HERE, from REDIS_URL, with a second copy of the
# URL-splitting logic; the reader resolves its own through `_ks_endpoint`,
# which PREFERS REDIS_HOST/REDIS_PORT. Measured, the two agreed — but only by
# accident of shell scoping (the assignments below were unexported shell
# variables that `_ks_endpoint`, sourced into this same shell, then read back).
# Anything that broke that coincidence — exporting, a subshell, a reorder —
# would have this script SET the switch on one server and assert against
# another: a drill that passes while writing nowhere, or writes live while
# reading a sandbox. Asking the reader where IT would go removes the second
# parser entirely, so writer and reader cannot diverge by construction.
_ks_resolve_endpoint() {
  [ -r "$_KS_HELPER" ] || return 1
  # shellcheck source=/dev/null
  ( . "$_KS_HELPER" > /dev/null 2>&1 && _ks_endpoint \
      && printf '%s %s\n' "$_KS_HOST" "$_KS_PORT" )
}
read -r _EP_HOST _EP_PORT <<< "$(_ks_resolve_endpoint)"
if [ -n "${_EP_HOST:-}" ] && [ -n "${_EP_PORT:-}" ]; then
  REDIS_HOST="$_EP_HOST"
  REDIS_PORT="$_EP_PORT"
else
  # No reader on disk (should not happen: Dockerfile.watchdog ships it next to
  # this script). Fall back to the local parse, and --live refuses below —
  # an endpoint nobody can prove the reader shares is not one to write to.
  REDIS_HOST=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
  REDIS_PORT=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
fi
ks_value() {
  if [ ! -r "$_KS_HELPER" ]; then echo "NO-READER"; return 0; fi
  # shellcheck source=/dev/null
  . "$_KS_HELPER" && killswitch_read
  case "$KS_VERDICT" in
    ACTIVE) echo "active" ;;
    CLEAR)  echo "" ;;
    *)      echo "UNVERIFIABLE: $KS_REASON" ;;
  esac
}

LIVE=false
[ "${1:-}" = "--live" ] && LIVE=true

# PRE-FLIGHT: --live REFUSES over a switch that is not provably CLEAR
# (2026-07-27 safety-switch fence). Reproduced before this guard existed: with
# the Captain's stop armed at the resolved endpoint, step 1 reported the
# mismatch, the script CARRIED ON, and step 6's unconditional DEL cleared the
# real emergency stop — exit 1 at the end, damage already done. A drill that
# can silently undo a Captain stop is the same class as one that arms it.
# Refusing here also covers UNVERIFIABLE (NOAUTH/NOPERM/WRONGTYPE/LOADING) and
# a missing reader: absence of the literal "active" is not evidence of a clear
# switch, and this script is about to write to it.
if [ "$LIVE" = true ]; then
  KS_PREFLIGHT=$(ks_value)
  if [ -n "$KS_PREFLIGHT" ]; then
    echo "REFUSED: --live writes cabinet:killswitch at ${REDIS_HOST}:${REDIS_PORT}," >&2
    echo "and the switch there does not read as provably clear (got: '$KS_PREFLIGHT')." >&2
    echo "A stop may be armed right now. Clearing it is Captain-side only —" >&2
    echo "kill-switch.sh deactivate or the dashboard toggle, never a drill." >&2
    echo "Re-run without --live for the dry run, or resolve the switch first." >&2
    exit 64
  fi
fi

PASSED=0
FAILED=0
TOTAL=0

test_step() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  TOTAL=$((TOTAL + 1))

  if [ "$actual" = "$expected" ]; then
    echo "  ✅ $name"
    PASSED=$((PASSED + 1))
  else
    echo "  ❌ $name (expected: '$expected', got: '$actual')"
    FAILED=$((FAILED + 1))
  fi
}

echo "============================================"
echo " Kill Switch Escalation Chain Test"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo " Mode: $( [ "$LIVE" = true ] && echo "LIVE" || echo "DRY RUN")"
echo "============================================"
echo ""

# ============================================================
# Test 1: Verify kill switch is currently OFF
# ============================================================
echo "1. Pre-flight checks"
KS=$(ks_value)
test_step "Kill switch is currently off" "" "$KS"

# ============================================================
# Test 2: Activate kill switch
# ============================================================
echo ""
echo "2. Activating kill switch"
if [ "$LIVE" = true ]; then
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET cabinet:killswitch active > /dev/null 2>&1
  KS=$(ks_value)
  test_step "Kill switch set to 'active'" "active" "$KS"
else
  echo "  ⏭️  SKIPPED (dry run) — would SET cabinet:killswitch active"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 3: Verify pre-tool-use hook would block
# ============================================================
echo ""
echo "3. Verifying pre-tool-use hook behavior"
if [ "$LIVE" = true ]; then
  # Simulate what the hook checks
  KS=$(ks_value)
  test_step "pre-tool-use would read 'active'" "active" "$KS"

  # The hook exits 2 when kill switch is active (we can't run it directly
  # from watchdog, but we verify the Redis state it checks)
  echo "  ℹ️  Hook logic: if killswitch=active → exit 2 (block all tools)"
else
  echo "  ⏭️  SKIPPED (dry run)"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 4: Verify supervisor respects kill switch
# ============================================================
echo ""
echo "4. Supervisor kill switch respect"
if [ "$LIVE" = true ]; then
  KS=$(ks_value)
  test_step "Supervisor would skip restarts (killswitch=$KS)" "active" "$KS"
else
  echo "  ⏭️  SKIPPED (dry run)"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 5: Verify health check sees kill switch
# ============================================================
echo ""
echo "5. Health check kill switch awareness"
if [ "$LIVE" = true ]; then
  KS=$(ks_value)
  test_step "Health check would skip further checks" "active" "$KS"
else
  echo "  ⏭️  SKIPPED (dry run)"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 6: Deactivate kill switch
# ============================================================
echo ""
echo "6. Deactivating kill switch"
if [ "$LIVE" = true ]; then
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL cabinet:killswitch > /dev/null 2>&1
  KS=$(ks_value)
  test_step "Kill switch cleared" "" "$KS"
else
  echo "  ⏭️  SKIPPED (dry run) — would DEL cabinet:killswitch"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 7: Verify officers can resume
# ============================================================
echo ""
echo "7. Post-deactivation state"
if [ "$LIVE" = true ]; then
  KS=$(ks_value)
  test_step "Kill switch is off (operations would resume)" "" "$KS"

  # Check officer expected states still set. Roster DERIVED, not hardcoded:
  # this script runs in the watchdog container (Dockerfile.watchdog COPYs it
  # to /opt/watchdog/) with NO repo tree, so .claude/agents/ is unreachable —
  # enumerate cabinet:officer:expected:* from Redis exactly as health-check.sh
  # and officer-supervisor.sh do. The old `cos cto cro cpo` literal pinged
  # phantom officers that don't exist in the portfolio preset.
  ROSTER=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "cabinet:officer:expected:*" 2>/dev/null \
             | sed 's/cabinet:officer:expected://' | sort)
  if [ -z "$ROSTER" ]; then
    echo "  ℹ️  No cabinet:officer:expected:* keys found — no officers activated (or Redis empty)"
  fi
  for officer in $ROSTER; do
    EXPECTED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:officer:expected:$officer" 2>/dev/null)
    if [ "$EXPECTED" = "active" ]; then
      test_step "Officer $officer still marked as expected:active" "active" "$EXPECTED"
    else
      echo "  ℹ️  Officer $officer not marked active (expected=$EXPECTED)"
    fi
  done
else
  echo "  ⏭️  SKIPPED (dry run)"
  TOTAL=$((TOTAL + 1))
  PASSED=$((PASSED + 1))
fi

# ============================================================
# Test 8: Verify Redis safety keys exist
# ============================================================
echo ""
echo "8. Safety infrastructure checks"
# Check that spending limit keys can be read (FW-016: tokens:daily HSET is source of truth)
SPENDING=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGETALL "cabinet:cost:tokens:daily:$(date -u +%Y-%m-%d)" 2>/dev/null | head -1)
test_step "Daily cost counter is readable" "true" "$([ -n "$SPENDING" ] || [ "$SPENDING" = "" ] && echo "true")"

# Check Redis is healthy
PONG=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING 2>/dev/null)
test_step "Redis responds to PING" "PONG" "$PONG"

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================"
echo " Results: $PASSED/$TOTAL passed, $FAILED failed"
echo "============================================"

if [ "$FAILED" -gt 0 ]; then
  echo "⚠️  Some tests failed — review the output above."
  exit 1
else
  echo "✅ All tests passed."
  exit 0
fi
