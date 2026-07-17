// /vault route — redirect-alias contract (supersedes the 2026-07-17 /vault
// SOURCE contract that previously lived in this file).
//
// PROVENANCE — Captain ruling 2026-07-17: "keep the name Library — it fits
// the world; the vault is where it's kept, the Library is where you read."
// The phase-1 vault browser MOVED to /library/[[...path]] (its read-only +
// DB-free source contract moved with it into library-route.test.ts); /vault
// is now a pure redirect alias so every old deep link keeps working:
//
//   /vault            → /library
//   /vault/a/b.md     → /library/a/b.md   (segments re-percent-encoded)
//
// The stub renders nothing, reads nothing, and builds its target ONLY from
// re-encoded path segments under the /library prefix — never from a query
// string, header, or full URL — so it can never become an open redirect.

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

const P = (path?: string[]) => Promise.resolve({ path })

describe('/vault → /library redirect alias', () => {
  it('root /vault redirects to /library', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(mod.default({ params: P(undefined) })).rejects.toThrow(
      'REDIRECT:/library'
    )
    expect(mockRedirect).toHaveBeenCalledWith('/library')
  })

  it('a deep note path keeps working: /vault/decisions/n.md → /library/decisions/n.md', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['decisions', 'n.md']) })
    ).rejects.toThrow('REDIRECT:/library/decisions/n.md')
  })

  it('segments are re-percent-encoded (space, parens) — same encoding as vaultHref', async () => {
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['my note.md']) })
    ).rejects.toThrow('REDIRECT:/library/my%20note.md')
    await expect(mod.default({ params: P(['a(b).md']) })).rejects.toThrow(
      'REDIRECT:/library/a%28b%29.md'
    )
  })

  it('★ a decoded %2F inside a segment cannot fabricate an external target', async () => {
    // Next decodes %2F%2Fevil.com into a single segment '//evil.com'.
    // vaultHref splits on '/' and drops empty units, so the slashes COLLAPSE
    // (they can never survive into a protocol-relative //host) and the
    // target stays a same-origin /library path.
    const mod = await import('./[[...path]]/page')
    await expect(
      mod.default({ params: P(['//evil.com']) })
    ).rejects.toThrow('REDIRECT:/library/evil.com')
    const target = mockRedirect.mock.calls[0][0]
    expect(target.startsWith('/library/')).toBe(true)
    expect(target).not.toMatch(/^\/\//) // never protocol-relative
    expect(target).not.toContain('://') // never absolute-URL shaped
  })
})

describe('/vault stub — source contract (nothing but the redirect)', () => {
  const source = readFileSync(join(HERE, '[[...path]]', 'page.tsx'), 'utf-8')

  it('the browser truly MOVED: the stub reads no vault data and renders no markdown', () => {
    expect(source).not.toContain('listDir')
    expect(source).not.toContain('readNote')
    expect(source).not.toContain('VaultMarkdown')
    expect(source).not.toContain('@/lib/vault\'') // only vault-wikilinks (pure) allowed
  })

  it('no DB, no fs, no mutation handlers', () => {
    expect(source).not.toContain('@/lib/db')
    expect(source).not.toContain('@/lib/library')
    expect(source).not.toMatch(/from ['"]fs['"]|from ['"]node:fs['"]/)
    expect(source).not.toMatch(/export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)\b/)
  })

  it('the target is built through vaultHref (re-encoded, /library-prefixed)', () => {
    expect(source).toContain("from '@/lib/vault-wikilinks'")
    expect(source).toContain('vaultHref')
    expect(source).toContain("'/library'")
  })
})
