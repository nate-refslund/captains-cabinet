#!/bin/bash
# backfill-memory.sh — Idempotent backfill of existing data into cabinet_memory
# Sources: experience_records, cabinet_research (both from internal PG),
#          ALL hook-watched knowledge files (captain-decisions.md per-H2-entry,
#          captain-patterns/intents, tech radar, product specs, backlog, tier2
#          working notes + reflections, skills, product-brain corpus,
#          constitution), and framework extras (CLAUDE.md, agent defs, guide,
#          officer CLAUDE.md).
#
# Parsing/queueing logic is SHARED with the live hook: this script sources
# cabinet/scripts/hooks/post-file-write-memory.sh in library mode
# (POST_FILE_WRITE_MEMORY_LIB=1) so backfill and hook can never drift.
# Content-time rule: source_created_at derives from content (heading date,
# frontmatter, filename) — NEVER file mtime.
#
# Usage: backfill-memory.sh [--files-only]
#   --files-only   Skip the PG-sourced sections (experience_records,
#                  cabinet_research); re-queue only the knowledge files.
#
# Idempotent: cabinet_memory has a partial-unique (source_type, source_id), so
# re-queued items upsert in place (version bump) rather than duplicate.

set -uo pipefail

# Resolve repo root from script location — works for Mac worktrees and Docker /opt.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

# Auto-export env vars so subshells (pipes) inherit them
set -a
source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
set +a
source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

# Shared parsing/queueing functions (pfwm_*) — same code path as the live hook.
POST_FILE_WRITE_MEMORY_LIB=1
source "$CABINET_ROOT/cabinet/scripts/hooks/post-file-write-memory.sh"
unset POST_FILE_WRITE_MEMORY_LIB

# Fail fast if required env is missing (prevents silent queue of unembeddable items)
: "${NEON_CONNECTION_STRING:?NEON_CONNECTION_STRING is required}"
: "${VOYAGE_API_KEY:?VOYAGE_API_KEY is required}"
: "${REDIS_HOST:=redis}"
: "${REDIS_PORT:=6379}"

FILES_ONLY=0
[ "${1:-}" = "--files-only" ] && FILES_ONLY=1

log() { echo "[backfill $(date -u +%H:%M:%S)] $1"; }

# Backfill runs outside an officer session: honor CLAUDE_OFFICER when set,
# otherwise attribute to "system" (matches the historical backfill officer).
WRITER="${CLAUDE_OFFICER:-system}"

if [ "$FILES_ONLY" -eq 0 ]; then

# =============================================================
# 1. Experience records — queue for re-embedding (table has content but no embeddings)
# =============================================================
log "Queueing experience_records for embedding..."
EXP_COUNT=0
while IFS=$'\t' read -r rec_id officer summary outcome happened lessons created tags_str; do
  [ -z "$rec_id" ] && continue
  content="[${outcome}] ${summary}

${happened}

Lessons: ${lessons}"
  metadata=$(jq -nc --arg outcome "$outcome" --arg tags "$tags_str" '{outcome: $outcome, tags: $tags}')
  memory_queue_embed "experience_record" "exp-$rec_id" "$officer" "" "$content" "$metadata" "$created"
  EXP_COUNT=$((EXP_COUNT+1))
done < <(psql "$DATABASE_URL" -t -A -F $'\t' -c "
  SELECT id, officer, task_summary, outcome, what_happened, lessons_learned, created_at, tags::text
  FROM experience_records
  ORDER BY created_at DESC
" 2>/dev/null)
log "experience_records: queued $EXP_COUNT for embedding"

# =============================================================
# 2. Research briefs (embeddings already exist)
# =============================================================
log "Backfilling cabinet_research..."
psql "$DATABASE_URL" -t -A -F '|' -c "
  SELECT id, officer, title, content, summary, created_at, tags::text, embedding::text
  FROM cabinet_research
  WHERE embedding IS NOT NULL
  ORDER BY created_at
  LIMIT 100
" 2>/dev/null | while IFS='|' read -r rec_id officer title content summary created tags_str embedding; do
  [ -z "$rec_id" ] && continue
  metadata=$(jq -nc --arg title "$title" --arg tags "$tags_str" '{title: $title, tags: $tags}')

  psql "$NEON_CONNECTION_STRING" -q \
    -v source_type="research_brief" \
    -v source_id="rb-$rec_id" \
    -v officer="$officer" \
    -v content="$content" \
    -v summary="$summary" \
    -v embedding="$embedding" \
    -v metadata="$metadata" \
    -v source_ts="$created" \
    2>/dev/null <<'SQLEOF' > /dev/null
INSERT INTO cabinet_memory (source_type, source_id, officer, content, summary, embedding, metadata, source_created_at)
VALUES (:'source_type', :'source_id', :'officer', :'content', :'summary', :'embedding'::vector, :'metadata'::jsonb, :'source_ts'::timestamptz)
ON CONFLICT (source_type, source_id) WHERE source_id IS NOT NULL AND superseded_by IS NULL
DO NOTHING;
SQLEOF
done
log "cabinet_research: backfilled"

fi  # FILES_ONLY

# =============================================================
# 3. Watched knowledge files — SAME parsing as the live hook.
#    captain-decisions.md is split per-H2-entry inside
#    pfwm_queue_watched_file (whole-file fallback if zero entries parse);
#    all files get content-derived source_created_at (never mtime) and
#    writer/trust metadata.
# =============================================================
log "Queueing watched knowledge files (shared hook logic)..."
WF_COUNT=0
for f in "$CABINET_ROOT/shared/interfaces/captain-decisions.md" \
         "$CABINET_ROOT/shared/interfaces/captain-patterns.md" \
         "$CABINET_ROOT/shared/interfaces/captain-intents.md" \
         "$CABINET_ROOT/shared/interfaces/tech-radar.md" \
         "$CABINET_ROOT"/shared/interfaces/product-specs/*.md \
         "$CABINET_ROOT/shared/backlog.md" \
         "$CABINET_ROOT"/instance/memory/tier2/*/working-notes.md \
         "$CABINET_ROOT"/instance/memory/tier2/*/reflections/*.md \
         "$CABINET_ROOT"/memory/skills/*.md \
         "$CABINET_ROOT"/memory/skills/evolved/*.md \
         "$CABINET_ROOT/framework/constitution-base.md" \
         "$CABINET_ROOT/framework/safety-boundaries-base.md"; do
  [ ! -f "$f" ] && continue
  [[ "$(basename "$f")" == TEMPLATE* ]] && continue
  pfwm_queue_watched_file "$f" "$WRITER" && WF_COUNT=$((WF_COUNT+1))
done

# product-brain corpus (source_type=product_brain, whole-file embeds) — find,
# not a glob, because the corpus nests to arbitrary depth (decisions/,
# incidents/, per-product subdirs). Same TEMPLATE skip as above.
while IFS= read -r -d '' f; do
  [[ "$(basename "$f")" == TEMPLATE* ]] && continue
  pfwm_queue_watched_file "$f" "$WRITER" && WF_COUNT=$((WF_COUNT+1))
done < <(find "$CABINET_ROOT/product-brain" -type f -name '*.md' -print0 2>/dev/null)

log "watched knowledge files queued: $WF_COUNT"

# =============================================================
# 4. Framework extras not on the hook watch-list (CLAUDE.md, guide, agent
#    defs, officer CLAUDE.md). Content-time derived (never mtime), trust=derived.
# =============================================================
log "Queueing framework files..."
FW_COUNT=0
queue_framework_file() {
  local f="$1"
  [ ! -f "$f" ] && return 1
  local content rel_path ts meta
  content=$(cat "$f")
  [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ] && return 1
  rel_path="${f#${CABINET_ROOT}/}"
  ts="$(pfwm_content_ts "$f")"  # "" when underivable — NEVER mtime
  meta=$(jq -nc --arg writer "$WRITER" '{writer: $writer, trust: "derived"}')
  memory_queue_embed "framework_file" "$rel_path" "system" "" "$content" "$meta" "$ts"
}
for f in "$CABINET_ROOT/CLAUDE.md" \
         "$CABINET_ROOT/founders-cabinet-guide.md" \
         "$CABINET_ROOT"/.claude/agents/*.md \
         "$CABINET_ROOT"/officers/*/CLAUDE.md; do
  queue_framework_file "$f" && FW_COUNT=$((FW_COUNT+1))
done
log "framework files queued: $FW_COUNT"

log "Done queueing. The live memory-worker drains the queue; or run: bash cabinet/scripts/memory-worker.sh --once  (repeat until queue is empty)"
