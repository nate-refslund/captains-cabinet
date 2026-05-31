#!/usr/bin/env bash
# stagehand-runner.sh — Spec 049 Gate-4 visual-UAT runner (outer shell layer).
#
# Responsibilities:
#   1. Page-list allowlist gate (page-allowlist.sh AC #15 M3).
#   2. Semaphore acquire (visual-uat-semaphore.sh AC #13 M2).
#   3. Compute gate4BuildHash at loop START (cache-hash.sh AC #14, MF-4).
#   4. Invoke the Node entrypoint (stagehand-runner.js) for per-page loop,
#      vision-fallback cost accounting, and state-file writes.
#   5. Re-check gate4BuildHash at loop END — mismatch → discard + re-run the
#      whole gate (build-atomic guarantee JF-2 / MF-4). Spent cost counts.
#   6. Semaphore release on exit (including on error / SIGTERM).
#   7. Emit the JSONL audit record to visual-uat-cost.jsonl (ARCH-5 A11-log).
#
# MF-5 permit placement — this is the KEY discipline:
#   - Permit is RELEASED by the Node entrypoint during the AC#4 preview-
#     availability poll (unbounded network wait).
#   - Permit is RELEASED by the Node entrypoint during any cost-cap officer-
#     decision wait (unbounded human-latency).
#   - The Node entrypoint re-acquires on resume for each of the above.
#   - This shell wrapper holds the initial acquire and the final release.
#   The Node entrypoint calls back to shell primitives for acquire/release via
#   $STAGEHAND_RUNNER_SEM_KEY and $STAGEHAND_RUNNER_SEM_OWNER env vars.
#
# Build-atomic (JF-2 / MF-4):
#   gate4BuildHash computed HERE (start), Node persists it to state file,
#   THIS script re-checks at end. Mismatch → Node is told to discard + full
#   re-run from scratch (re-invokes itself); spent cost on the aborted run
#   still counts toward the cap.
#
# Fail-safe discipline (Spec 049 build-wide principle):
#   Missing lib / Stagehand / config → log + exit INDETERMINATE (99),
#   NEVER FAIL (exit 1) or false-PASS (exit 0).
#
# Exit codes (callers key on these):
#   0   = PASS
#   1   = FAIL (real visual defect confirmed)
#   2   = BLOCK (cost-cap — officer must bump or split task)
#   3   = INDETERMINATE (infra not ready / first-iteration missing preview)
#   4   = INDETERMINATE-BUDGET (FW-002 cabinet daily cap blocked mid-run)
#   5   = INDETERMINATE-CONCURRENCY-STARVATION (all permits held, timed out)
#   99  = runner setup error (missing dep / config; treated as INDETERMINATE)
#
# Usage:
#   stagehand-runner.sh \
#     --state   <path/to/.claude/active-task.json> \
#     --origin  <https://preview-xxx.vercel.app> \
#     --pages   </page1,/page2,...>  \
#     --cache-mode <nextjs|git-deps|custom> \
#     --project-root <path> \
#     [--cache-paths <dir1,dir2,...>] \
#     [--allowlist  <glob1,glob2,...>] \
#     [--max-slots  <N>]              (default 2) \
#     [--lock-timeout <s>]            (default 180) \
#     [--iteration  <N>]              (1=first; default 1)
#
# Environment (all optional — framework defaults apply):
#   CABINET_ROOT        framework root (default /opt/founders-cabinet)
#   STAGEHAND_ROOT      Stagehand install dir
#   WORKSPACE_ROOT      project workspaces root
#   ANTHROPIC_API_KEY   required for vision-fallback (Opus 4.7)
#   REDIS_HOST / REDIS_PORT
#   OFFICER / OFFICER_NAME
#   VUAT_SEM_PREFIX     (hermetic testing — overrides semaphore key prefix)
#   CONVENTIONAL_COMMIT_LOG  (not used here; present for env completeness)
#   VISUAL_UAT_COST_LOG override for the JSONL audit log path
#   VISUAL_UAT_DRY_RUN  set to 1 to skip Stagehand + emit fake results (tests)
#   STAGEHAND_RUNNER_FORCE_PREVIEW_DOWN  set to 1 to force preview-unavailable (F21 test)
#   S49_RERUN           re-run counter (incremented at boot, exported across exec)
#
# NEVER hardcode framework/workspace paths. All paths via env + CABINET_ROOT.
set -euo pipefail

# F2 — re-run cap: prevent unbounded re-exec livelock on build-hash instability.
# S49_RERUN is exported across re-invocations so the counter survives exec "$0".
S49_RERUN=$(( ${S49_RERUN:-0} + 1 ))
export S49_RERUN

# ─────────────────────────────────────────────────────────────────────────────
# 0. Boot constants (no hardcodes)
# ─────────────────────────────────────────────────────────────────────────────
CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
STAGEHAND_ROOT="${STAGEHAND_ROOT:-${CABINET_ROOT}/cabinet/tools/stagehand}"
LIB="${CABINET_ROOT}/cabinet/scripts/lib"
SCRIPTS="${CABINET_ROOT}/cabinet/scripts"
RUNNER_JS="${CABINET_ROOT}/cabinet/scripts/visual-uat/stagehand-runner.js"
COST_LOG="${VISUAL_UAT_COST_LOG:-${CABINET_ROOT}/cabinet/logs/visual-uat-cost.jsonl}"
OFFICER="${OFFICER:-${OFFICER_NAME:-unknown}}"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Exit codes (symbolic)
# ─────────────────────────────────────────────────────────────────────────────
EXIT_PASS=0
EXIT_FAIL=1
EXIT_BLOCK=2
EXIT_INDETERMINATE=3
EXIT_INDETERMINATE_BUDGET=4
EXIT_INDETERMINATE_STARVATION=5
EXIT_SETUP_ERROR=99

_fatal() { echo "stagehand-runner: FATAL: $*" >&2; exit $EXIT_SETUP_ERROR; }
_warn()  { echo "stagehand-runner: WARN: $*" >&2; }

# ─────────────────────────────────────────────────────────────────────────────
# 2. Parse args
# ─────────────────────────────────────────────────────────────────────────────
STATE_FILE=""
ORIGIN=""
PAGES_CSV=""
CACHE_MODE="nextjs"
PROJECT_ROOT=""
CACHE_PATHS_CSV=""
ALLOWLIST_CSV=""
MAX_SLOTS=2
LOCK_TIMEOUT=180
ITERATION=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --state)         STATE_FILE="$2";       shift 2 ;;
    --origin)        ORIGIN="$2";           shift 2 ;;
    --pages)         PAGES_CSV="$2";        shift 2 ;;
    --cache-mode)    CACHE_MODE="$2";       shift 2 ;;
    --project-root)  PROJECT_ROOT="$2";     shift 2 ;;
    --cache-paths)   CACHE_PATHS_CSV="$2";  shift 2 ;;
    --allowlist)     ALLOWLIST_CSV="$2";    shift 2 ;;
    --max-slots)     MAX_SLOTS="$2";        shift 2 ;;
    --lock-timeout)  LOCK_TIMEOUT="$2";     shift 2 ;;
    --iteration)     ITERATION="$2";        shift 2 ;;
    *) _fatal "unknown arg: $1" ;;
  esac
done

# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate required args
# ─────────────────────────────────────────────────────────────────────────────
[ -n "$STATE_FILE" ]   || _fatal "--state required"
[ -n "$ORIGIN" ]       || _fatal "--origin required"
[ -n "$PAGES_CSV" ]    || _fatal "--pages required"
[ -n "$PROJECT_ROOT" ] || _fatal "--project-root required"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Dependency checks (fail-safe: missing dep → INDETERMINATE, not FAIL)
# ─────────────────────────────────────────────────────────────────────────────
_check_dep() {
  local name="$1" path="$2"
  if [ ! -f "$path" ] && ! command -v "$name" >/dev/null 2>&1; then
    _warn "dependency missing: $name ($path) — returning INDETERMINATE"
    exit $EXIT_SETUP_ERROR
  fi
}

_check_dep "jq"      "$(command -v jq 2>/dev/null || true)"
_check_dep "node"    "$(command -v node 2>/dev/null || true)"
[ -f "$RUNNER_JS" ]   || { _warn "stagehand-runner.js not found at $RUNNER_JS — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }
[ -d "$STAGEHAND_ROOT" ] || { _warn "STAGEHAND_ROOT=$STAGEHAND_ROOT not found — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }
[ -f "$LIB/page-allowlist.sh" ]        || { _warn "page-allowlist.sh missing — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }
[ -f "$LIB/visual-uat-semaphore.sh" ]  || { _warn "visual-uat-semaphore.sh missing — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }
[ -f "$LIB/cache-hash.sh" ]            || { _warn "cache-hash.sh missing — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }
[ -f "$LIB/model-pricing.sh" ]         || { _warn "model-pricing.sh missing — INDETERMINATE"; exit $EXIT_SETUP_ERROR; }

# Stagehand package must be loadable from STAGEHAND_ROOT.
if ! node --input-type=module \
     <<< "import {Stagehand} from '${STAGEHAND_ROOT}/node_modules/@browserbasehq/stagehand/dist/index.js'; process.exit(0);" \
     >/dev/null 2>&1; then
  # Fallback: try require (CommonJS)
  if ! node -e "require('${STAGEHAND_ROOT}/node_modules/@browserbasehq/stagehand')" >/dev/null 2>&1; then
    _warn "Stagehand v3 not loadable from $STAGEHAND_ROOT — INDETERMINATE"
    exit $EXIT_SETUP_ERROR
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Source leaf libs
# ─────────────────────────────────────────────────────────────────────────────
# shellcheck source=../lib/page-allowlist.sh
source "$LIB/page-allowlist.sh"
# shellcheck source=../lib/visual-uat-semaphore.sh
source "$LIB/visual-uat-semaphore.sh"
# shellcheck source=../lib/cache-hash.sh
source "$LIB/cache-hash.sh"
# shellcheck source=../lib/model-pricing.sh
source "$LIB/model-pricing.sh"

# ─────────────────────────────────────────────────────────────────────────────
# 6. Page-list allowlist gate (AC #15 M3) — before any semaphore or Stagehand
# ─────────────────────────────────────────────────────────────────────────────
EFFECTIVE_ALLOWLIST="${ALLOWLIST_CSV:-$PAGE_ALLOWLIST_DEFAULT}"
# Convert pages CSV to args.
IFS=',' read -r -a PAGES_ARRAY <<< "$PAGES_CSV"
# Filter: page_allowlist_filter prints safe pages on stdout, WARNs rejected to stderr.
# Fail if NO pages survive (can't run Gate 4 with an empty page list).
SAFE_PAGES_NL="$(page_allowlist_filter "$EFFECTIVE_ALLOWLIST" "${PAGES_ARRAY[@]}" 2>&1)" || true
SAFE_PAGES_STDERR="$(page_allowlist_filter "$EFFECTIVE_ALLOWLIST" "${PAGES_ARRAY[@]}" 2>/dev/null)" || true
# Re-run cleanly to separate stdout/stderr:
SAFE_PAGES="$(page_allowlist_filter "$EFFECTIVE_ALLOWLIST" "${PAGES_ARRAY[@]}" 2>/dev/null)" || true

if [ -z "$SAFE_PAGES" ]; then
  _warn "all requested pages rejected by allowlist [$EFFECTIVE_ALLOWLIST] — INDETERMINATE"
  exit $EXIT_INDETERMINATE
fi

# Convert to newline-delimited for the Node entrypoint.
SAFE_PAGES_CSV="$(echo "$SAFE_PAGES" | tr '\n' ',' | sed 's/,$//')"

# ─────────────────────────────────────────────────────────────────────────────
# 7. Compute gate4BuildHash at loop START (MF-4 / JF-2 build-atomic)
# ─────────────────────────────────────────────────────────────────────────────
# Convert cache paths CSV to positional args.
CACHE_PATHS_ARGS=()
if [ -n "$CACHE_PATHS_CSV" ]; then
  IFS=',' read -r -a CACHE_PATHS_ARGS <<< "$CACHE_PATHS_CSV"
fi

START_BUILD_HASH=""
if ! START_BUILD_HASH="$(cache_hash_compute "$CACHE_MODE" "$PROJECT_ROOT" "${CACHE_PATHS_ARGS[@]}" 2>/dev/null)"; then
  _warn "cache_hash_compute failed (mode=$CACHE_MODE) — running without build-atomic guarantee"
  START_BUILD_HASH="UNKNOWN"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 8. Acquire concurrency semaphore (AC #13 M2)
# ─────────────────────────────────────────────────────────────────────────────
# Generate a unique owner token (task-id + officer + PID).
TASK_ID="$(jq -r '.issueId // "unknown"' "$STATE_FILE" 2>/dev/null || echo "unknown")"
SEM_OWNER="${OFFICER}:${TASK_ID}:$$"
SEM_KEY=""

_release_sem() {
  if [ -n "$SEM_KEY" ]; then
    vuat_sem_release "$SEM_KEY" "$SEM_OWNER" 2>/dev/null || true
    SEM_KEY=""
  fi
}
trap '_release_sem' EXIT INT TERM

# Probe Redis availability before entering the semaphore-acquire loop.
# Fail-open: if Redis is unreachable, skip the semaphore entirely (one concurrent
# run is harmless in the non-contended case; the crash-safe TTL handles the
# contended case once Redis recovers). Note the absence of a permit in the log.
_REDIS_AVAILABLE=0
if command -v redis-cli >/dev/null 2>&1; then
  redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" PING >/dev/null 2>&1 && _REDIS_AVAILABLE=1
fi

if [ "$_REDIS_AVAILABLE" -eq 0 ]; then
  _warn "Redis unavailable — skipping concurrency semaphore (fail-open; no starvation protection this run)"
  SEM_KEY=""
else
  # Try to acquire within LOCK_TIMEOUT seconds (poll every 2s).
  _ELAPSED=0
  _POLL=2
  while true; do
    SEM_KEY="$(vuat_sem_acquire "$MAX_SLOTS" "$SEM_OWNER" "$LOCK_TIMEOUT" 2>/dev/null)" && break || true
    if [ "$_ELAPSED" -ge "$LOCK_TIMEOUT" ]; then
      echo "stagehand-runner: INDETERMINATE-CONCURRENCY-STARVATION: all $MAX_SLOTS permits held for ${LOCK_TIMEOUT}s; defer and retry" >&2
      trap - EXIT INT TERM
      exit $EXIT_INDETERMINATE_STARVATION
    fi
    sleep "$_POLL"
    _ELAPSED=$(( _ELAPSED + _POLL ))
  done
fi

# ─────────────────────────────────────────────────────────────────────────────
# 9. Invoke the Node entrypoint
#
# The Node entrypoint handles:
#   - Per-page Stagehand navigation + action-cache
#   - Vision-fallback via Anthropic Opus 4.7 (max 3 retries/page)
#   - visualUatCost accumulation × model-pricing.json (AC #10 C1)
#   - $5 visual sub-cap + $1 vision-fallback budget (AC #10/AC #17)
#   - FW-002 mid-run check (INDETERMINATE-BUDGET)
#   - State-file incremental writes (crash-safe atomic)
#   - MF-5 permit release/re-acquire during AC#4 preview-poll + cost-cap wait
#     (communicated back to this shell via the env vars below)
#   - MF-3 terminal-state precedence (FAIL > BLOCK > INDETERMINATE)
#   - First-iteration INDETERMINATE (CTO #6)
# ─────────────────────────────────────────────────────────────────────────────
NODE_RC=99
NODE_EXIT_JSON=""

# Staleness check (advisory, never blocks).
model_pricing_staleness_check 2>&1 | grep -E "^WARN" >&2 || true

NODE_OUT_FILE="$(mktemp "/tmp/vuat-node-out.XXXXXX")"
trap 'rm -f "$NODE_OUT_FILE"; _release_sem' EXIT INT TERM

# F1: bracket node invocation with set +e / set -e so that a non-zero exit from
# Node does NOT trigger the shell's errexit and kill the script before we reach
# the build-atomic end-check, semaphore release, and JSONL audit emit. Without
# this bracket, FAIL/BLOCK/INDETERMINATE exits from Node cause the shell to die
# at L282 and skip everything below — violating the build-atomic guarantee.
set +e
node "$RUNNER_JS" \
  --state          "$STATE_FILE" \
  --origin         "$ORIGIN" \
  --pages          "$SAFE_PAGES_CSV" \
  --cache-mode     "$CACHE_MODE" \
  --project-root   "$PROJECT_ROOT" \
  --cache-paths    "${CACHE_PATHS_CSV:-}" \
  --iteration      "$ITERATION" \
  --start-build-hash "$START_BUILD_HASH" \
  --sem-key        "$SEM_KEY" \
  --sem-owner      "$SEM_OWNER" \
  --sem-max-slots  "$MAX_SLOTS" \
  --sem-lock-timeout "$LOCK_TIMEOUT" \
  --cost-log       "$COST_LOG" \
  --cabinet-root   "$CABINET_ROOT" \
  --stagehand-root "$STAGEHAND_ROOT" \
  --officer        "$OFFICER" \
  > "$NODE_OUT_FILE" 2>&1
NODE_RC=$?
set -e

# After Node returns, release the semaphore (Node may have released already on
# wait-points, re-acquired, and returned with it held — release here is always
# owner-checked + idempotent).
_release_sem

# ─────────────────────────────────────────────────────────────────────────────
# 10. Build-atomic end-check (JF-2 / MF-4)
# ─────────────────────────────────────────────────────────────────────────────
END_BUILD_HASH=""
END_BUILD_HASH="$(cache_hash_compute "$CACHE_MODE" "$PROJECT_ROOT" "${CACHE_PATHS_ARGS[@]}" 2>/dev/null)" || END_BUILD_HASH="UNKNOWN"

if [ "$START_BUILD_HASH" != "UNKNOWN" ] && [ "$END_BUILD_HASH" != "UNKNOWN" ] && \
   [ "$START_BUILD_HASH" != "$END_BUILD_HASH" ]; then
  echo "stagehand-runner: WARN: build changed mid-run (start=$START_BUILD_HASH end=$END_BUILD_HASH) — discarding partial results + full re-run required (cost spent counts)" >&2

  # F2: re-run cap. Track recursive re-exec count via S49_RERUN (incremented at
  # script top, exported so it survives exec). Cap at 2 re-runs to prevent
  # unbounded livelock on hash-churn (malicious cache-hash.sh, mtime jitter,
  # git-deps ref churn under load). On overrun: write INDETERMINATE to state +
  # emit audit + exit 3 (INDETERMINATE — no state change).
  if [ "$S49_RERUN" -gt 2 ]; then
    echo "stagehand-runner: ERROR: build-instability-after-2-reruns (S49_RERUN=$S49_RERUN); capping to INDETERMINATE" >&2
    if command -v jq >/dev/null 2>&1 && [ -f "$STATE_FILE" ]; then
      TMP_STATE="$(mktemp "${STATE_FILE}.s49capd.XXXXXX")"
      if jq '.STATE.visualUatLastError = "build-instability-after-2-reruns" |
             .selfReviewPassed = false | .selfReviewPassedSha = null |
             .selfReviewPassedAt = null | .gate4BuildHash = null | .checkpointBuildHash = null' \
          "$STATE_FILE" > "$TMP_STATE" 2>/dev/null; then
        mv "$TMP_STATE" "$STATE_FILE"
      else
        rm -f "$TMP_STATE"
        # Fallback write using printf+jq without the nested .STATE path
        jq '.visualUatLastError = "build-instability-after-2-reruns" |
            .selfReviewPassed = false | .selfReviewPassedSha = null |
            .selfReviewPassedAt = null | .gate4BuildHash = null | .checkpointBuildHash = null' \
          "$STATE_FILE" > "${STATE_FILE}.tmp2" 2>/dev/null && mv "${STATE_FILE}.tmp2" "$STATE_FILE" || true
      fi
    fi
    # Emit audit event.
    if command -v jq >/dev/null 2>&1; then
      jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
             --arg officer "$OFFICER" \
             --arg start "$START_BUILD_HASH" \
             --arg end "$END_BUILD_HASH" \
        '{ts:$ts,event:"BUILD_INSTABILITY_CAP",rerun_count:3,start_hash:$start,end_hash:$end,officer:$officer}' \
        >> "$COST_LOG" 2>/dev/null || true
    fi
    # F25: clean tmp file before exit (trap fires on EXIT but make explicit).
    rm -f "$NODE_OUT_FILE" || true
    exit 3
  fi

  # Annotate state file: clear gate4BuildHash + checkpointBuildHash + selfReviewPassed
  # to force a clean re-run. Also null selfReviewPassedAt (F3: was missing).
  if command -v jq >/dev/null 2>&1 && [ -f "$STATE_FILE" ]; then
    TMP_STATE="$(mktemp "${STATE_FILE}.s49reset.XXXXXX")"
    if jq '.gate4BuildHash=null | .checkpointBuildHash=null | .selfReviewPassed=false |
           .selfReviewPassedSha=null | .selfReviewPassedAt=null' \
        "$STATE_FILE" > "$TMP_STATE" 2>/dev/null; then
      mv "$TMP_STATE" "$STATE_FILE"
    else
      rm -f "$TMP_STATE"
    fi
  fi

  # F3: emit BUILD_MISMATCH_DISCARDED audit event to visual-uat-cost.jsonl.
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
           --arg officer "$OFFICER" \
           --arg start "$START_BUILD_HASH" \
           --arg end "$END_BUILD_HASH" \
           --argjson rerun "$S49_RERUN" \
      '{ts:$ts,event:"BUILD_MISMATCH_DISCARDED",rerun_n:$rerun,start_hash:$start,end_hash:$end,officer:$officer}' \
      >> "$COST_LOG" 2>/dev/null || true
  fi

  # F25: clean the NODE_OUT_FILE tmpfile BEFORE exec. exec() destroys the EXIT
  # trap, so the 'rm -f "$NODE_OUT_FILE"' trap installed above will NOT fire on
  # re-exec. Each re-run would otherwise leak a /tmp file.
  rm -f "$NODE_OUT_FILE" || true

  # Re-run: discard current results, re-invoke the gate.
  # Cost spent (already written by Node to state file) is preserved.
  # S49_RERUN is exported so the counter increments correctly on each re-exec.
  exec "$0" \
    --state          "$STATE_FILE" \
    --origin         "$ORIGIN" \
    --pages          "$PAGES_CSV" \
    --cache-mode     "$CACHE_MODE" \
    --project-root   "$PROJECT_ROOT" \
    --cache-paths    "${CACHE_PATHS_CSV:-}" \
    --allowlist      "${ALLOWLIST_CSV:-}" \
    --max-slots      "$MAX_SLOTS" \
    --lock-timeout   "$LOCK_TIMEOUT" \
    --iteration      "$ITERATION"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 11. Forward Node output + exit code
# ─────────────────────────────────────────────────────────────────────────────
cat "$NODE_OUT_FILE" >&2

exit $NODE_RC
