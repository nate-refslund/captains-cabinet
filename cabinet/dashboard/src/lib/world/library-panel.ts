/**
 * library-panel.ts — PURE helpers + the lane-2 search contract for the
 * world Library card (spec v2 §5.2 Memory Library / §9.2 library query
 * dialog / P6 "GET-only library/product search into cards").
 *
 * Doctrine constraints of this module:
 *  - lib/world tree: deterministic, no wall clock, no unseeded RNG, no DB
 *    imports (the retired Library vector store stays retired — the card's
 *    browse/read data comes from lib/vault's confined resolvers via the
 *    /api/world/library/* routes, and search comes from the lane-2 API
 *    over the cabinet_memory store).
 *  - Search query text is UNTRUSTED user input: it rides the lane-2 GET
 *    request's `q` search param as DATA (buildLane2SearchUrl —
 *    URLSearchParams-encoded; the landed route binds it as a pg
 *    parameter) — never interpolated into a URL path, SQL, or shell
 *    string anywhere in this module.
 *  - Backend responses are UNTRUSTED data: normalizeLane2Response coerces
 *    defensively (type-checks every field, caps lengths, drops paths that
 *    are not plain vault-relative paths). Rendering stays the caller's
 *    job through React text nodes / VaultMarkdown — never raw HTML.
 */

// ============================================================
// Payload types (exported for the card + routes + tests)
// ============================================================

export interface WorldLibraryEntry {
  name: string
  relPath: string
  kind: 'dir' | 'file'
}

export interface WorldLibraryBrowsePayload {
  vaultConfigured: boolean
  relPath: string
  entries: WorldLibraryEntry[]
}

export interface WorldLibraryNotePayload {
  relPath: string
  title: string
  /** Parsed frontmatter — DATA only; the card prints values as React text. */
  frontmatter: Record<string, unknown> | null
  /** Markdown body with wikilinks already rewritten to internal links by the
   *  server (the exact /library reader pipeline). Rendered ONLY via
   *  VaultMarkdown. */
  markdown: string
}

export interface WorldLibrarySearchHit {
  /** Opaque backend ref (record id / memory source id) — display only. */
  ref: string
  title: string
  snippet: string
  score: number | null
  /** Vault-relative note path when the backend provides one (opens in-card
   *  through the confined note route), else null. */
  vaultPath: string | null
}

export interface WorldLibrarySearchPayload {
  /** False = the search backend is not reachable/landed yet — the card says
   *  so honestly instead of guessing. Browse/read stay independent of it. */
  available: boolean
  hits: WorldLibrarySearchHit[]
  /** Lane-2 degrade parity: true = the semantic arm was down and the
   *  lexical-only fallback ranked these (the card says so, honestly). */
  degraded: boolean
  /** True = the lane-2 rate limit (429) answered — try again shortly. */
  rateLimited: boolean
  /** Human-readable provenance line for the card's PROOF strip. */
  backend: string
}

// ============================================================
// The lane-2 search contract (ONE place — tracks the LANDED route:
// GET /api/library/search?q=…&limit=… → { results: LibrarySearchHit[],
// degraded } with hit fields {snippet, source_type, source_id, score,
// when_at, libraryPath?}; 429 = rate-limited; docs/runbooks/
// library-search-2026-07-17.md "Querying the Library programmatically")
// ============================================================

/** The lane-2 library-search API (server-side call target of the adapter
 *  route): the Library search over the cabinet_memory store. */
export const LANE2_SEARCH_ENDPOINT = '/api/library/search'

/** The lane-2 route's own limit clamp (memory-search MAX_LIMIT). */
export const LANE2_MAX_LIMIT = 20

/** Provenance string the card's PROOF strip cites. */
export const LANE2_BACKEND_LABEL = `${LANE2_SEARCH_ENDPOINT} → cabinet_memory`

/** Build the lane-2 request URL. The query is UNTRUSTED text and rides the
 *  `q` search param as DATA (URLSearchParams encoding — never path text,
 *  never SQL; the lane-2 route binds it as a pg parameter). Server-side use
 *  only (the world card itself issues plain GET fetches to
 *  /api/world/library/*). */
export function buildLane2SearchUrl(origin: string, query: string, limit: number): URL {
  const u = new URL(LANE2_SEARCH_ENDPOINT, origin)
  u.searchParams.set('q', query)
  u.searchParams.set('limit', String(Math.max(1, Math.min(LANE2_MAX_LIMIT, Math.floor(limit)))))
  return u
}

const MAX_HITS = 25
const MAX_TITLE = 200
const MAX_SNIPPET = 500
const MAX_PATH = 512

function firstString(...vals: unknown[]): string | null {
  for (const v of vals) {
    if (typeof v === 'string' && v.trim()) return v
  }
  return null
}

function finiteNumber(...vals: unknown[]): number | null {
  for (const v of vals) {
    if (typeof v === 'number' && Number.isFinite(v)) return v
  }
  return null
}

/** Accept ONLY a plain vault-relative path: non-empty string, no NUL, not
 *  absolute (posix or windows), no `..` segment, no backslashes. Anything
 *  else → null. (Defense in depth — the note route re-confines via
 *  lib/vault resolveInVault regardless.) */
export function safeRelPath(p: unknown): string | null {
  if (typeof p !== 'string') return null
  const t = p.trim()
  if (!t || t.length > MAX_PATH) return null
  if (t.includes('\0') || t.includes('\\')) return null
  if (t.startsWith('/') || /^[a-zA-Z]:/.test(t)) return null
  const segs = t.split('/')
  if (segs.some((s) => s === '..' || s === '')) return null
  return t
}

interface Lane2RowLike {
  [key: string]: unknown
}

/** Display title for a lane-2 hit: the vault note's basename (extension
 *  stripped, dashes/underscores spaced) when the hit maps to a note, else
 *  the source id, else the source type. Pure string cosmetics — data only. */
function titleForRow(row: Lane2RowLike, vaultPath: string | null): string {
  if (vaultPath) {
    const base = vaultPath.split('/').pop() ?? vaultPath
    const pretty = base.replace(/\.(md|markdown)$/i, '').replace(/[-_]+/g, ' ').trim()
    if (pretty) return pretty
  }
  return firstString(row.title, row.source_id, row.source_type) ?? '(untitled)'
}

/**
 * Normalize a lane-2 search response (unknown JSON) to WorldLibrarySearchHit
 * rows. Primary shape = the LANDED contract ({snippet, source_type,
 * source_id, score, when_at, libraryPath?}); the retired record-store shape
 * ({record_id,title,preview,similarity}) is tolerated defensively.
 * Garbage in → [] out; every field type-checked; lengths capped; row count
 * capped; only plain vault-relative paths survive.
 */
export function normalizeLane2Response(json: unknown): WorldLibrarySearchHit[] {
  if (!json || typeof json !== 'object') return []
  const container = json as { results?: unknown; hits?: unknown }
  const rows = Array.isArray(container.results)
    ? container.results
    : Array.isArray(container.hits)
      ? container.hits
      : null
  if (!rows) return []

  const out: WorldLibrarySearchHit[] = []
  for (const raw of rows) {
    if (out.length >= MAX_HITS) break
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
    const row = raw as Lane2RowLike

    const snippet = firstString(row.snippet, row.preview, row.content, row.excerpt) ?? ''
    const vaultPath = safeRelPath(firstString(row.libraryPath, row.vault_path, row.vaultPath))
    const ref = firstString(row.source_id, row.record_id, row.id, row.ref) ?? ''
    const whenAt = firstString(row.when_at)
    if (!snippet && !ref && !vaultPath) continue

    const title = titleForRow(row, vaultPath)
    out.push({
      ref: whenAt ? `${ref} · ${whenAt}` : ref,
      title: title.slice(0, MAX_TITLE),
      snippet: snippet.slice(0, MAX_SNIPPET),
      score: finiteNumber(row.score, row.similarity, row.rank),
      vaultPath,
    })
  }
  return out
}

/** True when a lane-2 response body declares the lexical-only degrade arm. */
export function lane2Degraded(json: unknown): boolean {
  return Boolean(
    json && typeof json === 'object' && (json as { degraded?: unknown }).degraded === true
  )
}

// ============================================================
// In-card navigation helpers (pure)
// ============================================================

/** The internal reader roots an in-note href may address: /library (the
 *  reader) and /vault (its permanent redirect alias — older notes may carry
 *  literal /vault links). */
const INTERNAL_ROOTS = ['/vault', '/library'] as const

/**
 * True when an href's PATH part addresses the internal library reader
 * (either root, bare or nested; fragments/queries ignored; exact prefixes
 * only) — INDEPENDENT of whether it maps to a safe vault relpath. The card
 * pairs this with overlayPathFromHref: an internal-shaped href that does
 * NOT map (a note-authored '/library/%zz' or '/library/../x') is rendered
 * INERT — it must never fall through to next/link and same-tab-navigate
 * the world away.
 */
export function isInternalLibraryHref(href: unknown): boolean {
  if (typeof href !== 'string' || !href) return false
  const cut = href.split(/[?#]/, 1)[0]
  return INTERNAL_ROOTS.some((root) => cut === root || cut.startsWith(root + '/'))
}

/**
 * Map an internal library href to a vault-relative path for IN-CARD
 * navigation: '/vault/a/b.md' | '/library/a/b.md' → 'a/b.md'; the bare
 * roots → ''. Exact route prefixes only (never a sibling like '/vaultfoo');
 * fragments/queries are stripped; percent-encoded segments are decoded
 * (mirroring vaultHref's per-segment encoding). Anything else — external,
 * protocol, mailto, unresolved sentinel, or an internal-shaped href whose
 * path fails decode/safeRelPath — → null (the card distinguishes the last
 * case via isInternalLibraryHref and inerts it; genuinely external anchors
 * keep their own hardened behavior — the card never invents navigation).
 */
export function overlayPathFromHref(href: unknown): string | null {
  if (typeof href !== 'string' || !href) return null
  const cut = href.split(/[?#]/, 1)[0]
  let rest: string | null = null
  for (const root of INTERNAL_ROOTS) {
    if (cut === root) return ''
    if (cut.startsWith(root + '/')) {
      rest = cut.slice(root.length + 1)
      break
    }
  }
  if (rest === null) return null
  let decoded: string
  try {
    decoded = rest
      .split('/')
      .filter(Boolean)
      .map((s) => decodeURIComponent(s))
      .join('/')
  } catch {
    return null // malformed percent-encoding — refuse, never guess
  }
  return safeRelPath(decoded) ?? (decoded === '' ? '' : null)
}

/** Parent of a vault-relative dir/file path ('' at the root). */
export function parentPath(rel: string): string {
  const t = rel.replace(/\/+$/, '')
  const i = t.lastIndexOf('/')
  return i === -1 ? '' : t.slice(0, i)
}

/** Breadcrumb rows for a vault-relative path (root excluded). */
export function crumbsFor(rel: string): Array<{ label: string; path: string }> {
  const out: Array<{ label: string; path: string }> = []
  let acc = ''
  for (const part of rel.split('/').filter(Boolean)) {
    acc = acc ? `${acc}/${part}` : part
    out.push({ label: part, path: acc })
  }
  return out
}
