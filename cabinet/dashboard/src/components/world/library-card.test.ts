// LibraryCard — static read-only/doctrine contracts + XSS negative controls
// + the engine-shell wiring asserts (same grep-ratchet style as
// ui-layer.test.ts, which owns the T3 rules; this suite pins the Library
// card's).
//
//  A. READ-ONLY BY CONSTRUCTION: plain single-argument GET fetches only, no
//     server-action imports, no mutation, wrapped in the pixel frame.
//  B. NO INJECTION SURFACES: no dangerouslySetInnerHTML/innerHTML; hostile
//     search titles/snippets render as escaped React text; note bodies ride
//     the existing VaultMarkdown sanitize pipeline.
//  C. ONE CONTINUOUS WORLD: the card is chrome OVER the live canvas — no
//     router/navigation APIs, no iframes; deep-links open a NEW tab; the
//     shell mounts the canvas unconditionally (never gated on libraryOpen —
//     the no-scene-swap doctrine assert).
//  D. WIRING: the Library building's primary interaction opens the card at
//     close/mid; Escape closes it; secondary keeps the era×rung inspect
//     card (Legend Law).

// (This file is deliberately `.test.ts` + createElement — the world-tree
// grep ratchets exclude `.test.ts` sources, and the negative-control tokens
// below must never count as world-tree occurrences.)

import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LibrarySearchHitList } from './library-card'
import type { WorldLibrarySearchHit } from '@/lib/world/library-panel'

const DASH = path.resolve(__dirname, '..', '..', '..')
const src = (...rel: string[]) =>
  fs.readFileSync(path.join(DASH, 'src', ...rel), 'utf8')

const CARD = ['components', 'world', 'library-card.tsx']
const SHELL = ['components', 'world', 'engine-client.tsx']
const ROUTES = [
  ['app', 'api', 'world', 'library', 'browse', 'route.ts'],
  ['app', 'api', 'world', 'library', 'note', 'route.ts'],
  ['app', 'api', 'world', 'library', 'search', 'route.ts'],
] as const

/** fetch(...) calls must be single-argument (no init object → plain GET) —
 *  the exact ui-layer.test.ts contract for world cards. */
function assertPlainGetFetches(text: string, name: string) {
  const calls = text.match(/fetch\(([^)]*)\)/g) ?? []
  expect(calls.length, `${name} should fetch something`).toBeGreaterThan(0)
  for (const call of calls) {
    expect(call, `${name}: ${call}`).not.toMatch(/,/)
  }
  expect(text, name).not.toMatch(/method\s*:/i)
  expect(text, name).not.toMatch(/@\/actions\//)
  expect(text, name).not.toMatch(/['"]use server['"]/)
}

describe('A. library card is read-only by construction', () => {
  it('plain GET fetches only, no actions, no mutation', () => {
    assertPlainGetFetches(src(...CARD), 'library-card')
  })

  it('wears the pixel frame (parchment — Harvestholm memory surface)', () => {
    const text = src(...CARD)
    expect(text).toMatch(/<PixelFrame/)
    expect(text).toMatch(/theme="parchment"/)
    expect(text).toMatch(/data-world-library/)
  })

  it('routes export GET only, carry the auth gate, and never touch the DB', () => {
    for (const rel of ROUTES) {
      const text = src(...rel)
      const name = rel.join('/')
      expect(text, name).toMatch(/export\s+async\s+function\s+GET/)
      expect(text, name).not.toMatch(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)/
      )
      expect(text, name).toMatch(/cabinet_session/)
      expect(text, name).toMatch(/401/)
      // the retired Library store stays retired; the vault is the corpus
      expect(text, name).not.toMatch(/@\/lib\/db/)
      expect(text, name).not.toMatch(/library_records|library_spaces/)
    }
  })

  it('browse/note read ONLY through the confined vault resolvers', () => {
    for (const rel of ROUTES.slice(0, 2)) {
      const text = src(...rel)
      const name = rel.join('/')
      expect(text, name).toMatch(/@\/lib\/vault/)
      // no raw fs on user input — the resolvers own every read
      expect(text, name).not.toMatch(/from ['"]fs['"]|from ['"]node:fs['"]/)
      expect(text, name).not.toMatch(/fs\.(read|write|open|unlink|rm|mkdir|rename)/)
    }
  })
})

describe('B. no injection surfaces', () => {
  it('card + routes carry no HTML-injection API', () => {
    for (const rel of [CARD, ...ROUTES]) {
      const text = src(...(rel as readonly string[]))
      const name = (rel as readonly string[]).join('/')
      expect(text, name).not.toMatch(/dangerouslySetInnerHTML/)
      expect(text, name).not.toMatch(/\binnerHTML\s*=/)
      expect(text, name).not.toMatch(/insertAdjacentHTML/)
    }
  })

  it('note bodies render through the existing VaultMarkdown sanitize pipeline', () => {
    const text = src(...CARD)
    expect(text).toMatch(/from '@\/components\/vault\/VaultMarkdown'/)
    expect(text).toMatch(/<VaultMarkdown markdown=\{note\.markdown\}/)
  })

  it('hostile search titles/snippets render as escaped text — never DOM', () => {
    const hostile: WorldLibrarySearchHit[] = [
      {
        ref: '<script>alert(2)</script>',
        title: '<script>alert(1)</script>',
        snippet: '<img src=x onerror=alert(3)> & "quotes"',
        score: 0.5,
        vaultPath: null,
      },
      {
        ref: 'r2',
        title: 'clickable',
        snippet: 'has a note',
        score: null,
        vaultPath: 'notes/alpha.md',
      },
    ]
    const out = renderToStaticMarkup(
      createElement(LibrarySearchHitList, { hits: hostile, reveal: 10_000, onOpen: () => {} })
    )
    expect(out).not.toContain('<script')
    expect(out).not.toContain('<img')
    // 'onerror=' may appear as ESCAPED TEXT — it must never sit inside a tag
    expect(out).not.toMatch(/<[^>]*onerror=/)
    expect(out).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(out).toContain('&lt;img src=x onerror=alert(3)&gt;')
    // the vault-backed hit renders as an in-card button, not a link-out
    expect(out).toContain('<button')
  })

  it('the typewriter reveal is a character slice — hostile bytes stay text at every step', () => {
    const hit: WorldLibrarySearchHit = {
      ref: 'r',
      title: 't',
      snippet: '<script>alert(1)</script>',
      score: null,
      vaultPath: null,
    }
    for (const reveal of [0, 3, 9, 100]) {
      const out = renderToStaticMarkup(
        createElement(LibrarySearchHitList, { hits: [hit], reveal, onOpen: () => {} })
      )
      expect(out, `reveal=${reveal}`).not.toContain('<script')
    }
  })
})

describe('C. one continuous world — the card is chrome, never navigation', () => {
  it('card has no router/location/history/iframe surface', () => {
    const text = src(...CARD)
    expect(text).not.toMatch(/useRouter|next\/navigation/)
    expect(text).not.toMatch(/router\.push/)
    expect(text).not.toMatch(/window\.location/)
    expect(text).not.toMatch(/history\.(push|replace)State/)
    expect(text).not.toMatch(/<iframe/i)
  })

  it('the only anchors are deep-links to a NEW tab (the world stays put)', () => {
    const text = src(...CARD)
    const anchors = text.match(/<a\s[^>]*>/g) ?? []
    expect(anchors.length).toBeGreaterThan(0)
    for (const a of anchors) {
      expect(a, a).toMatch(/target="_blank"/)
    }
  })

  it('internal wikilinks are intercepted IN-CARD via the pure href mapper', () => {
    const text = src(...CARD)
    expect(text).toMatch(/onClickCapture/)
    expect(text).toMatch(/overlayPathFromHref/)
    expect(text).toMatch(/preventDefault/)
    // internal-shaped but UNMAPPABLE hrefs are inert — never a same-tab exit
    expect(text).toMatch(/isInternalLibraryHref/)
  })

  it('the shell mounts the canvas UNCONDITIONALLY of the card (no scene swap)', () => {
    const shell = src(...SHELL)
    // canvas mount stays gated on eraMode only — never on libraryOpen
    expect(shell).toMatch(/\{!eraMode && \(\s*<EngineCanvas/)
    expect(shell).not.toMatch(/libraryOpen[^\n]*<EngineCanvas/)
    expect(shell).not.toMatch(/<EngineCanvas[^>]*libraryOpen/)
    // the retired scene enum never resurfaces in the engine shell
    expect(shell).not.toMatch(/displayScene|SceneName/)
  })

  it('opening the library never moves the camera (enter ≠ teleport)', () => {
    const shell = src(...SHELL)
    const branch = shell.match(
      /if \(target\.kind === 'building' && target\.id === 'library'\) \{[\s\S]*?\}/
    )?.[0]
    expect(branch, 'library branch exists in onPrimary').toBeTruthy()
    expect(branch).toContain('setLibraryOpen(true)')
    expect(branch).not.toContain('setCamera')
  })
})

describe('D. engine-shell wiring', () => {
  it('shell imports + mounts the card gated on libraryOpen, Escape closes', () => {
    const shell = src(...SHELL)
    expect(shell).toMatch(/import LibraryCard from '\.\/library-card'/)
    expect(shell).toMatch(/\{libraryOpen && <LibraryCard onClose=\{\(\) => setLibraryOpen\(false\)\} \/>\}/)
    const escBlock = shell.match(/if \(ev\.key === 'Escape'\) \{[\s\S]*?\}/)?.[0]
    expect(escBlock).toBeTruthy()
    expect(escBlock).toContain('setLibraryOpen(false)')
  })

  it('secondary interaction keeps the era×rung inspect card (Legend Law)', () => {
    // onSecondary routes every non-ground target through openInspect —
    // the library branch lives ONLY in onPrimary.
    const shell = src(...SHELL)
    const secondary = shell.match(/const onSecondary = useCallback\([\s\S]*?\n  \)/)?.[0]
    expect(secondary).toBeTruthy()
    expect(secondary).toContain('openInspect')
    expect(secondary).not.toContain('setLibraryOpen')
  })

  it('the world card keeps typing out of the world hotkeys (except Escape)', () => {
    const text = src(...CARD)
    expect(text).toMatch(/stopWorldHotkeys/)
    expect(text).toMatch(/ev\.key !== 'Escape'/)
  })

  it('every fetch surface carries a stale-response guard (latest issue wins)', () => {
    const text = src(...CARD)
    for (const ref of ['browseSeqRef', 'noteSeqRef', 'searchSeqRef']) {
      expect(text, ref).toMatch(new RegExp(`\\+\\+${ref}\\.current`))
      expect(text, ref).toMatch(new RegExp(`!== ${ref}\\.current`))
    }
  })
})
