/**
 * T3 UI-layer pure helpers — unit suite: card tab coverage, ring
 * derivation (reserved palette, red NEVER), strict cost formatting,
 * roster ordering, decision-queue parsing.
 */
import { describe, expect, it } from 'vitest'
import {
  formatMicro,
  freshSeconds,
  parseActionCard,
  railOrder,
  RING_FRESH_S,
  ringFor,
  sortDecisionQueue,
  tabsFor,
} from './ui-cards'

describe('inspect-card coverage contract', () => {
  it('bound elements carry all three tabs; decorative are WHAT-only', () => {
    expect(tabsFor(false)).toEqual(['WHAT', 'NOW', 'PROOF'])
    expect(tabsFor(undefined)).toEqual(['WHAT', 'NOW', 'PROOF'])
    expect(tabsFor(true)).toEqual(['WHAT'])
  })
})

describe('status ring (reserved salience palette, dual-coded)', () => {
  it('fresh activity = green + check glyph', () => {
    expect(ringFor({ freshS: 30, expected: true, present: true })).toEqual({
      ring: 'green',
      glyph: '✓',
    })
  })
  it('stale-but-expected = amber (blocked/waiting)', () => {
    expect(
      ringFor({ freshS: RING_FRESH_S + 1, expected: true, present: true }).ring
    ).toBe('amber')
    expect(ringFor({ freshS: null, expected: true, present: false }).ring).toBe('amber')
  })
  it('unmeasured = grey; red is NEVER a ring state (killswitch-only)', () => {
    const grey = ringFor({ freshS: null, expected: false, present: false })
    expect(grey.ring).toBe('grey')
    // exhaustiveness: no input combination may yield anything but the trio
    for (const freshS of [null, 0, RING_FRESH_S, RING_FRESH_S * 10]) {
      for (const expected of [true, false]) {
        for (const present of [true, false]) {
          expect(['green', 'amber', 'grey']).toContain(
            ringFor({ freshS, expected, present }).ring
          )
        }
      }
    }
  })
})

describe('freshness + strict cost-viz', () => {
  it('freshSeconds derives from the passed now (no clock in lib/world)', () => {
    const now = Date.parse('2026-07-09T12:00:00Z')
    expect(freshSeconds('2026-07-09T11:59:00Z', now)).toBe(60)
    expect(freshSeconds(undefined, now)).toBeNull()
    expect(freshSeconds('not-a-date', now)).toBeNull()
  })
  it('formatMicro renders $X.XX; absence is the grey em-dash, never $0.00', () => {
    expect(formatMicro(7_683_389)).toBe('$7.68')
    expect(formatMicro(0)).toBe('$0.00') // an HONEST zero renders as zero
    expect(formatMicro(null)).toBe('—')
    expect(formatMicro(undefined)).toBe('—')
  })
})

describe('rail roster', () => {
  it('cos first, alpha after, and the unknown actor NEVER gets a slot', () => {
    expect(railOrder(['stephie-ceo', 'unknown', 'cos', 'comms-officer', 'polads-ceo'])).toEqual([
      'cos',
      'comms-officer',
      'polads-ceo',
      'stephie-ceo',
    ])
  })
})

describe('mailbox decision-queue parsing (cabinet:action:* cards)', () => {
  const key =
    'cabinet:action:cos|action-card|domain-transfer-pending|2026-07-09T09:54:21Z'
  it('parses a well-formed card with its key timestamp', () => {
    const item = parseActionCard(
      key,
      JSON.stringify({
        cid: 'abc123',
        lane: 'adhoc',
        subject: 'domain-transfer-pending',
        evidence: ['ref=a', 'ref=b'],
        confidence: 0.8,
        urgency: 'batch',
      })
    )
    expect(item).toEqual({
      cid: 'abc123',
      subject: 'domain-transfer-pending',
      lane: 'adhoc',
      urgency: 'batch',
      confidence: 0.8,
      evidenceCount: 2,
      ts: '2026-07-09T09:54:21Z',
    })
  })
  it('malformed JSON is skipped (null), never invented', () => {
    expect(parseActionCard(key, 'not json')).toBeNull()
    expect(parseActionCard(key, '"just a string"')).toBeNull()
  })
  it('sorts newest first; undated cards sink last', () => {
    const mk = (cid: string, ts: string) => ({
      cid,
      subject: cid,
      lane: 'x',
      urgency: 'batch',
      confidence: null,
      evidenceCount: 0,
      ts,
    })
    const sorted = sortDecisionQueue([
      mk('old', '2026-07-01T00:00:00Z'),
      mk('undated', ''),
      mk('new', '2026-07-09T00:00:00Z'),
    ])
    expect(sorted.map((i) => i.cid)).toEqual(['new', 'old', 'undated'])
  })
})
