// graph-tooltip.ts — hover-tooltip XSS negative controls.
//
// float-tooltip renders STRING tooltip content via innerHTML
// (d3-selection .html()), so the nodeLabel string built from vault
// frontmatter titles / folder names is a live DOM-HTML sink. These tests pin
// the escaping contract: no unescaped < > " ' & from title or dir can ever
// reach the string handed to the tooltip.

import { describe, it, expect } from 'vitest'
import { escapeHtml, graphNodeTooltipHtml, ROOT_DIR_LABEL } from './graph-tooltip'

describe('escapeHtml', () => {
  it('escapes every HTML-significant character', () => {
    expect(escapeHtml(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;')
  })

  it('is idempotent-safe on already-escaped text (no double-unescape path)', () => {
    // Escaping twice must never REDUCE escaping.
    expect(escapeHtml(escapeHtml('<b>'))).toBe('&amp;lt;b&amp;gt;')
  })

  it('leaves plain text untouched', () => {
    expect(escapeHtml('Alpha Ω · notes-2026')).toBe('Alpha Ω · notes-2026')
  })
})

describe('graphNodeTooltipHtml — the innerHTML-sink negative controls', () => {
  it('★ a stored-XSS title never yields live HTML (img/onerror payload)', () => {
    const out = graphNodeTooltipHtml({
      title: '<img src=x onerror=alert(document.cookie)>',
      dir: 'sub',
      degree: 2,
    })
    expect(out).not.toContain('<')
    expect(out).not.toContain('>')
    expect(out).toContain('&lt;img src=x onerror=alert(document.cookie)&gt;')
    expect(out).toContain('· sub · degree 2')
  })

  it('★ a hostile dir (script tag) is escaped too', () => {
    const out = graphNodeTooltipHtml({
      title: 'ok',
      dir: '<script>alert(1)</script>',
      degree: 0,
    })
    expect(out).not.toContain('<script')
    expect(out).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('★ attribute-breakout quotes are neutralized', () => {
    const out = graphNodeTooltipHtml({
      title: `" onmouseover="alert(1)`,
      dir: `'x'`,
      degree: 1,
    })
    expect(out).not.toContain('"')
    expect(out).not.toContain("'")
    expect(out).toContain('&quot; onmouseover=&quot;alert(1)')
  })

  it('degree is numeric-coerced — nothing stringly rides through it', () => {
    const out = graphNodeTooltipHtml({
      title: 't',
      dir: 'd',
      // Simulates a poisoned serialized prop; the type says number but the
      // sink must not trust it.
      degree: '<svg onload=alert(1)>' as unknown as number,
    })
    expect(out).not.toContain('<')
    expect(out).toBe('t · d · degree NaN')
  })

  it('root-level notes label as (root); normal fields render readable', () => {
    expect(graphNodeTooltipHtml({ title: 'Alpha', dir: '', degree: 3 })).toBe(
      `Alpha · ${ROOT_DIR_LABEL} · degree 3`
    )
  })
})
