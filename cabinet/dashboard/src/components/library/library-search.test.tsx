// LibrarySearch — XSS negative controls on the snippet render path + link
// encoding.
//
// Every snippet byte flows through highlightSnippet(), which emits ONLY
// React text nodes (strings inside <span>/<mark>), so rendering to static
// markup must yield escaped entities — never live <script>/<img>/on* markup.
// (Same convention as vault-markdown.test.tsx: assert on raw static HTML,
// no DOM needed.)

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { highlightSnippet, libraryHref, SOURCE_TYPE_LABELS } from './LibrarySearch'

function render(snippet: string, query: string): string {
  return renderToStaticMarkup(<p>{highlightSnippet(snippet, query)}</p>)
}

describe('highlightSnippet — stored HTML renders inert', () => {
  it('a <script> snippet is escaped, never emitted as an element', () => {
    const out = render('before <script>alert(1)</script> after', 'before')
    expect(out).not.toContain('<script')
    expect(out).toContain('&lt;script&gt;')
  })

  it('<img onerror> is escaped — no img tag, no live onerror attribute', () => {
    const out = render('x <img src=x onerror=alert(1)> y', 'zz')
    expect(out).not.toContain('<img')
    expect(out).toContain('&lt;img')
  })

  it('escaping survives WITH a matching highlight term in hostile text', () => {
    // The match boundary must not split the payload into live markup.
    const out = render('<script>alert(1)</script> steal cookies', 'script')
    expect(out).not.toContain('<script>')
    expect(out).toContain('<mark') // highlighting happened
    expect(out).toContain('&lt;')
  })

  it('event-handler text can never become an attribute (quotes escaped, text nodes only)', () => {
    const out = render('" onmouseover="alert(1)" x="', 'alert')
    // The handler-shaped text may appear as inert TEXT, but no element may
    // carry it as an attribute — and the breakout quotes must be escaped.
    expect(out).not.toMatch(/<[^>]*\son[a-z]+=/i)
    expect(out).toContain('&quot;')
    expect(out).not.toContain('="alert(1)"')
  })
})

describe('highlightSnippet — hostile QUERY terms are regex-escaped', () => {
  it('regex metacharacters in the query do not throw and do not over-match', () => {
    const out = render('abc', '.*')
    // '.*' is escaped → matches nothing → whole snippet is one text node.
    expect(out).toContain('abc')
    expect(out).not.toContain('<mark')
  })

  it('an HTML-shaped query term highlights as escaped text', () => {
    const out = render('watch <img src=x onerror=pwn()> closely', '<img')
    expect(out).not.toContain('<img ')
    expect(out).toContain('&lt;img')
  })

  it('unbalanced parens in the query do not crash the highlighter', () => {
    const out = render('c++ (test) code', 'c++ (test')
    expect(out).toContain('code')
  })
})

describe('highlightSnippet — highlighting behavior', () => {
  it('wraps case-insensitive term matches in <mark>', () => {
    const out = render('The Roadmap for roadmap season', 'roadmap')
    const marks = out.match(/<mark/g) ?? []
    expect(marks.length).toBe(2)
  })

  it('short (<2 char) terms are ignored', () => {
    const out = render('a b c', 'a')
    expect(out).not.toContain('<mark')
  })
})

describe('libraryHref — segment encoding into the vault browser', () => {
  // LINK-TARGET NOTE (integration 2026-07-17): the LIB-IDENT lane landed in
  // the same commit — /library IS the vault browser now, so hits link there
  // directly (/vault stays a redirect alias for stale links).
  it('preserves slashes, encodes segment contents', () => {
    expect(libraryHref('decisions/adr 001.md')).toBe(
      '/library/decisions/adr%20001.md'
    )
  })

  it('encodes hash/question characters so they cannot alter the URL', () => {
    expect(libraryHref('a/b#c.md')).toBe('/library/a/b%23c.md')
    expect(libraryHref('a/q?x.md')).toBe('/library/a/q%3Fx.md')
  })

  it('targets the LIVE reader route /library (the re-homed vault browser)', () => {
    // Post LIB-IDENT landing the catch-all reader serves /library/<path>
    // (note-shaped deep paths render, not 404) — a stale /vault target
    // would still work only via the redirect alias; link straight instead.
    expect(libraryHref('x.md').startsWith('/library/')).toBe(true)
  })
})

describe('SOURCE_TYPE_LABELS — badges cover the org-knowledge classes', () => {
  it('labels the non-linkable classes a captain will actually see', () => {
    expect(SOURCE_TYPE_LABELS.captain_law_summary).toBe('decision digest')
    expect(SOURCE_TYPE_LABELS.product_brain).toBe('vault note')
    expect(SOURCE_TYPE_LABELS.research_brief).toBe('research brief')
    expect(SOURCE_TYPE_LABELS.experience_record).toBe('experience')
    expect(SOURCE_TYPE_LABELS.consolidated_belief).toBe('belief')
  })
})
