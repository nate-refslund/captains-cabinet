/**
 * PLAIN-LANGUAGE LAW — the vitest tooth (Ruling B, captain-decisions
 * 2026-07-10: "enforced as a test, not a style hope").
 *
 * Three teeth:
 *  1. RENDER tooth — every string plainCard/consequenceFor/undoFor can
 *     produce for every kind × state × risk row must lint clean against the
 *     banned table (which is generated from framework/attention/plain.py —
 *     one source of truth).
 *  2. COPY tooth — every static table string shipped to this surface
 *     (copy/messages/results/buttons) lints clean.
 *  3. SOURCE tooth — string literals in the /queue page + card component
 *     lint clean (technical identifiers allowlisted explicitly; content
 *     behind the Details ▸ disclosure is DATA, not copy, and is exempt by
 *     construction).
 * Plus a mutation proof that the linter actually bites.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  consequenceFor,
  lintJargon,
  plainCard,
  TABLES,
  undoFor,
  VERBS,
} from './plain'
import type { QueueRow } from './queue'

function row(overrides: Partial<QueueRow>): QueueRow {
  return {
    id: 'sit-x',
    kind: 'action-proposal',
    state: 'pending',
    class: null,
    urgency: 'batch',
    deadline_iso: '2026-07-12T10:00:00Z',
    harm_class: null,
    age_h: 47,
    blast: { class: 'external', reach: 'external' },
    decay_stage: null,
    admission: null,
    pid: 'prop-abc',
    h: null,
    what: 'Reply to Alice about the DPA redline',
    why_now: { decay: 'waiting 47h; 2 demotions' },
    refs: ['cmt-4821'],
    one_tap: { approve: 'direct', veto: 'direct', defer: 'direct' },
    blast_worst_case: 'a message reaches a human outside the machine',
    filed_by: 'officer:cos',
    lane: 'polads',
    ...overrides,
  }
}

/** Everything the card's DEFAULT face (not Details) can say. */
function renderedStrings(r: QueueRow): string[] {
  const c = plainCard(r, Date.parse('2026-07-10T12:00:00Z'))
  const out = [
    c.sentence,
    c.kindName,
    c.stateName,
    c.risk,
    c.waiting,
    c.buttons.approve,
    c.buttons.later,
    c.buttons.no,
  ]
  for (const verb of VERBS) {
    out.push(consequenceFor(r, verb), undoFor(r, verb))
  }
  return out
}

const KINDS = [
  ...Object.keys(TABLES.kind_names),
  'mystery-kind', // unknown-kind fallback must be plain too
]
const STATES = [...Object.keys(TABLES.state_names), 'weird-state']
const RISKS = [...Object.keys(TABLES.risk_sentences), 'something new', null]

describe('render tooth: every card face lints clean', () => {
  it('kind × state matrix', () => {
    for (const kind of KINDS) {
      for (const state of STATES) {
        for (const s of renderedStrings(row({ kind, state }))) {
          expect(
            lintJargon(s),
            `kind=${kind} state=${state}: "${s}"`
          ).toEqual([])
        }
      }
    }
  })

  it('every risk rewrite (and the fallbacks)', () => {
    for (const risk of RISKS) {
      const r = row({
        blast_worst_case: risk,
        blast: { class: risk === null ? 'ceiling' : 'low', reach: 'internal' },
      })
      for (const s of renderedStrings(r)) {
        expect(lintJargon(s), `risk=${String(risk)}: "${s}"`).toEqual([])
      }
    }
  })

  it('degraded rows (no pid, no clocks, no title) stay plain', () => {
    const r = row({
      pid: null,
      what: null,
      age_h: null,
      deadline_iso: null,
      one_tap: null,
      blast: null,
      blast_worst_case: null,
      lane: null,
    })
    for (const s of renderedStrings(r)) {
      expect(lintJargon(s), `"${s}"`).toEqual([])
    }
  })
})

describe('copy tooth: the shipped tables lint clean', () => {
  it('copy + messages + results + buttons + names', () => {
    const all: string[] = [
      ...Object.values(TABLES.copy),
      ...Object.values(TABLES.messages),
      ...Object.values(TABLES.results),
      ...Object.values(TABLES.kind_names),
      TABLES.kind_name_default,
      ...Object.values(TABLES.state_names),
      TABLES.state_name_default,
      ...Object.values(TABLES.risk_sentences),
      TABLES.risk_default,
      TABLES.risk_default_ceiling,
      ...Object.values(TABLES.consequence_templates),
      ...Object.values(TABLES.undo_templates),
      ...Object.values(TABLES.door_buttons).flatMap((b) => Object.values(b)),
      ...Object.values(TABLES.banned), // suggested replacements must be plain
    ]
    for (const s of all) {
      expect(lintJargon(s), `"${s}"`).toEqual([])
    }
  })
})

describe('source tooth: /queue surface literals lint clean', () => {
  const SRC = path.resolve(__dirname, '..', '..')
  const FILES = [
    path.join(SRC, 'app', '(authenticated)', 'queue', 'page.tsx'),
    path.join(SRC, 'components', 'queue-decision-card.tsx'),
  ]
  // Technical identifiers that are not captain-facing copy.
  const ALLOW = new Set([
    '/api/attention/verdict',
    'X-Cabinet-CSRF',
    'content-type',
    'application/json',
    'use client',
    'force-dynamic',
  ])
  const ALLOW_PREFIX = ['@/', './', '../', 'node:', 'next/', 'react', 'https://t.me']

  function literals(text: string): string[] {
    // Comments are not captain-facing copy — strip them so prose apostrophes
    // don't open phantom string spans.
    const code = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    const out: string[] = []
    const rx = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/g
    for (const m of code.matchAll(rx)) {
      const lit = m[1] ?? m[2] ?? m[3] ?? ''
      if (!lit || ALLOW.has(lit)) continue
      if (ALLOW_PREFIX.some((p) => lit.startsWith(p))) continue
      out.push(lit)
    }
    return out
  }

  for (const file of FILES) {
    it(path.basename(file), () => {
      const text = fs.readFileSync(file, 'utf8')
      for (const lit of literals(text)) {
        expect(lintJargon(lit), `${path.basename(file)}: "${lit}"`).toEqual([])
      }
    })
  }
})

describe('the linter bites', () => {
  it('catches banned terms on word boundaries', () => {
    expect(lintJargon('answer in the binder').map((v) => v.term)).toEqual(['binder'])
    expect(lintJargon('Verdicts happen here')).toHaveLength(1)
    expect(lintJargon('the T2 queue')).toHaveLength(1)
  })

  it('does not false-positive on substrings', () => {
    expect(lintJargon('rapid progress')).toEqual([]) // pid inside a word
    expect(lintJargon('t2-rubric.md')).toEqual([]) // hyphen-joined identifier
    expect(lintJargon('parked until Monday')).toEqual([])
  })

  it('a planted violation turns the suite red (mutation proof)', () => {
    const mutated = `${TABLES.copy.footer_hint} — check the census`
    expect(lintJargon(mutated).length).toBeGreaterThan(0)
  })
})
