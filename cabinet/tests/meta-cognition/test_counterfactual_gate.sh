#!/bin/bash
# cabinet/tests/meta-cognition/test_counterfactual_gate.sh
#
# Regression + behavior test for the REVERSIBILITY-TIERED counterfactual-replay
# escalation gate in cabinet/scripts/record-experience.sh (block 1b).
#
# Contract under test:
#   - REVERSIBLE tier (CF_REVERSIBLE=1 OR [reversible]/[self-adjust] tag) →
#     proposal emitted at the FIRST occurrence.
#   - DEFAULT/IRREVERSIBLE tier (no signal) → NO proposal at occurrence 1..2;
#     proposal at occurrence 3 (CF_GATE_THRESHOLD default). This is the
#     prior-behavior regression: passing no signal must escalate exactly at >= 3.
#   - CF_GATE_THRESHOLD override is honored.
#
# Hermetic: own MC_PROPOSALS_FILE in a tmpdir, unique slugs per run (epoch+pid)
# so it never collides with live fleet counters, REDIS_HOST=127.0.0.1, no
# DATABASE_URL (file-only), CABINET_ROOT pinned to the repo so block 1b finds
# meta-cognition/lib.sh. Cleans up its redis keys + tmpdir on exit.
#
# Exit 0 = all pass. Skips (exit 0 with SKIP note) if redis-cli is unavailable.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)"
REC="$REPO_ROOT/cabinet/scripts/record-experience.sh"
[ -f "$REC" ] || { echo "FAIL: record-experience.sh not found at $REC"; exit 1; }

RH="${REDIS_HOST:-127.0.0.1}"; RP="${REDIS_PORT:-6379}"
if ! command -v redis-cli >/dev/null 2>&1 || [ "$(redis-cli -h "$RH" -p "$RP" PING 2>/dev/null)" != "PONG" ]; then
  echo "SKIP: redis unavailable at $RH:$RP — gate test needs the counter store."
  exit 0
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/cfgate.XXXXXX")"
PROPOSALS="$TMP/proposals.md"
RUN_TAG="cfgatetest-$(date +%s)-$$"     # unique token → unique slug, no fleet collision
KEYS_TOUCHED=()

cleanup() {
  # delete every counter key this run created (slug derived from RUN_TAG token)
  for k in "${KEYS_TOUCHED[@]:-}"; do
    [ -n "$k" ] && redis-cli -h "$RH" -p "$RP" DEL "$k" >/dev/null 2>&1
  done
  rm -rf "$TMP" 2>/dev/null
}
trap cleanup EXIT

PASS=0; FAIL=0
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# Run record-experience.sh once with a given counterfactual + env. Returns nothing;
# side effects land in $PROPOSALS (async, &-backgrounded in the script — we wait).
emit() {
  local cf="$1"; shift
  # The proposal is emitted in a backgrounded subshell (& + disown). Run the
  # script, then briefly poll the proposals file so the async write can land.
  env -i PATH="$PATH" HOME="$HOME" \
    CABINET_ROOT="$REPO_ROOT" \
    REDIS_HOST="$RH" REDIS_PORT="$RP" \
    MC_PROPOSALS_FILE="$PROPOSALS" \
    OFFICER_NAME=cfgate \
    "$@" \
    bash "$REC" cfgate success "gate test" "what happened" "" "test" "$cf" >/dev/null 2>&1
}

# Count how many proposal lines currently mention a fragment. Always echoes a
# single clean integer (grep -c exits non-zero on 0 matches; we normalize).
proposals_for() {
  local frag="$1" n
  [ -f "$PROPOSALS" ] || { echo 0; return; }
  n="$(grep -c "$frag" "$PROPOSALS" 2>/dev/null)"
  echo "${n:-0}"
}

slug_of() {
  # mirror the script's slug normalization to know which redis key to clean up
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9 ' ' ' | tr -s ' ' \
    | awk '{ for(i=1;i<=NF && i<=8;i++) printf "%s%s", (i>1?"-":""), $i }'
}

wait_for_proposal() {
  # poll up to ~3s for the async proposal write
  local frag="$1" i
  for i in $(seq 1 30); do
    [ "$(proposals_for "$frag")" -ge 1 ] 2>/dev/null && return 0
    sleep 0.1
  done
  return 1
}

echo "=== Counterfactual reversibility-tiered gate ==="

# ---- T1: reversible via CF_REVERSIBLE=1 → fires at occurrence 1 ----
CF1="reverse one ${RUN_TAG} alpha gather context first"
KEYS_TOUCHED+=("cabinet:meta:counterfactual:$(slug_of "$CF1")")
emit "$CF1" CF_REVERSIBLE=1
if wait_for_proposal "Reversible self-adjustment"; then
  ok "T1 CF_REVERSIBLE=1 → proposal at 1st occurrence"
else
  bad "T1 CF_REVERSIBLE=1 → expected proposal at 1st occurrence, none found"
fi

# ---- T2: reversible via [reversible] tag in text → fires at occurrence 1 ----
: > "$PROPOSALS"   # reset proposal file (counter keys differ by slug)
CF2="[reversible] sequence the sweep ${RUN_TAG} bravo differently"
KEYS_TOUCHED+=("cabinet:meta:counterfactual:$(slug_of "$CF2")")
emit "$CF2"
if wait_for_proposal "Reversible self-adjustment"; then
  ok "T2 [reversible] tag → proposal at 1st occurrence"
else
  bad "T2 [reversible] tag → expected proposal at 1st occurrence, none found"
fi

# ---- T3: default/unmarked → NO proposal at 1 or 2; proposal at 3 (regression) ----
: > "$PROPOSALS"
CF3="build a missing tool ${RUN_TAG} charlie for this wall"
KEYS_TOUCHED+=("cabinet:meta:counterfactual:$(slug_of "$CF3")")
emit "$CF3"                       # occurrence 1
sleep 0.3
n1="$(proposals_for "capability gap")"
emit "$CF3"                       # occurrence 2
sleep 0.3
n2="$(proposals_for "capability gap")"
if [ "$n1" -eq 0 ] && [ "$n2" -eq 0 ]; then
  ok "T3a default tier → NO proposal at occurrences 1 and 2 (prior behavior preserved)"
else
  bad "T3a default tier → unexpected proposal before threshold (n1=$n1 n2=$n2)"
fi
emit "$CF3"                       # occurrence 3
if wait_for_proposal "capability gap"; then
  ok "T3b default tier → proposal at 3rd occurrence (>= 3 unchanged)"
else
  bad "T3b default tier → expected proposal at 3rd occurrence, none found"
fi

# ---- T4: CF_GATE_THRESHOLD override honored (default tier, threshold 2 → fires at 2) ----
: > "$PROPOSALS"
CF4="expensive irreversible change ${RUN_TAG} delta needs gating"
KEYS_TOUCHED+=("cabinet:meta:counterfactual:$(slug_of "$CF4")")
emit "$CF4" CF_GATE_THRESHOLD=2   # occurrence 1
sleep 0.3
m1="$(proposals_for "capability gap")"
emit "$CF4" CF_GATE_THRESHOLD=2   # occurrence 2
if [ "$m1" -eq 0 ] && wait_for_proposal "capability gap"; then
  ok "T4 CF_GATE_THRESHOLD=2 → no proposal at 1, proposal at 2"
else
  bad "T4 CF_GATE_THRESHOLD=2 → expected gate at 2 (m1=$m1)"
fi

echo
echo "=== RESULT: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
