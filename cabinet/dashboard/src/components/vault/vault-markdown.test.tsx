// VaultMarkdown — XSS negative controls.
//
// Hostile note content must render INERT: no <script>/<img>/<iframe>/<object>
// tags reach the DOM, no on*-handler survives as an attribute, and no
// javascript:/data:/vbscript: href is emitted. We render to static markup and
// assert on the raw HTML string (no DOM/jsdom needed).

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import VaultMarkdown from './VaultMarkdown'
import { VAULT_UNRESOLVED_HREF, rewriteWikilinks } from '@/lib/vault-wikilinks'

// next/link needs no router context in a unit test — render it as a plain
// anchor so href/class assertions work in static markup.
vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string
    children: React.ReactNode
    className?: string
  }) => (
    <a href={typeof href === 'string' ? href : ''} className={className}>
      {children}
    </a>
  ),
}))

function render(md: string): string {
  return renderToStaticMarkup(<VaultMarkdown markdown={md} />)
}

describe('VaultMarkdown — raw HTML never becomes DOM', () => {
  it('a <script> tag is not emitted as a script element', () => {
    const out = render('before\n\n<script>alert(1)</script>\n\nafter')
    expect(out).not.toContain('<script')
    expect(out).not.toContain('alert(1)</script>')
  })

  it('<img onerror> is dropped — no img, no onerror', () => {
    const out = render('![x](y)\n\n<img src=x onerror=alert(1)>')
    expect(out).not.toContain('<img')
    expect(out).not.toContain('onerror')
  })

  it('<iframe> is not emitted', () => {
    const out = render('<iframe src="javascript:alert(1)"></iframe>')
    expect(out).not.toContain('<iframe')
  })

  it('an on*-handler never survives as an attribute', () => {
    const out = render('<div onclick="evil()">hi</div>')
    expect(out).not.toContain('<div onclick')
    expect(out).not.toContain('onclick=')
  })
})

describe('VaultMarkdown — dangerous URL protocols neutralized', () => {
  it('javascript: link href is stripped', () => {
    const out = render('[click](javascript:alert(1))')
    expect(out).not.toContain('javascript:')
  })

  it('data: link href is stripped', () => {
    const out = render('[x](data:text/html,<script>alert(1)</script>)')
    expect(out).not.toContain('data:text/html')
    expect(out).not.toContain('<script')
  })

  it('vbscript: link href is stripped', () => {
    const out = render('[x](vbscript:msgbox(1))')
    expect(out).not.toContain('vbscript:')
  })
})

describe('VaultMarkdown — link rendering contract', () => {
  it('an internal /library link renders via next/link with wikilink styling', () => {
    const out = render('[a](/library/decisions/n.md)')
    expect(out).toContain('href="/library/decisions/n.md"')
    expect(out).toContain('wikilink-resolved')
  })

  it('the unresolved-wikilink sentinel renders as inert text (no href)', () => {
    const out = render(`[ghost](${VAULT_UNRESOLVED_HREF})`)
    expect(out).toContain('wikilink-unresolved')
    expect(out).toContain('ghost')
    expect(out).not.toContain('href=')
    expect(out).not.toContain('__vault_unresolved__')
  })

  it('an external link opens safely (noopener/noreferrer/nofollow, _blank)', () => {
    const out = render('[e](https://example.com)')
    expect(out).toContain('href="https://example.com"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener noreferrer nofollow"')
  })

  it('a protocol-relative //host link is treated as external, not internal', () => {
    const out = render('[e](//evil.example)')
    // Emitted as an external anchor (new tab, no referrer) — never same-origin.
    expect(out).toContain('target="_blank"')
  })
})

describe('VaultMarkdown — legitimate content still renders', () => {
  it('renders GFM tables, headings, code, and safe links', () => {
    const out = render(
      '# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n`code` and [ok](https://ok.test)'
    )
    expect(out).toContain('<h1')
    expect(out).toContain('<table')
    expect(out).toContain('<code')
    expect(out).toContain('href="https://ok.test"')
  })
})

describe('VaultMarkdown — heading anchors (section fragments can land)', () => {
  it('assigns a slug id to headings', () => {
    const out = render('# Alpha Beta\n\n## Gamma')
    expect(out).toContain('<h1 id="alpha-beta"')
    expect(out).toContain('<h2 id="gamma"')
  })

  it('disambiguates duplicate heading slugs (dup, dup-1)', () => {
    const out = render('# Dup\n\n## Dup')
    expect(out).toContain('id="dup"')
    expect(out).toContain('id="dup-1"')
  })

  it('the id is slugify output only — heading text cannot inject an attribute', () => {
    // slugify('Hello, "World"! (v2)') === 'hello-world-v2' — no quotes/parens.
    const out = render('# Hello, "World"! (v2)')
    expect(out).toContain('id="hello-world-v2"')
    expect(out).not.toContain('id="hello, "') // no raw quote breaking the attr
  })
})

describe('VaultMarkdown — /library prefix is exact (no sibling capture)', () => {
  // Prefix pins updated /vault→/library 2026-07-17 (Captain naming ruling:
  // the reader is the Library; /vault stays a recognized-internal redirect
  // alias, covered below).
  it('a sibling path /libraryfoo is NOT rendered as an internal vault link', () => {
    const out = render('[x](/libraryfoo)')
    expect(out).not.toContain('href="/libraryfoo"')
    expect(out).not.toContain('wikilink-resolved')
  })

  it('a real /library/ path still renders as an internal link', () => {
    const out = render('[x](/library/a/b.md)')
    expect(out).toContain('href="/library/a/b.md"')
    expect(out).toContain('wikilink-resolved')
  })

  it('a legacy /vault/ path stays an internal link (redirect alias keeps it working)', () => {
    const out = render('[x](/vault/a/b.md)')
    expect(out).toContain('href="/vault/a/b.md"')
    expect(out).toContain('wikilink-resolved')
  })

  it('a sibling path /vaultfoo is NOT internal either', () => {
    const out = render('[x](/vaultfoo)')
    expect(out).not.toContain('href="/vaultfoo"')
    expect(out).not.toContain('wikilink-resolved')
  })
})

describe('VaultMarkdown — end-to-end: code-span wikilink stays literal', () => {
  it('★ rewrite+render leaves an illustrative code wikilink literal; sentinel never leaks', () => {
    const src = '- **`[[wikilinks]]`** and a real [[known]] link'
    const processed = rewriteWikilinks(src, (t) =>
      t === 'known' ? 'notes/known.md' : null
    )
    const out = renderToStaticMarkup(<VaultMarkdown markdown={processed} />)
    expect(out).not.toContain('__vault_unresolved__') // sentinel never shown
    expect(out).toContain('[[wikilinks]]') // code-span wikilink is literal
    expect(out).toContain('href="/library/notes/known.md"') // real one still links
  })
})
