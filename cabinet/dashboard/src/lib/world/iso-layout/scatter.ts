/**
 * SCATTER — Bridson Poisson-disk sampling with a DENSITY FIELD.
 *
 * PORTED FROM compose.py lines 604-682 and 1217-1263.
 *
 * WHY A DENSITY FIELD AT ALL. Uniform scatter is what made the planting read
 * as random rather than as a place: the same spacing in the village square as
 * at the forest edge, which no real landscape has. Here density(x,y) in 0..1
 * sets the LOCAL exclusion radius, so growth thickens toward the treeline and
 * thins through the meadow. That is the ecotope idea from the settlement-
 * generation literature and it is the standard fix for exactly this symptom.
 *
 * WHAT A DENSITY FIELD CANNOT DO is stop anything. This docstring used to claim
 * planting "stops dead on paving and on the fields"; it does not and cannot —
 * at density 0 the exclusion radius is still rMax, which means "spaced far
 * apart", never "not here". Measured against that claim, 72-80% of all planting
 * stood inside a keep-out disc. Stopping is the `pick` predicate's job, and the
 * caller composes it (see index.ts free()): the field decides how CROWDED an
 * admissible spot is, the predicate decides whether it is admissible at all.
 *
 * REJECTION AT SAMPLING TIME. A candidate whose ground is already taken, or
 * whose ground diamond touches a lane, is REJECTED — never sampled badly and
 * then nudged. Nudging oscillates between two neighbours and settles on
 * neither, and the failure is silent: the prop still draws, just wrongly. This
 * is the rule the whole clearance chapter was rewritten around.
 *
 * SEEDED. random.uniform / random.randrange / random.choice in the reference
 * all become one seededRng stream from hash.ts, so an org's island plants the
 * same way forever. The stream is consumed in the reference's exact order, so
 * changing one draw does not silently reshuffle every later one.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { fnv1a, seededRng } from '../hash'
import { footprintOnLane, groundTaken, type Footprint, type Occupant } from './clearance'
import type { LaneField } from './lanes'
import { clamp01, hypot, LAYOUT_SPACE, type LayoutSpace, type Point } from './space'

/** How wild a spot is: 1 = forest edge, 0 = paved village. */
export type DensityField = (x: number, y: number) => number

/** A district's keep-out disc — the village core suppresses growth around it. */
export interface District {
  at: Point
  r: number
}

/**
 * compose.py wildness(): coastal proximity raises it, districts and lanes
 * suppress it. This is the field that makes the treeline a treeline.
 *
 *   coast = 1 - clamp((edge - d) / (edge*0.55))     1 near the waterline
 *   civic = max over districts of 1 - dd/(r*1.7)
 *   lane  = 1 if within 46px of a carriageway
 *   -> clamp(coast*1.15 - civic*0.72 - lane*0.45 + 0.10)
 */
export function wildnessField(
  centre: Point,
  landEdge: (angle: number) => number,
  districts: readonly District[],
  lanes: LaneField
): DensityField {
  return (x, y) => {
    const ang = Math.atan2((y - centre.y) / 0.92, x - centre.x)
    const e = landEdge(ang)
    const d = hypot(x - centre.x, (y - centre.y) / 0.92)
    const coast = 1 - clamp01((e - d) / Math.max(1, e * 0.55))
    let civic = 0
    for (const district of districts) {
      const dd = hypot(x - district.at.x, (y - district.at.y) / 0.9)
      if (dd < district.r * 1.7) civic = Math.max(civic, 1 - dd / (district.r * 1.7))
    }
    const lane = lanes.nearLane(x, y, 46) ? 1 : 0
    return clamp01(coast * 1.15 - civic * 0.72 - lane * 0.45 + 0.1)
  }
}

export interface ScatterItem {
  kind: string
  at: Point
  flip: boolean
}

export interface ScatterOptions {
  space?: LayoutSpace
  /** Sprite names to draw from; one is chosen per point, seeded. */
  kinds: readonly string[]
  /** The drawn size used for every clearance test on these points. */
  size: Footprint
  /** Extra admissibility (inside the treeline, on the shore band, ...). */
  pick: (x: number, y: number) => boolean
  density: DensityField
  onLand: (x: number, y: number) => boolean
  lanes: LaneField
  occupied: readonly Occupant[]
  /** Bridson's k: candidates tried per active point. */
  k?: number
  /** Exclusion radius at density 1 and at density 0. */
  rMin?: number
  rMax?: number
  /** Hard cap on points emitted. */
  cap?: number
  /** Overlap fraction that counts as taken ground (sampling-time reject). */
  frac?: number
}

/**
 * Bridson-style Poisson disk sampling with a density field.
 *
 * Returns points in emission order. The caller adds them to the occupancy book
 * if later stages must avoid them — this function never mutates its inputs.
 */
export function poissonScatter(seedIn: string | number, opts: ScatterOptions): ScatterItem[] {
  // An empty kind set means the era has nothing of this sort to plant. Return
  // early rather than emit points with an undefined kind: a point that draws
  // nothing is a hole in the occupancy book that a later pass would fill.
  if (opts.kinds.length === 0) return []
  const space = opts.space ?? LAYOUT_SPACE
  const k = opts.k ?? 18
  const rMin = opts.rMin ?? 44
  const rMax = opts.rMax ?? 190
  const cap = opts.cap ?? 400
  const frac = opts.frac ?? 0.05
  const rng = seededRng(typeof seedIn === 'number' ? seedIn >>> 0 : fnv1a(seedIn))

  const radius = (x: number, y: number) => rMax - (rMax - rMin) * clamp01(opts.density(x, y))

  const cell = rMin / Math.SQRT2
  const grid = new Map<number, number[]>()
  const key = (gx: number, gy: number) => (gx + 1024) * 8192 + (gy + 1024)
  const cellOf = (v: number) => Math.floor(v / cell)

  const admissible = (x: number, y: number): boolean => {
    if (!(x > 40 && x < space.w - 40 && y > 40 && y < space.h - 40)) return false
    if (!opts.onLand(x, y) || !opts.pick(x, y)) return false
    const p = { x, y }
    // keep-out at SAMPLING time — never sample badly and hope a nudge rescues it
    if (groundTaken(p, opts.size, opts.occupied, frac)) return false
    if (footprintOnLane(p, opts.size, opts.lanes, 0)) return false
    const rr = radius(x, y)
    const gx = cellOf(x)
    const gy = cellOf(y)
    const span = Math.floor(rr / cell) + 1
    for (let ix = gx - span; ix <= gx + span; ix++) {
      for (let iy = gy - span; iy <= gy + span; iy++) {
        const bucket = grid.get(key(ix, iy))
        if (!bucket) continue
        for (let i = 0; i < bucket.length; i += 3) {
          const dx = x - bucket[i]
          const dy = (y - bucket[i + 1]) * 1.35
          const reach = Math.max(rr, bucket[i + 2])
          if (dx * dx + dy * dy < reach * reach) return false
        }
      }
    }
    return true
  }

  const remember = (x: number, y: number, rr: number) => {
    const kk = key(cellOf(x), cellOf(y))
    const bucket = grid.get(kk)
    if (bucket) bucket.push(x, y, rr)
    else grid.set(kk, [x, y, rr])
  }

  const active: Point[] = []
  const out: Point[] = []

  // seed points: up to 12 admissible spots from 600 uniform tries
  for (let i = 0; i < 600 && active.length < 12; i++) {
    const x = 60 + rng() * (space.w - 120)
    const y = 60 + rng() * (space.h - 120)
    if (!admissible(x, y)) continue
    remember(x, y, radius(x, y))
    active.push({ x, y })
    out.push({ x, y })
  }

  while (active.length > 0 && out.length < cap) {
    const i = Math.floor(rng() * active.length)
    const a = active[i]
    const rr = radius(a.x, a.y)
    let placed = false
    for (let attempt = 0; attempt < k; attempt++) {
      const ang = rng() * Math.PI * 2
      const dist = rr + rng() * rr // uniform in [rr, 2rr), as in the reference
      const x = a.x + Math.cos(ang) * dist
      const y = a.y + Math.sin(ang) * dist * 0.72
      if (!admissible(x, y)) continue
      remember(x, y, radius(x, y))
      active.push({ x, y })
      out.push({ x, y })
      placed = true
      break
    }
    if (!placed) active.splice(i, 1)
  }

  return out.map((p) => ({
    kind: opts.kinds[Math.min(opts.kinds.length - 1, Math.floor(rng() * opts.kinds.length))],
    at: p,
    flip: rng() < 0.5,
  }))
}
