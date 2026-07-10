/**
 * Plain renderer contracts: the cross-language revision fingerprint (golden
 * vectors pinned identically in framework/attention/tests/test_verdicts.py)
 * and the plainCard rules the /queue surface depends on.
 */
import { describe, expect, it } from 'vitest'
import { consequenceFor, duePlain, plainCard, revisionOf } from './plain'
import type { QueueRow } from './queue'

const NOW = Date.parse('2026-07-10T12:00:00Z')

function row(overrides: Partial<QueueRow>): QueueRow {
  return {
    id: 'sit-x',
    kind: 'action-proposal',
    state: 'pending',
    class: null,
    urgency: null,
    deadline_iso: null,
    harm_class: null,
    age_h: null,
    blast: null,
    decay_stage: null,
    admission: null,
    pid: 'prop-abc',
    h: null,
    what: 'Reply to Sofie',
    why_now: null,
    refs: [],
    one_tap: { approve: 'direct', veto: 'direct', defer: 'direct' },
    blast_worst_case: null,
    filed_by: null,
    lane: null,
    ...overrides,
  }
}

describe('revisionOf — the cross-language content fingerprint', () => {
  it('matches the Python golden vector', () => {
    expect(
      revisionOf({
        pid: 'prop-abc',
        state: 'pending',
        what: 'Reply to Sofie',
        deadline_iso: '2026-07-12T10:00:00Z',
      })
    ).toBe('9fb0ea6b9b60a93f')
  })

  it('treats missing fields as empty (second golden vector)', () => {
    expect(
      revisionOf({ pid: 'prop-abc', state: 'pending', what: null, deadline_iso: null })
    ).toBe('2b05d32c9837b8b4')
  })

  it('changes when content changes', () => {
    const a = revisionOf({ pid: 'p', state: 'pending', what: 'x', deadline_iso: null })
    const b = revisionOf({ pid: 'p', state: 'surfaced', what: 'x', deadline_iso: null })
    expect(a).not.toBe(b)
  })
})

describe('plainCard rules', () => {
  it('ritual kinds never offer a dashboard approve', () => {
    const c = plainCard(row({ kind: 'germline-handback' }), NOW)
    expect(c.ritual).toBe(true)
  })

  it('decided/acted rows are not decidable', () => {
    expect(plainCard(row({ state: 'acted' }), NOW).decided).toBe(true)
    expect(plainCard(row({ state: 'decided' }), NOW).decidable).toBe(false)
  })

  it('rows without a pid or one_tap render without buttons', () => {
    expect(plainCard(row({ pid: null }), NOW).decidable).toBe(false)
    expect(plainCard(row({ one_tap: null }), NOW).decidable).toBe(false)
  })

  it('untitled rows fall back to the plain placeholder', () => {
    expect(plainCard(row({ what: '  ' }), NOW).headline).toBe('(no title)')
  })

  it('clocks read as words', () => {
    expect(duePlain('2026-07-09T12:00:00Z', NOW)).toBe('overdue')
    expect(duePlain('2026-07-11T12:00:00Z', NOW)).toBe('due in 24 hours')
    expect(duePlain('2026-07-19T12:00:00Z', NOW)).toBe('due 2026-07-19')
  })

  it('draft messages confirm with the drafted-send consequence', () => {
    expect(consequenceFor(row({ kind: 'draft-outbound' }), 'approve')).toContain(
      'goes out as drafted'
    )
  })
})
