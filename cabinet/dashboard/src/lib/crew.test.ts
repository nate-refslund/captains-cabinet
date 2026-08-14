/**
 * NEVER-STARTED IS NOT AN ALARM — the state machine, and its degenerate ends.
 *
 * The defect: a fresh cabinet whose officers had never been deployed rendered
 * `🔴 First Mate is offline`. The fix has to be checked in BOTH directions, or
 * it just moves the lie:
 *   - the never-started case must come out calm (this is the arm that fails
 *     against the pre-change code, which had no such state at all), and
 *   - the DIED case must still come out as the alarm, including after the
 *     heartbeat key has expired, which is the only reason the second signal
 *     exists.
 *
 * The third thing every arm here pins is what happens when the second signal
 * cannot be taken: an install reading of `unknown` must NOT buy the calm
 * answer. A sensor that fails toward reassurance is the bug one direction over.
 */
import { describe, expect, it } from 'vitest'
import { freshnessOf, type Freshness } from './liveness'
import { crewState, isAlarming, isFolded, wakeableSlugs, type CrewMemberInput } from './crew'

const NOW = Date.parse('2026-08-14T12:00:00Z')
const FIFTEEN_MIN = 15 * 60 * 1000

const fresh: Freshness = freshnessOf(new Date(NOW - 1000).toISOString(), NOW, FIFTEEN_MIN)
const stale: Freshness = freshnessOf(new Date(NOW - 60 * 60 * 1000).toISOString(), NOW, FIFTEEN_MIN)
const absent: Freshness = freshnessOf(null, NOW, FIFTEEN_MIN)
const unreadable: Freshness = freshnessOf('not a date', NOW, FIFTEEN_MIN)

function member(over: Partial<CrewMemberInput> = {}): CrewMemberInput {
  return {
    slug: 'cos',
    heartbeat: absent,
    expected: 'active',
    install: { state: 'absent' },
    onDemand: false,
    hired: true,
    stoppedAtMs: null,
    nowMs: NOW,
    ...over,
  }
}

describe('the two states that used to be one', () => {
  it('NEVER STARTED — no heartbeat, no installed helper → calm, not an alarm', () => {
    const r = crewState(member({ heartbeat: absent, install: { state: 'absent' } }))
    expect(r.state).toBe('not-awake-yet')
    expect(isAlarming(r.state)).toBe(false)
    // The words the Captain rejected must not be reachable from this state.
    expect(r.reason).not.toMatch(/offline/i)
  })

  it('DIED — helper installed, heartbeat gone → still the alarm', () => {
    const r = crewState(member({ heartbeat: absent, install: { state: 'installed' } }))
    expect(r.state).toBe('quiet')
    expect(isAlarming(r.state)).toBe(true)
  })

  it('DIED, heartbeat still present but stale → the alarm, whatever the install says', () => {
    // This is the case the install signal must NOT be able to soften: a stale
    // stamp PROVES it ran, so "never started" is a lie no matter what is on
    // disk (a plist deleted by hand, a helper installed under another name).
    for (const install of [{ state: 'absent' } as const, { state: 'installed' } as const]) {
      const r = crewState(member({ heartbeat: stale, install }))
      expect(r.state).toBe('quiet')
    }
  })

  it('a heartbeat that expired 15 minutes after death is INDISTINGUISHABLE without the second signal', () => {
    // The reason this module exists, stated as a test: identical store state,
    // two different answers, and the ONLY difference is the install reading.
    const neverStarted = crewState(member({ install: { state: 'absent' } }))
    const died = crewState(member({ install: { state: 'installed' } }))
    expect(neverStarted.state).not.toBe(died.state)
  })
})

describe('the degenerate ends — an unmeasurable signal buys nothing', () => {
  it('install UNKNOWN is not calm and not an alarm — it is unknown, with the reason', () => {
    const r = crewState(
      member({ install: { state: 'unknown', reason: 'the folder could not be read' } })
    )
    expect(r.state).toBe('unknown')
    expect(r.state).not.toBe('not-awake-yet')
    expect(isAlarming(r.state)).toBe(false)
    expect(r.reason).toContain('the folder could not be read')
  })

  it('an unreadable heartbeat is unknown, never a health claim', () => {
    const r = crewState(member({ heartbeat: unreadable, install: { state: 'installed' } }))
    expect(r.state).toBe('unknown')
    expect(r.reason).toBeTruthy()
  })

  it('a future-dated heartbeat cannot render as awake', () => {
    const skewed = freshnessOf(new Date(NOW + 10 * 60 * 1000).toISOString(), NOW, FIFTEEN_MIN)
    expect(crewState(member({ heartbeat: skewed })).state).toBe('unknown')
  })
})

describe('deliberate quiet is not a fault', () => {
  it('an officer the operator put to sleep is resting, not broken', () => {
    for (const expected of ['stopped', 'suspended'] as const) {
      const r = crewState(member({ expected, install: { state: 'installed' } }))
      expect(r.state).toBe('resting')
      expect(isAlarming(r.state)).toBe(false)
    }
  })

  it('a slept officer whose STALE heartbeat is still around is resting too', () => {
    // `--stop` leaves the plist and the stale heartbeat behind; without this
    // arm the sleep button would look like it broke something.
    const r = crewState(member({ heartbeat: stale, expected: 'stopped' }))
    expect(r.state).toBe('resting')
  })

  it('the LEFTOVER heartbeat right after a stop is resting, not "working"', () => {
    // Found by driving the flow: the heartbeat is SETEX 900, so a successful
    // stop leaves a fresh one behind for a quarter of an hour. The card showed
    // "First Mate is planning your first week" directly above "Your crew is
    // asleep". The beat predates the stop, so it is a leftover.
    const beat = freshnessOf(new Date(NOW - 60_000).toISOString(), NOW, FIFTEEN_MIN)
    const r = crewState(
      member({ heartbeat: beat, expected: 'stopped', stoppedAtMs: NOW - 30_000 })
    )
    expect(r.state).toBe('resting')
  })

  it('a heartbeat NEWER than the stop is the stop failing — and it is an alarm', () => {
    // The opposite error, and the worse one: a card reading "stopped" over an
    // agent that is still running and still acting.
    const beat = freshnessOf(new Date(NOW - 5_000).toISOString(), NOW, FIFTEEN_MIN)
    const r = crewState(
      member({ heartbeat: beat, expected: 'stopped', stoppedAtMs: NOW - 60_000 })
    )
    expect(r.state).toBe('stop-failed')
    expect(isAlarming(r.state)).toBe(true)
  })

  it('with NO recorded stop time, a fresh beat surfaces the anomaly rather than reassuring', () => {
    // `suspend-officer.sh` records no time. Unknowable ⇒ take the safe
    // direction: a stop that silently did not take is the costlier error.
    const beat = freshnessOf(new Date(NOW - 5_000).toISOString(), NOW, FIFTEEN_MIN)
    expect(crewState(member({ heartbeat: beat, expected: 'suspended' })).state).toBe(
      'stop-failed'
    )
  })

  it('a stop-failed row is never folded away', () => {
    const beat = freshnessOf(new Date(NOW - 5_000).toISOString(), NOW, FIFTEEN_MIN)
    const input = member({
      slug: 'first-lane-ceo',
      onDemand: true,
      hired: false,
      heartbeat: beat,
      expected: 'stopped',
    })
    expect(isFolded(input, crewState(input))).toBe(false)
  })

  it('an unreadable heartbeat under a stop marker is unknown, not resting', () => {
    // The stopped branch may not swallow the unknown arm.
    expect(crewState(member({ heartbeat: unreadable, expected: 'stopped' })).state).toBe(
      'unknown'
    )
  })

  it('an on-demand consultant is on call, never dead — the same call cabinet-doctor makes', () => {
    const r = crewState(member({ onDemand: true, install: { state: 'absent' } }))
    expect(r.state).toBe('on-call')
    expect(isAlarming(r.state)).toBe(false)
  })

  it('a REPORTING officer with no stop marker is simply awake', () => {
    // The marker is what changes the question. Without one, a fresh beat is a
    // working officer and nothing competes with it.
    const r = crewState(member({ heartbeat: fresh, expected: 'active', install: { state: 'absent' } }))
    expect(r.state).toBe('awake')
  })
})

describe('the fold — hides expected quiet, never a fault', () => {
  it('the placeholder lane CEO nobody chose goes under the fold', () => {
    const input = member({ slug: 'first-lane-ceo', onDemand: true, hired: true })
    expect(isFolded(input, crewState(input))).toBe(true)
  })

  it('an officer generated but never hired goes under the fold', () => {
    const input = member({ slug: 'first-lane-ceo', hired: false, onDemand: false })
    expect(isFolded(input, crewState(input))).toBe(true)
  })

  it('the hired always-on crew is NEVER folded — including when it has never been started', () => {
    const input = member({ slug: 'cos', hired: true, onDemand: false })
    expect(crewState(input).state).toBe('not-awake-yet')
    expect(isFolded(input, crewState(input))).toBe(false)
  })

  it('anything WORKING or WRONG is never folded, however it got onto the list', () => {
    for (const hb of [fresh, stale]) {
      const input = member({ slug: 'stray-ceo', hired: false, onDemand: true, heartbeat: hb })
      const reading = crewState(input)
      expect(['awake', 'quiet']).toContain(reading.state)
      expect(isFolded(input, reading)).toBe(false)
    }
  })

  it('an UNKNOWN reading is never folded either — it needs a human, not a fold', () => {
    const input = member({ slug: 'stray-ceo', hired: false, onDemand: true, heartbeat: unreadable })
    expect(isFolded(input, crewState(input))).toBe(false)
  })
})

describe('the predicates are the LIVE ones, not twins', () => {
  it('isAlarming is what decides the red mark, the link, and the fold', () => {
    // Pinned as a set rather than per-state, so a state added later has to be
    // classified deliberately instead of defaulting to calm.
    const alarming = (
      ['awake', 'quiet', 'not-awake-yet', 'resting', 'stop-failed', 'on-call', 'unknown'] as const
    ).filter(isAlarming)
    expect(alarming.sort()).toEqual(['quiet', 'stop-failed'])
  })
})

describe('what a wake would actually start', () => {
  it('only the hired, always-on crew — consultants are refused by the deploy script', () => {
    const crew = [
      member({ slug: 'cos' }),
      member({ slug: 'first-lane-ceo', onDemand: true }),
      member({ slug: 'stray', hired: false }),
    ]
    expect(wakeableSlugs(crew)).toEqual(['cos'])
  })

  it('an empty roster promises nothing', () => {
    expect(wakeableSlugs([])).toEqual([])
  })
})
