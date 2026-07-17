/**
 * Course fold + voyage + chart-table card (grammar v4 direction surface).
 * Pins: the three ledger-state semantics EXACTLY, the 14d tacking boundary,
 * berth-law exclusions, the grey drift copy, and the no-canvas-text law.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import type { LaneRecord } from './era-engine'
import {
  buildChartTableCard,
  daysBetween,
  DRIFT_UNMEASURED_COPY,
  laneCourseState,
  TACKING_WINDOW_DAYS,
  voyageRender,
  type CourseInput,
} from './course'
import type { PortCallsArtifact } from './directions'

const rec = (over: Partial<LaneRecord> = {}): LaneRecord => ({
  ever: 1,
  active: 0,
  achieved: 0,
  retired: 0,
  ...over,
})

const base = (over: Partial<CourseInput> = {}): CourseInput => ({
  directionLanes: ['alpha', 'beta'],
  outcomeLanes: {},
  declaredLanes: ['alpha', 'beta', 'gamma'],
  portCalls: null,
  todayISO: '2026-07-17',
  ...over,
})

describe('daysBetween', () => {
  it('whole days, inclusive edges, honest nulls', () => {
    expect(daysBetween('2026-07-02', '2026-07-17')).toBe(15)
    expect(daysBetween('2026-07-17', '2026-07-17')).toBe(0)
    expect(daysBetween('2026-07-18', '2026-07-17')).toBeNull() // future stamp
    expect(daysBetween('junk', '2026-07-17')).toBeNull()
  })
})

describe('laneCourseState — the reduced honest set', () => {
  it('docked_refitting: ≥1 active outcome = open window (a ledger claim)', () => {
    const out = laneCourseState(
      base({ outcomeLanes: { alpha: rec({ active: 1 }) } })
    )
    expect(out.alpha.state).toBe('docked_refitting')
    expect(out.alpha.since).toBeNull() // no honest anchor date for a window
  })

  it('adrift: direction present, zero active, not retired (the renewal gap)', () => {
    const out = laneCourseState(base())
    expect(out.alpha.state).toBe('adrift')
    expect(out.beta.state).toBe('adrift')
  })

  it('tacking: flip within the window AND an active successor', () => {
    const out = laneCourseState(
      base({
        outcomeLanes: { alpha: rec({ active: 1, achieved: 1 }) },
        portCalls: { alpha: [{ date: '2026-07-10', outcome_id: 'outcome-alpha-001' }] },
      })
    )
    expect(out.alpha.state).toBe('tacking')
    expect(out.alpha.since).toBe('2026-07-10')
    expect(out.alpha.daysSinceLastPortCall).toBe(7)
  })

  it('tacking boundary: exactly 14 days is IN the window; 15 is out', () => {
    const mk = (date: string) =>
      laneCourseState(
        base({
          outcomeLanes: { alpha: rec({ active: 1, achieved: 1 }) },
          portCalls: { alpha: [{ date, outcome_id: 'o' }] },
        })
      ).alpha.state
    expect(TACKING_WINDOW_DAYS).toBe(14)
    expect(mk('2026-07-03')).toBe('tacking') // 14 days
    expect(mk('2026-07-02')).toBe('docked_refitting') // 15 days — window closed
  })

  it('a fresh flip with NO active successor is not tacking (adrift w/ direction)', () => {
    const out = laneCourseState(
      base({
        outcomeLanes: { alpha: rec({ achieved: 1 }) },
        portCalls: { alpha: [{ date: '2026-07-16', outcome_id: 'o' }] },
      })
    )
    expect(out.alpha.state).toBe('adrift')
  })

  it('berth law: undeclared pseudo-lanes get no course', () => {
    const out = laneCourseState(
      base({
        outcomeLanes: { 'world-onboarding-v1b': rec({ active: 1 }) },
      })
    )
    expect(out['world-onboarding-v1b']).toBeUndefined()
  })

  it('system-self never gets a course (its course IS the main island)', () => {
    const out = laneCourseState(
      base({
        directionLanes: ['system-self'],
        declaredLanes: ['system-self'],
        outcomeLanes: { 'system-self': rec({ active: 3 }) },
      })
    )
    expect(out).toEqual({})
  })

  it('retired and instance-test lanes stay reef buoys — no course', () => {
    const out = laneCourseState(
      base({
        directionLanes: [],
        outcomeLanes: {
          alpha: rec({ retired: 1 }),
          beta: rec({ active: 1, instanceTest: true }),
        },
      })
    )
    expect(out).toEqual({})
  })

  it('no direction + no open window = omitted (nothing honest to plot)', () => {
    const out = laneCourseState(
      base({
        directionLanes: [],
        outcomeLanes: { gamma: rec({ achieved: 1 }) },
        portCalls: { gamma: [{ date: '2026-01-01', outcome_id: 'o' }] },
      })
    )
    expect(out.gamma).toBeUndefined()
  })

  it('live-shape scenario (2026-07-17 ground truth): both lanes docked', () => {
    // polads/stephie flipped 2026-07-02 → 15 days → window closed, both
    // hold active successors → docked_refitting (the honest current state).
    const out = laneCourseState({
      directionLanes: ['stephie', 'polads', 'system-self'],
      outcomeLanes: {
        polads: rec({ ever: 3, active: 2, achieved: 1 }),
        stephie: rec({ ever: 2, active: 1, achieved: 1 }),
        stepnetwork: rec({ retired: 1 }),
        'system-self': rec({ active: 3 }),
        'world-onboarding-v1b': rec({ active: 1 }),
      },
      declaredLanes: ['adhoc', 'captains-cabinet', 'personal', 'polads', 'sensed', 'stephie', 'stepnetwork', 'system-self'],
      portCalls: {
        polads: [{ date: '2026-07-02', outcome_id: 'outcome-polads-003' }],
        stephie: [{ date: '2026-07-02', outcome_id: 'outcome-stephie-001' }],
      },
      todayISO: '2026-07-17',
    })
    expect(Object.keys(out).sort()).toEqual(['polads', 'stephie'])
    expect(out.polads.state).toBe('docked_refitting')
    expect(out.stephie.state).toBe('docked_refitting')
    expect(out.polads.portCallDates).toEqual(['2026-07-02'])
  })
})

describe('voyageRender', () => {
  const tack = (lane: string, days: number) => ({
    lane,
    state: 'tacking' as const,
    since: '2026-07-10',
    portCallDates: ['2026-07-10'],
    daysSinceLastPortCall: days,
  })

  it('moored when nothing tacks', () => {
    expect(voyageRender({})).toEqual({ underway: false, lane: null, progress: 0 })
    const docked = {
      a: { lane: 'a', state: 'docked_refitting' as const, since: null, portCallDates: [], daysSinceLastPortCall: null },
    }
    expect(voyageRender(docked).underway).toBe(false)
  })

  it('underway on the newest port call; deterministic tie-break', () => {
    const v = voyageRender({ a: tack('a', 10), b: tack('b', 3) })
    expect(v).toEqual({ underway: true, lane: 'b', progress: 3 / 14 })
    const tie = voyageRender({ b: tack('b', 3), a: tack('a', 3) })
    expect(tie.lane).toBe('a') // lane-name asc on equal freshness
  })

  it('progress is clamped to [0,1]', () => {
    expect(voyageRender({ a: tack('a', 14) }).progress).toBe(1)
    expect(voyageRender({ a: tack('a', 0) }).progress).toBe(0)
  })
})

describe('buildChartTableCard — free text lives ONLY in the authed card', () => {
  const apexDoc = {
    apex: { mission: 'Prove the org.', instruments: ['escalation_rate'] },
    lanes: { alpha: { mission: 'm', instruments: [] } },
  }
  const artifact: PortCallsArtifact = {
    schema: 'cabinet.world.port-calls/v1',
    generated_at: '2026-07-17T09:00:00+00:00',
    source_git_head: 'dab34876',
    port_calls_total: 1,
    last_port_call_date: '2026-07-02',
    lanes: { alpha: [{ date: '2026-07-02', outcome_id: 'outcome-alpha-001' }] },
  }

  it('renders apex verbatim + per-lane course rows + the grey drift row', () => {
    const courses = laneCourseState(
      base({
        directionLanes: ['alpha'],
        outcomeLanes: { alpha: rec({ active: 1 }) },
      })
    )
    const card = buildChartTableCard(apexDoc, courses, artifact)
    expect(card.nowRows[0]).toEqual({ label: 'apex', value: 'Prove the org.' })
    expect(card.nowRows.map((r) => r.label)).toContain('course · alpha')
    const drift = card.nowRows[card.nowRows.length - 1]
    expect(drift.label).toBe('drift')
    expect(drift.grey).toBe(true)
    expect(drift.value).toBe(DRIFT_UNMEASURED_COPY)
    expect(DRIFT_UNMEASURED_COPY).toContain('unmeasured')
    expect(DRIFT_UNMEASURED_COPY).toContain('org_events.product_slug')
  })

  it('uncharted apex renders grey honest absence', () => {
    const card = buildChartTableCard({ apex: null, lanes: {} }, {}, null)
    expect(card.nowRows[0].grey).toBe(true)
    expect(card.nowRows[0].value).toContain('uncharted')
    expect(card.proofLines[0]).toContain('no port-calls artifact')
  })

  it('PROOF carries dates + the as-of provenance line', () => {
    const card = buildChartTableCard(apexDoc, {}, artifact)
    expect(card.proofLines[0]).toContain('2026-07-02')
    expect(card.proofLines[card.proofLines.length - 1]).toContain('generated_at 2026-07-17T09:00:00+00:00')
    expect(card.proofLines[card.proofLines.length - 1]).toContain('source_git_head dab34876')
  })
})

describe('no-text-in-world-space law (chart table / courses / voyage)', () => {
  it('the engine canvas draws no text and never touches mission strings', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '..', '..', 'components', 'world', 'engine-canvas.tsx'),
      'utf8'
    )
    // in-canvas world text = none (spec §12): no pixi text objects, ever.
    expect(src).not.toMatch(/PIXI\.Text\b/)
    expect(src).not.toMatch(/PIXI\.BitmapText\b/)
    expect(src).not.toMatch(/PIXI\.HTMLText\b/)
    // direction free text (missions, instruments) never reaches the canvas.
    expect(src).not.toMatch(/\.mission\b/)
    expect(src).not.toMatch(/\.instruments\b/)
  })
})
