// vault-wikilinks.ts — pure parsers + internal-only rewrite.
//
// The rewrite is the wikilink XSS/escape boundary: a hostile [[target]] must
// NEVER become an external or javascript: href — only an internal /library link
// or the inert unresolved sentinel.
//
// Href pins updated /vault→/library 2026-07-17 (Captain naming ruling: the
// reader is the Library at /library; /vault redirects). Same invariants,
// new prefix.

import { describe, it, expect } from 'vitest'
import {
  parseWikilinks,
  parseWikilinksBounded,
  slugify,
  extractHeadings,
  vaultHref,
  rewriteWikilinks,
  VAULT_UNRESOLVED_HREF,
  WIKILINK_MAX_STARTS,
} from './vault-wikilinks'

describe('pure parsers (copied from wikilinks.ts)', () => {
  it('parses plain / alias / section wikilinks', () => {
    expect(parseWikilinks('see [[Note]]')[0]).toMatchObject({
      target: 'Note',
      alias: null,
      section: null,
    })
    expect(parseWikilinks('[[Note|Alias]]')[0]).toMatchObject({
      target: 'Note',
      alias: 'Alias',
    })
    expect(parseWikilinks('[[Note#Heading]]')[0]).toMatchObject({
      target: 'Note',
      section: 'Heading',
    })
  })

  it('slugify is deterministic + github-compatible', () => {
    expect(slugify('Hello World')).toBe('hello-world')
    expect(slugify('A/B & C!')).toBe('ab-c')
    expect(slugify('')).toBe('section')
  })

  it('extractHeadings disambiguates duplicate slugs', () => {
    const h = extractHeadings('# Dup\n## Dup\ntext')
    expect(h.map((x) => x.slug)).toEqual(['dup', 'dup-1'])
  })
})

describe('vaultHref — always an encoded internal path', () => {
  it('percent-encodes each segment and appends the section slug', () => {
    expect(vaultHref('decisions/my note.md')).toBe('/library/decisions/my%20note.md')
    expect(vaultHref('a/b.md', 'sec')).toBe('/library/a/b.md#sec')
  })
  it('a paren in a path is encoded so it cannot break a markdown link', () => {
    expect(vaultHref('a(b).md')).toBe('/library/a%28b%29.md')
  })
})

describe('rewriteWikilinks — internal-only', () => {
  const resolve = (t: string) =>
    t === 'known' || t === 'decisions/known' ? 'decisions/known.md' : null

  it('resolved target → internal /library link', () => {
    expect(rewriteWikilinks('[[known]]', resolve)).toBe(
      '[known](/library/decisions/known.md)'
    )
    expect(rewriteWikilinks('[[known#My Section]]', resolve)).toBe(
      '[known](/library/decisions/known.md#my-section)'
    )
    expect(rewriteWikilinks('[[known|Nice Name]]', resolve)).toBe(
      '[Nice Name](/library/decisions/known.md)'
    )
  })

  it('unresolved target → inert sentinel, never a create link', () => {
    const out = rewriteWikilinks('[[ghost]]', resolve)
    expect(out).toBe(`[ghost](${VAULT_UNRESOLVED_HREF})`)
    expect(out).not.toContain('/library/new')
  })

  it('★ hostile traversal target never yields an escaping href', () => {
    const out = rewriteWikilinks('[[../../etc/passwd]]', resolve)
    expect(out).toContain(`](${VAULT_UNRESOLVED_HREF})`)
    expect(out).not.toContain('](/library') // did not fabricate an in-vault link
    expect(out).not.toContain('](/etc') // and definitely not an escaping one
  })

  it('★ external-looking target never yields an external href', () => {
    const out = rewriteWikilinks('[[http://evil.com]]', resolve)
    expect(out).toContain(`](${VAULT_UNRESOLVED_HREF})`)
    expect(out).not.toContain('](http')
  })

  it('escapes markdown-significant chars in the display label', () => {
    const out = rewriteWikilinks('[[known|a*b_c]]', resolve)
    expect(out).toBe('[a\\*b\\_c](/library/decisions/known.md)')
  })
})

describe('rewriteWikilinks — code-aware (no sentinel leak into code)', () => {
  const resolve = (t: string) => (t === 'known' ? 'decisions/known.md' : null)

  it('leaves a wikilink inside an inline code span LITERAL', () => {
    const out = rewriteWikilinks('use `[[known]]` inline', resolve)
    expect(out).toBe('use `[[known]]` inline')
    expect(out).not.toContain('/library/')
    expect(out).not.toContain(VAULT_UNRESOLVED_HREF)
  })

  it('leaves an UNRESOLVED code-span wikilink literal — sentinel never appears', () => {
    // The exact README hazard: an illustrative `[[note-name]]` in prose.
    const out = rewriteWikilinks('see `[[note-name]]` here', resolve)
    expect(out).toBe('see `[[note-name]]` here')
    expect(out).not.toContain('__vault_unresolved__')
  })

  it('leaves a wikilink inside a fenced code block literal', () => {
    const md = 'text\n\n```\n[[known]]\n```\n\nmore'
    const out = rewriteWikilinks(md, resolve)
    expect(out).toContain('```\n[[known]]\n```')
    expect(out).not.toContain('/library/')
  })

  it('rewrites out-of-code wikilinks while leaving in-code ones literal', () => {
    const out = rewriteWikilinks('[[known]] and `[[known]]`', resolve)
    expect(out).toBe('[known](/library/decisions/known.md) and `[[known]]`')
  })

  it('handles multi-backtick inline code delimiters', () => {
    const out = rewriteWikilinks('a ``[[known]]`` b', resolve)
    expect(out).toBe('a ``[[known]]`` b')
  })

  it('caps rewriting on an oversized body (renders wikilinks literal, bounds backtracking)', () => {
    const big = '[[known]]' + 'x'.repeat(200_001)
    expect(rewriteWikilinks(big, resolve)).toBe(big)
  })

  it('skips rewriting on a pathological many-starts body (renders literal)', () => {
    const patho = '[[a'.repeat(WIKILINK_MAX_STARTS + 1) + ']]'
    expect(rewriteWikilinks(patho, resolve)).toBe(patho)
  })
})

// ============================================================
// parseWikilinksBounded — ReDoS guards (2026-07-17 review fix).
// The verbatim WIKILINK_REGEX is quadratic on adversarial input (measured
// ~16.5s SYNCHRONOUS on 200KB of `[` pre-fix — an event-loop-blocking DoS
// once the graph parses the whole corpus). These tests are the teeth: the
// guarded paths must stay in linear-time territory. Thresholds carry ~50x
// headroom over observed times (<5ms) so CI noise never flakes them, while
// a quadratic regression (hundreds of ms to seconds) fails loudly.
// ============================================================

describe('parseWikilinksBounded — linear guards on adversarial input', () => {
  const timed = (fn: () => unknown): number => {
    const t0 = performance.now()
    fn()
    return performance.now() - t0
  }

  it('★ 200KB of `[` (no `]]` anywhere) returns [] fast — the measured DoS case', () => {
    const evil = '['.repeat(200_000)
    let out: unknown
    const ms = timed(() => {
      out = parseWikilinksBounded(evil, 200_000)
    })
    expect(out).toEqual([])
    expect(ms).toBeLessThan(100)
  })

  it('★ a trailing `]]` does not resurrect the blowup — max-starts guard trips fast', () => {
    // includes(']]') passes, so only the starts guard stands between this
    // body and starts×length regex work.
    const evil = '[[a'.repeat(10_000) + ']x]]'
    let out: unknown
    const ms = timed(() => {
      out = parseWikilinksBounded(evil, 200_000)
    })
    expect(out).toEqual([])
    expect(ms).toBeLessThan(100)
  })

  it('★ worst case INSIDE the guards (500 starts × 32KB, all failing) stays fast', () => {
    // Exactly WIKILINK_MAX_STARTS starts, each scanning ~31KB to a `]x` that
    // can never close — the maximum regex work the guards admit.
    const evil =
      '[[a'.repeat(WIKILINK_MAX_STARTS) + 'x'.repeat(31_000) + ']x]]'
    expect(evil.length).toBeLessThanOrEqual(32_768)
    let out: unknown
    const ms = timed(() => {
      out = parseWikilinksBounded(evil, 32_768)
    })
    expect(out).toEqual([])
    expect(ms).toBeLessThan(150)
  })

  it('over-maxBytes bodies parse to [] (caller-declared budget)', () => {
    expect(parseWikilinksBounded('[[a]]' + 'x'.repeat(100), 50)).toEqual([])
  })

  it('differential: bounded === plain parseWikilinks on real-shaped input', () => {
    const md =
      'see [[Note]] and [[Other|alias]] plus [[Deep#Section]] — a `[[code]]` ' +
      'span, an escaped \\[[not-a-link]], [[*emphasis*]] rejected, [[]] empty.'
    expect(parseWikilinksBounded(md, 200_000)).toEqual(parseWikilinks(md))
    expect(parseWikilinksBounded(md, 200_000).length).toBeGreaterThan(0)
  })

  it('exactly WIKILINK_MAX_STARTS legitimate links still parse (guard is >, not >=)', () => {
    const md = Array.from({ length: WIKILINK_MAX_STARTS }, (_, i) => `[[n${i}]]`).join(' ')
    expect(parseWikilinksBounded(md, 200_000)).toHaveLength(WIKILINK_MAX_STARTS)
  })
})
