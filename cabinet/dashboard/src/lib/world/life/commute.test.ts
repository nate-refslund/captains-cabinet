/**
 * T2 LIFE — dominant-focus commute tests (spec v2 §3/§12 v1a acceptance:
 * "the commute classifier simulated over a recorded chronicle window — no
 * ping-pong: switch rule 0.6 share / 2 evals / 180 s dwell holds").
 */
import { describe, expect, it } from 'vitest'
import type { ChronicleRecord } from '../types'
import {
  EVAL_EVERY_TICKS,
  MIN_DWELL_TICKS,
  ROAD_WALK_TICKS,
  SWITCH_EVALS,
  VERB_GLOSS,
  bubbleBoxPx,
  bubbleFor,
  commuteStep,
  commuterProgress,
  dominantFocus,
  initialCommuteState,
  passingGlance,
  voteFor,
  type CommuteState,
  type CommuteWalk,
} from './commute'

const NOW = Date.parse('2026-07-09T12:00:00Z')
const LANES = new Set(['polads', 'stephie'])

let IID = 0
function rec(
  verb: string,
  ageS: number,
  opts: { actor?: string; lane?: string } = {}
): ChronicleRecord {
  return {
    v: 1,
    iid: ++IID,
    src: 'org_events',
    verb,
    kind: 'event',
    actor: opts.actor ?? 'cos',
    ts: new Date(NOW - ageS * 1000).toISOString(),
    ref: null,
    attrs: opts.lane ? { lane: opts.lane } : undefined,
  }
}

describe('voteFor — §3.2 closed classification', () => {
  it('product lane votes quay; self lanes vote village', () => {
    expect(voteFor(rec('tool.call', 10, { lane: 'polads' }), LANES)).toBe('quay')
    expect(voteFor(rec('tool.call', 10, { lane: 'system-self' }), LANES)).toBe(
      'village'
    )
  })
  it('work.* with lane system-self votes VILLAGE (the exception)', () => {
    expect(
      voteFor(rec('work.completed', 10, { lane: 'system-self' }), LANES)
    ).toBe('village')
  })
  it('mission-shaped verbs without a self lane vote quay', () => {
    expect(voteFor(rec('work.completed', 10), LANES)).toBe('quay')
    expect(voteFor(rec('task.created', 10), LANES)).toBe('quay')
  })
  it('loop/skill/fidelity verbs vote village', () => {
    expect(voteFor(rec('loop.completed', 10), LANES)).toBe('village')
    expect(voteFor(rec('skill.promoted', 10), LANES)).toBe('village')
  })
  it('neutral verbs cast no vote', () => {
    expect(voteFor(rec('comms.notified', 10), LANES)).toBeNull()
    expect(voteFor(rec('session.started', 10), LANES)).toBeNull()
    expect(voteFor(rec('tool.call', 10), LANES)).toBeNull()
  })
})

describe('dominantFocus — recency-weighted window', () => {
  it('fresh quay evidence outweighs stale village evidence', () => {
    const records = [
      rec('loop.completed', 140), // village, weight 0.5^(140/75) ≈ 0.27
      rec('work.completed', 5, { lane: 'polads' }), // quay ≈ 0.95
    ]
    const f = dominantFocus('cos', records, 'working', NOW, LANES)
    expect(f.district).toBe('quay')
    expect(f.share).toBeGreaterThan(0.6)
    expect(f.trigger?.verb).toBe('work.completed')
  })
  it('records outside the 150 s window are ignored', () => {
    const f = dominantFocus(
      'cos',
      [rec('work.completed', 200, { lane: 'polads' })],
      'working',
      NOW,
      LANES
    )
    expect(f.district).toBeNull()
    expect(f.share).toBe(0)
  })
  it('presence deploying is a standing quay vote', () => {
    const f = dominantFocus('cos', [], 'deploying', NOW, LANES)
    expect(f.district).toBe('quay')
    expect(f.share).toBe(1)
    expect(f.trigger?.verb).toBe('deploying')
  })
  it("other officers' records never vote for this officer", () => {
    const f = dominantFocus(
      'cos',
      [rec('work.completed', 5, { actor: 'polads-ceo', lane: 'polads' })],
      'working',
      NOW,
      LANES
    )
    expect(f.district).toBeNull()
  })
})

describe('thought bubble — closed table, pixel class', () => {
  it('renders the REAL trigger verb from the closed table', () => {
    const b = bubbleFor({ verb: 'reviewing', lane: 'polads' })
    expect(b).toEqual({ text: 'I should review the queue · polads', kind: 'pixel' })
  })
  it('unknown verb → NO bubble (honest absence, never invented text)', () => {
    expect(bubbleFor({ verb: 'somebody.new_verb', lane: null })).toBeNull()
  })
  it('non-identifier lane slugs are dropped, never rendered', () => {
    const b = bubbleFor({ verb: 'deploying', lane: 'Nate <naref@x.dk>' })
    expect(b?.text).toBe('I should ship this')
  })
  it('every gloss is short, closed, and free of markup', () => {
    for (const gloss of Object.values(VERB_GLOSS)) {
      expect(gloss.length).toBeLessThanOrEqual(24)
      expect(gloss).toMatch(/^[a-z .]+$/)
    }
  })
  it('pixel box is integer and text-proportional', () => {
    const b = bubbleFor({ verb: 'working', lane: null })!
    const box = bubbleBoxPx(b)
    expect(Number.isInteger(box.w)).toBe(true)
    expect(box.w).toBe(b.text.length * 6 + 10)
    expect(box.h).toBe(16)
  })
})

// ── the reducer: hysteresis / dwell / suspension ───────────────────────────

/** Drive the reducer across ticks with a fixed record set. */
function drive(
  state: CommuteState,
  ticks: number[],
  records: ChronicleRecord[],
  presenceVerb: string | null = 'working'
): { state: CommuteState; walks: CommuteWalk[]; arrivals: string[] } {
  const walks: CommuteWalk[] = []
  const arrivals: string[] = []
  for (const tick of ticks) {
    const r = commuteStep(state, {
      slug: 'cos',
      records,
      presenceVerb,
      nowTsMs: NOW,
      tick,
      productLanes: LANES,
    })
    state = r.state
    if (r.departed) walks.push(r.departed)
    if (r.arrived) arrivals.push(r.arrived)
  }
  return { state, walks, arrivals }
}

const range = (n: number) => Array.from({ length: n }, (_, i) => i)

describe('commuteStep — switch rule 0.6 share / 2 evals / 180 s dwell', () => {
  const quayRecords = [rec('work.completed', 5, { lane: 'polads' })]

  it('switches only after SWITCH_EVALS consecutive evaluations', () => {
    const { walks, arrivals, state } = drive(
      initialCommuteState(),
      range(EVAL_EVERY_TICKS * SWITCH_EVALS + ROAD_WALK_TICKS + 1),
      quayRecords
    )
    expect(walks).toHaveLength(1)
    // eval #1 at tick 0 (held 1), eval #2 at tick 60 → departure.
    expect(walks[0].startTick).toBe(EVAL_EVERY_TICKS)
    expect(walks[0].from).toBe('village')
    expect(walks[0].to).toBe('quay')
    expect(walks[0].bubble?.kind).toBe('pixel')
    expect(arrivals).toEqual(['quay'])
    expect(state.district).toBe('quay')
  })

  it('one hot record is not enough — a single eval never switches', () => {
    const { walks } = drive(
      initialCommuteState(),
      range(EVAL_EVERY_TICKS), // only tick 0 evaluates
      quayRecords
    )
    expect(walks).toHaveLength(0)
  })

  it('min-dwell holds after arrival (no immediate bounce home)', () => {
    // Arrive at quay first.
    let r = drive(
      initialCommuteState(),
      range(EVAL_EVERY_TICKS * 2 + ROAD_WALK_TICKS + 1),
      quayRecords
    )
    // Departure fires on eval #2 (tick EVAL_EVERY_TICKS); the road takes
    // ROAD_WALK_TICKS — so arrival lands at their sum.
    const arrivalTick = EVAL_EVERY_TICKS + ROAD_WALK_TICKS
    // Now the chronicle flips hard village — but dwell must hold 720 ticks.
    const villageRecords = [rec('loop.completed', 5)]
    const ticks = Array.from(
      { length: MIN_DWELL_TICKS + EVAL_EVERY_TICKS * 3 },
      (_, i) => arrivalTick + 1 + i
    )
    r = drive(r.state, ticks, villageRecords)
    expect(r.walks).toHaveLength(1)
    expect(r.walks[0].startTick - arrivalTick).toBeGreaterThanOrEqual(
      MIN_DWELL_TICKS
    )
  })

  it('ping-pong evidence never switches (share < 0.6 stays put)', () => {
    const noisy = [
      rec('work.completed', 4, { lane: 'polads' }),
      rec('loop.completed', 6),
      rec('work.assigned', 12, { lane: 'polads' }),
      rec('loop.started', 14),
    ]
    const { walks } = drive(
      initialCommuteState(),
      range(EVAL_EVERY_TICKS * 20),
      noisy
    )
    expect(walks).toHaveLength(0)
  })

  it('classifier is SUSPENDED mid-walk (no U-turns)', () => {
    const start = drive(
      initialCommuteState(),
      range(EVAL_EVERY_TICKS * 2 + 1),
      quayRecords
    )
    expect(start.state.walking).not.toBeNull()
    // Mid-walk the world flips village — the walk completes anyway.
    const mid = drive(
      start.state,
      range(ROAD_WALK_TICKS).map((i) => EVAL_EVERY_TICKS * 2 + 1 + i),
      [rec('loop.completed', 2)]
    )
    expect(mid.arrivals).toEqual(['quay'])
    expect(mid.walks).toHaveLength(0)
  })

  it('TTL-expired presence: stay put, candidates reset', () => {
    // Build one held eval first…
    const one = drive(initialCommuteState(), [0], quayRecords)
    expect(one.state.candidate).toBe('quay')
    // …then presence expires: candidate resets, nothing ever departs.
    const out = drive(
      one.state,
      range(EVAL_EVERY_TICKS * 10).map((i) => 1 + i),
      quayRecords,
      null
    )
    expect(out.walks).toHaveLength(0)
    expect(out.state.candidate).toBeNull()
    expect(out.state.district).toBe('village')
  })

  it('deterministic: identical inputs → identical walk schedules', () => {
    const ticks = range(EVAL_EVERY_TICKS * 4 + ROAD_WALK_TICKS)
    const a = drive(initialCommuteState(), ticks, quayRecords)
    const b = drive(initialCommuteState(), ticks, quayRecords)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
  })
})

describe('road progress + passing glance', () => {
  const walkTo = (to: 'quay' | 'village', startTick: number): CommuteWalk => ({
    from: to === 'quay' ? 'village' : 'quay',
    to,
    startTick,
    walkTicks: ROAD_WALK_TICKS,
    bubble: null,
  })
  it('progress is clamped 0..1', () => {
    const w = walkTo('quay', 100)
    expect(commuterProgress(w, 50)).toBe(0)
    expect(commuterProgress(w, 160)).toBeCloseTo(0.5)
    expect(commuterProgress(w, 500)).toBe(1)
  })
  it('opposite walkers meeting mid-road glance; same-direction never', () => {
    const a = walkTo('quay', 0)
    const b = walkTo('village', 0)
    // Both at road position 0.5 on tick 60.
    expect(passingGlance({ walk: a, tick: 60 }, { walk: b, tick: 60 })).toBe(true)
    expect(passingGlance({ walk: a, tick: 60 }, { walk: a, tick: 60 })).toBe(false)
    // Far apart on the road → no glance.
    expect(passingGlance({ walk: a, tick: 10 }, { walk: b, tick: 10 })).toBe(false)
  })
})
