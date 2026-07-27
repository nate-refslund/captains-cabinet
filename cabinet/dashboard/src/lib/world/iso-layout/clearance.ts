/**
 * CLEARANCE — the ground-diamond rules. Nothing on a lane, nothing sharing
 * ground with a structure, blocked decoration DROPPED rather than stacked.
 *
 * PORTED FROM compose.py lines 417-506 and 547-560.
 *
 * ONE GEOMETRY, USED EVERYWHERE — or three different bugs (paid 2026-07-26).
 * Road clearance, prop stacking and both of their audits each carried their
 * own notion of "where a sprite is": a base point, a base line, a sprite
 * rectangle. Every one was wrong in a different way, and each audit certified
 * its own rule's blind spot, so the world was reported clean three times while
 * the Captain could see props standing on the road. An isometric sprite does
 * not stand on a line and does not occupy its bounding box — it stands on a
 * DIAMOND of half-width dw*0.42 and depth min(dh*0.55, dw*0.55), extending UP
 * the screen from its base centre. That geometry is defined once, in
 * ../projection.ts (groundDiamond / groundBox / groundOverlap), shared with
 * the renderer and the offline checks, and this module only calls it.
 *
 * THE TWO RULES MUST RESPECT EACH OTHER. Clearing a prop off the road pushed
 * it onto a neighbour; separating it from the neighbour pushed it back onto
 * the road; each pass undid the other and a house ended up on another house.
 * So the passes interleave for two rounds and THE ROAD GETS THE LAST WORD — a
 * blocked lane is the worse defect, and the road is the constraint a viewer
 * can see being violated from any zoom level.
 *
 * REJECTION BEATS NUDGING. Nudging oscillates: pushed off one neighbour
 * straight onto the next, settling on neither. Decoration is therefore
 * rejected at SAMPLING time (see scatter.ts) and anything that still cannot
 * settle is DROPPED — a missing bush is invisible, a bush growing through a
 * roof is not.
 *
 * NOTHING STANDS ON OPEN WATER (compose.py:530-539 and :870-883). Every anchor
 * in this library is authored against the fixed compass layout while the island
 * is a function of the org seed, so any anchor can be stranded offshore by a
 * coastline that never saw it. Two ported rules close that: walkInland() for a
 * thing being placed, snapInland() for an anchor other things are derived from.
 * Both are the reference's, and placeOnGround() is the one door structures come
 * through — so it either returns a point on land or returns null.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { groundBox, groundOverlap, type PxBox } from '../projection'
import type { LaneField } from './lanes'
import { LAYOUT_SPACE, type Point } from './space'

/** A sprite's drawn size in layout px — what the ground diamond derives from. */
export interface Footprint {
  w: number
  h: number
}

/** Something standing on the ground, for mutual clearance. */
export interface Occupant {
  at: Point
  size: Footprint
}

/** The ground box of an occupant — ../projection owns the geometry. */
export function occupantBox(o: Occupant): PxBox {
  return groundBox(o.at.x, o.at.y, o.size.w, o.size.h)
}

/**
 * Does the sprite's ground DIAMOND touch a lane? (compose.py _footprint_on_path)
 *
 * Sampling only the base row passed anything the road crossed higher up the
 * screen, which is how a market stall ended up squarely on the road while the
 * audit reported it clear. The diamond is probed at four depths, and the span
 * narrows toward its far vertex because that is the shape of a diamond.
 */
export function footprintOnLane(
  at: Point,
  size: Footprint,
  lanes: LaneField,
  grow = 0
): boolean {
  const half = Math.max(4, size.w * 0.42)
  const depth = Math.max(6, Math.min(size.h * 0.55, size.w * 0.55))
  for (const fy of [0, 0.35, 0.7, 1]) {
    const yy = at.y - depth * fy
    const span = half * (1 - 0.45 * fy)
    for (const fx of [-1, -0.55, 0, 0.55, 1]) {
      if (lanes.onLane(at.x + span * fx, yy, grow)) return true
    }
  }
  return false
}

/**
 * Is this ground already occupied? (compose.py _ground_taken)
 * `frac` is the share of the SMALLER footprint that counts as stacked — two
 * isometric buildings routinely overlap on SCREEN, and the one behind being
 * partly occluded is correct and desirable. Only a shared ground diamond
 * means they are stacked.
 */
export function groundTaken(
  at: Point,
  size: Footprint,
  occupied: readonly Occupant[],
  frac = 0.16
): boolean {
  return maxGroundOverlap(at, size, occupied) > frac
}

/**
 * The worst ground-diamond overlap this spot has with anything already standing
 * — the same quantity groundTaken thresholds, before the threshold.
 *
 * It exists because "is this taken?" is the wrong question when NOTHING is
 * free: clearOfLane's fallback then has to choose between spots that are all
 * taken, and a boolean cannot rank them.
 */
export function maxGroundOverlap(
  at: Point,
  size: Footprint,
  occupied: readonly Occupant[]
): number {
  const a = groundBox(at.x, at.y, size.w, size.h)
  let worst = 0
  for (const o of occupied) {
    const v = groundOverlap(a, occupantBox(o))
    if (v > worst) worst = v
  }
  return worst
}

/** Where "inland" is when nothing says otherwise: the island centre. */
const ISLAND_CENTRE: Point = { x: LAYOUT_SPACE.cx, y: LAYOUT_SPACE.cy }

/**
 * Walk a sprite inland until it has ground under it (compose.py:530-539).
 *
 * The reference is explicit about why this is a walk and not a drop: dropping
 * the sprite "silently deletes whole districts whenever the coastline moves".
 * So it steps up to 45% of the way toward the island centre in 40 stations and
 * takes the first one with land under the sprite's base — and returns null only
 * when there is no ground within that reach, which is the reference's `return
 * None` and means the thing does not exist rather than standing on the sea.
 *
 * The probe is (x, y-2), the reference's: a base sitting exactly on the
 * waterline row reads as land in a mask that was blurred and thresholded, and
 * the sprite is drawn UP the screen from its base.
 */
export function walkInland(
  at: Point,
  onLand: (x: number, y: number) => boolean,
  toward: Point = ISLAND_CENTRE,
  steps = 40,
  reach = 0.45
): Point | null {
  if (onLand(at.x, at.y - 2)) return at
  for (let t = 1; t <= steps; t++) {
    const f = (t / steps) * reach
    const x = at.x + (toward.x - at.x) * f
    const y = at.y + (toward.y - at.y) * f
    if (onLand(x, y - 2)) return { x, y }
  }
  return null
}

/** compose.py snap()'s margin: how much ground an anchor must clear each way. */
export const SNAP_MARGIN = 70

/**
 * The ground test snapInland accepts a station on: the point AND its margin in
 * every direction (compose.py:879-880).
 *
 * Exported because a second stage — the post-snap separation relaxation in
 * lots.ts — has to move a lot only to ground the snap would also have taken,
 * and two copies of that predicate is how the two stages drift into disagreeing
 * about where land is.
 */
export function clearsMargin(
  x: number,
  y: number,
  onLand: (x: number, y: number) => boolean,
  margin = SNAP_MARGIN
): boolean {
  return (
    onLand(x, y) &&
    onLand(x, y + margin) &&
    onLand(x - margin, y) &&
    onLand(x + margin, y) &&
    onLand(x, y - margin)
  )
}

/**
 * Pull an ANCHOR inland until it and its footprint sit on land (compose.py
 * snap(), :870-883).
 *
 * The difference from walkInland is what is being moved: an anchor is a point
 * other things are derived FROM — a district's keep-out disc, a lot's centre,
 * the plot a drive is drawn to. It therefore has to clear a margin in every
 * direction rather than merely have ground under one pixel, and it may travel
 * the whole way to the centre rather than 45% of it.
 *
 * The reference's last resort is the island centre. That is only honest if the
 * centre is itself land, so this checks rather than assumes: an island with no
 * centre (a degenerate radius, a cove that ate the island) returns null and the
 * caller decides, instead of handing back a point in the sea.
 */
export function snapInland(
  at: Point,
  onLand: (x: number, y: number) => boolean,
  toward: Point = ISLAND_CENTRE,
  margin = SNAP_MARGIN,
  steps = 60
): Point | null {
  for (let t = 0; t <= steps; t++) {
    const f = t / steps
    const x = at.x + (toward.x - at.x) * f
    const y = at.y + (toward.y - at.y) * f
    if (clearsMargin(x, y, onLand, margin)) {
      // The reference rounds to whole pixels here because it is about to draw
      // on a bitmap. This library is float layout space, and rounding moved a
      // lot off the exact 168px separation it had just been relaxed to — a
      // quantisation that breaks a measured invariant for no benefit.
      return { x, y }
    }
  }
  return onLand(toward.x, toward.y) ? { x: toward.x, y: toward.y } : null
}

export interface SettleOptions {
  /** Overlap fraction that counts as stacked. */
  overlap?: number
  /** How many push rounds before giving up. */
  tries?: number
  /** Push distance per round, in layout px. */
  step?: number
}

/**
 * Push a thing out of anything already standing on the same ground
 * (compose.py _clear_of_props). Returns `settled: false` when it was squeezed
 * between neighbours and never found clear ground — the caller decides whether
 * that means "draw it anyway" (a measured structure) or "drop it" (decoration).
 */
export function settleAgainstOccupants(
  at: Point,
  size: Footprint,
  occupied: readonly Occupant[],
  opts: SettleOptions = {}
): { at: Point; settled: boolean } {
  const overlap = opts.overlap ?? 0.16
  const tries = opts.tries ?? 26
  const step = opts.step ?? 17
  let cx = at.x
  let cy = at.y
  for (let i = 0; i < tries; i++) {
    const a = groundBox(cx, cy, size.w, size.h)
    let hit: Point | null = null
    for (const o of occupied) {
      if (groundOverlap(a, occupantBox(o)) > overlap) {
        hit = o.at
        break
      }
    }
    if (!hit) return { at: { x: cx, y: cy }, settled: true }
    let dx = cx - hit.x
    let dy = cy - hit.y
    let n = Math.sqrt(dx * dx + dy * dy)
    if (n < 1) {
      // exactly coincident: there is no direction to push along, so break the
      // tie with a fixed one rather than dividing by ~0 and flinging it away.
      dx = 1
      dy = 0.6
      n = 1.166
    }
    cx += (dx / n) * step
    cy += (dy / n) * step * 0.6
  }
  return { at: { x: cx, y: cy }, settled: false }
}

export interface ClearOfLaneOptions {
  /** How far out the ring search will look. */
  reach?: number
  /** Refuse landing spots whose ground is already taken. */
  respectOccupants?: boolean
  /** Overlap fraction that counts as taken. */
  frac?: number
}

/**
 * Push a thing fully off the carriageway, onto ground nothing else is using
 * (compose.py _clear_of_path). Rings outward in 16 directions, squashed 0.66
 * vertically because a ring on the ground projects squashed.
 *
 * The `fallback` is the reference's and it matters: a spot that is off the
 * road but shares ground is remembered and used only if NOTHING fully clear
 * exists — because the road wins, and a slight stack beats a blocked lane.
 *
 * AND IT IS THE SLIGHTEST STACK AVAILABLE, not the first one the ring happened
 * to find. Two neighbouring lots on a crowded shore ran the same deterministic
 * ring search, both fell through to the fallback, and both took the same first
 * off-road spot — two officer dwellings 5px apart on org-13, which auditLayout
 * reported and no arm covered. "A slight stack beats a blocked lane" is only an
 * argument for the SLIGHTEST one; ranking the candidates by shared ground costs
 * one number and is what the sentence already claimed.
 */
export function clearOfLane(
  at: Point,
  size: Footprint,
  lanes: LaneField,
  onLand: (x: number, y: number) => boolean,
  occupied: readonly Occupant[],
  opts: ClearOfLaneOptions = {}
): Point {
  const reach = opts.reach ?? 300
  const respect = opts.respectOccupants ?? true
  const frac = opts.frac ?? 0.16
  if (!footprintOnLane(at, size, lanes)) return at
  let fallback: Point | null = null
  let fallbackOverlap = Infinity
  for (let r = 8; r < reach; r += 7) {
    for (let i = 0; i < 16; i++) {
      const ang = (i * Math.PI * 2) / 16
      const p = { x: at.x + Math.cos(ang) * r, y: at.y + Math.sin(ang) * r * 0.66 }
      if (!onLand(p.x, p.y) || footprintOnLane(p, size, lanes)) continue
      if (respect) {
        const overlap = maxGroundOverlap(p, size, occupied)
        if (overlap > frac) {
          if (overlap < fallbackOverlap) {
            fallbackOverlap = overlap
            fallback = p
          }
          continue
        }
      }
      return p
    }
  }
  return fallback ?? at
}

export interface PlaceOptions {
  /** Tighter thresholds and a longer search — for structures. */
  strict?: boolean
  /** Drop rather than stack when it never settles. */
  dropIfBlocked?: boolean
  /** Skip the lane rule (fences deliberately gap where a lane crosses). */
  avoidLane?: boolean
  /** Where the land walk heads: the island centre (compose.py ICX/ICY). */
  inlandTo?: Point
}

/**
 * Settle one thing against both rules and report where it ended up, or null if
 * it must be dropped (compose.py place(), lines 530-560).
 *
 * The interleave is the whole point: nudging a prop out of its neighbour could
 * push it back into the road, and clearing the road could push it into a
 * neighbour. Two rounds settle it, and the road gets the last word.
 *
 * THE LAND RULE BOOKENDS THE SETTLE, and the closing half is this port's, not
 * the reference's. compose.py walks inland once, before the two rounds, and its
 * _clear_of_props has no land test at all — so a prop pushed off a neighbour
 * can be pushed straight back over the waterline and the reference draws it
 * there. Re-testing afterwards is what turns "nothing stands on open water"
 * from an intention into a property this function GUARANTEES: it returns a
 * point on land, or it returns null and the caller draws nothing.
 */
export function placeOnGround(
  at: Point,
  size: Footprint,
  lanes: LaneField,
  onLand: (x: number, y: number) => boolean,
  occupied: readonly Occupant[],
  opts: PlaceOptions = {}
): Point | null {
  const strict = opts.strict ?? false
  const toward = opts.inlandTo ?? ISLAND_CENTRE
  const frac = strict ? 0.04 : 0.1
  const grounded = walkInland(at, onLand, toward)
  if (!grounded) return null
  let p = grounded
  let settled = true
  for (let round = 0; round < 2; round++) {
    const s = settleAgainstOccupants(p, size, occupied, {
      overlap: strict ? 0.04 : 0.1,
      tries: strict ? 60 : 30,
      step: strict ? 30 : 19,
    })
    p = s.at
    settled = s.settled
    if (opts.avoidLane !== false) {
      p = clearOfLane(p, size, lanes, onLand, occupied, { frac })
    }
  }
  if (!onLand(p.x, p.y - 2)) {
    const back = walkInland(p, onLand, toward)
    if (!back) return null
    // the ring search only ever lands on ground, so this cannot undo the walk
    p = opts.avoidLane === false ? back : clearOfLane(back, size, lanes, onLand, occupied, { frac })
    if (!onLand(p.x, p.y - 2)) return null
  }
  if (opts.dropIfBlocked && !settled) return null
  return p
}
