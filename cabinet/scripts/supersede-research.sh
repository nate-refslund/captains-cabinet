#!/bin/bash
# supersede-research.sh — Mark a research brief as superseded in pgvector
# Usage: bash supersede-research.sh <old-brief-title-or-id> [new-brief-path]
set -euo pipefail

# Resolve repo root from script location — works for Mac worktrees and Docker /opt.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

QUERY="${1:-}"
NEW_BRIEF="${2:-}"

[[ -z "$QUERY" ]] && { echo "Usage: bash supersede-research.sh <title-search-term> [new-brief-path]"; exit 1; }

DB_URL="${NEON_CONNECTION_STRING:-${NEON_DATABASE_URL:-${DATABASE_URL:-}}}"
[[ -z "$DB_URL" ]] && { echo "Error: NEON_CONNECTION_STRING (or NEON_DATABASE_URL/DATABASE_URL) not set"; exit 1; }

# Use parameterized query to prevent SQL injection
SEARCH_PATTERN="%${QUERY}%"
RESULT=$(psql "$DB_URL" -t -A \
  -v pattern="$SEARCH_PATTERN" \
  -c "UPDATE cabinet_research
  SET usage_status = 'superseded', updated_at = NOW()
  WHERE LOWER(title) LIKE LOWER(:'pattern')
    AND usage_status != 'superseded'
  RETURNING id, title;")

if [ -z "$RESULT" ]; then
  echo "No matching briefs found for: $QUERY"
else
  echo "Superseded:"
  echo "$RESULT"
fi

# If a new brief path is provided, embed it as the replacement
if [ -n "$NEW_BRIEF" ] && [ -f "$NEW_BRIEF" ]; then
  echo ""
  echo "Embedding replacement brief..."
  bash "$CABINET_ROOT/cabinet/scripts/embed-research.sh" "$NEW_BRIEF" --tags "replacement"
fi
