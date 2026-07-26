/**
 * LANES — the road network, as data.
 *
 * PORTED FROM compose.py lines 185-236 and 678-682.
 *
 * THE ROAD NETWORK IS ITSELF A LADDER RUNG. Its WIDTH follows the rung
 * (dirt_path .. cobbled_road) and its EXTENT follows the era: a camp has ONE
 * worn track down to the water, not a nine-way junction with nothing on it.
 * Leaving the full network in place at camp is exactly what made the hatch
 * frame read as a village with its houses deleted — the reference records that
 * failure in its own comment at compose.py:205-207.
 *
 * ONE DELIBERATE DIVERGENCE FROM THE REFERENCE. compose.py gates every lane
 * except two on `hamlet_only`, so a camp still draws the main street AND the
 * great-house forecourt spur — two lanes, against its own stated rule of one
 * worn track. The Captain's ruling states the rule, so the rule wins: the
 * forecourt spur is village dressing (a forecourt is a consequence of there
 * being a house with a front), and at camp only the track to the water exists.
 *
 * A lane is emitted as its JITTERED CENTRELINE plus a width, not as a raster.
 * The renderer paints it; the layout stages test against it. compose.py paints
 * overlapping ellipses of radius (w/2, w/2*0.72) every ~16px along the line and
 * thresholds the result, so the occupancy test here is the same family of
 * discs — same geometry, no bitmap.
 *
 * PURE: no clocks, no unseeded randomness (the wobble is a sine of position,
 * exactly as in the reference), no IO, no DOM.
 */
import { hypot, type Era, type Point, type RoadRung } from './space'

/** compose.py:208 — lane width multiplier per road rung. */
export const ROAD_WIDTH: Record<RoadRung, number> = {
  dirt_path: 0.44,
  dirt_worn: 0.62,
  gravel_road: 0.82,
  cobbled_road: 1.0,
}

/** compose.py:189-190 — the two fixed civic points every lane hangs off. */
export const SQUARE: Point = { x: 1200, y: 1010 }
export const GREAT: Point = { x: 1200, y: 800 }

/** A lane's role, so the renderer and the era gate can both reason about it. */
export type LaneKind = 'main' | 'spur' | 'district' | 'coastal' | 'driveway'

export interface LaneSpec {
  key: string
  kind: LaneKind
  /** Control points, before the wobble. */
  points: readonly Point[]
  /** Nominal width at rung 1.0, before the rung multiplier. */
  width: number
  /** False = this lane exists at camp too. */
  villageOnly: boolean
}

/**
 * The network, verbatim from compose.py:216-235 (control points and widths)
 * with each lane's era gate carried alongside it rather than as a call flag.
 * The `main` track runs square -> harbour head: that is the one a camp keeps,
 * because a camp's whole reason for a road is reaching the water.
 */
export const LANE_SPECS: readonly LaneSpec[] = [
  {
    key: 'main',
    kind: 'main',
    points: [SQUARE, { x: 1200, y: 1140 }, { x: 1215, y: 1270 }, { x: 1200, y: 1360 }],
    width: 62,
    villageOnly: false,
  },
  { key: 'forecourt', kind: 'spur', points: [SQUARE, GREAT], width: 54, villageOnly: true },
  {
    key: 'north',
    kind: 'district',
    points: [GREAT, { x: 1190, y: 640 }, { x: 1200, y: 470 }, { x: 1200, y: 380 }],
    width: 44,
    villageOnly: true,
  },
  {
    key: 'ne',
    kind: 'district',
    points: [{ x: 1250, y: 760 }, { x: 1420, y: 640 }, { x: 1580, y: 520 }],
    width: 40,
    villageOnly: true,
  },
  {
    key: 'east',
    kind: 'district',
    points: [{ x: 1270, y: 950 }, { x: 1500, y: 900 }, { x: 1720, y: 830 }],
    width: 44,
    villageOnly: true,
  },
  {
    key: 'se',
    kind: 'district',
    points: [{ x: 1290, y: 1060 }, { x: 1480, y: 1120 }, { x: 1650, y: 1180 }],
    width: 40,
    villageOnly: true,
  },
  {
    key: 'west',
    kind: 'district',
    points: [{ x: 1140, y: 980 }, { x: 930, y: 930 }, { x: 720, y: 860 }],
    width: 44,
    villageOnly: true,
  },
  {
    key: 'nw',
    kind: 'district',
    points: [{ x: 1150, y: 720 }, { x: 960, y: 600 }, { x: 800, y: 500 }],
    width: 36,
    villageOnly: true,
  },
  {
    key: 'sw',
    kind: 'district',
    points: [{ x: 1150, y: 1090 }, { x: 980, y: 1170 }, { x: 840, y: 1220 }],
    width: 38,
    villageOnly: true,
  },
  {
    key: 'coastal',
    kind: 'coastal',
    points: [{ x: 720, y: 860 }, { x: 620, y: 1030 }, { x: 700, y: 1210 }, { x: 840, y: 1220 }],
    width: 30,
    villageOnly: true,
  },
]

/**
 * The LOT-BEARING lanes (compose.py:244-251). These are the same roads under
 * slightly different control points: the reference walks lots along a lane
 * whose ends differ from the painted one (`west` starts further out so the
 * officer row has frontage on both sides). Kept as its own table for exactly
 * the reason the reference keeps it: lots front a road's IDEALISED line, and
 * snapping them to the wobbled paint would scatter the row.
 */
export const LOT_LANES: Record<string, readonly Point[]> = {
  west: [{ x: 742, y: 742 }, { x: 656, y: 900 }, { x: 712, y: 1050 }],
  north: [{ x: 1200, y: 800 }, { x: 1190, y: 640 }, { x: 1200, y: 470 }, { x: 1200, y: 380 }],
  east: [{ x: 1270, y: 950 }, { x: 1500, y: 900 }, { x: 1720, y: 830 }],
  ne: [{ x: 1250, y: 760 }, { x: 1420, y: 640 }, { x: 1580, y: 520 }],
  se: [{ x: 1290, y: 1060 }, { x: 1480, y: 1120 }, { x: 1650, y: 1180 }],
  main: [{ x: 1200, y: 1010 }, { x: 1200, y: 1140 }, { x: 1215, y: 1270 }, { x: 1200, y: 1360 }],
}

/** One painted lane: the wobbled centreline plus the width it is painted at. */
export interface Lane {
  key: string
  kind: LaneKind
  width: number
  /** Dense centreline samples, ~16 layout px apart, wobble applied. */
  path: Point[]
}

/**
 * compose.py lane(): walk the polyline at ~16px, wobbling with a sine of the
 * parameter and the segment origin. Deterministic by construction — there is
 * no RNG in the reference here either, and that is why the same org always
 * gets the same street.
 */
export function laneCentreline(points: readonly Point[], jitter = 9): Point[] {
  const out: Point[] = []
  let prev = points[0]
  for (let i = 1; i < points.length; i++) {
    const p = points[i]
    const steps = Math.max(2, Math.floor(hypot(p.x - prev.x, p.y - prev.y) / 16))
    for (let s = 0; s <= steps; s++) {
      const t = s / steps
      const x = prev.x + (p.x - prev.x) * t + Math.sin(t * 3.1 + prev.x) * jitter
      const y = prev.y + (p.y - prev.y) * t + Math.cos(t * 2.7 + prev.y) * jitter * 0.6
      out.push({ x, y })
    }
    prev = p
  }
  return out
}

/** compose.py:209 — `max(13, int(w*_rw))`, the painted width for a rung. */
export function laneWidth(nominal: number, rung: RoadRung): number {
  return Math.max(13, Math.trunc(nominal * ROAD_WIDTH[rung]))
}

/**
 * The lane occupancy field: "is this point on a carriageway?"
 *
 * compose.py samples a painted, blurred, thresholded raster. The equivalent
 * without a bitmap is the union of the discs that raster was painted from —
 * radius w/2 across, w/2*0.72 down, because a circle on the ground projects
 * squashed. Bucketed on a uniform grid because the scatter stage asks this
 * question tens of thousands of times.
 */
export interface LaneField {
  readonly lanes: readonly Lane[]
  /** compose.py on_path(). `grow` widens the disc, for a "near" query. */
  onLane(x: number, y: number, grow?: number): boolean
  /** compose.py near_path(x,y,r): the same 3x3 probe the reference uses. */
  nearLane(x: number, y: number, r?: number): boolean
}

const SQUASH = 0.72
const BUCKET = 64

export function buildLaneField(lanes: readonly Lane[]): LaneField {
  // grid of (x, y, halfWidth) discs
  const grid = new Map<number, number[]>()
  // Offset before packing so a negative bucket (a query near the canvas edge)
  // can never alias a positive one — a collision here would report clear road
  // as occupied, silently, in one corner of the map only.
  const key = (gx: number, gy: number) => (gx + 1024) * 8192 + (gy + 1024)
  let maxHalf = 1
  const add = (x: number, y: number, half: number) => {
    const k = key(Math.floor(x / BUCKET), Math.floor(y / BUCKET))
    const cell = grid.get(k)
    if (cell) cell.push(x, y, half)
    else grid.set(k, [x, y, half])
  }
  for (const lane of lanes) {
    const half = lane.width / 2
    if (half > maxHalf) maxHalf = half
    // RESAMPLE rather than trust the caller's spacing. The field is a union of
    // discs, so any gap wider than a disc is a hole in the road that every
    // clearance rule then reports as clear ground. laneCentreline already
    // emits ~16px apart, but a Lane is a plain object anyone can construct,
    // and a hole here fails SILENTLY and only in one place on the map.
    const spacing = Math.max(2, Math.min(half, 16))
    for (let i = 0; i < lane.path.length; i++) {
      const a = lane.path[i]
      add(a.x, a.y, half)
      const b = lane.path[i + 1]
      if (!b) continue
      const len = hypot(b.x - a.x, b.y - a.y)
      const n = Math.floor(len / spacing)
      for (let s = 1; s < n; s++) {
        const t = s / n
        add(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, half)
      }
    }
  }

  const onLane = (x: number, y: number, grow = 0): boolean => {
    const reach = maxHalf + grow
    const gx0 = Math.floor((x - reach) / BUCKET)
    const gx1 = Math.floor((x + reach) / BUCKET)
    const gy0 = Math.floor((y - reach / SQUASH) / BUCKET)
    const gy1 = Math.floor((y + reach / SQUASH) / BUCKET)
    for (let gx = gx0; gx <= gx1; gx++) {
      for (let gy = gy0; gy <= gy1; gy++) {
        const cell = grid.get(key(gx, gy))
        if (!cell) continue
        for (let i = 0; i < cell.length; i += 3) {
          const hw = cell[i + 2] + grow
          const dx = (x - cell[i]) / hw
          const dy = (y - cell[i + 1]) / (hw * SQUASH)
          if (dx * dx + dy * dy <= 1) return true
        }
      }
    }
    return false
  }

  return {
    lanes,
    onLane,
    nearLane(x, y, r = 46) {
      for (const dx of [-r, 0, r]) for (const dy of [-r, 0, r]) if (onLane(x + dx, y + dy)) return true
      return false
    },
  }
}

/**
 * The network an (era, rung) actually has. A camp keeps the single track to
 * the water; everything else is a consequence of there being a village.
 */
export function buildLanes(era: Era, rung: RoadRung, specs: readonly LaneSpec[] = LANE_SPECS): Lane[] {
  const camp = era === 'camp'
  const out: Lane[] = []
  for (const spec of specs) {
    if (camp && spec.villageOnly) continue
    out.push({
      key: spec.key,
      kind: spec.kind,
      width: laneWidth(spec.width, rung),
      // a camp's ONE track is a worn track, so it wobbles more, not less
      path: laneCentreline(spec.points, camp ? 12 : 9),
    })
  }
  return out
}
