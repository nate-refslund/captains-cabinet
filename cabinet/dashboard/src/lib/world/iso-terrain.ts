/**
 * ISO-TERRAIN — the procedural ground, ported from designs/world-mockup-v2/terrain.py.
 *
 * WHY IT IS COMPUTED AND NOT TILED. The approved stills' ground is generated:
 * fractal noise quantised onto a small palette ramp with a 4x4 ordered dither,
 * so it reads as pixel art at the same grain as the 1:1 sprites instead of as a
 * smooth gradient. A repeating texture cannot express that — the flagstone
 * paving's cells sit on the ISOMETRIC lattice (u = (x/2 + y)/CELL), which is a
 * function of world position, and the furrows in a ploughed plot run along the
 * iso axis at 26.5 degrees for the same reason. terrain.py's own header records
 * why the art is generated at all: the generated terrain tiles came back as
 * featureless colour washes.
 *
 * WORLD-ANCHORED. Every field takes an origin (ox, oy) in layout space and
 * evaluates its noise and its lattice at (ox+x, oy+y), so two patches that abut
 * are continuous: the plaza's stones line up with the plaza's neighbours, and
 * regenerating a field at a different bounding box gives the same pixels where
 * they overlap. A field evaluated in its own local space would move every time
 * its bounding box moved, which is how ground ends up shimmering under a camera.
 *
 * THE NOISE BASIS DIFFERS FROM THE REFERENCE AND THAT IS STATED, NOT HIDDEN.
 * terrain.py uses OpenSimplex; this is seeded VALUE noise over hash.ts's mix32
 * lattice hash, because the world tree's determinism ratchet forbids
 * Math.random and no simplex implementation ships with the app. Both are smooth,
 * band-limited fractal fields at the same octave structure and scale, so the
 * ground reads the same; the exact pixels are NOT identical to the Python stills and no test
 * here claims they are.
 *
 * PURE: no clock, no unseeded randomness, no DOM. Returns pixel BUFFERS; the
 * component turns them into a texture. That keeps it testable without a browser.
 */
import { mix32 } from './hash'

/** 4x4 Bayer matrix — terrain.py:22, verbatim. The dither that keeps banding
 * from reading as a gradient. */
const BAYER: readonly (readonly number[])[] = [
  [0, 8, 2, 10],
  [12, 4, 14, 6],
  [3, 11, 1, 9],
  [15, 7, 13, 5],
]

/**
 * The palette ramps, dark -> light, exactly as terrain.py declares them.
 * These ARE the brief's ramps: the reference generates the ground here
 * precisely so the palette cannot drift, and a hue invented in this file would
 * be a hue no corpus fitted.
 */
export const RAMPS = {
  grass: [0x4e6b3c, 0x5e7a46, 0x6a8252, 0x7a945c, 0x8aa468],
  grassDark: [0x415c33, 0x4e6b3c, 0x5a7745, 0x67854e],
  dirt: [0x8a6a42, 0x9c7a4e, 0xad8a5c, 0xbc9a6c, 0xc9a87a],
  sand: [0xcdb98c, 0xd8c69c, 0xe2d2ac, 0xebdcbb],
  sea: [0x3e6e6b, 0x48807c, 0x54918c, 0x61a099, 0x6faea6],
  cobbleBase: [0x9a9084, 0xa79c8f, 0xb4a99a],
  cobbleCells: [0x8b8175, 0x998f80, 0xa79c8c, 0xb4a997, 0xc1b6a3, 0xcec3af],
  ploughed: [0x5c3d28, 0x6b4a30, 0x7a5335, 0x8a5f3d, 0x996b45],
  crop: [0x6a8252, 0x79924f, 0x8aa255, 0x9db25e, 0xb4c06a],
} as const

/** terrain.py:119 — the furrow angle, on the isometric ground axis. */
export const FURROW_ANGLE = (26.5 * Math.PI) / 180
/** terrain.py:98 — the flagstone cell size, in layout px. */
export const COBBLE_CELL = 30

export interface FieldOptions {
  /** Palette ramp, dark -> light. */
  ramp: readonly number[]
  /** Seed for the noise basis. */
  seed: number
  /** Noise frequency, in 1/px (terrain.py's `scale`). */
  scale?: number
  octaves?: number
  contrast?: number
  bias?: number
  /** Pixel block size — the field is computed once per block. */
  block?: number
  /** [period, depth, angle] — the ploughed/crop furrows. */
  furrow?: { period: number; depth: number; angle: number }
  /** [period, depth] — the sea's swell. */
  ripple?: { period: number; depth: number }
  /** World origin of this patch, so abutting patches are continuous. */
  ox?: number
  oy?: number
  /**
   * Lattice period at the base frequency. Non-zero makes the field TILEABLE
   * over `period / scale` pixels — required for the open sea, which repeats
   * in screen space and would otherwise draw a grid across the water.
   */
  period?: number
}

/** A computed field: RGBA at block resolution, to be drawn scaled by `block`. */
export interface TerrainBuffer {
  /** Width/height in BLOCKS (not layout px). */
  w: number
  h: number
  block: number
  /** RGBA, row-major. Pinned to a plain ArrayBuffer so it can be handed
   * straight to ImageData without a copy. */
  rgba: Uint8ClampedArray<ArrayBuffer>
}

/** Positive modulo — a lattice index may go negative west of the origin. */
function wrap(v: number, m: number): number {
  return m <= 0 ? v : ((v % m) + m) % m
}

/**
 * Seeded 2D value noise in [-1,1] — the ratchet-legal noise basis.
 *
 * `period` wraps the LATTICE, which is what makes a field tileable: the open
 * sea is a screen-space repeat and a non-periodic field would draw a visible
 * grid across the water every patch width.
 */
function valueNoise(seed: number, x: number, y: number, period = 0): number {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const xf = x - xi
  const yf = y - yi
  // smoothstep (the same C1 fade a gradient noise uses)
  const u = xf * xf * (3 - 2 * xf)
  const v = yf * yf * (3 - 2 * yf)
  const x0 = wrap(xi, period)
  const y0 = wrap(yi, period)
  const x1 = wrap(xi + 1, period)
  const y1 = wrap(yi + 1, period)
  const a = mix32(seed, x0, y0) / 2147483647.5 - 1
  const b = mix32(seed, x1, y0) / 2147483647.5 - 1
  const c = mix32(seed, x0, y1) / 2147483647.5 - 1
  const d = mix32(seed, x1, y1) / 2147483647.5 - 1
  const top = a + (b - a) * u
  const bot = c + (d - c) * u
  return top + (bot - top) * v
}

/** terrain.py:25 _fbm — normalised to 0..1. Every octave wraps on the SAME
 * spatial period, which is why the lattice period doubles with the frequency. */
function fbm(seed: number, x: number, y: number, octaves: number, period = 0): number {
  let v = 0
  let a = 0
  let amp = 1
  let f = 1
  for (let o = 0; o < octaves; o++) {
    v += amp * valueNoise(seed + o * 7919, x * f, y * f, period * f)
    a += amp
    amp *= 0.5
    f *= 2
  }
  return (v / a) * 0.5 + 0.5
}

/**
 * terrain.py:32 field() — a quantised, dithered colour field.
 *
 * The dither comparison is the reference's: the ramp index is advanced by one
 * when the fractional part exceeds the Bayer threshold, which is what turns
 * five flat bands into a stippled gradient.
 */
export function terrainField(w: number, h: number, o: FieldOptions): TerrainBuffer {
  const block = Math.max(1, Math.trunc(o.block ?? 2))
  const scale = o.scale ?? 0.006
  const octaves = Math.max(1, Math.trunc(o.octaves ?? 4))
  const contrast = o.contrast ?? 1
  const bias = o.bias ?? 0
  const ox = o.ox ?? 0
  const oy = o.oy ?? 0
  const ramp = o.ramp
  if (ramp.length < 2) throw new Error('iso-terrain: a ramp needs at least two stops')
  const k = ramp.length
  const bw = Math.max(1, Math.ceil(w / block))
  const bh = Math.max(1, Math.ceil(h / block))
  const rgba = new Uint8ClampedArray(new ArrayBuffer(bw * bh * 4))
  const fa = o.furrow ? Math.cos(o.furrow.angle) : 0
  const fb = o.furrow ? Math.sin(o.furrow.angle) : 0
  for (let j = 0; j < bh; j++) {
    const by = oy + j * block
    for (let i = 0; i < bw; i++) {
      const bx = ox + i * block
      let v = fbm(o.seed, bx * scale, by * scale, octaves, o.period ?? 0)
      v = 0.5 + (v - 0.5) * contrast + bias
      if (o.furrow) {
        const s = (bx * fa + by * fb) / o.furrow.period
        v += Math.sin(s * Math.PI * 2) * o.furrow.depth
      }
      if (o.ripple) {
        v +=
          Math.sin(by / o.ripple.period + Math.sin(bx / (o.ripple.period * 2.4)) * 1.3) *
          o.ripple.depth
      }
      v = Math.min(0.999, Math.max(0, v))
      // Bayer is indexed by BLOCK, exactly as terrain.py's (by//block) % 4.
      const d = (BAYER[j % 4][i % 4] + 0.5) / 16
      const idx = v * (k - 1)
      const lo = Math.trunc(idx)
      const col = ramp[Math.min(k - 1, lo + (idx - lo > d ? 1 : 0))]
      const p = (j * bw + i) * 4
      rgba[p] = (col >> 16) & 0xff
      rgba[p + 1] = (col >> 8) & 0xff
      rgba[p + 2] = col & 0xff
      rgba[p + 3] = 255
    }
  }
  return { w: bw, h: bh, block, rgba }
}

/**
 * Which flagstone a layout-space point falls on, and where inside it.
 *
 * THE LATTICE, exported because it is the shape the paving actually has and a
 * shape is testable: u and v are the two ground axes of a 2:1 projection, so
 * one cell is a rhombus twice as wide on screen as it is tall. Nothing else in
 * the ground has a directional grid, and it is the reason the paving cannot be
 * a repeating texture.
 */
export function cobbleCell(
  x: number,
  y: number
): { cu: number; cv: number; fu: number; fv: number } {
  const u = (x * 0.5 + y) / COBBLE_CELL
  const v = (x * 0.5 - y) / COBBLE_CELL
  const cu = Math.floor(u)
  const cv = Math.floor(v)
  return { cu, cv, fu: u - cu, fv: v - cv }
}

/**
 * terrain.py:88 cobble() — flagstone paving on the ISOMETRIC lattice.
 *
 * Each iso cell gets its own stone tone and the joint is only a shade below the
 * cell, because a hard mortar grid at full contrast reads as chain-link. The
 * lattice is u = (x/2 + y)/CELL, v = (x/2 - y)/CELL: the two ground axes of a
 * 2:1 projection, which is why this is the one ground class a tiled texture
 * cannot express.
 */
export function cobbleField(w: number, h: number, seed: number, ox = 0, oy = 0): TerrainBuffer {
  const buf = terrainField(w, h, {
    ramp: RAMPS.cobbleBase,
    seed,
    scale: 0.03,
    octaves: 3,
    contrast: 0.7,
    block: 2,
    ox,
    oy,
  })
  const cells = RAMPS.cobbleCells
  const { block, w: bw, h: bh, rgba } = buf
  for (let j = 0; j < bh; j++) {
    const y = oy + j * block
    for (let i = 0; i < bw; i++) {
      const x = ox + i * block
      const { cu, cv, fu, fv } = cobbleCell(x, y)
      const col = cells[mix32(seed ^ 0x5bf03635, cu, cv) % cells.length]
      const joint = Math.min(fu, 1 - fu, fv, 1 - fv) < 0.055
      const kk = joint ? 0.72 : 0.3
      const dim = joint ? 0.8 : 1
      const p = (j * bw + i) * 4
      rgba[p] = rgba[p] * (1 - kk) + ((col >> 16) & 0xff) * kk * dim
      rgba[p + 1] = rgba[p + 1] * (1 - kk) + ((col >> 8) & 0xff) * kk * dim
      rgba[p + 2] = rgba[p + 2] * (1 - kk) + (col & 0xff) * kk * dim
    }
  }
  return buf
}

/** The ground classes the layout's paint regions and coastline ask for. */
export type GroundClass =
  | 'grass'
  | 'grass_dark'
  | 'dirt'
  | 'sand'
  | 'sea'
  | 'cobble'
  | 'ploughed'
  | 'crop'

/**
 * One field per ground class, at the reference's own parameters
 * (terrain.py:62-125). `block` is a caller lever rather than a constant: the
 * island-wide grass costs a fbm evaluation per block, so a coarser block is the
 * one honest way to trade grain for bake time — and it is honest because the
 * dither is indexed by block, so a coarser block is a COARSER pixel-art grain,
 * not a blur.
 */
export function groundField(
  cls: GroundClass,
  w: number,
  h: number,
  seed: number,
  ox = 0,
  oy = 0,
  block = 2
): TerrainBuffer {
  switch (cls) {
    case 'grass':
      return terrainField(w, h, { ramp: RAMPS.grass, seed: seed + 3, scale: 0.0045, octaves: 5, contrast: 1.15, block, ox, oy })
    case 'grass_dark':
      return terrainField(w, h, { ramp: RAMPS.grassDark, seed: seed + 8, scale: 0.0075, octaves: 4, contrast: 1.2, block, ox, oy })
    case 'dirt':
      return terrainField(w, h, { ramp: RAMPS.dirt, seed: seed + 5, scale: 0.012, octaves: 4, contrast: 1.1, block, ox, oy })
    case 'sand':
      return terrainField(w, h, { ramp: RAMPS.sand, seed: seed + 6, scale: 0.01, octaves: 4, contrast: 0.95, block, ox, oy })
    case 'sea':
      return terrainField(w, h, { ramp: RAMPS.sea, seed: seed + 7, scale: 0.0035, octaves: 3, contrast: 0.9, ripple: { period: 26, depth: 0.09 }, block, ox, oy })
    case 'cobble':
      return cobbleField(w, h, seed + 9, ox, oy)
    case 'ploughed':
      return terrainField(w, h, { ramp: RAMPS.ploughed, seed: seed + 11, scale: 0.012, octaves: 3, contrast: 0.85, furrow: { period: 17, depth: 0.24, angle: FURROW_ANGLE }, block, ox, oy })
    case 'crop':
      return terrainField(w, h, { ramp: RAMPS.crop, seed: seed + 12, scale: 0.011, octaves: 3, contrast: 0.8, furrow: { period: 17, depth: 0.26, angle: FURROW_ANGLE }, block, ox, oy })
  }
}

/**
 * The OPEN SEA, as a seamless repeating patch.
 *
 * The world beyond the island is unbounded — there is never a foreign void
 * past the canvas — so the sea is a screen-space repeat rather than a field
 * over a finite rect. That makes seamlessness a requirement, not a nicety: a
 * non-periodic field draws a visible grid across the water at every patch
 * edge. The frequency is chosen so the patch holds a WHOLE number of noise
 * cells (SEA_TILE_PX * scale is an integer), which is what the lattice wrap
 * needs to line up, and it lands within a few percent of terrain.py's own
 * sea scale of 0.0035.
 *
 * The reference's swell (its `ripple` term) is deliberately dropped here: it
 * is a function of absolute y and does not repeat, so including it would put
 * the seam back. The swell reads at the shoreline, where the beach ring and
 * the coast do the work.
 */
export const SEA_TILE_PX = 1024
const SEA_CELLS = 4

/**
 * The sea field's exact options — EXPORTED so a test can build the patch's
 * neighbour from the SAME options rather than from a hand-copied twin. A
 * seamlessness test that re-declares `period` proves the test is periodic and
 * says nothing about the sea the world actually draws.
 */
export function seaFieldOptions(seed: number): FieldOptions {
  return {
    ramp: RAMPS.sea,
    seed: seed + 7,
    scale: SEA_CELLS / SEA_TILE_PX,
    octaves: 3,
    contrast: 0.9,
    block: 2,
    period: SEA_CELLS,
  }
}

export function seaTile(seed: number): TerrainBuffer {
  return terrainField(SEA_TILE_PX, SEA_TILE_PX, seaFieldOptions(seed))
}
