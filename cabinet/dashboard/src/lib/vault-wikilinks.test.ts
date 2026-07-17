// vault-wikilinks.ts — pure parsers + internal-only rewrite.
//
// The rewrite is the wikilink XSS/escape boundary: a hostile [[target]] must
// NEVER become an external or javascript: href — only an internal /vault link
// or the inert unresolved sentinel.

import { describe, it, expect } from 'vitest'
import {
  parseWikilinks,
  slugify,
  extractHeadings,
  vaultHref,
  rewriteWikilinks,
  VAULT_UNRESOLVED_HREF,
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
    expect(vaultHref('decisions/my note.md')).toBe('/vault/decisions/my%20note.md')
    expect(vaultHref('a/b.md', 'sec')).toBe('/vault/a/b.md#sec')
  })
  it('a paren in a path is encoded so it cannot break a markdown link', () => {
    expect(vaultHref('a(b).md')).toBe('/vault/a%28b%29.md')
  })
})

describe('rewriteWikilinks — internal-only', () => {
  const resolve = (t: string) =>
    t === 'known' || t === 'decisions/known' ? 'decisions/known.md' : null

  it('resolved target → internal /vault link', () => {
    expect(rewriteWikilinks('[[known]]', resolve)).toBe(
      '[known](/vault/decisions/known.md)'
    )
    expect(rewriteWikilinks('[[known#My Section]]', resolve)).toBe(
      '[known](/vault/decisions/known.md#my-section)'
    )
    expect(rewriteWikilinks('[[known|Nice Name]]', resolve)).toBe(
      '[Nice Name](/vault/decisions/known.md)'
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
    expect(out).not.toContain('](/vault') // did not fabricate an in-vault link
    expect(out).not.toContain('](/etc') // and definitely not an escaping one
  })

  it('★ external-looking target never yields an external href', () => {
    const out = rewriteWikilinks('[[http://evil.com]]', resolve)
    expect(out).toContain(`](${VAULT_UNRESOLVED_HREF})`)
    expect(out).not.toContain('](http')
  })

  it('escapes markdown-significant chars in the display label', () => {
    const out = rewriteWikilinks('[[known|a*b_c]]', resolve)
    expect(out).toBe('[a\\*b\\_c](/vault/decisions/known.md)')
  })
})

describe('rewriteWikilinks — code-aware (no sentinel leak into code)', () => {
  const resolve = (t: string) => (t === 'known' ? 'decisions/known.md' : null)

  it('leaves a wikilink inside an inline code span LITERAL', () => {
    const out = rewriteWikilinks('use `[[known]]` inline', resolve)
    expect(out).toBe('use `[[known]]` inline')
    expect(out).not.toContain('/vault/')
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
    expect(out).not.toContain('/vault/')
  })

  it('rewrites out-of-code wikilinks while leaving in-code ones literal', () => {
    const out = rewriteWikilinks('[[known]] and `[[known]]`', resolve)
    expect(out).toBe('[known](/vault/decisions/known.md) and `[[known]]`')
  })

  it('handles multi-backtick inline code delimiters', () => {
    const out = rewriteWikilinks('a ``[[known]]`` b', resolve)
    expect(out).toBe('a ``[[known]]`` b')
  })

  it('caps rewriting on an oversized body (renders wikilinks literal, bounds backtracking)', () => {
    const big = '[[known]]' + 'x'.repeat(200_001)
    expect(rewriteWikilinks(big, resolve)).toBe(big)
  })
})
