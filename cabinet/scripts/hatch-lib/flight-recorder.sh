# shellcheck shell=bash
# hatch-lib/flight-recorder.sh — flight recorder for hatch.sh (sourced, not run).
#
# The mini-hatch runbook's flight-recorder rule ("wrap the hatch, gate the
# exit") made structural: every step gets a wall-clock timing appended to a
# flight log, plus named stamps (HATCH_START / HATCH_PROOFS_DONE /
# FIRST_RECEIPT_DONE) so TTFR (proofs-done → first-receipt) and total time
# are computed, printed, and auditable afterwards.
#
# Log layout (all under $HATCH_LOG_DIR):
#   flight.log        epoch-stamped STEP_BEGIN / STEP_END / STAMP lines
#   step-<id>.log     full stdout+stderr of each step
#
# NO values ever land here — commands, step names, timings, exit codes only
# (names-in-files doctrine; secrets stay in cabinet/.env).
#
# Bash 3.2-compatible on purpose (macOS /bin/bash): indexed arrays +
# printf -v only — no declare -A, no ${var,,}, no mapfile.

# ---- state (initialized by flight_init) -------------------------------------
HATCH_LOG_DIR=""
HATCH_FLIGHT_LOG=""
FLIGHT_STEP_IDS=()
FLIGHT_STEP_STATUS=()
FLIGHT_STEP_SECS=()

# flight_init <log_dir> <flight_log_path>
flight_init() {
  HATCH_LOG_DIR="$1"
  HATCH_FLIGHT_LOG="$2"
  mkdir -p "$HATCH_LOG_DIR"
  : >> "$HATCH_FLIGHT_LOG"
  flight_line "FLIGHT_OPEN pid=$$ log_dir=$HATCH_LOG_DIR"
}

# flight_line <text...> — one epoch-stamped line into the flight log
flight_line() {
  printf '%s %s %s\n' "$(date +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    >> "$HATCH_FLIGHT_LOG"
}

# flight_stamp <NAME> — named stamp (valid identifier chars only), stored for
# later delta math and appended to the flight log.
flight_stamp() {
  local name="$1" now
  now="$(date +%s)"
  printf -v "FLIGHT_STAMP_${name}" '%s' "$now"
  flight_line "STAMP ${name}"
}

# flight_stamp_get <NAME> — echo the epoch for a stamp, empty if never set
flight_stamp_get() {
  local var="FLIGHT_STAMP_$1"
  printf '%s' "${!var:-}"
}

# flight_step_begin <id> <desc>
flight_step_begin() {
  flight_line "STEP_BEGIN [$1] $2"
}

# flight_step_end <id> <ok|fail|skip> <seconds>
flight_step_end() {
  FLIGHT_STEP_IDS[${#FLIGHT_STEP_IDS[@]}]="$1"
  FLIGHT_STEP_STATUS[${#FLIGHT_STEP_STATUS[@]}]="$2"
  FLIGHT_STEP_SECS[${#FLIGHT_STEP_SECS[@]}]="$3"
  flight_line "STEP_END [$1] status=$2 dur=${3}s"
}

# flight_summary — the printed summary table + stamps + TTFR/total.
# Safe to call at any point (failure paths included).
flight_summary() {
  local i=0 start proofs receipt now total
  echo ""
  echo "---- FLIGHT SUMMARY -------------------------------------------"
  printf '%-24s %-6s %10s\n' "STEP" "STATUS" "SECONDS"
  while [ "$i" -lt "${#FLIGHT_STEP_IDS[@]}" ]; do
    printf '%-24s %-6s %10s\n' \
      "${FLIGHT_STEP_IDS[$i]}" "${FLIGHT_STEP_STATUS[$i]}" "${FLIGHT_STEP_SECS[$i]}"
    i=$((i + 1))
  done
  start="$(flight_stamp_get HATCH_START)"
  proofs="$(flight_stamp_get HATCH_PROOFS_DONE)"
  receipt="$(flight_stamp_get FIRST_RECEIPT_DONE)"
  now="$(date +%s)"
  echo ""
  [ -n "$start" ]   && echo "HATCH_START         $(date -u -r "$start"   +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "@$start")"
  [ -n "$proofs" ]  && echo "HATCH_PROOFS_DONE   $(date -u -r "$proofs"  +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "@$proofs")"
  [ -n "$receipt" ] && echo "FIRST_RECEIPT_DONE  $(date -u -r "$receipt" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "@$receipt")"
  if [ -n "$proofs" ] && [ -n "$receipt" ]; then
    echo "TTFR (proofs-done -> first-receipt): $((receipt - proofs))s"
  else
    echo "TTFR: not reached (needs both HATCH_PROOFS_DONE and FIRST_RECEIPT_DONE)"
  fi
  if [ -n "$start" ]; then
    total=$((now - start))
    echo "TOTAL (hatch-start -> now):          ${total}s"
    flight_line "TOTAL dur=${total}s"
  fi
  echo "Flight log: $HATCH_FLIGHT_LOG"
  echo "----------------------------------------------------------------"
}
