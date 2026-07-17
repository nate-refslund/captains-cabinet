// /api/world/library/* — the world Library card's data routes.
//
// Teeth:
//  - AUTH: every route 401s without the cabinet_session cookie (ratchet #7
//    pattern; the edge middleware HMAC-verifies for real — the route check
//    is presence, same as every sibling world route).
//  - PARITY: browse/note serve EXACTLY what the library surface serves —
//    lib/vault listDir/readNote + the same wikilink rewrite the /library
//    reader uses (vaultHref emits /library/… hrefs; /vault is its permanent
//    redirect alias) — over the same fixture vault (the world shows the
//    same Library data, not a fork).
//  - CONFINEMENT THROUGH THE ROUTE: traversal / absolute / NUL paths die as
//    a generic 404 whose body is BYTE-IDENTICAL to a genuine miss (no
//    existence oracle).
//  - LANE-2 CONTRACT: the search route forwards the query as URL
//    search-param DATA (`q`) to GET /api/library/search with the caller's
//    own cookie — hostile query text arrives byte-equal as data (the landed
//    route binds it as a pg parameter, never SQL/path text), is never
//    logged, and a down/unlanded backend yields an honest available:false.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { NextRequest } from 'next/server'

// Per-test cookie store (house pattern — tasks/stream route test).
let mockCookieStore: Record<string, { value: string } | undefined> = {}
vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) => mockCookieStore[name],
  })),
}))

import { GET as browseGET } from './browse/route'
import { GET as noteGET } from './note/route'
import { GET as searchGET } from './search/route'
import {
  listDir,
  readNote,
  buildBasenameIndex,
  resolveNoteTarget,
  resetVaultRootCache,
  resetBasenameIndexCache,
} from '@/lib/vault'
import { rewriteWikilinks } from '@/lib/vault-wikilinks'
import type {
  WorldLibraryBrowsePayload,
  WorldLibraryNotePayload,
  WorldLibrarySearchPayload,
} from '@/lib/world/library-panel'

const ENV_KEYS = ['CABINET_ROOT', 'CABINET_ORG_VAULT_DIR', 'CABINET_PRODUCT_BRAIN_DIR'] as const
let saved: Record<string, string | undefined>
let vault: string
let cleanupDirs: string[] = []

function makeFixtureVault(): void {
  vault = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'wl-vault-')))
  cleanupDirs.push(vault)
  fs.mkdirSync(path.join(vault, 'notes'))
  fs.writeFileSync(path.join(vault, 'notes', 'alpha.md'), '# Alpha\n\nalpha body')
  fs.writeFileSync(
    path.join(vault, 'decisions.md'),
    '---\ntitle: Decisions Log\nowner: cabinet\n---\n# Decisions\n\nsee [[alpha]] and [[missing-note]]\n'
  )
  fs.writeFileSync(path.join(vault, 'README.md'), '# Readme')
  fs.writeFileSync(path.join(vault, 'data.txt'), 'not markdown') // non-md → never served
  fs.mkdirSync(path.join(vault, '.git'))
  fs.writeFileSync(path.join(vault, '.git', 'hidden.md'), 'x')
  process.env.CABINET_ORG_VAULT_DIR = vault
  resetVaultRootCache()
  resetBasenameIndexCache()
}

function req(pathname: string, params: Record<string, string>, cookie = 'cabinet_session=t1'): NextRequest {
  const u = new URL(`http://localhost:3100${pathname}`)
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v)
  return new NextRequest(u, { headers: cookie ? { cookie } : {} })
}

beforeEach(() => {
  saved = {}
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k]
    delete process.env[k]
  }
  mockCookieStore = { cabinet_session: { value: 't1' } }
  makeFixtureVault()
})

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
  for (const d of cleanupDirs.splice(0)) {
    try {
      fs.rmSync(d, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
  resetVaultRootCache()
  resetBasenameIndexCache()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

describe('auth gate — every world library route', () => {
  it('401 without the session cookie', async () => {
    mockCookieStore = {}
    for (const [name, handler, params] of [
      ['browse', browseGET, { path: '' }],
      ['note', noteGET, { path: 'notes/alpha.md' }],
      ['search', searchGET, { q: 'x' }],
    ] as const) {
      const res = await handler(req(`/api/world/library/${name}`, params, ''))
      expect(res.status, name).toBe(401)
    }
  })
})

// ---------------------------------------------------------------------------
// Browse — parity + confinement
// ---------------------------------------------------------------------------

describe('GET /api/world/library/browse', () => {
  it('root listing is EXACTLY lib/vault listDir("") — the same Library data', async () => {
    const res = await browseGET(req('/api/world/library/browse', { path: '' }))
    expect(res.status).toBe(200)
    const body = (await res.json()) as WorldLibraryBrowsePayload
    expect(body.vaultConfigured).toBe(true)
    expect(body.entries).toEqual(
      listDir('').map((e) => ({ name: e.name, relPath: e.relPath, kind: e.kind }))
    )
    // dirs-first ordering + dotdir exclusion ride the shared resolver
    expect(body.entries[0]).toEqual({ name: 'notes', relPath: 'notes', kind: 'dir' })
    expect(body.entries.map((e) => e.name)).not.toContain('.git')
  })

  it('subdir listing parity', async () => {
    const res = await browseGET(req('/api/world/library/browse', { path: 'notes' }))
    const body = (await res.json()) as WorldLibraryBrowsePayload
    expect(body.entries).toEqual(
      listDir('notes').map((e) => ({ name: e.name, relPath: e.relPath, kind: e.kind }))
    )
  })

  it('traversal / absolute / NUL → 404 byte-identical to a genuine miss', async () => {
    const miss = await browseGET(req('/api/world/library/browse', { path: 'nope/nowhere' }))
    expect(miss.status).toBe(404)
    const missBody = await miss.text()
    for (const evil of ['../../etc', '/etc', 'a\0b', '..']) {
      const res = await browseGET(req('/api/world/library/browse', { path: evil }))
      expect(res.status, evil).toBe(404)
      expect(await res.text(), evil).toBe(missBody) // no existence oracle
    }
  })

  it('no corpus → honest vaultConfigured:false (never a crash)', async () => {
    const empty = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'wl-empty-')))
    cleanupDirs.push(empty)
    delete process.env.CABINET_ORG_VAULT_DIR
    process.env.CABINET_ROOT = empty // no vault/ nor product-brain/ inside
    resetVaultRootCache()
    const res = await browseGET(req('/api/world/library/browse', { path: '' }))
    const body = (await res.json()) as WorldLibraryBrowsePayload
    expect(body).toEqual({ vaultConfigured: false, relPath: '', entries: [] })
  })
})

// ---------------------------------------------------------------------------
// Note — parity (the exact /library reader pipeline) + confinement
// ---------------------------------------------------------------------------

describe('GET /api/world/library/note', () => {
  it('serves the EXACT /library reader pipeline output (readNote + wikilink rewrite)', async () => {
    const res = await noteGET(req('/api/world/library/note', { path: 'decisions.md' }))
    expect(res.status).toBe(200)
    const body = (await res.json()) as WorldLibraryNotePayload
    const note = readNote('decisions.md')
    const index = buildBasenameIndex()
    const expected = rewriteWikilinks(note.body, (t) => resolveNoteTarget(t, index))
    expect(body.markdown).toBe(expected)
    expect(body.title).toBe('Decisions Log') // frontmatter title wins
    expect(body.relPath).toBe('decisions.md')
    expect(body.frontmatter).toEqual(note.frontmatter)
    // the wikilink resolved to an INTERNAL /library href (the reader —
    // /vault is only its redirect alias since the identity landing) …
    expect(body.markdown).toContain('/library/notes/alpha.md')
    // … and the unresolved one became the inert sentinel, never a link target
    expect(body.markdown).toContain('#__vault_unresolved__')
  })

  it('traversal / absolute / NUL / non-md / empty → 404 byte-identical to a miss', async () => {
    const miss = await noteGET(req('/api/world/library/note', { path: 'nope.md' }))
    expect(miss.status).toBe(404)
    const missBody = await miss.text()
    // (dotfile paths behave EXACTLY like the /library vault surface — hidden
    // from every listing; direct reads ride the same confinement. Parity,
    // not a fork.)
    for (const evil of ['../../etc/passwd', '/etc/passwd', 'a\0b.md', 'data.txt', '']) {
      const res = await noteGET(req('/api/world/library/note', { path: evil }))
      expect(res.status, evil).toBe(404)
      expect(await res.text(), evil).toBe(missBody)
    }
  })
})

// ---------------------------------------------------------------------------
// Search — the lane-2 contract seam
// ---------------------------------------------------------------------------

interface FetchCall {
  url: string
  init: RequestInit | undefined
}

function stubLane2(response: {
  ok: boolean
  status?: number
  json?: unknown
  reject?: boolean
}): FetchCall[] {
  const calls: FetchCall[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: URL | RequestInfo, init?: RequestInit) => {
      calls.push({ url: String(input), init })
      if (response.reject) throw new Error('ECONNREFUSED')
      return {
        ok: response.ok,
        status: response.status ?? (response.ok ? 200 : 404),
        json: async () => response.json ?? null,
      } as Response
    })
  )
  return calls
}

describe('GET /api/world/library/search', () => {
  it('forwards the LANDED lane-2 contract: GET /api/library/search?q=&limit=, query as param DATA, caller cookie, no mutating verb', async () => {
    const hostile = `'; DROP TABLE cabinet_memory;-- <script>alert(1)</script>`
    const calls = stubLane2({ ok: true, json: { results: [], degraded: false } })
    const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
      vi.spyOn(console, m)
    )

    const res = await searchGET(
      req('/api/world/library/search', { q: hostile }, 'cabinet_session=t1; other=2')
    )
    expect(res.status).toBe(200)

    expect(calls).toHaveLength(1)
    const fwd = new URL(calls[0].url)
    expect(fwd.pathname).toBe('/api/library/search')
    expect(fwd.searchParams.get('q')).toBe(hostile) // byte-equal DATA after decode — never SQL/path text
    expect(fwd.searchParams.get('limit')).toBe('10')
    // GET-only round-trip (spec v2 v3 acceptance: no mutating verbs anywhere)
    expect(calls[0].init?.method ?? 'GET').toBe('GET')
    expect(calls[0].init?.body ?? null).toBeNull()
    const headers = calls[0].init?.headers as Record<string, string>
    expect(headers.cookie).toBe('cabinet_session=t1; other=2') // caller's own auth, no secrets of ours

    // the untrusted query is NEVER logged
    for (const spy of logSpies) {
      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain('DROP TABLE')
      }
    }
  })

  it('normalizes the landed hit shape (snippet/source_id/score/when_at/libraryPath) + degraded passthrough', async () => {
    stubLane2({
      ok: true,
      json: {
        results: [
          {
            snippet: 'the charter says…',
            source_type: 'product_brain',
            source_id: 'vault/decisions/charter.md',
            score: 0.91,
            when_at: '2026-07-10 09:30',
            libraryPath: 'decisions/charter.md',
          },
          {
            snippet: 'a framework doc hit',
            source_type: 'framework_doc',
            source_id: 'docs/runbooks/x.md',
            score: 0.5,
            when_at: null,
          },
        ],
        degraded: true,
      },
    })
    const res = await searchGET(req('/api/world/library/search', { q: 'charter' }))
    const body = (await res.json()) as WorldLibrarySearchPayload
    expect(body.available).toBe(true)
    expect(body.degraded).toBe(true)
    expect(body.rateLimited).toBe(false)
    expect(body.hits).toHaveLength(2)
    expect(body.hits[0]).toEqual({
      ref: 'vault/decisions/charter.md · 2026-07-10 09:30',
      title: 'charter',
      snippet: 'the charter says…',
      score: 0.91,
      vaultPath: 'decisions/charter.md', // opens in-card via the confined note route
    })
    expect(body.hits[1].vaultPath).toBeNull()
    expect(body.hits[1].title).toBe('docs/runbooks/x.md')
  })

  it('clamps limit to the lane-2 max (20), never pass-through', async () => {
    const calls = stubLane2({ ok: true, json: { results: [] } })
    await searchGET(req('/api/world/library/search', { q: 'x', limit: '999' }))
    expect(new URL(calls[0].url).searchParams.get('limit')).toBe('20')
  })

  it('upstream 429 → honest rateLimited (still available)', async () => {
    stubLane2({ ok: false, status: 429 })
    const body = (await (
      await searchGET(req('/api/world/library/search', { q: 'x' }))
    ).json()) as WorldLibrarySearchPayload
    expect(body).toMatchObject({ available: true, rateLimited: true, hits: [] })
  })

  it('backend down / unlanded → honest available:false (no relay, no throw)', async () => {
    stubLane2({ ok: false })
    const down = (await (
      await searchGET(req('/api/world/library/search', { q: 'x' }))
    ).json()) as WorldLibrarySearchPayload
    expect(down).toMatchObject({ available: false, hits: [] })

    stubLane2({ ok: true, reject: true })
    const dead = (await (
      await searchGET(req('/api/world/library/search', { q: 'x' }))
    ).json()) as WorldLibrarySearchPayload
    expect(dead).toMatchObject({ available: false, hits: [] })
  })

  it('validates q: missing/empty → 400, oversized → 400 (never forwarded)', async () => {
    const calls = stubLane2({ ok: true, json: { results: [] } })
    expect((await searchGET(req('/api/world/library/search', {}))).status).toBe(400)
    expect((await searchGET(req('/api/world/library/search', { q: '   ' }))).status).toBe(400)
    expect(
      (await searchGET(req('/api/world/library/search', { q: 'x'.repeat(300) }))).status
    ).toBe(400)
    expect(calls).toHaveLength(0)
  })
})
