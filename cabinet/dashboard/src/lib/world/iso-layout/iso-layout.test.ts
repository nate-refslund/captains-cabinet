/**
 * ISO-LAYOUT tests — properties, not smoke.
 *
 * Every arm here asserts something that would be FALSE against a naive
 * implementation, and each one names the defect it exists to catch. A test
 * that only proves a function returned an object is a disabled sensor wearing
 * a green tick (the dominant defect class of 2026-07-25/26), so each arm below
 * either has a negative twin proving it can fail, or asserts a relation that a
 * flat tile lattice would violate.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  auditLayout,
  buildCoastline,
  buildLaneField,
  buildLanes,
  clipToLand,
  composeLayout,
  countOf,
  CIVIC_ANCHORS,
  DEFAULT_FOOTPRINTS,
  drivewayWidth,
  footprintOnLane,
  groundTaken,
  ISO_AXIS_SLOPE,
  isoRoute,
  LANE_SPECS,
  LANE_WIDTH_RUNGS,
  laneDemandFrom,
  laneWidthAt,
  LAYOUT_SPACE,
  LOT_LANES,
  LOT_SEPARATION,
  lotsAlong,
  lotFor,
  placeOnGround,
  poissonScatter,
  polyPoint,
  rasterDims,
  buildClearedGround,
  CANOPY_KINDS,
  CLEARING_EDGE_BAND,
  FURNITURE_MAX_TIMBER,
  RECORD_FRAMES,
  RING_BUILT_OVERLAP,
  type Lane,
  type Layout,
  type LayoutState,
  type Point,
} from './index'
import {
  clearOfLane,
  clipBlobToLand,
  grownField,
  maxGroundOverlap,
  paintField,
  snapInland,
  walkInland,
  waterField,
} from './index'
import { groundBox, groundDiamond, groundOverlap } from '../projection'
import { seededRng } from '../hash'

// A coarse coastline for arms that do not need shoreline fidelity: the field
// is the expensive stage and most properties here are about lanes, lots and
// clearance, which do not care how finely the shore was sampled.
const FAST = { coastline: { step: 8 } }

const HAMLET: LayoutState = {
  era: 'hamlet',
  road: 'dirt_worn',
  stages: {
    great_house: 'cottage',
    well: 'stone_well',
    library: 'shelf',
    workshop: 'forge',
    outbuildings: 'shed',
    market_stall: 'stall',
  },
  counts: { officer_dwellings: 3, field_plots: 2 },
}

const CAMP: LayoutState = {
  era: 'camp',
  road: 'dirt_path',
  stages: { great_house: 'camp_log_cabin', library: 'none', workshop: 'none' },
  counts: { officer_dwellings: 1 },
}

/**
 * THE FULL ISLAND — every ladder several rungs up, which is the era where the
 * clearings are widest and the most things have been placed. Two of the arms
 * below only bite here: the belt-against-a-building rule (more buildings to
 * crowd) and the shallow-waterline warehouse (the beyond_bay quay is the only
 * place a `put` reaches the shore).
 */
const BEYOND_BAY: LayoutState = {
  era: 'beyond_bay',
  road: 'cobbled_road',
  stages: {
    great_house: 'great_hall',
    well: 'stone_well',
    library: 'stone_hall',
    workshop: 'forge',
    outbuildings: 'barn',
    firepit: 'firepit',
    lighthouse: 'lit_tower',
  },
  counts: {
    officer_dwellings: 6,
    field_plots: 4,
    great_house: 4,
    library: 4,
    workshop: 4,
    outbuildings: 3,
    well: 3,
    lighthouse: 3,
  },
}

const hamlet = composeLayout(HAMLET, 'acme-corp', FAST)
const camp = composeLayout(CAMP, 'acme-corp', FAST)

/** Seeds used wherever a property must hold for more than one island. */
const SEEDS = ['acme-corp', 'harbour', 'lantern', 'captains-cabinet', 'zeta']

/**
 * A WIDE seed set, for the properties five named islands cannot decide.
 *
 * Every defect this file has ever been re-opened for was found by a sweep and
 * missed by SEEDS: the lot snap broke the 168px separation on 40 of 80 seeds
 * and stacked two dwellings on org-13 while all five named seeds stayed clean,
 * and nine scatter items stood in a crop plot on seeds nobody had composed.
 * Five islands decide a property that is about the RULES; a property that is
 * about the seed SPACE needs the space. These are cheap at step 8.
 */
const WIDE_SEEDS = Array.from({ length: 80 }, (_, i) => `org-${i}`)

/** The state the sweeps run at: a full village, so every rule is in play. */
const VILLAGE: LayoutState = {
  era: 'hamlet',
  road: 'gravel_road',
  stages: {
    great_house: 'timber_hall',
    library: 'stone_hall',
    workshop: 'forge',
    outbuildings: 'barn',
    well: 'stone_well',
    market_stall: 'stall',
    firepit: 'firepit',
  },
  counts: { officer_dwellings: 6, field_plots: 4 },
}

/** Closest pair of lot centres, in the rule's own y/0.8 metric. */
function closestLotPair(l: Layout): number {
  const cs = Object.values(l.lots).flat().map((lot) => lot.c)
  let mn = Infinity
  for (let a = 0; a < cs.length; a++) {
    for (let b = a + 1; b < cs.length; b++) {
      mn = Math.min(mn, Math.hypot(cs[a].x - cs[b].x, (cs[a].y - cs[b].y) / 0.8))
    }
  }
  return mn
}

/**
 * The structure ROLES a state justifies, derived from the state and not from
 * the layout — the shape of checks/world_checks.py check_state_traceable, which
 * asks whether every drawn thing traces back to a rule over `state`.
 *
 * It is written out longhand rather than imported so the arms that use it are
 * measuring the RULE's claim rather than re-running the rule's code. It covers
 * the village set only; a state with berths, cargo or a harbourmaster also
 * builds quayside structures, and the arms below assert separately that this
 * state builds none.
 */
function justifiedRoles(state: LayoutState): string[] {
  const present = (obj: string) => {
    const rung = state.stages?.[obj]
    return rung !== null && rung !== undefined && rung !== 'none'
  }
  const out: string[] = []
  if (present('great_house')) out.push('great_house')
  if (present('well')) out.push('well')
  out.push('firepit') // ALWAYS_DRAWN: an unbuilt hearth is still a hearth
  for (let i = 0; i < countOf(state, 'officer_dwellings'); i++) out.push('officer_dwelling')
  for (const obj of ['library', 'workshop', 'outbuildings']) if (present(obj)) out.push(obj)
  out.push('lighthouse') // ALWAYS_DRAWN: an unlit cairn is the drawing
  return out
}

function sizeOfItem(kind: string) {
  return DEFAULT_FOOTPRINTS[kind] ?? { w: 96, h: 96 }
}

/** Every lane sample, runs flattened — the whole painted centreline. */
function laneSamples(l: Layout): { key: string; at: Point }[] {
  return l.lanes.flatMap((lane) =>
    lane.runs.flat().map((at) => ({ key: lane.key, at }))
  )
}

/**
 * The keep-out test in the reference's own metric (compose.py:1213), written
 * here rather than imported so the arms measure the RULE's claim and not the
 * rule's code.
 */
function insideDisc(l: Layout, p: Point): boolean {
  return l.districts.some((d) => (p.x - d.at.x) ** 2 + ((p.y - d.at.y) * 1.35) ** 2 < d.r * d.r)
}

function insidePaint(l: Layout, kinds: string[], p: Point): boolean {
  return l.paint.some(
    (r) =>
      kinds.includes(r.kind) &&
      r.blobs.some((b) => ((p.x - b.c.x) / b.rx) ** 2 + ((p.y - b.c.y) / b.ry) ** 2 <= 1)
  )
}

/**
 * A blob's extent, sampled DENSELY and independently of the implementation's
 * own sampling: 90 rim angles and a 7x7 interior grid, against the clip's 24
 * angles and one interior ring. A sensor that probes exactly the points the
 * control probes cannot detect anything between them.
 */
function blobExtentSamples(b: { c: Point; rx: number; ry: number }): Point[] {
  const out: Point[] = [b.c]
  for (let i = 0; i < 90; i++) {
    const a = (i * Math.PI * 2) / 90
    out.push({ x: b.c.x + Math.cos(a) * b.rx, y: b.c.y + Math.sin(a) * b.ry })
  }
  for (let ix = -3; ix <= 3; ix++) {
    for (let iy = -3; iy <= 3; iy++) {
      const fx = ix / 3
      const fy = iy / 3
      if (fx * fx + fy * fy > 1) continue
      out.push({ x: b.c.x + fx * b.rx, y: b.c.y + fy * b.ry })
    }
  }
  return out
}

/** The layout, minus the coastline raster, as a comparable value. */
function shape(l: Layout) {
  return JSON.stringify({
    lanes: l.lanes,
    lots: l.lots,
    driveways: l.driveways,
    paint: l.paint,
    structures: l.structures,
    scatter: l.scatter,
  })
}

// ── determinism ────────────────────────────────────────────────────────────

describe('determinism — the law that replaces layout_fold', () => {
  it('two runs with the same inputs are byte-identical', () => {
    const a = composeLayout(HAMLET, 'acme-corp', FAST)
    const b = composeLayout(HAMLET, 'acme-corp', FAST)
    expect(shape(b)).toBe(shape(a))
    expect(Array.from(b.coast.land)).toEqual(Array.from(a.coast.land))
  })

  it('a DIFFERENT seed gives a different island and a different planting', () => {
    // the negative twin: without this, "deterministic" would be satisfied by a
    // function that ignores its seed entirely
    const other = composeLayout(HAMLET, 'beta-works', FAST)
    expect(shape(other)).not.toBe(shape(hamlet))
    expect(Array.from(other.coast.land)).not.toEqual(Array.from(hamlet.coast.land))
  })

  it('the invariants hold at the PRODUCTION sampling step, not just the fast one', () => {
    // Every other arm runs the coastline coarse for speed. A test environment
    // that guarantees something production does not is the defect class this
    // arm exists to close: run the real default (compose.py's STEP = 2) once
    // and re-assert the load-bearing properties on it.
    const real = composeLayout(HAMLET, 'acme-corp')
    expect(real.coast.step).toBe(2)
    const audit = auditLayout(real)
    expect(audit.onLane).toEqual([])
    expect(audit.stacked).toEqual([])
    expect(audit.inWater).toEqual([])
    expect(real.structures.length).toBeGreaterThan(5)
    expect(real.scatter.length).toBeGreaterThan(30)
    expect(shape(composeLayout(HAMLET, 'acme-corp'))).toBe(shape(real))
  })

  it('the seed reaches the coastline, not just the scatter', () => {
    const a = buildCoastline('one', LAYOUT_SPACE, { step: 8 })
    const b = buildCoastline('two', LAYOUT_SPACE, { step: 8 })
    let diff = 0
    for (let i = 0; i < a.land.length; i++) if (a.land[i] !== b.land[i]) diff++
    expect(diff).toBeGreaterThan(100)
  })
})

// ── coastline ──────────────────────────────────────────────────────────────

describe('coastline — a real shore with a carved cove', () => {
  const c = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 4 })

  it('the island centre is land and the far corners are sea', () => {
    expect(c.landAt(LAYOUT_SPACE.cx, LAYOUT_SPACE.cy)).toBe(true)
    expect(c.landAt(20, 20)).toBe(false)
    expect(c.landAt(LAYOUT_SPACE.w - 20, LAYOUT_SPACE.h - 20)).toBe(false)
  })

  it('the shore is IRREGULAR — not the ellipse it is built from', () => {
    // a pure ellipse would give landEdge(ang) == the ellipse radius at ang for
    // every angle; the fbm term is what makes a coastline. Measure the spread
    // of edge/ellipse across the compass and require real variation.
    const ratios: number[] = []
    for (let i = 0; i < 48; i++) {
      const ang = (i * Math.PI * 2) / 48
      // the ellipse radius along ang, with the same 0.92 vertical walk
      const ex = Math.cos(ang) / 962
      const ey = (Math.sin(ang) * 0.92) / 784
      const rEllipse = 1 / Math.sqrt(ex * ex + ey * ey)
      ratios.push(c.landEdge(ang) / rEllipse)
    }
    const min = Math.min(...ratios)
    const max = Math.max(...ratios)
    expect(max - min).toBeGreaterThan(0.08)
  })

  it('the cove is CARVED — the south shore bites in where nothing else does', () => {
    // straight down from the island centre runs into the cove; the two
    // shoulders either side of it do not.
    const south = c.landEdge(Math.PI / 2)
    const swShoulder = c.landEdge(Math.PI / 2 - 0.9)
    const seShoulder = c.landEdge(Math.PI / 2 + 0.9)
    expect(south).toBeLessThan(swShoulder)
    expect(south).toBeLessThan(seShoulder)
  })

  it('with the cove removed the same seed has NO bite — the carve is the cause', () => {
    const nocove = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 4, cove: null })
    expect(nocove.landEdge(Math.PI / 2)).toBeGreaterThan(c.landEdge(Math.PI / 2))
  })

  it('the beach band sits OUTSIDE the land, never on it', () => {
    let overlap = 0
    let beachCells = 0
    for (let i = 0; i < c.land.length; i++) {
      if (c.beach[i]) beachCells++
      if (c.beach[i] && c.land[i]) overlap++
    }
    expect(beachCells).toBeGreaterThan(0)
    // the two masks come from disjoint bands of the same field; blurring can
    // fray the boundary, but they must not be the same region
    expect(overlap / beachCells).toBeLessThan(0.35)
  })

  it('rasterDims refuses an allocation it cannot afford', () => {
    expect(() => rasterDims({ w: 1e6, h: 1e6, cx: 0, cy: 0 }, 1)).toThrow(/MAX_RASTER_CELLS/)
    expect(() => rasterDims({ w: 0, h: 10, cx: 0, cy: 0 }, 1)).toThrow(/invalid layout space/)
  })
})

// ── lanes ──────────────────────────────────────────────────────────────────

/**
 * "The island is everywhere" — for arms about widths, keys and era gating,
 * which are not about the coastline. Named rather than inlined so a reader can
 * see at a glance which arms are running WITHOUT a real shore, and the arms
 * that are about the shore all use a real coastline.
 */
const LAND = () => true

/** The state, as ./lanes asks it — the composer's own reading, never a copy. */
const demand = (state: LayoutState) => laneDemandFrom(state)

/** Every ladder any lane hangs off, at a rung, so the whole network is earned. */
const FULL_NETWORK: LayoutState = {
  era: 'hamlet',
  road: 'gravel_road',
  stages: {
    great_house: 'great_house',
    law_plot: 'wood_fence',
    library: 'library_hall',
    workshop: 'shed',
    outbuildings: 'small_barn',
    quay: 'timber_jetty',
  },
  counts: { officer_dwellings: 3 },
}

describe('lanes — a path is worn by traffic, not switched on by an era', () => {
  it('a hatched island has the track to the water, and it runs to the water', () => {
    // The landing is the ONE place open on day zero, so its road is too.
    const campCarriageways = camp.lanes.filter((l) => l.kind !== 'driveway')
    expect(campCarriageways.map((l) => l.key)).toContain('main')
    const main = campCarriageways.find((l) => l.key === 'main')!
    const runs = main.runs
    const last = runs[runs.length - 1]
    const end = last[last.length - 1]
    // It REACHES the water rather than crossing it: the control points run to
    // y=1360, which is inside the cove on every island, so the land clip is
    // what decides where the track actually stops. Assert the shore, not the
    // authored endpoint — that is the property "runs to the water" means once
    // the coastline is a function of the seed.
    expect(camp.coast.landAt(end.x, end.y)).toBe(true)
    expect(camp.coast.landAt(end.x, end.y + 40)).toBe(false)
    expect(end.y).toBeGreaterThan(1100)
  })

  it('a lane exists ONLY when the place at its far end does', () => {
    // THE DEFECT: `villageOnly` made all nine carriageways appear the instant
    // the era index crossed a threshold — the largest pop-in on the frame, and
    // against the world's own "no structure ever pops in" law. Each pair below
    // differs by ONE ladder, so the arm names which lane that ladder wears.
    const bare: LayoutState = { era: 'hamlet', road: 'gravel_road', stages: {}, counts: {} }
    const keys = (s: LayoutState) =>
      buildLanes(s.road, LAND, demand(s)).map((l) => l.key)
    const base = keys(bare)
    for (const [object, rung, lane] of [
      ['library', 'library_hall', 'ne'],
      ['workshop', 'shed', 'east'],
      ['outbuildings', 'small_barn', 'se'],
      ['quay', 'timber_jetty', null], // widens `main`, never creates it
    ] as const) {
      expect(base, `${lane ?? object} must not exist unmeasured`).not.toContain(lane)
      const grown = keys({ ...bare, stages: { [object]: rung } })
      if (lane !== null) expect(grown).toContain(lane)
    }
    // and a count ladder does it too: one officer wears the residential street
    expect(base).not.toContain('west')
    expect(keys({ ...bare, counts: { officer_dwellings: 1 } })).toContain('west')
  })

  it('the ERA STEP no longer hands the island a road network', () => {
    // THE DEFECT, stated as the size of the jump: camp -> hamlet with nothing
    // built used to go from 1 carriageway to 10 in one keyframe. What may still
    // arrive with the village is the furniture-only districts, whose paths come
    // with the furniture that makes them places.
    const nothing = { stages: {}, counts: {} }
    const camped = buildLanes('dirt_path', LAND,
      demand({ era: 'camp', road: 'dirt_path', ...nothing })).map((l) => l.key)
    const villaged = buildLanes('gravel_road', LAND,
      demand({ era: 'hamlet', road: 'gravel_road', ...nothing })).map((l) => l.key)
    expect(camped).toEqual(['main'])
    expect(villaged.filter((k) => !camped.includes(k)).sort()).toEqual(['nw', 'sw'])
  })

  it('the network GROWS edge by edge rather than stepping', () => {
    // The Captain's picture: the island is cleared, so the roads arrive one at
    // a time with the buildings. Adding one ladder at a time must add at most
    // one carriageway at a time and never remove one. `coastal` is allowed to
    // ride along with `west`, because a link is not a destination — it is the
    // second end of one that just arrived.
    const ladders: [string, string, string][] = [
      // ladder, a real rung of it, the lane that place wears
      ['quay', 'timber_jetty', 'main'],       // already there — the landing is day zero
      ['great_house', 'cottage', 'forecourt'],
      ['library', 'library_hall', 'ne'],
      ['workshop', 'shed', 'east'],
      ['outbuildings', 'small_barn', 'se'],
      ['law_plot', 'wood_fence', 'north'],
      ['officer_dwellings', 'dwelling_1', 'west'],
    ]
    const stages: Record<string, string> = {}
    const counts: Record<string, number> = {}
    const at = () =>
      buildLanes('gravel_road', LAND, demand({
        era: 'hamlet', road: 'gravel_road', stages, counts,
      })).map((l) => l.key)
    let prev = at()
    for (const [obj, rung, lane] of ladders) {
      stages[obj] = rung
      if (obj === 'officer_dwellings') counts[obj] = 1
      const now = at()
      for (const k of prev) expect(now, `${obj} removed ${k}`).toContain(k)
      // NO BURST: one ladder buys at most one new carriageway, and `coastal` is
      // exempt because a link is not a destination — it is the far end of one
      // that has just arrived.
      const added = now.filter((k) => !prev.includes(k) && k !== 'coastal')
      expect(added.length, `${obj} added ${added.join()}`).toBeLessThanOrEqual(1)
      // AND THE PLACE IS REACHABLE: building it must not leave it roadless.
      expect(now, `${obj} built with no ${lane}`).toContain(lane)
      prev = now
    }
  })

  it('WIDTH follows the destination, and only the destination', () => {
    // The two axes must be independent: the library's own rung widens the
    // library's lane and moves nothing else. Under the old rule the org-wide
    // road rung moved every width at once.
    const at = (libraryRung: number) => {
      const lanes = buildLanes('gravel_road', LAND, {
        present: (o) => o === 'library' || o === 'workshop',
        usage: (o) => (o === 'library' ? libraryRung : 1),
        village: true,
      })
      return Object.fromEntries(lanes.map((l) => [l.key, l.width]))
    }
    const quiet = at(0)
    const busy = at(5)
    expect(busy.ne).toBeGreaterThan(quiet.ne)
    expect(busy.east).toBe(quiet.east)
    expect(quiet.ne).toBe(LANE_WIDTH_RUNGS[0])
    expect(busy.ne).toBe(LANE_WIDTH_RUNGS[5])
  })

  it('a lane is BORN at the hairline, whatever the org road rung is', () => {
    // "only a tiny/narrow path to begin with" (Captain 2026-07-27). A cobbled
    // org does not hand a brand-new library a carriageway.
    for (const road of ['dirt_path', 'cobbled_road'] as const) {
      const lane = buildLanes(road, LAND, {
        present: (o) => o === 'library',
        usage: () => 0,
        village: false,
      }).find((l) => l.key === 'ne')!
      expect(lane).toBeDefined()
      expect(lane.width).toBe(LANE_WIDTH_RUNGS[0])
    }
  })

  it('the ROAD RUNG sets the surface and nothing else', () => {
    const same = demand(FULL_NETWORK)
    const dirt = buildLanes('dirt_path', LAND, same)
    const cobble = buildLanes('cobbled_road', LAND, same)
    expect(dirt.map((l) => l.key)).toEqual(cobble.map((l) => l.key))
    expect(dirt.map((l) => l.width)).toEqual(cobble.map((l) => l.width))
    expect(dirt.map((l) => l.runs)).toEqual(cobble.map((l) => l.runs))
    expect(new Set(dirt.map((l) => l.surface))).toEqual(new Set(['dirt_path']))
    expect(new Set(cobble.map((l) => l.surface))).toEqual(new Set(['cobbled_road']))
  })

  it('the width ladder is monotone and starts at the paint floor', () => {
    for (let i = 1; i < LANE_WIDTH_RUNGS.length; i++) {
      expect(LANE_WIDTH_RUNGS[i]).toBeGreaterThan(LANE_WIDTH_RUNGS[i - 1])
    }
    // A width below the ground painter's floor is a lane that is declared and
    // never drawn — a claim with no paint behind it.
    expect(LANE_WIDTH_RUNGS[0]).toBe(13)
    // out of range in BOTH directions lands on a real rung, never on undefined
    expect(laneWidthAt(-3)).toBe(LANE_WIDTH_RUNGS[0])
    expect(laneWidthAt(99)).toBe(LANE_WIDTH_RUNGS[LANE_WIDTH_RUNGS.length - 1])
    expect(laneWidthAt(Number.NaN)).toBe(LANE_WIDTH_RUNGS[0])
  })

  it('a district nothing measures keeps a hairline forever', () => {
    // The dojo and the crossroads have NO ladder in growth-ladders.yml, so no
    // amount of org growth may widen them. An invented metric would be three
    // false claims; the honest answer is the bottom rung, at every rung of
    // everything else.
    for (const usage of [0, 3, 7]) {
      const lanes = buildLanes('cobbled_road', LAND, {
        present: () => true,
        usage: () => usage,
        village: true,
      })
      for (const key of ['nw', 'sw', 'coastal']) {
        const lane = lanes.find((l) => l.key === key)!
        expect(lane.width, `${key} widened on a metric it does not have`).toBe(
          LANE_WIDTH_RUNGS[0]
        )
      }
    }
  })

  it('an unmeasured district has no lane at all until the village does', () => {
    const camped = buildLanes('dirt_path', LAND, {
      present: () => false,
      usage: () => 0,
      village: false,
    })
    expect(camped.map((l) => l.key)).toEqual(['main'])
  })

  it('a LINK lane needs both of the lanes it joins', () => {
    // The shore path is a link, not a destination: nobody's errand ends
    // halfway along it, so it exists only when both its ends are streets.
    const withWest = buildLanes('gravel_road', LAND, {
      present: (o) => o === 'officer_dwellings',
      usage: () => 1,
      village: true,
    }).map((l) => l.key)
    expect(withWest).toContain('west')
    expect(withWest).toContain('sw') // village-entitled
    expect(withWest).toContain('coastal')
    const noWest = buildLanes('gravel_road', LAND, {
      present: () => false,
      usage: () => 0,
      village: true,
    }).map((l) => l.key)
    expect(noWest).toContain('sw')
    expect(noWest).not.toContain('west')
    expect(noWest, 'a link with one end missing is not a path').not.toContain('coastal')
  })

  it('the lane a spur hangs off must exist too', () => {
    // `north` leaves the great house's forecourt. Without a great house it
    // would be a carriageway floating in grass with a junction at neither end.
    const orphan = buildLanes('gravel_road', LAND, {
      present: (o) => o === 'law_plot',
      usage: () => 4,
      village: true,
    }).map((l) => l.key)
    expect(orphan).not.toContain('north')
    const joined = buildLanes('gravel_road', LAND, {
      present: (o) => o === 'law_plot' || o === 'great_house',
      usage: () => 4,
      village: true,
    }).map((l) => l.key)
    expect(joined).toContain('north')
  })

  it('a drive is one household of its road, and never wider than it', () => {
    for (const usage of [0, 2, 5, 7]) {
      const carriageway = laneWidthAt(usage)
      expect(drivewayWidth(usage, carriageway)).toBeLessThanOrEqual(carriageway)
      expect(drivewayWidth(usage, carriageway)).toBeGreaterThanOrEqual(LANE_WIDTH_RUNGS[0])
    }
    expect(drivewayWidth(6, 999)).toBeGreaterThan(drivewayWidth(1, 999))
  })

  it('every traffic ladder a spec names is a real ladder in growth-ladders.yml', () => {
    // A lane widening on a name nothing measures would be a switch wired to the
    // empty set — the market-stall defect, one layer up. Read the law, do not
    // restate it.
    const yml = readFileSync(
      join(process.cwd(), '..', 'world', 'growth-ladders.yml'), 'utf8')
    for (const spec of LANE_SPECS) {
      if (spec.to.at !== 'built' && spec.to.at !== 'landing') continue
      expect(yml, `${spec.key}: no ladder ${spec.to.traffic}`)
        .toContain(`\n  ${spec.to.traffic}:\n`)
    }
    for (const spec of LANE_SPECS) {
      if (spec.to.at !== 'built') continue
      for (const o of spec.to.objects) {
        expect(yml, `${spec.key}: no ladder ${o}`).toContain(`\n  ${o}:\n`)
      }
    }
  })

  it('the narrowest lane does not NECK between its samples', () => {
    // THE SQUASH BITES ON THE STEP, not just on the disc, and the first version
    // of this arm asserted the wrong thing: it looked for a HOLE, there has
    // never been one (the discs overlap at every step the code can produce), and
    // it came back GREEN against the pre-fix spacing. What the coarse step
    // really costs is WIDTH — a disc reaches `half` across but `half*0.72` down,
    // so stepping a vertical run by `half` pinches the union to 0.72 of its
    // width halfway between centres. On the 13px path this ladder starts every
    // lane at that is 1.8px of necking, drawn as a chain of beads.
    //
    // A PIXEL is the bar, and it is a real one rather than a tuned one: at the
    // narrowest rung the ladder has, the painted band may not lose a whole pixel
    // of half-width between samples. The old step fails it (1.8px), the
    // squashed step passes (0.87px).
    const vertical: Lane = {
      key: 'v',
      kind: 'main',
      width: LANE_WIDTH_RUNGS[0],
      surface: 'dirt_path',
      runs: [[{ x: 1000, y: 900 }, { x: 1000, y: 1100 }]],
    }
    const field = buildLaneField([vertical])
    const half = LANE_WIDTH_RUNGS[0] / 2
    /**
     * The band's half-width in x at this y, BISECTED rather than walked: a
     * fixed-step walk quantises the answer by its own step, and the whole
     * quantity here is under two pixels.
     */
    const reachAt = (y: number) => {
      let lo = 0
      let hi = half + 2
      for (let i = 0; i < 40; i++) {
        const mid = (lo + hi) / 2
        if (field.onLane(1000 + mid, y)) lo = mid
        else hi = mid
      }
      return lo
    }
    let worst = half
    for (let y = 950; y <= 1050; y += 0.25) worst = Math.min(worst, reachAt(y))
    expect(half - worst, `the band necks by ${(half - worst).toFixed(2)}px`)
      .toBeLessThan(1)
  })

  it('the lane field answers on/off the carriageway', () => {
    const field = buildLaneField(buildLanes('cobbled_road', LAND, demand(FULL_NETWORK)))
    // the village square is the head of the main street
    expect(field.onLane(1200, 1010)).toBe(true)
    // open meadow far from any lane
    expect(field.onLane(400, 400)).toBe(false)
    expect(field.nearLane(400, 400)).toBe(false)
  })
})

// ── lots ───────────────────────────────────────────────────────────────────

describe('lots — computed from the lanes, separated at birth', () => {
  const onLand = () => true

  it('no two lots are born on the same spot', () => {
    const lots = lotsAlong(LOT_LANES.west, 6, onLand, [], { side: -1, setback: 118 })
    for (let i = 0; i < lots.length; i++) {
      for (let j = i + 1; j < lots.length; j++) {
        // the separation rule itself, in its own metric
        const d = Math.hypot(lots[i].c.x - lots[j].c.x, (lots[i].c.y - lots[j].c.y) / 0.8)
        expect(d).toBeGreaterThanOrEqual(LOT_SEPARATION - 1e-6)
        // and the property that actually matters: a cottage on each of them
        // does not share ground with a cottage on the other
        expect(
          groundTaken(lots[i].c, { w: 150, h: 150 }, [{ at: lots[j].c, size: { w: 150, h: 150 } }])
        ).toBe(false)
      }
    }
  })

  it('the separation push RUNS — without it the same lane crowds', () => {
    // a lane walked with no separation at all: emit the raw arc-length points
    // and show they land closer than the rule allows. This is the negative
    // twin proving the assertion above is not vacuous.
    const raw: Point[] = []
    for (let i = 0; i < 6; i++) {
      const t = 0.1 + 0.8 * ((i + 0.5) / 6)
      raw.push(polyPoint(LOT_LANES.west, t).at)
    }
    let closest = Infinity
    for (let i = 1; i < raw.length; i++) {
      closest = Math.min(closest, Math.hypot(raw[i].x - raw[i - 1].x, (raw[i].y - raw[i - 1].y) / 0.8))
    }
    expect(closest).toBeLessThan(100)
  })

  it('lots repel the CIVIC anchors too, not just each other', () => {
    // civic anchors are on the main street, so walk lots down it with no
    // setback at all and check the book still pushes them clear
    const lots = lotsAlong(LOT_LANES.main, 3, onLand, CIVIC_ANCHORS, { side: 1, setback: 20 })
    for (const lot of lots) {
      for (const civic of CIVIC_ANCHORS) {
        const d = Math.hypot(lot.c.x - civic.x, (lot.c.y - civic.y) / 0.8)
        expect(d).toBeGreaterThan(100)
      }
    }
  })

  it('a lot fronts its lane: face points from the road to the plot', () => {
    const lots = lotsAlong(LOT_LANES.west, 3, onLand, [], { side: -1, setback: 118 })
    for (const lot of lots) {
      const dx = lot.c.x - lot.road.x
      const dy = lot.c.y - lot.road.y
      // the facing agrees with the road->plot direction (positive projection)
      expect(lot.face.x * dx + lot.face.y * dy).toBeGreaterThan(0)
    }
  })

  it('lotFor keeps the doctrine anchor and only takes frontage from the lane', () => {
    const anchor = { x: 1640, y: 512 }
    const lot = lotFor(anchor, LOT_LANES.ne)
    expect(lot.c).toEqual(anchor)
    // the road point is genuinely ON the polyline it was sampled from
    const nearest = Math.min(
      ...Array.from({ length: 401 }, (_, i) => {
        const p = polyPoint(LOT_LANES.ne, i / 400).at
        return Math.hypot(p.x - lot.road.x, p.y - lot.road.y)
      })
    )
    expect(nearest).toBeLessThan(1)
  })

  it('no two STRUCTURES share ground in the composed layout', () => {
    const audit = auditLayout(hamlet)
    expect(audit.stacked).toEqual([])
  })

  it('the stacking audit can actually FAIL — two things on one spot', () => {
    const a = groundBox(1000, 1000, 150, 150)
    const b = groundBox(1004, 1002, 150, 150)
    expect(groundOverlap(a, b)).toBeGreaterThan(0.16)
    expect(groundTaken({ x: 1000, y: 1000 }, { w: 150, h: 150 }, [
      { at: { x: 1004, y: 1002 }, size: { w: 150, h: 150 } },
    ])).toBe(true)
  })
})

// ── driveways ──────────────────────────────────────────────────────────────

describe('driveways — an L on the two isometric ground axes', () => {
  const cases: [Point, Point][] = [
    [{ x: 100, y: 100 }, { x: 400, y: 260 }],
    [{ x: 900, y: 900 }, { x: 700, y: 1000 }],
    [{ x: 1200, y: 800 }, { x: 1200, y: 1010 }],
    [{ x: 500, y: 500 }, { x: 900, y: 300 }],
  ]

  it('every leg runs on an iso ground axis', () => {
    for (const [a, b] of cases) {
      const [p0, p1, p2] = isoRoute(a, b)
      for (const [u, v] of [[p0, p1], [p1, p2]] as const) {
        const dx = v.x - u.x
        const dy = v.y - u.y
        if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) continue // zero-length leg
        expect(Math.abs(Math.abs(dy / dx) - ISO_AXIS_SLOPE)).toBeLessThan(1e-9)
      }
    }
  })

  it('the two legs use OPPOSITE axes — it is an L, not a straight line', () => {
    for (const [a, b] of cases) {
      const [p0, p1, p2] = isoRoute(a, b)
      const s1 = (p1.y - p0.y) / (p1.x - p0.x)
      const s2 = (p2.y - p1.y) / (p2.x - p1.x)
      if (!Number.isFinite(s1) || !Number.isFinite(s2)) continue
      expect(Math.sign(s1)).not.toBe(Math.sign(s2))
    }
  })

  it('the route starts at the door and ends on the road', () => {
    for (const [a, b] of cases) {
      const r = isoRoute(a, b)
      expect(r[0]).toEqual(a)
      expect(r[2]).toEqual(b)
    }
  })

  it('a straight screen-space line would FAIL the axis test', () => {
    // the naive implementation this rule exists to forbid
    const naive = [{ x: 100, y: 100 }, { x: 400, y: 260 }]
    const dx = naive[1].x - naive[0].x
    const dy = naive[1].y - naive[0].y
    expect(Math.abs(Math.abs(dy / dx) - ISO_AXIS_SLOPE)).toBeGreaterThan(1e-3)
  })

  it('only BUILT lots get a drive — a path to empty grass is a lie', () => {
    const none = composeLayout(
      { era: 'hamlet', road: 'dirt_worn', stages: { great_house: 'cottage' }, counts: {} },
      'acme-corp',
      FAST
    )
    expect(none.driveways).toHaveLength(0)
    expect(hamlet.driveways).toHaveLength(
      countOf(HAMLET, 'officer_dwellings') + 3 // library, workshop, outbuildings
    )
  })

  it('drives join the SAME occupancy surface as the carriageways', () => {
    const drives = hamlet.lanes.filter((l) => l.kind === 'driveway')
    expect(drives.length).toBeGreaterThan(0)
    const field = buildLaneField(hamlet.lanes)
    for (const d of drives) {
      const run = d.runs[0]
      const mid = run[Math.floor(run.length / 2)]
      expect(field.onLane(mid.x, mid.y)).toBe(true)
    }
  })

  it('a camp officer gets a street AND a drive — the road follows the tent', () => {
    // THE MODEL CHANGED HERE, 2026-07-27, and this arm is the change. It used to
    // read "a camp gets NO drive", which was true only because the residential
    // street was gated on the ERA: one officer had a tent and no way to it. A
    // path is worn by whoever walks it, so the officer's arrival wears both the
    // street and the drive, at the narrowest rung the ladder has.
    expect(camp.driveways).toHaveLength(1)
    const drives = camp.lanes.filter((l) => l.kind === 'driveway')
    expect(drives).toHaveLength(1)
    const west = camp.lanes.find((l) => l.key === 'west')!
    expect(west, 'the drive joins a street that has to exist').toBeDefined()
    expect(drives[0].width).toBeLessThanOrEqual(west.width)
  })

  it('...and an EMPTY camp gets neither — nobody has walked anywhere yet', () => {
    // The negative twin, and the one the old era gate was really protecting:
    // a drive to a lot nobody has built on is a path to empty grass.
    const empty = composeLayout(
      { era: 'camp', road: 'dirt_path', stages: {}, counts: {} },
      'acme-corp',
      FAST
    )
    expect(empty.driveways).toHaveLength(0)
    expect(empty.lanes.map((l) => l.key)).toEqual(['main'])
  })

  it('a drive exists only where the lane its lot fronts is part of this era', () => {
    // What the gate actually promises, stated exactly. It is an ERA test, not a
    // geometric one: at hamlet the district lanes exist and every built lot gets
    // its drive; at camp they do not and none does.
    //
    // NOT PROMISED, and left open deliberately: that a drive's far end lands on
    // painted cobble. The officer row fronts LOT_LANES.west — the idealised
    // frontage line the reference walks lots along (compose.py:245) — which is
    // NOT the same polyline as the painted `west` carriageway
    // (compose.py:227). The reference has that gap too and paints those drives
    // anyway; closing it moves the whole officer row, which is a direction
    // call, not a fix. Asserting it here would be asserting a property the
    // design does not have.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const keys = new Set(l.lanes.filter((x) => x.kind !== 'driveway').map((x) => x.key))
      expect(keys.has('west')).toBe(true)
      expect(l.driveways.length).toBe(countOf(HAMLET, 'officer_dwellings') + 3)
      // Every drive joins a carriageway that is REALLY IN THE NETWORK. The gate
      // used to be the era; now it is the far end of the drive's own lane, and
      // the case it still catches is a seed whose coastline clips that lane
      // away entirely — a drive to a road the sea took.
      for (const d of l.lanes.filter((x) => x.kind === 'driveway')) {
        const group = d.key.replace(/^drive-/, '').replace(/-\d+$/, '')
        const lane = { residential: 'west', memory: 'ne', works: 'east', fields: 'se' }[group]
        expect(keys.has(lane!), `${seed}: ${d.key} joins a missing ${lane}`).toBe(true)
      }
    }
  })

  it('a drive is dropped when the sea took the road it joins', () => {
    // The gate, exercised: an island whose only land is the east district keeps
    // the works spur and loses the residential street, so the officer row's
    // drives cannot be drawn even though the dwellings are measured.
    const eastOnly = (x: number, _y: number) => x > 1300
    const lanes = buildLanes('gravel_road', eastOnly, demand(FULL_NETWORK)).map((l) => l.key)
    expect(lanes).toContain('east')
    expect(lanes).not.toContain('west')
  })
})

// ── clearance ──────────────────────────────────────────────────────────────

describe('clearance — the ground diamond, and the road wins', () => {
  it('the footprint is a DIAMOND, never a rectangle', () => {
    const g = groundDiamond(150, 150)
    expect(g.hw).toBeCloseTo(150 * 0.42, 9)
    expect(g.depth).toBeCloseTo(Math.min(150 * 0.55, 150 * 0.55), 9)
    // a rectangle would be as deep as it is wide; the diamond is not
    expect(g.depth).not.toBeCloseTo(g.hw * 2, 3)
  })

  it('a lane crossing ABOVE the base line still counts as on the lane', () => {
    // the defect this exists to catch: sampling only the base row passed a
    // market stall standing squarely on a road the audit called clear
    const lanes = buildLaneField([
      { key: 't', kind: 'main', width: 40, surface: 'gravel_road', runs: [[{ x: 1000, y: 900 }, { x: 1200, y: 900 }]] },
    ])
    const size = { w: 150, h: 150 }
    // base BELOW the lane, but the diamond (depth ~82) reaches up onto it
    expect(lanes.onLane(1100, 960)).toBe(false)
    expect(footprintOnLane({ x: 1100, y: 960 }, size, lanes)).toBe(true)
    // far enough below and the diamond clears it
    expect(footprintOnLane({ x: 1100, y: 1100 }, size, lanes)).toBe(false)
  })

  it('nothing in the composed layout stands on a lane', () => {
    const audit = auditLayout(hamlet)
    expect(audit.onLane).toEqual([])
    expect(auditLayout(camp).onLane).toEqual([])
  })

  it('the ON-LANE audit can actually fail — an unmoved prop trips it', () => {
    // negative twin: place something on the main street with the rule OFF and
    // show the audit catches it, so the green above is a measurement
    const field = buildLaneField(hamlet.lanes)
    const onStreet = { ...hamlet.lanes[0].runs[0][2] }
    expect(footprintOnLane(onStreet, { w: 150, h: 150 }, field)).toBe(true)
  })

  it('clearing the road never lands a thing on another thing', () => {
    const field = buildLaneField(hamlet.lanes)
    const onStreet = { ...hamlet.lanes[0].runs[0][2] }
    const neighbour = { at: { x: onStreet.x + 90, y: onStreet.y + 20 }, size: { w: 150, h: 150 } }
    const p = placeOnGround(onStreet, { w: 150, h: 150 }, field, () => true, [neighbour], {
      strict: true,
    })
    expect(p).not.toBeNull()
    expect(footprintOnLane(p!, { w: 150, h: 150 }, field)).toBe(false)
    expect(groundTaken(p!, { w: 150, h: 150 }, [neighbour], 0.16)).toBe(false)
  })

  it('decoration that cannot settle is DROPPED, not stacked', () => {
    const field = buildLaneField([])
    // Fully occupied ground, wider than the whole push budget (30 tries x 19px
    // = 570px), so there is genuinely nowhere clear to be pushed to. A ring is
    // not enough — the settle walks straight out of a ring, which is what it
    // is supposed to do.
    const wall = []
    for (let x = 200; x <= 2200; x += 80) {
      for (let y = 200; y <= 1700; y += 60) {
        wall.push({ at: { x, y }, size: { w: 200, h: 200 } })
      }
    }
    const dropped = placeOnGround({ x: 1000, y: 1000 }, { w: 150, h: 150 }, field, () => true, wall, {
      dropIfBlocked: true,
    })
    expect(dropped).toBeNull()
    // the same input WITHOUT the drop flag returns a position — proving the
    // null above comes from the flag and not from an unrelated failure
    const kept = placeOnGround({ x: 1000, y: 1000 }, { w: 150, h: 150 }, field, () => true, wall, {})
    expect(kept).not.toBeNull()
  })
})

// ── scatter ────────────────────────────────────────────────────────────────

describe('scatter — a density field, and rejection at sampling time', () => {
  const coast = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 8 })
  const field = buildLaneField(buildLanes('gravel_road', (x, y) => coast.landAt(x, y), demand(FULL_NETWORK)))
  /**
   * THE FIELD THIS BLOCK USED TO DRIVE WAS `wildnessField`, AND IT IS GONE.
   *
   * It read `coast*1.15 - civic*0.72 - lane*0.45 + 0.10`: highest at the
   * waterline, lowest in the middle — a coastal ring of trees around a sparse
   * interior, i.e. wilderness as decoration placed around the buildings. The
   * Captain's 2026-07-27 direction inverts that (iso-layout/clearing.ts):
   * timber is the island's default state, clearing is subtractive, and the
   * density field describes how much timber is LEFT. The two arms below are
   * the same two properties re-asked of the field that replaced it, and their
   * expected answers are OPPOSITE at the coast, which is the point.
   */
  const cleared = buildClearedGround(
    [
      { at: { x: 1200, y: 1010 }, r: 300, rawness: 1, role: 'square', cut: 'felled' },
      { at: { x: 1200, y: 800 }, r: 250, rawness: 0.5, role: 'great_house', cut: 'felled' },
    ],
    {
      lanes: field,
      onPaving: () => false,
      inWater: () => false,
      onQuay: () => false,
    }
  )
  const timber = cleared.timber

  it('the density FIELD is FULL at the treeline AND in the untouched middle', () => {
    // The inverted claim. Under the old field the coast was wild and the middle
    // was tame; under this one both are wood, because nobody has cut either.
    const edge = coast.landEdge(-Math.PI / 2)
    const treeline = { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy - (edge - 60) * 0.92 }
    // 700px west of the island centre: outside both clearings, off every lane.
    const untouched = { x: LAYOUT_SPACE.cx - 700, y: LAYOUT_SPACE.cy }
    expect(timber(treeline.x, treeline.y)).toBe(1)
    expect(timber(untouched.x, untouched.y)).toBe(1)
  })

  it('the density field is ZERO on a lane and in a clearing', () => {
    expect(timber(1200, 1010)).toBe(0)
    const onMain = buildLanes('gravel_road', (x, y) => coast.landAt(x, y), demand(FULL_NETWORK))[0].runs[0][2]
    expect(timber(onMain.x, onMain.y)).toBe(0)
  })

  it('and it THINS across the edge band rather than stopping dead', () => {
    // The treeline is the ramp, and a hard-edged clearing would read as a
    // cookie cutter. Sampled straight west from the great house's clearing at
    // (1200,800), r=250: cut ground is bare right up to the rim, and the
    // CLEARING_EDGE_BAND OUTSIDE it is the gradient the wood thins across.
    const at = (dx: number) => timber(1200 + dx, 800)
    expect(at(-120)).toBe(0)
    expect(at(-250)).toBe(0)
    expect(at(-250 - CLEARING_EDGE_BAND)).toBe(1)
    const mid = at(-250 - CLEARING_EDGE_BAND / 2)
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1)
    expect(at(-250 - CLEARING_EDGE_BAND * 0.75)).toBeGreaterThan(mid)
  })

  /**
   * THE ARM THE FIELD ACTUALLY NEEDED — realised canopy, not the helper.
   *
   * The three arms above drive `buildClearedGround` on a hand-written list, and
   * a hand-written list is not the artifact: measured 2026-07-27, `timber()`
   * over the tree pass's own admissible domain on the COMPOSED islands returned
   * ONE distinct value (1.0000, 240,000 samples) while those arms were green,
   * because the ramp lived on ground the planting predicate refuses. Collapsing
   * TREE_SPACING_MAX 250 -> 72 left the sha256 of every scatter and ring item
   * on twenty islands unchanged. This arm counts CANOPY PER UNIT OF PLANTABLE
   * AREA either side of one band width from the nearest rim, so it can only
   * pass if the gradient reaches the trees that were really planted.
   */
  /**
   * THE CHOSEN SPRITE IS RE-TESTED — and until 2026-07-27 nothing said so.
   *
   * `ScatterOptions.sizeOf` carries a long docstring about why the sampling
   * size is not a conservative size, and deleting the filter it gates
   * (scatter.ts's closing `items.filter`) left all 222 arms in this library
   * GREEN. The composed islands do not currently reach it often enough to trip
   * anything, which is the honest reason it needs a driven arm rather than a
   * bigger seed sweep: unreached is not unreachable, and the mechanism is
   * exactly the one the docstring names.
   *
   * THE SETUP IS THE MECHANISM. The pool's sampling size is the per-axis MAX of
   * its members — 200x200 for a 200x44 plank and a 44x200 post — so it is
   * larger in AREA than either sprite that can be drawn. `groundTaken` divides
   * the shared area by min(area), so the same absolute overlap that reads 0.04
   * against the sampling box reads far more against the sprite that lands.
   */
  it('an item whose DRAWN sprite fails a rule is dropped, not drawn', () => {
    const coast = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 8 })
    const lanes = buildLaneField(buildLanes('gravel_road', (x, y) => coast.landAt(x, y), demand(FULL_NETWORK)))
    const SZ: Record<string, { w: number; h: number }> = {
      plank_wide: { w: 200, h: 44 },
      post_tall: { w: 44, h: 200 },
    }
    const occupied: { at: Point; size: { w: number; h: number } }[] = []
    for (let x = 500; x < 1900; x += 150) {
      for (let y = 500; y < 1400; y += 130) {
        occupied.push({ at: { x, y }, size: { w: 120, h: 120 } })
      }
    }
    const base = {
      space: LAYOUT_SPACE,
      kinds: ['plank_wide', 'post_tall'],
      size: { w: 200, h: 200 },
      pick: () => true,
      density: () => 1,
      onLand: (x: number, y: number) => coast.landAt(x, y),
      lanes,
      occupied,
      rMin: 60,
      rMax: 60,
      cap: 400,
    }
    const loose = poissonScatter('chosen-sprite', base)
    const tight = poissonScatter('chosen-sprite', { ...base, sizeOf: (k: string) => SZ[k] })
    expect(loose.length).toBeGreaterThan(60)
    // IT IS A FILTER, not a re-run: the same points in the same order, minus
    // the ones whose drawn sprite fails. If it reshuffled, one item's kind
    // would change every later item's.
    const keptKeys = new Set(tight.map((i) => `${i.at.x},${i.at.y},${i.kind}`))
    for (const k of keptKeys) {
      expect(loose.some((i) => `${i.at.x},${i.at.y},${i.kind}` === k)).toBe(true)
    }
    const dropped = loose.filter((i) => !keptKeys.has(`${i.at.x},${i.at.y},${i.kind}`))
    expect(dropped.length).toBeGreaterThan(0)
    for (const d of dropped) {
      const drawn = SZ[d.kind]
      // it passed at the SAMPLING size ...
      expect(groundTaken(d.at, base.size, occupied, 0.05)).toBe(false)
      expect(footprintOnLane(d.at, base.size, lanes, 0)).toBe(false)
      // ... and fails on the sprite that would actually have been drawn
      const bad =
        groundTaken(d.at, drawn, occupied, 0.05) || footprintOnLane(d.at, drawn, lanes, 0)
      expect({ kind: d.kind, bad }).toEqual({ kind: d.kind, bad: true })
    }
  })

  it('the wood THINS toward a clearing — measured on the realised canopy', () => {
    // AT CAMP, POOLED OVER EIGHT SEEDS, and both halves of that are the arm
    // rather than convenience. Camp is the era that HAS a wood — the general
    // planting lands 87-103 canopy sprites there against 12-16 at hamlet, where
    // the village has cut most of the interior — so hamlet has no population to
    // measure a density on and its ratio is noise (1.06 control, 0.70 under the
    // mutation: the wrong side, from 40 trees). Pooling eight islands is what
    // makes the number stable enough to threshold.
    let nearArea = 0
    let farArea = 0
    let nearTrees = 0
    let farTrees = 0
    for (const seed of ['acme-corp', 'harbour', 'zeta', 'lantern', 'org-13', 'alpha', 'beta', 'gamma']) {
      const l = composeLayout(CAMP, seed, FAST)
      /** Distance outside the nearest clearing rim; negative inside one. */
      const offRim = (x: number, y: number) => {
        let best = Infinity
        for (const c of l.cleared.clearings) {
          if (c.r <= 0) continue
          const d = Math.hypot(x - c.at.x, (y - c.at.y) * 1.35) - c.r
          if (d < best) best = d
        }
        return best
      }
      // The two populations, by area: ground within a band of a rim, and ground
      // beyond it. Both restricted to what the tree pass could actually plant
      // on, so the ratio compares like with like.
      const rng = seededRng(0xf0e57)
      for (let i = 0; i < 60000; i++) {
        const x = rng() * l.space.w
        const y = rng() * l.space.h
        if (!l.coast.landAt(x, y)) continue
        if (l.cleared.isCleared(x, y)) continue
        const o = offRim(x, y)
        if (o <= 0) continue
        if (o < CLEARING_EDGE_BAND) nearArea++
        else farArea++
      }
      // THE SCATTER ONLY, AND THAT IS THE POINT. The belt does not read a
      // density field at all — it walks the shore by angle — so counting it
      // here would let the arm pass on the belt's coastal stacking while the
      // field it claims to measure was flat. Measured: with `l.ring` folded in,
      // the TREE_SPACING_MAX 250 -> 72 mutation stayed GREEN. That is the
      // sensor-tests-something-other-than-the-control class, caught on this
      // arm's first mutation run.
      for (const t of l.scatter) {
        if (!CANOPY_KINDS.has(t.kind)) continue
        const o = offRim(t.at.x, t.at.y)
        if (o <= 0) continue
        if (o < CLEARING_EDGE_BAND) nearTrees++
        else farTrees++
      }
    }
    expect(nearArea).toBeGreaterThan(5000)
    expect(farArea).toBeGreaterThan(5000)
    expect(nearTrees + farTrees).toBeGreaterThan(300)
    const near = nearTrees / nearArea
    const far = farTrees / farArea
    // MEASURED, BOTH ARMS OF THE MUTATION: 3.76 as it stands, 1.12 with
    // TREE_SPACING_MAX collapsed from 250 to 72 (the mutation that was GREEN on
    // 147 arms before this one existed). The bar sits between them, nearer the
    // mutation, because the claim is a DIRECTION — the wood thins as it
    // approaches cut ground — and a bar at 1.0 would pass on noise.
    expect({ thins: far > near * 2, ratio: far / near > 2 }).toEqual({ thins: true, ratio: true })
  })

  it('REALIZED planting no longer thins toward the middle of the island', () => {
    // THE INVERTED FORM OF THE OLD ARM, which asserted the opposite ratio and
    // was right about the old model. It measured points per unit of plantable
    // area either side of a radial split and required the OUTER band to carry
    // 1.3x the inner one — the ecotope of a coastal ring. Under the Captain's
    // direction the island is overgrown by default, so the honest property is
    // that the interior is no longer the sparse half: an untouched island is
    // wood all the way across, and what thins the middle is the CLEARING, not
    // the distance from the sea.
    //
    // Measured on the camp island (the one with almost nothing cut): 0.0148
    // outer vs 0.0138 per unit area inner — the two bands are within 8%, where
    // the old model ran 1.9x. The bar is set at parity-with-slack rather than
    // at a flipped inequality, because "the interior is denser than the coast"
    // would be just as wrong a claim in the other direction: the belt genuinely
    // does stack four sublayers at the shore.
    const items = [...camp.ring, ...camp.scatter]
    expect(items.length).toBeGreaterThan(200)
    const c = { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy }
    const radialFraction = (p: Point) => {
      const ang = Math.atan2((p.y - c.y) / 0.92, p.x - c.x)
      const d = Math.hypot(p.x - c.x, (p.y - c.y) / 0.92)
      return d / camp.coast.landEdge(ang)
    }
    const SPLIT = 0.55
    let areaOuter = 0
    let areaInner = 0
    const rng = seededRng(0xc0ffee)
    for (let i = 0; i < 40000; i++) {
      const x = rng() * LAYOUT_SPACE.w
      const y = rng() * LAYOUT_SPACE.h
      if (!camp.coast.landAt(x, y)) continue
      if (radialFraction({ x, y }) > SPLIT) areaOuter++
      else areaInner++
    }
    expect(areaOuter).toBeGreaterThan(500)
    expect(areaInner).toBeGreaterThan(500)
    let nOuter = 0
    let nInner = 0
    for (const it of items) (radialFraction(it.at) > SPLIT ? nOuter++ : nInner++)
    const outer = nOuter / areaOuter
    const inner = nInner / areaInner
    expect(inner).toBeGreaterThan(outer * 0.7)
    expect(inner).toBeLessThan(outer * 1.4)
  })

  it('a candidate whose ground is TAKEN is rejected, never nudged', () => {
    const occupied = [{ at: { x: 1200, y: 700 }, size: { w: 400, h: 400 } }]
    const items = poissonScatter('t', {
      kinds: ['bush_round'],
      size: { w: 60, h: 60 },
      pick: () => true,
      density: () => 0.5,
      onLand: (x, y) => coast.landAt(x, y),
      lanes: field,
      occupied,
      cap: 200,
    })
    expect(items.length).toBeGreaterThan(10)
    for (const it of items) {
      expect(groundTaken(it.at, sizeOfItem(it.kind), occupied, 0.05)).toBe(false)
      expect(footprintOnLane(it.at, { w: 60, h: 60 }, field)).toBe(false)
    }
  })

  it('scatter is seeded — same seed same points, different seed different', () => {
    const args = {
      kinds: ['bush_round'],
      size: { w: 60, h: 60 },
      pick: () => true,
      density: () => 0.5,
      onLand: (x: number, y: number) => coast.landAt(x, y),
      lanes: field,
      occupied: [],
      cap: 60,
    }
    expect(poissonScatter('s1', args)).toEqual(poissonScatter('s1', args))
    expect(poissonScatter('s2', args)).not.toEqual(poissonScatter('s1', args))
  })

  it('the exclusion radius follows the density — dense field, more points', () => {
    const base = {
      kinds: ['bush_round'],
      size: { w: 60, h: 60 },
      pick: () => true,
      onLand: (x: number, y: number) => coast.landAt(x, y),
      lanes: field,
      occupied: [],
      cap: 400,
      rMin: 50,
      rMax: 260,
    }
    const wild = poissonScatter('d', { ...base, density: () => 1 })
    const tame = poissonScatter('d', { ...base, density: () => 0 })
    expect(wild.length).toBeGreaterThan(tame.length * 2)
  })
})

// ── era gates content ──────────────────────────────────────────────────────

describe('era gates CONTENT, not just size', () => {
  it('a camp has no plaza and no market', () => {
    // NAMED FOR WHAT IT CAN DETECT. This arm used to claim "...and no field
    // plots" as well, and it could not fail for that reason: field plots are
    // gated on `counts.field_plots` alone and the CAMP fixture omits the count,
    // so the assertion passed on the fixture rather than on the code. The
    // property is asserted properly by the count arm below — which asserts the
    // opposite, because a measured field plot is a COUNT and era may never hide
    // one.
    expect(camp.paint.map((p) => p.kind)).not.toContain('plaza')
    // THE STALL IS DRESSING, NOT A STRUCTURE (iso-layout/dressing.ts). Looking
    // for it in `structures` would now pass for the wrong reason — it is not
    // there at ANY era — so the arm asks the list that can actually hold one.
    expect(camp.dressing.map((d) => d.kind)).not.toContain('market_stall')
    // and the whole village-life class with it: a camp has no benches, no
    // lamps, no market goods and no fowl (compose.py:523)
    expect(camp.dressing.filter((d) => d.role === 'village_life')).toEqual([])
  })

  it('a camp WITH measured field plots draws them — era may not hide a count', () => {
    const farmedCamp = composeLayout(
      { ...CAMP, counts: { officer_dwellings: 1, field_plots: 3 } },
      'acme-corp',
      FAST
    )
    expect(farmedCamp.paint.map((p) => p.kind)).toContain('ploughed')
    // THREE PLOT REGIONS, named by kind rather than by "everything that is not
    // the pond": that phrasing counted the ground-shading passes too, so adding
    // the broken meadow or the mottle broke an arm about FIELD PLOTS. A count
    // over a complement is a count over whatever else the file happens to emit.
    expect(
      farmedCamp.paint.filter((p) => p.kind === 'ploughed' || p.kind === 'crop')
    ).toHaveLength(3)
    // and the fixture camp, which has no such count, draws none
    expect(camp.paint.map((p) => p.kind)).not.toContain('ploughed')
  })

  it('a hamlet has them', () => {
    expect(hamlet.paint.map((p) => p.kind)).toContain('plaza')
    expect(hamlet.dressing.map((d) => d.kind)).toContain('market_stall')
    expect(hamlet.paint.map((p) => p.kind)).toContain('ploughed')
    // AND THE STALL IS GATED ON THE ERA ALONE. It used to be gated on
    // `isBuilt(state, 'market_stall')`, a ladder that does not exist in
    // growth-ladders.yml — so the predicate was false on every state and this
    // arm passed only because `structures` never contained the name it was
    // asserting the absence of one test up. A hamlet with NO stages at all
    // still has a market.
    const bare = composeLayout(
      { era: 'hamlet', road: 'gravel_road', stages: {}, counts: {} },
      'acme-corp',
      FAST
    )
    expect(bare.dressing.map((d) => d.kind)).toContain('market_stall')
  })

  it('a camp still has NATURE — an island is not empty because an org is young', () => {
    expect(camp.scatter.length).toBeGreaterThan(20)
  })

  it('a camp has no verge dressing beside its one worn track', () => {
    const field = buildLaneField(camp.lanes)
    const verge = camp.scatter.filter(
      (s) => field.nearLane(s.at.x, s.at.y, 96) && !field.nearLane(s.at.x, s.at.y, 62)
    )
    // nature can still land near the track; what must not exist is the
    // deliberate verge pass, which plants a dense line of it
    expect(verge.length).toBeLessThan(12)
  })

  it('era may never hide a COUNT: dwellings track the measured number', () => {
    for (const n of [0, 2, 5]) {
      const l = composeLayout({ ...HAMLET, counts: { officer_dwellings: n } }, 'acme-corp', FAST)
      // by ROLE, not by sprite: the officer row draws a different house per lot
      // (see dwellingKind), so a filter on `kind` would count one variant.
      expect(l.structures.filter((s) => s.role === 'officer_dwelling')).toHaveLength(n)
    }
  })

  it('org state cannot reshape MORPHOLOGY — the pond ignores the field count', () => {
    // The pond is emitted AFTER the fields, so with one shared rng stream its
    // shape would depend on how many draws the fields consumed — i.e. water
    // would move because an org ploughed a field. Per-region streams are what
    // make "morphology, not doctrine" literally true.
    //
    // Assert the pond EXISTS first: it is clipped to land, so on an island
    // with no west meadow there is nothing to compare and the arm would pass
    // vacuously — which is a disabled sensor, not a green one.
    // seed 'zeta' rather than 'acme-corp': the pond is clipped to land, and on
    // acme-corp the west meadow is genuinely offshore, so there is no pond to
    // compare. Picking a seed that HAS one is the difference between an arm and
    // a vacuous pass — hence the toBeDefined() below.
    const pondOf = (n: number) =>
      composeLayout(
        { ...HAMLET, counts: { officer_dwellings: 3, field_plots: n } },
        'zeta',
        FAST
      ).paint.find((p) => p.kind === 'pond')
    const bare = pondOf(0)
    const farmed = pondOf(3)
    expect(bare).toBeDefined()
    expect(bare!.blobs.length).toBeGreaterThan(0)
    expect(farmed).toEqual(bare)
  })

  it('the pond is clipped to LAND ALONG ITS WHOLE EXTENT, not at its centre', () => {
    // THE ARM THIS REPLACES WAS DEAD. It sampled blob CENTRES — the one
    // quantity the old implementation special-cased — so it could not fail for
    // the reason it named. Measured against that code: every centre was on
    // land while 11 of 26 extent samples on seed acme-corp and 24 of 182 on
    // seed lantern stood in open water. Sampling is 90 rim angles plus a 7x7
    // interior grid, denser than and offset from the clip's own probe.
    let ponds = 0
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const pond = l.paint.find((p) => p.kind === 'pond')
      if (!pond) continue
      ponds++
      for (const b of pond.blobs) {
        for (const p of blobExtentSamples(b)) {
          expect(l.coast.landAt(p.x, p.y)).toBe(true)
        }
      }
    }
    // "no pond anywhere" would satisfy every assertion above without testing
    // anything — which is the failure mode this whole arm was rewritten for
    expect(ponds).toBeGreaterThan(2)
  })

  it('the extent sensor is STRICTLY STRONGER than the centre sensor it replaced', () => {
    // Permanent proof that the fix to the sensor is a fix: build a blob whose
    // centre is on land and whose rim is not, and show the two sensors
    // disagree. Without this, "the pond is clipped" could quietly revert to
    // being tested at its centre again and every arm would stay green.
    const onLand = (x: number, _y: number) => x < 1000
    const b = { c: { x: 960, y: 500 }, rx: 80, ry: 40 }
    expect(onLand(b.c.x, b.c.y)).toBe(true) // the dead sensor passes it
    expect(blobExtentSamples(b).every((p) => onLand(p.x, p.y))).toBe(false)
    // and the clip refuses it at that size, shrinking it until it fits
    const clipped = clipBlobToLand(b, onLand)
    expect(clipped).not.toBeNull()
    expect(clipped!.rx).toBeLessThan(b.rx)
    expect(blobExtentSamples(clipped!).every((p) => onLand(p.x, p.y))).toBe(true)
    // a blob with no land under it at all is DROPPED, not shrunk to a dot
    expect(clipBlobToLand({ c: { x: 1400, y: 500 }, rx: 80, ry: 40 }, onLand)).toBeNull()
  })

  it('the audit measures the CALLER’s footprints, not a default table', () => {
    // An audit that looked sizes up in DEFAULT_FOOTPRINTS would silently
    // measure a different world whenever the pack overrides them — which is
    // the "audit must call the same function the rule calls" defect. Prove it
    // by handing the audit an item whose CARRIED size reaches a lane and whose
    // TABLE size does not: only an audit reading the carried size sees it.
    const big = composeLayout(HAMLET, 'acme-corp', {
      ...FAST,
      footprintOf: (k) => (k === 'bush_round' ? { w: 400, h: 400 } : undefined),
    })
    for (const s of big.scatter) {
      if (s.kind === 'bush_round') expect(s.size).toEqual({ w: 400, h: 400 })
    }
    // find a probe point where the two sizes genuinely disagree, and assert
    // that precondition rather than assuming a hand-picked offset still holds
    const field = buildLaneField(big.lanes)
    const east = big.lanes.find((l) => l.key === 'east')!
    const eastRun = east.runs[0]
    const anchor = eastRun[Math.floor(eastRun.length / 2)]
    let probe: Point | null = null
    for (let dy = 60; dy <= 200 && !probe; dy += 5) {
      const p = { x: anchor.x, y: anchor.y + dy }
      const bigReaches = footprintOnLane(p, { w: 400, h: 400 }, field)
      const smallReaches = footprintOnLane(p, DEFAULT_FOOTPRINTS.bush_round, field)
      if (bigReaches && !smallReaches) probe = p
    }
    expect(probe).not.toBeNull()
    const planted = {
      ...big,
      scatter: [
        ...big.scatter,
        { kind: 'bush_round', at: probe!, flip: false, size: { w: 400, h: 400 } },
      ],
    }
    expect(auditLayout(planted).onLane.map((o) => o.kind)).toEqual(['bush_round'])
    const tableSized = {
      ...planted,
      scatter: planted.scatter.map((s) => ({ ...s, size: DEFAULT_FOOTPRINTS[s.kind] ?? s.size })),
    }
    expect(auditLayout(tableSized).onLane).toEqual([])
  })

  it('an unbuilt object draws nothing', () => {
    const l = composeLayout(
      { era: 'hamlet', road: 'dirt_worn', stages: { library: 'none', workshop: null }, counts: {} },
      'acme-corp',
      FAST
    )
    expect(l.structures.map((s) => s.kind)).not.toContain('library')
    expect(l.structures.map((s) => s.kind)).not.toContain('workshop')
  })
})

// ── nothing stands on open water ───────────────────────────────────────────

/**
 * Every FELLED clearing is centred on land, and the natural ones need not be.
 *
 * THE ARM USED TO SAY "every district anchor". It was right while a district
 * was a keep-out disc derived from an authored compass anchor: a disc centred
 * in the sea reserves sea, and the planting it was meant to keep out of the
 * village then arrives in the village. It went red on the inverted model
 * (Captain 2026-07-27) because the list now also carries the LANDING — the one
 * place a hatched island is open on day zero — whose centre is the cove, which
 * is water by construction and is the whole reason that clearing exists.
 *
 * So the invariant is kept where it means something and named where it does
 * not: anything an axe made must stand on ground, and a clearing that marks a
 * pond or a beach marks exactly the thing that is not ground. Every clearing is
 * checked; none is skipped silently.
 */
function expectClearingsGrounded(l: Layout) {
  const natural = new Set(['pond', 'landing'])
  for (const c of l.cleared.clearings) {
    if (c.cut === 'natural') {
      expect({ role: c.role, known: natural.has(c.role) }).toEqual({ role: c.role, known: true })
      continue
    }
    expect({ role: c.role, land: l.coast.landAt(c.at.x, c.at.y) }).toEqual({
      role: c.role,
      land: true,
    })
  }
  // and the derived disc list is exactly the clearings, so nothing can be added
  // to one and not the other
  expect(l.districts.length).toBe(l.cleared.clearings.length)
}

describe('the land rule — nothing stands on open water', () => {
  it('every structure in every era on every seed stands on land', () => {
    for (const seed of SEEDS) {
      for (const state of [HAMLET, CAMP]) {
        const l = composeLayout(state, seed, FAST)
        expect(l.structures.length).toBeGreaterThan(0) // not vacuous
        for (const s of l.structures) {
          expect({
            seed,
            kind: s.kind,
            land: l.coast.landAt(s.at.x, s.at.y - 2),
          }).toEqual({ seed, kind: s.kind, land: true })
        }
        expect(auditLayout(l).inWater).toEqual([])
      }
    }
  })

  it('every LOT and every district anchor ends on land', () => {
    // A lot is not just where a sprite stands: it is what the door, the drive
    // and the keep-out disc are derived from, so a lot in the sea puts a drive
    // in the sea even when the building was walked inland. Measured before the
    // snap: 13 of 80 seeds had a lot in open water.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      for (const lot of Object.values(l.lots).flat()) {
        expect(l.coast.landAt(lot.c.x, lot.c.y)).toBe(true)
      }
      expectClearingsGrounded(l)
    }
  })

  it('a SMALLER island strands every fixed anchor — and still nothing is drawn on water', () => {
    // THE ARM THAT ACTUALLY BITES. On the reference ellipse the compass anchors
    // happen to be inland on most seeds, so the arms above pass with the land
    // rules deleted for four seeds out of five — a sensor that cannot detect
    // the absence of the thing it names. Shrinking the island through the
    // public `coastline.radii` option strands the anchors on EVERY seed, which
    // is how the review reproduced it (hw=560 put four structures including the
    // workshop in open sea, with the audit reporting clean).
    // The small radii are not gratuitous: at hw<=360 the CIVIC anchors (square,
    // well, market stall) are themselves offshore, and those are not lots and
    // are not snapped — so they are the case that proves the land walk inside
    // placeOnGround is load-bearing rather than belt-and-braces. Measured: at
    // hw=300 on seed zeta all three civic anchors are in the sea and all ten
    // structures still stand on land.
    for (const hw of [800, 700, 560, 360, 300]) {
      for (const seed of ['acme-corp', 'zeta']) {
        const l = composeLayout(HAMLET, seed, {
          coastline: { step: 4, radii: { hw, vh: Math.round((hw * 784) / 962) } },
        })
        // EVERY MEASURED BUILDING STILL EXISTS — the rule moves things, it
        // does not quietly delete the org's districts. Asserted as the set of
        // ROLES the state justifies rather than as a count: the count was 10,
        // which silently encoded "one of the eleven is dropped on these radii",
        // so a change that made the eleventh fit read as a regression. A number
        // that nobody can derive from the state is a number nobody can check.
        expect(l.structures.map((s) => s.role).sort()).toEqual(
          justifiedRoles(HAMLET).sort()
        )
        for (const s of l.structures) {
          expect({ hw, seed, kind: s.kind, land: l.coast.landAt(s.at.x, s.at.y - 2) }).toEqual({
            hw,
            seed,
            kind: s.kind,
            land: true,
          })
        }
        expect(auditLayout(l).inWater).toEqual([])
        for (const lot of Object.values(l.lots).flat()) {
          expect(l.coast.landAt(lot.c.x, lot.c.y)).toBe(true)
        }
        expectClearingsGrounded(l)
        for (const lane of l.lanes) {
          for (const p of lane.runs.flat()) expect(l.coast.landAt(p.x, p.y)).toBe(true)
        }
      }
    }
  })

  it('the walk goes INLAND and gives up rather than lying', () => {
    // a half-plane of sea to the west; the centre is east of it
    const onLand = (x: number, _y: number) => x > 1000
    const walked = walkInland({ x: 900, y: 760 }, onLand, { x: 1200, y: 760 })
    expect(walked).not.toBeNull()
    expect(onLand(walked!.x, walked!.y)).toBe(true)
    expect(walked!.x).toBeGreaterThan(900)
    // 45% of the way is the reference's reach: from 300px out it cannot arrive
    expect(walkInland({ x: 100, y: 760 }, onLand, { x: 1200, y: 760 })).toBeNull()
    // and a thing already on land is not moved at all
    const still = { x: 1500, y: 400 }
    expect(walkInland(still, onLand, { x: 1200, y: 760 })).toEqual(still)
  })

  it('placeOnGround returns NULL rather than a point in the sea', () => {
    const field = buildLaneField([])
    const sea = () => false
    expect(placeOnGround({ x: 400, y: 400 }, { w: 150, h: 150 }, field, sea, [])).toBeNull()
    // the same call over land returns a point — so the null is the water rule
    // and not an unrelated failure
    expect(placeOnGround({ x: 400, y: 400 }, { w: 150, h: 150 }, field, LAND, [])).not.toBeNull()
  })

  it('snapInland clears a MARGIN, not just the point, and can refuse', () => {
    const onLand = (x: number, _y: number) => x > 1000
    const snapped = snapInland({ x: 900, y: 700 }, onLand, { x: 1400, y: 700 }, 70)
    expect(snapped).not.toBeNull()
    // the margin in every direction, which a bare point test would not give
    for (const [dx, dy] of [[0, 0], [0, 70], [0, -70], [70, 0], [-70, 0]]) {
      expect(onLand(snapped!.x + dx, snapped!.y + dy)).toBe(true)
    }
    // an island with no land at all cannot be snapped to, and saying so beats
    // handing back the centre and calling it ground
    expect(snapInland({ x: 900, y: 700 }, () => false, { x: 1400, y: 700 })).toBeNull()
  })

  it('the WATER audit can actually fail — a structure moved offshore trips it', () => {
    // negative twin for the arms above: without it, `inWater: []` would also be
    // what a broken audit that never looks at anything returns.
    const sea = { x: 60, y: 60 }
    expect(hamlet.coast.landAt(sea.x, sea.y)).toBe(false)
    const drowned = {
      ...hamlet,
      structures: [
        {
          kind: 'workshop',
          role: 'workshop',
          at: sea,
          flip: false,
          size: { w: 170, h: 170 },
          rung: 0,
          age: 0,
        },
      ],
    }
    expect(auditLayout(drowned).inWater).toEqual([{ kind: 'workshop', at: sea }])
  })
})

// ── the painted surfaces are clipped to land ───────────────────────────────

describe('every painted mask is clipped to land', () => {
  it('no lane or drive sample stands in open water', () => {
    // The measurement the review ran, as an arm: sampled every 6px along each
    // run exactly as checks/world_checks.py:check_terrain samples a lane, with
    // the same cove exemption (a harbour approach is allowed to reach the
    // water). Before the clip, 37 of 80 seeds had at least one such sample.
    const cove = { x: 1200, y: 1430, r: 300 }
    for (const seed of SEEDS) {
      for (const state of [HAMLET, CAMP]) {
        const l = composeLayout(state, seed, FAST)
        // not vacuous: a camp keeps 14-19 samples of its one clipped track,
        // a hamlet 300+ across the network
        expect(laneSamples(l).length).toBeGreaterThan(10)
        for (const lane of l.lanes) {
          for (const run of lane.runs) {
            for (let i = 0; i + 1 < run.length; i++) {
              const a = run[i]
              const b = run[i + 1]
              const steps = Math.floor(Math.hypot(b.x - a.x, b.y - a.y) / 6) + 1
              for (let t = 0; t <= steps; t++) {
                const x = a.x + ((b.x - a.x) * t) / steps
                const y = a.y + ((b.y - a.y) * t) / steps
                if (Math.hypot(x - cove.x, y - cove.y) <= cove.r) continue
                expect({ seed, key: lane.key, land: l.coast.landAt(x, y) }).toEqual({
                  seed,
                  key: lane.key,
                  land: true,
                })
              }
            }
          }
        }
      }
    }
  })

  it('the clip CUTS rather than trims — a lane crossing an inlet is two runs', () => {
    const path = [
      { x: 100, y: 100 },
      { x: 200, y: 100 },
      { x: 300, y: 100 },
      { x: 400, y: 100 },
      { x: 500, y: 100 },
    ]
    const notInlet = (x: number, _y: number) => !(x > 250 && x < 350)
    expect(clipToLand(path, notInlet)).toEqual([
      [{ x: 100, y: 100 }, { x: 200, y: 100 }],
      [{ x: 400, y: 100 }, { x: 500, y: 100 }],
    ])
    // and the occupancy field does NOT bridge the gap: interpolating across it
    // would put the road back on the water the clip just removed
    const cut = buildLaneField([{ key: 'c', kind: 'main', width: 40, surface: 'gravel_road', runs: clipToLand(path, notInlet) }])
    const whole = buildLaneField([{ key: 'c', kind: 'main', width: 40, surface: 'gravel_road', runs: [path] }])
    expect(whole.onLane(300, 100)).toBe(true)
    expect(cut.onLane(300, 100)).toBe(false)
    // a lane wholly offshore is not a lane
    expect(clipToLand(path, () => false)).toEqual([])
  })

  it('the clip cuts on the SEGMENT, not just the station — a narrow channel still cuts', () => {
    // Stations are ~16px apart, so testing only stations lets the line cross
    // anything narrower than that, and both the renderer and the occupancy
    // field then carry the road over it. Measured with station-only clipping:
    // 1 of 80 seeds still bridged an inlet. Here every station is on land and
    // only the 10px channel between two of them is not.
    const path = [
      { x: 100, y: 100 },
      { x: 140, y: 100 },
      { x: 160, y: 100 },
      { x: 200, y: 100 },
    ]
    const channel = (x: number, _y: number) => !(x > 145 && x < 155)
    expect(path.every((p) => channel(p.x, p.y))).toBe(true) // stations all on land
    expect(clipToLand(path, channel)).toEqual([
      [{ x: 100, y: 100 }, { x: 140, y: 100 }],
      [{ x: 160, y: 100 }, { x: 200, y: 100 }],
    ])
  })

  it('every painted blob — plaza, field and pond — is on land along its extent', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const kinds = l.paint.map((r) => r.kind)
      expect(kinds).toContain('plaza')
      expect(kinds).toContain('crop') // not vacuous: something is painted
      for (const region of l.paint) {
        for (const b of region.blobs) {
          for (const p of blobExtentSamples(b)) {
            expect({ seed, kind: region.kind, land: l.coast.landAt(p.x, p.y) }).toEqual({
              seed,
              kind: region.kind,
              land: true,
            })
          }
        }
      }
    }
  })

  it('a field plot with no land under it is DROPPED, not painted on the sea', () => {
    // The seed the review found with a whole crop plot offshore is a moving
    // target; assert the mechanism instead. The four plot anchors sit in the
    // south-east, so an island whose east half is sea must lose plots rather
    // than paint them — and the layout says so by emitting fewer regions.
    const westOnly = composeLayout(HAMLET, 'acme-corp', {
      ...FAST,
      coastline: { step: 8, radii: { hw: 500, vh: 500 }, cove: null },
    })
    const fields = westOnly.paint.filter((p) => p.kind === 'crop' || p.kind === 'ploughed')
    expect(fields.length).toBeLessThan(2)
    // the same state on the full island paints both
    expect(hamlet.paint.filter((p) => p.kind === 'crop' || p.kind === 'ploughed')).toHaveLength(2)
  })
})

// ── the keep-out discs are an exclusion ────────────────────────────────────

describe('a keep-out disc is an exclusion, not a density hint', () => {
  it('nothing is planted inside a clearing except the record of the felling', () => {
    // Measured before the fix: 72-80% of every seed's planting stood inside a
    // disc, including a full-size oak 26px from the great house.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      // NOT VACUOUS — counted over the planting, which is the ring AND the
      // meadow scatter. The old guard counted `scatter` alone and it started
      // tripping the moment the belt landed: the belt takes the coastal band
      // first, so the meadow pass legitimately emits fewer points while the
      // island carries three times as many plants. A liveness guard aimed at
      // part of a population reports a shortage that does not exist.
      expect(l.ring.length + l.scatter.length).toBeGreaterThan(60)
      // EXCEPT THE POND'S OWN TWO PLANTS. Lilypads and bank reeds are placed
      // by passes that are deliberately not free()-gated — exactly as the verge
      // pass is not — and the pond's 190px disc covers the water and its whole
      // margin, so both land inside one by design.
      //
      // The exemption is stated as WHERE, not as WHICH SPRITE: an item may be
      // inside a disc only if it is standing in the pond or on the pond's
      // margin. Exempting the name `reeds` would have opened a hole for the
      // SHORE pass, which plants reeds too and is free()-gated, so a shore reed
      // that wandered into the village square would have stopped being visible
      // to this arm. planting.test.ts then pins the other half — that every one
      // of these really is at a waterline.
      const pondPlant = (p: Point) =>
        waterField(l.paint)(p.x, p.y) || grownField(l.paint, ['pond', 'stream'], 52)(p.x, p.y)
      // AND EXCEPT THE FELLING RECORD, which arrived with the inverted model
      // (Captain 2026-07-27). A disc is no longer an exclusion; it is ground
      // that was CUT, and a stump stands where the tree stood — inside it, at
      // the rim. Exempted as WHERE and WHAT together: only a record sprite, and
      // only within RECORD_BAND of a felled rim, so a stump that wandered into
      // the middle of the square is still a defect this arm can see.
      const onRim = (p: Point) => l.cleared.recordAt(p.x, p.y) > 0
      const inside = l.scatter.filter(
        (s) =>
          insideDisc(l, s.at) &&
          !pondPlant(s.at) &&
          !(RECORD_FRAMES.has(s.kind) && onRim(s.at))
      )
      expect({ seed, inside: inside.map((s) => s.kind) }).toEqual({ seed, inside: [] })
      // NOT VACUOUS the other way either: the exemption must be used, or this
      // arm silently became the old one again.
      expect(
        l.scatter.some((s) => RECORD_FRAMES.has(s.kind) && insideDisc(l, s.at))
      ).toBe(true)
    }
  })

  it('the disc test is LIVE — the village core is inside one', () => {
    // negative twin: without this, "nothing inside a disc" would also pass if
    // `districts` were empty or the metric never returned true
    expect(hamlet.districts.length).toBeGreaterThan(4)
    const gh = hamlet.structures.find((s) => s.kind === 'great_house')!
    expect(insideDisc(hamlet, gh.at)).toBe(true)
    expect(insideDisc(hamlet, { x: 60, y: 60 })).toBe(false)
  })

  it('nothing is planted on the plaza, in a field or in the pond', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const onPaint = l.scatter.filter(
        (s) => s.kind !== 'lilypads' && insidePaint(l, ['plaza', 'crop', 'ploughed', 'pond'], s.at)
      )
      expect({ seed, onPaint: onPaint.map((s) => s.kind) }).toEqual({ seed, onPaint: [] })
      // ...and the ring, which is a separate population placed by a separate
      // module against its own predicate — the arm above would not have noticed
      // a belt growing straight across the plaza.
      const ringOnPaint = l.ring.filter((s) =>
        insidePaint(l, ['plaza', 'crop', 'ploughed', 'pond', 'stream'], s.at)
      )
      expect({ seed, ringOnPaint: ringOnPaint.map((s) => s.kind) }).toEqual({
        seed,
        ringOnPaint: [],
      })
    }
  })

  /**
   * THE BELT KEEPS OFF A BUILDING TOO — the other half of "the trees".
   *
   * index.ts's WOOD_OVERLAP docstring claimed "the unit arm measures
   * tree-against-structure overlap across the composed islands and holds it at
   * zero". That arm read `l.scatter`. The BELT is a second population placed by
   * ./ring against its own rules, and it was calling `groundTaken` at the
   * tree-vs-tree default of 0.16: measured 2026-07-27, 27 belt-vs-structure
   * pairs over 0.04 with a worst of 0.131 — a pine standing through a wall,
   * with every arm in the library green. A claim about the trees that counts
   * one of the two populations that plant them is the coverage-bound failure.
   */
  it('NEITHER population of trees shares a building’s ground', () => {
    let checked = 0
    for (const state of [CAMP, HAMLET, BEYOND_BAY]) {
      for (const seed of SEEDS) {
        const l = composeLayout(state, seed, FAST)
        const built = l.structures.map((s) => ({ at: s.at, size: s.size }))
        expect(built.length).toBeGreaterThan(0)
        for (const [name, pop] of [
          ['ring', l.ring],
          ['scatter', l.scatter],
        ] as const) {
          for (const t of pop) {
            const v = maxGroundOverlap(t.at, t.size, built)
            checked++
            if (v > RING_BUILT_OVERLAP) {
              expect({ seed, era: state.era, pop: name, kind: t.kind, v }).toEqual({
                seed,
                era: state.era,
                pop: name,
                kind: t.kind,
                v: 0,
              })
            }
          }
        }
      }
    }
    // not vacuous: there really are thousands of trees to have caught
    expect(checked).toBeGreaterThan(2000)
  })

  /**
   * VILLAGE FURNITURE STANDS ON GROUND SOMEBODY CUT (Captain 2026-07-27).
   *
   * Measured before the rule existed, over 20 hamlet islands: 648 pieces of
   * village furniture in standing timber, 129 of them under FULLY CLOSED
   * canopy, one fence run 188px past the nearest rim. The bar is the treeline's
   * midpoint rather than the rim — see FURNITURE_MAX_TIMBER.
   */
  it('no village furniture stands in ground that is more wood than clearing', () => {
    let seen = 0
    for (const state of [HAMLET, BEYOND_BAY]) {
      for (const seed of SEEDS) {
        const l = composeLayout(state, seed, FAST)
        for (const d of l.dressing) {
          if (d.role !== 'village_life' || d.overWater) continue
          seen++
          const t = l.cleared.timber(d.at.x, d.at.y)
          if (t >= FURNITURE_MAX_TIMBER) {
            expect({ seed, era: state.era, kind: d.kind, timber: t }).toEqual({
              seed,
              era: state.era,
              kind: d.kind,
              timber: 0,
            })
          }
        }
      }
    }
    // not vacuous, and the count is the other half of the claim: the furniture
    // did not simply vanish when the rule arrived
    expect(seen).toBeGreaterThan(400)
  })

  /**
   * NOTHING A `put` EMITS STANDS IN THE SEA — on the row it is RECORDED on.
   *
   * `placeOnGround` closed with `onLand(p.x, p.y - 2)` while returning `p`, and
   * two pixels is everything on a shallow waterline: two warehouses stood at
   * (1057,1281) and (1053,1289) on the composed beyond_bay island, byte
   * identical across three commits, because their stem row was the last row of
   * beach and their own foot was not. The audit never saw them because it asks
   * the same `y - 2` question the placer did.
   */
  it('placeOnGround refuses a spot whose OWN row is water', () => {
    // A synthetic coast whose waterline is a single row: land at y <= 1000.
    const onLand = (_x: number, y: number) => y <= 1000
    const lanes = buildLaneField([])
    const size = { w: 80, h: 80 }
    // POSITIVE CONTROL: two rows further in, the same call succeeds — so a null
    // below is the land rule and not a broken fixture.
    const good = placeOnGround({ x: 1200, y: 996 }, size, lanes, onLand, [], {
      inlandTo: { x: 1200, y: 500 },
    })
    expect(good).not.toBeNull()
    expect(onLand(good!.x, good!.y)).toBe(true)
    // The 2px band the two rules used to disagree over: y = 1001 has land at
    // y-2 = 999 and water at its own row.
    expect(onLand(1200, 1001)).toBe(false)
    expect(onLand(1200, 999)).toBe(true)
    const walked = placeOnGround({ x: 1200, y: 1001 }, size, lanes, onLand, [], {
      inlandTo: { x: 1200, y: 500 },
    })
    // it is not dropped — it is WALKED INLAND, which is the point: the rule
    // rescues rather than deletes, and what it returns is on land on its own row
    expect(walked).not.toBeNull()
    expect(onLand(walked!.x, walked!.y)).toBe(true)
    // and with no land at all in reach there is nothing to return
    expect(
      placeOnGround({ x: 1200, y: 1400 }, size, lanes, () => false, [], {
        inlandTo: { x: 1200, y: 500 },
      })
    ).toBeNull()
  })

  it('the great house keeps its ground — no full-size tree at its door', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const gh = l.structures.find((s) => s.kind === 'great_house')!
      // TWO POINTS, because they are not the same point and pretending they are
      // would hide which rule is doing the work. The disc reserves the ANCHOR
      // (the lot, 1200,800); the house is DRAWN 115px west of it, because the
      // forecourt lane ends at the anchor and the road wins. So the disc arm is
      // measured against the anchor, and the drawn house gets the weaker claim
      // it can actually make.
      // THE RADIUS IS READ, NOT TYPED. It used to be the literal 250 of the
      // authored GREAT district disc; under the inverted model the great house
      // cuts its OWN clearing and its radius is a function of the drawn size and
      // the rung (iso-layout/clearing.ts), so a hardcoded number here would be a
      // second opinion about how much ground the manor took. The clearing is
      // found by role, and the arm fails loudly if there is not exactly one.
      //
      // AND THE FELLING RECORD IS EXEMPT, for the reason the disc arm above
      // records: a stump stands inside the ground it was cut from.
      const ghClearing = l.cleared.clearings.filter((c) => c.role === 'great_house')
      expect(ghClearing.length).toBe(1)
      const planting = l.scatter.filter((s) => !RECORD_FRAMES.has(s.kind))
      const toCentre = Math.min(
        ...planting.map((s) =>
          Math.hypot(s.at.x - ghClearing[0].at.x, (s.at.y - ghClearing[0].at.y) * 1.35)
        )
      )
      expect(toCentre).toBeGreaterThan(ghClearing[0].r)
      const toHouse = Math.min(
        ...planting.map((s) => Math.hypot(s.at.x - gh.at.x, s.at.y - gh.at.y))
      )
      // measured before the keep-out fix: 26-103px, i.e. a 150px oak touching
      // the manor. After: 128-222px across these seeds.
      expect(toHouse).toBeGreaterThan(120)
      // and nothing shares its ground, which is the occupancy rule, not the disc
      expect(groundTaken(gh.at, gh.size, l.scatter.map((s) => ({ at: s.at, size: s.size })), 0.05)).toBe(
        false
      )
    }
  })

  it('the pond is water, and water is not a place to plant', () => {
    const ponded = composeLayout(HAMLET, 'zeta', FAST)
    const pondWater = waterField(ponded.paint)
    const pond = ponded.paint.find((p) => p.kind === 'pond')!
    expect(pondWater(pond.blobs[0].c.x, pond.blobs[0].c.y)).toBe(true)
    expect(pondWater(60, 60)).toBe(false)
    for (const s of ponded.scatter) expect(pondWater(s.at.x, s.at.y)).toBe(false)
    // an island with no pond has no water field rather than a phantom one
    expect(waterField([])(612, 1086)).toBe(false)
  })

  it('the pond keep-out disc COVERS the pond — which is why the water term is quiet', () => {
    // Deleting the `inWater` term from free() leaves every arm above green: the
    // pond lies wholly inside its own 190px district disc, so the disc is what
    // is actually keeping trees out of the water today. That is a dependency,
    // not a coincidence, and an undeclared dependency is how a rule gets
    // deleted as "redundant" and takes a live guarantee with it. This arm is
    // the declaration: if the pond ever grows past its disc — new blob radii, a
    // moved anchor, an era gate on the disc — it goes red, and the water term
    // becomes load-bearing at exactly that moment.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const pond = l.paint.find((p) => p.kind === 'pond')
      if (!pond) continue
      for (const b of pond.blobs) {
        for (const p of blobExtentSamples(b)) expect(insideDisc(l, p)).toBe(true)
      }
    }
  })
})

// ── the rules that five seeds cannot decide ────────────────────────────────

describe('the seed SPACE, not five islands', () => {
  it('the land snap does not undo the separation it runs after', () => {
    // THE ARM THE REGRESSION NEEDED. Snapping a lot inland pulls it toward the
    // island centre — and so does its neighbour's snap, so a row relaxed to
    // exactly 168px closes up behind itself. Measured when the snap was added
    // with no repair: 40 of 80 seeds under the rule, worst 59.8px, and two
    // officer dwellings sharing ground on org-13. Every one of the five named
    // seeds was clean, which is why the sweep is the sensor and not SEEDS.
    //
    // TWO NUMBERS, because one of them cannot see half the defect. Measured on
    // this exact sweep, with each guard disabled in turn:
    //
    //                                     worst pair   seeds under the rule
    //   as built                             67.2px            5 / 80
    //   the repair pass removed              64.2px           42 / 80   <- the regression
    //   its monotone test removed            42.2px            5 / 80
    //   its second (bare-land) phase removed 67.2px           32 / 80
    //
    // The worst pair barely moves when the pass is deleted — a floor alone
    // would have been a green tick over the defect it was written for — while
    // the count moves 8x. And the count barely moves when the monotone test is
    // deleted, while the worst pair collapses. Both, or neither works.
    let worst = Infinity
    let worstSeed = ''
    let under = 0
    for (const seed of WIDE_SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      expect(Object.values(l.lots).flat().length).toBeGreaterThan(6) // not vacuous
      const d = closestLotPair(l)
      if (d < LOT_SEPARATION - 0.1) under++
      if (d < worst) {
        worst = d
        worstSeed = seed
      }
    }
    expect({ worstSeed, worstOk: worst > 60, under }).toEqual({
      worstSeed,
      worstOk: true,
      under: expect.any(Number),
    })
    expect(under).toBeLessThanOrEqual(10)
  })

  it('no two structures share ground on ANY seed, not just the demo island', () => {
    // auditLayout reported a stacked pair on org-13 for a whole review cycle
    // while the only stacking arm composed one seed.
    for (const seed of WIDE_SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      expect(l.structures.length).toBeGreaterThan(6) // not vacuous
      expect({ seed, stacked: auditLayout(l).stacked }).toEqual({ seed, stacked: [] })
    }
  })

  it('the road-wins fallback takes the SLIGHTEST stack, not the first one', () => {
    // clearOfLane may only fall back to shared ground when nothing is clear —
    // and then it has to rank. Two occupants, one barely overlapping and one
    // heavily: with the ring boxed in by lanes, the answer must be the light one.
    const size = { w: 150, h: 150 }
    const at = { x: 1000, y: 1000 }
    const lanes = buildLaneField([
      { key: 'wall', kind: 'main', width: 200, surface: 'gravel_road', runs: [[at]] },
    ])
    expect(footprintOnLane(at, size, lanes)).toBe(true) // the search must engage
    // exactly two pockets of land within reach, and both are occupied — so the
    // ring cannot return anything clear and MUST rank its fallbacks
    const EAST = { x: 1197, y: 1000 }
    const WEST = { x: 803, y: 1000 }
    const onLand = (x: number, y: number) =>
      Math.hypot(x - EAST.x, y - EAST.y) < 15 || Math.hypot(x - WEST.x, y - WEST.y) < 15
    const heavy = { at: EAST, size } //  the ring reaches this one FIRST
    const light = { at: { x: WEST.x + 100, y: WEST.y }, size }
    expect(maxGroundOverlap(EAST, size, [heavy])).toBeGreaterThan(0.9)
    expect(maxGroundOverlap(WEST, size, [light])).toBeGreaterThan(0.16)
    expect(maxGroundOverlap(WEST, size, [light])).toBeLessThan(0.5)
    const landed = clearOfLane(at, size, lanes, onLand, [heavy, light], { reach: 400 })
    // it took the west pocket: the lighter stack, not the one it met first
    expect(maxGroundOverlap(landed, size, [heavy, light])).toBeLessThan(0.5)
    expect(Math.abs(landed.x - WEST.x)).toBeLessThan(15)
    // and it really is off the road, which is the constraint that wins
    expect(footprintOnLane(landed, size, lanes)).toBe(false)
  })

  it('nothing is planted on the plaza or in a plot ACROSS THE SWEEP', () => {
    // The five-seed arm above passed while nine shore-band items (reeds,
    // rock_small, rock_cluster) stood in the east crop plot, whose outer rim
    // reaches past every keep-out disc. The property was carried incidentally
    // by the discs, and incidental coverage is not coverage.
    for (const seed of WIDE_SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      expect(l.paint.some((r) => r.kind === 'crop' || r.kind === 'ploughed')).toBe(true)
      const on = [...l.ring, ...l.scatter].filter(
        (s) => s.kind !== 'lilypads' && insidePaint(l, ['plaza', 'crop', 'ploughed', 'pond'], s.at)
      )
      expect({ seed, on: on.map((s) => `${s.kind}@${s.at.x.toFixed(0)},${s.at.y.toFixed(0)}`) }).toEqual({
        seed,
        on: [],
      })
    }
  })

  it('paintField answers about the painted region, and is empty when nothing is painted', () => {
    // negative twin for the term above: a predicate that returns false
    // everywhere would also make the sweep pass
    const l = composeLayout(VILLAGE, 'org-9', FAST)
    const plots = paintField(l.paint, ['crop', 'ploughed'])
    const b = l.paint.find((r) => r.kind === 'crop' || r.kind === 'ploughed')!.blobs[0]
    expect(plots(b.c.x, b.c.y)).toBe(true)
    expect(plots(60, 60)).toBe(false)
    expect(paintField([], ['crop'])(1548, 1218)).toBe(false)
    // and it is keyed on KIND — the pond is not a plot
    expect(paintField(l.paint, ['crop', 'ploughed'])(612, 1086)).toBe(false)
  })
})

// ── the rules that had no sensor at all ────────────────────────────────────

describe('rules that were stated and never measured', () => {
  it('a blob with WATER INSIDE IT is rejected even when its whole rim is land', () => {
    // The clip probes a rim AND an interior lattice, and the interior half had
    // no arm: deleting it left all 74 arms green. It is not decoration —
    // replaying the clip over 84,336 (rim, interior) evaluations across seeds
    // and island sizes, the interior was the deciding probe 13 times, on the
    // default island (org-1 and org-3 ponds, org-2 ploughed, org-24 plaza).
    // A lagoon is the shape that does it: land all the way round, water in the
    // middle, which a rim-only test calls solid ground.
    // A MOAT, not a lagoon: the centre has to be LAND, or the clip's separate
    // centre test does the work and the lattice is still unmeasured. (Written
    // as a lagoon first — it passed with the lattice deleted, which is the same
    // dead-sensor shape this arm exists to close.)
    const moat = (x: number, y: number) => {
      const d = Math.hypot(x - 1000, y - 1000)
      return d < 40 || (d > 120 && d < 300)
    }
    expect(moat(1000, 1000)).toBe(true) // centre: land
    // the rim at r=200 is entirely on land, so a rim-only clip keeps it whole
    for (let i = 0; i < 90; i++) {
      const a = (i * Math.PI * 2) / 90
      expect(moat(1000 + Math.cos(a) * 200, 1000 + Math.sin(a) * 200)).toBe(true)
    }
    const clipped = clipBlobToLand({ c: { x: 1000, y: 1000 }, rx: 200, ry: 200 }, moat)
    // ...and the clip must not: the ring of water at 40<d<120 is inside it, so
    // the blob is shrunk back inside the keep rather than painted over the moat
    expect(clipped).not.toBeNull()
    expect(clipped!.rx).toBeLessThan(40)
    // measured independently of the clip's own probe, as the extent arms are
    for (const p of blobExtentSamples(clipped!)) expect(moat(p.x, p.y)).toBe(true)
    // the same blob on solid ground survives untouched, so the null is the
    // interior probe and not an unrelated refusal
    expect(clipBlobToLand({ c: { x: 1000, y: 1000 }, rx: 200, ry: 200 }, () => true)).toEqual({
      c: { x: 1000, y: 1000 },
      rx: 200,
      ry: 200,
    })
    // and a blob with no land at all under it is DROPPED, so the shrink is not
    // the only outcome this function has
    expect(clipBlobToLand({ c: { x: 1000, y: 1000 }, rx: 200, ry: 200 }, () => false)).toBeNull()
  })

  it('a lane with NO on-land run is dropped, not emitted empty', () => {
    // lanes.ts states it; nothing measured it. Reachable through the public
    // radii option: measured 448 lane drops across the island sizes this suite
    // already composes, and the drive gate below reads the surviving key set —
    // so a lane kept as an empty husk would put a drive on a road that is not
    // there, which is the defect the era gate exists for.
    const eastOnly = (x: number, _y: number) => x > 1300
    const lanes = buildLanes('gravel_road', eastOnly, demand(FULL_NETWORK))
    expect(lanes.length).toBeGreaterThan(0) // not vacuous
    expect(lanes.map((l) => l.key)).not.toContain('west')
    expect(lanes.map((l) => l.key)).not.toContain('coastal')
    for (const lane of lanes) {
      expect(lane.runs.length).toBeGreaterThan(0)
      for (const p of lane.runs.flat()) expect(eastOnly(p.x, p.y)).toBe(true)
    }
    // and with land everywhere the whole network survives, so the drop is the
    // land test rather than the era gate doing it
    expect(buildLanes('gravel_road', () => true, demand(FULL_NETWORK))).toHaveLength(LANE_SPECS.length)
  })

  it('a drive with no on-land run is not emitted either', () => {
    // index.ts states it; nothing measured it. On a small island the officer
    // row's drives run off the shore — measured 293 unemitted drives across the
    // island sizes above. A Driveway with no painted run is a record of paint
    // that does not exist.
    const full = composeLayout(VILLAGE, 'acme-corp', FAST)
    expect(full.driveways).toHaveLength(9)
    let dropped = 0
    for (const hw of [560, 460, 360]) {
      for (const seed of ['acme-corp', 'zeta', 'org-3']) {
        const l = composeLayout(VILLAGE, seed, {
          coastline: { step: 8, radii: { hw, vh: Math.round((hw * 784) / 962) } },
        })
        dropped += 9 - l.driveways.length
        // every drive that IS emitted has a run, and every sample is on land
        for (const lane of l.lanes.filter((x) => x.kind === 'driveway')) {
          expect(lane.runs.length).toBeGreaterThan(0)
          for (const p of lane.runs.flat()) expect(l.coast.landAt(p.x, p.y)).toBe(true)
        }
      }
    }
    expect(dropped).toBeGreaterThan(0)
  })

  it('the water audit measures SCATTER too, not only structures', () => {
    // The negative twin for the water audit injected a structure and never a
    // scatter item, so blanking the scatter half left every arm green. Each
    // half is probed by its own rule's convention — structures at y-2 (the
    // reference's, for a base sitting on the waterline row), scatter at y —
    // and both halves therefore need their own proof.
    const sea = { x: 60, y: 60 }
    expect(hamlet.coast.landAt(sea.x, sea.y)).toBe(false)
    const drowned = {
      ...hamlet,
      structures: [],
      scatter: [{ kind: 'tree_oak', at: sea, flip: false, size: { w: 150, h: 150 } }],
    }
    expect(auditLayout(drowned).inWater).toEqual([{ kind: 'tree_oak', at: sea }])
    // and a scatter item on land is not reported, so it is the water test
    const dry = {
      ...hamlet,
      structures: [],
      scatter: [{ kind: 'tree_oak', at: { x: 1200, y: 800 }, flip: false, size: { w: 150, h: 150 } }],
    }
    expect(hamlet.coast.landAt(1200, 800)).toBe(true)
    expect(auditLayout(dry).inWater).toEqual([])
  })
})

// ── purity ─────────────────────────────────────────────────────────────────

describe('purity', () => {
  it('composeLayout does not mutate the state it was given', () => {
    const state: LayoutState = { era: 'hamlet', road: 'dirt_worn', stages: {}, counts: {} }
    const before = JSON.stringify(state)
    composeLayout(state, 'x', FAST)
    expect(JSON.stringify(state)).toBe(before)
  })

  it('lotsAlong does not mutate the separation book it reads', () => {
    const book = [...CIVIC_ANCHORS]
    const copy = JSON.stringify(book)
    lotsAlong(LOT_LANES.west, 3, () => true, book, { side: -1 })
    expect(JSON.stringify(book)).toBe(copy)
  })
})
