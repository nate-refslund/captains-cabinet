/**
 * vault-graph.ts — FILESYSTEM wikilink graph + backlinks for the Library
 * reader (/library). Captain ruling 2026-07-17: the reader (and its graph)
 * returned; the retired DB graph (library_record_links over pg) stays
 * retired — this module rebuilds the graph from the vault markdown corpus
 * with ZERO database. Every path flows through the confinement layer in
 * lib/vault.ts:
 *
 *   - NODES: every markdown note found by a bounded recursive walk built ON
 *     listDir — which lstat's entries, NEVER follows symlinks, and
 *     re-confines every child through resolveInVault. A symlink-escape note
 *     therefore never enters the graph. Depth/file caps mirror the vault.ts
 *     basename-index walk (8 / 20000).
 *   - EDGES: per note, parseWikilinks(body) → resolveNoteTarget against the
 *     confined basename index; only targets that resolve to an in-vault,
 *     in-graph note become edges (deduped source→target; self-loops
 *     dropped). A hostile target ([[../../etc/passwd]], [[/abs/path]])
 *     resolves to null → no edge. Edge harvesting is parse-bounded (32KB
 *     per note, linear ReDoS guards via parseWikilinksBounded, corpus-wide
 *     byte budget) — over-bound bodies keep their node, skip their edges.
 *   - READ-ONLY + DB-FREE: no fs writes, no '@/lib/db', no pg, no query(),
 *     no '@/lib/library'. Pinned by library-route.test.ts.
 *
 * The graph is computed server-side and handed to the client canvas as
 * serialized props — there is NO API route for it (zero new endpoints).
 * Short TTL cache keyed on the resolved vault root; test seam below.
 *
 * Docs: docs/runbooks/vault-browser-2026-07-17.md.
 */

import {
  hasVault,
  listDir,
  readNote,
  buildBasenameIndex,
  resolveNoteTarget,
  vaultRoot,
} from './vault'
import { parseWikilinksBounded } from './vault-wikilinks'

// ============================================================
// Types (serializable — cross the server→client boundary as props)
// ============================================================

export interface VaultGraphNode {
  // Index signature mirrors the retired LibraryGraphNode shape — the
  // force-graph client decorates nodes (x/y/vx/vy) through an indexed type.
  [key: string]: unknown
  /** Vault-relative note path — doubles as the navigation target. */
  id: string
  /** Frontmatter `title` if present, else the basename without extension. */
  title: string
  /** Top-level vault folder ('' for root-level notes) — the grouping/color
   *  analog of the retired graph's Space. */
  dir: string
  /** In+out wikilink degree (deduped edges). */
  degree: number
}

export interface VaultGraphEdge {
  [key: string]: unknown
  /** Source note relpath. */
  source: string
  /** Target note relpath (always an in-vault, in-graph note). */
  target: string
}

export interface VaultGraphData {
  nodes: VaultGraphNode[]
  edges: VaultGraphEdge[]
  /** True when the bounded walk hit the depth/file caps OR edge harvesting
   *  hit the corpus parse budget — the graph shown is a slice, not the whole
   *  corpus. */
  truncated: boolean
}

export interface VaultBacklink {
  sourceRel: string
  sourceTitle: string
  sourceDir: string
}

// Caps mirror lib/vault.ts WALK_DEPTH_CAP / WALK_FILE_CAP (kept local — the
// vault module deliberately does not export its internals).
const GRAPH_DEPTH_CAP = 8
const GRAPH_FILE_CAP = 20000
// Per-note edge-harvest parse cap — DELIBERATELY far below the 200KB
// single-note rewrite bound (2026-07-17 review fix): the graph parses the
// WHOLE corpus, and it rebuilds on every cold note view via getBacklinks, so
// one pathological note at a generous cap would stall every page, not one.
// 32KB is ample for real notes; larger bodies keep their node, skip edges.
// parseWikilinksBounded adds the linear no-`]]` / max-starts ReDoS guards on
// top of this size gate.
const GRAPH_PARSE_MAX_BYTES = 32_768
// Corpus-wide edge-harvest budget: the sum of parsed body bytes per build is
// bounded so many mid-size notes cannot stack into a long synchronous build
// (20k files × 32KB would otherwise admit ~640MB of parsing). Beyond it,
// remaining notes keep their nodes, skip edges, and the graph is flagged
// truncated.
const GRAPH_PARSE_TOTAL_BUDGET_BYTES = 8_000_000
const GRAPH_TTL_MS = 30_000

const MD_EXT = /\.(md|markdown)$/i

interface GraphCache {
  root: string
  builtAt: number
  data: VaultGraphData
}
let _cache: GraphCache | null = null

/** Test seam: drop the memoized graph. */
export function resetVaultGraphCache(): void {
  _cache = null
}

function topLevelDir(rel: string): string {
  const i = rel.indexOf('/')
  return i === -1 ? '' : rel.slice(0, i)
}

function noteTitle(rel: string, frontmatter: Record<string, unknown> | null): string {
  const t = frontmatter?.title
  if (typeof t === 'string' && t.trim()) return t.trim()
  return rel.split('/').pop()?.replace(MD_EXT, '') || rel
}

/**
 * Build {nodes, edges} for the whole (bounded) vault corpus. Pure read: the
 * only filesystem access is through listDir/readNote/buildBasenameIndex,
 * which confine every path. Cached ~30s per resolved root.
 */
export function buildVaultGraph(): VaultGraphData {
  const root = vaultRoot()
  if (!root || !hasVault()) return { nodes: [], edges: [], truncated: false }

  const now = Date.now()
  if (_cache && _cache.root === root && now - _cache.builtAt < GRAPH_TTL_MS) {
    return _cache.data
  }

  // 1. Collect every note relpath via the confined lister (symlinks are
  //    skipped INSIDE listDir; each entry was re-confined there).
  const rels: string[] = []
  let truncated = false
  const walk = (rel: string, depth: number): void => {
    if (depth > GRAPH_DEPTH_CAP) {
      truncated = true
      return
    }
    let entries
    try {
      entries = listDir(rel)
    } catch {
      return // vanished/denied mid-walk — skip subtree
    }
    for (const e of entries) {
      if (rels.length >= GRAPH_FILE_CAP) {
        truncated = true
        return
      }
      if (e.kind === 'dir') walk(e.relPath, depth + 1)
      else rels.push(e.relPath)
    }
  }
  walk('', 0)

  // 2. Read each note once; harvest title + resolved wikilink edges.
  const index = buildBasenameIndex()
  const nodeSet = new Set(rels)
  const titles = new Map<string, string>()
  const edgeKeys = new Set<string>()
  const edges: VaultGraphEdge[] = []

  let parsedBytes = 0
  for (const rel of rels) {
    let body: string | null = null
    let frontmatter: Record<string, unknown> | null = null
    try {
      const note = readNote(rel)
      body = note.body
      frontmatter = note.frontmatter
    } catch {
      // Race (deleted between walk and read) — keep the node, no edges.
    }
    titles.set(rel, noteTitle(rel, frontmatter))
    if (body === null || body.length > GRAPH_PARSE_MAX_BYTES) continue
    if (parsedBytes + body.length > GRAPH_PARSE_TOTAL_BUDGET_BYTES) {
      truncated = true // over the corpus parse budget — node kept, edges skipped
      continue
    }
    parsedBytes += body.length
    for (const link of parseWikilinksBounded(body, GRAPH_PARSE_MAX_BYTES)) {
      const target = resolveNoteTarget(link.target, index)
      // Only in-vault, in-graph targets; drop self-loops; dedupe pairs.
      if (!target || target === rel || !nodeSet.has(target)) continue
      const key = `${rel}\u0000${target}`
      if (edgeKeys.has(key)) continue
      edgeKeys.add(key)
      edges.push({ source: rel, target })
    }
  }

  // 3. Degrees over the deduped edge list.
  const degree = new Map<string, number>()
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
  }

  const nodes: VaultGraphNode[] = rels.map((rel) => ({
    id: rel,
    title: titles.get(rel) ?? rel,
    dir: topLevelDir(rel),
    degree: degree.get(rel) ?? 0,
  }))

  const data: VaultGraphData = { nodes, edges, truncated }
  _cache = { root, builtAt: now, data }
  return data
}

/**
 * Notes linking TO `rel` — the edge list inverted (Captain ruling 2026-07-17:
 * BacklinksPanel returns, filesystem-backed). Sorted by source relpath.
 */
export function getBacklinks(rel: string): VaultBacklink[] {
  const clean = rel.replace(/\/+$/, '')
  const { nodes, edges } = buildVaultGraph()
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const out: VaultBacklink[] = []
  for (const e of edges) {
    if (e.target !== clean) continue
    const src = byId.get(e.source)
    out.push({
      sourceRel: e.source,
      sourceTitle: src?.title ?? e.source,
      sourceDir: src?.dir ?? topLevelDir(e.source),
    })
  }
  out.sort((a, b) => a.sourceRel.localeCompare(b.sourceRel))
  return out
}
