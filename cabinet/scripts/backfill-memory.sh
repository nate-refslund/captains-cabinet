#!/bin/bash
# backfill-memory.sh — Idempotent backfill of existing data into cabinet_memory
# Sources: experience_records, cabinet_research (both from internal PG),
#          ALL hook-watched knowledge files (captain-decisions.md per-H2-entry,
#          captain-patterns/intents, tech radar, product specs, backlog, tier2
#          working notes + reflections, skills, the org vault corpus
#          (vault/, legacy product-brain/ checkouts included), the docs/
#          tree (framework_doc), constitution), and framework extras
#          (CLAUDE.md, agent defs, guide, officer CLAUDE.md).
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

# PG-sourced sections need DATABASE_URL — fail fast up front instead of
# silently queueing nothing from an unset/misconfigured connection string.
if [ "$FILES_ONLY" -eq 0 ]; then
  : "${DATABASE_URL:?DATABASE_URL is required for the PG-sourced sections (or pass --files-only)}"
fi

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
# One row_to_json object per output line: JSON escapes embedded newlines, so
# multi-line columns (what_happened, lessons_learned — the normal case) can
# never shatter row framing the way delimiter-split -F output did.
while IFS= read -r row; do
  [ -z "$row" ] && continue
  rec_id=$(printf '%s' "$row" | jq -r '.id // empty' 2>/dev/null)
  [ -z "$rec_id" ] && continue
  officer=$(printf '%s' "$row" | jq -r '.officer // ""')
  created=$(printf '%s' "$row" | jq -r '.created_at // ""')
  content=$(printf '%s' "$row" | jq -r '"[\(.outcome // "")] \(.task_summary // "")\n\n\(.what_happened // "")\n\nLessons: \(.lessons_learned // "")"')
  metadata=$(printf '%s' "$row" | jq -c '{outcome: (.outcome // ""), tags: (.tags // "")}')
  memory_queue_embed "experience_record" "exp-$rec_id" "$officer" "" "$content" "$metadata" "$created"
  EXP_COUNT=$((EXP_COUNT+1))
done < <(psql "$DATABASE_URL" -t -A -c "
  SELECT row_to_json(t)
  FROM (
    SELECT id, officer, task_summary, outcome, what_happened, lessons_learned, created_at, tags::text AS tags
    FROM experience_records
    ORDER BY created_at DESC
  ) t
" 2>/dev/null)
log "experience_records: queued $EXP_COUNT for embedding"

# =============================================================
# 2. Research briefs (embeddings already exist)
# =============================================================
log "Backfilling cabinet_research..."
# row_to_json framing here too: research content is multi-line prose and may
# contain the old '|' delimiter — both shattered/corrupted rows before.
psql "$DATABASE_URL" -t -A -c "
  SELECT row_to_json(t)
  FROM (
    SELECT id, officer, title, content, summary, created_at, tags::text AS tags, embedding::text AS embedding
    FROM cabinet_research
    WHERE embedding IS NOT NULL
    ORDER BY created_at
    LIMIT 100
  ) t
" 2>/dev/null | while IFS= read -r row; do
  [ -z "$row" ] && continue
  rec_id=$(printf '%s' "$row" | jq -r '.id // empty' 2>/dev/null)
  [ -z "$rec_id" ] && continue
  officer=$(printf '%s' "$row" | jq -r '.officer // ""')
  content=$(printf '%s' "$row" | jq -r '.content // ""')
  summary=$(printf '%s' "$row" | jq -r '.summary // ""')
  embedding=$(printf '%s' "$row" | jq -r '.embedding // ""')
  created=$(printf '%s' "$row" | jq -r '.created_at // ""')
  metadata=$(printf '%s' "$row" | jq -c '{title: (.title // ""), tags: (.tags // "")}')

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

# Org vault corpus (source_type=product_brain — the DB taxonomy name predates
# the 2026-07-16 vault rename; whole-file embeds) + docs/ tree
# (source_type=framework_doc, joined the memory index 2026-07-17). find, not a
# glob, because both trees nest to arbitrary depth. Same TEMPLATE skip as
# above. Queued with an EXPLICIT source_type (mirroring pfwm_queue_watched_file
# byte-for-byte in meta shape) rather than via pfwm_source_type: the hook's own
# vault/ + docs/ watch patterns land in a germline ceremony
# (patches/germline-vault-hook-watch-2026-07-17.patch) and backfill must not
# depend on that timing. Legacy product-brain/ is still walked for
# un-migrated checkouts.
queue_typed_file() {  # $1=source_type  $2=path
  local st="$1" f="$2" content rel ts meta
  [ ! -f "$f" ] && return 1
  content=$(cat "$f") || return 1
  [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ] && return 1
  rel="${f#${CABINET_ROOT}/}"
  ts="$(pfwm_content_ts "$f")"  # "" when underivable — NEVER mtime
  meta=$(jq -nc --arg officer "$WRITER" --arg writer "$WRITER" \
    --arg trust "$(pfwm_trust_for "$st")" \
    '{edited_by: $officer, writer: $writer, trust: $trust}')
  memory_queue_embed "$st" "$rel" "$WRITER" "" "$content" "$meta" "$ts"
}
while IFS= read -r -d '' f; do
  [[ "$(basename "$f")" == TEMPLATE* ]] && continue
  queue_typed_file product_brain "$f" && WF_COUNT=$((WF_COUNT+1))
done < <(find "$CABINET_ROOT/vault" "$CABINET_ROOT/product-brain" \
           -type f -name '*.md' -print0 2>/dev/null)
while IFS= read -r -d '' f; do
  [[ "$(basename "$f")" == TEMPLATE* ]] && continue
  queue_typed_file framework_doc "$f" && WF_COUNT=$((WF_COUNT+1))
done < <(find "$CABINET_ROOT/docs" -type f -name '*.md' -print0 2>/dev/null)

log "watched knowledge files queued: $WF_COUNT"

# =============================================================
# 4. Framework extras not on the hook watch-list (CLAUDE.md, guide, agent
#    defs, officer CLAUDE.md). Content-time derived (never mtime), trust=derived.
# =============================================================
log "Queueing framework files..."
FW_COUNT=0
queue_framework_file() {
  local f="$1"
  if [ ! -f "$f" ]; then
    # WARN for explicitly-listed files; an unexpanded glob (literal '*'
    # remains) is a normal empty match, not a missing file.
    case "$f" in
      *\**) : ;;
      *) log "WARN: listed framework file missing: $f" ;;
    esac
    return 1
  fi
  local content rel_path ts meta
  content=$(cat "$f")
  [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ] && return 1
  rel_path="${f#${CABINET_ROOT}/}"
  ts="$(pfwm_content_ts "$f")"  # "" when underivable — NEVER mtime
  meta=$(jq -nc --arg writer "$WRITER" '{writer: $writer, trust: "derived"}')
  memory_queue_embed "framework_file" "$rel_path" "system" "" "$content" "$meta" "$ts"
}
for f in "$CABINET_ROOT/CLAUDE.md" \
         "$CABINET_ROOT/captains-cabinet-guide.md" \
         "$CABINET_ROOT"/.claude/agents/*.md \
         "$CABINET_ROOT"/officers/*/CLAUDE.md; do
  queue_framework_file "$f" && FW_COUNT=$((FW_COUNT+1))
done
log "framework files queued: $FW_COUNT"

log "Done queueing. The live memory-worker drains the queue; or run: bash cabinet/scripts/memory-worker.sh --once  (repeat until queue is empty)"
