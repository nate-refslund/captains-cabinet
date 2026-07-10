/**
 * ERA × RUNG engine — resolution + hysteresis + hot-reload suite (T1).
 *
 * Pins: basket→index math (twin of world-growth-backtest.py), era
 * advance/demote hysteresis, rung modes (tier/count/flag/per_lane),
 * era-vocab selection, unmeasured honesty, and the loader's mtime
 * hot-reload + fail-closed contract against the REAL shipped config.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import yaml from 'js-yaml'
import {
  engineStep,
  eraIndex,
  eraStep,
  holdStep,
  initialEngineState,
  initialEraState,
  initialHold,
  laneRung,
  normMetric,
  rawRung,
  validateGrowthLadders,
  type EraConfig,
  type GrowthLaddersConfig,
  type LadderSpec,
} from './era-engine'
import {
  laddersPath,
  loadGrowthLadders,
  resetLaddersCache,
} from './ladders-loader'

const ERA: EraConfig = {
  names: ['camp', 'hamlet', 'town', 'beyond_bay'],
  basket: {
    a: { weight: 0.5, curve: 'linear', cap: 100, source: 'census_keyframe' },
    b: { weight: 0.5, curve: 'log2', cap: 15, source: 'census_keyframe' },
  },
  thresholds: { camp: 0, hamlet: 0.25, town: 0.55, beyond_bay: 0.8 },
  hysteresis: { advance_hold_evals: 2, demote_margin: 0.03 },
}

describe('norm + index math (backtest twin)', () => {
  it('linear caps at 1; zero/null/negative → 0', () => {
    expect(normMetric(50, 'linear', 100)).toBeCloseTo(0.5)
    expect(normMetric(200, 'linear', 100)).toBe(1)
    expect(normMetric(0, 'linear', 100)).toBe(0)
    expect(normMetric(null, 'linear', 100)).toBe(0)
    expect(normMetric(-5, 'linear', 100)).toBe(0)
  })
  it('log curves: logN(v+1)/logN(cap+1), capped', () => {
    expect(normMetric(15, 'log2', 15)).toBeCloseTo(1)
    expect(normMetric(3, 'log2', 15)).toBeCloseTo(Math.log2(4) / Math.log2(16))
    expect(normMetric(9, 'log10', 99)).toBeCloseTo(1 / 2)
  })
  it('eraIndex sums weighted norms and flags unmeasured', () => {
    const r = eraIndex({ a: 50, b: null }, ERA)
    expect(r.index).toBeCloseTo(0.25)
    expect(r.unmeasured).toEqual(['b'])
    const r2 = eraIndex({ a: 100, b: 15 }, ERA)
    expect(r2.index).toBeCloseTo(1)
    expect(r2.unmeasured).toEqual([])
  })
})

describe('era hysteresis state machine', () => {
  it('advances only after advance_hold_evals consecutive evals at the bar', () => {
    let s = initialEraState()
    let r = eraStep(s, 0.3, ERA)
    expect(r.era).toBe('camp') // one eval above hamlet — not yet
    r = eraStep(r.state, 0.3, ERA)
    expect(r.era).toBe('hamlet') // second consecutive → advance
    expect(r.transition).toEqual({ from: 'camp', to: 'hamlet' })
  })
  it('a dip resets the advance streak (no flapping)', () => {
    let r = eraStep(initialEraState(), 0.3, ERA)
    r = eraStep(r.state, 0.2, ERA) // dip below hamlet
    r = eraStep(r.state, 0.3, ERA)
    expect(r.era).toBe('camp') // streak restarted — still camp
    r = eraStep(r.state, 0.3, ERA)
    expect(r.era).toBe('hamlet')
  })
  it('demotes only below threshold − margin, held the same evals', () => {
    // reach hamlet first
    let r = eraStep(initialEraState(), 0.3, ERA)
    r = eraStep(r.state, 0.3, ERA)
    expect(r.era).toBe('hamlet')
    // 0.23 is inside the margin band (0.25 − 0.03 = 0.22): no demotion ever
    r = eraStep(r.state, 0.23, ERA)
    r = eraStep(r.state, 0.23, ERA)
    r = eraStep(r.state, 0.23, ERA)
    expect(r.era).toBe('hamlet')
    // 0.20 below the band: demote after 2 consecutive evals
    r = eraStep(r.state, 0.2, ERA)
    expect(r.era).toBe('hamlet')
    r = eraStep(r.state, 0.2, ERA)
    expect(r.era).toBe('camp')
    expect(r.transition).toEqual({ from: 'hamlet', to: 'camp', demotion: true })
  })
})

describe('rung modes', () => {
  const tierLad: LadderSpec = {
    metric: 'm',
    source: 's',
    mode: 'tier',
    base: 64,
    rungs: ['r0', 'r1', 'r2', 'r3'],
  }
  it('tier = clamp(floor(log2(v/base+1)), 0, len-1)', () => {
    expect(rawRung(tierLad, null)).toBeNull()
    expect(rawRung(tierLad, 0)).toBe(0)
    expect(rawRung(tierLad, 63)).toBe(0)
    expect(rawRung(tierLad, 64)).toBe(1)
    expect(rawRung(tierLad, 192)).toBe(2)
    expect(rawRung(tierLad, 10_000_000)).toBe(3) // clamped to last rung
  })
  it('count = one rung per real thing, clamped', () => {
    const lad: LadderSpec = { metric: 'm', source: 's', mode: 'count', rungs: ['none', 'one', 'two'] }
    expect(rawRung(lad, 0)).toBe(0)
    expect(rawRung(lad, 1)).toBe(1)
    expect(rawRung(lad, 9)).toBe(2)
  })
  it('flag honors `at` (harbormaster hut at 2 roles)', () => {
    const lad: LadderSpec = { metric: 'm', source: 's', mode: 'flag', at: 2, rungs: ['none', 'hut'] }
    expect(rawRung(lad, 1)).toBe(0)
    expect(rawRung(lad, 2)).toBe(1)
  })
  it('per_lane: reef for retired AND instance-test lanes (Captain ruling)', () => {
    expect(laneRung(undefined)).toBe(0)
    expect(laneRung({ ever: 0, active: 0, achieved: 0, retired: 0 })).toBe(0)
    expect(laneRung({ ever: 1, active: 0, achieved: 0, retired: 1 })).toBe(0) // retired → reef
    expect(laneRung({ ever: 3, active: 2, achieved: 1, retired: 0, instanceTest: true })).toBe(0) // 'sensed' law
    expect(laneRung({ ever: 1, active: 1, achieved: 0, retired: 0 })).toBe(1) // dock r0
    expect(laneRung({ ever: 3, active: 2, achieved: 1, retired: 0 })).toBe(2) // warehouses r1
  })
})

describe('rung hysteresis (hold)', () => {
  it('first measurement lands immediately; changes hold N evals', () => {
    let h = initialHold()
    h = holdStep(h, 2, 2)
    expect(h.visible).toBe(2) // day one of hysteresis is itself honest
    h = holdStep(h, 3, 2)
    expect(h.visible).toBe(2) // candidate, not yet
    h = holdStep(h, 3, 2)
    expect(h.visible).toBe(3) // held 2 evals → moves
  })
  it('null (unmeasured) never moves the visible rung', () => {
    let h = holdStep(initialHold(), 1, 2)
    h = holdStep(h, null, 2)
    expect(h.visible).toBe(1)
  })
  it('a wobbling candidate never lands (2-keyframe law)', () => {
    let h = holdStep(initialHold(), 1, 2)
    h = holdStep(h, 2, 2)
    h = holdStep(h, 1, 2)
    h = holdStep(h, 2, 2)
    expect(h.visible).toBe(1)
  })
})

// ── the REAL shipped config resolves the whole world ────────────────────────

describe('engineStep over the shipped growth-ladders.yml', () => {
  const raw = yaml.load(fs.readFileSync(laddersPath(path.resolve(__dirname, '..', '..', '..', '..', '..')), 'utf8'))
  const { config, problems } = validateGrowthLadders(raw)
  it('the shipped config validates clean', () => {
    expect(problems).toEqual([])
    expect(config).not.toBeNull()
  })
  const cfg = config as GrowthLaddersConfig

  it('resolves the verified 2026-07-09 live values to the expected world', () => {
    // metrics = the verified: values pinned in the config itself
    const metrics: Record<string, number | null> = {}
    for (const [, lad] of Object.entries(cfg.ladders)) {
      const l = lad as LadderSpec & { verified?: { value: number } }
      if (l.verified) metrics[l.metric] = l.verified.value
    }
    metrics.org_age_days = 45
    metrics.org_events_total = 168_917
    metrics.outcomes_achieved = 2
    metrics.cells_graduated = 0
    metrics.active_lanes = 4
    const ev = {
      metrics,
      lanes: {
        bakery: { ever: 5, active: 3, achieved: 1, retired: 0 },
        newsletter: { ever: 2, active: 1, achieved: 1, retired: 0 },
        exampleco: { ever: 1, active: 0, achieved: 0, retired: 1 },
        'system-self': { ever: 3, active: 3, achieved: 0, retired: 0 },
      },
    }
    const { out } = engineStep(initialEngineState(), ev, cfg)
    // calibrated: late-hamlet @ ~0.359 (config header receipt)
    expect(out.era).toBe('camp') // first eval — hysteresis holds camp…
    const second = engineStep(engineStep(initialEngineState(), ev, cfg).state, ev, cfg)
    expect(second.out.era).toBe('hamlet') // …and the 2nd consecutive eval advances
    expect(second.out.eraIndex).toBeGreaterThan(0.3)
    expect(second.out.eraIndex).toBeLessThan(0.45)
    // the honest zeros: lighthouse lamp dark, no lit posts, veto plinth empty
    expect(out.elements.lighthouse_lamp.rung).toBe(0)
    expect(out.elements.posts_lit.rung).toBe(0)
    expect(out.elements.veto_plinth.rung).toBe(0)
    // earned structure: packet boat (2 achieved), warehouses ×2
    expect(out.elements.harbor_boat.rungName).toBe('packet_boat')
    expect(out.elements.warehouse.rung).toBe(2)
    // isle rings: bakery/newsletter r1, exampleco reef (retired ruling)
    expect(out.lanes.bakery.rungName).toBe('warehouses_r1')
    expect(out.lanes.newsletter.rungName).toBe('warehouses_r1')
    expect(out.lanes.exampleco.rungName).toBe('reef_buoy')
    expect(out.lanes['system-self']).toBeUndefined() // main island IS system-self
    // era vocab (hamlet on the 2nd eval): great house renders cottage family
    expect(second.out.elements.great_house.vocab).toBe('cottage')
  })

  it('unmeasured metric renders baseline rung, flagged — never interpolated', () => {
    const { out } = engineStep(initialEngineState(), { metrics: {} }, cfg)
    expect(out.elements.water_store.measured).toBe(false)
    expect(out.elements.water_store.rung).toBe(0)
    expect(out.elements.water_store.value).toBeNull()
    expect(out.eraUnmeasured.length).toBeGreaterThan(0)
  })

  it('deterministic: identical eval sequences resolve identically', () => {
    const ev = { metrics: { ev_session_started: 700, cells_accumulating: 18 } }
    let a = initialEngineState()
    let b = initialEngineState()
    for (let i = 0; i < 5; i++) {
      const ra = engineStep(a, ev, cfg)
      const rb = engineStep(b, ev, cfg)
      a = ra.state
      b = rb.state
      expect(ra.out).toEqual(rb.out)
    }
  })
})

// ── loader: hot-reload on mtime + fail-closed ──────────────────────────────

describe('ladders-loader hot-reload', () => {
  const GOOD = fs.readFileSync(
    laddersPath(path.resolve(__dirname, '..', '..', '..', '..', '..')),
    'utf8'
  )

  it('reloads when mtime changes; caches when it does not', () => {
    resetLaddersCache()
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ladders-'))
    const p = path.join(dir, 'growth-ladders.yml')
    fs.writeFileSync(p, GOOD)
    const first = loadGrowthLadders(p)
    expect(first.reloaded).toBe(true)
    expect(first.config).not.toBeNull()
    const cached = loadGrowthLadders(p)
    expect(cached.reloaded).toBe(false)
    // Captain VALUE edit: bump a base, back-date… touch mtime forward.
    const edited = GOOD.replace('base: 512', 'base: 256')
    fs.writeFileSync(p, edited)
    fs.utimesSync(p, new Date(), new Date(Date.now() + 5000))
    const reloaded = loadGrowthLadders(p)
    expect(reloaded.reloaded).toBe(true)
    expect(reloaded.config?.ladders.great_house.base).toBe(256)
    fs.rmSync(dir, { recursive: true, force: true })
  })

  it('fail-closes on malformed config (no stale shadow law)', () => {
    resetLaddersCache()
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ladders-'))
    const p = path.join(dir, 'growth-ladders.yml')
    fs.writeFileSync(p, GOOD)
    expect(loadGrowthLadders(p).config).not.toBeNull()
    fs.writeFileSync(p, 'schema: wrong/schema\nera: {}\n')
    fs.utimesSync(p, new Date(), new Date(Date.now() + 5000))
    const bad = loadGrowthLadders(p)
    expect(bad.config).toBeNull()
    expect(bad.problems.length).toBeGreaterThan(0)
    fs.rmSync(dir, { recursive: true, force: true })
  })

  it('missing file → null + problem, never a throw', () => {
    resetLaddersCache()
    const r = loadGrowthLadders('/nonexistent/growth-ladders.yml')
    expect(r.config).toBeNull()
    expect(r.problems[0]).toContain('unreadable')
  })

  it('untruthful config refused: a ladder without a metric citation', () => {
    const doc = yaml.load(GOOD) as Record<string, unknown>
    const ladders = doc.ladders as Record<string, Record<string, unknown>>
    delete ladders.great_house.metric
    const { config, problems } = validateGrowthLadders(doc)
    expect(config).toBeNull()
    expect(problems.some((p) => p.includes('great_house.metric'))).toBe(true)
  })
})
