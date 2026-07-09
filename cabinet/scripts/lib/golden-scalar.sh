#!/bin/bash
# golden-scalar.sh — Rec 3.4 per-model golden-eval scalar emission (2026-07-09).
#
# Sourced by run-golden-evals.sh; standalone-testable. One function:
#
#   golden_scalar_emit <model> <pass> <fail> <skip> <series_path>
#
# Appends ONE report-only JSONL line {ts, date, model, pass, fail, skip,
# scalar} where scalar = pass/(pass+fail) (null when the suite scored
# nothing). Best-effort: returns non-zero on failure but NEVER exits the
# caller — a failed append must not mask the suite verdict. jq -n builds
# the line safely (the model id is data, never interpolated into code).
# REPORT-ONLY series: nothing may read it as an autonomy gate — that half
# is promotion mechanics and stays defer-captain per D5/CG-10.

golden_scalar_emit() {
  local model="$1" pass="$2" fail="$3" skip="$4" series="$5"
  command -v jq >/dev/null 2>&1 || { echo "WARN: jq unavailable — golden-eval scalar line not emitted" >&2; return 1; }
  case "$pass$fail$skip" in *[!0-9]*) echo "WARN: golden_scalar_emit non-numeric counts ($pass/$fail/$skip)" >&2; return 1 ;; esac
  local scalar
  scalar=$(awk -v p="$pass" -v f="$fail" 'BEGIN{ t=p+f; if (t>0) printf "%.4f", p/t; else print "null" }')
  mkdir -p "$(dirname "$series")" 2>/dev/null
  jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
         --arg date "$(date -u +%Y-%m-%d)" \
         --arg model "$model" \
         --argjson pass "$pass" --argjson fail "$fail" --argjson skip "$skip" \
         --argjson scalar "$scalar" \
         '{ts:$ts, date:$date, model:$model, pass:$pass, fail:$fail, skip:$skip, scalar:$scalar}' \
    >> "$series" 2>/dev/null || { echo "WARN: golden-eval scalar append failed (series untouched; the suite verdict is authoritative)" >&2; return 1; }
}
