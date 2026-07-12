#!/bin/bash
# memory.sh — Shared Cabinet Memory library (universal semantic search)
# Usage: source this file, then call memory_embed / memory_search / memory_queue_embed

# Source cabinet/.env when either the connection string OR the tenant id is
# missing — worker/hook contexts may inherit NEON_CONNECTION_STRING from
# launchd without CABINET_ID, and tenant stamping needs both. CALLER-SET
# VALUES ALWAYS WIN (review fix 2026-07-07): .env only BACK-FILLS the missing
# variable — a caller that exports an explicit NEON_CONNECTION_STRING (scratch
# DB, test harness, second cabinet) but no CABINET_ID must never have its
# connection string silently replaced by the live .env value, or scratch
# embeds/searches land in the live cabinet_memory.
if [ -z "${NEON_CONNECTION_STRING:-}" ] || [ -z "${CABINET_ID:-}" ]; then
  MEMORY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CABINET_ROOT="${CABINET_ROOT:-$(cd "$MEMORY_LIB_DIR/../../.." && pwd)}"
  _mem_pre_neon="${NEON_CONNECTION_STRING:-}"
  _mem_pre_cid="${CABINET_ID:-}"
  set -a
  source "$CABINET_ROOT/cabinet/.env" 2>/dev/null || true
  set +a
  if [ -n "$_mem_pre_neon" ]; then NEON_CONNECTION_STRING="$_mem_pre_neon"; fi
  if [ -n "$_mem_pre_cid" ]; then CABINET_ID="$_mem_pre_cid"; fi
  unset _mem_pre_neon _mem_pre_cid
fi

MEM_REDIS_HOST="${REDIS_HOST:-redis}"
MEM_REDIS_PORT="${REDIS_PORT:-6379}"
MEM_QUEUE_KEY="cabinet:memory:embed_queue"

# =============================================================
# EMBED-SEAM (R4, 2026-07-12 — closes operative-egg-ledger:1938)
# The embedding provider/model/dims are a NAMED SEAM so a fresh captain can
# point the semantic spine at a different provider WITHOUT editing this
# library. Defaults reproduce today's deployment EXACTLY (Voyage voyage-4-large,
# 1024-dim) — nothing changes for the current cabinet unless these are set.
#
# WIRED PROVIDERS: only "voyage" has an arm in memory_get_embedding today.
# EMBED_PROVIDER is recorded (memory_embedding_stamp) + surfaced by the
# cabinet-doctor embed-seam probe. Pointing at an unwired provider DEGRADES
# cleanly (loud stderr WARN + return 1 → the keyless lexical arm), never a
# silent wrong-endpoint call. Adding a provider = add an arm below + a one-off
# re-embed backfill (a dims change re-embeds every row — deliberately NOT an
# auto-organ; see cabinet/sql/046-embedding-meta.sql + the doctor probe).
EMBED_PROVIDER="${EMBED_PROVIDER:-voyage}"
EMBED_MODEL="${EMBED_MODEL:-voyage-4-large}"
EMBED_DIMS="${EMBED_DIMS:-1024}"
# Cross-encoder reranker (R2). Same seam discipline: default reproduces the
# proven in-house choice; a fresh captain can retune without editing the lib.
EMBED_RERANK_MODEL="${EMBED_RERANK_MODEL:-rerank-2.5}"

# =============================================================
# TENANT RESOLUTION (cabinet_id scoping)
# Canonical resolver = env CABINET_ID, default 'main' — same precedence as
# framework/authority/posture.py cabinet_id() and load-preset.sh's CP9b
# validator. Charset mirrors load-preset.sh (^[a-zA-Z0-9_-]+$); an invalid
# value is treated as unset rather than erroring (this lib is best-effort).
# =============================================================

# Write-side id: what new rows are stamped with. Never empty — falls back to
# 'main' (the cabinet_id column default) exactly like record-experience.sh.
memory_cabinet_id() {
  local cid="${CABINET_ID:-main}"
  if ! printf '%s' "$cid" | grep -qE '^[A-Za-z0-9_-]+$'; then
    echo "memory.sh WARN: CABINET_ID invalid charset — falling back to 'main'" >&2
    cid="main"
  fi
  printf '%s' "$cid"
}

# Search-side scope: empty string = unscoped (match ALL rows — the pre-scoping
# behavior, kept ONLY for the genuinely-unset case). A set-but-INVALID
# CABINET_ID resolves 'main' here too (review fix 2026-07-07): both resolvers
# must agree, otherwise a box with a malformed id (e.g. 'acme.eu') would
# WRITE rows as 'main' while SEARCHING fully unscoped — silently reading
# every tenant's rows on a shared DB. Invalid → 'main' keeps the box
# self-consistent (it reads what it writes) and never unscoped, with a loud
# stderr warning so the misconfiguration is visible.
memory_cabinet_scope() {
  local cid="${CABINET_ID:-}"
  if [ -n "$cid" ] && ! printf '%s' "$cid" | grep -qE '^[A-Za-z0-9_-]+$'; then
    echo "memory.sh WARN: CABINET_ID invalid charset — scoping search to 'main'" >&2
    cid="main"
  fi
  printf '%s' "$cid"
}

# =============================================================
# CORE: generate embedding via Voyage API (returns JSON array)
# =============================================================
memory_get_embedding() {
  local text="$1"
  # EMBED-SEAM dispatch (R4): only the "voyage" provider is wired. An unwired
  # EMBED_PROVIDER must DEGRADE loudly (→ caller falls back to lexical), never
  # POST a foreign model to the Voyage endpoint. Compared case-insensitively.
  case "$(printf '%s' "${EMBED_PROVIDER:-voyage}" | tr '[:upper:]' '[:lower:]')" in
    voyage) : ;;
    *)
      echo "memory.sh WARN: EMBED_PROVIDER='${EMBED_PROVIDER}' has no wired arm (only 'voyage') — DEGRADING (add an arm in memory_get_embedding + re-embed backfill)" >&2
      return 1
      ;;
  esac
  # Use :- to survive `set -u` in callers (pre-captain-dm.sh + worker both
  # enable it). Without the default, an unset VOYAGE_API_KEY raises rather
  # than returning a clean 1.
  [ -z "${VOYAGE_API_KEY:-}" ] && return 1
  # voyage-4-large accepts up to 32K tokens (~128K chars). Cut to 32000 chars
  # keeps well under the limit with headroom for over-tokenization.
  text=$(echo "$text" | tr '\n' ' ' | cut -c1-32000)
  # Model comes from the EMBED-SEAM (EMBED_MODEL), defaulting to voyage-4-large.
  curl -s --max-time 30 https://api.voyageai.com/v1/embeddings \
    -H "Authorization: Bearer $VOYAGE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$text" --arg model "${EMBED_MODEL:-voyage-4-large}" '{input: [$text], model: $model}')" \
    | jq -r '.data[0].embedding | @json'
}

# =============================================================
# EMBED-SEAM STAMP (R4, 2026-07-12): record the active provider/model/dims in
# the one-row cabinet_embedding_meta table (cabinet/sql/046-embedding-meta.sql)
# so cabinet-doctor can detect drift between the configured seam and what the
# store was embedded with. Idempotent; run at DEPLOY/bootstrap — NEVER on the
# read path (that would add a write to every search). Self-sufficient: creates
# the table if absent, so a captain can stamp an existing estate in one call.
# Requires a writable NEON_CONNECTION_STRING.
# =============================================================
memory_embedding_stamp() {
  if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
    echo "memory.sh: no NEON_CONNECTION_STRING — cannot stamp cabinet_embedding_meta" >&2
    return 1
  fi
  psql "$NEON_CONNECTION_STRING" -q \
    -v provider="${EMBED_PROVIDER:-voyage}" \
    -v model="${EMBED_MODEL:-voyage-4-large}" \
    -v dims="${EMBED_DIMS:-1024}" \
    <<'SQLEOF'
CREATE TABLE IF NOT EXISTS cabinet_embedding_meta (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  provider TEXT NOT NULL, model TEXT NOT NULL, dims INT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO cabinet_embedding_meta (id, provider, model, dims, updated_at)
VALUES (1, :'provider', :'model', (:'dims')::int, NOW())
ON CONFLICT (id) DO UPDATE SET
  provider = EXCLUDED.provider,
  model    = EXCLUDED.model,
  dims     = EXCLUDED.dims,
  updated_at = NOW();
SQLEOF
}

# =============================================================
# SYNC INSERT: embed + insert immediately (for backfill)
# Args: source_type, source_id (can be empty), officer, sender, content,
#       metadata_json, source_created_at,
#       cabinet_id (optional 8th; default = memory_cabinet_id resolver —
#                   callers like memory-worker.sh may pass a queued value
#                   through so the ENQUEUER's tenant wins over the worker's)
# =============================================================
memory_embed() {
  local source_type="$1"
  local source_id="${2:-}"
  local officer="${3:-}"
  local sender="${4:-}"
  local content="$5"
  local metadata="${6:-{\}}"
  local source_ts="${7:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  local cabinet_id="${8:-$(memory_cabinet_id)}"

  # Refuse empty/whitespace-only content — Voyage happily embeds " " to a valid vector,
  # so this check must happen before embedding (not after)
  if [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ]; then
    return 1
  fi

  # Validate metadata is JSON; fall back to {} if not
  if ! printf '%s' "$metadata" | jq -e . >/dev/null 2>&1; then
    metadata='{}'
  fi

  local embedding
  embedding=$(memory_get_embedding "$content")
  [ -z "$embedding" ] || [ "$embedding" = "null" ] && return 1

  psql "$NEON_CONNECTION_STRING" -q \
    -v source_type="$source_type" \
    -v source_id="${source_id:-}" \
    -v officer="${officer:-}" \
    -v sender="${sender:-}" \
    -v content="$content" \
    -v embedding="$embedding" \
    -v metadata="$metadata" \
    -v source_ts="$source_ts" \
    -v cid="$cabinet_id" \
    2>/dev/null <<'SQLEOF'
INSERT INTO cabinet_memory (source_type, source_id, officer, sender, content, embedding, metadata, source_created_at, cabinet_id)
VALUES (
  NULLIF(:'source_type', ''),
  NULLIF(:'source_id', ''),
  NULLIF(:'officer', ''),
  NULLIF(:'sender', ''),
  :'content',
  :'embedding'::vector,
  :'metadata'::jsonb,
  :'source_ts'::timestamptz,
  COALESCE(NULLIF(:'cid', ''), 'main')
)
ON CONFLICT (source_type, source_id) WHERE source_id IS NOT NULL AND superseded_by IS NULL
DO UPDATE SET
  content = EXCLUDED.content,
  embedding = EXCLUDED.embedding,
  metadata = EXCLUDED.metadata,
  source_created_at = EXCLUDED.source_created_at,
  cabinet_id = EXCLUDED.cabinet_id,
  version = cabinet_memory.version + 1
RETURNING id;
SQLEOF
}

# =============================================================
# ASYNC QUEUE: push to Redis, worker processes
# Args: same as memory_embed. Returns immediately.
# =============================================================
memory_queue_embed() {
  local source_type="$1"
  local source_id="${2:-}"
  local officer="${3:-}"
  local sender="${4:-}"
  local content="$5"
  local metadata="${6:-{\}}"
  local source_ts="${7:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

  # Skip empty/whitespace-only content — prevents worker from embedding " "
  if [ -z "$(printf '%s' "$content" | tr -d '[:space:]')" ]; then
    return 1
  fi

  # Validate metadata JSON; fall back to {} if invalid (prevents silent payload drop)
  if ! printf '%s' "$metadata" | jq -e . >/dev/null 2>&1; then
    metadata='{}'
  fi

  # Build payload as compact JSON (one line — required for XADD single-value parsing)
  # cabinet_id is stamped at ENQUEUE time (the enqueuer's box identity is the
  # authoritative tenant); the worker passes it through to memory_embed, which
  # falls back to its local resolver if the field is absent (old payloads).
  local payload
  payload=$(jq -nc \
    --arg source_type "$source_type" \
    --arg source_id "$source_id" \
    --arg officer "$officer" \
    --arg sender "$sender" \
    --arg content "$content" \
    --argjson metadata "$metadata" \
    --arg source_ts "$source_ts" \
    --arg cabinet_id "$(memory_cabinet_id)" \
    '{source_type: $source_type, source_id: $source_id, officer: $officer, sender: $sender, content: $content, metadata: $metadata, source_ts: $source_ts, cabinet_id: $cabinet_id}')

  [ -z "$payload" ] && return 1

  redis-cli -h "$MEM_REDIS_HOST" -p "$MEM_REDIS_PORT" XADD "$MEM_QUEUE_KEY" '*' payload "$payload" > /dev/null 2>&1
}

# =============================================================
# SEARCH: hybrid semantic + lexical + recency query
# Args: query, source_type (optional, comma-separated multi-type OK),
#       officer (optional), limit (default 10),
#       min_score (optional; default 0.45, env CABINET_MEMORY_MIN_SCORE),
#       as_of (optional ISO timestamp; fail-closed content-time fence —
#              rows with NULL source_created_at are EXCLUDED under a fence)
#
# Ranking formula (blended, computed in SQL):
#   vec     = 1 - (embedding <=> query)                  cosine similarity, 0..1
#   lex     = r / (r + 0.05) where r = ts_rank(content_tsv, plainto_tsquery)
#             (bounded transform → 0..1; 0 when the tsquery is empty)
#   recency = exp(-ln(2) * age_days / 90)                90-day half-life;
#             NULL source_created_at → neutral 0.5
#   final   = 0.60*vec + 0.25*lex + 0.15*recency
#   Degraded (empty tsquery — e.g. stopword-only query): the lex channel
#   drops out and the remaining weights renormalize:
#   final   = 0.80*vec + 0.20*recency
#   Keyless/outage (no embedding at all): falls back to memory_search_lexical
#   (bottom of this file) — lexical-only + recency, never a blank result set.
# The similarity floor (min_score) applies to vec, not final — a lexically
# strong but semantically unrelated row must not sneak in.
#
# RERANK (R2): the blended score above ranks a POOL of limit*4 candidates;
# memory_rerank then reorders that pool with a Voyage cross-encoder and cuts
# to top-k. Fail-soft — keyless/error yields the blended top-k unchanged. The
# 8-column output contract is identical either way (only intra-top-k order and
# which pool rows make the cut can change).
#
# Tenant scoping: results are fenced to this cabinet's rows —
# cabinet_id = memory_cabinet_scope() OR 'main' (legacy transition rows);
# CABINET_ID unset → unscoped (all rows). See the transition comment inline.
# =============================================================
memory_search() {
  local query="$1"
  local source_type_filter="${2:-}"
  local officer_filter="${3:-}"
  local limit="${4:-10}"
  local min_score="${5:-${CABINET_MEMORY_MIN_SCORE:-0.45}}"
  local as_of="${6:-}"

  # min_score must be a plain non-negative decimal — junk falls back to the
  # default rather than erroring the query.
  if ! printf '%s' "$min_score" | grep -qE '^[0-9]*\.?[0-9]+$'; then
    min_score="0.45"
  fi

  local query_embedding
  query_embedding=$(memory_get_embedding "$query")
  if [ -z "$query_embedding" ] || [ "$query_embedding" = "null" ]; then
    # Keyless / provider-outage fail-soft (EMBED-SEAM forward-guard,
    # 2026-07-07): an unset VOYAGE_API_KEY (or a Voyage outage) must DEGRADE
    # search, never blank it — a keyless Mini hatch still needs org recall.
    # Fall back to the lexical-only arm below (BM25-style ts_rank, same
    # filters/fences/8-col output shape). The old "Embedding failed" sentinel
    # is no longer emitted here; downstream sentinel handling stays as belt.
    echo "memory.sh WARN: embedding unavailable (no VOYAGE_API_KEY or provider outage) — DEGRADED to lexical-only search" >&2
    memory_search_lexical "$query" "$source_type_filter" "$officer_filter" "$limit" "$as_of"
    return $?
  fi

  # Tenant scope (cabinet_id). TRANSITION RULE (2026-07-07): all pre-scoping
  # rows carry the column default 'main' (verified live: 624/624 rows =
  # 'main' while this box resolves CABINET_ID=hq-macbook), so a strict
  # `cabinet_id = resolved` filter would zero out recall. Until those rows
  # are restamped, the filter matches (resolved id OR 'main') — 'main' rows
  # are treated as this-cabinet legacy rows. Empty scope (CABINET_ID unset)
  # = match ALL, today's pre-scoping behavior. Corollary: on a SHARED
  # multi-cabinet DB every cabinet must run with an explicit non-'main'
  # CABINET_ID; drop the OR-'main' arm once a backfill restamps legacy rows.
  local cid_scope
  cid_scope="$(memory_cabinet_scope)"

  # Rerank pool (R2, 2026-07-12): over-fetch a blended-ranked pool of limit*4
  # rows so the Voyage cross-encoder (memory_rerank, below) has a real
  # candidate set to reorder before the cut to top-k. The candidate CTE
  # already pulls GREATEST(limit*5,50), so this pool is a strict subset — no
  # extra HNSW cost. Fail-soft: if rerank is unavailable the pool is simply
  # cut to top-k in blended order (today's behavior).
  local rerank_pool=$(( limit * 4 ))
  [ "$rerank_pool" -lt "$limit" ] && rerank_pool="$limit"

  # Use tab separator (safer than | — content may contain |)
  # Strip any tabs/newlines from preview so one row = one line, cleanly parseable
  # Filters passed via psql -v (parameterized, injection-safe)
  # candidates CTE keeps the HNSW index in play: pull a vector-ordered pool
  # (5x limit, floor 50), then re-rank the pool by the blended score.
  # The 9th column (rerank_text) is INTERNAL — it feeds memory_rerank and is
  # stripped before the 8-col contract leaves this function.
  local _pool_rows
  _pool_rows=$(psql "$NEON_CONNECTION_STRING" -q -t -A -F $'\t' \
    -v embedding="$query_embedding" \
    -v query="$query" \
    -v limit="$limit" \
    -v pool="$rerank_pool" \
    -v st_filter="${source_type_filter:-}" \
    -v of_filter="${officer_filter:-}" \
    -v min_score="$min_score" \
    -v as_of="${as_of:-}" \
    -v cid="$cid_scope" \
    2>/dev/null <<'SQLEOF'
WITH params AS (
  SELECT plainto_tsquery('english', :'query') AS tsq
),
candidates AS (
  SELECT m.*,
    (1 - (m.embedding <=> :'embedding'::vector)) AS vec_sim
  FROM cabinet_memory m
  WHERE m.superseded_by IS NULL
    AND (:'st_filter' = '' OR m.source_type = ANY(string_to_array(:'st_filter', ',')))
    AND (:'of_filter' = '' OR m.officer = :'of_filter')
    -- Tenant fence: resolved id OR legacy 'main' rows (transition rule
    -- above); empty scope = unscoped (pre-scoping behavior).
    AND (:'cid' = '' OR m.cabinet_id = :'cid' OR m.cabinet_id = 'main')
    -- Fail-closed content-time fence: under --as-of, NULL-timestamp rows are excluded.
    AND (:'as_of' = '' OR (m.source_created_at IS NOT NULL
                           AND m.source_created_at <= NULLIF(:'as_of', '')::timestamptz))
  ORDER BY m.embedding <=> :'embedding'::vector
  LIMIT GREATEST((:'limit')::int * 5, 50)
),
scored AS (
  SELECT c.*,
    CASE WHEN c.source_created_at IS NULL THEN 0.5
         ELSE exp(-ln(2.0) * GREATEST(extract(epoch FROM (now() - c.source_created_at)), 0) / (90.0 * 86400.0))
    END AS recency,
    CASE WHEN numnode(p.tsq) = 0 THEN 0.0
         ELSE ts_rank(c.content_tsv, p.tsq) / (ts_rank(c.content_tsv, p.tsq) + 0.05)
    END AS lex,
    (numnode(p.tsq) > 0) AS has_lex
  FROM candidates c CROSS JOIN params p
),
final AS (
  SELECT s.*,
    -- final = 0.60*vec + 0.25*lex + 0.15*recency (empty tsquery → 0.80*vec + 0.20*recency)
    CASE WHEN s.has_lex
         THEN 0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency
         ELSE 0.80 * s.vec_sim + 0.20 * s.recency
    END AS final_score
  FROM scored s
)
SELECT
  source_type,
  COALESCE(officer, sender, 'n/a') as who,
  to_char(source_created_at, 'YYYY-MM-DD HH24:MI') as when_at,
  round(vec_sim::numeric, 3) as similarity,
  round(final_score::numeric, 3) as score,
  COALESCE(NULLIF(regexp_replace(LEFT(metadata->>'trust', 32), E'[\t\n\r ]+', '', 'g'), ''), 'derived') as trust,
  regexp_replace(LEFT(COALESCE(summary, content), 200), E'[\t\n\r]+', ' ', 'g') as preview,
  COALESCE(source_id, id::text) as ref,
  regexp_replace(LEFT(COALESCE(summary, content), 1024), E'[\t\n\r]+', ' ', 'g') as rerank_text
FROM final
WHERE vec_sim >= (:'min_score')::float8
ORDER BY final_score DESC
LIMIT (:'pool')::int;
SQLEOF
)

  # R2 rerank stage + cut to top-k. Emits the 8-column memory_search contract
  # (source_type/who/when_at/similarity/score/trust/preview/ref); the internal
  # 9th rerank_text column is consumed here and never surfaces. Fail-soft — a
  # keyless box or any rerank error yields the blended top-k unchanged.
  memory_rerank "$query" "$limit" "$_pool_rows"
}

# =============================================================
# RERANK (R2, 2026-07-12): single Voyage cross-encoder stage.
# Reorders the blended candidate pool produced by memory_search by a Voyage
# /rerank call, then cuts to top-k — the single largest known quality lift on
# the org retrieval path (SOTA: hybrid+rerank −67% retrieval failures vs −49%
# hybrid alone). FAIL-SOFT BY CONSTRUCTION: keyless, curl/jq error, or an
# empty/garbled response all fall back to the blended order — the exact mirror
# of memory_search's lexical-degrade arm. Rerank can therefore NEVER blank or
# corrupt a result set; the worst case is today's blended behavior.
# Bash 3.2-safe (macOS ships 3.2 — no mapfile/readarray/nameref).
#
# Args: query, topk, pool_rows (newline-separated; 9 tab columns each, the 9th
#       = rerank_text). Emits <=topk rows of the 8-column contract.
# =============================================================
_memory_blended_topk() {
  # stdin: pool rows (9 tab cols). $1: topk. Emits <=topk rows, columns 1-8.
  local topk="$1" line count=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    [ "$count" -ge "$topk" ] && break
    printf '%s\n' "$line" | cut -f1-8
    count=$((count+1))
  done
}

memory_rerank() {
  local query="$1" topk="$2" rows="$3"

  # Build an index-stable array of non-empty pool lines (for reordering).
  local _pool=()
  local _line
  while IFS= read -r _line; do
    [ -n "$_line" ] && _pool+=("$_line")
  done <<< "$rows"
  local _n=${#_pool[@]}
  [ "$_n" -eq 0 ] && return 0

  # Fail-soft arm 1 (keyless): no rerank possible → blended top-k. In practice
  # memory_search already degraded to lexical before reaching here when the key
  # is absent; this keeps memory_rerank independently correct + unit-testable.
  if [ -z "${VOYAGE_API_KEY:-}" ]; then
    printf '%s\n' "${_pool[@]}" | _memory_blended_topk "$topk"
    return 0
  fi

  # documents[] = the 9th (rerank_text) column of each pool row, IN POOL ORDER
  # so the returned .index maps straight back into _pool. jq -R reads each line
  # as a JSON string; -s slurps them to an array.
  local _docs_json
  _docs_json=$(printf '%s\n' "${_pool[@]}" | awk -F'\t' '{print $9}' | jq -R . | jq -s . 2>/dev/null)

  local _resp="" _order=""
  if [ -n "$_docs_json" ] && [ "$_docs_json" != "null" ]; then
    # VOYAGE_API_KEY travels ONLY in the Authorization header (never logged).
    _resp=$(curl -s --max-time 30 https://api.voyageai.com/v1/rerank \
      -H "Authorization: Bearer ${VOYAGE_API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$(jq -nc --arg q "$query" --argjson docs "$_docs_json" --argjson k "$topk" \
            --arg model "${EMBED_RERANK_MODEL:-rerank-2.5}" \
            '{query:$q, documents:$docs, model:$model, top_k:$k}')" 2>/dev/null)
    # Voyage returns the ranking under .data (current API) or .results (older),
    # each element {index, relevance_score}. Accept either envelope and sort by
    # relevance_score DESC ourselves rather than trusting response order; .index
    # is 0-based into documents[].
    _order=$(printf '%s' "$_resp" | jq -r \
      '(.data // .results // []) | sort_by(-(.relevance_score // 0)) | .[].index' 2>/dev/null)
  fi

  # Fail-soft arm 2 (any rerank error / empty result) → blended top-k unchanged.
  if [ -z "$_order" ]; then
    echo "memory.sh WARN: rerank unavailable (error/empty response) — DEGRADED to blended order" >&2
    printf '%s\n' "${_pool[@]}" | _memory_blended_topk "$topk"
    return 0
  fi

  # Reorder by the reranked indices, cut to top-k, strip the 9th column.
  local _idx _count=0
  while IFS= read -r _idx; do
    [ "$_count" -ge "$topk" ] && break
    case "$_idx" in ''|*[!0-9]*) continue ;; esac
    if [ "$_idx" -lt "$_n" ]; then
      printf '%s\n' "${_pool[$_idx]}" | cut -f1-8
      _count=$((_count+1))
    fi
  done <<< "$_order"
}

# =============================================================
# DEGRADED SEARCH: lexical-only arm (no embedding available)
# Called by memory_search when memory_get_embedding yields nothing (unset
# VOYAGE_API_KEY, or a Voyage outage). Same filters + fences + 8-column TSV
# contract as memory_search; ranking is BM25-style lexical blended with
# recency:
#   lex     = r / (r + 0.05) where r = ts_rank(content_tsv, plainto_tsquery)
#   final   = 0.80*lex + 0.20*recency   (mirrors the hybrid query's
#             empty-tsquery renormalization — there is no vec channel here)
# min_score is NOT applied: it is a vec-similarity floor by definition (see
# the memory_search header) and no vec channel exists in this arm — the
# @@ tsquery match is the relevance gate (stopword-only queries yield an
# empty tsquery and honestly return 0 rows). The similarity column carries
# lex so the 8-col parsers (search-memory.sh, framework/sources/org.py)
# stay shape-compatible.
# =============================================================
memory_search_lexical() {
  local query="$1"
  local source_type_filter="${2:-}"
  local officer_filter="${3:-}"
  local limit="${4:-10}"
  local as_of="${5:-}"

  local cid_scope
  cid_scope="$(memory_cabinet_scope)"

  psql "$NEON_CONNECTION_STRING" -q -t -A -F $'\t' \
    -v query="$query" \
    -v limit="$limit" \
    -v st_filter="${source_type_filter:-}" \
    -v of_filter="${officer_filter:-}" \
    -v as_of="${as_of:-}" \
    -v cid="$cid_scope" \
    2>/dev/null <<'SQLEOF'
WITH params AS (
  SELECT plainto_tsquery('english', :'query') AS tsq
),
candidates AS (
  SELECT m.*, ts_rank(m.content_tsv, p.tsq) AS lex_rank
  FROM cabinet_memory m CROSS JOIN params p
  WHERE m.superseded_by IS NULL
    AND numnode(p.tsq) > 0
    AND m.content_tsv @@ p.tsq
    AND (:'st_filter' = '' OR m.source_type = ANY(string_to_array(:'st_filter', ',')))
    AND (:'of_filter' = '' OR m.officer = :'of_filter')
    -- Tenant fence: identical to memory_search (resolved id OR legacy 'main').
    AND (:'cid' = '' OR m.cabinet_id = :'cid' OR m.cabinet_id = 'main')
    -- Fail-closed content-time fence: under --as-of, NULL-timestamp rows are excluded.
    AND (:'as_of' = '' OR (m.source_created_at IS NOT NULL
                           AND m.source_created_at <= NULLIF(:'as_of', '')::timestamptz))
  ORDER BY ts_rank(m.content_tsv, p.tsq) DESC
  LIMIT GREATEST((:'limit')::int * 5, 50)
),
scored AS (
  SELECT c.*,
    CASE WHEN c.source_created_at IS NULL THEN 0.5
         ELSE exp(-ln(2.0) * GREATEST(extract(epoch FROM (now() - c.source_created_at)), 0) / (90.0 * 86400.0))
    END AS recency,
    c.lex_rank / (c.lex_rank + 0.05) AS lex
  FROM candidates c
),
final AS (
  SELECT s.*, 0.80 * s.lex + 0.20 * s.recency AS final_score
  FROM scored s
)
SELECT
  source_type,
  COALESCE(officer, sender, 'n/a') as who,
  to_char(source_created_at, 'YYYY-MM-DD HH24:MI') as when_at,
  round(lex::numeric, 3) as similarity,
  round(final_score::numeric, 3) as score,
  COALESCE(NULLIF(regexp_replace(LEFT(metadata->>'trust', 32), E'[\t\n\r ]+', '', 'g'), ''), 'derived') as trust,
  regexp_replace(LEFT(COALESCE(summary, content), 200), E'[\t\n\r]+', ' ', 'g') as preview,
  COALESCE(source_id, id::text) as ref
FROM final
ORDER BY final_score DESC
LIMIT (:'limit')::int;
SQLEOF
}
