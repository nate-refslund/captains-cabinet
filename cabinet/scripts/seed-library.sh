#!/bin/bash
# seed-library.sh — Seed the Library with a preset's starter Spaces + records
#
# Usage:
#   bash cabinet/scripts/seed-library.sh [--preset <slug>] [--space <basename>] [--dry-run]
#
#   --preset <slug>    Preset whose starter-spaces/ to seed. Default: the
#                      active preset (instance/config/active-preset), else "work".
#   --space <basename> Seed only presets/<slug>/starter-spaces/<basename>.yml
#   --dry-run          Read-only pass: report what would be created, write nothing.
#
# Templates live in presets/<slug>/starter-spaces/*.yml — YAML with the same
# space fields as the legacy cabinet/starter-spaces/*.json (name, description,
# schema_json, starter_template, access_rules) plus a `records:` list of seed
# record stubs (title, labels, schema_data, content_markdown). Format doc:
# presets/README.md → "Library starter spaces".
#
# Idempotent by existence check, not upsert:
#   - Space: matched by name (library_spaces.name UNIQUE). An existing Space
#     is reused as-is — description/schema/access_rules are NOT overwritten,
#     so Captain curation survives re-runs.
#   - Record: matched by (space_id, title) across ALL versions, so a re-run
#     never duplicates a seed, never overwrites an edit, and never resurrects
#     a record the Captain deleted (soft-deletes and superseded versions count
#     as "exists").
#
# Writes go through the Library's own path (cabinet/scripts/lib/library.sh
# library_create_space / library_create_record): parameterized psql -v binds
# and a best-effort cabinet_memory queue via memory_queue_embed. Since the
# Library retirement (2026-07-16) records are inserted VECTOR-FREE — no
# voyage embed, embedding column stays NULL (see
# docs/runbooks/library-retirement-2026-07-16.md). INSERT-only —
# nothing here updates or deletes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

usage() {
  sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------
# Args
# ---------------------------------------------------------------
PRESET=""
ONLY_SPACE=""
DRY_RUN=false
while [ $# -gt 0 ]; do
  case "$1" in
    --preset)  PRESET="${2:-}"; shift 2 ;;
    --space)   ONLY_SPACE="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "seed-library: unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [ -z "$PRESET" ]; then
  PRESET="$(tr -d '[:space:]' < "$CABINET_ROOT/instance/config/active-preset" 2>/dev/null || true)"
  PRESET="${PRESET:-work}"
fi

SPACES_DIR="$CABINET_ROOT/presets/$PRESET/starter-spaces"
if [ ! -d "$SPACES_DIR" ]; then
  echo "seed-library: preset '$PRESET' ships no starter-spaces/ ($SPACES_DIR) — nothing to seed"
  exit 0
fi

# ---------------------------------------------------------------
# Env + Library write path
# ---------------------------------------------------------------
if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  set -a
  source "$CABINET_ROOT/cabinet/.env" 2>/dev/null || true
  set +a
fi
: "${NEON_CONNECTION_STRING:?seed-library: NEON_CONNECTION_STRING not set (cabinet/.env)}"

source "$CABINET_ROOT/cabinet/scripts/lib/library.sh"
export OFFICER_NAME="${OFFICER_NAME:-system}"

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

# Parse a starter-space YAML into compact JSON on stdout.
# File path rides argv into python — never interpolated into code.
yaml_to_json() {
  python3 - "$1" <<'PY'
import json
import sys

import yaml

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
json.dump(data, sys.stdout)
PY
}

# Does an active-or-historical record with this title exist in the space?
# Prints the record id if so, empty otherwise. Title rides psql -v (never
# interpolated into SQL).
record_exists() {
  local space_id="$1" title="$2"
  psql "$NEON_CONNECTION_STRING" -q -t -A \
    -v sid="$space_id" \
    -v title="$title" \
    <<'SQLEOF'
SELECT id FROM library_records
WHERE space_id = :'sid'::bigint AND title = :'title'
LIMIT 1;
SQLEOF
}

TOTAL_SPACES_CREATED=0
TOTAL_RECORDS_CREATED=0
TOTAL_RECORDS_SKIPPED=0
SEEDED_FILES=0

# Seed one starter-space YAML file: ensure the Space, then each missing record.
seed_space_file() {
  local file="$1"
  local spec_json name desc schema_json starter access_rules space_id
  spec_json="$(yaml_to_json "$file")"

  name="$(printf '%s' "$spec_json" | jq -r '.name // empty')"
  if [ -z "$name" ]; then
    echo "seed-library: SKIP $(basename "$file") — no .name field" >&2
    return 0
  fi
  desc="$(printf '%s' "$spec_json" | jq -r '.description // ""')"
  schema_json="$(printf '%s' "$spec_json" | jq -c '.schema_json // {}')"
  starter="$(printf '%s' "$spec_json" | jq -r '.starter_template // "blank"')"
  access_rules="$(printf '%s' "$spec_json" | jq -c '.access_rules // {}')"

  # --- Space: existence check first; never overwrite an existing Space ---
  space_id="$(library_space_id "$name")"
  if [ -n "$space_id" ]; then
    echo "seed-library: space '$name' exists (id=$space_id) — reusing, not updating"
  elif [ "$DRY_RUN" = true ]; then
    echo "seed-library: [dry-run] would create space '$name' (template=$starter)"
  else
    space_id="$(library_create_space "$name" "$desc" "$schema_json" "$starter" "$OFFICER_NAME" "$access_rules")"
    if [ -z "$space_id" ]; then
      echo "seed-library: FAILED to create space '$name'" >&2
      return 1
    fi
    TOTAL_SPACES_CREATED=$((TOTAL_SPACES_CREATED + 1))
    echo "seed-library: created space '$name' (id=$space_id)"
  fi

  # --- Records: skip any title ever seen in this space ---
  local created=0 skipped=0
  local rec title content schema_data labels rid existing
  while IFS= read -r rec; do
    [ -z "$rec" ] && continue
    title="$(printf '%s' "$rec" | jq -r '.title // empty')"
    if [ -z "$title" ]; then
      echo "seed-library: SKIP record with no title in $(basename "$file")" >&2
      continue
    fi

    if [ -n "$space_id" ]; then
      existing="$(record_exists "$space_id" "$title")"
      if [ -n "$existing" ]; then
        skipped=$((skipped + 1))
        continue
      fi
    fi

    if [ "$DRY_RUN" = true ]; then
      echo "seed-library: [dry-run] would create record '$title' in '$name'"
      created=$((created + 1))
      continue
    fi

    content="$(printf '%s' "$rec" | jq -r '.content_markdown // ""')"
    schema_data="$(printf '%s' "$rec" | jq -c '.schema_data // {}')"
    labels="$(printf '%s' "$rec" | jq -r '(.labels // []) | join(",")')"

    rid="$(library_create_record "$space_id" "$title" "$content" "$schema_data" "$labels")"
    if [ -z "$rid" ]; then
      echo "seed-library: FAILED to create record '$title' in '$name'" >&2
      return 1
    fi
    created=$((created + 1))
    echo "seed-library: created record '$title' (id=$rid) in '$name'"
  done < <(printf '%s' "$spec_json" | jq -c '.records[]?')

  TOTAL_RECORDS_CREATED=$((TOTAL_RECORDS_CREATED + created))
  TOTAL_RECORDS_SKIPPED=$((TOTAL_RECORDS_SKIPPED + skipped))
  SEEDED_FILES=$((SEEDED_FILES + 1))
  echo "seed-library: $(basename "$file") → space '$name': $created record(s) created, $skipped already present"
}

# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
FOUND_ANY=false
for f in "$SPACES_DIR"/*.yml "$SPACES_DIR"/*.yaml; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  base="${base%.*}"
  if [ -n "$ONLY_SPACE" ] && [ "$base" != "$ONLY_SPACE" ]; then
    continue
  fi
  FOUND_ANY=true
  seed_space_file "$f"
done

if [ "$FOUND_ANY" = false ]; then
  if [ -n "$ONLY_SPACE" ]; then
    echo "seed-library: no starter space '$ONLY_SPACE' under $SPACES_DIR" >&2
    exit 1
  fi
  echo "seed-library: no *.yml starter spaces under $SPACES_DIR — nothing to seed"
  exit 0
fi

MODE="live"
[ "$DRY_RUN" = true ] && MODE="dry-run"
echo "seed-library: done ($MODE, preset=$PRESET) — files=$SEEDED_FILES spaces_created=$TOTAL_SPACES_CREATED records_created=$TOTAL_RECORDS_CREATED records_already_present=$TOTAL_RECORDS_SKIPPED"

# Read-only closing snapshot so the operator sees the Library state.
psql "$NEON_CONNECTION_STRING" -q -t -A -F $'\t' <<'SQLEOF' | awk -F'\t' '{printf "seed-library: library now holds %s space(s), %s active record(s)\n", $1, $2}'
SELECT (SELECT COUNT(*) FROM library_spaces),
       (SELECT COUNT(*) FROM library_records WHERE superseded_by IS NULL);
SQLEOF
