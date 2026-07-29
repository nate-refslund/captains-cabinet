#!/bin/bash
# search-memory.sh — Query the Cabinet Memory layer
# Usage: search-memory.sh "<query>" [--type TYPE[,TYPE...]] [--officer OFFICER] [--limit N] [--min-score S] [--as-of TS]

set -uo pipefail

QUERY=""
TYPE=""
OFFICER=""
LIMIT=10
MIN_SCORE=""
AS_OF=""

while [ $# -gt 0 ]; do
  case "$1" in
    --type) TYPE="$2"; shift 2 ;;
    --officer) OFFICER="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --min-score) MIN_SCORE="$2"; shift 2 ;;
    --as-of) AS_OF="$2"; shift 2 ;;
    *) QUERY="$1"; shift ;;
  esac
done

if [ -z "$QUERY" ]; then
  echo "Usage: search-memory.sh \"<query>\" [--type TYPE[,TYPE...]] [--officer OFFICER] [--limit N] [--min-score S] [--as-of TS]"
  echo "Types: telegram_dm, telegram_group, officer_trigger, reflection, correction, captain_decision, product_spec, tech_radar, working_note, skill, role_definition, session_memory, golden_eval, experience_record, research_brief, framework_file"
  echo "  --type       one type or a comma-separated list (matches any of them)"
  echo "  --min-score  vec-similarity floor 0..1 (default ${MEMORY_VEC_FLOOR_DEFAULT:-0.28}, measured — see lib/memory.sh; env CABINET_MEMORY_MIN_SCORE)"
  echo "  --as-of      ISO timestamp content-time fence: only rows with source_created_at <= TS;"
  echo "               rows WITHOUT a source timestamp are EXCLUDED under a fence (fail-closed)"
  exit 1
fi

# Resolve repo root from script location so search works regardless of where
# the cabinet is checked out (Mac dev worktree, Docker /opt, fresh clone).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

RESULTS=$(memory_search "$QUERY" "$TYPE" "$OFFICER" "$LIMIT" "$MIN_SCORE" "$AS_OF")

# Belt: legacy sentinel. Since 2026-07-07 memory_search DEGRADES to a
# lexical-only search when the embedding is unavailable (keyless box /
# Voyage outage) instead of emitting "Embedding failed" — the case below is
# kept for older lib versions only. Callers (pre-captain-dm semantic recall,
# retro scans) still bail on the "No results found." string.
case "$RESULTS" in
  "Embedding failed"*|"Embedding failed")
    echo "No results found."
    exit 0
    ;;
esac

if [ -z "$(echo "$RESULTS" | tr -d '[:space:]')" ]; then
  echo "No results found."
  # STDERR ONLY — stdout stays byte-identical for the placeholder-matching
  # consumers (pre-captain-dm.sh's exact "Noresultsfound." compare,
  # captain_inbound.py's literal check). Says WHICH empty this is: a store
  # with nothing in it, or a similarity floor that discarded real candidates.
  # See memory_empty_reason in lib/memory.sh for the measurement behind it.
  memory_empty_reason "$(memory_scope_count "$TYPE" "$AS_OF")" "$MIN_SCORE" "$QUERY" >&2
  exit 0
fi

echo "=== Cabinet Memory Search: '$QUERY' ==="
[ -n "$TYPE" ] && echo "Type: $TYPE"
[ -n "$OFFICER" ] && echo "Officer: $OFFICER"
[ -n "$AS_OF" ] && echo "As-of fence: $AS_OF (rows without a source timestamp excluded)"
echo ""

# Row fields (tab-separated, from memory_search):
#   source_type, who, when_at, similarity (cosine), score (blended
#   0.60*vec + 0.25*lex + 0.15*recency), trust (metadata.trust or
#   'derived'), preview, ref
echo "$RESULTS" | while IFS=$'\t' read -r source_type who when_at similarity score trust preview ref; do
  [ -z "$source_type" ] && continue
  printf "[trust:%s] [%s] %s by %s @ %s (sim: %s, score: %s)\n" "${trust:-derived}" "$source_type" "$ref" "$who" "$when_at" "$similarity" "$score"
  echo "  $preview"
  echo ""
done
