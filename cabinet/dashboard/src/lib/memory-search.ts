/**
 * memory-search.ts — server-side Library search over the cabinet_memory store.
 *
 * This is the DASHBOARD arm of the org's ONE search engine
 * (cabinet/scripts/lib/memory.sh memory_search). It deliberately mirrors that
 * hybrid CTE — vector candidates (HNSW) + lexical (content_tsv) + recency
 * blend, superseded_by fence, cabinet_id tenant fence, vec min_score floor —
 * rather than inventing a second ranking. Where memory.sh degrades to its
 * lexical-only arm on a missing/broken embedding provider, so does this
 * module. The Voyage cross-encoder RERANK stage (memory.sh R2) is NOT
 * mirrored here (one extra provider round-trip per keystroke is the wrong
 * economy for a UI search box); recorded as a residual in
 * docs/runbooks/library-search-2026-07-17.md.
 *
 * PARITY NOTE: the blended weights / floors / half-life below must track
 * memory.sh's RANKING-BLOCK (0.60*vec + 0.25*lex + 0.15*recency; empty
 * tsquery → 0.80*vec + 0.20*recency; lexical arm 0.80*lex + 0.20*recency;
 * 90-day half-life; vec floor default 0.45). memory-search.test.ts pins the
 * constants so drift is loud.
 *
 * SECURITY (Corridor-gated):
 *   - Query text is UNTRUSTED. It reaches Postgres exclusively as a pg bind
 *     parameter ($n) — never interpolated into SQL program text. The SQL
 *     strings below are static module constants.
 *   - READ-ONLY: this module issues single SELECT statements against
 *     cabinet_memory only. It never references the RETIRED
 *     library_records/library_spaces tables and contains no mutation SQL.
 *   - SOURCE FENCE: results are hard-limited to ORG_KNOWLEDGE_SOURCE_TYPES
 *     (bound as a parameter, no empty-filter bypass arm). Conversational /
 *     private classes (telegram_dm, telegram_group, session_memory,
 *     officer_trigger, correction, captain_decision, reflection,
 *     working_note, skill, role_definition, golden_eval) are structurally
 *     unreachable from this surface — there is no client-controllable type
 *     parameter.
 *   - KEYS: VOYAGE_API_KEY / NEON_CONNECTION_STRING are read from server env
 *     only, never logged, never surfaced in responses. The query text goes to
 *     the embedding provider in the TLS request body (exactly as memory.sh
 *     does) and nowhere else.
 *   - NO filesystem access. deriveLibraryPath() only rewrites a source_id
 *     string; the Library reader (/library) re-confines the path via
 *     lib/vault.ts resolveInVault() when the user navigates.
 */

import { query } from './db'

// ============================================================
// Org-knowledge source fence
// ============================================================

/**
 * The org-knowledge classes exposed to the Library search surface. Values are
 * verified against the live writers (2026-07-17):
 *   - product_brain      memory-reconcile.sh / post-file-write hooks — the org
 *                        VAULT corpus (source_id = repo-relative path, e.g.
 *                        `vault/decisions/x.md`; legacy `product-brain/…`)
 *   - framework_doc      memory-reconcile.sh — docs/**.md reference tree
 *   - framework_file     memory-reconcile.sh — constitution/safety base files
 *   - captain_law_summary memory-distill.py — distilled captain-law digests
 *   - research_brief     backfill-memory.sh — research briefs
 *   - experience_record  record-experience.sh — officer experience records
 *   - library_record     lib/library.sh + lib/library.ts mirror queue — the
 *                        retired Library's records (search-continuity path)
 *   - product_spec       memory-reconcile.sh — shared/interfaces/product-specs
 *   - tech_radar         memory-reconcile.sh — shared/interfaces/tech-radar.md
 *   - consolidated_belief officer retro/reflection skills
 *                        (memory/skills/individual-reflection.md +
 *                        cross-officer-retro.md) — each cycle terminates in
 *                        3–5 distilled org beliefs queued via
 *                        memory_queue_embed with trust=reflection; the
 *                        terminal step is enforced by
 *                        cabinet/scripts/tests/test_memory_distill.py. These
 *                        are org knowledge BY DESIGN (compressed lessons,
 *                        not conversation), so the Library must surface
 *                        them — excluding the class would silently hide the
 *                        first retro's output. (Review fix 2026-07-17: the
 *                        earlier "no writer exists" rationale was wrong.)
 */
export const ORG_KNOWLEDGE_SOURCE_TYPES = [
  'product_brain',
  'framework_doc',
  'framework_file',
  'captain_law_summary',
  'research_brief',
  'experience_record',
  'library_record',
  'product_spec',
  'tech_radar',
  'consolidated_belief',
] as const

export type OrgKnowledgeSourceType = (typeof ORG_KNOWLEDGE_SOURCE_TYPES)[number]

// ============================================================
// Result contract (the world-librarian API shape — see
// docs/runbooks/library-search-2026-07-17.md "Querying the Library
// programmatically")
// ============================================================

export interface LibrarySearchHit {
  [key: string]: unknown
  /** Whitespace-collapsed head of COALESCE(summary, content) — plain text. */
  snippet: string
  source_type: string
  /** Natural key (file path, `lib-<id>`, record slug) or the row id. */
  source_id: string
  /** Blended relevance score (higher = better). */
  score: number
  /** `YYYY-MM-DD HH24:MI` of source_created_at, or null. */
  when_at: string | null
  /** Vault-relative path when the hit maps to a vault note (product_brain
   *  rows only) — link target `/library/<libraryPath>` (LIB-IDENT landed
   *  2026-07-17: /library is the vault reader, /vault redirects there;
   *  see libraryHref() in components/library/LibrarySearch.tsx). */
  libraryPath?: string
}

export interface LibrarySearchResult {
  hits: LibrarySearchHit[]
  /** true when the semantic arm was unavailable and the lexical-only
   *  fallback ranked the results (memory.sh degrade parity). */
  degraded: boolean
}

const MAX_LIMIT = 20
const DEFAULT_MIN_SCORE = 0.45
const EMBED_TIMEOUT_MS = 8_000
/** voyage-4-large accepts ~32K tokens; memory.sh cuts at 32000 chars. */
const EMBED_MAX_CHARS = 32_000

// ============================================================
// SQL — static constants, exported so tests can assert on the exact program
// text (read-only, bind-only, fenced). Mirrors memory.sh memory_search()'s
// RANKING-BLOCK minus the rerank stage and the officer/as_of filters.
// ============================================================

/**
 * Hybrid arm. Binds:
 *   $1 embedding literal (`[0.1,…]`) → $1::vector
 *   $2 query text (plainto_tsquery input)
 *   $3 comma-joined source-type allowlist (string_to_array parity with
 *      memory.sh; NO empty-string bypass arm — the fence is unconditional)
 *   $4 cabinet scope ('' = unscoped; else id, OR legacy 'main' rows)
 *   $5 vec min_score floor
 *   $6 limit
 */
export const HYBRID_SQL = `
WITH params AS (
  SELECT plainto_tsquery('english', $2) AS tsq
),
candidates AS (
  SELECT m.*,
    (1 - (m.embedding <=> $1::vector)) AS vec_sim
  FROM cabinet_memory m
  WHERE m.superseded_by IS NULL
    AND m.source_type = ANY(string_to_array($3, ','))
    AND ($4 = '' OR m.cabinet_id = $4 OR m.cabinet_id = 'main')
  ORDER BY m.embedding <=> $1::vector
  LIMIT GREATEST($6::int * 5, 50)
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
    CASE WHEN s.has_lex
         THEN 0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency
         ELSE 0.80 * s.vec_sim + 0.20 * s.recency
    END AS final_score
  FROM scored s
)
SELECT
  source_type,
  COALESCE(source_id, id::text) AS source_id,
  round(final_score::numeric, 3)::float8 AS score,
  to_char(source_created_at, 'YYYY-MM-DD HH24:MI') AS when_at,
  regexp_replace(LEFT(COALESCE(summary, content), 300), E'[\\t\\n\\r]+', ' ', 'g') AS snippet
FROM final
WHERE vec_sim >= $5::float8
ORDER BY final_score DESC
LIMIT $6::int`

/**
 * Lexical-only degrade arm (memory.sh memory_search_lexical parity). Binds:
 *   $1 query text  $2 comma-joined allowlist  $3 cabinet scope  $4 limit
 * min_score is deliberately NOT applied — it is a vec-similarity floor by
 * definition and no vec channel exists here; the @@ tsquery match is the
 * relevance gate (stopword-only queries honestly return 0 rows).
 */
export const LEXICAL_SQL = `
WITH params AS (
  SELECT plainto_tsquery('english', $1) AS tsq
),
candidates AS (
  SELECT m.*, ts_rank(m.content_tsv, p.tsq) AS lex_rank
  FROM cabinet_memory m CROSS JOIN params p
  WHERE m.superseded_by IS NULL
    AND numnode(p.tsq) > 0
    AND m.content_tsv @@ p.tsq
    AND m.source_type = ANY(string_to_array($2, ','))
    AND ($3 = '' OR m.cabinet_id = $3 OR m.cabinet_id = 'main')
  ORDER BY ts_rank(m.content_tsv, p.tsq) DESC
  LIMIT GREATEST($4::int * 5, 50)
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
  COALESCE(source_id, id::text) AS source_id,
  round(final_score::numeric, 3)::float8 AS score,
  to_char(source_created_at, 'YYYY-MM-DD HH24:MI') AS when_at,
  regexp_replace(LEFT(COALESCE(summary, content), 300), E'[\\t\\n\\r]+', ' ', 'g') AS snippet
FROM final
ORDER BY final_score DESC
LIMIT $4::int`

// ============================================================
// Env resolution (memory.sh parity)
// ============================================================

/** Search-side tenant scope: '' = unscoped (CABINET_ID unset — pre-scoping
 *  behavior); invalid charset resolves 'main', matching memory.sh's
 *  memory_cabinet_scope so this surface reads exactly what the box writes. */
function cabinetScope(): string {
  const cid = process.env.CABINET_ID || ''
  if (cid && !/^[A-Za-z0-9_-]+$/.test(cid)) {
    console.warn(
      "[library-search] CABINET_ID invalid charset — scoping search to 'main'"
    )
    return 'main'
  }
  return cid
}

/** Vec-similarity floor; junk env falls back to the default (memory.sh
 *  parity: plain non-negative decimal only). */
function minScore(): number {
  const raw = process.env.CABINET_MEMORY_MIN_SCORE || ''
  if (/^[0-9]*\.?[0-9]+$/.test(raw)) return parseFloat(raw)
  return DEFAULT_MIN_SCORE
}

function clampLimit(limit: number | undefined): number {
  if (typeof limit !== 'number' || !Number.isFinite(limit)) return MAX_LIMIT
  return Math.min(Math.max(Math.trunc(limit), 1), MAX_LIMIT)
}

// ============================================================
// Query embedding (EMBED-SEAM parity; fail-soft → lexical arm)
// ============================================================

/**
 * Embed the query server-side via the seam-configured provider. Returns null
 * on ANY failure (unwired provider, missing key, timeout, non-200, malformed
 * or wrong-dims response) — the caller degrades to the lexical arm, exactly
 * like memory.sh. Never throws; never logs the query text or the key.
 */
async function embedQuery(q: string): Promise<number[] | null> {
  // EMBED-SEAM dispatch parity: only the "voyage" provider is wired.
  const provider = (process.env.EMBED_PROVIDER || 'voyage').toLowerCase()
  if (provider !== 'voyage') return null
  const key = process.env.VOYAGE_API_KEY
  if (!key) return null
  const dims = Number.parseInt(process.env.EMBED_DIMS || '1024', 10) || 1024

  // WIRE-TEXT PARITY (review fix 2026-07-17): memory.sh memory_get_embedding
  // preprocesses the text as `echo "$text" | tr '\n' ' ' | cut -c1-32000` —
  // interior newlines become spaces and echo's appended newline becomes ONE
  // trailing space, both BEFORE the 32000-char cut. The store's vectors were
  // built from those bytes, so this arm must embed byte-identical wire text:
  // measured live, the bare string shifts cosine similarity ~0.06, enough to
  // cross the 0.45 vec floor and blank on-topic results the shell engine
  // returns. Pinned by memory-search.test.ts ("wire-text parity").
  const wire = (q.replace(/\n/g, ' ') + ' ').slice(0, EMBED_MAX_CHARS)

  try {
    const res = await fetch('https://api.voyageai.com/v1/embeddings', {
      method: 'POST',
      headers: {
        // The key travels ONLY in this header — never logged, never returned.
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        input: [wire],
        model: process.env.EMBED_MODEL || 'voyage-4-large',
      }),
      signal: AbortSignal.timeout(EMBED_TIMEOUT_MS),
    })
    if (!res.ok) return null
    const data = (await res.json()) as {
      data?: Array<{ embedding?: unknown }>
    }
    const emb = data?.data?.[0]?.embedding
    if (
      !Array.isArray(emb) ||
      emb.length !== dims ||
      !emb.every((x) => typeof x === 'number' && Number.isFinite(x))
    ) {
      return null
    }
    return emb as number[]
  } catch {
    // Timeout / network / JSON error — degrade silently (the route reports
    // `degraded: true`); details never include the query.
    return null
  }
}

// ============================================================
// libraryPath derivation (string rewrite only — NO filesystem access)
// ============================================================

const MD_EXT_RE = /\.(md|markdown)$/i

/**
 * Map a hit onto the vault browser when possible. Only product_brain
 * rows carry a repo-relative vault path as source_id (`vault/…` current,
 * `product-brain/…` legacy). The returned path is vault-relative and
 * conservatively validated (no NUL/backslash, not absolute, no empty/./..
 * segments, markdown only); the browser route re-confines it through
 * lib/vault.ts resolveInVault() on navigation, so this derivation is a UX
 * affordance, never a security boundary.
 */
export function deriveLibraryPath(
  sourceType: string,
  sourceId: string | null | undefined
): string | undefined {
  if (sourceType !== 'product_brain' || !sourceId) return undefined
  let rel: string | null = null
  for (const prefix of ['vault/', 'product-brain/']) {
    if (sourceId.startsWith(prefix)) {
      rel = sourceId.slice(prefix.length)
      break
    }
  }
  if (!rel) return undefined
  if (rel.includes('\0') || rel.includes('\\')) return undefined
  if (rel.startsWith('/')) return undefined
  if (!MD_EXT_RE.test(rel)) return undefined
  const segments = rel.split('/')
  if (segments.some((s) => s === '' || s === '.' || s === '..')) {
    return undefined
  }
  return rel
}

// ============================================================
// The search
// ============================================================

interface SearchRow {
  [key: string]: unknown
  source_type: string
  source_id: string
  score: number
  when_at: string | null
  snippet: string
}

/**
 * Search the org-knowledge slice of cabinet_memory. Hybrid when the query can
 * be embedded server-side; lexical-only otherwise (degraded: true). `q` is
 * untrusted and travels only as a bind parameter.
 */
export async function searchMemory(
  q: string,
  limit?: number
): Promise<LibrarySearchResult> {
  const lim = clampLimit(limit)
  const cid = cabinetScope()
  const typesParam = ORG_KNOWLEDGE_SOURCE_TYPES.join(',')

  const embedding = await embedQuery(q)

  let rows: SearchRow[]
  let degraded = false
  if (embedding) {
    rows = await query<SearchRow>(HYBRID_SQL, [
      JSON.stringify(embedding),
      q,
      typesParam,
      cid,
      minScore(),
      lim,
    ])
  } else {
    degraded = true
    rows = await query<SearchRow>(LEXICAL_SQL, [q, typesParam, cid, lim])
  }

  const hits: LibrarySearchHit[] = rows.map((r) => {
    const hit: LibrarySearchHit = {
      snippet: typeof r.snippet === 'string' ? r.snippet : '',
      source_type: r.source_type,
      source_id: r.source_id,
      score: typeof r.score === 'number' ? r.score : Number(r.score ?? 0),
      when_at: r.when_at ?? null,
    }
    const libraryPath = deriveLibraryPath(r.source_type, r.source_id)
    if (libraryPath) hit.libraryPath = libraryPath
    return hit
  })

  return { hits, degraded }
}
