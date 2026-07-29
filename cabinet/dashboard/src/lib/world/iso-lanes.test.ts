/**
 * ISO LANE SITES — the archipelago the isometric world did not have.
 *
 * WHAT THESE ARMS ARE FOR. The product lanes were UNREACHABLE under iso for the
 * whole of the default flip: nothing drew them and `pickIso` could not return
 * `kind:'lane'`, so five lanes and the why-strings that cite `outcomes.yml`
 * were invisible while the suite over the world stayed green. A test that only
 * asserted "isoLaneSites returns five things" would have been green on a
 * version that piled all five on top of the great house, so every arm below is
 * about a PROPERTY a reader would notice being wrong: where they are relative
 * to the island, which way each one lies, how big it is for its rung, and
 * whether the pointer and the pen agree.
 *
 * THE GEOMETRY IS RESTATED HERE, NEVER IMPORTED. `ISO_GROUND_SQUASH` is written
 * as the literal 0.5 and the ellipse test is spelt out, because a test that
 * imports the function it is checking against can only prove the module is
 * self-consistent. The one thing that IS imported is the authored fan data
 * (`ISLE_SLOTS`, `QUAY_CENTER`) — that is the law being ported, not the port.
 *
 * Every arm was proven able to fail; the mutations are recorded in the landing
 * commit.
 */
import { describe, expect, it } from 'vitest'
import {
  BUOY_RED,
  homeExtentOf,
  homeHalfWidth,
  isoLaneFanRadius,
  isoLaneSites,
  isoQuayMouth,
  laneBearing,
  laneGroundHw,
  pickIsoLane,
  pointInLaneSite,
  ISO_GROUND_SQUASH,
  LANE_FAN_CLEARANCE,
  type HomeExtent,
} from './iso-lanes'
import { composeLayout, LAYOUT_SPACE, type Layout, type LayoutState } from './iso-layout'
import {
  buildWorldGeo,
  ISLE_SLOTS,
  MAIN_ISLAND_R_CAP,
  QUAY_CENTER,
  type LaneSite,
} from './world-geo'
import type { LaneRecord } from './era-engine'

/** The 2:1 ground plane, as a LITERAL — see the header. */
const SQUASH = 0.5

const SEED = 'cabinet-iso-lanes'

function layoutFor(over: Partial<LayoutState> = {}, opts = {}): Layout {
  const state: LayoutState = {
    era: 'hamlet',
    road: 'gravel_road',
    stages: {
      great_house: 'great_house',
      officer_dwellings: 'dwellings_4',
      lighthouse: 'tower_full',
      quay: 'timber_jetty',
      berths: 'berths_7plus',
      warehouse: 'warehouse',
      ...(over.stages ?? {}),
    },
    counts: { berths: 7, officer_dwellings: 4, ...(over.counts ?? {}) },
    ...over,
  }
  return composeLayout(state, SEED, { space: LAYOUT_SPACE, ...opts })
}

function rec(over: Partial<LaneRecord> = {}): LaneRecord {
  return { ever: 0, active: 0, achieved: 0, retired: 0, instanceTest: false, ...over }
}

/** The five sites the engine's own fold produces for a live-shaped cabinet:
 * one isle at ring r1, one instance-test reef, one un-ratified reef, two mist. */
function laneSites(): LaneSite[] {
  return buildWorldGeo({
    orgEventsTotal: 900,
    lanes: {
      alpha: rec({ ever: 2, active: 1, achieved: 1 }),
      beta: rec({ instanceTest: true }),
    },
    berths: ['alpha', 'beta', 'gamma', null, null],
    probeWiredLanes: ['alpha'],
  }).laneSites
}

const LAYOUT = layoutFor()
const HOME = homeExtentOf(LAYOUT)
const SITES = isoLaneSites(laneSites(), LAYOUT_SPACE, HOME)

// ── 1. WHERE THEY ARE: open water, never on the island ──────────────────────

describe('the fan is sited in open water, measured off the island itself', () => {
  it('every lane site is outside everything the home island owns', () => {
    expect(SITES).toHaveLength(ISLE_SLOTS.length)
    for (const s of SITES) {
      const insideBox =
        s.x >= HOME.x0 && s.x <= HOME.x1 && s.y >= HOME.y0 && s.y <= HOME.y1
      expect(insideBox, `slot ${s.slot} at ${s.x},${s.y} is inside the home extent`).toBe(false)
    }
  })

  it('the seaward slot clears the harbour by the stated margin, not by luck', () => {
    // Slot 3 points straight out of the harbour (bearing 90 degrees), so it is
    // the one the vertical term of the radius exists for. Its own ground must
    // begin below everything the island owns, plus the clearance.
    const seaward = SITES.find((s) => s.slot === 3)!
    const top = seaward.y - seaward.hw * SQUASH
    expect(top).toBeGreaterThanOrEqual(HOME.y1 + LANE_FAN_CLEARANCE - 1e-6)
  })

  it('a deeper harbour pushes its own archipelago further out', () => {
    // The mooring rows walk further seaward per pair of open outcome windows,
    // so a busy harbour out-reaches its island. If the fan were sited on the
    // coastline alone this would not move — and a reef buoy would end up among
    // the moorings on exactly the deployments with the most to show.
    const quiet = layoutFor({ stages: { berths: 'berth_1' }, counts: { berths: 1 } })
    const busy = layoutFor({ stages: { berths: 'berths_7plus' }, counts: { berths: 40 } })
    const rQuiet = isoLaneFanRadius(LAYOUT_SPACE, homeExtentOf(quiet))
    const rBusy = isoLaneFanRadius(LAYOUT_SPACE, homeExtentOf(busy))
    expect(homeExtentOf(busy).y1).toBeGreaterThan(homeExtentOf(quiet).y1)
    expect(rBusy).toBeGreaterThan(rQuiet)
  })

  it('the reach is MEASURED off the coastline, not read from its default constant', () => {
    // composeLayout takes a coastline radii override. A homeExtentOf that read
    // ISLAND_RADII would return the same box for both islands, and would site
    // the archipelago against an island the caller had already changed.
    const small = layoutFor({}, { coastline: { radii: { hw: 400, vh: 320 } } })
    const smallHome = homeExtentOf(small)
    expect(homeHalfWidth(LAYOUT_SPACE, smallHome)).toBeLessThan(
      homeHalfWidth(LAYOUT_SPACE, HOME)
    )
  })
})

// ── 2. WHICH WAY: the authored bearings survive the kernel change ───────────

describe('the authored fan bearings are preserved', () => {
  it.each(ISLE_SLOTS.map((s) => [s.slot, s] as const))(
    'slot %i lies on its ISLE_SLOTS bearing from the island centre',
    (slot, isle) => {
      const s = SITES.find((x) => x.slot === slot)!
      // Un-squash the ground plane and the point's bearing IS the fan bearing.
      const got = Math.atan2((s.y - LAYOUT_SPACE.cy) / SQUASH, s.x - LAYOUT_SPACE.cx)
      const want = Math.atan2(isle.cy - QUAY_CENTER.y, isle.cx - QUAY_CENTER.x)
      expect(got).toBeCloseTo(want, 9)
      expect(laneBearing(isle)).toBeCloseTo(want, 12)
    }
  )

  it('the ring is a 2:1 ellipse on the ground, not a circle in the air', () => {
    const R = isoLaneFanRadius(LAYOUT_SPACE, HOME)
    for (const s of SITES) {
      const u = (s.x - LAYOUT_SPACE.cx) / R
      const v = (s.y - LAYOUT_SPACE.cy) / (R * SQUASH)
      expect(u * u + v * v, `slot ${s.slot} is off the ring`).toBeCloseTo(1, 9)
    }
    // and the squash is the projection kernel's own 2:1, not a taste
    expect(ISO_GROUND_SQUASH).toBe(SQUASH)
  })

  it('sites join their slot by NUMBER, so a reordered fold cannot rotate the world', () => {
    const shuffled = [...laneSites()].reverse()
    expect(isoLaneSites(shuffled, LAYOUT_SPACE, HOME)).toEqual(SITES)
  })
})

// ── 3. HOW BIG: rung measures it, in both kernels ───────────────────────────

describe('an isle is the same fraction of home in both kernels', () => {
  it('ring r1 is exactly twice ring r0, because isleRadius says 10 against 5', () => {
    const hw = homeHalfWidth(LAYOUT_SPACE, HOME)
    expect(laneGroundHw('isle', 2, hw)).toBeCloseTo(2 * laneGroundHw('isle', 1, hw), 9)
    expect(laneGroundHw('isle', 1, hw)).toBeCloseTo((hw * 5) / MAIN_ISLAND_R_CAP, 9)
  })

  it('a reef buoy and a mist pocket have NO land — their mark is the hit size', () => {
    const hw = homeHalfWidth(LAYOUT_SPACE, HOME)
    expect(laneGroundHw('reef_buoy', 0, hw)).toBe(laneGroundHw('mist_reserved', 0, hw))
    // …and it is not an isle's size: a marker must never read as earned land
    expect(laneGroundHw('reef_buoy', 0, hw)).toBeLessThan(laneGroundHw('isle', 1, hw))
  })

  it('an isle never out-grows the island it is a lane off', () => {
    const hw = homeHalfWidth(LAYOUT_SPACE, HOME)
    for (const s of SITES) expect(s.hw).toBeLessThan(hw)
  })

  it('only the rung and the island WIDTH size an isle — nothing about the sea does', () => {
    // ERA styles a thing, RUNG measures it. `isoLaneSites` takes no era at all,
    // and the arm that proves it is not a tautology is this one: two islands of
    // the same width whose harbours reach very different depths push their fans
    // to different radii and still draw the SAME isle.
    const shallow: HomeExtent = { x0: 400, y0: 100, x1: 2000, y1: 1200 }
    const deep: HomeExtent = { ...shallow, y1: 1900 }
    const a = isoLaneSites(laneSites(), LAYOUT_SPACE, shallow)
    const b = isoLaneSites(laneSites(), LAYOUT_SPACE, deep)
    expect(isoLaneFanRadius(LAYOUT_SPACE, deep)).toBeGreaterThan(
      isoLaneFanRadius(LAYOUT_SPACE, shallow)
    )
    expect(b.map((s) => s.hw)).toEqual(a.map((s) => s.hw))
    expect(b.map((s) => s.y)).not.toEqual(a.map((s) => s.y))
  })
})

// ── 4. THE CARD IS THE ENGINE'S OWN WHY-STRING, carried not rewritten ───────

describe('what the site says about itself', () => {
  it('lane, render, ring and why come through verbatim from buildWorldGeo', () => {
    const src = laneSites()
    for (const s of SITES) {
      const from = src.find((x) => x.slot === s.slot)!
      expect({ lane: s.lane, render: s.render, ringRung: s.ringRung, why: s.why }).toEqual({
        lane: from.lane,
        render: from.render,
        ringRung: from.ringRung,
        why: from.why,
      })
    }
  })

  it('the three renders are all present on a live-shaped cabinet', () => {
    expect(new Set(SITES.map((s) => s.render))).toEqual(
      new Set(['isle', 'reef_buoy', 'mist_reserved'])
    )
  })
})

// ── 5. THE POINTER AND THE PEN AGREE ────────────────────────────────────────

describe('the hit test is the geometry that was drawn', () => {
  it('the anchor of every site is a hit', () => {
    for (const s of SITES) expect(pickIsoLane(SITES, s.x, s.y)?.slot).toBe(s.slot)
  })

  it('just outside the hit ellipse is NOT a hit, on both axes', () => {
    for (const s of SITES) {
      expect(pointInLaneSite(s, s.x + s.pickHw * 1.02, s.y)).toBe(false)
      expect(pointInLaneSite(s, s.x, s.y + s.pickHw * SQUASH * 1.02)).toBe(false)
      // …and just INSIDE is, so the arm above is not passing on a broken test
      expect(pointInLaneSite(s, s.x + s.pickHw * 0.98, s.y)).toBe(true)
      expect(pointInLaneSite(s, s.x, s.y + s.pickHw * SQUASH * 0.98)).toBe(true)
    }
  })

  it('the hit ellipse is squashed like the ground, not round', () => {
    // A round hit area would answer a point a full pickHw below the anchor.
    for (const s of SITES) expect(pointInLaneSite(s, s.x, s.y + s.pickHw * 0.9)).toBe(false)
  })

  it('an isle is easier to hit than its own land is big — it is clicked far away', () => {
    for (const s of SITES.filter((x) => x.render === 'isle')) {
      expect(s.pickHw).toBeGreaterThan(s.hw)
    }
  })

  it('overlapping hit areas resolve to the NEAREST, never to the first in order', () => {
    // Two sites forced onto the same water: the pointer must get the one it is
    // sitting on. `first wins` would make one of them permanently unreachable.
    const a = { ...SITES[0], slot: 1, x: 0, y: 0, pickHw: 400 }
    const b = { ...SITES[1], slot: 2, x: 300, y: 0, pickHw: 400 }
    expect(pickIsoLane([a, b], 280, 0)?.slot).toBe(2)
    expect(pickIsoLane([a, b], 20, 0)?.slot).toBe(1)
    expect(pickIsoLane([b, a], 20, 0)?.slot).toBe(1)
  })

  it('open sea answers nothing', () => {
    expect(pickIsoLane(SITES, LAYOUT_SPACE.cx, LAYOUT_SPACE.cy)).toBeNull()
    expect(pickIsoLane(SITES, -99999, -99999)).toBeNull()
  })
})

// ── 6. THE DEGENERATE ENDS ──────────────────────────────────────────────────

describe('the degenerate ends are honest, not lucky', () => {
  it('no lane sites at all ⇒ no archipelago, and no throw', () => {
    expect(isoLaneSites([], LAYOUT_SPACE, HOME)).toEqual([])
    expect(pickIsoLane([], 0, 0)).toBeNull()
  })

  it('a partial fold places only the slots it was given', () => {
    const one = laneSites().filter((s) => s.slot === 4)
    const got = isoLaneSites(one, LAYOUT_SPACE, HOME)
    expect(got.map((s) => s.slot)).toEqual([4])
  })

  it('a slot number no ISLE_SLOT carries is dropped, never placed at a default', () => {
    const bogus: LaneSite[] = [
      { ...laneSites()[0], slot: 99 },
    ]
    expect(isoLaneSites(bogus, LAYOUT_SPACE, HOME)).toEqual([])
  })

  it('a zero-size hit area can never be hit', () => {
    const dead = { ...SITES[0], pickHw: 0 }
    expect(pointInLaneSite(dead, dead.x, dead.y)).toBe(false)
    expect(pickIsoLane([dead], dead.x, dead.y)).toBeNull()
  })

  it('an island with no harbour still gets a fan, sited on its coastline', () => {
    const noCove = layoutFor({}, { coastline: { cove: null } })
    expect(noCove.harbour).toBeNull()
    const home = homeExtentOf(noCove)
    const sites = isoLaneSites(laneSites(), LAYOUT_SPACE, home)
    expect(sites).toHaveLength(ISLE_SLOTS.length)
    for (const s of sites) {
      expect(s.y - s.hw * SQUASH > home.y1 || s.x > home.x1 || s.x < home.x0).toBe(true)
    }
  })
})

// ── 7. WHERE A COURSE LEAVES FROM ───────────────────────────────────────────

describe('the course origin is the harbour mouth', () => {
  it('the pier end when there is a pier', () => {
    expect(LAYOUT.harbour?.jetty).toBeTruthy()
    expect(isoQuayMouth(LAYOUT, HOME)).toEqual({
      x: LAYOUT.harbour!.jetty!.end.x,
      y: LAYOUT.harbour!.jetty!.end.y,
    })
  })

  it('the cove when the quay rung has built no pier — never the island centre', () => {
    const noPier = layoutFor({ stages: { quay: 'none' } })
    expect(noPier.harbour?.jetty ?? null).toBeNull()
    const at = isoQuayMouth(noPier, homeExtentOf(noPier))
    expect(at).toEqual({ x: noPier.harbour!.cove.x, y: noPier.harbour!.cove.y })
    expect(at.y).toBeGreaterThan(LAYOUT_SPACE.cy)
  })

  it('an island with no cove at all falls back to its own seaward point', () => {
    const noCove = layoutFor({}, { coastline: { cove: null } })
    const home = homeExtentOf(noCove)
    expect(isoQuayMouth(noCove, home)).toEqual({ x: LAYOUT_SPACE.cx, y: home.y1 })
  })
})

// ── 8. THE PALETTE THE MARK IS DRAWN IN ─────────────────────────────────────

describe('the buoy red is the pack atlas own', () => {
  it('is the colour sampled from the shipped buoy frame, not a chosen red', () => {
    // atlas-0.png, `buoy` frame at (210,903) 77x92 — (198,85,63). The palette
    // gate is fitted on that atlas, so a red picked by eye is foreign mass by
    // construction. Pinned as a number so a re-pick is a visible diff.
    expect(BUOY_RED).toBe((198 << 16) | (85 << 8) | 63)
    // and explicitly NOT the top-down kernel's own buoy red
    expect(BUOY_RED).not.toBe(0xc63228)
  })
})

// ── 9. THE CLEARANCE IS A MARGIN, NOT A RADIUS ──────────────────────────────

describe('the radius is derived, so a bigger island pushes its own fan out', () => {
  it('a wider island gets a wider fan', () => {
    const wide = homeExtentOf(layoutFor({}, { coastline: { radii: { hw: 1150, vh: 900 } } }))
    const narrow = homeExtentOf(layoutFor({}, { coastline: { radii: { hw: 500, vh: 400 } } }))
    expect(isoLaneFanRadius(LAYOUT_SPACE, wide)).toBeGreaterThan(
      isoLaneFanRadius(LAYOUT_SPACE, narrow)
    )
  })

  it('the clearance enters BOTH terms of the radius', () => {
    // TWO FIXTURES, and that is the whole point of the arm. The radius is the
    // max of a horizontal and a vertical term, so a single island tests only
    // whichever one happens to win — measured 2026-07-29, the first version of
    // this arm used a tall island, the vertical term covered the bound on its
    // own, and dropping the clearance from the HORIZONTAL term came back GREEN.
    // A bound another term already satisfies is not a sensor.
    const wide: HomeExtent = { x0: 100, y0: 400, x1: 2300, y1: 800 } // across wins
    const deep: HomeExtent = { x0: 900, y0: 400, x1: 1500, y1: 1700 } // down wins
    for (const [label, home] of [['wide', wide], ['deep', deep]] as const) {
      const r = isoLaneFanRadius(LAYOUT_SPACE, home)
      const hw = homeHalfWidth(LAYOUT_SPACE, home)
      const isle = laneGroundHw('isle', 2, hw)
      expect(r, `${label}: across`).toBeGreaterThanOrEqual(hw + isle + LANE_FAN_CLEARANCE - 1e-9)
      expect(r * ISO_GROUND_SQUASH, `${label}: down`).toBeGreaterThanOrEqual(
        home.y1 - LAYOUT_SPACE.cy + isle * ISO_GROUND_SQUASH + LANE_FAN_CLEARANCE - 1e-9
      )
    }
  })
})
