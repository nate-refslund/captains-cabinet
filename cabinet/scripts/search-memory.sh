#!/bin/bash
# search-memory.sh — Query the Cabinet Memory layer
# Usage: search-memory.sh "<query>" [--type TYPE] [--officer OFFICER] [--limit N]

set -uo pipefail

QUERY=""
TYPE=""
OFFICER=""
LIMIT=10

while [ $# -gt 0 ]; do
  case "$1" in
    --type) TYPE="$2"; shift 2 ;;
    --officer) OFFICER="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    *) QUERY="$1"; shift ;;
  esac
done

if [ -z "$QUERY" ]; then
  echo "Usage: search-memory.sh \"<query>\" [--type TYPE] [--officer OFFICER] [--limit N]"
  echo "Types: telegram_dm, telegram_group, officer_trigger, reflection, correction, captain_decision, product_spec, tech_radar, working_note, skill, role_definition, session_memory, golden_eval, experience_record, research_brief, framework_file"
  exit 1
fi

# Resolve repo root from script location so search works regardless of where
# the cabinet is checked out (Mac dev worktree, Docker /opt, fresh clone).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

RESULTS=$(memory_search "$QUERY" "$TYPE" "$OFFICER" "$LIMIT")

# memory_search echoes "Embedding failed" on Voyage/Neon outage. Treat that
# the same as no results — quiet output, exit 0. Callers (pre-captain-dm
# semantic recall, retro scans) bail on the "No results found." string.
case "$RESULTS" in
  "Embedding failed"*|"Embedding failed")
    echo "No results found."
    exit 0
    ;;
esac

if [ -z "$(echo "$RESULTS" | tr -d '[:space:]')" ]; then
  echo "No results found."
  exit 0
fi

echo "=== Cabinet Memory Search: '$QUERY' ==="
[ -n "$TYPE" ] && echo "Type: $TYPE"
[ -n "$OFFICER" ] && echo "Officer: $OFFICER"
echo ""

echo "$RESULTS" | while IFS=$'\t' read -r source_type who when_at similarity preview ref; do
  [ -z "$source_type" ] && continue
  printf "[%s] %s by %s @ %s (sim: %s)\n" "$source_type" "$ref" "$who" "$when_at" "$similarity"
  echo "  $preview"
  echo ""
done
