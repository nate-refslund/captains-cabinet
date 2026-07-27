/**
 * ISO-LAYOUT — composeLayout(state, seed): the whole ported LAYOUT stage, as
 * one pure seeded function returning plain data the renderer consumes.
 *
 * THE STAGE ORDER IS ITSELF A RULE (compose.py's docstring, "armature first"):
 *
 *   coastline -> lanes -> lots -> driveways -> ground paint -> structures -> scatter
 *
 * Every arrow is load-bearing and each one was learned the expensive way:
 *   - lanes need the coastline, because a lot whose setback lands in the sea
 *     has to be pulled in, and only the coastline knows that;
 *   - lots come from lanes, because hand-typed building anchors are what made
 *     everything downstream need hand-typed offsets too;
 *   - DRIVEWAYS MUST EXIST BEFORE THE GROUND IS PAINTED. A drive is paved
 *     surface and it is part of the lane occupancy field; paint it after and
 *     the clearance rules are testing against a road that is not all there;
 *   - structures before scatter, because scatter rejects at sampling time
 *     against occupied ground, and ground a house has not claimed yet is
 *     ground a tree will take (the reference records a tree claiming a house
 *     plot before the house existed, compose.py:907-909).
 *
 * ERA GATES CONTENT, NOT JUST SIZE. A camp has ONE worn track, no plaza, no
 * market, no verge dressing, no ambient village props. RUNG measures — the
 * road's width, how many dwellings — and era may never hide a count. Anything
 * emitted here that cannot be traced to a rule over `state` is a bug.
 *
 * PURE and SEEDED: no unseeded randomness, no wall-clock read, no IO, no
 * DOM — the world CI ratchet greps this tree for both. Same (state,
 * seed) gives a byte-identical layout forever. That determinism is what
 * replaces the layout_fold law this directory bends (see space.ts).
 */
import { fnv1a, seededRng } from '../hash'
import { buildCoastline, type Coastline, type CoastlineOptions } from './coastline'
import {
  footprintOnLane,
  groundTaken,
  placeOnGround,
  snapInland,
  type Footprint,
  type Occupant,
} from './clearance'
import { driveway, drivewayLane, type Driveway } from './driveways'
import {
  buildLaneField,
  buildLanes,
  GREAT,
  LOT_LANES,
  SQUARE,
  type Lane,
  type LaneField,
} from './lanes'
import { lotDoor, lotFlip, lotFor, lotsAlong, CIVIC_ANCHORS, type Lot } from './lots'
import {
  poissonScatter,
  wildnessField,
  type DensityField,
  type District,
  type ScatterItem,
} from './scatter'
import {
  clamp,
  eraAtLeast,
  LAYOUT_SPACE,
  type Era,
  type LayoutSpace,
  type Point,
  type RoadRung,
} from './space'

// ── the state the world is a function of ───────────────────────────────────

/**
 * The subset of the cabinet's replayed world state the LAYOUT needs. It is
 * read, never invented: `era` styles, `stages` says which rung an object is
 * on, `counts` says how many really exist. An unmeasured metric renders its
 * baseline, never an interpolation — which here means an absent count is 0 and
 * an absent stage is "not built", both of which draw nothing.
 */
export interface LayoutState {
  era: Era
  /** The road ladder's own rung — the network's width follows it. */
  road: RoadRung
  /** object -> rung, e.g. { library: 'stone_hall', workshop: 'none' }. */
  stages?: Readonly<Record<string, string | null | undefined>>
  /** object -> how many exist, e.g. { officer_dwellings: 3 }. */
  counts?: Readonly<Record<string, number | undefined>>
}

/** worldstate.py present(): rungs that mean "nothing is built here yet". */
const EMPTY_RUNGS = new Set([
  'none',
  'bare_ground',
  'bare_pole',
  'bare_wall',
  'empty_plinth',
  'dark',
  'dark_cairn',
])

/**
 * compose.py:26 — a handful of objects draw even at an empty rung, because the
 * empty rung IS the drawing (an unlit cairn is a lighthouse that has not been
 * earned, and showing nothing there would hide the fact).
 */
const ALWAYS_DRAWN = new Set(['veto_plinth', 'flagpole', 'firepit', 'lighthouse'])

export function isBuilt(state: LayoutState, obj: string): boolean {
  const stage = state.stages?.[obj]
  if (ALWAYS_DRAWN.has(obj)) return true
  if (stage === null || stage === undefined) return false
  return !EMPTY_RUNGS.has(stage)
}

export function countOf(state: LayoutState, obj: string): number {
  const v = state.counts?.[obj]
  return v === undefined || !Number.isFinite(v) ? 0 : Math.max(0, Math.trunc(v))
}

// ── footprints ─────────────────────────────────────────────────────────────

/**
 * DISPLAY sizes in layout px, measured from designs/world-mockup-v2 —
 * manifest.py's (generated w, generated h) divided by scale_of()'s integer
 * fraction, which is the size the compositor actually draws at.
 *
 * These are a DEFAULT, not the truth: the renderer must pass the shipped
 * pack's own sizes through `opts.footprintOf`, because the pack is what draws.
 * A layout computed against a stale size puts the ground diamond in the wrong
 * place, and a wrong ground diamond is how props end up on the road.
 */
export const DEFAULT_FOOTPRINTS: Readonly<Record<string, Footprint>> = {
  great_house: { w: 200, h: 200 },
  library: { w: 190, h: 190 },
  workshop: { w: 170, h: 170 },
  officer_dwelling: { w: 150, h: 150 },
  outbuildings: { w: 150, h: 150 },
  market_stall: { w: 150, h: 140 },
  well: { w: 140, h: 150 },
  firepit: { w: 130, h: 115 },
  tree_oak: { w: 150, h: 150 },
  tree_oak_small: { w: 55, h: 55 },
  tree_birch: { w: 150, h: 150 },
  tree_willow: { w: 150, h: 150 },
  bush_round: { w: 47, h: 47 },
  bush_flowering: { w: 47, h: 47 },
  fern_cluster: { w: 47, h: 47 },
  flowers_white: { w: 47, h: 45 },
  flowers_yellow: { w: 47, h: 45 },
  flowers_pink: { w: 47, h: 45 },
  rock_small: { w: 47, h: 45 },
  rock_cluster: { w: 47, h: 45 },
  mushrooms: { w: 47, h: 45 },
  tree_stump: { w: 47, h: 45 },
  fallen_log: { w: 47, h: 45 },
  reeds: { w: 47, h: 55 },
}

const FALLBACK_FOOTPRINT: Footprint = { w: 96, h: 96 }

// ── districts ──────────────────────────────────────────────────────────────

/**
 * compose.py:901-905 — the keep-out discs that stop scatter landing on a
 * district, and that suppress the wildness field around the village core.
 *
 * A DISC IS AN EXCLUSION, NOT A DENSITY HINT. compose.py:1211-1213 gates its
 * whole planting predicate on these discs — `free()` is false inside one, so
 * the reference plants exactly nothing there. Feeding them only to the wildness
 * field (which is what this port did until 2026-07-27) sets a local SPACING and
 * nothing more: at wildness 0 the exclusion radius is still rMax, so trees keep
 * arriving, just further apart. Measured on the old code, 72-80% of all planting
 * stood inside a disc, a full-size oak stood 26px from the great house, and
 * trees grew on the paved plaza and in the ploughed fields. The reference states
 * the intent at :899-901: "the enclosure ring is meant to frame the village,
 * not grow through it."
 *
 * ERA-GATED, unlike the reference. A keep-out disc is not drawn, but it is
 * VISIBLE: it makes a bald patch in the planting. Reserving the works ridge on
 * an island that has no works yet would put a mown circle around nothing,
 * which is precisely the "drawn but not traceable to a state rule" defect.
 */
const DISTRICT_ANCHORS: readonly { at: Point; r: number; villageOnly: boolean }[] = [
  { at: GREAT, r: 250, villageOnly: false },
  { at: SQUARE, r: 300, villageOnly: false },
  { at: { x: 1200, y: 400 }, r: 240, villageOnly: true },
  { at: { x: 1640, y: 512 }, r: 200, villageOnly: true },
  { at: { x: 1830, y: 800 }, r: 290, villageOnly: true },
  { at: { x: 1620, y: 1180 }, r: 300, villageOnly: true },
  { at: { x: 700, y: 690 }, r: 150, villageOnly: true },
  { at: { x: 612, y: 848 }, r: 150, villageOnly: true },
  { at: { x: 668, y: 1006 }, r: 150, villageOnly: true },
  { at: { x: 836, y: 760 }, r: 150, villageOnly: true },
  { at: { x: 790, y: 928 }, r: 150, villageOnly: true },
  { at: { x: 520, y: 700 }, r: 130, villageOnly: true },
  { at: { x: 760, y: 470 }, r: 210, villageOnly: true },
  { at: { x: 960, y: 372 }, r: 170, villageOnly: true },
  { at: { x: 840, y: 1226 }, r: 150, villageOnly: true },
  { at: { x: 612, y: 1086 }, r: 190, villageOnly: false }, // the pond: water, not doctrine
]

// ── ground paint ───────────────────────────────────────────────────────────

/** One painted blob — the renderer unions them into an organic region. */
export interface Blob {
  c: Point
  rx: number
  ry: number
}

/**
 * The regions this stage actually emits. `meadow_dark` was declared here and
 * never produced — the reference's broken-meadow pass (compose.py:143-150, 70
 * dark-grass blobs) is not ported — and a declared-but-unreachable member is a
 * promise to the renderer that nothing keeps. It comes back when the pass does.
 */
export type PaintKind = 'plaza' | 'ploughed' | 'crop' | 'pond'

export interface PaintRegion {
  kind: PaintKind
  blobs: Blob[]
}

/**
 * compose.py:366 — the tilled plots in the south-east, taken in order and
 * truncated to the number of field plots that really exist.
 */
const FIELD_PLOTS: readonly { c: Point; w: number; h: number; kind: PaintKind }[] = [
  { c: { x: 1548, y: 1218 }, w: 150, h: 74, kind: 'ploughed' },
  { c: { x: 1772, y: 1152 }, w: 138, h: 68, kind: 'crop' },
  { c: { x: 1650, y: 1332 }, w: 158, h: 70, kind: 'crop' },
  { c: { x: 1420, y: 1300 }, w: 120, h: 58, kind: 'ploughed' },
]

/** compose.py:154 — the inland pond, which gave the dead west meadow a reason. */
const POND: Point = { x: 612, y: 1086 }

// ── structures ─────────────────────────────────────────────────────────────

export interface Structure {
  kind: string
  /** Base centre, in layout space — the bottom vertex of its ground diamond. */
  at: Point
  /** Mirror so the door faces its lane. Sprites have one baked facing. */
  flip: boolean
  size: Footprint
  /** The lot it stands on, when it has one. */
  lot?: Lot
}

// ── the layout ─────────────────────────────────────────────────────────────

/**
 * A scattered prop, WITH the size the clearance rules used on it.
 *
 * The size is carried rather than re-derived because the caller may override
 * every footprint via `opts.footprintOf`; an audit that looked the size up in
 * DEFAULT_FOOTPRINTS would then be measuring a different world from the one
 * the rules built — the exact defect that had three placement rules and two
 * audits each carrying their own notion of where a sprite stands.
 */
export interface PlacedItem extends ScatterItem {
  size: Footprint
}

export interface Layout {
  space: LayoutSpace
  seed: number
  state: LayoutState
  coast: Coastline
  /** Carriageways AND drives — one surface, because one occupancy field. */
  lanes: Lane[]
  lots: Record<string, Lot[]>
  driveways: Driveway[]
  paint: PaintRegion[]
  structures: Structure[]
  scatter: PlacedItem[]
  /** Keep-out discs, exported so the renderer can debug-draw the field. */
  districts: District[]
}

export interface ComposeOptions {
  space?: LayoutSpace
  coastline?: CoastlineOptions
  /** The shipped pack's drawn size for a sprite kind. */
  footprintOf?: (kind: string) => Footprint | undefined
}

/** Nature that exists whether or not anyone lives here. */
const NATURE_TREES = ['tree_oak', 'tree_oak', 'tree_oak_small', 'tree_birch', 'tree_willow']
const NATURE_SHRUBS = ['bush_round', 'bush_flowering', 'fern_cluster']
const NATURE_FLOWERS = ['flowers_white', 'flowers_yellow', 'flowers_pink']
const NATURE_GROUND = ['rock_small', 'rock_cluster', 'tree_stump', 'fallen_log']
const SHORE_KINDS = ['reeds', 'rock_small', 'rock_cluster']
const VERGE_KINDS = ['flowers_white', 'flowers_yellow', 'bush_round', 'rock_small']

/**
 * Compose the whole layout for a world state.
 *
 * `seed` keys every seeded decision — coastline, plaza edge, planting. The
 * same org therefore always gets the same island, which is what makes a
 * computed lot centre as trustworthy as an authored one.
 */
export function composeLayout(
  state: LayoutState,
  seed: string | number,
  opts: ComposeOptions = {}
): Layout {
  const space = opts.space ?? LAYOUT_SPACE
  const numSeed = typeof seed === 'number' ? seed >>> 0 : fnv1a(seed)
  const camp = state.era === 'camp'
  const village = eraAtLeast(state.era, 'hamlet')
  const sizeOf = (kind: string): Footprint =>
    opts.footprintOf?.(kind) ?? DEFAULT_FOOTPRINTS[kind] ?? FALLBACK_FOOTPRINT

  // ---- 1. coastline -------------------------------------------------------
  const coast = buildCoastline(numSeed, space, opts.coastline)
  const onLand = (x: number, y: number) => coast.landAt(x, y)
  const inland: Point = { x: space.cx, y: space.cy }
  /** compose.py snap(): an anchor other things derive from must be on land. */
  const anchor = (p: Point): Point => snapInland(p, onLand, inland) ?? p

  // ---- 2. lanes -----------------------------------------------------------
  // CLIPPED TO LAND at birth (compose.py:343) — every later stage samples this
  // network, so a lane that ran into the sea would carry the sea with it into
  // the clearance rules, the verge pass and the audit.
  const carriageways = buildLanes(state.era, state.road, onLand)
  const laneKeys = new Set(carriageways.map((l) => l.key))

  // ---- 3. lots ------------------------------------------------------------
  // The separation book starts with the civic spots, which were never lane
  // derived and must still repel: a dwelling born on the well is a dwelling
  // nothing downstream can rescue.
  const book: Point[] = [...CIVIC_ANCHORS]
  const residential = [
    ...lotsAlong(LOT_LANES.west, 4, onLand, book, { side: -1, setback: 118, inlandTo: inland }),
  ]
  book.push(...residential.map((l) => l.c))
  const residentialInner = lotsAlong(LOT_LANES.west, 2, onLand, book, {
    side: 1,
    setback: 104,
    spread: [0.24, 0.7],
    inlandTo: inland,
  })
  book.push(...residentialInner.map((l) => l.c))

  // The doctrine anchors stay authoritative — snap() only pulls one inland when
  // THIS island has no ground under it, which is the case the reference wrote
  // it for (compose.py:873-875: "any change to the island's radius can strand
  // one offshore").
  const lots: Record<string, Lot[]> = {
    residential: [...residential, ...residentialInner],
    memory: [lotFor(anchor({ x: 1640, y: 512 }), LOT_LANES.ne)],
    works: [lotFor(anchor({ x: 1790, y: 800 }), LOT_LANES.east)],
    fields: [lotFor(anchor({ x: 1660, y: 1056 }), LOT_LANES.se)],
    centre: [lotFor(anchor(GREAT), LOT_LANES.main)],
  }

  /** Which carriageway each lot group fronts — a drive needs it to EXIST. */
  const LOT_GROUP_LANE: Readonly<Record<string, string>> = {
    residential: 'west',
    memory: 'ne',
    works: 'east',
    fields: 'se',
    centre: 'main',
  }

  // ---- 4. driveways -------------------------------------------------------
  // ONLY LOTS THAT WILL ACTUALLY BE BUILT GET A DRIVE — a path to empty grass
  // is a lie about what the org has.
  //
  // AND ONLY WHERE THE ROAD IT JOINS EXISTS. A lot's `road` point is sampled
  // from the IDEALISED lot lane, which is a table of control points and not the
  // network: at camp every district carriageway is gone, so a drive was still
  // being drawn from the one dwelling to a road that is not there — a gravel
  // stub ending in open grass. That is the same lie as a path to an unbuilt
  // plot, one level up. Measured before this gate: `composeLayout(CAMP,
  // dwellings: 1)` emitted `drive-residential-0` whose road end (709,802) lay
  // on no carriageway at all.
  const built: { key: string; obj: string; lot: Lot; group: string }[] = []
  const dwellings = Math.min(countOf(state, 'officer_dwellings'), lots.residential.length)
  for (let i = 0; i < dwellings; i++) {
    built.push({
      key: `residential-${i}`,
      obj: 'officer_dwelling',
      lot: lots.residential[i],
      group: 'residential',
    })
  }
  for (const [key, obj] of [
    ['memory', 'library'],
    ['works', 'workshop'],
    ['fields', 'outbuildings'],
  ] as const) {
    if (isBuilt(state, obj)) built.push({ key, obj, lot: lots[key][0], group: key })
  }

  const driveways: Driveway[] = []
  const driveLanes: Lane[] = []
  for (const b of built) {
    if (!laneKeys.has(LOT_GROUP_LANE[b.group])) continue
    const d = driveway(lotDoor(b.lot), b.lot.road, state.road)
    const lane = drivewayLane(d, `drive-${b.key}`, onLand)
    // a drive with no on-land run is a drive that was entirely offshore; the
    // record would then describe paint that does not exist
    if (lane.runs.length === 0) continue
    driveways.push(d)
    driveLanes.push(lane)
  }

  // Carriageways and drives are ONE surface from here on. Splitting them would
  // give the clearance rules a road they cannot see.
  const lanes: Lane[] = [...carriageways, ...driveLanes]
  const laneField: LaneField = buildLaneField(lanes)

  // ---- 5. ground paint regions -------------------------------------------
  const paint = paintRegions(state, numSeed, coast, village)

  // ---- 6. structures ------------------------------------------------------
  const occupied: Occupant[] = []
  const structures: Structure[] = []
  const put = (kind: string, at: Point, flip: boolean, lot?: Lot) => {
    const size = sizeOf(kind)
    // Structures are STRICT and are not dropped for being crowded: a measured
    // building that cannot find clear ground is a fact about the org, and
    // deleting it would be a lie of omission. Decoration is what gets dropped.
    //
    // THE ONE THING THAT DOES DELETE A STRUCTURE IS WATER. compose.py:530-539
    // walks a sprite inland and returns None when there is no ground within
    // reach, and null here means the building is not emitted — because the
    // alternative is a workshop standing in open sea, which is the one defect
    // a viewer sees instantly from any zoom. It is also reported: auditLayout's
    // water arm re-measures every emitted thing against the coastline.
    //
    // A structure WILL move off its compass anchor when its ground diamond
    // sits on a lane — the road wins, as it must, and the anchor's authority
    // is over which lot the building belongs to, not over the last hundred
    // pixels. The forecourt lane ends AT the great house's anchor, so the
    // great house is the routine case, not the exception.
    const p = placeOnGround(at, size, laneField, onLand, occupied, {
      strict: true,
      inlandTo: inland,
    })
    if (!p) return
    occupied.push({ at: p, size })
    structures.push({ kind, at: p, flip, size, lot })
  }

  if (isBuilt(state, 'great_house')) {
    put('great_house', lots.centre[0].c, lotFlip(lots.centre[0]), lots.centre[0])
  }
  if (isBuilt(state, 'well')) put('well', { x: 1050, y: 970 }, false)
  if (isBuilt(state, 'firepit')) put('firepit', SQUARE, false)
  if (village && isBuilt(state, 'market_stall')) put('market_stall', { x: 1386, y: 958 }, false)
  for (const b of built) put(b.obj, b.lot.c, lotFlip(b.lot), b.lot)

  // ---- 7. scatter ---------------------------------------------------------
  const districts: District[] = [
    ...DISTRICT_ANCHORS.filter((d) => village || !d.villageOnly).map((d) => ({
      // SNAPPED, like every other anchor: a disc centred in the sea reserves
      // sea, and the planting it was meant to keep out of the village then
      // arrives in the village.
      at: anchor(d.at),
      r: d.r,
    })),
    // the GENERATED lots, which is where buildings actually land
    ...Object.values(lots).flat().map((l) => ({ at: l.c, r: 150 })),
  ]
  const wildness = wildnessField(
    { x: space.cx, y: space.cy },
    // the MEMOISED edge: the field is sampled once per scatter candidate and
    // landEdge walks the raster in 6px steps (compose.py caches it the same
    // way, on the same 0.02-radian key)
    (ang) => coast.edgeAt(ang),
    districts,
    laneField
  )
  const scatter = plant(numSeed, {
    space,
    coast,
    laneField,
    occupied,
    districts,
    wildness,
    inWater: waterField(paint),
    onPaving: paintField(paint, ['plaza', 'crop', 'ploughed']),
    sizeOf,
    village,
    camp,
  })

  return {
    space,
    seed: numSeed,
    state,
    coast,
    lanes,
    lots,
    driveways,
    paint,
    structures,
    scatter,
    districts,
  }
}

// ── stage helpers ──────────────────────────────────────────────────────────

/**
 * EVERY PAINTED MASK IS CLIPPED TO LAND — compose.py clips all four
 * (`ImageChops.darker(m, landmask)`): paths :343, plaza :360, each field plot
 * :374, pond :171. This port clipped only the pond, and only by testing its
 * blob CENTRE, so ploughed soil and crop were painted onto open sea on most
 * seeds (measured: 38-189 of 468 field-blob samples over water across five
 * seeds; one seed had an entire crop plot offshore).
 *
 * A raster intersection keeps the on-land crescent of a blob. A blob here is an
 * ellipse, not pixels, so the honest equivalent is to SHRINK it until its whole
 * extent is on land and to DROP it when it cannot fit. Shrinking never paints
 * water and never invents a shape the reference would not have painted; it can
 * only paint less. The alternative — emitting the full ellipse and telling the
 * renderer to clip — puts the land rule in a stage that has no test around it,
 * which is how this defect got in.
 *
 * THE WHOLE ELLIPSE IS SAMPLED, not just its rim: a lattice at ~BLOB_PROBE_STEP
 * px plus the rim at the same arc spacing. Rim-only sampling has a hole in the
 * middle (a blob wide enough to straddle an inlet has water inside it its rim
 * never sees), and a fixed number of rim angles has holes between them that
 * grow with the blob — a 150px field plot probed at 24 angles skips 39px of arc
 * at a time, and the coastline mask is quantised to the sampling step, so the
 * gaps do not average out. The probe step is finer than the finest coastline
 * raster this library will build.
 */
const BLOB_PROBE_STEP = 5
const BLOB_MIN_RADIUS = 8

function blobOnLand(
  c: Point,
  rx: number,
  ry: number,
  onLand: (x: number, y: number) => boolean
): boolean {
  if (!onLand(c.x, c.y)) return false
  const n = Math.max(24, Math.ceil((2 * Math.PI * Math.max(rx, ry)) / BLOB_PROBE_STEP))
  for (let i = 0; i < n; i++) {
    const a = (i * Math.PI * 2) / n
    if (!onLand(c.x + Math.cos(a) * rx, c.y + Math.sin(a) * ry)) return false
  }
  const sx = Math.max(1, Math.ceil(rx / BLOB_PROBE_STEP))
  const sy = Math.max(1, Math.ceil(ry / BLOB_PROBE_STEP))
  for (let ix = -sx; ix <= sx; ix++) {
    for (let iy = -sy; iy <= sy; iy++) {
      const fx = ix / sx
      const fy = iy / sy
      if (fx * fx + fy * fy > 1) continue
      if (!onLand(c.x + fx * rx, c.y + fy * ry)) return false
    }
  }
  return true
}

/** The blob that fits on land, or null when even a shrunken one does not. */
export function clipBlobToLand(
  b: Blob,
  onLand: (x: number, y: number) => boolean
): Blob | null {
  let rx = b.rx
  let ry = b.ry
  for (let i = 0; i < 10; i++) {
    if (blobOnLand(b.c, rx, ry, onLand)) return { c: b.c, rx, ry }
    rx *= 0.82
    ry *= 0.82
    if (rx < BLOB_MIN_RADIUS || ry < BLOB_MIN_RADIUS) break
  }
  return null
}

/**
 * compose.py:176-177 in_water() — the pond is water, and nothing is planted in
 * water. Built from the painted pond region rather than from POND, so it is the
 * water that was actually emitted (clipped, possibly absent) and not the water
 * that was intended.
 */
export function waterField(paint: readonly PaintRegion[]): (x: number, y: number) => boolean {
  return paintField(paint, ['pond'])
}

/**
 * Is this point inside a painted region of one of these kinds?
 *
 * A PAVED SQUARE AND A TILLED PLOT ARE SURFACES, NOT SPACING HINTS — the same
 * argument the keep-out discs needed. Until 2026-07-27 nothing tested for them
 * at all: the property "no tree on the plaza, no reed in the crop" was carried
 * incidentally by whichever district disc happened to overlap the region, and
 * it LEAKED wherever one did not. Measured across 80 seeds with the discs
 * enforced: 9 shore-band items (reeds, rock_small, rock_cluster) standing in a
 * crop plot, all of them on the east plot's outer rim at x>=1900, which lies
 * outside every disc — and 2 of those survive at the production coastline step.
 * The arm named for the property ran five seeds and passed over all nine.
 *
 * It is the port's own term, not the reference's: compose.py can afford to
 * leave the plots to its KEEPOUT list because by planting time that list also
 * carries every fenced plot, hedgerow and outbuilding it drew over them, none
 * of which is ported. This layout emits the regions as data, so it can just say
 * so — and a claim in a test name has to be a rule somewhere or it is decoration.
 */
export function paintField(
  paint: readonly PaintRegion[],
  kinds: readonly PaintKind[]
): (x: number, y: number) => boolean {
  const blobs = paint.filter((r) => kinds.includes(r.kind)).flatMap((r) => r.blobs)
  if (blobs.length === 0) return () => false
  return (x, y) =>
    blobs.some((b) => ((x - b.c.x) / b.rx) ** 2 + ((y - b.c.y) / b.ry) ** 2 <= 1)
}

/** compose.py:355-376 — the plaza and the tilled plots, as seeded blob sets. */
function paintRegions(
  state: LayoutState,
  seed: number,
  coast: Coastline,
  village: boolean
): PaintRegion[] {
  // ONE STREAM PER REGION, not one stream for the file. A single shared
  // stream makes each region's shape depend on how many draws the regions
  // BEFORE it consumed — so gaining a field plot would silently reshape the
  // pond, and the pond is morphology: water does not wait for an org to grow.
  const streamFor = (tag: string) => seededRng(fnv1a(`${seed}:paint:${tag}`))
  const out: PaintRegion[] = []
  const onLand = (x: number, y: number) => coast.landAt(x, y)
  // Clip AFTER every draw, never instead of one: the rng stream must be
  // consumed in the reference's order whatever the coastline does, or a blob
  // that fell in the sea would reshape every blob after it.
  const keep = (kind: PaintKind, blobs: Blob[]) => {
    const clipped = blobs.map((b) => clipBlobToLand(b, onLand)).filter((b): b is Blob => b !== null)
    if (clipped.length > 0) out.push({ kind, blobs: clipped })
  }

  // The square is PAVED only once there is a village to gather in it. A camp
  // has trodden grass, which is the absence of this region, not a smaller one.
  if (village) {
    const rng = streamFor('plaza')
    const blobs: Blob[] = []
    for (let i = 0; i < 26; i++) {
      const a = rng() * Math.PI * 2
      const rr = Math.sqrt(rng())
      const r = 54 + rng() * 42
      blobs.push({
        c: { x: SQUARE.x + Math.cos(a) * rr * 124, y: SQUARE.y + Math.sin(a) * rr * 74 },
        rx: r,
        ry: r * 0.62,
      })
    }
    keep('plaza', blobs)
  }

  const plots = clamp(countOf(state, 'field_plots'), 0, FIELD_PLOTS.length)
  for (let i = 0; i < plots; i++) {
    const plot = FIELD_PLOTS[i]
    // per-plot stream: plot 1 looks the same whether or not plot 2 exists
    const rng = streamFor(`field-${i}`)
    const blobs: Blob[] = []
    for (let j = 0; j < 9; j++) {
      blobs.push({
        c: {
          x: plot.c.x + (rng() * 80 - 40),
          y: plot.c.y + (rng() * 36 - 18),
        },
        rx: plot.w,
        ry: plot.h,
      })
    }
    keep(plot.kind, blobs)
  }

  // The pond is morphology, not doctrine: it is there in every era, because
  // water does not wait for an org to grow — and its own stream is what makes
  // that literally true rather than merely intended.
  const rng = streamFor('pond')
  const pondBlobs: Blob[] = []
  for (let i = 0; i < 14; i++) {
    const a = rng() * Math.PI * 2
    const rr = Math.sqrt(rng())
    const r = 46 + rng() * 32
    const c = { x: POND.x + Math.cos(a) * rr * 74, y: POND.y + Math.sin(a) * rr * 38 }
    // compose.py:171 clips the pond mask against the land mask
    // (ImageChops.darker(pond_m, landmask_pre)) — an inland pond that bled
    // into the sea would read as a hole in the island. The seed decides where
    // the west meadow actually is, so on some islands the pond is smaller and
    // on some there is no room for one at all.
    //
    // ALONG ITS WHOLE EXTENT, not at its centre. Testing the centre alone was
    // the port's original clip and it is the shape of a dead sensor: the one
    // quantity the code checks is the one quantity a test of it can never fail
    // on. Measured on the old code, 11 of 26 pond samples on seed acme-corp and
    // 24 of 182 on seed lantern stood in open water while every blob centre was
    // on land.
    pondBlobs.push({ c, rx: r, ry: r * 0.58 })
  }
  keep('pond', pondBlobs)
  return out
}

interface PlantCtx {
  space: LayoutSpace
  coast: Coastline
  laneField: LaneField
  occupied: Occupant[]
  districts: District[]
  wildness: DensityField
  /** compose.py in_water(): the pond that was actually painted. */
  inWater: (x: number, y: number) => boolean
  /** The paved square and the tilled plots that were actually painted. */
  onPaving: (x: number, y: number) => boolean
  sizeOf: (kind: string) => Footprint
  village: boolean
  camp: boolean
}

/**
 * compose.py:1240-1263 — the six planting passes, in order. Each pass reads
 * the occupancy the previous ones wrote, so a bush cannot land inside a tree.
 */
function plant(seed: number, ctx: PlantCtx): PlacedItem[] {
  const out: PlacedItem[] = []
  /**
   * compose.py:1213 free(): `near_path(34) or in_water(x,y)` OR inside a
   * keep-out disc. All three terms are HARD — this is the predicate `inner()`,
   * `shore_band()` and the verge pass are each gated on, so the reference
   * plants nothing inside a district, nothing on a lane and nothing in the
   * pond. The disc term is the one this port lost; see DISTRICT_ANCHORS.
   *
   * The 1.35 vertical squash is the reference's and it is not decoration: a
   * disc on the ground projects flattened on a 2:1 screen, so a circular test
   * in screen space would reserve a tall oval nobody drew.
   *
   * HONEST NOTE ON THE WATER TERM: with today's constants it is REDUNDANT. The
   * pond sits inside its own 190px keep-out disc, so deleting `inWater` here
   * leaves every arm green — measured, not assumed. It is kept because the disc
   * is doctrine (a district reservation, era-gated, movable) while the water is
   * morphology, and because it is the reference's own rule; the test suite pins
   * the dependency with an arm asserting the pond's disc still covers the pond,
   * so the day the two part company the suite says so instead of the planting
   * quietly arriving in the water.
   *
   * THE PAVING TERM IS NOT REDUNDANT, which is how it was found: the same
   * incidental-coverage argument was made for the plaza and the plots, and it
   * was false. 9 items across 80 seeds stood in a crop plot whose outer rim
   * reaches past every disc (see paintField). Both terms now exist for the same
   * reason, and only one of them is quiet.
   */
  const inDistrict = (x: number, y: number) =>
    ctx.districts.some(
      (d) => (x - d.at.x) ** 2 + ((y - d.at.y) * 1.35) ** 2 < d.r * d.r
    )
  const free = (x: number, y: number) =>
    !ctx.laneField.nearLane(x, y, 34) &&
    !ctx.inWater(x, y) &&
    !ctx.onPaving(x, y) &&
    !inDistrict(x, y)
  const inner = (x: number, y: number) => ctx.coast.isInner(x, y) && free(x, y)

  const pass = (
    tag: string,
    kinds: readonly string[],
    pick: (x: number, y: number) => boolean,
    density: DensityField,
    rMin: number,
    rMax: number,
    cap: number
  ) => {
    // compose.py:638-639 — sample against the LARGEST sprite in the set, not
    // the first. Sampling against a small one and then drawing a large one is
    // how a full-size oak lands in a gap that only fitted a sapling.
    const size = {
      w: Math.max(...kinds.map((n) => ctx.sizeOf(n).w)),
      h: Math.max(...kinds.map((n) => ctx.sizeOf(n).h)),
    }
    const items = poissonScatter(`${seed}:${tag}`, {
      space: ctx.space,
      kinds,
      size,
      pick,
      density,
      onLand: (x, y) => ctx.coast.landAt(x, y),
      lanes: ctx.laneField,
      occupied: ctx.occupied,
      rMin,
      rMax,
      cap,
    })
    for (const item of items) {
      const itemSize = ctx.sizeOf(item.kind)
      ctx.occupied.push({ at: item.at, size: itemSize })
      out.push({ ...item, size: itemSize })
    }
  }

  pass('trees', NATURE_TREES, inner, ctx.wildness, 104, 300, 60)
  pass('shrubs', NATURE_SHRUBS, inner, ctx.wildness, 62, 170, 110)
  pass('flowers', NATURE_FLOWERS, inner, (x, y) => 1 - ctx.wildness(x, y) * 0.5, 58, 150, 90)
  // Mushrooms and toadstool clumps are village-adjacent dressing in the
  // reference's AMBIENT set; the rocks and deadwood are not. A camp keeps the
  // deadwood, which is what an unworked island actually has lying around.
  pass('ground', NATURE_GROUND.concat(ctx.camp ? [] : ['mushrooms']), inner, ctx.wildness, 104, 260, 40)

  // A verge is a consequence of a road having sides worth dressing. A camp's
  // worn track through grass has none.
  //
  // compose.py's verge() is NOT free() — it wants to be near a lane, which
  // free() forbids — but it carries the same disc and water terms, so verge
  // dressing does not appear inside the square or in the pond either.
  if (ctx.village) {
    const verge = (x: number, y: number) =>
      ctx.laneField.nearLane(x, y, 96) &&
      !ctx.laneField.nearLane(x, y, 62) &&
      !ctx.inWater(x, y) &&
      !ctx.onPaving(x, y) &&
      !inDistrict(x, y)
    pass('verge', VERGE_KINDS, verge, () => 0.7, 88, 130, 34)
  }

  pass('shore', SHORE_KINDS, (x, y) => ctx.coast.inShoreBand(x, y) && free(x, y), () => 0.8, 96, 150, 30)
  return out
}

// ── audit surface ──────────────────────────────────────────────────────────

/**
 * Every layout invariant, measured with the SAME functions the rules used.
 *
 * "An audit must call the same function the rule calls, or it is measuring a
 * different world" (paid 2026-07-26 — three placement rules and two audits,
 * each with its own notion of where a sprite stands, and the world reported
 * clean three times while props stood on the road). Exported so the tests and
 * any future checker share one implementation.
 */
export function auditLayout(layout: Layout): {
  onLane: { kind: string; at: Point }[]
  stacked: { a: string; b: string }[]
  inWater: { kind: string; at: Point }[]
} {
  const field = buildLaneField(layout.lanes)
  const onLane: { kind: string; at: Point }[] = []
  // Both lists carry the size the RULES used, so the audit cannot measure a
  // different world than the one that was built.
  const all: { kind: string; at: Point; size: Footprint }[] = [
    ...layout.structures.map((s) => ({ kind: s.kind, at: s.at, size: s.size })),
    ...layout.scatter.map((s) => ({ kind: s.kind, at: s.at, size: s.size })),
  ]
  for (const item of all) {
    if (footprintOnLane(item.at, item.size, field)) onLane.push({ kind: item.kind, at: item.at })
  }
  const stacked: { a: string; b: string }[] = []
  for (let i = 0; i < layout.structures.length; i++) {
    for (let j = i + 1; j < layout.structures.length; j++) {
      const a = layout.structures[i]
      const b = layout.structures[j]
      // groundTaken is the RULE's own function against a one-element book, so
      // the audit and the rule cannot drift apart.
      if (groundTaken(a.at, a.size, [{ at: b.at, size: b.size }], 0.16)) {
        stacked.push({ a: a.kind, b: b.kind })
      }
    }
  }
  // NOTHING STANDS ON OPEN WATER, re-measured rather than trusted. The rules
  // that place things now guarantee it, which is exactly why the audit has to
  // check it independently: a guarantee with no sensor on it is an assumption,
  // and this one was silently absent while a workshop stood in the sea.
  //
  // EACH CLASS IS PROBED THE WAY ITS OWN RULE PROBES IT. A structure's rule
  // asks about (x, y-2) — the reference's, because a base exactly on the
  // waterline row reads as land in a blurred, thresholded mask. Scatter's
  // sampling rule asks about (x, y). Using one convention for both would report
  // a defect against a rule that never made that claim.
  const inWater: { kind: string; at: Point }[] = []
  for (const s of layout.structures) {
    if (!layout.coast.landAt(s.at.x, s.at.y - 2)) inWater.push({ kind: s.kind, at: s.at })
  }
  for (const s of layout.scatter) {
    if (!layout.coast.landAt(s.at.x, s.at.y)) inWater.push({ kind: s.kind, at: s.at })
  }
  return { onLane, stacked, inWater }
}

export * from './space'
export * from './coastline'
export * from './lanes'
export * from './lots'
export * from './driveways'
export * from './clearance'
export * from './scatter'
