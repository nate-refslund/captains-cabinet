/**
 * Plain renderer contracts: the cross-language revision fingerprint (golden
 * vectors pinned identically in framework/attention/tests/test_verdicts.py)
 * and the plainCard rules the /queue surface depends on.
 */
import { describe, expect, it } from 'vitest'
import { consequenceFor, duePlain, plainCard, revisionOf, riskSentence, undoFor } from './plain'
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
    what: 'Reply to Casey',
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
        what: 'Reply to Casey',
        deadline_iso: '2026-07-12T10:00:00Z',
      })
    ).toBe('053c030785a15e81')
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
    const c = consequenceFor(row({ kind: 'draft-outbound' }), 'approve')
    expect(c).toContain('goes out exactly as drafted')
    // Blind-approve guard: the confirm face points the reader at the draft
    // text (it lives on the item's Telegram card) BEFORE the fire tap.
    expect(c).toContain("Haven't read it?")
  })

  it('no-return approves never promise a receipt pull-back', () => {
    const money = row({
      blast: { class: 'org', reach: 'org' },
      blast_worst_case: 'money leaves the org',
    })
    expect(undoFor(money, 'approve')).toContain("can't be pulled back")
    const ext = row({ blast: { class: 'org', reach: 'external' } })
    expect(undoFor(ext, 'approve')).toContain("can't be pulled back")
    const internal = row({
      blast: { class: 'low', reach: 'internal' },
      blast_worst_case: null,
    })
    expect(undoFor(internal, 'approve')).toContain('pulled back from the receipt')
  })

  it('question/ratification kinds never claim "I go ahead with it"', () => {
    const q = row({ kind: 'pipe-prompt', blast: null, blast_worst_case: null })
    expect(riskSentence(q)).toBe("I'll follow whatever you answer.")
    const r = row({
      kind: 'outcome-ratification',
      blast: null,
      blast_worst_case: null,
    })
    expect(riskSentence(r)).not.toContain('I go ahead')
  })

  it('escalation cards get decide-or-delegate buttons', () => {
    const e = plainCard(row({ kind: 'escalation' }), NOW)
    expect(e.buttons.approve).toBe("I'll decide")
    expect(e.buttons.no).toBe('Ask the Chair')
    const c = consequenceFor(row({ kind: 'escalation' }), 'approve')
    expect(c).toContain('Nothing runs yet')
  })
})
