/**
 * LOTS — the plots buildings stand on, derived from the lane network.
 *
 * PORTED FROM compose.py lines 238-325.
 *
 * THE PIPELINE IS roads -> lots -> buildings -> dressing. Hand-typed building
 * anchors are what made everything downstream need hand-typed offsets too: a
 * fence that had to be nudged to meet the house, a garden that had to be
 * nudged to sit between the door and a road nobody had told it about. A lot
 * knows three things — where it sits, which lane it fronts, and which way its
 * door faces — and that is enough to orient the building AND draw its drive.
 *
 * TWO WAYS TO GET A LOT, and the difference is doctrinal:
 *   lotsAlong() walks a lane by arc length and emits lots that FRONT it. Use
 *     it for repeated, countable things (the officer row) where the count is
 *     a real measured number and the position is not a decision.
 *   lotFor() wraps an EXISTING compass anchor: the doctrine anchors (Law
 *     north, Memory north-east, ...) stay authoritative and the lane supplies
 *     only frontage direction and the drive. Deriving those anchors from the
 *     lane instead moved whole districts — compose.py:313-314 records it.
 *
 * SEPARATION IS AT BIRTH. Two lots emitted on the same spot cannot be rescued
 * downstream: nudging one off the other pushes it onto the next, and a lot
 * that never settles takes its building, its garden and its drive with it. So
 * the push runs at generation time against every lot already in the book,
 * including the fixed civic spots (square, well, stall) that were never
 * lane-derived at all.
 *
 * A LOT IS AN ANCHOR, SO IT ENDS ON LAND. A lot is not merely a place a sprite
 * stands: it is the point a building, its door, its drive and its keep-out disc
 * are all derived from, so a lot in the sea puts a drive in the sea even when
 * the building itself was walked inland. The reference pulls a lot in at
 * emission (compose.py:281-282) and then pushes it for separation with no land
 * test at all — measured, that left a lot in open water on 13 of 80 seeds. The
 * fix is at the END of the pipeline, not the middle: whatever survives the
 * separation relaxation is snapped inland before it is returned, so there is
 * exactly one place that decides this and exactly one place to test.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { snapInland } from './clearance'
import { hypot, LAYOUT_SPACE, type Point } from './space'

/** A plot: where it sits, the road point it fronts, and its facing. */
export interface Lot {
  /** Plot centre, in layout space. */
  c: Point
  /** The point on the lane this lot fronts — where its drive meets the road. */
  road: Point
  /** Unit vector from road to plot: which way the frontage looks. */
  face: Point
}

/**
 * compose.py:268 — the civic spots that exist before any lane-derived lot and
 * must never be built on: the village square, the well, the market stall.
 * They enter the separation book as lots with no frontage of their own.
 */
export const CIVIC_ANCHORS: readonly Point[] = [
  { x: 1200, y: 1010 },
  { x: 1050, y: 970 },
  { x: 1386, y: 958 },
]

/** compose.py:284 — minimum centre-to-centre gap, measured with y/0.8. */
export const LOT_SEPARATION = 168

/** Point and unit tangent at arc-length fraction `t` (compose.py _poly_point). */
export function polyPoint(
  pts: readonly Point[],
  t: number
): { at: Point; tangent: Point } {
  if (pts.length === 0) throw new Error('iso-layout: polyPoint on an empty polyline')
  const segs: { a: Point; b: Point; len: number }[] = []
  for (let i = 0; i < pts.length - 1; i++) {
    segs.push({ a: pts[i], b: pts[i + 1], len: hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y) })
  }
  if (segs.length === 0) return { at: pts[0], tangent: { x: 1, y: 0 } }
  const total = segs.reduce((s, g) => s + g.len, 0) || 1
  const want = t * total
  let acc = 0
  for (let i = 0; i < segs.length; i++) {
    const { a, b, len } = segs[i]
    if (acc + len >= want || i === segs.length - 1) {
      const f = (want - acc) / Math.max(1e-6, len)
      return {
        at: { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f },
        tangent: { x: (b.x - a.x) / Math.max(1e-6, len), y: (b.y - a.y) / Math.max(1e-6, len) },
      }
    }
    acc += len
  }
  return { at: pts[pts.length - 1], tangent: { x: 1, y: 0 } }
}

export interface LotsAlongOptions {
  /** Which side of the lane: +1 or -1 (the lane normal's sign). */
  side?: number
  /** How far back from the carriageway the plot centre sits. */
  setback?: number
  /** Arc-length window the lots spread over. */
  spread?: [number, number]
  /** Where "inland" is for the land snap — the island centre. */
  inlandTo?: Point
}

/**
 * n lots down one side of a lane, each fronting it.
 *
 * `taken` is every lot ALREADY placed anywhere in the layout — the separation
 * push runs against it and against the lots this call has emitted so far. It
 * is read, never written: the caller owns the book, so the function stays a
 * pure map from (lane, n, options, book) to lots.
 */
export function lotsAlong(
  lanePoints: readonly Point[],
  n: number,
  onLand: (x: number, y: number) => boolean,
  taken: readonly Point[] = [],
  opts: LotsAlongOptions = {}
): Lot[] {
  const side = opts.side ?? 1
  const setback = opts.setback ?? 140
  const [t0, t1] = opts.spread ?? [0.1, 0.9]
  const out: Lot[] = []
  for (let i = 0; i < n; i++) {
    const t = t0 + (t1 - t0) * ((i + 0.5) / n)
    const { at: road, tangent } = polyPoint(lanePoints, t)
    // the lane normal — the direction "back from the road" on this side
    const nx = -tangent.y * side
    const ny = tangent.x * side
    let cx = road.x + nx * setback
    let cy = road.y + ny * setback * 0.82
    if (!onLand(cx, cy)) {
      // the shore is closer than the setback: pull the plot in rather than
      // dropping it, because a dropped lot deletes a measured building.
      cx = road.x + nx * setback * 0.6
      cy = road.y + ny * setback * 0.5
    }
    for (const prev of [...taken, ...out.map((l) => l.c)]) {
      const d = hypot(cx - prev.x, (cy - prev.y) / 0.8)
      if (d < LOT_SEPARATION) {
        const push = (LOT_SEPARATION - d) / Math.max(1, d)
        cx += (cx - prev.x) * push
        cy += (cy - prev.y) * push * 0.8
      }
    }
    out.push({ c: { x: cx, y: cy }, road, face: { x: nx, y: ny } })
  }
  const toward = opts.inlandTo ?? { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy }
  // The snap runs LAST, after the separation relaxation, because relaxation is
  // what strands a lot: the pull-in at emission above is undone by the very
  // next push. A lot that cannot be snapped (no island under it at all) is
  // returned where it was rather than deleted — deleting it would remove a
  // measured building silently, and auditLayout reports it instead.
  return relax(out, taken).map((l) => ({
    ...l,
    c: snapInland(l.c, onLand, toward) ?? l.c,
  }))
}

/**
 * ONE PASS IS NOT SEPARATION. The reference pushes each new lot away from
 * every earlier one in a single sweep — but a push away from neighbour A moves
 * the lot toward neighbour B, and the sweep never looks again. Measured on the
 * officer row: six lots emitted, closest pair 95px apart against a 168px rule,
 * i.e. the rule silently did not hold for the case it exists for.
 *
 * So the sweep is followed by a bounded relaxation: repeat until no pair is
 * inside the rule, or until the budget runs out. It stays pure and
 * deterministic (fixed iteration order, fixed budget) and it converges in two
 * or three rounds on real input. Bounded rather than while-true because a
 * genuinely over-subscribed lane must terminate with the best it managed
 * rather than spin — and the layout audit will then report the overlap
 * honestly instead of the loop hiding it.
 */
const RELAX_ROUNDS = 12

/**
 * THE RELAXATION HAS NO LAND TEST, DELIBERATELY. One was written and then
 * removed on measurement: refusing any push that would cross the waterline
 * changed 47 of 80 measured layouts on a shrunken island and improved nothing
 * measurable — the worst frontage drift was 207/218/277px with it and
 * 207/216/277px without, and every lot ends on land either way because the snap
 * runs afterwards. A branch that alters output while guarding no property is a
 * control nothing can test, which is worse than no control: it reads as
 * protection. The land invariant belongs to one place, snapInland, and one
 * place is where it can be proven.
 */
function relax(lots: Lot[], taken: readonly Point[]): Lot[] {
  const cur = lots.map((l) => ({ ...l, c: { ...l.c } }))
  for (let round = 0; round < RELAX_ROUNDS; round++) {
    let moved = false
    for (let i = 0; i < cur.length; i++) {
      const others = [...taken, ...cur.filter((_, j) => j !== i).map((l) => l.c)]
      for (const prev of others) {
        const d = hypot(cur[i].c.x - prev.x, (cur[i].c.y - prev.y) / 0.8)
        if (d >= LOT_SEPARATION) continue
        const push = (LOT_SEPARATION - d) / Math.max(1, d)
        cur[i].c.x += (cur[i].c.x - prev.x) * push
        cur[i].c.y += (cur[i].c.y - prev.y) * push * 0.8
        moved = true
      }
    }
    if (!moved) break
  }
  return cur
}

/**
 * Build a lot AROUND an existing district anchor (compose.py lot_for).
 *
 * The anchor is authoritative — it encodes doctrine, not aesthetics. All the
 * lane contributes is the nearest road point (sampled at 41 stations, as in
 * the reference) and, from it, the frontage direction.
 */
export function lotFor(anchor: Point, lanePoints: readonly Point[]): Lot {
  let best: { d: number; at: Point } | null = null
  for (let i = 0; i <= 40; i++) {
    const { at } = polyPoint(lanePoints, i / 40)
    const d = hypot(at.x - anchor.x, at.y - anchor.y)
    if (!best || d < best.d) best = { d, at }
  }
  const road = best!.at
  const dx = anchor.x - road.x
  const dy = anchor.y - road.y
  const n = hypot(dx, dy) || 1
  return { c: { x: anchor.x, y: anchor.y }, road, face: { x: dx / n, y: dy / n } }
}

/**
 * The door of a lot, in layout space (compose.py:341 — the drive starts 18px
 * downhill of the plot centre, which is where the sprite's base edge is).
 */
export function lotDoor(lot: Lot): Point {
  return { x: lot.c.x, y: lot.c.y + 18 }
}

/**
 * Sprites have ONE baked isometric facing, so "facing the road" is a mirror:
 * pick the flip that puts the door on the road side (compose.py:831).
 */
export function lotFlip(lot: Lot): boolean {
  return lot.road.x > lot.c.x
}
