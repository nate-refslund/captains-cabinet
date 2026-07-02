#!/bin/bash
# cabinet/scripts/meta-cognition/anomaly-scan.sh — LAYER 2 (DETECT) telemetry reader
#
# The deterministic half of anomaly-seeking (the judgment lives in the retro's
# first phase, memory/skills/cross-officer-retro.md). This script reads the
# already-emitted telemetry streams and prints a compact, factual snapshot the
# CoS can compare against what it would predict — "what violates what I'd
# predict?" It does NOT decide what is anomalous and it NEVER pings: it surfaces
# measured numbers; the CoS applies the CONFIDENCE FLOOR and only graduates a
# surprise that implies a testable hypothesis or a probable defect.
#
# Streams read (all already emitted — adds NO always-loaded loop):
#   * memory/logs/<date>.jsonl        — per-officer tool-call volume + repeated
#                                        identical tool calls (stuck-loop signal)
#   * cabinet/logs/hook-fires/*.jsonl — hook fire counts (storm / dead-gate)
#   * Redis cabinet:reflections:count — reflection cadence
#   * Redis cabinet:cost:tokens:daily:* + cabinet:cost:officer:* — spend
#   * Redis cabinet:schedule:last-run:* — overdue scheduled tasks
#
# Usage:
#   bash anomaly-scan.sh            # human-readable telemetry snapshot
#   bash anomaly-scan.sh --json     # JSON (for programmatic retro use)
#   ANOMALY_WINDOW_DAYS=2 ...       # how many days of JSONL logs to read (default 2)
#
# Secrets: NONE (cost values are token COUNTS, never keys). No network beyond
# local Redis. Read-only. Exit 0 always when readable.

set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
. "$SELF_DIR/lib.sh"

WINDOW_DAYS="${ANOMALY_WINDOW_DAYS:-2}"
LOG_DIR="$MC_REPO_ROOT/memory/logs"
HOOK_DIR="$MC_REPO_ROOT/cabinet/logs/hook-fires"
JSON_OUT=0
[ "${1:-}" = "--json" ] && JSON_OUT=1

RH="$MC_REDIS_HOST"; RP="$MC_REDIS_PORT"
redis_get() { command -v redis-cli >/dev/null 2>&1 && redis-cli -h "$RH" -p "$RP" GET "$1" 2>/dev/null || true; }
redis_keys() { command -v redis-cli >/dev/null 2>&1 && redis-cli -h "$RH" -p "$RP" KEYS "$1" 2>/dev/null || true; }

# Collect the JSONL log files in the window (today + WINDOW_DAYS-1 back).
log_files() {
  local i f
  for ((i=0; i<WINDOW_DAYS; i++)); do
    if date -v-"${i}"d >/dev/null 2>&1; then
      f="$LOG_DIR/$(date -u -v-"${i}"d +%Y-%m-%d).jsonl"   # BSD/macOS date
    else
      f="$LOG_DIR/$(date -u -d "-${i} day" +%Y-%m-%d).jsonl" # GNU date
    fi
    [ -f "$f" ] && echo "$f"
  done
}

# Build the whole snapshot in python (robust JSONL parse + aggregation), fed the
# log file list + redis-sourced values via env/argv.
FILES="$(log_files | tr '\n' ' ')"
REFLECTIONS="$(redis_get cabinet:reflections:count)"
SCHED_KEYS="$(redis_keys 'cabinet:schedule:last-run:*' | tr '\n' ' ')"
COST_KEYS="$(redis_keys 'cabinet:cost:officer:*' | tr '\n' ' ')"

# Pull last-run timestamps + cost values for the keys (so python can compute
# overdue / divergence without its own redis access).
SCHED_PAIRS=""
for k in $SCHED_KEYS; do
  v="$(redis_get "$k")"
  [ -n "$v" ] && SCHED_PAIRS="${SCHED_PAIRS}${k}=${v}"$'\n'
done
COST_PAIRS=""
for k in $COST_KEYS; do
  v="$(redis_get "$k")"
  [ -n "$v" ] && COST_PAIRS="${COST_PAIRS}${k}=${v}"$'\n'
done

HOOK_FILES="$(ls "$HOOK_DIR"/*.jsonl 2>/dev/null | tr '\n' ' ')"

export ANOM_FILES="$FILES"
export ANOM_HOOK_FILES="$HOOK_FILES"
export ANOM_REFLECTIONS="$REFLECTIONS"
export ANOM_SCHED_PAIRS="$SCHED_PAIRS"
export ANOM_COST_PAIRS="$COST_PAIRS"
export ANOM_JSON="$JSON_OUT"

python3 "$SELF_DIR/anomaly_report.py"
