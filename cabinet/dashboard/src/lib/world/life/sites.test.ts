/**
 * T2 LIFE — visible-work construction pipeline tests (spec v2 §3.3/D4):
 * progress is a pure function of (T0, tick); phases are ordered; crews are
 * seeded + decorative-honest; great works confirm on the 2nd keyframe or
 * are STRUCK; the ledger fold enforces rate-routing.
 */
import { describe, expect, it } from 'vitest'
import {
  CREW_CODEX,
  SITE_DURATION_TICKS,
  crewFor,
  crewSize,
  foldSiteLedger,
  footprintTier,
  lotPerimeter,
  resolveGreatWork,
  siteProgress,
  siteSign,
  struckCodex,
  type WorkSite,
} from './sites'

function site(over: Partial<WorkSite> = {}): WorkSite {
  return {
    id: 'site:workshop:t2',
    element: 'workshop',
    targetStage: 'hut',
    siteClass: 'great',
    t0Tick: 1000,
    footprint: { x: 10, y: 10, w: 4, h: 3 },
    witness: { kind: 'keyframe', ref: 'evolved_skills 3→4' },
    ...over,
  }
}

describe('siteProgress — pure f(T0, tick)', () => {
  const s = site()
  const D = SITE_DURATION_TICKS.great
  it('clamps below T0 and after completion', () => {
    expect(siteProgress(s, 0)).toEqual({ progress: 0, phase: 'clearing' })
    expect(siteProgress(s, 1000 + D * 2).progress).toBe(1)
  })
  it('phases land at the spec thresholds (<0.25/<0.75/<1/reveal)', () => {
    expect(siteProgress(s, 1000 + D * 0.1).phase).toBe('clearing')
    expect(siteProgress(s, 1000 + D * 0.5).phase).toBe('raising')
    expect(siteProgress(s, 1000 + D * 0.9).phase).toBe('finishing')
    expect(siteProgress(s, 1000 + D).phase).toBe('reveal')
  })
  it('progress is monotonic over ticks', () => {
    let prev = -1
    for (let t = 0; t <= D + 2000; t += 997) {
      const p = siteProgress(s, 1000 + t).progress
      expect(p).toBeGreaterThanOrEqual(prev)
      prev = p
    }
  })
  it('quick works run their minutes-scale durations', () => {
    expect(SITE_DURATION_TICKS.quick_small).toBe(15 * 60 * 4)
    expect(SITE_DURATION_TICKS.quick_large).toBe(90 * 60 * 4)
    expect(SITE_DURATION_TICKS.great).toBe(24 * 3600 * 4)
  })
})

describe('crew — 1 + footprint tier, seeded, decorative-honest', () => {
  it('crew size follows the log2 footprint tier, capped at 4', () => {
    expect(footprintTier(1)).toBe(0)
    expect(crewSize({ x: 0, y: 0, w: 1, h: 1 })).toBe(1)
    expect(crewSize({ x: 0, y: 0, w: 2, h: 2 })).toBe(2)
    expect(crewSize({ x: 0, y: 0, w: 4, h: 3 })).toBe(3)
    expect(crewSize({ x: 0, y: 0, w: 7, h: 4 })).toBe(4)
    expect(crewSize({ x: 0, y: 0, w: 40, h: 40 })).toBe(4) // cap
  })
  it('wrights stand on distinct perimeter tiles, facing the lot', () => {
    const s = site()
    const crew = crewFor(s, 1000 + 100)
    expect(crew).toHaveLength(3)
    const perim = new Set(lotPerimeter(s.footprint).map((p) => `${p.x},${p.y}`))
    const seen = new Set<string>()
    for (const w of crew) {
      const key = `${w.x},${w.y}`
      expect(perim.has(key)).toBe(true)
      expect(seen.has(key)).toBe(false)
      seen.add(key)
    }
  })
  it('action tracks the phase: fell → hammer → sweep → gone', () => {
    const s = site()
    const D = SITE_DURATION_TICKS.great
    expect(crewFor(s, 1000 + D * 0.1)[0].action).toBe('fell')
    expect(crewFor(s, 1000 + D * 0.5)[0].action).toBe('hammer')
    expect(crewFor(s, 1000 + D * 0.9)[0].action).toBe('sweep')
    expect(crewFor(s, 1000 + D)).toHaveLength(0) // reveal = quiet frame
  })
  it('struck sites have no crew (the crew departs)', () => {
    expect(crewFor(site(), 1000 + 100, 'struck')).toHaveLength(0)
  })
  it('deterministic: same site + tick → identical crew', () => {
    const a = crewFor(site(), 4321)
    const b = crewFor(site(), 4321)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
  })
  it('crew codex is the decorative-honest law verbatim class', () => {
    expect(CREW_CODEX).toContain('never an officer claim')
  })
})

describe('great-work 2-keyframe resolution', () => {
  it('building until a second keyframe arrives', () => {
    expect(resolveGreatWork(4, [{ tick: 100, value: 4 }])).toBe('building')
    expect(resolveGreatWork(4, [{ tick: 50, value: 3 }])).toBe('building')
  })
  it('confirmed when the next keyframe still shows the tier', () => {
    expect(
      resolveGreatWork(4, [
        { tick: 100, value: 4 },
        { tick: 200, value: 5 },
      ])
    ).toBe('confirmed')
  })
  it('STRUCK when the next keyframe does not confirm', () => {
    expect(
      resolveGreatWork(4, [
        { tick: 100, value: 4 },
        { tick: 200, value: 3 },
      ])
    ).toBe('struck')
  })
  it('struck codex cites BOTH keyframes', () => {
    const c = struckCodex(site(), { tick: 100, value: 4 }, { tick: 200, value: 3 })
    expect(c).toContain('tick 100')
    expect(c).toContain('tick 200')
    expect(c).toContain('honest false start')
  })
})

describe('site sign — WHAT/NOW/PROOF', () => {
  it('cites the witness record', () => {
    const sign = siteSign(site(), 1000 + SITE_DURATION_TICKS.great * 0.5)
    expect(sign.what).toBe('workshop → hut')
    expect(sign.now).toContain('raising')
    expect(sign.proof).toContain('census keyframe')
    expect(sign.proof).toContain('evolved_skills 3→4')
  })
  it('config-flip witness admits T0 is the observation, not the flip', () => {
    const sign = siteSign(
      site({ siteClass: 'quick_small', witness: { kind: 'config_first_seen', ref: 'probes.yml' } }),
      1000
    )
    expect(sign.proof).toContain('not the flip instant')
  })
})

describe('foldSiteLedger — P-SITES normalizer (never writes)', () => {
  it('dedupes by id keeping the EARLIEST T0 (T0 persistence)', () => {
    const fold = foldSiteLedger([site({ t0Tick: 2000 }), site({ t0Tick: 1000 })])
    expect(fold.sites).toHaveLength(1)
    expect(fold.sites[0].t0Tick).toBe(1000)
  })
  it('rejects malformed lots loudly, never silently', () => {
    const fold = foldSiteLedger([
      site({ footprint: { x: 0, y: 0, w: 0, h: 3 } }),
    ])
    expect(fold.sites).toHaveLength(0)
    expect(fold.problems[0]).toContain('malformed')
  })
  it('rate-routing: a great work with a chronicle witness is refused', () => {
    const fold = foldSiteLedger([
      site({ witness: { kind: 'chronicle', ref: 'iid 99' } }),
    ])
    expect(fold.sites).toHaveLength(0)
    expect(fold.problems[0]).toContain('rate-routing')
  })
  it('quick works may be chronicle- or config-witnessed', () => {
    const fold = foldSiteLedger([
      site({
        id: 'site:berth:chalk',
        siteClass: 'quick_small',
        witness: { kind: 'chronicle', ref: 'iid 12' },
      }),
    ])
    expect(fold.sites).toHaveLength(1)
    expect(fold.problems).toHaveLength(0)
  })
})
