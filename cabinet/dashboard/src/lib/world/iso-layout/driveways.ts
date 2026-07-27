/**
 * DRIVEWAYS — door to lane, on the two isometric ground axes, as an L.
 *
 * PORTED FROM compose.py lines 291-307.
 *
 * A straight screen-space line between a door and a lane cuts across the grain
 * of an isometric world and reads as wrong immediately — it is the single
 * fastest way to make a hand-built iso scene look like a top-down scene with a
 * skew applied. The ground axes run at slope +/-ISO_AXIS_SLOPE (0.5 on a 2:1
 * tile), so every leg of the route runs along one of them and the corner is a
 * real corner.
 *
 * THE ELBOW IS FORCED, not searched. With u = dx/2 + dy, the first leg travels
 * (u, u/2) — slope +1/2 — and the remainder is (dx-u, dy-u/2), which reduces
 * to slope -1/2 identically for every input. There is no case analysis and no
 * degenerate branch: the two axes span the plane, so exactly one L exists.
 *
 * ONLY LOTS THAT WILL ACTUALLY BE BUILT GET A DRIVE (compose.py:336). A path
 * to empty grass is a lie about what the org has, and the whole point of this
 * world is that it is a function of state.
 *
 * ORDERING: driveways must exist BEFORE the ground is painted, because the
 * drive is part of the paved surface and part of the lane occupancy field that
 * every later stage tests against. index.ts owns that order.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { clipToLand, laneCentreline, type Lane, ROAD_WIDTH } from './lanes'
import { ISO_AXIS_SLOPE, type Point, type RoadRung } from './space'

/**
 * Route a -> b using only the two isometric ground axes, as an L.
 * Returns [a, elbow, b] — three points, two legs.
 */
export function isoRoute(a: Point, b: Point): [Point, Point, Point] {
  const dx = b.x - a.x
  const dy = b.y - a.y
  // u is the distance travelled along the +slope axis. ISO_AXIS_SLOPE is the
  // renderer's tile ratio, so a change of tile aspect moves the elbow with it
  // instead of leaving a hardcoded 0.5 behind.
  const u = dx * ISO_AXIS_SLOPE + dy
  return [a, { x: a.x + u, y: a.y + u * ISO_AXIS_SLOPE }, b]
}

export interface Driveway {
  /** The building door this drive serves. */
  door: Point
  /** Where it meets the carriageway. */
  road: Point
  /**
   * [door, elbow, road] — the L, on the two iso axes. This is the RECORD of
   * which door joins which road, not the painted surface: the surface is this
   * drive's Lane in `layout.lanes`, which is clipped to land like every other
   * lane. Paint the route directly and a drive whose elbow overhangs the shore
   * is drawn on the sea.
   */
  route: [Point, Point, Point]
  width: number
}

/** compose.py:341 — `width=max(15, int(28*_rw))`: the drive follows the rung. */
export function drivewayWidth(rung: RoadRung): number {
  return Math.max(15, Math.trunc(28 * ROAD_WIDTH[rung]))
}

/** One drive from a door to the road point its lot fronts. */
export function driveway(door: Point, road: Point, rung: RoadRung): Driveway {
  return { door, road, route: isoRoute(door, road), width: drivewayWidth(rung) }
}

/**
 * A drive as a Lane, so it joins the SAME occupancy field the carriageways
 * live in. compose.py paints drives into the same `paths` bitmap the clearance
 * rules later sample; splitting them into a second surface here would give the
 * clearance rules a road they cannot see, which is the exact defect class this
 * port exists to remove.
 *
 * The drive is painted with jitter 3 (compose.py:307), not 9: a drive is a
 * short deliberate thing, and a wobble that reads as character on a lane reads
 * as a mistake on ten metres of gravel.
 *
 * CLIPPED TO LAND like any other lane, and for the same reason: compose.py
 * paints drives into the same `paths` bitmap that is intersected with the land
 * mask at :343. Measured before this clip, drive samples in open water were a
 * third of the offending lanes.
 */
export function drivewayLane(
  d: Driveway,
  key: string,
  onLand: (x: number, y: number) => boolean
): Lane {
  return {
    key,
    kind: 'driveway',
    width: d.width,
    runs: clipToLand(laneCentreline(d.route, 3), onLand),
  }
}
