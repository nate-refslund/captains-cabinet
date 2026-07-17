// library-panel.ts — pure-helper + lane-2 contract teeth.
//
// The world Library card's search rides the lane-2 contract through ONE
// module; these tests pin (a) the request contract (the query rides the `q`
// search param of the lane-2 GET as DATA — never SQL/path text), (b) the
// defensive response normalizer (garbage in → [] out; hostile/oversized
// fields capped or dropped; only plain vault-relative paths survive), and
// (c) the in-card navigation mappers (exact route prefixes only — no
// sibling, no protocol, no traversal; internal-but-unmappable stays
// distinguishable so the card can render it inert).

import { describe, it, expect } from 'vitest'
import {
  buildLane2SearchUrl,
  crumbsFor,
  isInternalLibraryHref,
  lane2Degraded,
  LANE2_MAX_LIMIT,
  LANE2_SEARCH_ENDPOINT,
  normalizeLane2Response,
  overlayPathFromHref,
  parentPath,
  safeRelPath,
} from './library-panel'

describe('lane-2 request contract (LANDED: GET /api/library/search?q=&limit=)', () => {
  it('endpoint is the library search API', () => {
    expect(LANE2_SEARCH_ENDPOINT).toBe('/api/library/search')
  })

  it('query rides the q param as DATA — decodes byte-equal, never path text', () => {
    const hostile = `'; DROP TABLE cabinet_memory;-- <script>alert(1)</script>`
    const u = buildLane2SearchUrl('http://localhost:3100', hostile, 10)
    expect(u.pathname).toBe('/api/library/search')
    expect(u.searchParams.get('q')).toBe(hostile) // data in, data out
    expect(u.searchParams.get('limit')).toBe('10')
    // the raw query never appears un-encoded in the URL string
    expect(u.toString()).not.toContain('DROP TABLE')
  })

  it('limit clamps to the lane-2 max', () => {
    expect(
      buildLane2SearchUrl('http://x', 'q', 999).searchParams.get('limit')
    ).toBe(String(LANE2_MAX_LIMIT))
    expect(buildLane2SearchUrl('http://x', 'q', -3).searchParams.get('limit')).toBe('1')
  })

  it('lane2Degraded reads only an explicit degraded:true', () => {
    expect(lane2Degraded({ degraded: true })).toBe(true)
    expect(lane2Degraded({ degraded: 'yes' })).toBe(false)
    expect(lane2Degraded({})).toBe(false)
    expect(lane2Degraded(null)).toBe(false)
  })
})

describe('normalizeLane2Response — defensive by construction', () => {
  it('garbage shapes → []', () => {
    for (const junk of [null, undefined, 42, 'hi', [], {}, { results: 'x' }, { results: {} }]) {
      expect(normalizeLane2Response(junk)).toEqual([])
    }
  })

  it('the LANDED hit shape maps (snippet/source_id/score/when_at/libraryPath)', () => {
    const hits = normalizeLane2Response({
      results: [
        {
          snippet: 'the harbor ledger…',
          source_type: 'product_brain',
          source_id: 'vault/library-archive/lib-9-harbor.md',
          score: 0.9,
          when_at: '2026-07-10 09:30',
          libraryPath: 'library-archive/lib-9-harbor.md',
        },
      ],
    })
    expect(hits).toEqual([
      {
        ref: 'vault/library-archive/lib-9-harbor.md · 2026-07-10 09:30',
        title: 'lib 9 harbor',
        snippet: 'the harbor ledger…',
        score: 0.9,
        vaultPath: 'library-archive/lib-9-harbor.md',
      },
    ])
  })

  it('the retired record-store shape still maps (defensive tolerance)', () => {
    const hits = normalizeLane2Response({
      results: [
        { record_id: '7', title: 'Decision 7', preview: 'we decided…', similarity: 0.42 },
      ],
    })
    expect(hits).toEqual([
      { ref: '7', title: 'Decision 7', snippet: 'we decided…', score: 0.42, vaultPath: null },
    ])
  })

  it('caps: 25 hits, 200-char titles, 500-char snippets', () => {
    const rows = Array.from({ length: 40 }, (_, i) => ({
      source_id: String(i),
      title: 'T'.repeat(1000),
      snippet: 'S'.repeat(9000),
    }))
    const hits = normalizeLane2Response({ results: rows })
    expect(hits).toHaveLength(25)
    expect(hits[0].title).toHaveLength(200)
    expect(hits[0].snippet).toHaveLength(500)
  })

  it('non-string / wrong-typed fields are dropped, not coerced blindly', () => {
    const hits = normalizeLane2Response({
      results: [{ title: { evil: true }, snippet: 'ok snippet', score: 'high' }],
    })
    expect(hits).toHaveLength(1)
    expect(hits[0].title).toBe('(untitled)')
    expect(hits[0].score).toBeNull()
  })

  it('hostile library paths never survive (absolute / traversal / NUL / windows)', () => {
    for (const bad of [
      '/etc/passwd',
      '../../secrets.md',
      'a/../../b.md',
      'a/\0b.md',
      'C:evil.md',
      'a\\b.md',
      '',
    ]) {
      const hits = normalizeLane2Response({
        results: [{ title: 't', snippet: 's', libraryPath: bad }],
      })
      expect(hits[0].vaultPath, bad).toBeNull()
    }
  })
})

describe('safeRelPath', () => {
  it('accepts plain relative note paths', () => {
    expect(safeRelPath('notes/alpha.md')).toBe('notes/alpha.md')
  })
  it('rejects everything else', () => {
    for (const bad of [null, 7, '/abs', '../x', 'a//b', 'a/..', 'x\\y', 'a\0', 'X'.repeat(600)]) {
      expect(safeRelPath(bad as unknown)).toBeNull()
    }
  })
})

describe('overlayPathFromHref — internal-only, exact prefixes', () => {
  it('maps /vault and /library hrefs (both roots + nested, decoded)', () => {
    expect(overlayPathFromHref('/vault')).toBe('')
    expect(overlayPathFromHref('/library')).toBe('')
    expect(overlayPathFromHref('/vault/notes/alpha.md')).toBe('notes/alpha.md')
    expect(overlayPathFromHref('/library/notes/alpha.md')).toBe('notes/alpha.md')
    expect(overlayPathFromHref('/vault/a%20b/c%28d%29.md')).toBe('a b/c(d).md')
    expect(overlayPathFromHref('/vault/notes/alpha.md#section')).toBe('notes/alpha.md')
    expect(overlayPathFromHref('/vault/notes/alpha.md?x=1')).toBe('notes/alpha.md')
  })

  it('never maps siblings, externals, protocols, or the unresolved sentinel', () => {
    for (const bad of [
      '/vaultfoo/x.md',
      '/librarian/x.md',
      'https://evil.example/vault/x.md',
      '//evil.example/vault/x.md',
      'javascript:alert(1)',
      'mailto:a@b.c',
      '#__vault_unresolved__',
      '#section',
      '',
      null,
      undefined,
    ]) {
      expect(overlayPathFromHref(bad as unknown), String(bad)).toBeNull()
    }
  })

  it('decoded traversal still dies (%2e%2e escape)', () => {
    expect(overlayPathFromHref('/vault/%2e%2e/%2e%2e/etc/passwd')).toBeNull()
    expect(overlayPathFromHref('/vault/..%2f..%2fetc')).toBeNull()
  })

  it('malformed percent-encoding refuses rather than guesses', () => {
    expect(overlayPathFromHref('/vault/%zz.md')).toBeNull()
  })
})

describe('isInternalLibraryHref — the inert-vs-external discriminator', () => {
  it('true for both reader roots, bare/nested, with query/fragment', () => {
    for (const good of [
      '/vault',
      '/library',
      '/vault/notes/alpha.md',
      '/library/notes/alpha.md',
      '/library/a%20b.md#sec',
      '/vault/x.md?y=1',
    ]) {
      expect(isInternalLibraryHref(good), good).toBe(true)
    }
  })

  it('true for internal-shaped but UNMAPPABLE hrefs — the card inerts these, never navigates', () => {
    for (const degenerate of [
      '/library/%zz.md',
      '/library/a%5Cb.md',
      '/vault/../x.md',
      '/library/..',
    ]) {
      expect(isInternalLibraryHref(degenerate), degenerate).toBe(true)
      expect(overlayPathFromHref(degenerate), degenerate).toBeNull()
    }
  })

  it('false for siblings, externals, protocols, fragments, junk', () => {
    for (const bad of [
      '/vaultfoo/x.md',
      '/librarian/x.md',
      'https://evil.example/vault/x.md',
      '//evil.example/vault/x.md',
      'javascript:alert(1)',
      'mailto:a@b.c',
      '#__vault_unresolved__',
      '#section',
      '',
      null,
      undefined,
      7,
    ]) {
      expect(isInternalLibraryHref(bad as unknown), String(bad)).toBe(false)
    }
  })
})

describe('path helpers', () => {
  it('parentPath walks up and stops at root', () => {
    expect(parentPath('a/b/c.md')).toBe('a/b')
    expect(parentPath('a')).toBe('')
    expect(parentPath('')).toBe('')
  })
  it('crumbsFor accumulates paths', () => {
    expect(crumbsFor('a/b')).toEqual([
      { label: 'a', path: 'a' },
      { label: 'b', path: 'a/b' },
    ])
    expect(crumbsFor('')).toEqual([])
  })
})
