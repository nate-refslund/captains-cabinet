#!/bin/bash
# runner-vocabulary.sh — the harness that watches the watcher.
#
# run-hook-regression.sh only ever sees a harness fail if that harness speaks a
# shape the runner's failure vocabulary matches. fw043-adversary.sh and
# fw045-pass7-adversary.sh emitted **FAIL-N**, which matched none of the
# runner's alternatives, and both ended on a bare echo so their exit code was 0
# whatever the probes did. With tolerance 0 the runner's pass test was
# 0 <= 0 && 0 <= 0: two adversary suites reporting green while checking
# nothing, for as long as they existed. Nothing was watching the vocabulary
# itself, so nothing could notice.
#
# This pins it. The regexes under test are the RUNNER'S OWN, sourced in library
# mode rather than restated here — a copy would drift and re-open the same hole
# from the other side. Every case below is a shape some harness in this
# directory actually emits, or a piece of prose one of them prints that must
# NOT be mistaken for a verdict.
#
# Note on this file's own output: it prints its expectations lower-cased on
# purpose. A harness that shouts FAIL while passing would trip the very regex
# it is testing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="$REPO_ROOT/cabinet/scripts/run-hook-regression.sh"

PASS=0; FAIL=0

if [ ! -f "$RUNNER" ]; then
  printf '  [FAIL] %s\n' "runner not found at $RUNNER"
  echo "=== Summary: PASS=0  FAIL=1 ==="
  exit 1
fi

# Library mode: hands over FAIL_LINE_RE / VERDICT_LINE_RE / classify_harness
# and returns before the suite loop, so sourcing the runner does not run it.
export CABINET_HOOK_REGRESSION_LIB=1
# shellcheck source=../../scripts/run-hook-regression.sh
. "$RUNNER"
unset CABINET_HOOK_REGRESSION_LIB

if ! command -v classify_harness >/dev/null 2>&1; then
  printf '  [FAIL] %s\n' "library mode did not export classify_harness"
  echo "=== Summary: PASS=0  FAIL=1 ==="
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# check <label> <want: pass|fail> <harness-exit-code> <tolerance> <log body>
#       [want-detail: the count or reason after the outcome word]
#
# want-detail is what stops a case passing for the wrong reason: "silence is a
# failure" and "this marker is a failure" both come back as fail, and only the
# detail distinguishes them.
check() {
  local label="$1" want="$2" ec="$3" tolerate="$4" body="$5" want_detail="${6:-}"
  local log="$WORK/probe.log"
  printf '%s' "$body" > "$log"
  local got outcome detail expected
  got="$(classify_harness "$ec" "$log" "$tolerate" | tr '[:upper:]' '[:lower:]')"
  outcome="${got%% *}"
  detail="${got#* }"
  expected="$want"
  [ -n "$want_detail" ] && expected="$want $want_detail"
  if [ "$outcome" = "$want" ] && { [ -z "$want_detail" ] || [ "$detail" = "$want_detail" ]; }; then
    PASS=$((PASS + 1))
    printf '  [PASS] %-42s want=%-14s got=%s\n' "$label" "$expected" "$got"
  else
    FAIL=$((FAIL + 1))
    printf '  [FAIL] %-42s want=%-14s got=%s\n' "$label" "$expected" "$got"
  fi
}

NL=$'\n'
CLEAN_LOG="  [OK] cd-chain   expect=2 got=2${NL}=== Summary: PASS=3  FAIL=0 ===${NL}"

echo "=== A: every failure shape a harness in this directory emits is HEARD ==="
check "reason-tagged marker (fw051, fw043, fw045)" fail 0 0 \
  "  [OK] a${NL}  [FAIL(bypass)] b   expect=2 got=0${NL}" 1
check "false-positive marker" fail 0 0 \
  "  [OK] a${NL}  [FAIL(FP)] b   expect=0 got=2${NL}" 1
check "emphasised dash marker (the defect)" fail 0 0 \
  "  [OK] a${NL}  [**FAIL-0**] b   expect=2 got=0${NL}" 1
check "bare bracketed verdict (fw041, fw042)" fail 0 0 \
  "  [PASS] a${NL}  [FAIL] b: exit=0 (expected=2)${NL}" 1
check "leading-token table row (fw040, germline)" fail 0 0 \
  "PASS   | a | exit=2${NL}FAIL   | b | exit=0${NL}" 1
check "leading-token bracket row (fw040-h6-v2)" fail 0 0 \
  "PASS   [exit=2 expect=BLOCK] a${NL}FAIL   [exit=0 expect=BLOCK] b${NL}" 1
check "counted summary line" fail 0 0 \
  "  [PASS] a${NL}=== Summary: PASS=2  FAIL=3 ===${NL}" 1

echo ""
echo "=== B: the two dead signals — silence and exit code ==="
check "silent harness is not a pass" fail 0 0 \
  "harness died before its first probe${NL}" no-verdict
check "non-zero exit with a clean log" fail 1 0 \
  "$CLEAN_LOG" 0

echo ""
echo "=== C: prose is not a verdict (a green harness must not redden itself) ==="
check "plural prose (fw043 summary)" pass 0 0 \
  "  [OK] a${NL}FAILs indicate bypass (got 0 when expected 2).${NL}" 0
check "legend prose (fw045 summary)" pass 0 0 \
  "  [OK] a${NL}FAIL = bypass (got 0 when expected 2).${NL}" 0
check "section header (captain-exceptions)" pass 0 0 \
  "  [PASS] a${NL}=== FAIL CLOSED: an unreadable list is never ignored ===${NL}" 0
check "zero-count summary" pass 0 0 \
  "PASS   | a | exit=2${NL}=== Summary: PASS=1  FAIL=0 ===${NL}" 0

echo ""
echo "=== D: tolerance still holds (fw051-baseline's accepted-deferred pair) ==="
check "clean log, harness exit 0" pass 0 0 \
  "$CLEAN_LOG" 0
check "two failures inside a tolerance of two" pass 0 2 \
  "  [exit=0 FAIL(FP)] a${NL}  [exit=0 FAIL(bypass)] b${NL}  [exit=2 PASS] c${NL}" 2
check "three failures against a tolerance of two" fail 0 2 \
  "  [exit=0 FAIL(FP)] a${NL}  [exit=0 FAIL(bypass)] b${NL}  [exit=0 FAIL(FP)] c${NL}" 3

echo ""
echo "=== Summary: PASS=$PASS  FAIL=$FAIL ==="
exit "$FAIL"
