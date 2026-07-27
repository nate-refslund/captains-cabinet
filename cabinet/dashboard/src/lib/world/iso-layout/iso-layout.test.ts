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
import { clipBlobToLand, snapInland, walkInland, waterField } from './index'
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

/** Seeds used wherever a property must hold for more than one island. */
const SEEDS = ['acme-corp', 'harbour', 'lantern', 'captains-cabinet', 'zeta']

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

describe('lanes — the road is a rung, and the era gates the network', () => {
  it('a camp has exactly ONE lane, and it runs to the water', () => {
    const campCarriageways = camp.lanes.filter((l) => l.kind !== 'driveway')
    expect(campCarriageways).toHaveLength(1)
    expect(campCarriageways[0].key).toBe('main')
    const runs = campCarriageways[0].runs
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
    const dirt = buildLanes('hamlet', 'dirt_path', LAND)
    const cobble = buildLanes('hamlet', 'cobbled_road', LAND)
    expect(dirt.map((l) => l.key)).toEqual(cobble.map((l) => l.key))
    expect(dirt.map((l) => l.runs)).toEqual(cobble.map((l) => l.runs))
    expect(cobble[0].width).toBeGreaterThan(dirt[0].width)
  })

  it('the lane field answers on/off the carriageway', () => {
    const field = buildLaneField(buildLanes('hamlet', 'cobbled_road', LAND))
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

  it('a camp gets NO drive — its dwelling fronts a road a camp does not have', () => {
    // A drive is drawn to the lot's `road` point, which comes from the
    // idealised lot-lane table and not from the network. At camp every district
    // carriageway is gone, so the drive used to run to a road that is not
    // there: measured, `drive-residential-0` ended at (709,802), on no lane.
    expect(camp.driveways).toHaveLength(0)
    expect(camp.lanes.filter((l) => l.kind === 'driveway')).toHaveLength(0)
  })

  it('...and the same state at HAMLET does get one — the gate is the era, not the count', () => {
    // the negative twin: without it, "no drive at camp" would be satisfied by a
    // build that never emits a drive for one dwelling at all
    const oneDwelling = composeLayout(
      { ...HAMLET, counts: { officer_dwellings: 1 } },
      'acme-corp',
      FAST
    )
    expect(oneDwelling.driveways.length).toBeGreaterThan(0)
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
      const c = composeLayout(CAMP, seed, FAST)
      expect(new Set(c.lanes.map((x) => x.key))).toEqual(new Set(['main']))
      expect(c.driveways).toHaveLength(0)
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
      { key: 't', kind: 'main', width: 40, runs: [[{ x: 1000, y: 900 }, { x: 1200, y: 900 }]] },
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
  const field = buildLaneField(buildLanes('hamlet', 'gravel_road', (x, y) => coast.landAt(x, y)))
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
    const onMain = buildLanes('hamlet', 'gravel_road', (x, y) => coast.landAt(x, y))[0].runs[0][2]
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
  it('a camp has no plaza and no market', () => {
    // NAMED FOR WHAT IT CAN DETECT. This arm used to claim "...and no field
    // plots" as well, and it could not fail for that reason: field plots are
    // gated on `counts.field_plots` alone and the CAMP fixture omits the count,
    // so the assertion passed on the fixture rather than on the code. The
    // property is asserted properly by the count arm below — which asserts the
    // opposite, because a measured field plot is a COUNT and era may never hide
    // one.
    expect(camp.paint.map((p) => p.kind)).not.toContain('plaza')
    expect(camp.structures.map((s) => s.kind)).not.toContain('market_stall')
  })

  it('a camp WITH measured field plots draws them — era may not hide a count', () => {
    const farmedCamp = composeLayout(
      { ...CAMP, counts: { officer_dwellings: 1, field_plots: 3 } },
      'acme-corp',
      FAST
    )
    expect(farmedCamp.paint.map((p) => p.kind)).toContain('ploughed')
    expect(farmedCamp.paint.filter((p) => p.kind !== 'pond')).toHaveLength(3)
    // and the fixture camp, which has no such count, draws none
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
      for (const d of l.districts) {
        expect(l.coast.landAt(d.at.x, d.at.y)).toBe(true)
      }
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
        // every measured building still exists — the rule moves things, it does
        // not quietly delete the org's districts
        expect(l.structures).toHaveLength(10)
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
        for (const d of l.districts) expect(l.coast.landAt(d.at.x, d.at.y)).toBe(true)
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
      structures: [{ kind: 'workshop', at: sea, flip: false, size: { w: 170, h: 170 } }],
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
    const cut = buildLaneField([{ key: 'c', kind: 'main', width: 40, runs: clipToLand(path, notInlet) }])
    const whole = buildLaneField([{ key: 'c', kind: 'main', width: 40, runs: [path] }])
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
  it('nothing is planted inside a district disc', () => {
    // Measured before the fix: 72-80% of every seed's planting stood inside a
    // disc, including a full-size oak 26px from the great house.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      expect(l.scatter.length).toBeGreaterThan(30) // not vacuous
      const inside = l.scatter.filter((s) => insideDisc(l, s.at))
      expect({ seed, inside: inside.map((s) => s.kind) }).toEqual({ seed, inside: [] })
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
      const onPaint = l.scatter.filter((s) =>
        insidePaint(l, ['plaza', 'crop', 'ploughed', 'pond'], s.at)
      )
      expect({ seed, onPaint: onPaint.map((s) => s.kind) }).toEqual({ seed, onPaint: [] })
    }
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
      const anchor = l.lots.centre[0].c
      const toAnchor = Math.min(
        ...l.scatter.map((s) => Math.hypot(s.at.x - anchor.x, (s.at.y - anchor.y) * 1.35))
      )
      expect(toAnchor).toBeGreaterThan(250) // its disc radius, in the disc metric
      const toHouse = Math.min(
        ...l.scatter.map((s) => Math.hypot(s.at.x - gh.at.x, s.at.y - gh.at.y))
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
