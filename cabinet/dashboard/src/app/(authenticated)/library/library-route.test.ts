// /library route — retirement contract (2026-07-16).
//
// The landing page is a STATIC read-only notice (no DB import, no data
// fetching) pointing at the vault archive; space/record/graph deep-links
// redirect to /library. The redirect stubs are imported and executed with a
// mocked next/navigation; the notice page (JSX) is pinned as a source
// contract so this test needs no DOM.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

const { mockRedirect } = vi.hoisted(() => ({
  mockRedirect: vi.fn((target: string) => {
    // Real next/navigation redirect() throws — emulate so callers stop.
    throw new Error(`REDIRECT:${target}`)
  }),
}))

vi.mock('next/navigation', () => ({ redirect: mockRedirect }))

beforeEach(() => {
  mockRedirect.mockClear()
})

describe('/library landing page — static retirement notice', () => {
  const source = readFileSync(join(HERE, 'page.tsx'), 'utf-8')

  it('does not touch the database layer', () => {
    expect(source).not.toContain("@/lib/library")
    expect(source).not.toContain("@/lib/db")
    expect(source).toContain("force-static")
  })

  it('says retired and points at the vault archive + runbook', () => {
    expect(source).toContain('retired')
    expect(source).toContain('library-archive')
    expect(source).toContain('memory_search')
    expect(source).toContain('docs/runbooks/library-retirement-2026-07-16.md')
  })

  it('offers no create/edit affordances', () => {
    expect(source).not.toMatch(/CreateSpaceForm|CreateRecordForm|RecordEditor/)
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

describe('deep-link stubs redirect to /library', () => {
  it('[spaceId] page redirects', async () => {
    const mod = await import('./[spaceId]/page')
    await expect(mod.default()).rejects.toThrow('REDIRECT:/library')
    expect(mockRedirect).toHaveBeenCalledWith('/library')
  })

  it('[spaceId]/[recordId] page redirects', async () => {
    const mod = await import('./[spaceId]/[recordId]/page')
    await expect(mod.default()).rejects.toThrow('REDIRECT:/library')
    expect(mockRedirect).toHaveBeenCalledWith('/library')
  })

  it('graph page redirects', async () => {
    const mod = await import('./graph/page')
    await expect(mod.default()).rejects.toThrow('REDIRECT:/library')
    expect(mockRedirect).toHaveBeenCalledWith('/library')
  })
})
