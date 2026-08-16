/**
 * The screen router — one state in, exactly one screen out, for every state the
 * core can produce.
 *
 * WHY THIS FILE EXISTS AT ALL. Screens replacing each other is only safe if
 * "which screen?" is DECIDABLE. The design it replaces was a pile of additive
 * `&&`-ed predicates over one card, and its two measured defects were both
 * routing defects: a panel that never left, and a finished journey with no
 * screen of its own. Every law below is about that — total coverage, no state
 * with two answers, and no state with none.
 *
 * THE STAGE LIST IS PINNED TO THE CORE, not to a copy of it. `journey.STAGES`
 * in framework/onboarding/journey.py is parsed here, so a stage added to the
 * product with no screen turns this red — the same discipline flow-rail.test.ts
 * applies to the rail and parity.test.ts applies to the action vocabulary.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  ASK_SCREENS,
  FLOW_SCREENS,
  NO_ASKS,
  firstOpenAsk,
  resumeInput,
  screenFor,
  type OpenAsks,
  type RouteInput,
  type ScreenId,
} from './screen-router'
import type { WizardStepId } from './wizard'

// <root>/cabinet/dashboard/src/lib/onboarding → five levels up = <root>
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..')
const CORE = path.join(REPO_ROOT, 'framework', 'onboarding', 'journey.py')

/** Every stage the core declares, read from the core rather than restated. */
function coreStages(): string[] {
  const source = fs.readFileSync(CORE, 'utf8')
  const match = /^STAGES: tuple\[str, \.\.\.\] = \(\n([\s\S]*?)^\)$/m.exec(source)
  expect(match, 'STAGES tuple not found in the core — parity cannot be verified').toBeTruthy()
  // Named constants as well as literals: the core spells some stages through a
  // module-level constant, and a parser that silently skipped those would drop
  // exactly the stages most likely to be new.
  const body = match![1]
  const names = [...body.matchAll(/"([a-z_]+)"/g)].map((row) => row[1])
  for (const named of body.matchAll(/^\s{4}([A-Z_]+),\s*$/gm)) {
    const value = new RegExp(`^${named[1]} = "([a-z_]+)"`, 'm').exec(source)
    expect(value, `STAGES names ${named[1]}, which has no top-level definition`).toBeTruthy()
    names.push(value![1])
  }
  expect(names.length, 'the STAGES tuple parsed empty, which is drift and not a pass')
    .toBeGreaterThan(3)
  return names
}

/** A settled, unremarkable journey — every arm overrides only what it is about. */
function input(over: Partial<RouteInput> = {}): RouteInput {
  return {
    loading: false,
    stage: 'welcome',
    kind: 'first_window',
    arrived: false,
    step: 'welcome',
    explored: false,
    asks: NO_ASKS,
    skipped: [],
    refusedAsk: null,
    editScope: false,
    purgeArmed: false,
    scanning: false,
    fullSurface: false,
    ...over,
  }
}

const OPEN = (over: Partial<OpenAsks>): OpenAsks => ({ ...NO_ASKS, ...over })

describe('every state the core can produce lands on exactly one screen', () => {
  it('gives every stage the core declares a screen of its own', () => {
    const unrouted = coreStages().filter((stage) => {
      const screen = screenFor(input({ stage, kind: 'x' }))
      // `status` is the honest fallback, so a stage that lands there is only
      // acceptable if it is one the flow genuinely has no screen for. The
      // arrival stages resolve through `arrived`, checked separately below.
      return screen === 'status' && !['complete', 'orientation_offered'].includes(stage)
    })
    expect(unrouted, 'stages with no screen of their own').toEqual([])
  })

  it('is a FUNCTION — the same state always answers the same screen', () => {
    const state = input({ stage: 'welcome', step: 'discover', explored: true })
    const answers = new Set(Array.from({ length: 25 }, () => screenFor(state)))
    expect([...answers]).toEqual(['sweep'])
  })

  it('routes the whole forward path, one screen per position', () => {
    const walk: Array<[Partial<RouteInput>, ScreenId]> = [
      [{ step: 'welcome' }, 'welcome'],
      [{ step: 'role' }, 'you'],
      [{ step: 'dream' }, 'dream'],
      [{ step: 'start' }, 'begin'],
      [{ step: 'window' }, 'folder'],
      [{ step: 'discover' }, 'connect'],
      [{ step: 'discover', explored: true }, 'sweep'],
      [{ stage: 'charter_pending' }, 'approve'],
      [{ scanning: true }, 'look'],
      [{ stage: 'dividend_ready' }, 'find'],
      [{ stage: 'complete', kind: 'arrival', arrived: true }, 'arrival'],
    ]
    for (const [over, expected] of walk) {
      expect(screenFor(input(over)), JSON.stringify(over)).toBe(expected)
    }
  })

  it('leaves no screen unreachable — a screen nothing routes to is dead code', () => {
    const reached = new Set<ScreenId>([
      screenFor(input({ loading: true, stage: '' })),
      screenFor(input({ stage: '' })),
      screenFor(input({ step: 'welcome' })),
      screenFor(input({ step: 'role' })),
      screenFor(input({ step: 'dream' })),
      screenFor(input({ step: 'start' })),
      screenFor(input({ step: 'discover' })),
      screenFor(input({ step: 'discover', explored: true })),
      screenFor(input({ step: 'discover', explored: true, asks: OPEN({ identity: true }) })),
      screenFor(input({ step: 'discover', explored: true, asks: OPEN({ salience: true }) })),
      screenFor(input({ step: 'discover', explored: true, asks: OPEN({ organization: true }) })),
      screenFor(input({ step: 'window' })),
      screenFor(input({ stage: 'charter_pending' })),
      screenFor(input({ scanning: true })),
      screenFor(input({ stage: 'dividend_ready' })),
      screenFor(input({ stage: 'complete', kind: 'arrival', arrived: true })),
      screenFor(input({ stage: 'paused' })),
      screenFor(input({ stage: 'revoked' })),
      screenFor(input({ stage: 'purged' })),
      screenFor(input({ stage: 'nothing_like_this' })),
      screenFor(input({ purgeArmed: true })),
    ])
    const declared: ScreenId[] = [
      'loading', 'unavailable', 'welcome', 'you', 'dream', 'begin', 'connect',
      'sweep', 'identity', 'salience', 'organization', 'folder', 'approve',
      'look', 'find', 'arrival', 'paused', 'revoked', 'purged', 'status', 'purge',
    ]
    expect([...declared].filter((screen) => !reached.has(screen))).toEqual([])
  })
})

describe('precedence — the order of the rules is the design', () => {
  it('a typed destructive confirmation outranks everything under it', () => {
    expect(
      screenFor(input({ purgeArmed: true, scanning: true, stage: 'dividend_ready' }))
    ).toBe('purge')
  })

  it('a read in flight outranks the stage it is about to change', () => {
    expect(screenFor(input({ scanning: true, stage: 'charter_pending' }))).toBe('look')
  })

  it('changing what may be read outranks the flow, from anywhere', () => {
    expect(screenFor(input({ editScope: true, stage: 'complete', arrived: true, kind: 'arrival' })))
      .toBe('folder')
  })

  it('a refused answer re-opens its own question rather than moving on', () => {
    expect(
      screenFor(input({ step: 'discover', explored: true, refusedAsk: 'salience' }))
    ).toBe('salience')
  })
})

describe('the earned asks fire only while unanswered', () => {
  it('asks nothing when nothing is open', () => {
    expect(firstOpenAsk(NO_ASKS)).toBeNull()
    expect(screenFor(input({ step: 'discover', explored: true }))).toBe('sweep')
  })

  it('asks in the order that unblocks the rest', () => {
    expect(firstOpenAsk(OPEN({ identity: true, salience: true, organization: true })))
      .toBe('identity')
    expect(firstOpenAsk(OPEN({ salience: true, organization: true }))).toBe('salience')
    expect(firstOpenAsk(OPEN({ organization: true }))).toBe('organization')
  })

  it('a skipped question is not a wall — the flow moves past it', () => {
    const asks = OPEN({ identity: true, salience: true })
    expect(firstOpenAsk(asks, ['identity'])).toBe('salience')
    expect(firstOpenAsk(asks, ['identity', 'salience'])).toBeNull()
    expect(
      screenFor(input({ step: 'discover', explored: true, asks, skipped: ['identity', 'salience'] }))
    ).toBe('sweep')
  })

  it('never re-asks an answered question, whatever this session did', () => {
    // The open set is derived from the core's offer plus committed state, so
    // "answered" is a fact on the record — this arm is that nothing else can
    // put an ask back on the screen.
    for (const ask of ASK_SCREENS) {
      expect(screenFor(input({ step: 'discover', explored: true, asks: NO_ASKS })))
        .not.toBe(ask)
    }
  })
})

describe('the ending is a management view, never the wizard', () => {
  it('a finished journey lands on the arrival', () => {
    expect(screenFor(input({ stage: 'complete', kind: 'arrival', arrived: true })))
      .toBe('arrival')
  })

  it('the legacy terminal stage lands there too', () => {
    expect(screenFor(input({ stage: 'orientation_offered', kind: 'arrival', arrived: true })))
      .toBe('arrival')
  })

  it('a stage claiming completion with nothing behind it does NOT get a success screen', () => {
    // THE DEGENERATE END. A hand-edited or half-restored state file must not be
    // able to make the product announce a success it cannot show.
    expect(screenFor(input({ stage: 'complete', kind: 'arrival', arrived: false })))
      .toBe('status')
    expect(screenFor(input({ stage: 'complete', kind: 'first_window', arrived: true })))
      .toBe('status')
  })

  it('asking a finished journey for its remaining questions opens them one at a time', () => {
    const base = { stage: 'complete', kind: 'arrival', arrived: true, fullSurface: true } as const
    expect(screenFor(input({ ...base, asks: OPEN({ identity: true }) }))).toBe('identity')
    expect(screenFor(input({ ...base, asks: OPEN({ identity: true }), skipped: ['identity'] })))
      .toBe('arrival')
    expect(screenFor(input({ ...base }))).toBe('arrival')
  })

  it('no URL and no step can put a finished operator back at question one', () => {
    // The wizard steps are only read inside the welcome stage, so a stale step
    // riding a finished journey cannot reopen the interview.
    const steps: WizardStepId[] = ['welcome', 'role', 'dream', 'start', 'window', 'discover']
    for (const step of steps) {
      const screen = screenFor(
        input({ stage: 'complete', kind: 'arrival', arrived: true, step, fullSurface: true })
      )
      expect(['arrival'], `step ${step} escaped the ending`).toContain(screen)
    }
  })
})

describe('a returning operator resumes on the right screen', () => {
  const base = {
    loading: false,
    stage: 'welcome',
    kind: 'first_window',
    arrived: false,
    asks: NO_ASKS,
    skipped: [],
    refusedAsk: null,
    editScope: false,
    purgeArmed: false,
    scanning: false,
    fullSurface: false,
  }

  it('a journey with no answers resumes at the door', () => {
    expect(screenFor(resumeInput(base, { seedAnswered: false, preference: undefined, swept: false })))
      .toBe('welcome')
  })

  it('answers given and a folder chosen resumes at the folder', () => {
    expect(screenFor(resumeInput(base, { seedAnswered: true, preference: 'point', swept: false })))
      .toBe('folder')
  })

  it('answers given and the connect branch chosen resumes at the catalog', () => {
    expect(screenFor(resumeInput(base, { seedAnswered: true, preference: 'decide', swept: false })))
      .toBe('connect')
  })

  it('a sweep on the record resumes PAST the catalog, never back into it', () => {
    // Resuming into the connect step would ask the operator to connect a tool
    // they have already connected and read.
    expect(screenFor(resumeInput(base, { seedAnswered: true, preference: 'decide', swept: true })))
      .toBe('sweep')
  })

  it('a sweep on the record with an open ask resumes at the ask', () => {
    const resumed = resumeInput(
      { ...base, asks: OPEN({ salience: true }) },
      { seedAnswered: true, preference: 'decide', swept: true }
    )
    expect(screenFor(resumed)).toBe('salience')
  })
})

describe('the rail only draws where there is progress to report', () => {
  it('every flow screen is a step, and no notice is', () => {
    for (const screen of ['paused', 'revoked', 'purged', 'status', 'purge', 'arrival'] as ScreenId[]) {
      expect(FLOW_SCREENS).not.toContain(screen)
    }
    for (const screen of ['welcome', 'you', 'folder', 'approve', 'find'] as ScreenId[]) {
      expect(FLOW_SCREENS).toContain(screen)
    }
  })
})
