/**
 * ISO-LAYOUT — composeLayout(state, seed): the whole ported LAYOUT stage, as
 * one pure seeded function returning plain data the renderer consumes.
 *
 * THE STAGE ORDER IS ITSELF A RULE (compose.py's docstring, "armature first"):
 *
 *   coastline -> lanes -> lots -> driveways -> ground paint -> structures ->
 *   CLEARING -> forest ring -> scatter
 *
 * THE ISLAND IS OVERGROWN AND CLEARING IS SUBTRACTIVE (Captain 2026-07-27, see
 * ./clearing). Wilderness is the island's default state, not decoration placed
 * around the buildings: every structure stands in ground that was CUT for it,
 * the cut grows with the object's own rung, and what a viewer reads as the org
 * maturing is the treeline receding. That is why `clearing` sits where it does
 * in the order — it can only be computed once the structures have landed, and
 * everything that plants is a function of what it left standing.
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
  maxGroundOverlap,
  placeOnGround,
  snapInland,
  type Footprint,
  type Occupant,
} from './clearance'
import { driveway, drivewayLane, type Driveway } from './driveways'
import {
  COUNT_GATED_BUILDINGS,
  dressDistricts,
  dressLanding,
  type DressItem,
  type Settle,
} from './dressing'
import {
  buildHarbour,
  CAIRN_CLEARING,
  inOpenWater,
  lampPosition,
  lighthouseSite,
  shoreAt,
  LIGHTHOUSE_CLEARING,
  rectContains,
  type Ellipse,
  type Harbour,
  type HarbourTimber,
  type Lighthouse,
  type Rect,
} from './harbour'
import {
  buildLaneField,
  buildLanes,
  GREAT,
  laneTrafficLadder,
  laneWidthAt,
  LOT_LANES,
  SQUARE,
  type Lane,
  type LaneDemand,
  type LaneField,
} from './lanes'
import { lotDoor, lotFlip, lotFor, lotsAlong, CIVIC_ANCHORS, type Lot } from './lots'
import {
  grownField,
  PAINT_KERB,
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
  type DensityField,
  type District,
  type ScatterItem,
} from './scatter'
import {
  buildClearedGround,
  CIVIC_ERA_SCALE,
  clearingRadius,
  FURNITURE_MAX_TIMBER,
  rawnessOfEra,
  rawnessOfRung,
  structureClearings,
  type Clearing,
  type ClearedGround,
  type CutBy,
} from './clearing'
import {
  clamp,
  emptyRung,
  eraAtLeast,
  hypot,
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

/**
 * How long the i-th of `n` identical things has stood, in rungs.
 *
 * WHY A COUNT LADDER NEEDS THIS AT ALL. `countOf(state, role)` is the visible
 * rung index and it is what sizes a clearing and ages its rim (see ./clearing).
 * For a TIER ladder that is the object's own maturity and it is exactly right.
 * For a COUNT ladder — `officer_dwellings` runs none / dwelling_1 / dwellings_2
 * — the number says how MANY exist, not how far any one of them has come, and
 * the layout was reading it as rung 0 for every dwelling: six cabins that all
 * look brand new, at every era, forever. Measured: the felling record's density
 * stopped falling past `town` and rose again at `beyond_bay`, because half the
 * rims on the island were pinned at rawness 1 by dwellings that were never new.
 *
 * The honest answer is in the count itself. Lots are filled in a fixed order, so
 * the i-th dwelling was raised when the count reached i+1 and `n-1-i` officers
 * have arrived since. The FIRST cabin is therefore the oldest — the widest
 * clearing and the most settled edge — and the LAST one is brand new, with a
 * small raw clearing. That is the Captain's own example rendered as data: "a new
 * officer spawns and then starts chopping trees and building his/her cabin".
 *
 * It invents nothing: same count, same order, same answer forever, and growing
 * from three officers to four AGES the three rather than reshuffling them.
 */
export function seniority(i: number, n: number): number {
  if (!Number.isFinite(i) || !Number.isFinite(n)) return 0
  return Math.max(0, Math.trunc(n) - 1 - Math.trunc(i))
}

/**
 * The state, as the question ./lanes asks of it: does that place exist, and how
 * much is it used?
 *
 * ONE DEFINITION, exported so nothing has to write a second one. The predicates
 * are exactly the ones the STRUCTURE stage is gated on further down this file —
 * `presentRung` for a tier ladder, a positive count for a count ladder — so a
 * road to the library and the library itself cannot disagree about whether
 * there is a library. A test that built its own demand would be free to drift
 * from the composer it is testing.
 *
 * USAGE IS THE RUNG INDEX, and that is not a shortcut: era-engine resolves each
 * ladder to `clamp(floor(log2(v/base + 1)))` and iso-scene.ts's layoutStateFrom
 * writes exactly that into `counts` (`counts[name] = trunc(el.rung)`). So the
 * log scaling a worn path needs is already applied by the ladder that owns the
 * metric, and no second curve is invented at the roadside. An absent ladder
 * answers 0 — the hairline, an honest unmeasured, never an interpolation.
 */
export function laneDemandFrom(state: LayoutState): LaneDemand {
  return {
    present: (obj) => presentRung(state, obj) || countOf(state, obj) > 0,
    usage: (obj) => countOf(state, obj),
    village: eraAtLeast(state.era, 'hamlet'),
  }
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
  // market_stall moved to the dressing block below with the pack's own size —
  // it is dressing now, not a building, and 150x140 was the manifest estimate
  // for a sprite the pack ships at 125x105.
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
  // ---- the district dressing (./dressing), from world-pack.json's own dw/dh
  // at the HAMLET vocabulary, which is the same convention every row above
  // uses. The LADDER objects are keyed by OBJECT name because that is the key
  // `sizeOf` is called with; blueprint.ts's OBJECT_OF_KIND then resolves the
  // real era/rung art, and a pack-backed caller never reaches these numbers.
  law_plot: { w: 29, h: 24 },
  pens: { w: 45, h: 43 },
  water_store: { w: 30, h: 37 },
  composter: { w: 48, h: 39 },
  noticeboard: { w: 39, h: 55 },
  flagpole: { w: 50, h: 173 },
  veto_plinth: { w: 43, h: 42 },
  observatory: { w: 146, h: 144 },
  journal_desk: { w: 45, h: 43 },
  lantern_posts: { w: 18, h: 63 },
  market_stall: { w: 125, h: 105 },
  market_goods: { w: 48, h: 35 },
  bench: { w: 38, h: 32 },
  wheelbarrow: { w: 33, h: 24 },
  chicken: { w: 19, h: 30 },
  signpost: { w: 31, h: 47 },
  lamp_dark: { w: 18, h: 63 },
  lamp_lantern: { w: 28, h: 65 },
  chart_table: { w: 96, h: 105 },
  dog_sleeping: { w: 33, h: 23 },
  law_post: { w: 25, h: 51 },
  consequence_ledger: { w: 45, h: 51 },
  fence_run: { w: 29, h: 24 },
  chart_tent: { w: 124, h: 111 },
  windmill: { w: 164, h: 178 },
  watermill_kiln: { w: 150, h: 150 },
  wood_pile: { w: 38, h: 32 },
  water_trough: { w: 44, h: 34 },
  scarecrow: { w: 34, h: 61 },
  haystack: { w: 45, h: 46 },
  cart: { w: 39, h: 37 },
  veg_garden: { w: 54, h: 35 },
  chicken_coop: { w: 90, h: 85 },
  laundry_line: { w: 55, h: 46 },
  beehives: { w: 43, h: 38 },
  mailbox: { w: 29, h: 54 },
  potted_plant: { w: 32, h: 45 },
  flowerbed: { w: 44, h: 36 },
  boat_rowing: { w: 88, h: 62 },
  boat_fishing: { w: 83, h: 113 },
  buoy: { w: 38, h: 46 },
  well_house: { w: 112, h: 114 },
}

const FALLBACK_FOOTPRINT: Footprint = { w: 96, h: 96 }

// ── districts ──────────────────────────────────────────────────────────────

/**
 * THE AUTHORED CIVIC GROUND — the clearings that belong to no single building.
 *
 * WHAT THESE WERE, AND WHAT THEY ARE NOW (Captain direction 2026-07-27, see
 * ./clearing). This table was `DISTRICT_ANCHORS`: keep-out discs that stopped
 * planting landing on a district (compose.py:901-905), i.e. exclusions carved
 * out of a lawn. Under the inverted model the island is overgrown by default
 * and these are CLEARED GROUND — the same geometry with the reason the other
 * way round. They are open because somebody felled them, which is why they are
 * the ground the felling record rims.
 *
 * WHAT LEFT THE TABLE, and this is the inversion in one list:
 *   THE GREAT HOUSE, THE MEMORY LOT AND THE SIX AUTHORED DWELLING DISCS. A lot
 *   nobody has built on is not open ground — it is forest, and it stays forest
 *   until an officer arrives and cuts it. That is the whole of the Captain's
 *   sentence about a new officer chopping trees, expressed as data: a clearing
 *   now comes from a structure that EXISTS (structureClearings), so an unbuilt
 *   lot has none. It also deletes the old "mown circle around nothing" defect
 *   at its root rather than era-gating around it.
 *   THE QUAYSIDE DISCS (warehouse 160, harbourmaster 110). Both are smaller
 *   than the clearing their own structure now cuts, so they were a second
 *   number saying the same thing less well.
 *
 * WHAT STAYED: the square, the law ground, the works ridge, the field terrace,
 * the training yard, the observatory rise and the signals crossroads — each a
 * civic ground the dressing stage furnishes but no single building owns — plus
 * the pond, which is not a clearing at all (see `cut: 'natural'`).
 *
 * ERA-GATED, as before, and now for a stronger reason than "a bald patch is
 * visible": a camp that has not cut the works ridge has TIMBER standing on it,
 * and the era gate is what makes camp read as young rather than as empty.
 */
const CIVIC_CLEARINGS: readonly {
  at: Point
  r: number
  role: string
  villageOnly: boolean
  cut: CutBy
}[] = [
  { at: SQUARE, r: 300, role: 'square', villageOnly: false, cut: 'felled' },
  { at: { x: 1200, y: 400 }, r: 240, role: 'law_ground', villageOnly: true, cut: 'felled' },
  { at: { x: 1830, y: 800 }, r: 290, role: 'works_ridge', villageOnly: true, cut: 'felled' },
  { at: { x: 1620, y: 1180 }, r: 300, role: 'field_terrace', villageOnly: true, cut: 'felled' },
  { at: { x: 760, y: 470 }, r: 210, role: 'training_yard', villageOnly: true, cut: 'felled' },
  { at: { x: 960, y: 372 }, r: 170, role: 'observatory_rise', villageOnly: true, cut: 'felled' },
  { at: { x: 840, y: 1226 }, r: 150, role: 'signals_cross', villageOnly: true, cut: 'felled' },
  // The pond is WATER, and water is not a clearing: no timber ever stood here,
  // so it is a hole in the canopy with no stumps at its edge and no era term.
  // Morphology, exactly like the coastline.
  { at: { x: 612, y: 1086 }, r: 190, role: 'pond', villageOnly: false, cut: 'natural' },
]

/**
 * How much open ground the landing itself is.
 *
 * THE ONE EXCEPTION ON A HATCHED ISLAND. The Captain's picture is "landing on
 * an island that hasn't been maintained" — dense wilderness everywhere except
 * the point you came ashore at. That point is the cove, and it is open because
 * it is a beach, not because anyone felled it: `natural`, rawness 0, no record.
 */
export const LANDING_CLEARING = 210

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
  /**
   * HOW FAR ALONG this particular thing is — `countOf(state, role)`, its own
   * ladder's visible rung index, and 0 for a member of a count ladder.
   * ./clearing sizes its clearing by this.
   */
  rung: number
  /**
   * HOW LONG IT HAS STOOD, in rungs. Equal to `rung` for a tier ladder; for the
   * i-th of n identical things off a count ladder it is `seniority(i, n)`.
   * ./clearing ages its rim by this — see StructureCut for why one number could
   * not do both jobs.
   *
   * CARRIED rather than re-derived, for the same reason PlacedItem carries its
   * size: the caller knows something the reader cannot look up (which of six
   * dwellings this is), and a consumer that recomputed it would be measuring a
   * different world from the one the rules built.
   */
  age: number
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
  /**
   * The authored district furniture — see ./dressing.
   *
   * SEPARATE FROM `structures` AND FROM `scatter`, because it is neither. A
   * structure is strict and is never dropped for being crowded; a scatter item
   * is sampled by a density field and has no authored spot. Dressing is
   * authored AND droppable, and folding it into either list would take away
   * exactly the property that distinguishes it.
   */
  dressing: DressItem[]
  /**
   * The cleared ground — what was cut, how raw its rim is, and how much timber
   * is left. EMITTED rather than re-derived, for the same reason `regions` is:
   * the renderer wants to shade the treeline and the checks want to ask whether
   * a frame's canopy matches its era, and a second module computing "where the
   * clearing is" would be a second answer to the question the planting already
   * answered.
   */
  cleared: ClearedGround
  /** Cleared discs, exported so the renderer can debug-draw the field. */
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
/** Loose ground cover. The deadwood LEFT here on 2026-07-27 — see RECORD_KINDS. */
const NATURE_GROUND = ['rock_small', 'rock_cluster']
const SHORE_KINDS = ['reeds', 'rock_small', 'rock_cluster']
const VERGE_KINDS = ['flowers_white', 'flowers_yellow', 'bush_round', 'rock_small']

/**
 * THE FELLING RECORD — what an axe leaves behind, at a clearing's rim.
 *
 * `tree_stump` and `fallen_log` used to ride in NATURE_GROUND, scattered at
 * random through the interior at the same density as rocks. That is the exact
 * reading the Captain's direction rejects: they are not ground cover, they are
 * the record of the cut, and scattering them anywhere says nothing about where
 * the treeline moved. `wood_pile` joins them at village and only at village —
 * see the `felled` pass for the two independent checkers that floor it there.
 */
const RECORD_KINDS = ['tree_stump', 'fallen_log']

/**
 * How far inside the waterline the wood begins.
 *
 * Inside the belt's own outermost inset (22px, plus up to 26px of jitter), so
 * the wood and the belt MEET rather than leaving a bare ribbon between them.
 * Beyond it is beach, wind-shorn rock and the belt's business.
 */
const WOOD_FRINGE = 56

/**
 * The canopy's exclusion radius at full timber and at bare clearing.
 *
 * 72px against a 150px oak is a CLOSED CANOPY — crowns overlap, which is what a
 * wood is and what the old 104px (against a density field that rarely rose
 * above 0.3, so an effective ~240px) could never produce. The max is what the
 * spacing opens to across a clearing's edge band, so the treeline thins out
 * instead of stopping dead.
 *
 * THE CAP IS A CEILING, NOT A TARGET. It exists so a degenerate coastline
 * cannot make the sampler run away; the number of trees on a real island is set
 * by the spacing and by how much ground is left standing, which is the whole
 * point. Re-measured 2026-07-27 over 8 seeds per era, belt and scatter
 * together: camp 180-231 canopy sprites, hamlet 86-119, town 68-104,
 * beyond_bay 53-96 — every one an order of magnitude inside the cap, so the cap
 * is not what separates the eras. (The numbers this docstring used to carry,
 * 430-500 and 300-360, no longer describe the composition and are corrected
 * rather than kept: a claim the reader can disprove in one command teaches them
 * to distrust the rest of the file.)
 */
const TREE_SPACING_MIN = 72
const TREE_SPACING_MAX = 250
const TREE_CAP = 620

/**
 * How much ground two trees may share — ring.ts's lesson, one level over.
 *
 * "Two buildings sharing a ground diamond are stacked and it is a defect; two
 * trees 40px apart with interpenetrating canopies are a FOREST, and holding a
 * belt to building-grade exclusivity thins it into a dotted line" (RING_SPACING).
 * The wood is now the largest population on the island and it was being held to
 * the scatter default of 0.05 — measured, that was the binding constraint on the
 * canopy, not the Poisson radius.
 *
 * IT IS SAFE HERE BECAUSE THE CLEARING IS WHAT PROTECTS A BUILDING NOW, not this
 * number. `wooded` refuses every point inside a clearing, and a clearing is at
 * least CLEAR_BASE past a structure's half-width, so a tree cannot come near one
 * however loose this is. The unit arm measures tree-against-structure overlap
 * across the composed islands and holds it at zero, which is the sensor for that
 * claim rather than the argument for it.
 *
 * AND IT COVERS THE SCATTER ONLY, which is half the trees. The BELT is a second
 * population placed by ./ring against its own rules, and until 2026-07-27 no
 * arm read it: measured then, 27 belt-vs-structure pairs over 0.04 with a worst
 * of 0.131, because the belt was calling `groundTaken` at the tree-vs-tree
 * default. Both halves are now measured, and the belt has its own strict bar
 * (RING_BUILT_OVERLAP). A claim about "the trees" that only counts one of the
 * two populations that plant them is the coverage-bound failure, not a pass.
 */
const WOOD_OVERLAP = 0.2

/** The record's own spacing: stumps cluster, they do not space like oaks. */
const RECORD_SPACING_MIN = 46
const RECORD_SPACING_MAX = 200
const RECORD_CAP = 130

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
  //
  // A LANE IS WORN BY THE PLACE AT ITS FAR END (see ./lanes). The predicates
  // handed over are the SAME ones the structure stage is gated on, five stages
  // down — `presentRung` for a tier ladder, a positive count for a count
  // ladder — so the road to the library and the library itself can never
  // disagree about whether there is a library. Reading anything else here
  // would be a second state source for one fact.
  const laneDemand = laneDemandFrom(state)
  const carriageways = buildLanes(state.road, onLand, laneDemand)
  const laneKeys = new Set(carriageways.map((l) => l.key))
  const laneWidthOf = new Map(carriageways.map((l) => [l.key, l.width]))

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
  /** The usage rung of the place a lot group's carriageway serves. */
  const laneUsage = (group: string): number => {
    const ladder = laneTrafficLadder(LOT_GROUP_LANE[group])
    return ladder === null ? 0 : laneDemand.usage(ladder)
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
  const built: {
    key: string
    obj: string
    kind: string
    lot: Lot
    group: string
    /** Its own ladder's rung — 0 for a member of a count ladder. */
    rung: number
    /** How long this one has stood, in rungs — see `seniority`. */
    age: number
  }[] = []
  const dwellings = Math.min(countOf(state, 'officer_dwellings'), lots.residential.length)
  for (let i = 0; i < dwellings; i++) {
    const key = `residential-${i}`
    built.push({
      key,
      obj: 'officer_dwelling',
      kind: dwellingKind(numSeed, state.era, key),
      lot: lots.residential[i],
      group: 'residential',
      // A COUNT LADDER MEMBER: no rung of its own, so it clears the baseline.
      rung: 0,
      age: seniority(i, dwellings),
    })
  }
  for (const [key, obj] of [
    ['memory', 'library'],
    ['works', 'workshop'],
    ['fields', 'outbuildings'],
  ] as const) {
    if (isBuilt(state, obj)) {
      const rung = countOf(state, obj)
      built.push({ key, obj, kind: obj, lot: lots[key][0], group: key, rung, age: rung })
    }
  }

  const driveways: Driveway[] = []
  const driveLanes: Lane[] = []
  for (const b of built) {
    const carriageway = LOT_GROUP_LANE[b.group]
    if (!laneKeys.has(carriageway)) continue
    // ITS OWN BUILDING'S USAGE, not the org's road rung — the same ladder that
    // widened the carriageway it joins, one rung down for one door. Reading
    // `state.road` here would leave a second width rule on the network,
    // contradicting the lanes it feeds into.
    const d = driveway(
      lotDoor(b.lot),
      b.lot.road,
      laneUsage(b.group),
      laneWidthOf.get(carriageway) ?? laneWidthAt(0)
    )
    const lane = drivewayLane(d, `drive-${b.key}`, onLand, state.road)
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
    lot?: Lot,
    /** Defaults to the object's OWN ladder rung; see Structure.rung. */
    rung: number = countOf(state, role),
    /** Defaults to the rung, which is right for every tier ladder. */
    age: number = rung
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
    const settled = clearOfRegions(p, size, plotGround, laneField, onLand, occupied)
    occupied.push({ at: settled, size })
    const s: Structure = { kind, role, at: settled, flip, size, lot, rung, age }
    structures.push(s)
    return s
  }

  if (isBuilt(state, 'great_house')) {
    put('great_house', 'great_house', lots.centre[0].c, lotFlip(lots.centre[0]), lots.centre[0])
  }
  if (isBuilt(state, 'well')) put('well', 'well', { x: 1050, y: 970 }, false)
  if (isBuilt(state, 'firepit')) put('firepit', 'firepit', SQUARE, false)
  // THE MARKET STALL MOVED TO ./dressing, and the gate it moved off was wired
  // to nothing: `isBuilt(state, 'market_stall')` asked a ladder that does not
  // exist (cabinet/world/growth-ladders.yml has 29 ladders and no
  // `market_stall`), so the predicate was false on every state and the stall
  // could never draw. compose.py:966 gates it on the era alone.
  // ONE SPRITE PER LOT, not one sprite six times — see dwellingKind.
  for (const b of built) put(b.kind, b.obj, b.lot.c, lotFlip(b.lot), b.lot, b.rung, b.age)

  // The quayside buildings stand on LAND above the wharf (compose.py:1165-1176)
  // and go through the same door as every other building — so a warehouse on a
  // seed whose cove ate its shore is DROPPED, not floated.
  const quayside: Structure[] = []
  const warehouseSites = harbour?.warehouseSites ?? []
  for (let i = 0; i < warehouseSites.length; i++) {
    // Warehouses come off a COUNT ladder exactly as the dwellings do, so each
    // clears the baseline, and the first shed on the quay is the old one while
    // the newest still has raw stumps round it — see `seniority`.
    const s = put(
      'warehouse',
      'warehouse',
      warehouseSites[i],
      false,
      undefined,
      0,
      seniority(i, warehouseSites.length)
    )
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

  // ---- 8a. the clearing ----------------------------------------------------
  // THE ISLAND IS OVERGROWN AND THIS IS WHAT WAS CUT OUT OF IT (Captain
  // 2026-07-27). Everything below plants against `timber` — what is LEFT — so
  // this stage is the one that decides what the world looks like, and it can
  // only run now, because a clearing belongs to a structure that landed.
  //
  // IT RUNS BEFORE THE DRESSING, which it did not until 2026-07-27, and the
  // move is what lets the district furniture obey the model instead of merely
  // being described by it. Its inputs are the paint (stage 5), the harbour
  // (6), the structures (7) and the lighthouse (8) — never the dressing — so
  // nothing is lost by asking the question earlier, and what is gained is that
  // `dressSettle` can refuse a spot in standing timber. Measured before the
  // move, over 20 hamlet islands: 648 pieces of village furniture stood in
  // uncut wood, 129 of them under fully closed canopy and one fence run 188px
  // deep into it.
  const inWater = waterField(paint)
  // GROWN BY THE KERB, not the bare blob: the paint bleeds past its own
  // boundary and a thing standing in the bleed is off the surface to the layout
  // and on it to the frame (see PAINT_KERB).
  const onPaving = grownField(paint, ['plaza', 'crop', 'ploughed'], PAINT_KERB)
  // ONE FIELD, built once and handed to every consumer: the clearing, the belt
  // and the scatter must agree on where the deck is, and two `rectField` calls
  // off the same rect is one call away from being two different rects.
  const onQuay = rectField(harbour?.wharf?.rect ?? null)
  const civicScale = CIVIC_ERA_SCALE[state.era] ?? 1
  const civicRawness = rawnessOfEra(state.era)
  const clearings: Clearing[] = [
    // EVERY STRUCTURE THAT WAS ACTUALLY BUILT, at the radius its own rung
    // earned — and NOTHING for a lot nobody has built on, which is the whole
    // inversion: an empty lot is forest until an officer arrives and cuts it.
    // `s.rung` is the object's own visible rung index for a tier ladder and its
    // seniority in the row for a count ladder (see Structure.rung).
    ...structureClearings(
      structures.map((s) => ({
        at: s.at,
        size: s.size,
        role: s.role,
        rung: s.rung,
        age: s.age,
      }))
    ),
    ...CIVIC_CLEARINGS.filter((d) => village || !d.villageOnly).map((d) => ({
      // SNAPPED, like every other anchor: a clearing centred in the sea clears
      // sea, and the timber it was meant to have felled is still standing in
      // the village.
      at: anchor(d.at),
      // The civic grounds have no rung of their own, so the ERA is their
      // measurement — a camp has a trodden gap where a town has a paved square.
      // The pond is exempt because it is not a clearing: water is morphology
      // and does not grow with the org.
      r: d.cut === 'natural' ? d.r : d.r * civicScale,
      rawness: d.cut === 'natural' ? 0 : civicRawness,
      role: d.role,
      cut: d.cut,
    })),
    // THE LIGHTHOUSE POINT (compose.py:905) — the belt frames the tower, it does
    // not swallow it. Centred on where the tower actually ENDED, not on the site
    // it was walked from: the structure rules may have moved it off a lane, and
    // a clearing round the old spot would leave the tower in the trees and a
    // bald circle beside it. It rides ALONGSIDE the lighthouse's own structure
    // clearing rather than replacing it, so the union takes whichever is larger.
    ...(lighthouse
      ? [
          {
            at: lighthouse.at,
            r: lighthouse.clearing,
            rawness: rawnessOfRung(countOf(state, 'lighthouse')),
            // (a tier ladder, so its rung IS its age)
            role: 'lighthouse_point',
            cut: 'felled' as CutBy,
          },
        ]
      : []),
    // THE COUNT-GATED OUTBUILDINGS — the windmill, the kiln and the coop.
    //
    // THEY ARE BUILDINGS THAT RIDE IN THE DRESSING, which is a fact about which
    // list they land in and not about what they are, and it left them as the
    // one built class with no ground of its own: measured 2026-07-27, 12 of
    // them over 80 composed islands stood in standing timber, up to 60px
    // outside the nearest rim. They cannot be dropped for it — each is a
    // measured count and hiding one is the failure the state law names — so
    // they get what every other built thing gets, a clearing.
    //
    // CENTRED ON THE AUTHORED SPOT, not on where the item settled, because the
    // settle happens one stage later; the radius carries CLEAR_BASE past the
    // sprite's half width, which is the slack that absorbs the settle. The
    // offsets are read from the same exported table the dressing places from,
    // so the two cannot drift apart.
    ...COUNT_GATED_BUILDINGS.filter(
      (b) => village && countOf(state, b.ladder) >= b.atLeast
    ).map((b) => {
      const base =
        b.from === 'works'
          ? (structures.find((s) => s.role === 'workshop')?.at ?? anchor({ x: 1830, y: 800 }))
          : (structures.find((s) => s.role === 'outbuildings')?.at ?? anchor({ x: 1620, y: 1180 }))
      return {
        at: anchor({ x: base.x + b.dx, y: base.y + b.dy }),
        // A COUNT LADDER, so each member clears the baseline — the same rule
        // `structureClearings` applies to the dwellings and the warehouses.
        r: clearingRadius(sizeOf(b.kind), 0),
        rawness: rawnessOfRung(countOf(state, b.ladder) - b.atLeast),
        role: b.kind,
        cut: 'felled' as CutBy,
      }
    }),
    // THE LANDING. The one place a hatched island is open on day zero, and it is
    // open because it is a beach: natural, rawness 0, no felling record.
    ...(coast.cove
      ? [
          {
            at: { x: coast.cove.x, y: coast.cove.y },
            r: LANDING_CLEARING,
            rawness: 0,
            role: 'landing',
            cut: 'natural' as CutBy,
          },
        ]
      : []),
  ]
  const cleared = buildClearedGround(clearings, {
    lanes: laneField,
    onPaving,
    inWater,
    onQuay,
  })

  // ---- 8b. district dressing ----------------------------------------------
  // BEFORE the planting and AFTER every building, which is the only order that
  // works: a bench must lose to a warehouse and win against a fern. The ring
  // and the scatter both sample `occupied`, so pushing the dressing into that
  // book here is what stops a tree growing through the market stall.
  //
  // Decoration is DROPPED rather than stacked (dropIfBlocked), which is the
  // opposite of the structure rule directly above and deliberately so: a
  // measured building that cannot find ground is a fact about the org and must
  // still be reported, while a barrel that cannot find ground is a barrel
  // nobody will miss.
  /**
   * VILLAGE FURNITURE STANDS ON GROUND SOMEBODY CUT — the Captain's model, as
   * a placement rule rather than as a paragraph.
   *
   * A bench, a fence run, a water trough and a veg garden are the furniture of
   * a settlement, and a settlement stands in a clearing. Authored offsets are a
   * WISH (see the module header): the fields district wishes its fence to run
   * 320-352px out from the barn, and at hamlet the ground that was cut for that
   * farm is 174px across, so the outer sections of that wish are in the wood.
   * They are DROPPED, exactly as a section that would stand on a carriageway is
   * dropped — the fence stops at the treeline, and the gap it leaves IS the
   * edge of the cleared field. As the org matures the clearing opens and the
   * same authored run reaches further, which is the direction's own sentence:
   * the enclosure grows because the treeline receded.
   *
   * THE BAR IS THE TREELINE'S MIDPOINT, not the rim — see FURNITURE_MAX_TIMBER
   * for the measurement that made a hard rim wrong (it deleted a bench standing
   * a tenth of a pixel outside its district).
   *
   * ONLY `village_life`. The ladder items — law_plot, composter, pens,
   * observatory, the count-gated buildings — go through `ctx.settle` directly
   * with their own role, and they are EXEMPT because dropping one would hide a
   * count, which is the one thing the state law forbids outright. The landing
   * is exempt for a different reason: `dressLanding` dresses a beach, and a
   * beach is not timber that anyone felled (it is `cut: 'natural'`), so the
   * cut-ground question is the wrong question there.
   */
  const dressSettle: Settle = (kind, role, at, flip, dopts) => {
    const size = sizeOf(kind)
    const p = placeOnGround(at, size, laneField, onLand, [...occupied, ...plotGround], {
      dropIfBlocked: true,
      avoidLane: dopts?.avoidLane,
      nudge: dopts?.nudge,
      inlandTo: inland,
    })
    if (!p) return null
    // A RUN THAT MAY NOT BE NUDGED OFF A LANE MUST BE DROPPED ON ONE. Turning
    // `avoidLane` off removes the only rule that was keeping the section off
    // the road, and a fence drawn across a carriageway is a real on-road
    // defect — so the test still runs, it just drops instead of moving. That
    // gap is the gate (compose.py fence_axis).
    if (dopts?.avoidLane === false && footprintOnLane(p, size, laneField)) return null
    const settledAt = clearOfRegions(p, size, plotGround, laneField, onLand, occupied)
    // THE PLOT RULE CAN UNDO THE SETTLE, so the settle is re-asserted after it.
    // clearOfRegions searches outward for ground that is off the plough AND
    // clear of neighbours, and when it finds neither it returns the least-bad
    // compromise — which for the chicken coop was a 31% overlap with the
    // watermill kiln, caught by check_stacking on the first frame that drew
    // both. A structure has to be drawn anyway (it is a measured fact); a piece
    // of dressing does not, so here the compromise is simply refused. This is
    // the one place the dressing is STRICTER than the buildings above it, and
    // deliberately: nothing is lost by not drawing a coop, and a coop inside a
    // kiln is a defect a viewer sees instantly.
    if (dopts?.nudge !== false && maxGroundOverlap(settledAt, size, occupied) > 0.1) return null
    // THE CUT-GROUND RULE, LAST, so it judges the spot the item actually takes
    // rather than the one it asked for: the lane rule and the plot rule both
    // move a piece of dressing, and a rule applied to the wish is a rule that
    // does not hold. Refused BEFORE the occupancy book is written, so a dropped
    // item reserves nothing — a phantom occupant is a hole a tree cannot fill.
    if (role === 'village_life' && cleared.timber(settledAt.x, settledAt.y) >= FURNITURE_MAX_TIMBER)
      return null
    occupied.push({ at: settledAt, size })
    return { kind, role, at: settledAt, flip, size, overWater: false }
  }
  const roleAt = (role: string): Point | null =>
    structures.find((s) => s.role === role)?.at ?? null
  /**
   * Everything the harbour BUILT over the water, and the open-water test the
   * landing's craft are held to. One closure, built once from the wharf and
   * pier that actually exist, so the landing and auditLayout below cannot end
   * up asking two different questions about the same planks.
   */
  const harbourTimber: HarbourTimber = {
    wharf: harbour?.wharf ?? null,
    jetty: harbour?.jetty ?? null,
  }
  const dressing: DressItem[] = [
    ...dressDistricts({
      era: state.era,
      village,
      stageOf: (obj) => state.stages?.[obj],
      countOf: (obj) => countOf(state, obj),
      built: (obj) => presentRung(state, obj),
      sizeOf,
      settle: dressSettle,
      anchor,
      great: (() => {
        const g = structures.find((s) => s.role === 'great_house')
        return g ? { at: g.at, size: g.size } : null
      })(),
      lib: roleAt('library'),
      works: roleAt('workshop'),
      fields: roleAt('outbuildings'),
      square: SQUARE,
      dwellings: structures
        .filter((s) => s.role === 'officer_dwelling')
        .map((s) => ({ at: s.at, face: s.lot?.face ?? { x: 1, y: 0 } })),
      shoreAt: coast.cove ? (x: number) => shoreAt(coast, coast.cove!, x) : null,
      cove: coast.cove ? { x: coast.cove.x, y: coast.cove.y } : null,
      openWater: null,
    }),
    ...dressLanding({
      era: state.era,
      village,
      stageOf: (obj) => state.stages?.[obj],
      countOf: (obj) => countOf(state, obj),
      built: (obj) => presentRung(state, obj),
      sizeOf,
      settle: dressSettle,
      anchor,
      great: null,
      lib: null,
      works: null,
      fields: null,
      square: SQUARE,
      dwellings: [],
      shoreAt: coast.cove ? (x: number) => shoreAt(coast, coast.cove!, x) : null,
      cove: coast.cove ? { x: coast.cove.x, y: coast.cove.y } : null,
      openWater: (at, size) => inOpenWater(coast, harbourTimber, at, size),
    }),
  ]
  // The floating half of the landing occupies WATER, not ground, so it never
  // enters the occupancy book — a buoy reserves nothing a tree could want, and
  // `dressSettle` (which does add to the book) is only ever called for the
  // items that stand on land.

  // ---- 9. the book of built ground ----------------------------------------
  const districts: District[] = cleared.districts
  // The dock kit occupies ground like anything else. It is not a structure (it
  // stands on a deck over water), but the half of it that lands on the shore
  // strip is real ground a reed must not grow through — and the scatter stage
  // rejects against `occupied` at sampling time, so the book is where it goes.
  for (const item of harbour?.items ?? []) occupied.push({ at: item.at, size: item.size })
  // EVERYTHING A PERSON MADE, snapshotted before anything is planted. The
  // timber passes hold themselves to a tighter ground rule against this book
  // than against each other — see PlantCtx.builtGround.
  const builtGround: readonly Occupant[] = [...occupied]

  // ---- 10. the forest enclosure ring --------------------------------------
  // MORPHOLOGY, not doctrine, so it stands in every era: an island has a
  // treeline whether or not anyone has landed on it, on the same argument that
  // keeps the pond at camp. What the ERA changes is where it may grow — at camp
  // almost nothing has been cut, so the belt is free to close over ground a
  // town has since felled.
  //
  // IT IS NOT THE WHOLE FOREST ANY MORE, and that is the inversion. The belt
  // used to be the island's canopy because the interior was a sparse gradient;
  // now it is the OUTERMOST BAND of a wood that runs right across the landmass
  // (see plant()'s timber passes). It keeps its own module because it is a
  // different kind of thing — walked by angle in depth sublayers, so the shore
  // reads as enclosed rather than as a lawn that happens to end.
  //
  // BEFORE the general planting and AFTER the structures: the belt takes the
  // coastal band first, and the timber passes then fill the interior behind it
  // against an occupancy book the ring has already written into.
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

  // ---- 11. the standing timber, and the record of what was cut ------------
  const scatter = plant(numSeed, {
    space,
    coast,
    laneField,
    occupied,
    cleared,
    builtGround,
    inWater,
    onPaving,
    // The plantable MARGIN around the water, which is wider than the painted
    // sand fringe — see grownField in ./paint for why the two differ.
    onBank: grownField(paint, ['pond', 'stream'], REED_MARGIN),
    // NOTHING IS PLANTED ON THE WHARF. This port's own term, on the same
    // argument the paving term needed: a deck is a surface, and no clearing
    // reaches it (the nearest is the square's, 400px north). The shore band
    // runs along the waterline, which is exactly where the deck is.
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
    dressing,
    cleared,
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
 * (the legacy island-layout.ts, deleted 2026-07-29:
 * `V.cottage[fnv1a(`${slug}:roof`) % V.cottage.length]`).
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
  /** What was cut, how raw each rim is, and how much timber is left. */
  cleared: ClearedGround
  /**
   * Everything a PERSON put on the island — structures, dressing, dock kit —
   * as it stood before anything was planted.
   *
   * A SECOND, TIGHTER BOOK for the timber passes. The wood runs at a loose
   * ground-overlap bar because a forest is trees standing in each other's
   * canopies; a tree standing in a WALL is a defect at any bar. See
   * ScatterOptions.strictOccupied for the willow that proved it.
   */
  builtGround: readonly Occupant[]
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
 * THE PLANTING PASSES — the standing timber first, then the record of what was
 * cut, then the dressing that only a settled place has.
 *
 * Each pass reads the occupancy the previous ones wrote, so a bush cannot land
 * inside a tree. The ORDER inside the timber block is deliberate: the canopy
 * claims the ground, the felling record claims the rim before the understory
 * can crowd it out, and the light-loving passes fill in behind both.
 */
function plant(seed: number, ctx: PlantCtx): PlacedItem[] {
  const out: PlacedItem[] = []
  /**
   * NOTHING GROWS ON CUT GROUND. compose.py:1213 free() was
   * `near_path(34) or in_water(x,y)` plus a keep-out disc; the disc term is now
   * `cleared.isCleared`, which is the same geometry read the other way round —
   * ground is bare because somebody felled it, not because a rule forbids
   * planting there.
   *
   * THE THREE SURFACE TERMS ARE REDUNDANT WITH `isCleared` TODAY, and they stay.
   * `buildClearedGround` folds the paving, the water, the deck and the lane
   * reach into `clearedAt`, so each `!ctx.…` below is currently implied. They
   * are kept because they are the terms that were MEASURED to matter (9 items in
   * a crop plot across 80 seeds; reeds and shore rocks on the deck), and because
   * a redundancy that one edit to LANE_CLEAR_REACH would end is not a redundancy
   * worth deleting. The one that is NOT redundant either way is the 34px lane
   * rule, which is narrower than LANE_CLEAR_REACH and therefore never decides
   * anything on its own — stated so nobody later reads it as the rule that keeps
   * planting off the road.
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
   * What is NOT quiet is the identical term in ring.ts — deleting it there turns
   * four arms red, because the belt walks the coastal band at a fixed angular
   * step and does not care how narrow a river is.
   */
  const free = (x: number, y: number) =>
    !ctx.laneField.nearLane(x, y, 34) &&
    !ctx.inWater(x, y) &&
    !ctx.onPaving(x, y) &&
    !ctx.onQuay(x, y) &&
    !ctx.cleared.isCleared(x, y)

  /**
   * THE WOOD: everywhere on the island that nobody has cut.
   *
   * THIS IS THE INVERSION, in one predicate. It used to be `coast.isInner` —
   * `d < landEdge - 190` — which confined the general planting to the deep
   * interior while the density field made that interior the SPARSEST part of
   * the island. An island whose trees are a coastal ring around a thin middle
   * is wilderness-as-decoration, and the Captain's ruling is that wilderness is
   * the island's default state. So the wood now runs from the belt right across
   * the landmass, stopping only at the shore fringe, the water and the cut.
   *
   * WOOD_FRINGE, not 0: the last stretch before the waterline is beach and
   * wind-shorn rock, and it belongs to the belt's outermost sublayer and the
   * shore pass. 56px is inside the belt's own outermost inset (22 + up to 26 of
   * jitter), so the two populations meet rather than leaving a bare ribbon.
   */
  const cx = ctx.space.cx
  const cy = ctx.space.cy
  const insetFrom = (inset: number) => (x: number, y: number) => {
    const ang = Math.atan2((y - cy) / 0.92, x - cx)
    const d = hypot(x - cx, (y - cy) / 0.92)
    return d < ctx.coast.edgeAt(ang) - inset
  }
  const insideFringe = insetFrom(WOOD_FRINGE)
  const wooded = (x: number, y: number) => insideFringe(x, y) && free(x, y)

  const pass = (
    tag: string,
    kinds: readonly string[],
    pick: (x: number, y: number) => boolean,
    density: DensityField,
    rMin: number,
    rMax: number,
    cap: number,
    frac?: number
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
      frac,
      // and the CHOSEN sprite is re-tested against both rules — see
      // ScatterOptions.sizeOf for the measurement that made this necessary.
      sizeOf: ctx.sizeOf,
      // A LOOSE bar against other plants and a TIGHT one against anything a
      // person built. Passed on EVERY pass, not only the loose ones: a rule
      // that is only wired where it currently matters is a rule the next edit
      // silently drops.
      strictOccupied: ctx.builtGround,
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

  // ---- THE RECORD OF THE CLEARING ----------------------------------------
  // Stumps, felled logs and (once there is somebody to stack it) sawn timber,
  // at the BOUNDARY between cut ground and standing wood. Captain 2026-07-27:
  // "the stumps, the felled logs and the woodpiles are then not decoration:
  // they are the RECORD of that clearing, and they belong at the edge of each
  // cleared area."
  //
  // NOT free()-GATED, deliberately, and for the same reason the bank and the
  // verge passes are not: a stump stands where the tree stood, which is inside
  // the ground that was cleared. free() forbids exactly that. The rim band is
  // its own admissibility rule and it carries the surface terms itself.
  //
  // DENSITY IS `recordAt` = how close to a rim x how raw that rim is, so the
  // pass thins as an org matures without anything era-gating it: a camp's one
  // clearing was cut this week and is ringed with raw stumps, a beyond_bay
  // town's clearings have had four rungs to grub theirs out and grow the edge
  // over. It also goes to zero where two clearings merged, because the arc
  // between them stopped being a boundary (RECORD_SWALLOWED_AT).
  //
  // WOOD_PILE ONLY AT VILLAGE, and that is not a taste call: check_era floors
  // both wood_pile and crate_single at hamlet, and `wood_pile` is justified by
  // the VILLAGE_LIFE class, so a woodpile on a camp frame is an orphan and
  // check_state_traceable goes red. Sawn timber stacked in a pile is a
  // settlement's output; a stump and a felled log are the cut itself, and both
  // are on ambient-nature.txt, so both stand at every era.
  const record = (x: number, y: number) =>
    ctx.cleared.recordAt(x, y) > 0 &&
    !ctx.laneField.nearLane(x, y, 34) &&
    !ctx.inWater(x, y) &&
    !ctx.onPaving(x, y) &&
    !ctx.onQuay(x, y)
  pass(
    'felled',
    ctx.village ? [...RECORD_KINDS, 'wood_pile'] : RECORD_KINDS,
    record,
    ctx.cleared.recordAt,
    RECORD_SPACING_MIN,
    RECORD_SPACING_MAX,
    RECORD_CAP
  )

  // ---- THE STANDING TIMBER ------------------------------------------------
  // The canopy at the tightest spacing of any pass: an island nobody has
  // maintained is WOOD, and the trees are the thing the rest of the planting
  // fills in around. `timber` is 1 across every acre nobody has cut, so the
  // exclusion radius sits at TREE_SPACING_MIN there and opens out to
  // TREE_SPACING_MAX across each clearing's edge band — which is what makes a
  // clearing read as a thinning treeline rather than as a stamped circle.
  //
  // THAT BAND IS ON THE STANDING SIDE OF THE RIM, and it was on the cut side
  // until 2026-07-27, where this pass could never reach it: `wooded` refuses
  // every point `isCleared` accepts and the old field was non-zero on exactly
  // that set, so `timber()` was the constant 1 over this pass's whole domain
  // (240,000 samples, one distinct value) and TREE_SPACING_MAX decided nothing
  // — collapsing it 250 -> 72 left twenty islands byte-identical. See
  // CLEARING_EDGE_BAND. The arm that now holds it is "the wood THINS toward a
  // clearing", which counts realised canopy per unit of plantable area either
  // side of one band width.
  //
  // AFTER THE RECORD, and that order was MEASURED, not assumed. With the canopy
  // first the rim band is full of oaks before the record pass samples, and
  // sampling-time rejection then drops almost every stump: 3-6 record items per
  // camp island against 30-40 with the order this way round. The rim is a thin
  // annulus and the wood is everything else, so whichever pass goes first gets
  // it — and the record is the smaller, more specific claim.
  pass(
    'trees',
    NATURE_TREES,
    wooded,
    ctx.cleared.timber,
    TREE_SPACING_MIN,
    TREE_SPACING_MAX,
    TREE_CAP,
    WOOD_OVERLAP
  )

  // ---- WHAT GROWS UNDER AND BETWEEN THE TREES -----------------------------
  pass('shrubs', NATURE_SHRUBS, wooded, ctx.cleared.timber, 62, 170, 190)
  // Light reaches the ground where the canopy has been opened, so the flowers
  // run the OTHER way to the timber — thickest against a clearing's edge,
  // thinnest under closed canopy. The old field was `1 - wildness*0.5`, which
  // meant the same thing about the old field and the opposite thing about the
  // island: wildness was highest at the COAST, so flowers pooled inland.
  pass('flowers', NATURE_FLOWERS, wooded, (x, y) => 1 - ctx.cleared.timber(x, y) * 0.65, 58, 150, 110)
  // Mushrooms and toadstool clumps are village-adjacent dressing in the
  // reference's AMBIENT set; the rocks are not. The deadwood that used to ride
  // in this pass moved to the felling record above, where it means something.
  pass('ground', NATURE_GROUND.concat(ctx.camp ? [] : ['mushrooms']), wooded, ctx.cleared.timber, 104, 260, 40)

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
      !ctx.cleared.isCleared(x, y)
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
  /** Declared `overWater` while standing on the island's ground. */
  waterClaim: { kind: string; at: Point }[]
  /** Declared afloat while drawn on land or on the harbour's own timber. */
  beached: { kind: string; at: Point }[]
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

  // THE `overWater` CLAIM, RE-MEASURED. It was a DECLARATION on the vessel and
  // on every craft the landing draws — hard-coded `true`, checked by nothing —
  // until the Captain returned a frame with the packet lying on the planks. The
  // flag means one thing only, "this does not stand on the island's ground", so
  // the arm is `overWater === !landAt(base)` and it is asked of every emitter
  // that carries the flag. It is deliberately the WEAK arm: it passes for a
  // crate on the deck, which is correct, and it passed for the beached boat
  // too, which is why the second arm below exists.
  const waterClaim: { kind: string; at: Point }[] = []
  const claimers: { kind: string; at: Point; overWater: boolean }[] = [
    ...(h?.items ?? []),
    ...layout.dressing,
  ]
  for (const c of claimers) {
    if (c.overWater !== !layout.coast.landAt(c.at.x, c.at.y)) {
      waterClaim.push({ kind: c.kind, at: c.at })
    }
  }

  // NOTHING THAT FLOATS IS DRAWN STANDING ON TIMBER — the arm the beached
  // vessel needed and did not have. The set is everything that declares
  // `afloat` plus every mooring post, which is in the water by construction and
  // was found on the wharf on 111 of 6400 measured cases; the test is the
  // sprite's own CONTACT PATCH (../projection's ground diamond, the same one
  // the lane and stacking rules use) against `inOpenWater`, which is the same
  // function the emitters checked before emitting. Asking about the base point
  // alone is exactly what let the defect through: the vessel's base sat 82px
  // clear of the deck it was drawn across.
  //
  // The dock kit is NOT in this set and must not be: a crate on the wharf is
  // cargo, and an arm that called it beached would be a sensor arguing with the
  // thing it measures.
  //
  // RUN WHETHER OR NOT THERE IS A HARBOUR. A cove whose shore has fewer than
  // four sampled columns builds no harbour at all, and the landing still
  // dresses that beach — gating this arm on `h` would have made the one case
  // with no wharf to check the one case with no check.
  const beached: { kind: string; at: Point }[] = []
  const timber: HarbourTimber = { wharf: h?.wharf ?? null, jetty: h?.jetty ?? null }
  const craft: { kind: string; at: Point; size: Footprint }[] = [
    ...(h?.items ?? []).filter((i) => i.afloat),
    ...layout.dressing.filter((d) => d.afloat),
    ...(h ? h.moorings.map((m) => ({ kind: 'mooring_post', at: m, size: h.mooringSize })) : []),
  ]
  for (const c of craft) {
    if (!inOpenWater(layout.coast, timber, c.at, c.size)) beached.push({ kind: c.kind, at: c.at })
  }
  return { onLane, stacked, inWater, outsideHarbour, waterClaim, beached }
}

export * from './space'
export * from './coastline'
export * from './lanes'
export * from './lots'
export * from './driveways'
export * from './clearance'
export * from './clearing'
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
