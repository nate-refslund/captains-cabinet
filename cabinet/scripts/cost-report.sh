#!/bin/bash
# cost-report.sh — Report token costs from Redis (stop-hook data) and/or transcript
# Usage: bash cost-report.sh [--daily] [--session <transcript-path>] [--officer <name>]

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

show_daily=false
show_session=false
TRANSCRIPT=""
OFFICER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --daily) show_daily=true; shift ;;
    --session) show_session=true; TRANSCRIPT="$2"; shift 2 ;;
    --officer) OFFICER="$2"; shift 2 ;;
    *) echo "Usage: $0 [--daily] [--session <path>] [--officer <name>]"; exit 1 ;;
  esac
done

# Default: show both daily and per-officer last turn
if ! $show_daily && ! $show_session; then
  show_daily=true
fi

format_cost() {
  local micro=${1:-0}
  # Convert microdollars to dollars with 2 decimal places using awk for precision
  echo "$micro" | awk '{printf "$%.2f", $1 / 1000000}'
}

if $show_daily; then
  TODAY=$(date -u +%Y-%m-%d)
  echo "=== Daily Cost Report: $TODAY ==="
  echo ""

  DATA=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGETALL "cabinet:cost:tokens:daily:$TODAY" 2>/dev/null)

  if [ -z "$DATA" ]; then
    echo "No cost data for today (stop-hook may not have fired yet)"
  else
    # Parse into associative-like variables
    for officer in cto cos cpo cro coo; do
      if [ -n "$OFFICER" ] && [ "$officer" != "$OFFICER" ]; then continue; fi

      input=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_input" 2>/dev/null)
      output=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_output" 2>/dev/null)
      cw=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_cache_write" 2>/dev/null)
      cr=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_cache_read" 2>/dev/null)
      cost=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_cost_micro" 2>/dev/null)

      input=${input:-0}; output=${output:-0}; cw=${cw:-0}; cr=${cr:-0}; cost=${cost:-0}

      if [ "$input" = "0" ] && [ "$output" = "0" ]; then continue; fi

      echo "$officer:"
      echo "  Input:       $(( input )) tokens"
      echo "  Output:      $(( output )) tokens"
      echo "  Cache write: $(( cw )) tokens"
      echo "  Cache read:  $(( cr )) tokens"
      echo "  Cost:        $(format_cost "$cost")"
      echo ""
    done

    # Sum per-officer costs directly
    total=0
    for officer in cto cos cpo cro coo; do
      oc=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${officer}_cost_micro" 2>/dev/null)
      total=$(( total + ${oc:-0} ))
    done
    echo "TOTAL: $(format_cost "$total")"
  fi
  echo ""
fi

if $show_session && [ -n "$TRANSCRIPT" ]; then
  if [ ! -f "$TRANSCRIPT" ]; then
    echo "Transcript not found: $TRANSCRIPT"
    exit 1
  fi

  echo "=== Session Cost Report ==="
  echo "Transcript: $(basename "$TRANSCRIPT")"
  echo ""

  # PRICING LIVES IN framework/cost/meter.py — NOT HERE (2026-07-27).
  # This report used to carry its own copy of the rate table, and that copy
  # carried the same bug the live meter did: opus cache_write at $3.75/MTok and
  # cache_read at $0.30/MTok, both exactly 5x under the published 1.25x/0.1x of
  # the input rate, with unknown models falling through to the CHEAPEST row.
  # A second copy of a rate table is how the first one survived review for
  # months, so this one is deleted rather than corrected. The meter also dedupes
  # by message.id — this report summed every assistant ENTRY, and the transcript
  # writes one entry per content block, so it over-counted responses while
  # under-pricing cache. Two errors in opposite directions is not an accurate
  # report; it is a number nobody can reason about.
  CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  PYTHONPATH="$CABINET_ROOT" python3 - "$TRANSCRIPT" <<'PYEOF' 2>/dev/null || echo "  (cost unavailable — framework/cost/meter.py not importable)"
import sys
from framework.cost import meter

sl = meter.parse_transcript(sys.argv[1])
if sl.responses_billed == 0:
    print("No billable API responses found in this transcript.")
    raise SystemExit(0)

models = ", ".join("%s x%d" % (k, v) for k, v in sorted(sl.models.items()))
print("Responses:   %d  (%d duplicate content-block entries skipped)"
      % (sl.responses_billed, sl.duplicates_skipped))
print("Models:      %s" % models)
print("Input:       %d tokens" % sl.input_tokens)
print("Output:      %d tokens" % sl.output_tokens)
print("Cache write: %d tokens" % sl.cache_write)
print("Cache read:  %d tokens" % sl.cache_read)
print("")
print("TOTAL:       $%.2f" % (sl.cost_micro / 1_000_000))
if sl.malformed_skipped:
    print("NOTE:        %d entr(ies) had unparseable token counts and were skipped"
          % sl.malformed_skipped)
PYEOF
fi
