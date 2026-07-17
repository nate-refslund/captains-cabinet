// /library route — THE LIBRARY contract (supersedes the 2026-07-16
// retirement contract that previously lived in this file).
//
// PROVENANCE — Captain ruling 2026-07-17: "keep the name Library — it fits
// the world; the vault is where it's kept, the Library is where you read."
// What that ruling pins, and what this file now asserts:
//
//   1. The retired STORE stays retired. The whole /library route tree and
//      every reader module it renders through is DB-FREE — no '@/lib/db',
//      no pg, no query(), no '@/lib/library' import — and READ-ONLY (no fs
//      write calls, no mutation HTTP exports). These asserts moved here from
//      the superseded /vault source contract when the browser moved.
//   2. The READER returns. /library renders the phase-1 vault browser
//      (MOVED from /vault, not duplicated) with the old full-page
//      retirement notice compressed into a collapsible History note on the
//      Library root (store retired 2026-07-16 · reader returned 2026-07-17 ·
//      content in the vault).
//   3. Deep links update to the new reality. /vault/* → /library/* (see
//      vault-route.test.ts beside the redirect stub); legacy 1–2-segment
//      extension-less /library deep links (the retired space/record id
//      shapes) land on /library instead of 404ing.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', '..', '..') // → cabinet/dashboard/src

// ------------------------------------------------------------
// Source collection: the route tree + the reader modules it renders through
// ------------------------------------------------------------

/** Every non-test .ts/.tsx source under the /library route tree. */
function collectRouteSources(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      out.push(...collectRouteSources(p))
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) {
      out.push(p)
    }
  }
  return out
}

const ROUTE_SOURCES = collectRouteSources(HERE)

/** The reader's data/render modules — the full import surface of the tree. */
const READER_MODULES: Record<string, string> = {
  vaultLib: join(SRC, 'lib', 'vault.ts'),
  vaultGraph: join(SRC, 'lib', 'vault-graph.ts'),
  wikilinks: join(SRC, 'lib', 'vault-wikilinks.ts'),
  renderer: join(SRC, 'components', 'vault', 'VaultMarkdown.tsx'),
  graphCanvas: join(SRC, 'components', 'library', 'GraphCanvas.tsx'),
  backlinksPanel: join(SRC, 'components', 'library', 'BacklinksPanel.tsx'),
  libraryTabs: join(SRC, 'components', 'library', 'LibraryTabs.tsx'),
}

// Strip block comments before grepping so the contract checks ACTUAL CODE,
// not doc prose (the modules deliberately DESCRIBE '@/lib/db' / query() in
// comments to explain why they are absent).
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, ' ')
}
const read = (p: string) => stripComments(readFileSync(p, 'utf-8'))

// Filesystem WRITE call shapes — matched as calls so read APIs never trip.
const WRITE_CALL =
  /\b(writeFile|writeFileSync|unlink|unlinkSync|rmSync|rmdir|rmdirSync|mkdir|mkdirSync|rename|renameSync|appendFile|appendFileSync|copyFile|copyFileSync|truncate|createWriteStream)\s*\(/

// ------------------------------------------------------------
// 1. The retired store stays retired — DB-free + read-only
// ------------------------------------------------------------

describe('/library contract — the retired STORE stays retired (DB-free tree)', () => {
  it('found the route tree sources (sanity: page + graph page at least)', () => {
    expect(ROUTE_SOURCES.length).toBeGreaterThanOrEqual(3) // catch-all page, graph page, layout
  })

  for (const p of ROUTE_SOURCES) {
    const label = p.slice(SRC.length + 1)
    it(`route source ${label} imports no database layer / retired store`, () => {
      const src = read(p)
      expect(src).not.toContain('@/lib/db')
      expect(src).not.toContain('@/lib/library')
      expect(src).not.toMatch(/from ['"]pg['"]/)
      expect(src).not.toMatch(/\bquery\s*\(/)
    })
  }

  for (const [name, p] of Object.entries(READER_MODULES)) {
    it(`reader module ${name} imports no database layer / retired store`, () => {
      const src = read(p)
      expect(src).not.toContain('@/lib/db')
      expect(src).not.toContain('@/lib/library')
      expect(src).not.toMatch(/from ['"]pg['"]/)
      expect(src).not.toMatch(/\bquery\s*\(/)
    })
  }

  it('the wikilinks module does NOT import lib/wikilinks (which pulls in db)', () => {
    expect(read(READER_MODULES.wikilinks)).not.toMatch(/from ['"]@\/lib\/wikilinks['"]/)
    expect(read(READER_MODULES.vaultLib)).not.toMatch(/from ['"]@\/lib\/wikilinks['"]/)
    expect(read(READER_MODULES.vaultGraph)).not.toMatch(/from ['"]@\/lib\/wikilinks['"]/)
  })
})

describe('/library contract — read-only (moved from the /vault source contract)', () => {
  for (const p of ROUTE_SOURCES) {
    const label = p.slice(SRC.length + 1)
    it(`route source ${label} makes no filesystem write calls`, () => {
      expect(read(p)).not.toMatch(WRITE_CALL)
    })
  }
  for (const [name, p] of Object.entries(READER_MODULES)) {
    it(`reader module ${name} makes no filesystem write calls`, () => {
      expect(read(p)).not.toMatch(WRITE_CALL)
    })
  }

  it('no route file exports a mutation HTTP handler', () => {
    for (const p of ROUTE_SOURCES) {
      const src = read(p)
      expect(src).not.toMatch(/export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)\b/)
      expect(src).not.toMatch(/export\s+const\s+(POST|PUT|PATCH|DELETE)\b/)
    }
  })

  it('the graph ships ZERO new endpoints: no /api/vault surface, no fetch in GraphCanvas', () => {
    // Data flows server component → serialized props; the client canvas never
    // fetches (the retired /api/library/* store surface stays untouched AND
    // unused by the reader).
    expect(existsSync(join(SRC, 'app', 'api', 'vault'))).toBe(false)
    expect(read(READER_MODULES.graphCanvas)).not.toMatch(/\bfetch\s*\(/)
    expect(read(READER_MODULES.backlinksPanel)).not.toMatch(/\bfetch\s*\(/)
  })

  it('GraphCanvas imports vault-graph TYPES only (fs never enters the client bundle)', () => {
    const src = readFileSync(READER_MODULES.graphCanvas, 'utf-8')
    expect(src).toMatch(/import\s+type\s+\{[^}]*\}\s+from\s+['"]@\/lib\/vault-graph['"]/)
    // No VALUE import of the fs-reaching module anywhere in the client file.
    expect(src).not.toMatch(/import\s+\{[^}]*\}\s+from\s+['"]@\/lib\/vault-graph['"]/)
    expect(src).not.toMatch(/from\s+['"]@\/lib\/vault['"]/)
  })
})

// ------------------------------------------------------------
// 2. The reader returns at /library
// ------------------------------------------------------------

describe('/library — the READER returns (Captain ruling 2026-07-17)', () => {
  const pageSource = readFileSync(join(HERE, '[[...path]]', 'page.tsx'), 'utf-8')

  it('the catch-all renders the phase-1 vault browser (moved, not duplicated)', () => {
    expect(pageSource).toContain('listDir')
    expect(pageSource).toContain('readNote')
    expect(pageSource).toContain('VaultMarkdown')
    expect(pageSource).toContain('rewriteWikilinks')
    // The browser no longer exists under /vault — moved, not copied.
    expect(existsSync(join(HERE, '..', 'vault', '[[...path]]', 'page.tsx'))).toBe(true)
    const vaultStub = readFileSync(
      join(HERE, '..', 'vault', '[[...path]]', 'page.tsx'),
      'utf-8'
    )
    expect(vaultStub).not.toContain('listDir')
    expect(vaultStub).not.toContain('VaultMarkdown')
  })

  it('the note view renders backlinks; the root offers the graph tab', () => {
    expect(pageSource).toContain('BacklinksPanel')
    expect(pageSource).toContain('LibraryTabs')
  })

  it('the retirement notice became a collapsible History note on the root', () => {
    expect(pageSource).toContain('<details')
    expect(pageSource).toContain('History')
    expect(pageSource).toContain('2026-07-16') // store retired
    expect(pageSource).toContain('2026-07-17') // reader returned
    expect(pageSource).toContain('library-archive') // where the records went
    expect(pageSource).toContain('memory_search') // how to search them
  })

  it('offers no create/edit affordances', () => {
    expect(pageSource).not.toMatch(/CreateSpaceForm|CreateRecordForm|RecordEditor/)
  })
})

describe('/library layout — passthrough, no data fetching', () => {
  const source = readFileSync(join(HERE, 'layout.tsx'), 'utf-8')

  it('no lib/library import, no sidebar fetch', () => {
    expect(source).not.toContain("@/lib/library")
    expect(source).not.toContain('listSpaces')
    expect(source).not.toContain('LibrarySidebar')
  })
})

// ------------------------------------------------------------
// 3. Legacy deep links — new reality (executed with mocked navigation)
// ------------------------------------------------------------

const { mockRedirect, mockNotFound, vaultState } = vi.hoisted(() => ({
  mockRedirect: vi.fn((target: string) => {
    // Real next/navigation redirect() throws — emulate so callers stop.
    throw new Error(`REDIRECT:${target}`)
  }),
  mockNotFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
  vaultState: { hasVault: true },
}))

vi.mock('next/navigation', () => ({
  redirect: mockRedirect,
  notFound: mockNotFound,
}))

// Partial mock: the page's routing decisions depend only on hasVault +
// classifyPath; everything else stays real. classifyPath → null models a
// path that resolves to nothing (miss OR confinement denial — the page must
// treat them identically).
vi.mock('@/lib/vault', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/vault')>()
  return {
    ...actual,
    hasVault: () => vaultState.hasVault,
    classifyPath: () => null,
  }
})

beforeEach(() => {
  mockRedirect.mockClear()
  mockNotFound.mockClear()
  vaultState.hasVault = true
})

const P = (path?: string[]) => Promise.resolve({ path })

describe('legacy /library deep links land on /library (superseding the redirect stubs)', () => {
  it('an old space-id shape (/library/<id>) redirects to /library', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['b39c2a1e-old-space-id']) })
    ).rejects.toThrow('REDIRECT:/library')
    expect(mockRedirect).toHaveBeenCalledWith('/library')
  })

  it('an old record shape (/library/<space>/<record>) redirects to /library', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['b39c2a1e', '77d1c0ff']) })
    ).rejects.toThrow('REDIRECT:/library')
  })

  it('a note-shaped miss (.md) stays a generic 404 — never a redirect', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['decisions', 'no-such-note.md']) })
    ).rejects.toThrow('NOT_FOUND')
    expect(mockRedirect).not.toHaveBeenCalled()
  })

  it('a deep (3+ segment) miss stays a generic 404', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['a', 'b', 'c']) })
    ).rejects.toThrow('NOT_FOUND')
  })

  it('legacy shapes land on /library even with no vault configured', async () => {
    vaultState.hasVault = false
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['b39c2a1e-old-space-id']) })
    ).rejects.toThrow('REDIRECT:/library')
  })
})
