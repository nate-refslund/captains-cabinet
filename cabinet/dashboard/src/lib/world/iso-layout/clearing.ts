/**
 * CLEARING — the island is OVERGROWN, and every structure stands in ground that
 * was cut for it.
 *
 * CAPTAIN DIRECTION 2026-07-27, verbatim: *"so much more overgrown for camp - as
 * if everything has been overgrown (like landing on an island that hasn't been
 * maintained). and when camp is expanding, for example with new officers that
 * should mean the new officer spawns and then starts chopping trees and building
 * his/her cabin/camp/house. so the island naturally expands by chopping trees and
 * making space for other things to appear/be built."*
 *
 * WHAT THIS INVERTS. Until this module the island's default state was grass:
 * wilderness was decoration placed AROUND the structures, the forest was a
 * coastal framing belt, and the keep-out discs were exclusions that stopped a
 * shrub landing on a roof. Growth meant buildings accumulating on a lawn.
 * Measured on that model, canopy coverage was 0.42 at camp and 0.25 / 0.25 /
 * 0.25 at hamlet / town / beyond_bay — three eras that a viewer cannot tell
 * apart, and a camp that read as "hamlet minus things" rather than as young.
 *
 * WHAT IT IS NOW. Timber is the DEFAULT and clearing is SUBTRACTIVE. The
 * keep-out discs survive as the same geometry with a better meaning: they are
 * cleared ground, which is WHY they exist. A structure's clearing GROWS WITH ITS
 * RUNG, so maturity reads as the treeline receding rather than as more roofs;
 * and the stumps, the felled logs and the woodpiles are not decoration but the
 * RECORD of the cut, which is why they belong at the clearing's rim.
 *
 * THREE KINDS OF CUT GROUND, and the difference decides what leaves a record:
 *   FELLED — a structure's own clearing, and the authored civic grounds (the
 *     square, the works ridge, the training yard). Somebody took an axe to
 *     these, so they carry a rim of stumps whose rawness falls as the rung
 *     rises: a camp's one clearing is raw, a beyond_bay town's are long settled.
 *   SURFACE — the lanes, the paved plaza, the tilled plots, the wharf deck.
 *     Cut ground, so no timber stands on them; but their edges are AUTHORED and
 *     fixed rather than a treeline that moved, so they leave no felling record.
 *     A road that gained a stump rim at every verge would bury the road, and
 *     the verge pass already dresses that boundary.
 *   NATURAL — the pond and the landing beach. Timber never stood here, so there
 *     is nothing to have felled: they are holes in the canopy, at rawness 0.
 *
 * WHY THE RUNG AND NOT THE ERA, for a structure. Era styles a thing, rung
 * measures it, and era may never hide a count — so the quantity that grows must
 * be the object's own. `countOf(state, role)` is the visible RUNG INDEX for
 * every ladder (iso-scene.layoutStateFrom writes `counts[name] = el.rung`), so
 * the great house at its top rung cuts more ground than the log cabin that
 * stood there at camp, by the object's own measurement rather than by the era
 * around it. An object with no ladder of its own — an officer dwelling, whose
 * ladder counts HOUSES and not how far one house has come — reads rung 0 and
 * clears its baseline, which is the honest answer: a count ladder says how
 * MANY, so it must show as more clearings and never as bigger ones.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import type { Footprint } from './clearance'
import type { LaneField } from './lanes'
import type { DensityField, District } from './scatter'
import { clamp01, hypot, type Era, type Point } from './space'

/**
 * The vertical squash of a ground disc on the 2:1 projection.
 *
 * THE SAME 1.35 THE PLANTING PREDICATE ALREADY USED (compose.py:1211-1213, via
 * index.ts's old `inDistrict`). A disc on the ground projects flattened, so a
 * circular test in screen space would reserve a tall oval nobody cut. It is
 * imported by nobody and re-typed by nobody: the one place a clearing's extent
 * is decided is this file.
 */
export const CLEARING_SQUASH = 1.35

/**
 * How far OUTSIDE a clearing's rim the canopy closes again, in layout px.
 *
 * This band IS the treeline, and it sits on the STANDING side of the rim —
 * which is a correction, not a restatement. It used to be described as running
 * INWARD ("outside the rim the canopy is closed; inside it the density field
 * falls to zero"), and that band was unreachable: `isCleared` is true on
 * exactly the set where `clearedAt` is non-zero, index.ts's `free()` refuses
 * that set, so every point the tree pass could sample had density exactly 1.
 * Measured 2026-07-27 over 240,000 samples of the tree pass's admissible
 * domain: `timber()` returned ONE distinct value, 1.0000, and the exclusion
 * radius was flat at TREE_SPACING_MIN everywhere. Collapsing
 * TREE_SPACING_MAX from 250 to 72 changed not one item on twenty islands.
 *
 * On the standing side the band is real: the canopy is 0 at the rim and closes
 * to 1 this far out, so the wood opens up as it approaches cut ground and a
 * clearing reads as a thinning treeline rather than as a stamped circle.
 * Widening it pushes the wood further back from every clearing; narrowing it
 * makes the island read as cookie-cuttered.
 */
export const CLEARING_EDGE_BAND = 96

/**
 * How much standing timber a piece of village furniture may have over it.
 *
 * A RIM IS NOT A FENCE, and gating the furniture on `isCleared` treats it as
 * one. The treeline is a BAND — CLEARING_EDGE_BAND wide — over which the canopy
 * closes, and ground inside that band is partly open: a fence at the wood's
 * edge, a bench under the last trees and a trough by the treeline are all
 * things a settlement really has. Measured with the hard predicate instead,
 * the observatory bench was dropped for standing ONE TENTH OF A PIXEL outside
 * its district's rim, and the market stall and the law ledger went with it —
 * three authored civic props deleted by a boundary that the composition never
 * meant as a boundary.
 *
 * 0.5 IS THE BAND'S MIDPOINT, which is the one non-arbitrary point on it: the
 * furniture may stand where the ground is more open than wooded and not where
 * it is more wooded than open. In px that is 48 of the 96, so an item may sit
 * just outside its clearing and may not walk into the wood. Measured on the
 * composed islands, that keeps every authored civic prop and still refuses the
 * 129 items per 20 hamlet islands that stood under fully closed canopy — the
 * defect this exists for, a fence run 188px deep into standing wood.
 */
export const FURNITURE_MAX_TIMBER = 0.5

/**
 * How far either side of a rim the felling record lies.
 *
 * A stump sits where the tree stood, so the band straddles the boundary rather
 * than sitting inside it: some of the record is on the cut ground and some of
 * it is in the standing timber that was cut back to.
 */
export const RECORD_BAND = 84

/**
 * A rim buried deeper than this inside ANOTHER clearing is not a rim.
 *
 * Two clearings that grew into each other share ground, and the swallowed arc
 * is no longer a boundary between cut and standing timber — it is the middle of
 * a bigger clearing. Without this term a mature town grows a line of stumps
 * straight through its own square, which is the opposite of the claim.
 */
export const RECORD_SWALLOWED_AT = 0.6

/** Cleared radius at the smallest footprint and the lowest rung. */
export const CLEAR_BASE = 58
/** How much of a structure's drawn width becomes cleared ground. */
export const CLEAR_PER_WIDTH = 0.5
/** How much further out the treeline goes for each rung the object climbs. */
export const CLEAR_PER_RUNG = 34
/** The rung index past which a clearing stops growing. */
export const CLEAR_RUNG_CAP = 6
/** Nothing cuts more ground than this, whatever its rung. */
export const CLEAR_MAX = 340

/**
 * How many rungs it takes for a clearing's edge to settle.
 *
 * The record's density follows how recently the ground was opened, and the
 * maturity signal this library has is the rung: a thing on its first rung has
 * just been raised in a gap that was forest last week, and a thing four rungs up
 * has had its stumps grubbed out and its edge grown over. So rawness is
 * `1 - rung/RAW_SETTLE_RUNGS`, floored at 0.
 */
export const RAW_SETTLE_RUNGS = 4

/**
 * How much of an authored civic clearing exists at each era.
 *
 * The civic grounds — the square, the works ridge, the training yard, the
 * signals crossroads — are not one object's clearing, so they have no rung of
 * their own; the era IS their measurement. A camp has a trodden gap where a
 * town has a paved square, and this is the number that says so.
 */
export const CIVIC_ERA_SCALE: Readonly<Record<Era, number>> = {
  camp: 0.4,
  hamlet: 0.58,
  town: 0.8,
  beyond_bay: 1,
}

const ERA_ORDINAL: Readonly<Record<Era, number>> = {
  camp: 0,
  hamlet: 1,
  town: 2,
  beyond_bay: 3,
}

/** What kind of cut ground this is — see the header's three classes. */
export type CutBy = 'felled' | 'surface' | 'natural'

/** One patch of ground that is not forest. */
export interface Clearing {
  at: Point
  /** Cleared radius along x, layout px; y is squashed by CLEARING_SQUASH. */
  r: number
  /**
   * How raw the edge is: 1 = felled within living memory, 0 = long settled.
   * Only `felled` ground can be raw — see `cut`.
   */
  rawness: number
  /** WHY this ground is open — the object, the surface or the landform. */
  role: string
  cut: CutBy
}

/**
 * How much ground a structure cut, from its drawn size and its own rung.
 *
 * BOTH TERMS ARE LOAD-BEARING and they answer different halves of the Captain's
 * sentence. The width term says a great house needs a bigger gap than a hut;
 * the rung term says the SAME object cuts more as it grows, which is the half
 * that makes maturity read as the treeline receding instead of as more roofs.
 */
export function clearingRadius(size: Footprint, rung: number): number {
  const r = Number.isFinite(rung) ? Math.max(0, Math.min(CLEAR_RUNG_CAP, Math.trunc(rung))) : 0
  const w = Number.isFinite(size.w) ? Math.max(0, size.w) : 0
  return Math.min(CLEAR_MAX, CLEAR_BASE + w * CLEAR_PER_WIDTH + CLEAR_PER_RUNG * r)
}

/** How raw a clearing's rim is at this rung — 1 just-felled, 0 long settled. */
export function rawnessOfRung(rung: number): number {
  const r = Number.isFinite(rung) ? Math.max(0, rung) : 0
  return clamp01(1 - r / RAW_SETTLE_RUNGS)
}

/** The era as the civic grounds' own maturity, on the same 0..1 scale. */
export function rawnessOfEra(era: Era): number {
  return rawnessOfRung(ERA_ORDINAL[era] ?? 0)
}

/**
 * One structure as the ground it cut.
 *
 * TWO NUMBERS, NOT ONE, and they are different questions. `rung` is HOW FAR
 * ALONG this object is and it sizes the clearing — a great house on its top rung
 * has cut more ground than the log cabin that stood there at camp. `age` is HOW
 * LONG AGO the ground was opened and it ages the rim.
 *
 * For a TIER ladder the two are the same number: an object several rungs up has
 * been standing a while. For a COUNT ladder they are not, and collapsing them
 * was measured wrong on 2026-07-27: the sixth officer's cabin took `rung = 5`
 * from its seniority in the row and therefore cut a WIDER clearing than the
 * great house four rungs up — a cottage with a bigger yard than the manor. A
 * count ladder says how MANY, so each member clears its baseline (`rung` 0) and
 * shows as another gap in the wood; what seniority legitimately says is that the
 * first officer's rim has had five arrivals' worth of time to grow over.
 */
export interface StructureCut {
  at: Point
  size: Footprint
  /** The state object — the ladder this structure came off. */
  role: string
  /** The object's own visible rung index; 0 when it has no ladder of its own. */
  rung: number
  /** How long it has stood, in rungs — `rung` for a tier ladder, seniority for a count. */
  age: number
}

/** Turn the placed structures into the clearings they cut. */
export function structureClearings(structures: readonly StructureCut[]): Clearing[] {
  return structures.map((s) => ({
    at: s.at,
    r: clearingRadius(s.size, s.rung),
    rawness: rawnessOfRung(s.age),
    role: s.role,
    cut: 'felled' as const,
  }))
}

/** The surfaces that are cut ground without being a felled clearing. */
export interface CutSurfaces {
  lanes: LaneField
  /** The paved square and the tilled plots that were actually painted. */
  onPaving: (x: number, y: number) => boolean
  /** The pond and its outflow — a hole in the canopy, never felled. */
  inWater: (x: number, y: number) => boolean
  /** The wharf deck that was actually built. */
  onQuay: (x: number, y: number) => boolean
}

/**
 * How far off a carriageway counts as cut for the road.
 *
 * THE SAME 46 THE OLD WILDNESS FIELD USED for its lane term, kept rather than
 * re-chosen: it is the distance at which the reference stopped calling ground
 * wild, and re-picking it here would be changing the composition under cover of
 * inverting it.
 */
export const LANE_CLEAR_REACH = 46

/**
 * The standing-timber map: what is left after everything was cut.
 *
 * `timber` is the density field the planting passes consume, and it is the
 * SIGN-FLIPPED successor to scatter.ts's old `wildnessField`. That field read
 * `coast*1.15 - civic*0.72 - lane*0.45 + 0.10` — highest at the waterline,
 * lowest in the middle — which is a coastal ring with a sparse interior, the
 * exact shape the Captain's direction rejects. This one is 1 everywhere nobody
 * has cut and falls to 0 across each clearing's edge band.
 */
export interface ClearedGround {
  /** Every felled/natural clearing, in the order the caller supplied them. */
  readonly clearings: readonly Clearing[]
  /**
   * HOW DEEP INTO CUT GROUND this point is: 0 on (or outside) a rim, 1 well
   * inside. Its only consumer is the record's swallow test, which asks whether
   * an arc has stopped being a boundary because a bigger clearing grew over it.
   */
  clearedAt(x: number, y: number): number
  /** Inside some clearing or on some cut surface at all — the hard predicate. */
  isCleared(x: number, y: number): boolean
  /**
   * HOW MUCH TIMBER IS LEFT STANDING here: 0 on cut ground, 1 under closed
   * canopy. The planting density field.
   *
   * NOT `1 - clearedAt`, and that is the fix rather than a tidy-up. While it
   * was the complement the gradient lived entirely INSIDE the discs, which is
   * exactly the set the planting predicate refuses — so the field the tree
   * pass consumed was the constant 1 (see CLEARING_EDGE_BAND). The two
   * quantities answer different questions from opposite sides of the same rim
   * and only agree at the two ends.
   */
  readonly timber: DensityField
  /** 1 exactly on a felled rim, falling to 0 at RECORD_BAND. Geometry only. */
  edgeAt(x: number, y: number): number
  /** The rawness of the rim nearest this point, 0 when no rim is in reach. */
  rawnessAt(x: number, y: number): number
  /** edgeAt * rawnessAt, suppressed where the rim was swallowed. */
  recordAt(x: number, y: number): number
  /** The clearings as the keep-out discs the forest ring already speaks. */
  readonly districts: District[]
}

/** Squashed radial distance from a clearing centre — the ground-disc metric. */
function discDist(x: number, y: number, c: Clearing): number {
  return hypot(x - c.at.x, (y - c.at.y) * CLEARING_SQUASH)
}

/**
 * Fold the clearings and the cut surfaces into one map.
 *
 * The clearings are read once and never mutated: the layout stays a pure map
 * from (state, seed) to data.
 */
export function buildClearedGround(
  clearings: readonly Clearing[],
  surfaces: CutSurfaces
): ClearedGround {
  const list = [...clearings]
  const band = Math.max(1, CLEARING_EDGE_BAND)

  const clearedAt = (x: number, y: number): number => {
    let best = 0
    for (const c of list) {
      if (c.r <= 0) continue
      const d = discDist(x, y, c)
      if (d >= c.r) continue
      const v = clamp01((c.r - d) / band)
      if (v > best) best = v
      if (best >= 1) return 1
    }
    // The surfaces are cut all the way to their painted edge — a plaza does not
    // have a thinning treeline, it has a kerb.
    if (surfaces.onPaving(x, y) || surfaces.inWater(x, y) || surfaces.onQuay(x, y)) return 1
    if (surfaces.lanes.nearLane(x, y, LANE_CLEAR_REACH)) return 1
    return best
  }

  const isCleared = (x: number, y: number): boolean => {
    for (const c of list) {
      if (c.r > 0 && discDist(x, y, c) < c.r) return true
    }
    return (
      surfaces.onPaving(x, y) ||
      surfaces.inWater(x, y) ||
      surfaces.onQuay(x, y) ||
      surfaces.lanes.nearLane(x, y, LANE_CLEAR_REACH)
    )
  }

  /**
   * The standing canopy: 0 on cut ground, closing to 1 one edge band out.
   *
   * THE SURFACES GET A KERB, NOT A TREELINE, and the three-classes header says
   * why: a plaza's, a lane's and a deck's edges are AUTHORED, so there is no
   * treeline that moved and nothing to ramp. They are 0 where they are and
   * silent everywhere else — which costs nothing, because the planting
   * predicate already refuses to stand on them.
   *
   * THE RAMP IS OFF THE NEAREST RIM, not summed over the clearings: two
   * clearings 300px apart do not clear the wood between them twice, and a sum
   * would thin a whole town's interior on arithmetic rather than on geometry.
   */
  const timberAt = (x: number, y: number): number => {
    if (surfaces.onPaving(x, y) || surfaces.inWater(x, y) || surfaces.onQuay(x, y)) return 0
    if (surfaces.lanes.nearLane(x, y, LANE_CLEAR_REACH)) return 0
    let nearest = Infinity
    for (const c of list) {
      if (c.r <= 0) continue
      const out = discDist(x, y, c) - c.r
      if (out <= 0) return 0
      if (out < nearest) nearest = out
    }
    if (!Number.isFinite(nearest)) return 1
    return clamp01(nearest / band)
  }

  /** The nearest FELLED rim, as (proximity 0..1, that clearing's rawness). */
  const nearestRim = (x: number, y: number): { edge: number; rawness: number } => {
    let edge = 0
    let rawness = 0
    for (const c of list) {
      if (c.cut !== 'felled' || c.r <= 0) continue
      const off = Math.abs(discDist(x, y, c) - c.r)
      if (off >= RECORD_BAND) continue
      const e = 1 - off / RECORD_BAND
      if (e > edge) {
        edge = e
        rawness = c.rawness
      }
    }
    return { edge, rawness }
  }

  return {
    clearings: list,
    clearedAt,
    isCleared,
    timber: timberAt,
    edgeAt: (x, y) => nearestRim(x, y).edge,
    rawnessAt: (x, y) => nearestRim(x, y).rawness,
    recordAt: (x, y) => {
      const { edge, rawness } = nearestRim(x, y)
      if (edge <= 0 || rawness <= 0) return 0
      if (clearedAt(x, y) > RECORD_SWALLOWED_AT) return 0
      return edge * rawness
    },
    districts: list.map((c) => ({ at: c.at, r: c.r })),
  }
}

// ── the measurement ────────────────────────────────────────────────────────

/**
 * The canopy sprites, by name.
 *
 * A CLOSED SET, hand-held for the same reason ambient-nature.txt is: a set
 * derived from "everything the planting passes emitted whose name starts with
 * tree_" is a sensor wired to its own subject, and it would silently start
 * counting a species that is not canopy the day one is added.
 */
export const CANOPY_KINDS: ReadonlySet<string> = new Set([
  'tree_oak',
  'tree_oak_small',
  'tree_birch',
  'tree_willow',
  'tree_pine',
  'tree_pine_small',
])

/**
 * The felling record's own frames — what an axe leaves at a rim.
 *
 * Hand-held for the same reason CANOPY_KINDS is. `wood_pile` is in the set even
 * though it can only be planted at village, because the measurement asks "how
 * much record is there", and a set that changed with the era would compare
 * different quantities at each end of the table.
 */
export const RECORD_FRAMES: ReadonlySet<string> = new Set([
  'tree_stump',
  'fallen_log',
  'wood_pile',
])

/** The minimum a layout must expose to be measured for canopy. */
export interface CanopyInput {
  space: { w: number; h: number }
  coast: { landAt(x: number, y: number): boolean }
  ring: readonly { kind: string; at: Point; size: Footprint }[]
  scatter: readonly { kind: string; at: Point; size: Footprint }[]
}

export interface CanopyCoverage {
  /** Sample points that landed on the island. */
  land: number
  /** Of those, how many sit under at least one canopy sprite. */
  under: number
  /** under / land — the number the eras are compared on. */
  fraction: number
  /** How many canopy sprites the layout emitted at all. */
  trees: number
}

/**
 * What fraction of the island's LAND reads as forest.
 *
 * WHAT IT MEASURES, stated plainly because the honest bound matters: a tree's
 * canopy is taken as its DRAWN RECT — x +/- w/2 and y-h .. y, the sprite's own
 * extent — and a land sample counts as under canopy if it falls in at least one
 * such rect. It is a union, never a sum, so overlapping crowns cannot inflate
 * it past 1. It is an OVER-estimate of opaque pixels, because a pine does not
 * fill its rect; what it is not is era-dependent, so comparing eras compares
 * like with like, and that comparison is the whole point of the number.
 *
 * SEEDED Monte Carlo rather than a raster: the caller may hand any space, and a
 * raster over 2400x1760 costs 4.2M cells per era. Same seed, same answer,
 * forever — this is a measurement other measurements are compared against, so
 * it may not wobble.
 */
export function canopyCoverage(
  layout: CanopyInput,
  rng: () => number,
  samples = 40000
): CanopyCoverage {
  const trees = [...layout.ring, ...layout.scatter].filter((s) => CANOPY_KINDS.has(s.kind))
  let land = 0
  let under = 0
  const n = Math.max(1, Math.trunc(samples))
  for (let i = 0; i < n; i++) {
    const x = rng() * layout.space.w
    const y = rng() * layout.space.h
    if (!layout.coast.landAt(x, y)) continue
    land++
    for (const t of trees) {
      if (
        x >= t.at.x - t.size.w / 2 &&
        x <= t.at.x + t.size.w / 2 &&
        y <= t.at.y &&
        y >= t.at.y - t.size.h
      ) {
        under++
        break
      }
    }
  }
  return { land, under, fraction: land === 0 ? 0 : under / land, trees: trees.length }
}

export interface RecordDensity {
  /** Sample points that landed on the island. */
  land: number
  /** Of those, how many sit on a felled rim AT ALL — the denominator. */
  rim: number
  /** How many record sprites the layout emitted. */
  items: number
  /** Items per 1000 rim samples — the number the eras are compared on. */
  perKiloRim: number
}

/**
 * How THICKLY the felling record lies, per unit of rim rather than in total.
 *
 * THE RAW COUNT ANSWERS THE WRONG QUESTION and would read as a green tick for a
 * broken model. A town has felled far more ground than a camp, so it has far
 * more rim; counting stumps compares two different lengths of edge, and measured
 * on the composed islands the totals barely move at all (20-22 at camp, 11-19 at
 * beyond_bay). Per unit of rim they separate, which is the Captain's sentence
 * exactly: "a mature town has an old, settled edge and a young camp has raw
 * stumps."
 *
 * THE DENOMINATOR IS `edgeAt`, NOT `recordAt`, and the difference is what makes
 * this a sensor rather than a restatement. `recordAt` is the rule: it already
 * multiplies by rawness and already suppresses a swallowed arc, so dividing by
 * it would measure "how densely did the pass fill the ground it chose", which is
 * roughly constant by construction and rose at beyond_bay when it was tried.
 * `edgeAt` is pure geometry — every rim the clearings actually have — so the
 * ratio asks the honest question: of all the edge this island cut, how much of
 * it still shows the axe?
 */
export function recordDensity(
  layout: CanopyInput & { cleared: Pick<ClearedGround, 'edgeAt'> },
  rng: () => number,
  samples = 40000
): RecordDensity {
  const items = layout.scatter.filter((s) => RECORD_FRAMES.has(s.kind)).length
  let land = 0
  let rim = 0
  const n = Math.max(1, Math.trunc(samples))
  for (let i = 0; i < n; i++) {
    const x = rng() * layout.space.w
    const y = rng() * layout.space.h
    if (!layout.coast.landAt(x, y)) continue
    land++
    if (layout.cleared.edgeAt(x, y) > 0) rim++
  }
  return { land, rim, items, perKiloRim: rim === 0 ? 0 : (items * 1000) / rim }
}
