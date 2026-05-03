#!/usr/bin/env bash
# MCP process audit — measures the per-Cabinet MCP-process baseline + growth.
# Runs as a one-shot OR a 24h watcher with periodic samples. Output is parseable
# CSV for downstream analysis.
#
# Goal: catch the production failure mode documented in April 2026 GitHub issues
# — MCP processes leaking on session restarts (openclaw #65694/#71110, openai/codex
# #18881 with 492 orphaned processes, agentgateway #1536, ZooClaw 88-process leak).
#
# v3.6 pool architecture math: 15 sessions × 7 stdio MCP servers per cabinet =
# 105 processes per cabinet. 3 cabinets = 315 total. This script tracks reality
# vs that projection and surfaces leaks.
#
# Usage:
#   audit-mcp-processes.sh [--watch <hours>] [--interval <sec>] [--out <file>]
#
#   audit-mcp-processes.sh                    # one-shot snapshot to stdout
#   audit-mcp-processes.sh --watch 24         # 24h watch, default interval 5min
#   audit-mcp-processes.sh --watch 1 --interval 60  # 1h watch every 60s
#   audit-mcp-processes.sh --out /tmp/mcp.csv # write to file instead of stdout

set -euo pipefail

WATCH_HOURS=0
INTERVAL_SEC=300
OUT_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --watch) WATCH_HOURS="$2"; shift 2 ;;
    --interval) INTERVAL_SEC="$2"; shift 2 ;;
    --out) OUT_FILE="$2"; shift 2 ;;
    -h|--help)
      grep "^# " "$0" | sed 's/^# \{0,1\}//' | head -20
      exit 0
      ;;
    *)
      echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

emit() {
  if [ -n "$OUT_FILE" ]; then
    echo "$@" >> "$OUT_FILE"
  else
    echo "$@"
  fi
}

snapshot() {
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  local total
  total=$(ps -eo pid,ppid,rss,etime,comm,args 2>/dev/null \
    | awk 'NR>1 && (tolower($0) ~ /mcp/ || tolower($6) ~ /mcp/) && !/audit-mcp-processes/' \
    | wc -l)

  local total_rss_kb
  total_rss_kb=$(ps -eo pid,ppid,rss,comm,args 2>/dev/null \
    | awk 'NR>1 && (tolower($0) ~ /mcp/) && !/audit-mcp-processes/ { sum += $3 } END { print sum+0 }')

  local orphaned
  orphaned=$(ps -eo pid,ppid,comm,args 2>/dev/null \
    | awk 'NR>1 && (tolower($0) ~ /mcp/) && $2 == 1 && !/audit-mcp-processes/' \
    | wc -l)

  local long_running
  long_running=$(ps -eo etime,comm,args 2>/dev/null \
    | awk 'NR>1 && (tolower($0) ~ /mcp/) && !/audit-mcp-processes/ && ($1 ~ /-/ || $1 ~ /[0-9]+:[0-9]+:[0-9]+/)' \
    | wc -l)

  local total_rss_mb=$(( total_rss_kb / 1024 ))

  emit "${ts},${total},${total_rss_mb},${orphaned},${long_running}"
}

emit_header() {
  emit "timestamp_utc,mcp_process_count,total_rss_mb,orphaned_count,long_running_count"
}

emit_baseline_note() {
  emit "# v3.6 pool baseline projection: 15 sessions x 7 stdio MCP = 105 per cabinet x 3 cabinets = 315 total"
  emit "# Leak signal: orphaned_count > 5 OR long_running_count growing without session uptime growth"
  emit "# RAM signal: total_rss_mb growing >2x baseline over 24h"
}

if [ "$WATCH_HOURS" = "0" ]; then
  emit_baseline_note
  emit_header
  snapshot
  exit 0
fi

emit_baseline_note
emit_header

end_ts=$(( $(date +%s) + WATCH_HOURS * 3600 ))
while [ "$(date +%s)" -lt "$end_ts" ]; do
  snapshot
  sleep "$INTERVAL_SEC"
done
