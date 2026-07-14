#!/bin/bash
# test-backfill-memory.sh — regression harness for backfill-memory.sh
# (memory-learning-4 + memory-learning-7).
#
# Asserts, with psql/redis-cli mocked via PATH and a throwaway fixture
# CABINET_ROOT (no real DB/redis touched):
#   - experience_records rows are framed as one row_to_json object per line:
#     a multi-line what_happened/lessons_learned queues ONE payload with the
#     full content intact (no shattered/truncated garbage rows)
#   - non-JSON output lines from psql are skipped, not queued
#   - cabinet_research content containing '|' and newlines reaches the
#     insert psql call intact
#   - DATABASE_URL is validated up front (fails fast without it; --files-only
#     still runs without it)
#   - the renamed captains-cabinet-guide.md is what gets queued, and a
#     missing explicitly-listed framework file logs a WARN (unmatched globs
#     stay silent)
#
# Run: bash cabinet/tests/memory/test-backfill-memory.sh

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SCRIPT="$ROOT/cabinet/scripts/backfill-memory.sh"

PASS=0
FAIL=0
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }
pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }

TMP="$(mktemp -d /tmp/backfill-memory-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# --- fixture CABINET_ROOT: real scripts, empty knowledge tree -------------
FIX="$TMP/root"
mkdir -p "$FIX/cabinet"
ln -s "$ROOT/cabinet/scripts" "$FIX/cabinet/scripts"
printf '# fixture CLAUDE.md\nEnough content to queue.\n' > "$FIX/CLAUDE.md"
# captains-cabinet-guide.md deliberately ABSENT -> expect the WARN path.

# --- mocks ------------------------------------------------------------------
MOCK_DIR="$TMP/mock"
mkdir -p "$MOCK_DIR/bin"
export MOCK_DIR

cat > "$MOCK_DIR/bin/psql" <<'MOCK'
#!/bin/bash
args="$*"
case "$args" in
  *experience_records*)
    cat "$MOCK_DIR/exp_rows.txt"
    ;;
  *cabinet_research*)
    cat "$MOCK_DIR/research_rows.txt"
    ;;
  *)
    # NEON insert path: swallow the heredoc SQL, record the argv.
    cat > /dev/null
    printf '%s\n' "INSERT_CALL" >> "$MOCK_DIR/insert.log"
    for a in "$@"; do printf 'ARG:%s\n' "$a" >> "$MOCK_DIR/insert.log"; done
    ;;
esac
exit 0
MOCK

cat > "$MOCK_DIR/bin/redis-cli" <<'MOCK'
#!/bin/bash
# capture the XADD payload (last arg), one line per queued item
printf '%s\n' "${!#}" >> "$MOCK_DIR/xadd.log"
exit 0
MOCK
chmod +x "$MOCK_DIR/bin/psql" "$MOCK_DIR/bin/redis-cli"

# Two valid row_to_json lines (r1 has multi-line columns — the normal case
# that shattered the old -F framing) plus one garbage line psql could never
# emit as a row.
{
  jq -nc '{id:"r1",officer:"cto",task_summary:"Did a thing",outcome:"success",
           what_happened:"line one\nline two\ttabbed",lessons_learned:"L1\nL2",
           created_at:"2026-07-01T10:00:00+00:00",tags:"{alpha,beta}"}'
  echo 'NOT-JSON-GARBAGE'
  jq -nc '{id:"r2",officer:"coo",task_summary:"Second",outcome:"failure",
           what_happened:"single line",lessons_learned:"none",
           created_at:"2026-07-03T11:00:00+00:00",tags:"{}"}'
} > "$MOCK_DIR/exp_rows.txt"

jq -nc '{id:"b1",officer:"cro",title:"T1",
         content:"research line one\nwith | pipe and\nthird line",
         summary:"S1",created_at:"2026-07-02T09:00:00+00:00",
         tags:"{x}",embedding:"[0.1,0.2,0.3]"}' > "$MOCK_DIR/research_rows.txt"

run_script() {
  # hermetic env: caller-set values win in lib/memory.sh, mocks first in PATH
  env PATH="$MOCK_DIR/bin:$PATH" \
      CABINET_ROOT="$FIX" \
      NEON_CONNECTION_STRING="postgres://mock/neon" \
      VOYAGE_API_KEY="x-test" \
      CABINET_ID="test" \
      REDIS_HOST="localhost" REDIS_PORT="6379" \
      "$@"
}

# =============================================================
# 1. Full run — row framing + guide WARN
# =============================================================
OUT="$(run_script DATABASE_URL="postgres://mock/db" bash "$SCRIPT" 2>&1)"
RC=$?
[ "$RC" -eq 0 ] && pass "full run exits 0" || fail "full run exited $RC: $OUT"

XADD_LOG="$MOCK_DIR/xadd.log"
EXP_N=$(grep -c '"source_type":"experience_record"' "$XADD_LOG" 2>/dev/null)
[ "$EXP_N" = "2" ] && pass "exactly 2 experience_record payloads (garbage line skipped)" \
  || { fail "expected 2 experience_record payloads, got ${EXP_N:-0}"; cat "$XADD_LOG" 2>/dev/null; }

echo "$OUT" | grep -q "experience_records: queued 2" \
  && pass "log reports queued 2" || fail "log did not report queued 2: $OUT"

R1=$(grep '"source_id":"exp-r1"' "$XADD_LOG" 2>/dev/null | head -1)
if [ -n "$R1" ]; then
  WANT_CONTENT='[success] Did a thing

line one
line two	tabbed

Lessons: L1
L2'
  GOT_CONTENT=$(printf '%s' "$R1" | jq -r '.content')
  [ "$GOT_CONTENT" = "$WANT_CONTENT" ] \
    && pass "multi-line content intact in one payload" \
    || fail "content mismatch: $(printf '%s' "$R1" | jq -c '.content')"
  [ "$(printf '%s' "$R1" | jq -r '.source_ts')" = "2026-07-01T10:00:00+00:00" ] \
    && pass "source_ts carried from created_at" || fail "wrong source_ts"
  [ "$(printf '%s' "$R1" | jq -r '.metadata.outcome + "/" + .metadata.tags')" = "success/{alpha,beta}" ] \
    && pass "metadata outcome+tags intact" || fail "metadata mismatch"
  [ "$(printf '%s' "$R1" | jq -r '.officer')" = "cto" ] \
    && pass "officer intact" || fail "officer mismatch"
else
  fail "no payload queued for exp-r1"
fi

grep -q 'NOT-JSON' "$XADD_LOG" \
  && fail "garbage line leaked into the queue" || pass "no garbage payloads queued"

# research insert: one call, multi-line/pipe content intact in argv
INS_N=$(grep -c '^INSERT_CALL$' "$MOCK_DIR/insert.log" 2>/dev/null)
[ "$INS_N" = "1" ] && pass "exactly 1 research insert call" \
  || fail "expected 1 research insert call, got ${INS_N:-0}"
grep -q 'content=research line one' "$MOCK_DIR/insert.log" 2>/dev/null \
  && grep -q 'with | pipe and' "$MOCK_DIR/insert.log" 2>/dev/null \
  && grep -q '^third line$' "$MOCK_DIR/insert.log" 2>/dev/null \
  && pass "research content (pipes + newlines) intact" \
  || fail "research content shattered/missing in insert argv"
grep -q 'embedding=\[0.1,0.2,0.3\]' "$MOCK_DIR/insert.log" 2>/dev/null \
  && pass "embedding intact" || fail "embedding missing/corrupted"

# memory-learning-7: renamed guide is WARNed when missing; globs stay silent
echo "$OUT" | grep -q "WARN: listed framework file missing: $FIX/captains-cabinet-guide.md" \
  && pass "WARN for missing captains-cabinet-guide.md" \
  || fail "no WARN for missing guide: $OUT"
echo "$OUT" | grep "WARN: listed framework file missing" | grep -q '\*' \
  && fail "WARN fired for an unmatched glob" || pass "no WARN for unmatched globs"
grep -q '"source_id":"CLAUDE.md"' "$XADD_LOG" \
  && pass "fixture CLAUDE.md queued as framework_file" || fail "CLAUDE.md not queued"

# =============================================================
# 2. DATABASE_URL validated up front
# =============================================================
OUT2="$(run_script bash "$SCRIPT" 2>&1)"
RC2=$?
[ "$RC2" -ne 0 ] && echo "$OUT2" | grep -q "DATABASE_URL" \
  && pass "missing DATABASE_URL fails fast with a named error" \
  || fail "missing DATABASE_URL did not fail fast (rc=$RC2): $OUT2"

: > "$MOCK_DIR/xadd.log"
OUT3="$(run_script bash "$SCRIPT" --files-only 2>&1)"
RC3=$?
[ "$RC3" -eq 0 ] && pass "--files-only runs without DATABASE_URL" \
  || fail "--files-only failed without DATABASE_URL (rc=$RC3): $OUT3"

echo ""
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
