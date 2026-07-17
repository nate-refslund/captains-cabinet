// vault-graph.ts — filesystem wikilink graph + backlinks teeth.
//
// Captain ruling 2026-07-17: the reader (and its graph) returned; the
// retired DB graph stays retired. These tests pin the FILESYSTEM graph:
//   - nodes == the fixture's real note count (and nothing else),
//   - edges == exactly the resolvable [[wikilinks]] (deduped, no self-loops,
//     unresolved/hostile targets contribute nothing),
//   - ★ CONFINEMENT: a symlink-escape note NEVER enters the graph — not as a
//     node, not as an edge endpoint — and traversal-shaped wikilinks
//     ([[../escape]], [[/abs/path]]) never produce an edge,
//   - backlinks are the exact inversion of the edge list.
// Fixtures are temp dirs — the real vault is never touched.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { resetVaultRootCache, resetBasenameIndexCache } from './vault'
import {
  buildVaultGraph,
  getBacklinks,
  resetVaultGraphCache,
  type VaultGraphData,
} from './vault-graph'

const ENV_KEYS = [
  'CABINET_ROOT',
  'CABINET_ORG_VAULT_DIR',
  'CABINET_PRODUCT_BRAIN_DIR',
] as const

let saved: Record<string, string | undefined>
let vault: string
let outside: string

function resetAll() {
  resetVaultRootCache()
  resetBasenameIndexCache()
  resetVaultGraphCache()
}

/**
 * Fixture corpus (5 REAL notes; the escaping symlink note is NOT one):
 *
 *   a.md                 ← linked by b, sub/c, sub/d        (title: Alpha)
 *   b.md                 → [[a]] twice (dedupe) + [[b]] self + [[missing]]
 *   sub/c.md             → [[a]], [[../escape-note]], [[/etc/passwd]]
 *   sub/d.md             → [[Alpha]] (title addressing → a.md) + [[c]]
 *   loner.md             → (no links)
 *   evil-link.md         — SYMLINK → outside/evil.md (which links [[a]]);
 *                          must never appear as node or edge source
 */
function makeFixtureVault(): void {
  vault = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vgraph-fx-')))
  outside = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'vgraph-out-')))

  fs.writeFileSync(
    path.join(vault, 'a.md'),
    '---\ntitle: Alpha\n---\n# Alpha\n\nno outgoing links'
  )
  fs.writeFileSync(
    path.join(vault, 'b.md'),
    'see [[a]] and again [[a]] and myself [[b]] and a ghost [[missing]]'
  )
  fs.mkdirSync(path.join(vault, 'sub'))
  fs.writeFileSync(
    path.join(vault, 'sub', 'c.md'),
    'up to [[a]] — and hostile: [[../escape-note]] [[/etc/passwd]]'
  )
  fs.writeFileSync(
    path.join(vault, 'sub', 'd.md'),
    'title-addressed [[Alpha]] and sibling [[c]]'
  )
  fs.writeFileSync(path.join(vault, 'loner.md'), 'no links here')

  // The escape: a note OUTSIDE the vault, symlinked in with a .md name. It
  // links [[a]] — if the walk ever followed it, a bogus node+edge appears.
  fs.writeFileSync(path.join(outside, 'evil.md'), 'evil links [[a]]')
  fs.symlinkSync(path.join(outside, 'evil.md'), path.join(vault, 'evil-link.md'), 'file')
  // A sibling escape-note target name so [[../escape-note]] LOOKS plausible.
  fs.writeFileSync(path.join(outside, 'escape-note.md'), 'outside note')
}

beforeEach(() => {
  saved = {}
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k]
    delete process.env[k]
  }
  makeFixtureVault()
  process.env.CABINET_ORG_VAULT_DIR = vault
  resetAll()
})

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
  resetAll()
  fs.rmSync(vault, { recursive: true, force: true })
  fs.rmSync(outside, { recursive: true, force: true })
})

const edgeSet = (d: VaultGraphData) => new Set(d.edges.map((e) => `${e.source}→${e.target}`))

describe('buildVaultGraph — nodes', () => {
  it('nodes == exactly the real notes of the fixture (count and ids)', () => {
    const d = buildVaultGraph()
    expect(d.nodes.map((n) => n.id).sort()).toEqual([
      'a.md',
      'b.md',
      'loner.md',
      'sub/c.md',
      'sub/d.md',
    ])
    expect(d.truncated).toBe(false)
  })

  it('★ the symlink-escape note never enters the graph', () => {
    const d = buildVaultGraph()
    const ids = new Set(d.nodes.map((n) => n.id))
    expect(ids.has('evil-link.md')).toBe(false)
    // …and it contributes no edge from either direction.
    for (const e of d.edges) {
      expect(e.source).not.toContain('evil')
      expect(e.target).not.toContain('evil')
    }
  })

  it('titles come from frontmatter when present, else the basename', () => {
    const d = buildVaultGraph()
    const byId = new Map(d.nodes.map((n) => [n.id, n]))
    expect(byId.get('a.md')?.title).toBe('Alpha')
    expect(byId.get('b.md')?.title).toBe('b')
    expect(byId.get('sub/c.md')?.title).toBe('c')
  })

  it('dir is the top-level folder ("" for root notes)', () => {
    const d = buildVaultGraph()
    const byId = new Map(d.nodes.map((n) => [n.id, n]))
    expect(byId.get('a.md')?.dir).toBe('')
    expect(byId.get('sub/c.md')?.dir).toBe('sub')
  })
})

describe('buildVaultGraph — edges match the wikilinks', () => {
  it('edges are exactly the resolvable links: deduped, no self-loops, no ghosts', () => {
    const d = buildVaultGraph()
    expect(edgeSet(d)).toEqual(
      new Set([
        'b.md→a.md', // [[a]] twice → ONE edge; [[b]] self-loop dropped; [[missing]] no edge
        'sub/c.md→a.md', // [[a]] resolves across dirs via the basename index
        'sub/d.md→a.md', // [[Alpha]] — title addressing
        'sub/d.md→sub/c.md', // [[c]] — sibling by basename
      ])
    )
  })

  it('★ traversal-shaped wikilinks produce no edge ([[../escape-note]], [[/etc/passwd]])', () => {
    const d = buildVaultGraph()
    for (const e of d.edges) {
      expect(e.target).not.toContain('..')
      expect(e.target.startsWith('/')).toBe(false)
      expect(e.target).not.toContain('escape-note')
      expect(e.target).not.toContain('passwd')
    }
    // sub/c.md's ONLY edge is the legitimate one.
    expect(d.edges.filter((e) => e.source === 'sub/c.md')).toEqual([
      { source: 'sub/c.md', target: 'a.md' },
    ])
  })

  it('degree counts in+out over deduped edges', () => {
    const d = buildVaultGraph()
    const byId = new Map(d.nodes.map((n) => [n.id, n]))
    expect(byId.get('a.md')?.degree).toBe(3) // ← b, c, d
    expect(byId.get('b.md')?.degree).toBe(1) // → a
    expect(byId.get('sub/d.md')?.degree).toBe(2) // → a, → c
    expect(byId.get('loner.md')?.degree).toBe(0)
  })

  it('the graph result is cached (TTL) and resettable for fresh corpora', () => {
    const d1 = buildVaultGraph()
    // Add a note behind the cache's back — same object comes back…
    fs.writeFileSync(path.join(vault, 'late.md'), 'late [[a]]')
    expect(buildVaultGraph()).toBe(d1)
    // …until the seams reset (root/index/graph), then the corpus refreshes.
    resetAll()
    const d2 = buildVaultGraph()
    expect(d2.nodes.map((n) => n.id)).toContain('late.md')
    expect(edgeSet(d2).has('late.md→a.md')).toBe(true)
  })
})

describe('getBacklinks — the edge list inverted', () => {
  it('lists exactly the notes linking TO the target, sorted by source path', () => {
    expect(getBacklinks('a.md').map((b) => b.sourceRel)).toEqual([
      'b.md',
      'sub/c.md',
      'sub/d.md',
    ])
  })

  it('carries the source title + top-level dir for rendering', () => {
    const back = getBacklinks('sub/c.md')
    expect(back).toEqual([
      { sourceRel: 'sub/d.md', sourceTitle: 'd', sourceDir: 'sub' },
    ])
  })

  it('a note nobody links to has zero backlinks', () => {
    expect(getBacklinks('loner.md')).toEqual([])
    expect(getBacklinks('b.md')).toEqual([])
  })

  it('★ the outside note is never a backlink source (its [[a]] never counted)', () => {
    const sources = getBacklinks('a.md').map((b) => b.sourceRel)
    expect(sources).not.toContain('evil-link.md')
    expect(sources.every((s) => !s.includes('evil'))).toBe(true)
  })

  it('tolerates a trailing slash on the queried rel', () => {
    expect(getBacklinks('a.md/').map((b) => b.sourceRel)).toEqual([
      'b.md',
      'sub/c.md',
      'sub/d.md',
    ])
  })
})

describe('edge-harvest bounds — pathological notes degrade, never stall (2026-07-17 review fix)', () => {
  // Pre-fix, ONE planted note could block the event loop ~16.5s on every
  // cold graph/backlink build (quadratic wikilink regex at a 200KB cap).
  // Each pin below goes red if its guard is reverted:
  //   - the 32KB parse cap (big.md would regain its edge),
  //   - the linear no-`]]`/max-starts guards (patho notes would parse),
  //   - the timing bound (the 200KB `[` note would take seconds again).

  it('★ a 200KB pure-`[` planted note keeps its node, gets no edges, and the build stays fast', () => {
    fs.writeFileSync(path.join(vault, 'patho-brackets.md'), '['.repeat(200_000))
    resetAll()
    const t0 = performance.now()
    const d = buildVaultGraph()
    const ms = performance.now() - t0
    expect(d.nodes.map((n) => n.id)).toContain('patho-brackets.md')
    expect(d.edges.some((e) => e.source === 'patho-brackets.md')).toBe(false)
    // Pre-fix this build measured ~16.5s; guarded it is a few ms. The bound
    // carries wide CI headroom while still failing loudly on a regression.
    expect(ms).toBeLessThan(1000)
  })

  it('★ a many-starts note (600 × [[a]], over WIKILINK_MAX_STARTS) contributes no edges', () => {
    // WITHOUT the starts guard these 600 links resolve to a.md and the edge
    // patho-starts.md→a.md appears — the assert has teeth.
    fs.writeFileSync(path.join(vault, 'patho-starts.md'), '[[a]] '.repeat(600))
    resetAll()
    const d = buildVaultGraph()
    expect(d.nodes.map((n) => n.id)).toContain('patho-starts.md')
    expect(d.edges.some((e) => e.source === 'patho-starts.md')).toBe(false)
  })

  it('a note over the 32KB per-note parse cap keeps its node, skips its edges', () => {
    // WITHOUT the lowered cap (200KB pre-fix) this note's [[a]] would
    // resolve and big.md→a.md would appear.
    fs.writeFileSync(path.join(vault, 'big.md'), '[[a]] ' + 'x'.repeat(40_000))
    resetAll()
    const d = buildVaultGraph()
    expect(d.nodes.map((n) => n.id)).toContain('big.md')
    expect(d.edges.some((e) => e.source === 'big.md')).toBe(false)
  })

  it('an in-bounds note of the same shape still gets its edge (guards are not over-broad)', () => {
    fs.writeFileSync(path.join(vault, 'fine.md'), '[[a]] ' + 'x'.repeat(10_000))
    resetAll()
    const d = buildVaultGraph()
    expect(edgeSet(d).has('fine.md→a.md')).toBe(true)
  })
})

describe('no vault configured — empty graph, never a crash', () => {
  it('returns an empty graph when the corpus is absent', () => {
    delete process.env.CABINET_ORG_VAULT_DIR
    process.env.CABINET_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vgraph-empty-'))
    resetAll()
    expect(buildVaultGraph()).toEqual({ nodes: [], edges: [], truncated: false })
    expect(getBacklinks('a.md')).toEqual([])
  })
})
