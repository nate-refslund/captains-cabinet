/**
 * Growth read-model — what survives of it.
 *
 * WHAT THIS FILE WAS. A whole-world read-model from census keyframes to render
 * tiers (`buildGrowth` → `GrowthModel`), with a hysteresis pair per surface, an
 * org-age band for the street set-dressing, and the morphology tier law
 * `clamp(floor(log2(S/base + 1)), 0, 7)`. Its consumers were the top-down
 * outdoor scenes: `world-client.tsx` called `buildGrowth`, and
 * `island-layout.ts` and `street-layout.ts` consumed the model it returned.
 *
 * WHY IT IS A THIRD OF ITS FORMER SIZE. Those three files were deleted with the
 * legacy shell on 2026-07-29, and the model went with them — but the module
 * stayed whole, because `world-geo.ts` still imports `landRadius` from it and
 * file-granularity reachability therefore reports the file as live. NINE
 * exports (`tier`, `surfaceGrowth`, `GrowthSurface`, `ageDays`, `streetAgeBand`,
 * `StreetAgeBand`, `GrowthModel`, `GROWTH_BASES`, `buildGrowth`) had no
 * production caller at all, and `growth.test.ts` ran thirteen green tests over
 * a builder nothing called. A suite that passes over dead code is not covering
 * anything; it is manufacturing confidence, and it makes the module look
 * maintained to the next reader.
 *
 * The isometric island does not use this shape. It renders from
 * `growth-ladders.yml` rungs resolved by `era-engine.ts` into
 * `resolution.elements`, which `iso-scene.layoutStateFrom` turns into the
 * `LayoutState` the composition reads. Rungs, hysteresis and bases live THERE
 * as Captain-tunable data. A second tier law in TypeScript would be a second
 * answer to the same question — the exact defect the ladder file exists to
 * prevent — so it is deleted rather than kept warm.
 *
 * WHAT REMAINS IS WHAT IS CALLED, and `ratchets.test.ts` now checks that at
 * SYMBOL granularity rather than file granularity, so the next dead export
 * cannot hide behind a live neighbour.
 *
 * PURE: no clocks, no randomness, no fetches.
 */

/**
 * One census keyframe line from shared/interfaces/world-chronicle.jsonl.
 *
 * Consumed by /api/world/grammar, which parses the keyframe tail server-side
 * (it reads the same fenced file the binding validator executes against — no DB
 * creds and no Redis in the render path).
 */
export type CensusKeyframe = Record<string, number | string | null>

/**
 * Island fold law: land radius R = 24 + 6*floor(log10(total_events+1)).
 *
 * The one surviving caller is `world-geo.ts`, which caps it to the core grid.
 * This is `island_land_radius` in cabinet/world/morphology.yml — the formula is
 * LAW and changes by grammar PR, never by a code tweak.
 */
export function landRadius(totalEvents: number): number {
  const n = Number.isFinite(totalEvents) && totalEvents > 0 ? totalEvents : 0
  return 24 + 6 * Math.floor(Math.log10(n + 1))
}
