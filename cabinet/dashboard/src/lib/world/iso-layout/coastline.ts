/**
 * COASTLINE — the island field: a real, irregular shore with a carved cove.
 *
 * PORTED FROM compose.py lines 48-121 (the MODEL, not the Pillow calls):
 *
 *   nx,ny = (px-ICX)/HWr, (py-ICY)/VHr          normalised ellipse coords
 *   d     = sqrt(nx*nx*1.02 + (ny*1.05)^2)      slightly non-circular falloff
 *   e     = 0.60*fbm(nx*1.7+5, ny*1.7+5) + (0.97 - 1.16*d*d)
 *   cove  : cd = |p-COVE| with y*1.45, / COVE.r ; if cd<1 then e -= (1-cd)*1.9
 *   land  = e >  0.05        beach = e > -0.028
 *   then BLUR(3) + THRESHOLD (115 / 95) on both masks
 *
 * The blur+threshold is not decoration: thresholding a noisy field directly
 * leaves single-cell speckle and hairline isthmuses that later stages then try
 * to build on. Blurring the binary mask and re-thresholding is a morphological
 * open/close — it rounds the shore and deletes anything thinner than the blur.
 * It is reproduced here with a separable box blur (two passes ~ Gaussian),
 * because that is the part of the Pillow call that carries meaning.
 *
 * WHAT DIVERGES FROM THE REFERENCE, deliberately: the noise BASIS. compose.py
 * uses OpenSimplex; this uses a hashed value-noise lattice with a quintic fade.
 * Porting OpenSimplex byte-for-byte would pin the mockup's exact island and
 * nothing else — the Captain's ruling is about the KIND of coastline (real,
 * carved, irregular), and the determinism law is about the same seed always
 * giving the same island. Both hold. Anything that depended on the mockup's
 * literal pixels would be depending on an artefact of a Python library.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { fnv1a } from '../hash'
import { hypot, LAYOUT_SPACE, type LayoutSpace, type Point, rasterDims } from './space'

// ── noise ──────────────────────────────────────────────────────────────────

/**
 * FNV-1a over the four bytes of each lattice coordinate — the integer-domain
 * twin of hash.ts's fnv1a(string), same constants and same avalanche.
 *
 * WHY NOT fnv1a() DIRECTLY: the island field is ~1M samples x 5 octaves x 4
 * lattice corners, so a string per hash would dominate everything else in the
 * module. The SEED still goes through hash.ts's fnv1a (see coastlineSeed), so
 * seeded variation enters through the sanctioned door and only the inner loop
 * is specialised.
 */
function latticeHash(ix: number, iy: number, seed: number): number {
  let h = (0x811c9dc5 ^ seed) >>> 0
  // Unrolled over the eight bytes of (ix, iy): this is the hottest line in the
  // library and an array literal here allocates once per lattice corner.
  h = Math.imul(h ^ (ix & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((ix >>> 8) & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((ix >>> 16) & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((ix >>> 24) & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ (iy & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((iy >>> 8) & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((iy >>> 16) & 0xff), 0x01000193) >>> 0
  h = Math.imul(h ^ ((iy >>> 24) & 0xff), 0x01000193) >>> 0
  return h >>> 0
}

/** Lattice value in [-1,1). */
function latticeValue(ix: number, iy: number, seed: number): number {
  return latticeHash(ix, iy, seed) / 2147483648 - 1
}

/** Quintic fade — C2 continuous, so the shore has no lattice creases. */
function fade(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10)
}

/** Value noise in [-1,1]. */
export function valueNoise2(x: number, y: number, seed: number): number {
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const fx = fade(x - x0)
  const fy = fade(y - y0)
  const v00 = latticeValue(x0, y0, seed)
  const v10 = latticeValue(x0 + 1, y0, seed)
  const v01 = latticeValue(x0, y0 + 1, seed)
  const v11 = latticeValue(x0 + 1, y0 + 1, seed)
  const a = v00 + (v10 - v00) * fx
  const b = v01 + (v11 - v01) * fx
  return a + (b - a) * fy
}

/**
 * compose.py's fbm(), verbatim in structure: octaves of halving amplitude and
 * doubling frequency, normalised by the amplitude sum so the result stays in
 * the same range as one octave.
 */
export function fbm(x: number, y: number, seed: number, octaves = 5): number {
  let v = 0
  let a = 0
  let amp = 1
  let f = 1
  for (let i = 0; i < octaves; i++) {
    v += amp * valueNoise2(x * f, y * f, seed)
    a += amp
    amp *= 0.5
    f *= 2
  }
  return v / a
}

// ── the island ─────────────────────────────────────────────────────────────

/** compose.py:60 — the island's half-width and half-height. */
export const ISLAND_RADII = { hw: 962, vh: 784 } as const

/** compose.py:59 — the concave harbour bite carved up into the south shore. */
export const COVE = { x: 1200, y: 1430, r: 300 } as const

export interface CoastlineOptions {
  /** Sampling step in layout px. compose.py's STEP is 2. */
  step?: number
  /** Island half-extents; defaults to the reference ellipse. */
  radii?: { hw: number; vh: number }
  /** The carved cove; pass null for an island with no harbour bite. */
  cove?: { x: number; y: number; r: number } | null
}

/** What a point sits on. Mirrors the reference's land / beach / sea masks. */
export type Ground = 'sea' | 'beach' | 'land'

export interface Coastline {
  readonly space: LayoutSpace
  readonly seed: number
  /**
   * The cove this island was actually carved with, or null when it was built
   * without one. EMITTED rather than re-derived by the caller: the harbour and
   * the lighthouse are both sited against the cove, and a second literal COVE
   * in those stages would keep claiming a harbour bite after a caller passed
   * `coastline: { cove: null }` — a wharf pinned to water that is not there.
   */
  readonly cove: { x: number; y: number; r: number } | null
  /** Raster step in layout px, and the raster's own dimensions. */
  readonly step: number
  readonly mw: number
  readonly mh: number
  /** 1 = land. Row-major, mw*mh, the renderer's own coastline source. */
  readonly land: Uint8Array
  /** 1 = beach band (the sand ring OUTSIDE the land mask). */
  readonly beach: Uint8Array
  /** compose.py onland(): is there ground under this layout-space point? */
  landAt(x: number, y: number): boolean
  beachAt(x: number, y: number): boolean
  groundAt(x: number, y: number): Ground
  /**
   * compose.py land_edge(): distance from the island centre (or a given
   * origin) to the waterline along `angle`, walking outward. The 0.92 vertical
   * squash is the reference's, and it is what makes the radius comparable in
   * every direction on a 2:1 projection.
   */
  landEdge(angle: number, from?: Point): number
  /**
   * landEdge quantised to 0.02 rad and memoised — compose.py's `_edge_at`.
   * The density field asks this question once per scatter candidate and
   * landEdge walks the raster in 6px steps, so the exact form is the wrong
   * tool there. Fields use this; one-off geometry uses landEdge.
   */
  edgeAt(angle: number): number
  /** compose.py shore_y(): lowest land row in a column — the quay sits here. */
  shoreY(x: number, yFrom: number, yTo: number): number | null
  /**
   * The planting band just inside the waterline (compose.py shore_band):
   * e-118 < d < e-26 from the centre. Reeds and shore rocks live here.
   */
  inShoreBand(x: number, y: number): boolean
  /** Well inside the treeline (compose.py inner): d < landEdge(ang) - 190. */
  isInner(x: number, y: number): boolean
}

/** The numeric seed for a coastline — through hash.ts, as the ratchet requires. */
export function coastlineSeed(seed: string | number): number {
  return typeof seed === 'number' ? seed >>> 0 : fnv1a(seed)
}

/**
 * Separable box blur over a 0/255 mask, `passes` times. Box passes are the
 * standard cheap Gaussian; two are enough at this radius and are what the
 * shore actually needs (the mask is binary and the field beneath it is smooth,
 * so the blur's whole job is to delete speckle and round corners).
 */
function boxBlur(
  src: Uint8Array,
  mw: number,
  mh: number,
  radius: number,
  passes: number
): Uint8Array {
  const ci = (v: number, hi: number) => (v < 0 ? 0 : v > hi ? hi : v)
  let cur = src
  const span = radius * 2 + 1
  for (let p = 0; p < passes; p++) {
    const horiz = new Uint8Array(mw * mh)
    for (let y = 0; y < mh; y++) {
      const row = y * mw
      let sum = 0
      for (let x = -radius; x <= radius; x++) sum += cur[row + ci(x, mw - 1)]
      for (let x = 0; x < mw; x++) {
        horiz[row + x] = sum / span
        sum -= cur[row + ci(x - radius, mw - 1)]
        sum += cur[row + ci(x + radius + 1, mw - 1)]
      }
    }
    const vert = new Uint8Array(mw * mh)
    for (let x = 0; x < mw; x++) {
      let sum = 0
      for (let y = -radius; y <= radius; y++) sum += horiz[ci(y, mh - 1) * mw + x]
      for (let y = 0; y < mh; y++) {
        vert[y * mw + x] = sum / span
        sum -= horiz[ci(y - radius, mh - 1) * mw + x]
        sum += horiz[ci(y + radius + 1, mh - 1) * mw + x]
      }
    }
    cur = vert
  }
  return cur
}

/** Threshold a blurred mask back to 0/1, the reference's `.point(v>t)`. */
function threshold(src: Uint8Array, t: number): Uint8Array {
  const out = new Uint8Array(src.length)
  for (let i = 0; i < src.length; i++) out[i] = src[i] > t ? 1 : 0
  return out
}

/**
 * Build the island field for a seed. Same (space, seed, options) always give a
 * byte-identical raster — that determinism is what lets a lot's centre be a
 * FUNCTION of the coastline rather than an authored constant.
 */
export function buildCoastline(
  seedIn: string | number,
  space: LayoutSpace = LAYOUT_SPACE,
  opts: CoastlineOptions = {}
): Coastline {
  const seed = coastlineSeed(seedIn)
  const { step, mw, mh } = rasterDims(space, opts.step ?? 2)
  const radii = opts.radii ?? ISLAND_RADII
  const cove = opts.cove === undefined ? COVE : opts.cove

  const rawLand = new Uint8Array(mw * mh)
  const rawBeach = new Uint8Array(mw * mh)
  for (let my = 0; my < mh; my++) {
    const py = my * step
    for (let mx = 0; mx < mw; mx++) {
      const px = mx * step
      const nx = (px - space.cx) / radii.hw
      const ny = (py - space.cy) / radii.vh
      const d = Math.sqrt(nx * nx * 1.02 + (ny * 1.05) ** 2)
      let e = 0.6 * fbm(nx * 1.7 + 5, ny * 1.7 + 5, seed) + (0.97 - 1.16 * d * d)
      if (cove) {
        const cx = px - cove.x
        const cy = py - cove.y
        const cd = Math.sqrt(cx * cx + cy * cy * 1.45) / cove.r
        if (cd < 1) e -= (1 - cd) * 1.9
      }
      const i = my * mw + mx
      if (e > 0.05) rawLand[i] = 255
      else if (e > -0.028) rawBeach[i] = 255
    }
  }

  // compose.py blurs by 3 PIXELS; the raster is sampled every `step` px, so the
  // radius converts. Below one cell the blur cannot do its job, hence the floor.
  const r = Math.max(1, Math.round(3 / step))
  const land = threshold(boxBlur(rawLand, mw, mh, r, 2), 115)
  const beach = threshold(boxBlur(rawBeach, mw, mh, r, 2), 95)

  const at = (mask: Uint8Array, x: number, y: number): boolean => {
    if (!(x >= 0 && x < space.w && y >= 0 && y < space.h)) return false
    const mx = Math.min(mw - 1, Math.floor(x / step))
    const my = Math.min(mh - 1, Math.floor(y / step))
    return mask[my * mw + mx] > 0
  }

  const landAt = (x: number, y: number) => at(land, x, y)

  const landEdge = (angle: number, from?: Point): number => {
    const ox = from ? from.x : space.cx
    const oy = from ? from.y : space.cy
    // compose.py walks out in 6px increments from r=60 and stops at 1300.
    let rr = 60
    while (rr < 1300) {
      if (!landAt(ox + Math.cos(angle) * rr, oy + Math.sin(angle) * rr * 0.92)) return rr
      rr += 6
    }
    return rr
  }

  // land_edge() is called per scatter candidate; the reference caches it on a
  // 0.02-radian key and so do we. The cache is write-once per coastline and
  // never observable in the output, so the layout stays a pure function.
  const edgeCache = new Map<number, number>()
  const edgeAtAngle = (angle: number): number => {
    const key = Math.round(angle / 0.02)
    const hit = edgeCache.get(key)
    if (hit !== undefined) return hit
    const v = landEdge(key * 0.02)
    edgeCache.set(key, v)
    return v
  }

  const radialFrom = (x: number, y: number) => ({
    d: hypot(x - space.cx, (y - space.cy) / 0.92),
    ang: Math.atan2((y - space.cy) / 0.92, x - space.cx),
  })

  return {
    space,
    seed,
    cove,
    step,
    mw,
    mh,
    land,
    beach,
    landAt,
    beachAt: (x, y) => at(beach, x, y),
    groundAt: (x, y) => (landAt(x, y) ? 'land' : at(beach, x, y) ? 'beach' : 'sea'),
    landEdge,
    edgeAt: edgeAtAngle,
    shoreY(x, yFrom, yTo) {
      let last: number | null = null
      for (let y = Math.floor(yFrom); y < Math.floor(yTo); y++) if (landAt(x, y)) last = y
      return last
    },
    inShoreBand(x, y) {
      const { d, ang } = radialFrom(x, y)
      const e = edgeAtAngle(ang)
      return e - 118 < d && d < e - 26
    },
    isInner(x, y) {
      const { d, ang } = radialFrom(x, y)
      return d < edgeAtAngle(ang) - 190
    },
  }
}
