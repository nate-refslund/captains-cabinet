/**
 * SCATTER — Bridson Poisson-disk sampling with a DENSITY FIELD.
 *
 * PORTED FROM compose.py lines 604-682 and 1217-1263.
 *
 * WHY A DENSITY FIELD AT ALL. Uniform scatter is what made the planting read
 * as random rather than as a place: the same spacing everywhere, which no real
 * landscape has. Here density(x,y) in 0..1 sets the LOCAL exclusion radius, so
 * growth thickens where nothing has been cut and thins toward a clearing's rim.
 * That is the ecotope idea from the settlement-generation literature and it is
 * the standard fix for exactly this symptom.
 *
 * THE FIELD THAT FEEDS IT INVERTED ON 2026-07-27 (Captain direction, see
 * ./clearing). It used to be `wildnessField` — coastal proximity RAISED it and
 * districts and lanes suppressed it, i.e. a coastal ring of trees around a
 * sparse interior, wilderness as decoration placed around the buildings. It is
 * now `ClearedGround.timber`: 1 across every acre nobody has cut, falling to 0
 * across the edge band of each clearing. Timber is the island's default state
 * and clearing is subtractive, so the gradient this function consumes now sits
 * at every treeline instead of at the coast. `wildnessField` was DELETED rather
 * than left beside it — two density notions is how the module ends up with a
 * dead one that a test still pins.
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
import {
  buildOccupancyIndex,
  footprintOnLane,
  type Footprint,
  type Occupant,
} from './clearance'
import type { LaneField } from './lanes'
import { clamp01, LAYOUT_SPACE, type LayoutSpace, type Point } from './space'

/** How much timber stands here: 1 = closed canopy, 0 = cleared ground. */
export type DensityField = (x: number, y: number) => number

/**
 * A CLEARED disc — ground that was cut, which is why nothing grows in it.
 *
 * The shape is unchanged from the keep-out disc it used to be and the geometry
 * is the same geometry; what changed on 2026-07-27 is what it MEANS. It was an
 * exclusion ("do not plant on the village"); it is now the record of an axe
 * ("this ground was felled, which is why it is open"). ./clearing owns the
 * quantity; this type is the shape the ring and the planting predicate already
 * speak, kept so those two did not have to be rewritten to say the same thing.
 */
export interface District {
  at: Point
  r: number
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
  /**
   * The DRAWN size of each kind, so the chosen sprite is re-tested.
   *
   * THE SAMPLING SIZE IS NOT A CONSERVATIVE SIZE — ring.ts paid for this and
   * the lesson is general. `size` above is the pool's LARGEST sprite, which is
   * right for a containment question ("nothing lands in a gap that only fitted
   * a sapling") and WRONG for both rejection rules: `footprintOnLane` is a
   * sparse 4x5 probe grid whose points scale with the footprint, so a bigger
   * diamond does not probe a superset of a smaller one's; and `groundTaken`
   * divides the shared area by min(area), so shrinking the candidate pushes the
   * SAME overlap across the threshold. Measured 2026-07-27 on the felling
   * record: sampled as a 60x47 log and drawn as a 47x45 stump, an item settled
   * inside the great house's ground diamond and the house's own arm caught it.
   *
   * With this set, an item whose CHOSEN sprite fails either rule is dropped.
   * The kind and flip are still drawn in the same order for every point, so
   * turning it on removes items without reshuffling the rest.
   */
  sizeOf?: (kind: string) => Footprint
  /**
   * A SECOND book, held to a tighter bar than `occupied` — the built ground.
   *
   * TWO TIERS, because two trees and a tree-and-a-house are not the same
   * question. ring.ts states the half of this that was already paid for: "two
   * buildings sharing a ground diamond are stacked and it is a defect; two trees
   * 40px apart with interpenetrating canopies are a FOREST", and holding a wood
   * to building-grade exclusivity thins it into a dotted line. The wood
   * therefore runs at a loose `frac` — and the moment it did, a 155px willow
   * settled 141px from the great house with 5.6% of its ground shared, on seed
   * `lantern`, and the house's own arm caught it.
   *
   * A clearing is what keeps a tree away from a building in the normal case;
   * this is what keeps the DIAGONAL case honest, where the squashed clearing
   * metric puts a point outside the disc while its ground diamond still reaches
   * the wall. Tested at both sampling time and on the chosen sprite.
   */
  strictOccupied?: readonly Occupant[]
  /** The tighter bar. Defaults to the structure rule's own 0.04. */
  strictFrac?: number
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
  // The occupancy book, indexed once per call. Same answers as scanning it —
  // see buildOccupancyIndex for why that is guaranteed rather than hoped.
  const book = buildOccupancyIndex(opts.occupied)
  const strictBook = opts.strictOccupied ? buildOccupancyIndex(opts.strictOccupied) : null
  const strictFrac = opts.strictFrac ?? 0.04

  const admissible = (x: number, y: number): boolean => {
    if (!(x > 40 && x < space.w - 40 && y > 40 && y < space.h - 40)) return false
    if (!opts.onLand(x, y) || !opts.pick(x, y)) return false
    const p = { x, y }
    // keep-out at SAMPLING time — never sample badly and hope a nudge rescues it
    if (book.taken(p, opts.size, frac)) return false
    if (strictBook && strictBook.taken(p, opts.size, strictFrac)) return false
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

  const items = out.map((p) => ({
    kind: opts.kinds[Math.min(opts.kinds.length - 1, Math.floor(rng() * opts.kinds.length))],
    at: p,
    flip: rng() < 0.5,
  }))
  const sizeOf = opts.sizeOf
  if (!sizeOf) return items
  return items.filter((it) => {
    const s = sizeOf(it.kind)
    if (strictBook && strictBook.taken(it.at, s, strictFrac)) return false
    return !book.taken(it.at, s, frac) && !footprintOnLane(it.at, s, opts.lanes, 0)
  })
}
