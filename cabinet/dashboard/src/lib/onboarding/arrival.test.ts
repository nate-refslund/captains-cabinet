/**
 * The arrival summary invents nothing.
 *
 * A closing screen is where a product is most tempted to write prose: the
 * operator is finished, the tone wants to be warm, and nobody audits a farewell
 * the way they audit a finding. So the guarantee is mechanical rather than
 * editorial — every clause carries the path it was read from and the value it
 * found there, and the arms below check both against a real journey state.
 *
 * THE SENSOR IS PROVEN TO FIRE. `invents` at the bottom of this file is a
 * clause table with one fabricated word in it, run through the same arm, which
 * must reject it. Without that, "the summary invents nothing" would be a claim
 * this file asserts about itself.
 */
import { describe, expect, it } from 'vitest'

import { ARRIVAL_CLAUSE_LIMIT, arrivalClauses, readPath, type ArrivalClause } from './arrival'
import type { OnboardingState } from './types'

/** A journey that answered everything — the maximal clause set. */
const FULL = {
  schema: 'cabinet.onboarding-journey/v2',
  journey_id: 'journey-abc',
  evidence_trial_id: 'onboarding-x',
  revision: 7,
  stage: 'complete',
  purpose: 'Find one useful thing I may be missing.',
  relationship_destination: 'reversible',
  orientation_mode: 'observe_only',
  access: 'active_read_only',
  seed: { text: 'I run a small ryokan on the coast', answered_at: '2026-08-14T09:00:00Z' },
  organization: { name: 'Hoshiyama Ryokan', answered_at: '2026-08-14T09:01:00Z' },
  mission: { purpose: 'A calmer front desk' },
  source: {
    kind: 'folder',
    root: '/Users/host/Documents/ryokan',
    label: 'ryokan',
    status: 'ratified_read_only',
    ownership: 'self',
  },
  charter: { hash: 'abcdef0123456789', status: 'ratified', payload: {} },
  first_dividend: {
    finding: {
      summary: 'Two documents disagree about the check-in time. One says 15:00, the other 16:00.',
      citations: [{ path: 'front-desk.md', line: 12, excerpt: 'check-in 15:00' }],
    },
  },
  connector_sweep: {
    schema: 'cabinet.connector-sweep/v1',
    swept_at: '2026-08-14T09:05:00Z',
    declared: 2,
    calls: 2,
    connectors: [
      { name: 'calendar', connected: true, items: 40, calls: 1 },
      { name: 'notes', connected: true, items: 12, calls: 1 },
    ],
  },
  created_at: '2026-08-14T08:00:00Z',
  updated_at: '2026-08-14T09:06:00Z',
} as unknown as OnboardingState

/** The minimum a journey can carry and still have arrived. */
const BARE = {
  ...FULL,
  seed: undefined,
  organization: undefined,
  connector_sweep: undefined,
} as unknown as OnboardingState

/**
 * THE ARM. Every clause must (a) declare a path that resolves in this state and
 * (b) be built from words that are actually in it. `value` is compared piecewise
 * so a joined list ("calendar, notes") is checked name by name rather than as a
 * string the state never contained.
 */
function assertNoInvention(state: OnboardingState, clauses: ArrivalClause[]) {
  const serialized = JSON.stringify(state)
  for (const clause of clauses) {
    expect(readPath(state, clause.path), `${clause.id}: path ${clause.path} is dead`).toBeDefined()
    for (const piece of clause.value.split(', ')) {
      expect(serialized, `${clause.id}: “${piece}” is not in the journey state`).toContain(piece)
    }
    expect(clause.text, `${clause.id}: the sentence dropped its own value`).toContain(clause.value)
  }
}

describe('the arrival summary is assembled from recorded answers', () => {
  it('reads every answered clause, in the order they are worth reading', () => {
    const clauses = arrivalClauses(FULL)
    expect(clauses.map((c) => c.id)).toEqual([
      'who',
      'organization',
      'window',
      'finding',
      'tools',
    ])
  })

  it('invents nothing — every clause traces to its own recorded answer', () => {
    assertNoInvention(FULL, arrivalClauses(FULL))
  })

  it('repeats back the PATH that was approved, never just the folder name', () => {
    const window = arrivalClauses(FULL).find((c) => c.id === 'window')
    expect(window?.text).toContain('/Users/host/Documents/ryokan')
    // The label alone would let two different folders make the same sentence —
    // the lesson the Charter card paid for.
    expect(window?.path).toBe('source.root')
  })

  it('shows the finding HEADLINE, and the headline is a prefix of the record', () => {
    const finding = arrivalClauses(FULL).find((c) => c.id === 'finding')
    expect(finding?.value).toBe('Two documents disagree about the check-in time.')
    const recorded = readPath(FULL, 'first_dividend.finding.summary') as string
    expect(recorded.startsWith(finding!.value)).toBe(true)
    // …and the rest is not deleted: it is rendered in full under "What I found"
    // on the same screen — pinned in journey-card.test.ts.
    expect(recorded.length).toBeGreaterThan(finding!.value.length)
  })

  it('names the connected tools from the sweep, not from a count', () => {
    const tools = arrivalClauses(FULL).find((c) => c.id === 'tools')
    expect(tools?.value).toBe('calendar, notes')
  })
})

describe('an unanswered question produces silence, never a plausible filler', () => {
  it('drops the clauses whose answers are missing', () => {
    const clauses = arrivalClauses(BARE)
    expect(clauses.map((c) => c.id)).toEqual(['window', 'finding'])
    assertNoInvention(BARE, clauses)
  })

  it('drops a clause whose answer is present but blank', () => {
    const blank = { ...FULL, seed: { text: '   ', answered_at: 'x' } } as unknown as OnboardingState
    expect(arrivalClauses(blank).map((c) => c.id)).not.toContain('who')
  })

  it('drops the tools clause when the sweep found no connector', () => {
    const none = {
      ...FULL,
      connector_sweep: { ...FULL.connector_sweep!, connectors: [] },
    } as unknown as OnboardingState
    expect(arrivalClauses(none).map((c) => c.id)).not.toContain('tools')
  })

  it('returns nothing at all for no journey', () => {
    expect(arrivalClauses(null)).toEqual([])
    expect(arrivalClauses(undefined)).toEqual([])
  })
})

describe('the cap', () => {
  it('is four, and the screen shows at most that many', () => {
    expect(ARRIVAL_CLAUSE_LIMIT).toBe(4)
    expect(arrivalClauses(FULL).slice(0, ARRIVAL_CLAUSE_LIMIT)).toHaveLength(4)
  })

  it('only ever drops clauses that have their own section further down', () => {
    // The cap moves a fact, it does not delete one. Everything past the cap is
    // rendered in full by the management sections — window, finding, tools.
    const dropped = arrivalClauses(FULL).slice(ARRIVAL_CLAUSE_LIMIT)
    for (const clause of dropped) {
      expect(['window', 'finding', 'tools']).toContain(clause.id)
    }
  })
})

describe('THE SENSOR FIRES', () => {
  it('rejects a clause that says more than the record does', () => {
    const invents: ArrivalClause[] = [
      {
        id: 'who',
        provenance: 'you told me',
        path: 'seed.text',
        // One word the operator never wrote.
        value: 'I run a small luxury ryokan on the coast',
        text: '“I run a small luxury ryokan on the coast”',
      },
    ]
    expect(() => assertNoInvention(FULL, invents)).toThrow()
  })

  it('rejects a clause whose declared path does not resolve', () => {
    const dead: ArrivalClause[] = [
      {
        id: 'ghost',
        provenance: 'you told me',
        path: 'operator.name',
        value: 'ryokan',
        text: 'ryokan',
      },
    ]
    expect(() => assertNoInvention(FULL, dead)).toThrow()
  })
})
