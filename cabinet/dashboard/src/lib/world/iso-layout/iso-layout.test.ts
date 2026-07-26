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
import {
  auditLayout,
  buildCoastline,
  buildLaneField,
  buildLanes,
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
  LAYOUT_SPACE,
  laneWidth,
  LOT_LANES,
  LOT_SEPARATION,
  lotsAlong,
  lotFor,
  placeOnGround,
  poissonScatter,
  polyPoint,
  rasterDims,
  wildnessField,
  type Layout,
  type LayoutState,
  type Point,
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

const hamlet = composeLayout(HAMLET, 'acme-corp', FAST)
const camp = composeLayout(CAMP, 'acme-corp', FAST)

function sizeOfItem(kind: string) {
  return DEFAULT_FOOTPRINTS[kind] ?? { w: 96, h: 96 }
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

describe('lanes — the road is a rung, and the era gates the network', () => {
  it('a camp has exactly ONE lane, and it runs to the water', () => {
    const campCarriageways = camp.lanes.filter((l) => l.kind !== 'driveway')
    expect(campCarriageways).toHaveLength(1)
    expect(campCarriageways[0].key).toBe('main')
    const end = campCarriageways[0].path[campCarriageways[0].path.length - 1]
    // it ends south of the village square, heading for the harbour
    expect(end.y).toBeGreaterThan(1300)
  })

  it('a hamlet has the network', () => {
    const village = hamlet.lanes.filter((l) => l.kind !== 'driveway')
    expect(village.length).toBe(LANE_SPECS.length)
    expect(village.length).toBeGreaterThan(5)
  })

  it('the road RUNG sets the width, monotonically', () => {
    const widths = (['dirt_path', 'dirt_worn', 'gravel_road', 'cobbled_road'] as const).map((r) =>
      laneWidth(62, r)
    )
    for (let i = 1; i < widths.length; i++) expect(widths[i]).toBeGreaterThan(widths[i - 1])
    expect(drivewayWidth('cobbled_road')).toBeGreaterThan(drivewayWidth('dirt_path'))
  })

  it('era changes the network, rung changes only its width', () => {
    const dirt = buildLanes('hamlet', 'dirt_path')
    const cobble = buildLanes('hamlet', 'cobbled_road')
    expect(dirt.map((l) => l.key)).toEqual(cobble.map((l) => l.key))
    expect(dirt.map((l) => l.path)).toEqual(cobble.map((l) => l.path))
    expect(cobble[0].width).toBeGreaterThan(dirt[0].width)
  })

  it('the lane field answers on/off the carriageway', () => {
    const field = buildLaneField(buildLanes('hamlet', 'cobbled_road'))
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
      const mid = d.path[Math.floor(d.path.length / 2)]
      expect(field.onLane(mid.x, mid.y)).toBe(true)
    }
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
      { key: 't', kind: 'main', width: 40, path: [{ x: 1000, y: 900 }, { x: 1200, y: 900 }] },
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
    const onStreet = { x: hamlet.lanes[0].path[2].x, y: hamlet.lanes[0].path[2].y }
    expect(footprintOnLane(onStreet, { w: 150, h: 150 }, field)).toBe(true)
  })

  it('clearing the road never lands a thing on another thing', () => {
    const field = buildLaneField(hamlet.lanes)
    const onStreet = { x: hamlet.lanes[0].path[2].x, y: hamlet.lanes[0].path[2].y }
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
  const field = buildLaneField(buildLanes('hamlet', 'gravel_road'))
  const districts = [
    { at: { x: 1200, y: 1010 }, r: 300 },
    { at: { x: 1200, y: 800 }, r: 250 },
  ]
  const wildness = wildnessField(
    { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy },
    (a) => coast.landEdge(a),
    districts,
    field
  )

  it('the density FIELD is higher at the treeline than in the village', () => {
    const edge = coast.landEdge(-Math.PI / 2)
    const treeline = { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy - (edge - 60) * 0.92 }
    const village = { x: 1200, y: 1010 }
    expect(wildness(treeline.x, treeline.y)).toBeGreaterThan(wildness(village.x, village.y) + 0.3)
  })

  it('the density field is ZERO on a lane and in the village core', () => {
    expect(wildness(1200, 1010)).toBe(0)
    const onMain = buildLanes('hamlet', 'gravel_road')[0].path[2]
    expect(wildness(onMain.x, onMain.y)).toBe(0)
  })

  it('REALIZED planting is denser at the treeline than in the meadow', () => {
    // The property that matters is not the field, it is the points the field
    // produced. Counting points per ANNULUS would measure the wrong thing: the
    // plantable region is bounded by the same `isInner` predicate the pass
    // used, so the two bands have areas nothing analytic can give. Measure
    // both areas by seeded Monte Carlo through THAT predicate, then compare
    // points per unit plantable area.
    const items = hamlet.scatter
    expect(items.length).toBeGreaterThan(30)
    const c = { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy }
    const radialFraction = (p: Point) => {
      const ang = Math.atan2((p.y - c.y) / 0.92, p.x - c.x)
      const d = Math.hypot(p.x - c.x, (p.y - c.y) / 0.92)
      return d / hamlet.coast.landEdge(ang)
    }
    const SPLIT = 0.55
    let areaOuter = 0
    let areaInner = 0
    const rng = seededRng(0xc0ffee)
    for (let i = 0; i < 40000; i++) {
      const x = rng() * LAYOUT_SPACE.w
      const y = rng() * LAYOUT_SPACE.h
      if (!hamlet.coast.landAt(x, y) || !hamlet.coast.isInner(x, y)) continue
      if (radialFraction({ x, y }) > SPLIT) areaOuter++
      else areaInner++
    }
    expect(areaOuter).toBeGreaterThan(500)
    expect(areaInner).toBeGreaterThan(500)
    let nOuter = 0
    let nInner = 0
    for (const it of items) (radialFraction(it.at) > SPLIT ? nOuter++ : nInner++)
    // measured 0.0184 vs 0.0097 per unit area: the treeline band carries
    // roughly twice the planting of the village side, which is the ecotope the
    // density field exists to produce
    expect(nOuter / areaOuter).toBeGreaterThan((nInner / areaInner) * 1.3)
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
  it('a camp has no plaza, no market and no field plots', () => {
    expect(camp.paint.map((p) => p.kind)).not.toContain('plaza')
    expect(camp.structures.map((s) => s.kind)).not.toContain('market_stall')
    expect(camp.paint.map((p) => p.kind)).not.toContain('ploughed')
  })

  it('a hamlet has them', () => {
    expect(hamlet.paint.map((p) => p.kind)).toContain('plaza')
    expect(hamlet.structures.map((s) => s.kind)).toContain('market_stall')
    expect(hamlet.paint.map((p) => p.kind)).toContain('ploughed')
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
      expect(l.structures.filter((s) => s.kind === 'officer_dwelling')).toHaveLength(n)
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
    const pondOf = (n: number) =>
      composeLayout(
        { ...HAMLET, counts: { officer_dwellings: 3, field_plots: n } },
        'acme-corp',
        FAST
      ).paint.find((p) => p.kind === 'pond')
    const bare = pondOf(0)
    const farmed = pondOf(3)
    expect(bare).toBeDefined()
    expect(bare!.blobs.length).toBeGreaterThan(0)
    expect(farmed).toEqual(bare)
  })

  it('the pond is clipped to LAND — no puddle floating on the sea', () => {
    for (const seed of ['acme-corp', 'harbour', 'lantern']) {
      const l = composeLayout(HAMLET, seed, FAST)
      const pond = l.paint.find((p) => p.kind === 'pond')
      if (!pond) continue
      for (const b of pond.blobs) expect(l.coast.landAt(b.c.x, b.c.y)).toBe(true)
    }
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
    const anchor = east.path[Math.floor(east.path.length / 2)]
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
