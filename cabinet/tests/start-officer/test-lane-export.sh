#!/bin/bash
# test-lane-export.sh — T4 (Design §3 FIX-4): CABINET_LANE export contract.
#
# resolve_lane() (framework/authority/lane.py) reads CABINET_LANE FIRST, then
# PROJECT, then None — it is the single source of truth for the lane dimension
# of the F+A cell tuple (officer, lane, action_type). For per-lane bars and the
# instance lane→risk-class bindings to work, the officer-start scripts MUST
# export CABINET_LANE derived from the SAME --project / active-context machinery
# that scopes the session. This test pins that contract.
#
# Asserts (Linux start-officer.sh, via CABINET_TEST_DRY_RUN=1):
#   - pool mode (--project sensed) exports CABINET_LANE=sensed in EXPORT_VARS
#   - CABINET_LANE matches CABINET_ACTIVE_PROJECT (same machinery, one source)
#   - legacy mode (no active-project.txt) does NOT leak a CABINET_LANE export
#     (so resolve_lane falls through to PROJECT/None — fail-safe to unmeasured)
#   - a poisoned CABINET_LANE=... in legacy mode is scrubbed (defensive unset)
#
# Run: bash cabinet/tests/start-officer/test-lane-export.sh

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCRIPT="$ROOT/cabinet/scripts/start-officer.sh"

PASS=0
FAIL=0
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }

export TELEGRAM_CTO_TOKEN="x-test-token"
export TELEGRAM_HQ_CHAT_ID="x-test-chat"
export CABINET_TEST_DRY_RUN=1
# Point the script at THIS repo so it resolves load-preset.sh + cabinet/env/<slug>.env
# (the default /opt/founders-cabinet is the deployment path, absent in dev).
export CABINET_ROOT="$ROOT"
# Portability: the script's bot-token lookup uses bash-4 case-upper (${OFFICER^^}).
# CI runs bash 5 (ubuntu-latest) where TELEGRAM_CTO_TOKEN resolves. On a bash-3.2
# host (e.g. stock macOS dev) ${OFFICER^^} degrades to the empty string, so the
# token var name becomes TELEGRAM__TOKEN — set it too so the script still reaches
# the dry-run gate locally. This is a harness accommodation only; the EXPORT_VARS
# assertions below are identical under both bash versions.
export TELEGRAM__TOKEN="x-test-token-bash32-fallback"

# ----------------------------------------------------------------------------
# L1: Pool mode exports CABINET_LANE=<slug> (derived from --project).
# ----------------------------------------------------------------------------
output=$(bash "$SCRIPT" cto --project sensed 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  fail "L1: pool mode exited rc=$rc — $output"
else
  if echo "$output" | grep -q 'CABINET_LANE=sensed'; then
    pass "L1: pool mode exports CABINET_LANE=sensed (resolve_lane's load-bearing source)"
  else
    fail "L1: pool mode missing CABINET_LANE=sensed export — $(echo "$output" | grep '^EXPORT_VARS=')"
  fi
  # The lane MUST be derived from the same machinery as CABINET_ACTIVE_PROJECT.
  if echo "$output" | grep -q 'CABINET_ACTIVE_PROJECT=sensed' \
    && echo "$output" | grep -q 'CABINET_LANE=sensed'; then
    pass "L1b: CABINET_LANE tracks CABINET_ACTIVE_PROJECT (one source of truth)"
  else
    fail "L1b: CABINET_LANE/CABINET_ACTIVE_PROJECT diverged"
  fi
fi

# ----------------------------------------------------------------------------
# L2: Legacy mode (no active-project.txt → empty ACTIVE_SLUG) does NOT export
#     CABINET_LANE. An empty lane export would shadow PROJECT in resolve_lane;
#     omitting it lets resolve_lane fall through to PROJECT then None (fail-safe).
# ----------------------------------------------------------------------------
output=$(bash "$SCRIPT" cto 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  fail "L2: legacy mode exited rc=$rc — $output"
elif echo "$output" | grep -q 'CABINET_LANE'; then
  fail "L2: legacy mode (no slug) LEAKED a CABINET_LANE export — $(echo "$output" | grep '^EXPORT_VARS=')"
else
  pass "L2: legacy mode without a slug does not export CABINET_LANE (fail-safe fall-through)"
fi

# ----------------------------------------------------------------------------
# L3: Defensive unset — a poisoned CABINET_LANE from a sourced env/shell must
#     NOT leak into EXPORT_VARS in legacy mode (mirrors the FW-072
#     CABINET_ACTIVE_PROJECT scrub).
# ----------------------------------------------------------------------------
output=$(CABINET_LANE=poisoned bash "$SCRIPT" cto 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  fail "L3: poisoned legacy invocation exited rc=$rc"
elif echo "$output" | grep -q 'CABINET_LANE'; then
  fail "L3: poisoned CABINET_LANE LEAKED into EXPORT_VARS — defensive unset missing"
else
  pass "L3: poisoned CABINET_LANE scrubbed in legacy mode (defensive unset held)"
fi

echo
echo "=========================================="
echo "T4 CABINET_LANE export: PASS=$PASS  FAIL=$FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ]
