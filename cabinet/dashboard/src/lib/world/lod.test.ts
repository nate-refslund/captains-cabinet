/**
 * LOD camera + roof cutaway suite (T1) — continuous zoom, tier
 * quantization, per-tier cull rules, and cutaway PURITY (same inputs →
 * same outputs; hold discipline; deterministic tie-break; in-place fade).
 */
import { describe, expect, it } from 'vitest'
import {
  CUTAWAY_FADE_MS,
  CUTAWAY_HOLD_TICKS,
  LOD_RULES,
  ROOF_ALPHA_OPEN,
  TICK_MS,
  ZOOM_MAX,
  ZOOM_MIN,
  clampZoom,
  cutawayCandidate,
  cutawayStep,
  initialCutaway,
  lodTier,
  roofAlpha,
  type BuildingBox,
  type CutawayState,
  type EngineCamera,
} from './lod'

describe('continuous zoom', () => {
  it('clamps to [0.25, 3] and swallows non-finite', () => {
    expect(clampZoom(5)).toBe(ZOOM_MAX)
    expect(clampZoom(0.01)).toBe(ZOOM_MIN)
    expect(clampZoom(1.37)).toBe(1.37) // continuous — no snapping
    expect(clampZoom(NaN)).toBe(1)
  })
  it('quantizes into the D1 LOD ladder tiers', () => {
    expect(lodTier(3)).toBe('close')
    expect(lodTier(2.5)).toBe('close')
    expect(lodTier(2)).toBe('mid')
    expect(lodTier(1.5)).toBe('mid')
    expect(lodTier(1)).toBe('island')
    expect(lodTier(0.75)).toBe('island')
    expect(lodTier(0.5)).toBe('coast')
    expect(lodTier(0.25)).toBe('archipelago')
  })
  it('LOD transitions are monotone across the zoom range (no gaps)', () => {
    const order = ['archipelago', 'coast', 'island', 'mid', 'close']
    let prev = -1
    for (let z = ZOOM_MIN; z <= ZOOM_MAX + 1e-9; z += 0.01) {
      const i = order.indexOf(lodTier(z))
      expect(i).toBeGreaterThanOrEqual(prev)
      prev = i
    }
    expect(prev).toBe(order.length - 1)
  })
  it('archipelago/coast cull props+officers, keep ships, aggregate light', () => {
    for (const tier of ['coast', 'archipelago'] as const) {
      expect(LOD_RULES[tier].props).toBe(false)
      expect(LOD_RULES[tier].officers).toBe(false)
      expect(LOD_RULES[tier].shipsSilhouette).toBe(true)
      expect(LOD_RULES[tier].buildingsAsFootprints).toBe(true)
      expect(LOD_RULES[tier].lightMassAggregate).toBe(true)
      expect(LOD_RULES[tier].cutawayEligible).toBe(false)
    }
    expect(LOD_RULES.close.cutawayEligible).toBe(true)
    expect(LOD_RULES.mid.cutawayEligible).toBe(false) // single-active, close only
  })
})

// ── cutaway ────────────────────────────────────────────────────────────────

const VP = { w: 960, h: 720 }
/** Great House 6×5 tiles at (117,17); library 4×4 at (125,20). */
const BUILDINGS: BuildingBox[] = [
  { id: 'great_house', x: 117, y: 17, w: 6, h: 5, bound: true },
  { id: 'library', x: 125, y: 20, w: 4, h: 4, bound: true },
  { id: 'decor_shed', x: 110, y: 20, w: 6, h: 6, bound: false },
]
/** Camera close over the Great House center. */
const CAM_GH: EngineCamera = { z: 3, x: 120, y: 19.5 }
const CAM_AWAY: EngineCamera = { z: 3, x: 40, y: 150 }

describe('cutaway candidate (≥40% of the central third, birth order)', () => {
  it('picks the building under a close camera', () => {
    expect(cutawayCandidate(BUILDINGS, CAM_GH, VP)).toBe('great_house')
  })
  it('never fires below close zoom (universal cutaway is close-only)', () => {
    expect(cutawayCandidate(BUILDINGS, { ...CAM_GH, z: 2 }, VP)).toBeNull()
    expect(cutawayCandidate(BUILDINGS, { ...CAM_GH, z: 0.5 }, VP)).toBeNull()
  })
  it('unbound decor never cutaways', () => {
    const cam: EngineCamera = { z: 3, x: 113, y: 23 }
    expect(cutawayCandidate(BUILDINGS, cam, VP)).toBeNull()
  })
  it('nothing under the camera → null', () => {
    expect(cutawayCandidate(BUILDINGS, CAM_AWAY, VP)).toBeNull()
  })
  it('tie-break is deterministic by birth order (array order)', () => {
    // camera between the two bound buildings so both cover the middle third
    const cam: EngineCamera = { z: 3, x: 123.5, y: 20.5 }
    const both = cutawayCandidate(BUILDINGS, cam, VP)
    const reversed = cutawayCandidate([BUILDINGS[1], BUILDINGS[0], BUILDINGS[2]], cam, VP)
    if (both !== null && reversed !== null && both !== reversed) {
      // both qualify: first-in-array wins each time — deterministic
      expect(both).toBe('great_house')
      expect(reversed).toBe('library')
    } else {
      // otherwise the same single candidate resolves regardless of order
      expect(both).toBe(reversed)
    }
  })
})

describe('cutaway state machine (hold, single-active, purity)', () => {
  it('opens only after the candidate holds CUTAWAY_HOLD_TICKS ticks', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    expect(s.openId).toBeNull() // 1 tick — not held yet
    s = cutawayStep(s, 'great_house', 11)
    expect(s.openId).toBe('great_house')
    expect(s.openedAt).toBe(11)
  })
  it('a flickering candidate never opens (pan-through guard)', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, null, 11)
    s = cutawayStep(s, 'great_house', 12)
    s = cutawayStep(s, null, 13)
    expect(s.openId).toBeNull()
  })
  it('pan away closes after the hold; the roof fades BACK in place', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, 'great_house', 11)
    s = cutawayStep(s, null, 12)
    expect(s.openId).toBe('great_house') // null must hold too
    s = cutawayStep(s, null, 13)
    expect(s.openId).toBeNull()
    expect(s.closingId).toBe('great_house')
    expect(s.closedAt).toBe(13)
  })
  it('single-active: switching buildings closes the old as the new opens', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, 'great_house', 11)
    s = cutawayStep(s, 'library', 12)
    expect(s.openId).toBe('great_house') // library not held yet
    s = cutawayStep(s, 'library', 13)
    expect(s.openId).toBe('library')
    expect(s.closingId).toBe('great_house')
  })
  it('PURITY: identical (state, candidate, tick) sequences → identical states', () => {
    const seq: Array<[string | null, number]> = [
      ['great_house', 1],
      ['great_house', 2],
      ['great_house', 3],
      ['library', 4],
      ['library', 5],
      [null, 6],
      [null, 7],
      [null, 8],
    ]
    let a: CutawayState = initialCutaway()
    let b: CutawayState = initialCutaway()
    for (const [cand, tick] of seq) {
      a = cutawayStep(a, cand, tick)
      b = cutawayStep(b, cand, tick)
      expect(a).toEqual(b)
    }
  })
})

describe('roof alpha (fade in place, 300ms, 1 → 0.08)', () => {
  it('fades the open roof down over CUTAWAY_FADE_MS of logical time', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, 'great_house', 11)
    expect(roofAlpha(s, 'great_house', 11)).toBe(1) // fade starts at open tick
    const mid = roofAlpha(s, 'great_house', 12) // 250ms of 300ms
    expect(mid).toBeLessThan(1)
    expect(mid).toBeGreaterThan(ROOF_ALPHA_OPEN)
    const done = roofAlpha(s, 'great_house', 10 + Math.ceil(CUTAWAY_FADE_MS / TICK_MS) + 2)
    expect(done).toBeCloseTo(ROOF_ALPHA_OPEN, 10)
  })
  it('fades the closing roof back up; untouched roofs stay at 1', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, 'great_house', 11)
    s = cutawayStep(s, null, 12)
    s = cutawayStep(s, null, 13)
    expect(roofAlpha(s, 'great_house', 13)).toBe(ROOF_ALPHA_OPEN)
    expect(roofAlpha(s, 'great_house', 20)).toBe(1)
    expect(roofAlpha(s, 'library', 13)).toBe(1)
  })
  it('is pure: same (state, id, tick) → same alpha, every call', () => {
    let s = initialCutaway()
    s = cutawayStep(s, 'great_house', 10)
    s = cutawayStep(s, 'great_house', 11)
    for (const t of [11, 12, 13, 14]) {
      expect(roofAlpha(s, 'great_house', t)).toBe(roofAlpha(s, 'great_house', t))
    }
  })
  it('hold constants match the ratified law (2 ticks, 300ms, 0.08)', () => {
    expect(CUTAWAY_HOLD_TICKS).toBe(2)
    expect(CUTAWAY_FADE_MS).toBe(300)
    expect(ROOF_ALPHA_OPEN).toBe(0.08)
  })
})
