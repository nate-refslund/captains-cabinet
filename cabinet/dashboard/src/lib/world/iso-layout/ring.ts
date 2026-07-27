/**
 * FOREST ENCLOSURE RING — "the biggest single lever" (compose.py:885).
 *
 * PORTED FROM compose.py lines 885-941.
 *
 * WHAT IT IS. Four sublayers of trees at increasing insets from the waterline,
 * walked by ANGLE around the island rather than sampled over its area. That
 * distinction is the whole point: a Poisson field with a density that rises
 * toward the coast produces a gradient, and a gradient is not a frame. Walking
 * the shore at a fixed angular step produces a continuous belt of canopy with
 * the meadow inside it, which is what makes an island read as enclosed instead
 * of as a lawn that happens to end.
 *
 * WHY THIS PORT NEEDED IT BADLY. Enforcing the keep-out discs deleted the trees
 * that had been standing INSIDE the village and nothing replaced the ones that
 * belong on the rim: planting fell from 173-206 items per hamlet to 42-68, and
 * the density profile from a disc rim outward read 0 / 137 / 72 / 41 per Mpx —
 * a hard edge with a pile-up on it, and empty coast beyond. The exclusions were
 * right; the ring is the half that was missing.
 *
 * THE GAPS ARE NOT DECORATION (compose.py:886-889). A ring with no gaps is a
 * wall: it hides the water, and the water is what says "island". The reference
 * opens three arcs, and this port keeps its numbers verbatim because the
 * approved stills are what those numbers produce. Their measured directions,
 * in this coordinate frame (0 = east, 90 = south, 180 = west, y grows down):
 *   58-122   due south — the harbour and its cove.
 *   18-46    east-south-east — the lighthouse point.
 *   196-224  west-north-west.
 * The reference's own comment names the third one "the west coastal lane". It
 * is not: that lane runs 126-167 degrees and already punches its own hole in
 * the ring through the near-lane rule below. The arc is recorded here by what
 * it measures rather than by what the comment calls it, because a port that
 * copies a label it can disprove teaches the next reader something false.
 *
 * WHERE THIS DIVERGES FROM THE REFERENCE, deliberately, twice:
 *
 *   ORDER. compose.py plants the ring BEFORE it places the district buildings,
 *   protecting the plots only with the keep-out discs it reserved first
 *   (:899-914). This port plants it AFTER the structures, so a ring tree can
 *   never take ground a measured building needs — the exact defect
 *   compose.py:907-909 records paying for, one level deeper. The visible result
 *   is the same belt (the discs already keep the ring 93px clear of every lot
 *   centre) and the failure mode is strictly smaller.
 *
 *   REJECTION. The reference calls place() with its default nudge, which shoves
 *   a blocked tree sideways until it settles. This port's standing rule is
 *   reject-at-sampling-time and DROP, because nudging oscillates between two
 *   neighbours and settles on neither — silently, since the prop still draws.
 *   So a ring candidate that is not admissible is dropped. Belt-vs-belt spacing
 *   is the reference's own `reserve(x, y, 30)` (see RING_SPACING) rather than
 *   the building-grade ground-diamond rule; the caller's occupancy book keeps
 *   the strict rule, so a building still keeps its ground.
 *
 * PURE and SEEDED: one stream per layer, consumed in the reference's order.
 */
import { footprintOnLane, groundTaken, type Footprint, type Occupant } from './clearance'
import { fnv1a, seededRng } from '../hash'
import type { Coastline } from './coastline'
import type { LaneField } from './lanes'
import type { District, ScatterItem } from './scatter'
import type { LayoutSpace, Point } from './space'

/**
 * compose.py:920-921 — the two species pools. Pines are the silhouette against
 * the sea; broadleaf fills in behind them.
 */
export const RING_PINES: readonly string[] = ['tree_pine', 'tree_pine_small']
export const RING_BROAD: readonly string[] = ['tree_oak', 'tree_oak_small', 'tree_birch']

/** One depth sublayer of the belt. */
export interface RingLayer {
  /** How far inside the waterline this layer's trunks sit. */
  inset: number
  /** The species pool this layer draws from. */
  kinds: readonly string[]
  /** Extra inward jitter, 0..jitter px, so the belt has no machined edge. */
  jitter: number
}

/**
 * compose.py:923-927. The reference's tuple carries a fourth field it calls
 * `density` (108/96/118/130) which its own loop body never reads — a dead
 * parameter, not a rule, so it is not ported. Porting it would have meant
 * inventing a meaning for it and then testing the invention.
 */
export const RING_LAYERS: readonly RingLayer[] = [
  { inset: 22, kinds: RING_PINES, jitter: 26 },
  { inset: 78, kinds: [...RING_PINES, ...RING_BROAD], jitter: 40 },
  { inset: 140, kinds: [...RING_BROAD, 'tree_oak_small', 'bush_round'], jitter: 48 },
  {
    inset: 206,
    kinds: [...RING_BROAD, 'bush_round', 'bush_flowering', 'fern_cluster'],
    jitter: 60,
  },
]

/** compose.py:888-889 — the arcs the belt opens, in degrees. */
export const RING_GAPS: readonly (readonly [number, number])[] = [
  [58, 122],
  [18, 46],
  [196, 224],
]

/** compose.py:888 in_gap(). Exclusive at both ends, as in the reference. */
export function inRingGap(deg: number): boolean {
  return RING_GAPS.some(([lo, hi]) => deg > lo && deg < hi)
}

/**
 * compose.py:916-918 clear_of_districts(). The disc is shrunk to `k` of its
 * radius because "the ring frames the village; it may crowd a district but not
 * grow through it" — a belt held off at the full radius leaves a bald collar
 * around every district, which is the hole this whole exercise exists to close.
 *
 * The 1.3 vertical squash is the reference's, and it is NOT the 1.35 the
 * planting predicate uses. Both are copied rather than unified: they are two
 * separate constants in the reference and quietly making them agree would be
 * changing the composition under cover of tidying it.
 */
export const RING_DISTRICT_K = 0.62

export function clearOfDistricts(
  x: number,
  y: number,
  districts: readonly District[],
  k = RING_DISTRICT_K
): boolean {
  return !districts.some(
    (d) => (x - d.at.x) ** 2 + ((y - d.at.y) * 1.3) ** 2 < (d.r * k) ** 2
  )
}

/** compose.py:936 — below this radius the belt would be planting the meadow. */
export const RING_MIN_RADIUS = 130

/**
 * The belt's own minimum trunk separation — a SAFETY RAIL, not a density lever.
 *
 * THIS IS NOT THE GROUND-DIAMOND RULE, and that is the point. Two buildings
 * sharing a ground diamond are stacked and it is a defect; two trees 40px apart
 * with interpenetrating canopies are a FOREST, and holding a belt to
 * building-grade exclusivity thins it into a dotted line. Measured with
 * `groundTaken` at the standard 0.16 against the belt's own members: a full pine
 * needs ~92px of clearance, the belt's angular step gives 69-113px of arc, and
 * layer 1 (inset 78) sits inside layer 0's (inset 22) diamonds almost
 * everywhere — so the belt came out at 35-75 items and the depth sublayers
 * largely cancelled each other. The reference resolves that by never dropping:
 * place() nudges a crowded tree up to 30 times and draws it wherever it ends up.
 * This port may not nudge (see the header), so it needs SOME admission rule that
 * is not the ground diamond, and 30px is it.
 *
 * TWO CORRECTIONS TO WHAT THIS NUMBER USED TO CLAIM, both measured 2026-07-27:
 *
 *   IT IS NOT THE REFERENCE'S BELT RULE. compose.py:941 does call
 *   `reserve(x, y, 30)` after planting each belt tree, but `_DISTRICTS` — the
 *   list `clear_of_districts` reads — is snapshotted at compose.py:915, BEFORE
 *   the ring loop runs. The belt's own reservations are invisible to the belt.
 *   They are picked up by `AV = list(KEEPOUT)` at :1211, which gates the later
 *   meadow SCATTER. So the number is the reference's, and its job there is
 *   keeping the scatter off the belt; using it as the belt's own admission rule
 *   is this port's repurposing, and calling it the reference's spacing was a
 *   label the code could disprove.
 *
 *   IT BARELY DOES ANYTHING. Composed hamlet belt over 20 seeds: 96.5 items per
 *   island at 30px, 97.2 at 1px — the whole rule rejects 0.8 candidates per
 *   island. The angular step is coarse enough that neighbours are rarely within
 *   30px to begin with. Anyone reaching for this constant to thicken the belt
 *   should know it has no room in it; the belt's size comes from elsewhere (see
 *   forestRing's rejection budget).
 *
 * Buildings still keep their ground: the caller's occupancy book is tested with
 * the strict rule.
 */
export const RING_SPACING = 30

/**
 * How much of a BUILT thing's ground a belt tree may share — the strict bar.
 *
 * THE BELT WAS RUNNING AT THE LOOSE ONE and nothing said so. `groundTaken`
 * defaults to 0.16, which is the tree-against-tree bar; `ctx.occupied` at the
 * one call site contains nothing but built ground (the structures, the
 * dressing and the dock kit — the belt keeps its own members in `planted`),
 * so that default was being applied to exactly the population it is wrong for.
 * Measured 2026-07-27 across 20 composed islands: 27 belt-vs-structure pairs
 * over 0.04, worst 0.131 of a house's ground diamond — a pine standing through
 * a wall. index.ts:611-613 claimed "the unit arm ... holds it at zero", and
 * that arm reads `l.scatter` only; the belt is a separate population placed by
 * a separate module and no arm read it.
 *
 * 0.04 IS THE NUMBER THE REST OF THE LIBRARY ALREADY USES for anything against
 * a building — placeOnGround's strict mode and ScatterOptions.strictFrac both
 * — so this is the belt joining the existing rule rather than a new one. Cost,
 * measured: 1.0 items per island (96.5 -> 95.5 at hamlet).
 */
export const RING_BUILT_OVERLAP = 0.04

export interface RingItem extends ScatterItem {
  /** Which sublayer planted it — the renderer's depth cue, 0 = outermost. */
  layer: number
  size: Footprint
}

export interface RingContext {
  space: LayoutSpace
  coast: Coastline
  lanes: LaneField
  districts: readonly District[]
  /** The occupancy book. READ here; the caller decides what to add to it. */
  occupied: readonly Occupant[]
  /** The painted water (pond + outflow) — nothing is planted in it. */
  inWater: (x: number, y: number) => boolean
  /** The painted plaza and tilled plots — nothing is planted on them either. */
  onPaving: (x: number, y: number) => boolean
  /**
   * The wharf deck that was actually built — a surface, like the plaza.
   *
   * ADDED 2026-07-27, and its mutation is GREEN, which is the reason to state
   * what it is for rather than let a later reader assume it was measured. Across
   * 240 composed islands (80 seeds x 3 states) NO belt item lands on the deck
   * with or without this term, so today it removes nothing. It is here because
   * the thing that keeps the belt off the deck is a COINCIDENCE OF TWO
   * UNRELATED CONSTANTS: the wharf spans cove.x +/- SHORE_HALF_SPAN (360), and
   * the reference's south gap runs 58-122 degrees. Measured in this frame, the
   * wharf's east end sits at ~58.5 degrees — half a degree inside a gap edge
   * that exists to show the water at the harbour, not to keep trees off a deck.
   * Nothing links the two numbers, so the belt is one edit to either away from
   * walking onto the wharf silently, and the shore band is exactly where the
   * belt's outermost layer plants.
   *
   * The unit arm in planting.test.ts drives the term directly (a synthetic deck
   * in an ungapped arc) so the RULE has a sensor even though the composed
   * layout does not currently reach it — unreached is not unreachable, and a
   * rule with no sensor at either level is the defect this port keeps finding.
   */
  onQuay: (x: number, y: number) => boolean
  sizeOf: (kind: string) => Footprint
  layers?: readonly RingLayer[]
}

/**
 * Walk the shore and plant the belt. Returns items in emission order,
 * outermost layer first; the caller adds them to the occupancy book.
 *
 * `occupied` is read once per candidate and the function keeps its OWN running
 * book of what it has planted, so two trees in the same layer cannot land on
 * each other. It never mutates the caller's array: the layout stays a pure map
 * from (state, seed) to data.
 *
 * THE REJECTION BUDGET, measured 2026-07-27 over 20 composed hamlet islands, per
 * island — because "the belt is thinner than the reference's" was an open
 * question with no numbers under it, and this is where the belt's size actually
 * comes from:
 *
 *   249.9 candidates   (4 layers x 360 degrees at a 4.4-7.2 degree step)
 *    -82.1  in a gap arc          } all three are the REFERENCE'S OWN terms,
 *    -47.4  inside a district     } with the reference's own constants
 *    -20.6  within 40px of a lane }
 *     -3.5  everything this port ADDED, in total:
 *              1.3 pool footprint on a lane      0.8 belt spacing
 *              0.7 pool ground taken             0.4 painted water/paving/quay
 *              0.3 chosen sprite's ground taken  0.0 chosen sprite on a lane
 *   = 96.5 planted
 *
 * So the belt's density is set by the gaps, the keep-out discs and the lanes —
 * every one of them a number this port copied rather than chose. The port's own
 * divergences (reject-instead-of-nudge, the extra surface terms, planting after
 * the structures rather than before) cost THREE AND A HALF ITEMS an island. If
 * the belt needs to be denser, the levers are the gap arcs, the district radii
 * or the angular step, and each of those is a composition change that wants a
 * render and the Captain's eye — not a rule this port added.
 */
export function forestRing(seed: string | number, ctx: RingContext): RingItem[] {
  const numSeed = typeof seed === 'number' ? seed >>> 0 : fnv1a(seed)
  const layers = ctx.layers ?? RING_LAYERS
  const out: RingItem[] = []
  // Everything this call has planted so far, as the reference's reservations:
  // (x, y) with RING_SPACING. The caller's book is tested separately, with the
  // strict ground rule — see RING_SPACING for why the belt gets its own.
  const planted: Point[] = []
  const crowded = (x: number, y: number) =>
    planted.some(
      (p) => (x - p.x) ** 2 + ((y - p.y) * 1.35) ** 2 < RING_SPACING * RING_SPACING
    )
  const cx = ctx.space.cx
  const cy = ctx.space.cy

  for (let li = 0; li < layers.length; li++) {
    const layer = layers[li]
    // ONE STREAM PER LAYER, not one for the ring: the layers are independent
    // bands and a shared stream would make the outermost belt's shape depend on
    // how many candidates the layer before it happened to reject.
    const rng = seededRng(fnv1a(`${numSeed}:ring:${li}`))
    // Sampled against the LARGEST sprite in the pool, as everywhere else in
    // this library: sampling against a sapling and then drawing a full pine is
    // how a 175px tree lands in a gap that only fitted a 50px one.
    const size = {
      w: Math.max(...layer.kinds.map((n) => ctx.sizeOf(n).w)),
      h: Math.max(...layer.kinds.map((n) => ctx.sizeOf(n).h)),
    }

    let a = 0
    while (a < 360) {
      // deg is read BEFORE the step is added — the reference's own order, and
      // it is what puts the first sample at exactly 0 degrees.
      const deg = a % 360
      a += 4.4 + rng() * 2.8
      if (inRingGap(deg)) continue
      const ang = (deg * Math.PI) / 180
      const r = ctx.coast.edgeAt(ang) - layer.inset - Math.floor(rng() * (layer.jitter + 1))
      if (r < RING_MIN_RADIUS) continue
      const x = cx + Math.cos(ang) * r
      const y = cy + Math.sin(ang) * r * 0.92
      const at = { x, y }
      // the reference's three terms...
      if (!ctx.coast.landAt(x, y)) continue
      if (ctx.lanes.nearLane(x, y, 40)) continue
      if (!clearOfDistricts(x, y, ctx.districts)) continue
      // ...and this port's three: painted water, paved/tilled surface, and the
      // wharf deck. The reference's ring predicate omits all three because its
      // pond and its plots are covered incidentally by district discs it
      // happens to have reserved. The outflow stream is not, and it runs
      // through open west meadow the innermost layer reaches on most seeds; the
      // deck is not either, and only the south gap's placement keeps the belt
      // off it (see RingContext.onQuay, whose mutation is green today).
      if (ctx.inWater(x, y) || ctx.onPaving(x, y) || ctx.onQuay(x, y)) continue
      // ...and the standing rejection rules every placement in this library
      // obeys: the road wins, and a building's ground is a building's ground.
      if (footprintOnLane(at, size, ctx.lanes)) continue
      if (groundTaken(at, size, ctx.occupied, RING_BUILT_OVERLAP)) continue
      if (crowded(x, y)) continue

      // THE SAMPLING SIZE IS NOT A CONSERVATIVE SIZE, and assuming it was is how
      // the belt put four trees on the coastal carriageway (measured 2026-07-27:
      // 4 items over 200 hamlet islands, and 40 of 11031 items sharing ground
      // with a building). Sampling against the pool's LARGEST sprite is right for
      // a containment question, and it is WRONG for both of the rules above:
      //   - footprintOnLane is a sparse 4x5 probe grid whose sample points scale
      //     with the footprint, so a bigger diamond does not probe a superset of
      //     a smaller one's points. An 18px-wide lane passes clean between a
      //     150x150 diamond's probes and is hit square on by a 47x47 one's.
      //   - groundTaken divides the shared area by min(area) — shrink the
      //     candidate and the same overlap crosses the threshold.
      // The renderer, check_on_road and auditLayout all measure the sprite that
      // was DRAWN, so the drawn sprite is what has to pass. Both rules therefore
      // run twice: once on the pool max at sampling time (nothing lands in a gap
      // that only fitted a sapling) and once on the chosen sprite here.
      //
      // The kind and the flip are drawn BEFORE this test so the stream is
      // consumed in the reference's order whatever the answer is — the same
      // discipline the paint stage's clip-after-draw follows.
      const kind = layer.kinds[Math.min(layer.kinds.length - 1, Math.floor(rng() * layer.kinds.length))]
      const flip = rng() < 0.5
      const itemSize = ctx.sizeOf(kind)
      if (footprintOnLane(at, itemSize, ctx.lanes)) continue
      if (groundTaken(at, itemSize, ctx.occupied, RING_BUILT_OVERLAP)) continue
      planted.push(at)
      out.push({ kind, at, flip, layer: li, size: itemSize })
    }
  }
  return out
}

/** The belt's angular span in degrees, gaps removed — used by the tests. */
export function ringOpenDegrees(): number {
  let open = 360
  for (const [lo, hi] of RING_GAPS) open -= hi - lo
  return open
}

/** Where a point sits relative to the island centre, in the ring's own frame. */
export function ringAngleDeg(p: Point, space: LayoutSpace): number {
  const d = (Math.atan2((p.y - space.cy) / 0.92, p.x - space.cx) * 180) / Math.PI
  return (d + 360) % 360
}
