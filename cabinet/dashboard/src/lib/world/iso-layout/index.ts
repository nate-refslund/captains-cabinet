/**
 * ISO-LAYOUT — composeLayout(state, seed): the whole ported LAYOUT stage, as
 * one pure seeded function returning plain data the renderer consumes.
 *
 * THE STAGE ORDER IS ITSELF A RULE (compose.py's docstring, "armature first"):
 *
 *   coastline -> lanes -> lots -> driveways -> ground paint -> structures ->
 *   forest ring -> scatter
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
 *     plot before the house existed, compose.py:907-909);
 *   - THE FOREST RING BEFORE THE SCATTER. The belt frames the island and the
 *     meadow planting fills in behind it; run the other way round, a shrub that
 *     happened to land on the shore band takes the tree's spot and the frame
 *     goes ragged. compose.py runs the ring before the district BUILDINGS as
 *     well, protected only by the discs it reserved first — this port runs it
 *     after them instead, so a tree can never take ground a measured building
 *     needs (see ring.ts, which records both divergences and why).
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
  clearOfRegions,
  footprintOnLane,
  groundTaken,
  placeOnGround,
  snapInland,
  type Footprint,
  type Occupant,
} from './clearance'
import { driveway, drivewayLane, type Driveway } from './driveways'
import {
  buildHarbour,
  CAIRN_CLEARING,
  lampPosition,
  lighthouseSite,
  LIGHTHOUSE_CLEARING,
  rectContains,
  type Ellipse,
  type Harbour,
  type Lighthouse,
  type Rect,
} from './harbour'
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
  grownField,
  paintField,
  paintRegions,
  POND,
  REED_MARGIN,
  waterField,
  type PaintRegion,
} from './paint'
import { forestRing, type RingItem } from './ring'
import {
  poissonScatter,
  wildnessField,
  type DensityField,
  type District,
  type ScatterItem,
} from './scatter'
import {
  clamp,
  emptyRung,
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

/**
 * compose.py:26 — a handful of objects draw even at an empty rung, because the
 * empty rung IS the drawing (an unlit cairn is a lighthouse that has not been
 * earned, and showing nothing there would hide the fact).
 */
const ALWAYS_DRAWN = new Set(['veto_plinth', 'flagpole', 'firepit', 'lighthouse'])

export function isBuilt(state: LayoutState, obj: string): boolean {
  if (ALWAYS_DRAWN.has(obj)) return true
  return presentRung(state, obj)
}

/**
 * worldstate.py present(), WITHOUT the always-drawn override: has this object's
 * rung actually built anything?
 *
 * The two questions are different and conflating them is how a lamp ends up
 * floating over a cairn. `isBuilt('lighthouse')` is true at every era because
 * the empty rung IS the drawing — an unlit cairn is a lighthouse that has not
 * been earned, and hiding it would hide the fact. `presentRung('lighthouse')`
 * is false there, which is what the lamp has to ask: a lamp needs a tower.
 */
export function presentRung(state: LayoutState, obj: string): boolean {
  return !emptyRung(state.stages?.[obj])
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
 *
 * RE-DERIVED FROM manifest.py ENTRY BY ENTRY on 2026-07-27, because the sentence
 * above was a claim nobody had checked and five rows contradicted it:
 * tree_birch was 150x150 for a 125x165 sprite, tree_willow 150x150 for 155x155,
 * and rock_cluster, fallen_log and mushrooms all carried the generic 47x45 of
 * the small-nature block while manifest.py generates them at 105x95, 120x95 and
 * 90x90 (all three are in HALF, so 52x47, 60x47 and 45x45). Every spacing
 * number this library measures — belt separation, ground overlap, lane
 * clearance — is computed against these, so a wrong row is not a cosmetic
 * error: it is a rule enforcing the wrong distance and reporting that it did.
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
  // the harbour and the lighthouse (manifest.py:33-35, :72-85, :124-125,
  // divided by scale_of()'s HALF fraction where it applies)
  warehouse: { w: 200, h: 175 },
  harbormaster_hut: { w: 145, h: 145 },
  lighthouse: { w: 130, h: 200 },
  harbor_crane: { w: 150, h: 190 },
  // the packet boat: the hamlet rung of the harbor_boat ladder, which is the
  // middle of its three sprites — the renderer overrides with the real one
  harbor_boat: { w: 165, h: 165 },
  mooring_post: { w: 47, h: 55 },
  cargo_stacks: { w: 55, h: 55 },
  cargo_barrels: { w: 55, h: 50 },
  crate_single: { w: 45, h: 45 },
  rope_coil: { w: 45, h: 45 },
  crab_pots: { w: 50, h: 50 },
  fish_barrel: { w: 47, h: 47 },
  fishing_net: { w: 52, h: 47 },
  fish_drying_rack: { w: 130, h: 130 },
  anchor: { w: 50, h: 55 },
  barrel_single: { w: 45, h: 47 },
  tree_oak: { w: 150, h: 150 },
  tree_oak_small: { w: 55, h: 55 },
  tree_birch: { w: 125, h: 165 },
  tree_willow: { w: 155, h: 155 },
  bush_round: { w: 47, h: 47 },
  bush_flowering: { w: 47, h: 47 },
  fern_cluster: { w: 47, h: 47 },
  flowers_white: { w: 47, h: 45 },
  flowers_yellow: { w: 47, h: 45 },
  flowers_pink: { w: 47, h: 45 },
  rock_small: { w: 47, h: 45 },
  rock_cluster: { w: 52, h: 47 },
  mushrooms: { w: 45, h: 45 },
  tree_stump: { w: 47, h: 45 },
  fallen_log: { w: 60, h: 47 },
  reeds: { w: 47, h: 55 },
  // the enclosure ring's conifers, and the pond's own plant (manifest.py
  // NATURE, at scale_of()'s 1 and 2 respectively)
  tree_pine: { w: 130, h: 175 },
  tree_pine_small: { w: 50, h: 65 },
  lilypads: { w: 47, h: 45 },
  // the six dwelling variants the officer row draws from (manifest.py
  // BUILDINGS), plus the shelter that stands on those lots at camp
  officer_house_a: { w: 150, h: 150 },
  officer_house_b: { w: 150, h: 150 },
  officer_house_c: { w: 150, h: 150 },
  cottage_a: { w: 150, h: 150 },
  cottage_b: { w: 150, h: 150 },
  cottage_c: { w: 145, h: 145 },
  camp_tent: { w: 120, h: 120 },
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

// ── structures ─────────────────────────────────────────────────────────────

export interface Structure {
  /**
   * The SPRITE drawn here. One role may have several: the officer row draws a
   * different house per lot, which is why this is no longer the same string as
   * `role`. A renderer keys the atlas off this.
   */
  kind: string
  /**
   * The STATE OBJECT this structure is — the thing whose rung or count made it
   * exist ('officer_dwelling', 'library', 'well', ...).
   *
   * It exists because `kind` stopped being able to answer "why is this drawn?"
   * the moment one role gained six sprites, and that question is the whole of
   * check_state_traceable: anything drawn that cannot be traced to a rule over
   * `state` is a bug. A checker matching on sprite names would have to carry
   * its own copy of the variant table, which is a second place for the answer
   * to be wrong.
   */
  role: string
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

/**
 * THE REGION EXTENTS, in the shapes checks/world_checks.py reads them.
 *
 * EMITTED BY THE LAYOUT, not derived downstream. The blueprint's `plaza`,
 * `fields` and `quay` are read by check_on_road (which exempts anything standing
 * on a paved square, a tilled plot or the wharf) and by check_terrain (which
 * sweeps them for paving and cultivation, and lets a lane leave the shore at the
 * harbour). Deriving them in a bridge would mean a second module deciding where
 * the plaza is — and the exemption zone of a check must be the surface that was
 * actually painted, or the check is being turned down over ground nobody paved.
 *
 * They are computed from the EMITTED blobs, not from the authored constants:
 * this port shrinks and drops blobs that would spill into the sea, so the
 * authored 300x190 plaza is not the plaza on most islands.
 */
export interface Regions {
  /** [cx,cy,rx,ry]; null at camp, where the square is trodden grass. */
  plaza: Ellipse | null
  /** [cx,cy,rx,ry] per tilled plot, in emission order. */
  fields: Ellipse[]
  /** [x0,y0,x1,y1]; null when no deck was built. */
  quay: Rect | null
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
  /**
   * The forest enclosure ring, outermost sublayer first, each item carrying the
   * `layer` it belongs to.
   *
   * SEPARATE FROM `scatter` on purpose. It is a different kind of thing: a belt
   * walked by angle around the shore, in depth sublayers a renderer wants to
   * draw as bands, against a meadow scatter sampled over area. Merging them
   * would throw the layer away and leave a consumer no way to get it back.
   */
  ring: RingItem[]
  scatter: PlacedItem[]
  /** Keep-out discs, exported so the renderer can debug-draw the field. */
  districts: District[]
  /** null on an island carved with no cove: no bite, no harbour. */
  harbour: Harbour | null
  /** null only when there is no ground to stand it on. */
  lighthouse: Lighthouse | null
  regions: Regions
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
  const built: { key: string; obj: string; kind: string; lot: Lot; group: string }[] = []
  const dwellings = Math.min(countOf(state, 'officer_dwellings'), lots.residential.length)
  for (let i = 0; i < dwellings; i++) {
    const key = `residential-${i}`
    built.push({
      key,
      obj: 'officer_dwelling',
      kind: dwellingKind(numSeed, state.era, key),
      lot: lots.residential[i],
      group: 'residential',
    })
  }
  for (const [key, obj] of [
    ['memory', 'library'],
    ['works', 'workshop'],
    ['fields', 'outbuildings'],
  ] as const) {
    if (isBuilt(state, obj)) built.push({ key, obj, kind: obj, lot: lots[key][0], group: key })
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
  // Two numbers rather than the state: see ./paint. The plots are the only
  // count the ground stage may read, and the era reaches it only as `village`.
  const paint = paintRegions(numSeed, coast, countOf(state, 'field_plots'), village)

  // ---- 6. the harbour -----------------------------------------------------
  // BEFORE the structures, because it decides where the quayside buildings and
  // the lighthouse stand; those anchors then go through the same structure
  // rules as every other building, so the harbour never places anything on
  // water by fiat. No cove, no harbour: the whole section is pinned to the
  // cove's waterline and an island carved without one has no bite to build in.
  const harbour = coast.cove
    ? buildHarbour(coast, coast.cove, {
        era: state.era,
        quay: state.stages?.quay,
        berths: countOf(state, 'berths'),
        cargo: countOf(state, 'cargo_stacks'),
        warehouses: countOf(state, 'warehouse'),
        harbourmaster: presentRung(state, 'harbormaster_hut'),
        packs: countOf(state, 'packs_inherited'),
        boat: presentRung(state, 'harbor_boat'),
        sizeOf,
      })
    : null

  // ---- 7. structures ------------------------------------------------------
  const occupied: Occupant[] = []
  const structures: Structure[] = []

  /**
   * THE TILLED PLOTS ARE TAKEN GROUND, for buildings as well as for planting.
   *
   * FOUND BY DRAWING A FRAME, 2026-07-27, and by nothing else: the first
   * capture ever rendered from this layout put the harbourmaster's hut in a
   * ploughed plot, and check_on_road flagged it (soil is the same warm brown as
   * a dirt lane, so a building in the crop reads as a building in the road).
   * Measured across 40 village seeds before the fix: 28 of 40 stood a structure
   * on a plot — the hut, whose harbour offset is the plots' own column, and on
   * some islands the lighthouse. Three adversarial rounds of layout-only review
   * never saw it, because the plots are PAINT and no arm compared paint to
   * buildings.
   *
   * The predicate already existed one stage down: index.ts free() forbids
   * planting on 'crop' and 'ploughed', and a building is a stronger claim on
   * ground than a shrub. It is expressed as OCCUPANTS rather than a new
   * placeOnGround parameter so the existing settle machinery does the work — a
   * plot is ground that is taken, which is exactly what an Occupant means.
   *
   * NOT ADDED TO `occupied` ITSELF, on purpose: the ring and scatter passes
   * already exclude the plots through `onPaving`, and pushing plot rectangles
   * into their occupancy book would move planting near every plot edge for no
   * reason. Structures are the only stage that could not see them.
   *
   * THE PLAZA IS DELIBERATELY NOT HERE. The firepit and the market stall stand
   * ON the square by design — it is somewhere to stand, not a surface to keep
   * off. Adding it would delete the square's whole purpose.
   *
   * ONE OCCUPANT PER PLOT, NOT ONE PER BLOB, and that is the difference
   * between a fix and a half-fix. settleAgainstOccupants pushes away from the
   * occupant it collided with; a plot is 27 overlapping blobs, so per-blob
   * occupants make the building bounce from one blob into the next and give up
   * inside the plot after 60 tries. Measured over the same 40 seeds: per-blob
   * took 28 down to 17, per-plot takes it to 0. A partial fix that looked like
   * a fix is worse than none, because the arm goes green over the remainder.
   *
   * KNOWN LIMIT, on the safe side: the extent is the ellipse INSCRIBED IN THE
   * BLOBS' BOUNDING BOX (ellipseOfRegion), which is a superset of the paint —
   * about 3.5% of the average declared plot is grass the plough never turned.
   * So a building is pushed slightly further from a plot than the soil strictly
   * requires. Over-reserving here costs a few pixels of siting; under-reserving
   * would put a hut back in the crop.
   */
  const plotGround: Occupant[] = paint
    .filter((r) => r.kind === 'ploughed' || r.kind === 'crop')
    .map((r) => ellipseOfRegion(r))
    .filter((e): e is Ellipse => e !== null)
    .map(([cx, cy, rx, ry]) => ({
      // An Occupant's ground box is (x-w*0.42, y-min(h,w)*0.55, x+w*0.42, y),
      // so the sizes that make the box EXACTLY the plot extent are rx/0.42 and
      // 2*ry/0.55. Writing 2*rx/0.42 (the obvious symmetry with the height)
      // reserves twice the plot's width, which is a different island.
      at: { x: cx, y: cy + ry },
      size: { w: rx / 0.42, h: (2 * ry) / 0.55 },
    }))
  const put = (
    kind: string,
    role: string,
    at: Point,
    flip: boolean,
    lot?: Lot
  ): Structure | null => {
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
    const p = placeOnGround(at, size, laneField, onLand, [...occupied, ...plotGround], {
      strict: true,
      inlandTo: inland,
    })
    if (!p) return null
    // placeOnGround knows about lanes, water and neighbours; it does not know
    // about the plough. Its own recovery path is what puts a building back on a
    // plot — the settle shoves a shoreline anchor into the sea and the land walk
    // returns it inland onto the soil it was pushed off — so the plot rule gets
    // the last word, exactly as the road does inside placeOnGround.
    const cleared = clearOfRegions(p, size, plotGround, laneField, onLand, occupied)
    occupied.push({ at: cleared, size })
    const s: Structure = { kind, role, at: cleared, flip, size, lot }
    structures.push(s)
    return s
  }

  if (isBuilt(state, 'great_house')) {
    put('great_house', 'great_house', lots.centre[0].c, lotFlip(lots.centre[0]), lots.centre[0])
  }
  if (isBuilt(state, 'well')) put('well', 'well', { x: 1050, y: 970 }, false)
  if (isBuilt(state, 'firepit')) put('firepit', 'firepit', SQUARE, false)
  if (village && isBuilt(state, 'market_stall')) {
    put('market_stall', 'market_stall', { x: 1386, y: 958 }, false)
  }
  // ONE SPRITE PER LOT, not one sprite six times — see dwellingKind.
  for (const b of built) put(b.kind, b.obj, b.lot.c, lotFlip(b.lot), b.lot)

  // The quayside buildings stand on LAND above the wharf (compose.py:1165-1176)
  // and go through the same door as every other building — so a warehouse on a
  // seed whose cove ate its shore is DROPPED, not floated.
  const quayside: Structure[] = []
  for (const site of harbour?.warehouseSites ?? []) {
    const s = put('warehouse', 'warehouse', site, false)
    if (s) quayside.push(s)
  }
  if (harbour?.harbourmasterSite) {
    const s = put('harbormaster_hut', 'harbormaster_hut', harbour.harbourmasterSite, false)
    if (s) quayside.push(s)
  }

  // ---- 8. the lighthouse --------------------------------------------------
  // ALWAYS DRAWN: an unlit cairn is a lighthouse that has not been earned, and
  // drawing nothing there would hide the fact (compose.py:26). Its site is
  // WALKED from the coastline, so it moves with the island rather than sitting
  // at an authored bearing that half the seeds put inland.
  const lighthouse = placeLighthouse(state, coast, space, put)

  // ---- 9. scatter ---------------------------------------------------------
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
    // THE LIGHTHOUSE CLEARING (compose.py:905) — the forest ring frames the
    // point, it does not swallow the tower. Centred on where the tower actually
    // ENDED, not on the site it was walked from: the structure rules may have
    // moved it off a lane, and a clearing round the old spot would leave the
    // tower in the trees and a bald circle beside it.
    ...(lighthouse ? [{ at: lighthouse.at, r: lighthouse.clearing }] : []),
    // compose.py:1171,1176 reserves the quayside buildings the same way
    ...quayside.map((s) => ({ at: s.at, r: s.kind === 'warehouse' ? 160 : 110 })),
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
  // The dock kit occupies ground like anything else. It is not a structure (it
  // stands on a deck over water), but the half of it that lands on the shore
  // strip is real ground a reed must not grow through — and the scatter stage
  // rejects against `occupied` at sampling time, so the book is where it goes.
  for (const item of harbour?.items ?? []) occupied.push({ at: item.at, size: item.size })

  // ---- 10. the forest enclosure ring --------------------------------------
  // MORPHOLOGY, not doctrine, so it stands in every era: an island has a
  // treeline whether or not anyone has landed on it, on the same argument that
  // keeps the pond at camp. What the ERA changes is where it may grow — at camp
  // the village-only keep-out discs do not exist, so the belt is free to close
  // over ground a hamlet would have reserved.
  //
  // BEFORE the general planting and AFTER the structures: the belt takes the
  // coastal band first (that is what makes it a belt rather than the outer tail
  // of a gradient) and the six scatter passes then fill the meadow inside it
  // against an occupancy book the ring has already written into.
  const inWater = waterField(paint)
  const onPaving = paintField(paint, ['plaza', 'crop', 'ploughed'])
  // ONE FIELD, built once and handed to both planting stages: the belt and the
  // scatter must agree on where the deck is, and two `rectField` calls off the
  // same rect is one call away from being two different rects.
  const onQuay = rectField(harbour?.wharf?.rect ?? null)
  const ring = forestRing(numSeed, {
    space,
    coast,
    lanes: laneField,
    districts,
    occupied,
    inWater,
    onPaving,
    onQuay,
    sizeOf,
  })
  for (const item of ring) occupied.push({ at: item.at, size: item.size })

  // ---- 11. scatter --------------------------------------------------------
  const scatter = plant(numSeed, {
    space,
    coast,
    laneField,
    occupied,
    districts,
    wildness,
    inWater,
    onPaving,
    // The plantable MARGIN around the water, which is wider than the painted
    // sand fringe — see grownField in ./paint for why the two differ.
    onBank: grownField(paint, ['pond', 'stream'], REED_MARGIN),
    // NOTHING IS PLANTED ON THE WHARF. This port's own term, on the same
    // argument the paving term needed: a deck is a surface, and the keep-out
    // discs do not reach it (the nearest is the square's, 400px north). The
    // shore band runs along the waterline, which is exactly where the deck is.
    onQuay,
    sizeOf,
    village,
    camp,
  })

  // ---- 12. region extents -------------------------------------------------
  const regions: Regions = {
    plaza: ellipseOfRegion(paint.find((r) => r.kind === 'plaza')),
    fields: paint
      .filter((r) => r.kind === 'ploughed' || r.kind === 'crop')
      .map((r) => ellipseOfRegion(r))
      .filter((e): e is Ellipse => e !== null),
    quay: harbour?.wharf?.rect ?? null,
  }

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
    ring,
    scatter,
    districts,
    harbour,
    lighthouse,
    regions,
  }
}

/**
 * PER-OFFICER HOUSE VARIETY (compose.py:1067-1072).
 *
 * The officer row drew ONE sprite on every lot, which is what makes a row of
 * cottages read as a barracks: six identical roofs in a line is a pattern no
 * village has. The reference varies it per lot from a pool of six.
 *
 * SEEDED ON THE LOT'S IDENTITY, not on its index alone. The reference uses
 * `HOUSES[i % 6]`, which gives every org on earth the same six houses in the
 * same order; keying on (world seed, lot key) gives each island its own row and
 * is just as stable, because the lot keys are generated in a fixed order from
 * data that does not depend on how many dwellings are occupied. Growing from
 * three officers to four therefore ADDS a house rather than reshuffling three.
 * It is the pattern the world already uses for per-officer roof cuts
 * (island-layout.ts: `V.cottage[fnv1a(`${slug}:roof`) % V.cottage.length]`).
 *
 * ERA GATES IT. At camp a dwelling is a canvas tent: a slate-roofed cottage on
 * a camp lot would be claiming a building the org has not earned. The reference
 * keys the same rule off the sprite the dwelling ladder resolves to (`_dw`
 * starting with `camp_`); this port has no sprite table, so it keys off the era
 * that decides that rung — the same fact, read from the surface this layer has.
 */
export const HOUSE_KINDS: readonly string[] = [
  'officer_house_a',
  'officer_house_b',
  'officer_house_c',
  'cottage_a',
  'cottage_b',
  'cottage_c',
]

/** compose.py's `camp_` dwelling: what stands on an officer lot before a house. */
export const CAMP_DWELLING = 'camp_tent'

export function dwellingKind(seed: number, era: Era, lotKey: string): string {
  if (!eraAtLeast(era, 'hamlet')) return CAMP_DWELLING
  return HOUSE_KINDS[fnv1a(`${seed}:dwelling:${lotKey}`) % HOUSE_KINDS.length]
}

/**
 * Site, place and light the lighthouse.
 *
 * The site is WALKED from the coastline (harbour.ts lighthouseSite) and then
 * goes through the same `put` every other building does, so the tower is on
 * land or it does not exist. When the walk finds no south-east point at all the
 * island centre is the last resort, exactly as compose.py's snap() ends — and
 * `put` still refuses to draw it if even that is water.
 */
function placeLighthouse(
  state: LayoutState,
  coast: Coastline,
  space: LayoutSpace,
  put: (kind: string, role: string, at: Point, flip: boolean) => Structure | null
): Lighthouse | null {
  const site = lighthouseSite(coast, space, coast.cove) ?? { x: space.cx, y: space.cy }
  const s = put('lighthouse', 'lighthouse', site, false)
  if (!s) return null
  const tower = presentRung(state, 'lighthouse')
  const rungLit = state.stages?.lighthouse_lamp === 'lit'
  // A LAMP NEEDS A TOWER. See LighthouseLamp in harbour.ts: `rungLit` keeps the
  // measurement even on the frame that cannot draw it, so nothing is hidden.
  const lit = rungLit && tower
  return {
    at: s.at,
    size: s.size,
    clearing: tower ? LIGHTHOUSE_CLEARING : CAIRN_CLEARING,
    tower,
    lamp: { rungLit, lit, at: lit ? lampPosition(s.at, s.size) : null },
  }
}

/**
 * The bounding ellipse of a painted region — [cx,cy,rx,ry], or null if empty.
 *
 * IT IS THE ELLIPSE INSCRIBED IN THE BLOBS' BOUNDING BOX, so it is a SUPERSET
 * of the paint, and that is a known limit rather than an oversight. Measured
 * 2026-07-27 over 20 village islands by 2px lattice: 9.0% of the declared plaza
 * ellipse and 3.5% of the average declared field ellipse is grass the paint
 * never covered (worst island: 15.1% and 17.7%). check_on_road exempts anything
 * inside these, so its exemption is that much wider than the surface.
 *
 * NOT FIXED, deliberately, for three reasons stated so the next reader can
 * disagree with the reasoning rather than rediscover the number:
 *   - the direction is safe for the OTHER consumer. check_terrain sweeps these
 *     same ellipses for paving and cultivation, and a wider ellipse puts more
 *     grass in the denominator — it can only make that check harder to pass,
 *     never easier.
 *   - nothing this layout produces can hide in the difference. The plaza and
 *     every plot sit inside keep-out discs, so no planting pass reaches them at
 *     all; the structures near the square go through placeOnGround, which
 *     refuses a lane outright before the exemption is ever consulted.
 *   - the honest alternative — shrinking each ellipse until it is contained in
 *     the blob union — is a per-island lattice search on the compose path, paid
 *     on every render, to tighten an exemption that currently exempts nothing
 *     the checks would have caught.
 * If a consumer ever stands something inside a region extent WITHOUT going
 * through placeOnGround, this becomes a real hole and the search is worth it.
 */
export function ellipseOfRegion(region: PaintRegion | undefined): Ellipse | null {
  if (!region || region.blobs.length === 0) return null
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const b of region.blobs) {
    x0 = Math.min(x0, b.c.x - b.rx)
    x1 = Math.max(x1, b.c.x + b.rx)
    y0 = Math.min(y0, b.c.y - b.ry)
    y1 = Math.max(y1, b.c.y + b.ry)
  }
  return [(x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2]
}

/** Membership of a rect extent, as a field the planting predicate can compose. */
export function rectField(rect: Rect | null): (x: number, y: number) => boolean {
  if (!rect) return () => false
  return (x, y) => rectContains(rect, { x, y })
}

// ── stage helpers ──────────────────────────────────────────────────────────
//
// The ground-paint stage moved to ./paint when it gained the broken meadow, the
// outflow stream, the pond bank and the value mottle: it was a third of this
// file and it is a stage of its own, exactly like ./lanes and ./lots. Its whole
// surface is re-exported below, so `from './index'` is unchanged.

interface PlantCtx {
  space: LayoutSpace
  coast: Coastline
  laneField: LaneField
  occupied: Occupant[]
  districts: District[]
  wildness: DensityField
  /** compose.py in_water(): the pond and outflow that were actually painted. */
  inWater: (x: number, y: number) => boolean
  /** The paved square and the tilled plots that were actually painted. */
  onPaving: (x: number, y: number) => boolean
  /** The wharf deck that was actually built. */
  onQuay: (x: number, y: number) => boolean
  /** The sand ring around the water — where reeds belong and nothing else. */
  onBank: (x: number, y: number) => boolean
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
   * THE WATER TERM IS STILL QUIET, and the outflow did NOT change that — which
   * is worth writing down, because it was the obvious prediction and it is
   * wrong. Measured 2026-07-27 by deleting `!ctx.inWater(x, y)` from this
   * predicate and running both suites: 164 arms, all green. The stream reaches
   * well outside the pond's 190px disc (20 of its blobs do on seed zeta), so the
   * disc is no longer the whole reason — but the surviving reasons are just as
   * effective: the outflow is 24-30px wide against meadow passes that space at
   * 58-104px, and the bank and lilypad passes have already written the margin
   * and the water into the occupancy book by the time those passes sample.
   *
   * So this stays a REDUNDANT rule, kept deliberately: it is the reference's own
   * term, the disc above it is doctrine (era-gated, movable) while water is
   * morphology, and three coincidences are not an invariant. What is NOT quiet
   * is the identical term in ring.ts — deleting it there turns four arms red,
   * because the belt walks the coastal band at a fixed angular step and does not
   * care how narrow a river is.
   *
   * THE PAVING TERM IS NOT REDUNDANT, which is how it was found: the same
   * incidental-coverage argument was made for the plaza and the plots, and it
   * was false. 9 items across 80 seeds stood in a crop plot whose outer rim
   * reaches past every disc (see paintField). Both terms now exist for the same
   * reason, and only one of them is quiet.
   *
   * THE QUAY TERM IS THE SAME ARGUMENT AGAIN, and it is not quiet either: no
   * keep-out disc reaches the wharf (the nearest is the square's, 400px north),
   * and the SHORE BAND — the pass that plants reeds and shore rocks — is defined
   * as the strip just inside the waterline, which is precisely where the deck
   * is. Measured with the term dropped, reeds and shore rocks stand on the deck.
   */
  const inDistrict = (x: number, y: number) =>
    ctx.districts.some(
      (d) => (x - d.at.x) ** 2 + ((y - d.at.y) * 1.35) ** 2 < d.r * d.r
    )
  const free = (x: number, y: number) =>
    !ctx.laneField.nearLane(x, y, 34) &&
    !ctx.inWater(x, y) &&
    !ctx.onPaving(x, y) &&
    !ctx.onQuay(x, y) &&
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

  // THE POND'S OWN DRESSING, first, so the bank is not already full of meadow
  // shrubs by the time the reeds arrive. Neither pass is free()-gated — free()
  // forbids the pond's 190px disc, which is the whole area these two want —
  // exactly as the verge pass is not free()-gated because it wants a lane.
  // That is also why they are the only way anything reaches the water: the
  // general passes still cannot, and the arm that says so is now stronger for
  // naming what may.
  //
  // MORPHOLOGY, so both stand at camp. Reeds at a waterline are not tending.
  const bank = (x: number, y: number) =>
    ctx.onBank(x, y) &&
    !ctx.inWater(x, y) &&
    !ctx.laneField.nearLane(x, y, 34) &&
    !ctx.onPaving(x, y) &&
    !ctx.onQuay(x, y)
  pass('bank', ['reeds'], bank, () => 0.85, 54, 92, 22)
  // Lilypads are the one thing that belongs ON the water, and they are gated on
  // water they can actually float on: `inWater` is built from the pond that was
  // EMITTED, so a seed whose west meadow had no room for a pond gets no pads
  // rather than pads on grass.
  pass('lilypads', ['lilypads'], (x, y) => ctx.inWater(x, y), () => 0.9, 46, 78, 14)

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
  //
  // AND THE QUAY TERM, which is where it was found: the main street ends AT the
  // harbour head, so the verge band — 62 to 96px off a carriageway — lies
  // squarely on the wharf. Measured with the term on free() only: 8 verge items
  // (5 shore rocks, 2 flowers, a bush) standing on the deck across 30 seeds, all
  // of them on the landward strip where nothing else would catch them. Adding a
  // term to one predicate and calling the rule enforced is exactly how the
  // paving leak survived its own arm.
  if (ctx.village) {
    const verge = (x: number, y: number) =>
      ctx.laneField.nearLane(x, y, 96) &&
      !ctx.laneField.nearLane(x, y, 62) &&
      !ctx.inWater(x, y) &&
      !ctx.onPaving(x, y) &&
      !ctx.onQuay(x, y) &&
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
  outsideHarbour: { kind: string; at: Point }[]
} {
  const field = buildLaneField(layout.lanes)
  const onLane: { kind: string; at: Point }[] = []
  // Both lists carry the size the RULES used, so the audit cannot measure a
  // different world than the one that was built.
  // THE RING IS AUDITED TOO. It is the largest single population the layout
  // emits and it is placed by its own module against its own predicate, which
  // makes it the population most likely to drift out from under the rules —
  // exactly the argument for auditing anything at all.
  const all: { kind: string; at: Point; size: Footprint }[] = [
    ...layout.structures.map((s) => ({ kind: s.kind, at: s.at, size: s.size })),
    ...layout.ring.map((s) => ({ kind: s.kind, at: s.at, size: s.size })),
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
  // The ring samples with the scatter's convention (x, y), so it is probed with
  // the scatter's convention. A belt planted at `landEdge - inset` is the
  // population standing closest to the waterline by construction, which makes
  // this the arm most likely to catch a coastline the ring stopped agreeing with.
  for (const s of layout.ring) {
    if (!layout.coast.landAt(s.at.x, s.at.y)) inWater.push({ kind: s.kind, at: s.at })
  }
  // THE HARBOUR'S OWN INVARIANT, because the water arm cannot be its sensor.
  // A mooring post is in the water by construction and a crate stands on a deck
  // that is over water, so the honest question about them is not "is this on
  // land" but "is this in the HARBOUR" — a dock kit computed from the wrong
  // origin, a mooring row indexed off the wrong base, or a crane laid along a
  // span that is not the wharf's all put working gear out in open sea, and none
  // of those is visible to any other arm here.
  //
  // The envelope is built from the cove and the shore ONLY (harbour.ts
  // `extent`), never from the items it contains: a box fitted around the things
  // it checks is a sensor that cannot fail.
  const outsideHarbour: { kind: string; at: Point }[] = []
  const h = layout.harbour
  if (h) {
    const inside = (p: Point) => rectContains(h.extent, p)
    for (const item of h.items) {
      if (!inside(item.at)) outsideHarbour.push({ kind: item.kind, at: item.at })
    }
    for (const m of h.moorings) {
      if (!inside(m)) outsideHarbour.push({ kind: 'mooring_post', at: m })
    }
    for (const c of h.cranes) {
      if (!inside(c)) outsideHarbour.push({ kind: 'harbor_crane', at: c })
    }
    // The jetty is absent on an unmeasured quay ladder; an absent pier cannot
    // be outside the envelope, and asking would be asserting against null.
    if (h.jetty && (!inside(h.jetty.at) || !inside(h.jetty.end))) {
      outsideHarbour.push({ kind: 'jetty', at: h.jetty.end })
    }
  }
  return { onLane, stacked, inWater, outsideHarbour }
}

export * from './space'
export * from './coastline'
export * from './lanes'
export * from './lots'
export * from './driveways'
export * from './clearance'
export * from './scatter'
export * from './paint'
export * from './ring'
// ./harbour was the one sibling missing from this list, and it is the one whose
// types the Layout's own public surface is written in: `harbour: Harbour | null`,
// `lighthouse: Lighthouse | null` and Regions' `Ellipse`/`Rect` could not be
// NAMED by anything importing from './index'. tsc does not catch that — a
// structurally-reachable type still checks — so the seam only shows the first
// time a renderer tries to hold one in a variable. Found 2026-07-27 by asking
// the compiler directly, in the same review that found the belt's size aliasing;
// both are what two writers editing one barrel in one worktree look like.
export * from './harbour'
