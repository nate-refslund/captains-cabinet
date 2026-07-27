#!/bin/bash
# cost-report.sh — Report token costs from Redis (stop-hook data) and/or transcript
# Usage: bash cost-report.sh [--daily] [--session <transcript-path>] [--officer <name>]

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

# FAIL-CLOSED SPEND REPORTING (2026-07-26) — see cabinet/scripts/lib/plane-read.sh.
# Until this date an unreachable control plane produced BOTH a false zero AND a
# wrong innocent cause: `HGETALL 2>/dev/null` returned "", and the report said
# "No cost data for today (stop-hook may not have fired yet)". Naming a benign
# cause for a failure you did not diagnose is worse than silence — it tells the
# reader to stop looking. Now: an unreadable plane says so and prints no figure.
_CR_ROOT="${CABINET_SOURCE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
PLANE_LIB="$_CR_ROOT/cabinet/scripts/lib/plane-read.sh"
if [ -r "$PLANE_LIB" ]; then
  # shellcheck disable=SC1090
  . "$PLANE_LIB"
fi
if ! command -v plane_read_int >/dev/null 2>&1; then
  echo "cost-report: FATAL — proven-read helper unavailable at $PLANE_LIB; refusing to report unverifiable cost figures" >&2
  exit 2
fi

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

  # One field read, three outcomes. Sets CF_VALUE (never printed via a
  # subshell — a $( ) capture would swallow the CR_UNAVAIL assignment and the
  # report would silently continue past an unreadable field).
  #   VALUE  -> CF_VALUE = the integer
  #   ABSENT -> CF_VALUE = 0, PROVEN: the field is genuinely unset
  #   else   -> rc 11 and CR_UNAVAIL set; the caller must abandon the report
  cost_field() {
    plane_read_int HGET "cabinet:cost:tokens:daily:$TODAY" "$1"
    case "$PLANE_VERDICT" in
      VALUE)  CF_VALUE="$PLANE_VALUE"; return 0 ;;
      ABSENT) CF_VALUE=0;              return 0 ;;
      *)      CF_VALUE=""; CR_UNAVAIL="$PLANE_REASON"; return 11 ;;
    esac
  }

  CR_UNAVAIL=""
  CF_VALUE=""
  plane_read_lines HGETALL "cabinet:cost:tokens:daily:$TODAY"
  case "$PLANE_VERDICT" in
    INDETERMINATE) CR_UNAVAIL="$PLANE_REASON" ;;
    ABSENT)        DATA="" ;;
    *)             DATA="$PLANE_VALUE" ;;
  esac

  if [ -n "$CR_UNAVAIL" ]; then
    echo "COST DATA UNAVAILABLE — control plane unreachable at $(plane_endpoint_str)."
    echo "No figures are shown because none could be sourced. This is NOT a zero-spend day."
    echo "Detail: $CR_UNAVAIL"
    echo ""
    exit 3
  elif [ -z "$DATA" ]; then
    # Proven: a live server answered and today's hash is genuinely empty. The
    # cause below is now an OBSERVATION about a verified-reachable plane, not a
    # guess offered in place of a diagnosis.
    echo "No cost data for today — control plane verified reachable at $(plane_endpoint_str), today's ledger is empty (no officer turn has been priced yet)"
  else
    # Parse into associative-like variables
    for officer in cto cos cpo cro coo; do
      if [ -n "$OFFICER" ] && [ "$officer" != "$OFFICER" ]; then continue; fi

      cost_field "${officer}_input"       || break; input="$CF_VALUE"
      cost_field "${officer}_output"      || break; output="$CF_VALUE"
      cost_field "${officer}_cache_write" || break; cw="$CF_VALUE"
      cost_field "${officer}_cache_read"  || break; cr="$CF_VALUE"
      cost_field "${officer}_cost_micro"  || break; cost="$CF_VALUE"

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
      cost_field "${officer}_cost_micro" || break
      total=$(( total + CF_VALUE ))
    done

    # A read that went INDETERMINATE anywhere above invalidates the TOTAL —
    # print the failure, never a partial sum dressed up as the day's spend.
    if [ -n "$CR_UNAVAIL" ]; then
      echo "TOTAL UNAVAILABLE — control plane became unreadable mid-report at $(plane_endpoint_str)."
      echo "Detail: $CR_UNAVAIL"
      echo ""
      exit 3
    fi
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
