/**
 * T2 LIFE — THE DETERMINISM SUITE (spec v2 §12 v1a acceptance: "determinism
 * replay check — same state + tick ⇒ byte-identical output, two runs").
 *
 * Every LIFE behavior rides one reducer (lifeStep). This suite replays a
 * synthetic-but-chronicle-shaped 600-tick window TWICE — presence changes,
 * chronicle evolution, a killswitch freeze in the middle — and requires the
 * two output sequences to be byte-identical, plus behavior-level ratchets:
 * the commute holds its 0.6/2-evals/180s hysteresis over the noisy window
 * (no ping-pong), the world freezes byte-stably under killswitch, and no
 * module leaks wall-clock or unseeded randomness (the tree-wide grep
 * ratchet in ../ratchets.test.ts covers life/ automatically — asserted
 * here so a future move of this directory fails loudly).
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import type { ChronicleRecord } from '../types'
import { EVAL_EVERY_TICKS, ROAD_WALK_TICKS } from './commute'
import { initialLifeState, lifeStep, type LifeInput, type LifeState } from './life'
import type { LifeGrammar } from './life-grammar'
import { parseLifeGrammar } from './life-grammar'

const NOW = Date.parse('2026-07-09T12:00:00Z')
const LANES = new Set(['bakery', 'newsletter'])

const CONFIG: LifeGrammar = parseLifeGrammar(`
version: 3
commute:
  switch_share: 0.6
  switch_evals: 2
  dwell_s: 180
  walk_s: [20, 30]
  bubble: verb_icon
construction:
  quick_small_min: 15
  quick_large_min: 90
  great_hours: 24
  phases: {clearing: 0.25, raising: 0.75, finishing: 1.0}
  site_ledger: "shared/interfaces/world-sites.jsonl"
fauna:
  cat: {home: wardroom_kettle_counter, decorative: true}
  dog: {home: village, decorative: true}
  birds: {home: sky, decorative: true}
  butterflies: {home: meadow, decorative: true}
  fish: {home: quay_water, decorative: true}
apprentices:
  cap_per_officer: 3
`)

let IID = 0
function rec(
  verb: string,
  ageS: number,
  actor: string,
  attrs?: Record<string, string>
): ChronicleRecord {
  return {
    v: 1,
    iid: ++IID,
    src: 'org_events',
    verb,
    kind: verb === 'tool.call' ? 'Agent' : 'event',
    actor,
    ts: new Date(NOW - ageS * 1000).toISOString(),
    ref: null,
    attrs,
  }
}

/** Deterministic synthetic timeline: the input at tick t is a pure
 * function of t (which is exactly what a recorded window replays as). */
function inputAt(tick: number): LifeInput {
  IID = 1000 + tick // stable iids per tick
  const records: ChronicleRecord[] = [
    rec('work.completed', 5, 'bakery-ceo', { lane: 'bakery' }),
    rec('loop.completed', 20, 'cos'),
    rec('loop.started', 90, 'cos'),
    rec('tool.call', 30, 'cos', { tool: 'Agent' }),
  ]
  // A noisy alternating voter for the ping-pong ratchet.
  if (tick % 2 === 0) records.push(rec('work.assigned', 8, 'cos', { lane: 'bakery' }))
  else records.push(rec('skill.promoted', 8, 'cos'))
  const killswitch = tick >= 300 && tick < 380
  return {
    tick,
    nowTsMs: NOW + tick * 250,
    clockHour: 12,
    killswitch,
    officers: {
      cos: { presence: { present: true, verb: 'working' }, x: 10, y: 8 },
      'bakery-ceo': {
        presence:
          tick < 200
            ? { present: true, verb: 'deploying' }
            : { present: false },
        x: 40,
        y: 30,
      },
    },
    records,
    productLanes: LANES,
    siteEntries: [
      {
        id: 'site:workshop:t2',
        element: 'workshop',
        targetStage: 'hut',
        siteClass: 'great',
        t0Tick: 100,
        footprint: { x: 10, y: 10, w: 4, h: 3 },
        witness: { kind: 'keyframe', ref: 'evolved_skills 3→4' },
      },
    ],
    siteKeyframes: {
      'site:workshop:t2': {
        target: 4,
        obs: [{ tick: 100, value: 4 }],
      },
    },
    fauna: {
      bounds: { w: 60, h: 48 },
      flowerAnchors: [{ x: 20, y: 20 }],
      quayWater: [{ x: 30, y: 46 }],
      catPerch: { x: 15, y: 12 },
    },
    config: CONFIG,
  }
}

function replay(ticks: number): string[] {
  let state: LifeState = initialLifeState()
  const frames: string[] = []
  for (let t = 0; t < ticks; t++) {
    const r = lifeStep(state, inputAt(t))
    state = r.state
    frames.push(JSON.stringify(r.out))
  }
  return frames
}

describe('THE DETERMINISM SUITE — lifeStep replay', () => {
  const a = replay(600)
  const b = replay(600)

  it('two runs over the identical window are byte-identical, every tick', () => {
    expect(a.length).toBe(600)
    for (let t = 0; t < a.length; t++) {
      expect(a[t], `tick ${t}`).toBe(b[t])
    }
  })

  it('killswitch freezes the world byte-stably (frames re-emit verbatim)', () => {
    // Ticks 301..379 are frozen at the tick-300 world (fauna mid-flap,
    // crews mid-swing) modulo the states map, which names them frozen.
    const frozen = a.slice(305, 379)
    for (const f of frozen) {
      expect(f).toBe(a[304])
      expect(JSON.parse(f).states.cos).toBe('frozen')
    }
    // …and the world resumes moving after release.
    expect(a[390]).not.toBe(a[304])
    expect(JSON.parse(a[390]).states.cos).toBe('working')
  })

  it('no ping-pong: the noisy alternating chronicle never walks cos', () => {
    for (const f of a) {
      const out = JSON.parse(f)
      expect(out.districts.cos).toBe('village')
      expect(
        out.commuters.filter((c: { slug: string }) => c.slug === 'cos')
      ).toHaveLength(0)
    }
  })

  it('the construction site runs its pure-function pipeline in every frame', () => {
    const first = JSON.parse(a[0])
    expect(first.sites).toHaveLength(1)
    const later = JSON.parse(a[599])
    expect(later.sites[0].progress.progress).toBeGreaterThanOrEqual(
      first.sites[0].progress.progress
    )
    expect(later.sites[0].crew.length).toBeGreaterThan(0)
  })

  it('apprentice figures exist only for live runs, deterministically', () => {
    const out = JSON.parse(a[10])
    expect(
      out.apprentices.figures.some(
        (f: { officer: string }) => f.officer === 'cos'
      )
    ).toBe(true)
  })

  it('config = null → every behavior is OFF (no pixels without law)', () => {
    const r = lifeStep(initialLifeState(), { ...inputAt(50), config: null })
    expect(r.out.commuters).toHaveLength(0)
    expect(r.out.sites).toHaveLength(0)
    expect(r.out.fauna).toHaveLength(0)
    expect(r.out.apprentices.figures).toHaveLength(0)
  })
})

describe('commute departs and arrives on schedule under a clean signal', () => {
  it('a quay-classified officer walks the road once, 30 s, then lives there', () => {
    let state = initialLifeState()
    const walksSeen: number[] = []
    let arrivedTick: number | null = null
    for (let t = 0; t < EVAL_EVERY_TICKS * 3 + ROAD_WALK_TICKS + 10; t++) {
      const base = inputAt(t)
      const input: LifeInput = {
        ...base,
        killswitch: false,
        records: [rec('work.completed', 5, 'cos', { lane: 'bakery' })],
      }
      const r = lifeStep(state, input)
      state = r.state
      const cos = r.out.commuters.find((c) => c.slug === 'cos')
      if (cos) walksSeen.push(t)
      if (arrivedTick === null && r.out.districts.cos === 'quay') arrivedTick = t
    }
    expect(walksSeen.length).toBe(ROAD_WALK_TICKS)
    expect(walksSeen[0]).toBe(EVAL_EVERY_TICKS)
    expect(arrivedTick).toBe(EVAL_EVERY_TICKS + ROAD_WALK_TICKS)
  })
})

describe('ratchet coverage — life/ lives inside the ratcheted tree', () => {
  it('this directory is scanned by world ratchets (Math.random/Date.now ban)', () => {
    // ratchets.test.ts collects src/lib/world recursively; prove our
    // sources actually sit under it so the grep ratchet applies.
    const here = __dirname
    expect(here).toContain(path.join('src', 'lib', 'world'))
    for (const f of fs.readdirSync(here)) {
      if (!f.endsWith('.ts') || f.endsWith('.test.ts')) continue
      const text = fs.readFileSync(path.join(here, f), 'utf8')
      expect(text, f).not.toMatch(/Math\.random\s*\(/)
      expect(text, f).not.toMatch(/Date\.now\s*\(/)
      expect(text, f).not.toMatch(/new Date\(\s*\)/)
    }
  })
})
