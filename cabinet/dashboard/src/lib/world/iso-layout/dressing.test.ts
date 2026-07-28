/**
 * DISTRICT DRESSING tests — a district's furniture may not outlive its district.
 *
 * WHAT THIS FILE IS FOR. The Captain's 2026-07-27 frame showed the consequence
 * ledger — an open book on a stand — alone in open grass beside three fence
 * posts and a rock, with no law plot around it. Every district in dressing.ts
 * is anchored at a fixed compass point and its props were placed at fixed
 * offsets from that anchor, gated on the ERA alone. So a district whose measured
 * structure had never been built still drew its whole yard, and a district built
 * at a LOW RUNG drew a yard sized for a full one.
 *
 * EVERY ARM CARRIES ITS OWN POSITIVE CONTROL, and that is not padding. "No
 * ledger on a state with no law plot" passes trivially if the ledger can never
 * draw at all — the degenerate end of this check is a layout that emits no
 * dressing whatsoever, which is exactly the shape a fix that over-gates would
 * take. So each arm asserts BOTH directions off the same base state, changing
 * only the ladder under test.
 *
 * SOURCE MUTATIONS RUN AGAINST THESE ARMS (2026-07-27, on a scratch copy of the
 * tree, one at a time, `vitest run src/lib/world/iso-layout/dressing.test.ts`):
 *   `law-ungated`      — restore `row(life, 'law_post', …, village ? 3 : 0, …)`
 *                        and `life('consequence_ledger', …, LAW.x + 104, …)`.
 *                        Result: the two LAW arms go RED.
 *   `works-ungated`    — put the yard clutter back on `life`. Result: the WORKS
 *                        arm goes RED.
 *   `fields-ungated`   — put the farmyard back on `life`. Result: the FIELDS
 *                        arm goes RED.
 *   `homes-ungated`    — put the residential spine back on `life`. Result: the
 *                        RESIDENTIAL arm goes RED.
 *   `obs-ungated`      — put the observatory bench back on `life`. Result: the
 *                        OBSERVATORY arm goes RED.
 *   `ledger-fixed-off` — keep the gate but restore the fixed `LAW.x + 104`.
 *                        Result: the ledger-follows-the-plot arm goes RED, the
 *                        gate arms stay green (they test different things).
 *   `law-postcap-off`  — restore `village ? 3 : 0` for the post row.
 *                        Result: RED — but only after the post-count line was
 *                        added. THE FIRST RUN CAME BACK GREEN and is recorded
 *                        here rather than buried: every other arm builds a
 *                        THREE-run plot, where `Math.min(3, lawRuns)` is a
 *                        no-op, so nothing could see the cap. The fix was a
 *                        sensor (assert 1 post on a 1-run plot), not a
 *                        loosened claim.
 */
import { describe, expect, it } from 'vitest'
import type { Footprint } from './clearance'
import { dressLanding, type DressCtx, type DressItem } from './dressing'
import { composeLayout, DEFAULT_FOOTPRINTS, type Layout, type LayoutState, type Point } from './index'

const FAST = { coastline: { step: 8 } }
const SEED = 'dressing-districts'

/** A hamlet with every district built — the positive control for all of them. */
const BUILT: LayoutState = {
  era: 'hamlet',
  road: 'gravel_road',
  stages: {
    great_house: 'timber_hall',
    well: 'stone_well',
    library: 'library_hall',
    workshop: 'shed',
    outbuildings: 'small_barn',
    firepit: 'stone_ring',
    law_plot: 'wood_fence',
    observatory: 'dome_frame',
    lantern_posts: 'posts_2',
    posts_lit: 'lit_1',
  },
  counts: { officer_dwellings: 4, field_plots: 3, law_plot: 3, outbuildings: 2, lantern_posts: 2 },
}

/** BUILT minus one ladder — everything else identical, so only that changes. */
function without(...ladders: string[]): LayoutState {
  const stages = { ...BUILT.stages }
  const counts = { ...BUILT.counts }
  for (const l of ladders) {
    delete stages[l]
    delete counts[l]
  }
  return { ...BUILT, stages, counts }
}

/** Buildings live on `structures`, district furniture on `dressing`. */
const kinds = (l: Layout, kind: string) =>
  [...l.structures, ...l.dressing].filter((s) => s.kind === kind)
const has = (l: Layout, kind: string) => kinds(l, kind).length > 0
const compose = (s: LayoutState) => composeLayout(s, SEED, FAST)

/** dressing.ts's own compass anchors for the two fallback districts. */
const WORKS = { x: 1830, y: 800 }
const FIELDS = { x: 1620, y: 1180 }

/** How many of these kinds stand inside one district's window. */
const near = (l: Layout, ks: readonly string[], c: { x: number; y: number }, r: number) =>
  ks.reduce(
    (n, k) => n + kinds(l, k).filter((s) => Math.hypot(s.at.x - c.x, s.at.y - c.y) <= r).length,
    0
  )

describe('a district draws its furniture only when the district was built', () => {
  it('LAW: no law plot means no ledger and no posts — with one, both return', () => {
    const built = compose(BUILT)
    const bare = compose(without('law_plot'))
    expect({
      builtLedger: has(built, 'consequence_ledger'),
      builtPosts: kinds(built, 'law_post').length > 0,
      barePlot: has(bare, 'law_plot'),
      bareLedger: has(bare, 'consequence_ledger'),
      barePosts: kinds(bare, 'law_post').length,
    }).toEqual({
      builtLedger: true,
      builtPosts: true,
      barePlot: false,
      bareLedger: false,
      barePosts: 0,
    })
  })

  it('LAW: the ledger stands at the END of the plot the rung really built', () => {
    // Two states differing ONLY in the law_plot rung. The plot row walks east
    // at 62px a run and falls 8px a run; the ledger has to walk with it, which
    // a fixed offset from the district anchor cannot do.
    const short = compose({
      ...BUILT,
      stages: { ...BUILT.stages, law_plot: 'wood_fence' },
      counts: { ...BUILT.counts, law_plot: 1 },
    })
    const long = compose({
      ...BUILT,
      stages: { ...BUILT.stages, law_plot: 'wood_fence' },
      counts: { ...BUILT.counts, law_plot: 4 },
    })
    const ledgerX = (l: Layout) => kinds(l, 'consequence_ledger')[0]?.at.x ?? null
    const plotEndX = (l: Layout) => Math.max(...kinds(l, 'law_plot').map((s) => s.at.x))
    const sx = ledgerX(short)
    const lx = ledgerX(long)
    expect({ shortDrawn: sx !== null, longDrawn: lx !== null }).toEqual({
      shortDrawn: true,
      longDrawn: true,
    })
    // it MOVED with the rung, and it sits near the far end rather than 100px
    // past it: within one plot step of the last fence run, on both states.
    expect({
      moved: lx! > sx! + 100,
      shortNearEnd: Math.abs(sx! - plotEndX(short)) < 62,
      longNearEnd: Math.abs(lx! - plotEndX(long)) < 62,
    }).toEqual({ moved: true, shortNearEnd: true, longNearEnd: true })
    // AND THE POSTS STAND INSIDE IT: at most one per fence run. Without this
    // line the `law-postcap-off` mutation came back green — the cap was a
    // no-op on every other arm's 3-run plot — which is a sensor that cannot
    // see the rule it is supposed to guard.
    expect({
      shortPosts: kinds(short, 'law_post').length,
      longPosts: kinds(long, 'law_post').length,
    }).toEqual({ shortPosts: 1, longPosts: 3 })
  })

  it('WORKS: no workshop means no yard clutter — with one, the yard returns', () => {
    // COUNTED INSIDE THE DISTRICT, not island-wide, and that is the whole
    // point: `wood_pile` and `water_trough` are also the per-officer yard prop
    // on the residential row, and a global count would go green the moment the
    // dwellings changed. The window is centred on the WORKS compass anchor so
    // it covers both the workshop's placed centre and the fallback.
    const built = compose(BUILT)
    const bare = compose(without('workshop'))
    const yard = (l: Layout) => near(l, ['wood_pile', 'water_trough', 'crate_single'], WORKS, 400)
    expect({ builtWorkshop: has(built, 'workshop'), builtYard: yard(built) > 0 }).toEqual({
      builtWorkshop: true,
      builtYard: true,
    })
    expect({ bareWorkshop: has(bare, 'workshop'), bareYard: yard(bare) }).toEqual({
      bareWorkshop: false,
      bareYard: 0,
    })
  })

  it('FIELDS: no outbuildings means no farmyard — with them, it returns', () => {
    // Same window discipline: the square keeps a chicken and the dojo keeps a
    // scarecrow (TRAINING has no ladder and is deliberately era-entitled), so
    // this counts the FIELDS district's own furniture and nothing else.
    const built = compose(BUILT)
    const bare = compose(without('outbuildings'))
    // 320, not 420: the square's own chicken stands 368px from the FIELDS
    // anchor, and a window that swallowed it would report a farmyard that had
    // already gone. Measured, not guessed.
    const farm = (l: Layout) => near(l, ['scarecrow', 'cart', 'veg_garden', 'chicken'], FIELDS, 320)
    expect({ builtBarn: has(built, 'outbuildings'), builtFarm: farm(built) > 0 }).toEqual({
      builtBarn: true,
      builtFarm: true,
    })
    expect({ bareBarn: has(bare, 'outbuildings'), bareFarm: farm(bare) }).toEqual({
      bareBarn: false,
      bareFarm: 0,
    })
  })

  it('RESIDENTIAL: no dwellings means no washing line and no hives', () => {
    const built = compose(BUILT)
    const bare = compose(without('officer_dwellings'))
    expect({
      builtLaundry: has(built, 'laundry_line'),
      builtHives: has(built, 'beehives'),
    }).toEqual({ builtLaundry: true, builtHives: true })
    expect({
      bareLaundry: has(bare, 'laundry_line'),
      bareHives: has(bare, 'beehives'),
    }).toEqual({ bareLaundry: false, bareHives: false })
  })

  it('OBSERVATORY: the bench needs the dome it faces', () => {
    const built = compose(BUILT)
    const bare = compose(without('observatory'))
    const benchNearDome = (l: Layout) => {
      const obs = kinds(l, 'observatory')[0]
      if (!obs) return false
      return kinds(l, 'bench').some(
        (b) => Math.hypot(b.at.x - obs.at.x, b.at.y - obs.at.y) < 140
      )
    }
    expect({ builtDome: has(built, 'observatory'), builtBench: benchNearDome(built) }).toEqual({
      builtDome: true,
      builtBench: true,
    })
    // With no dome there is no anchor to measure against, so the assertion is
    // that nothing sits where the dome would have been (960, 372 + the bench's
    // own 64/56 offset), not that benches vanish — the square still has four.
    const ghost = kinds(bare, 'bench').filter(
      (b) => Math.hypot(b.at.x - (960 + 64), b.at.y - (372 + 56)) < 140
    )
    expect({ bareDome: has(bare, 'observatory'), ghostBenches: ghost.length }).toEqual({
      bareDome: false,
      ghostBenches: 0,
    })
  })

  it('the gate NARROWS village life and never widens it: a camp is still silent', () => {
    // The whole class stays era-first. Nothing here may put a bench on a camp.
    const camp = compose({
      era: 'camp',
      road: 'dirt_path',
      stages: { great_house: 'camp_log_cabin', law_plot: 'wood_fence', observatory: 'dome_frame' },
      counts: { officer_dwellings: 1, law_plot: 3 },
    })
    const villageLife = ['bench', 'consequence_ledger', 'law_post', 'laundry_line', 'beehives']
    expect(villageLife.filter((k) => has(camp, k))).toEqual([])
  })
})

// ── the landing: nothing the shore draws may be drawn ON something ─────────

/**
 * THE BEACHED FISHING BOAT (Captain, 2026-07-27: "is it on purpose that the
 * ship is ON the ground and not water?").
 *
 * The craft the Captain saw lying along the finger pier's planks came from
 * `dressLanding`, not from the harbour: the reference's own offset,
 * `cove.x + 122`, is inside the pier's column here (the pier is rooted at
 * `cove.x + 104` and is 44 to 58px wide), and every craft carried
 * `overWater: true` as a hard-coded claim that nothing measured. Swept over 80
 * seeds x 4 eras x 5 quay rungs before the fix: 1600 of 1600 fishing boats
 * beached — 982 on the pier, 618 on the wharf — plus 752 of 3200 buoys and 30
 * of 1600 rowboats. After: 0 of each, and none dropped.
 *
 * These arms are UNIT arms on the ctx rather than sweeps, because the two
 * branches that matter are the ones a seeded island does not reach: the drift
 * (every seed found water within one or two steps) and the DROP.
 *
 * SOURCE MUTATIONS RUN AGAINST THEM (2026-07-27, scratch copy, one at a time):
 *   `landing-unchecked` — restore the direct push at the authored offset with
 *                         no `openWater` test. Result: the drift arm and the
 *                         drop arm both go RED.
 *   `landing-nodrop`    — keep the search but emit the last candidate when none
 *                         passes. Result: the drop arm goes RED.
 */
describe('the landing', () => {
  const COVE = { x: 1200, y: 1430 }
  const SHORE = 1300

  function landingCtx(openWater: ((at: Point, size: Footprint) => boolean) | null): DressCtx {
    const nope = (name: string) => (): never => {
      throw new Error(`landingCtx has no ${name}: this fixture dresses a beach only`)
    }
    return {
      era: 'hamlet',
      village: true,
      stageOf: () => null,
      countOf: () => 0,
      built: () => false,
      sizeOf: (k: string) => DEFAULT_FOOTPRINTS[k] ?? { w: 96, h: 96 },
      settle: nope('settle'),
      anchor: (p) => p,
      great: null,
      lib: null,
      works: null,
      fields: null,
      square: { x: 1200, y: 1000 },
      dwellings: [],
      shoreAt: () => SHORE,
      cove: COVE,
      openWater,
    }
  }

  it('draws its four craft where the reference put them when that is open water', () => {
    const out = dressLanding(landingCtx(() => true))
    expect(out.map((d) => d.kind)).toEqual(['boat_rowing', 'buoy', 'buoy', 'boat_fishing'])
    // the reference's own offsets, untouched when nothing is in the way
    expect(out.map((d) => d.at.x)).toEqual([914, 1552, 828, 1322])
    for (const d of out) {
      expect(d.overWater).toBe(true)
      expect(d.afloat).toBe(true)
    }
  })

  it('drifts a craft away from the cove until it finds open water', () => {
    // A band of timber over the pier's own columns — which is where the fishing
    // boat's authored offset lands — and open water everywhere else.
    const out = dressLanding(landingCtx((at) => !(at.x > 1280 && at.x < 1380)))
    const fishing = out.find((d) => d.kind === 'boat_fishing')
    expect(fishing).toBeDefined()
    // EAST, away from the cove's centre: the reference's own "east of the pier
    // head", which drifting the other way would have contradicted.
    expect((fishing as DressItem).at.x).toBeGreaterThanOrEqual(1380)
    // and the craft that were already clear did not move
    expect(out.find((d) => d.kind === 'boat_rowing')?.at.x).toBe(914)
  })

  it('draws NOTHING rather than a beached craft when no drift finds water', () => {
    expect(dressLanding(landingCtx(() => false))).toEqual([])
    // and refuses to place at all with no way to ask — a craft emitted without
    // the check is the claim that was paid for once already
    expect(dressLanding(landingCtx(null))).toEqual([])
  })
})
