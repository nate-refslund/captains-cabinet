/**
 * T2 LIFE — officer life-state tests, incl. the night-asleep law:
 * TTL-expired + night (or NO clock data) ⇒ asleep — the presence-TTL
 * honesty that makes the night cottage cutaway TRUE (spec v2 §5.2).
 */
import { describe, expect, it } from 'vitest'
import { lifeStateLabel, officerLifeState } from './states'

const live = { present: true, verb: 'working' }
const expired = { present: false }

describe('officerLifeState — closed, total, deterministic', () => {
  it('killswitch preempts everything', () => {
    expect(
      officerLifeState({ presence: live, clockHour: 12, killswitch: true })
    ).toBe('frozen')
    expect(
      officerLifeState({ presence: expired, clockHour: 2, killswitch: true })
    ).toBe('frozen')
  })
  it('commuting preempts work states', () => {
    expect(
      officerLifeState({ presence: live, clockHour: 12, commuting: true })
    ).toBe('commuting')
  })
  it('live verb → working; grouped → meeting', () => {
    expect(officerLifeState({ presence: live, clockHour: 12 })).toBe('working')
    expect(
      officerLifeState({ presence: live, clockHour: 12, inGroupScene: true })
    ).toBe('meeting')
  })
  it('TTL-expired + day → wandering (the idle program)', () => {
    expect(officerLifeState({ presence: expired, clockHour: 12 })).toBe(
      'wandering'
    )
  })
  it('TTL-expired + night → asleep', () => {
    expect(officerLifeState({ presence: expired, clockHour: 23 })).toBe('asleep')
    expect(officerLifeState({ presence: expired, clockHour: 5 })).toBe('asleep')
  })
  it('NO clock data fail-closes to rest, never to invented work', () => {
    expect(officerLifeState({ presence: expired, clockHour: null })).toBe(
      'asleep'
    )
    expect(officerLifeState({ presence: expired })).toBe('asleep')
  })
  it('present-but-verbless counts as expired (the TTL is the truth)', () => {
    expect(
      officerLifeState({ presence: { present: true }, clockHour: 23 })
    ).toBe('asleep')
  })
})

describe('labels — honest one-liners', () => {
  it('names the mechanism, not a mood', () => {
    expect(lifeStateLabel('wandering', null)).toContain('no tool call in 5 min')
    expect(lifeStateLabel('asleep', null)).toContain('TTL expired')
    expect(lifeStateLabel('frozen', null)).toContain('killswitch')
    expect(lifeStateLabel('working', 'testing')).toBe('working — testing')
    expect(lifeStateLabel('commuting', null)).toContain('re-classified')
  })
})
