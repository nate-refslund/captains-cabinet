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

  # Detect the model from the transcript and pick rates matching
  # cabinet/scripts/hooks/stop-hook.sh ($/MTok: in/out/cache_write/cache_read).
  # Last-seen assistant model wins; mixed-model transcripts are priced at that
  # model's rates (same convention as stop-hook, which prices the last entry).
  MODEL=$(jq -r 'select(.type == "assistant" and .message.model != null) | .message.model' "$TRANSCRIPT" 2>/dev/null | tail -1)
  MODEL=${MODEL:-unknown}
  case "$MODEL" in
    *fable*) IN_RATE=10; OUT_RATE=50; CW_RATE=12.5; CR_RATE=1.0 ;;
    *opus*)  IN_RATE=15; OUT_RATE=75; CW_RATE=3.75; CR_RATE=0.30 ;;
    *)       IN_RATE=3;  OUT_RATE=15; CW_RATE=0.75; CR_RATE=0.06 ;;  # Sonnet default
  esac

  jq -c 'select(.type == "assistant" and .message.usage != null) | .message.usage' "$TRANSCRIPT" 2>/dev/null | jq -s '
  {
    input: (map(.input_tokens // 0) | add // 0),
    output: (map(.output_tokens // 0) | add // 0),
    cache_write: (map(.cache_creation_input_tokens // 0) | add // 0),
    cache_read: (map(.cache_read_input_tokens // 0) | add // 0),
    turns: length
  }' 2>/dev/null | jq -r \
    --arg model "$MODEL" \
    --argjson in_rate "$IN_RATE" --argjson out_rate "$OUT_RATE" \
    --argjson cw_rate "$CW_RATE" --argjson cr_rate "$CR_RATE" '
    "Turns: \(.turns)",
    "Input:       \(.input) tokens (\(.input / 1000000 * 100 | round / 100) MTok)",
    "Output:      \(.output) tokens (\(.output / 1000000 * 100 | round / 100) MTok)",
    "Cache write: \(.cache_write) tokens (\(.cache_write / 1000000 * 100 | round / 100) MTok)",
    "Cache read:  \(.cache_read) tokens (\(.cache_read / 1000000 * 100 | round / 100) MTok)",
    "",
    "Cost (\($model): $\($in_rate)/$\($out_rate)/$\($cw_rate)/$\($cr_rate) per MTok):",
    "  Input:       $\(.input / 1000000 * $in_rate * 100 | round / 100)",
    "  Output:      $\(.output / 1000000 * $out_rate * 100 | round / 100)",
    "  Cache write: $\(.cache_write / 1000000 * $cw_rate * 100 | round / 100)",
    "  Cache read:  $\(.cache_read / 1000000 * $cr_rate * 100 | round / 100)",
    "  TOTAL:       $\((.input / 1000000 * $in_rate + .output / 1000000 * $out_rate + .cache_write / 1000000 * $cw_rate + .cache_read / 1000000 * $cr_rate) * 100 | round / 100)"
  ' 2>/dev/null
fi
