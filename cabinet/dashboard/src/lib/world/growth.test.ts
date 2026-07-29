/**
 * Growth read-model tests — WHAT IS LEFT TO TEST.
 *
 * This file used to run thirteen tests, pinning `buildGrowth`'s whole model
 * against the live 2026-07-08 census keyframes. Every one of them was green on
 * 2026-07-29 over a builder with no production caller: its consumers
 * (`world-client.tsx`, `island-layout.ts`, `street-layout.ts`) had been deleted
 * with the legacy shell that day, and nothing noticed because `world-geo.ts`
 * still imports `landRadius` from the same module, so file-level reachability
 * kept reporting it live.
 *
 * Deleting the tests WITH the code they covered is the point: a test over dead
 * code is not coverage, it is a green light on a surface nobody can reach, and
 * it is worse than no test because it makes the module look maintained.
 *
 * `landRadius` keeps its pins because `world-geo.ts` calls it and it IS
 * `island_land_radius` in cabinet/world/morphology.yml — a live law row with a
 * live consumer, which is exactly the bar.
 */
import { describe, expect, it } from 'vitest'
import { landRadius } from './growth'

describe('landRadius — island fold law (morphology island_land_radius)', () => {
  it('is R = 24 + 6*floor(log10(total_events+1))', () => {
    expect(landRadius(0)).toBe(24) // log10(0+1) = 0 — the day-zero islet
    // The +1 puts the step ONE SHORT of each power of ten, not on it: at 9 the
    // argument is already 10. Written out because the first draft of this test
    // asserted the steps on the round numbers and was wrong in both directions.
    expect(landRadius(8)).toBe(24)
    expect(landRadius(9)).toBe(30)
    expect(landRadius(10)).toBe(30)
    expect(landRadius(99)).toBe(36)
    expect(landRadius(999)).toBe(42)
    expect(landRadius(1_000)).toBe(42)
    expect(landRadius(155_784)).toBe(54) // the live 2026-07-08 keyframe
  })

  it('treats absent / broken / negative counts as day zero, never as NaN', () => {
    expect(landRadius(-1)).toBe(24)
    expect(landRadius(Number.NaN)).toBe(24)
    expect(landRadius(Number.POSITIVE_INFINITY)).toBe(24)
  })

  it('never shrinks as the org grows (a fold law that reversed would be a bug)', () => {
    let prev = -Infinity
    for (const n of [0, 1, 10, 100, 1_000, 10_000, 100_000, 1_000_000]) {
      const r = landRadius(n)
      expect(r).toBeGreaterThanOrEqual(prev)
      prev = r
    }
  })
})
