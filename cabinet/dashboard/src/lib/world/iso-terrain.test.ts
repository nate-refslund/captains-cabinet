/**
 * The procedural ground, held to the properties that make it the reference's
 * ground rather than a noise field with the right colours.
 *
 * KNOWN GAP, stated rather than hidden: the ramps here are a hand-copy of
 * designs/world-mockup-v2/terrain.py's, and there is no machine link between
 * the two — that file lives outside this repo, so a test reading it would pass
 * on one machine and fail everywhere else, which is a disabled sensor wearing a
 * green badge. What IS enforced below is the SHAPE of a ramp (monotone in
 * luminance, muted, hue-continuous), which catches a stop replaced by something
 * off-brief. A real link needs the pack's generator to ship the ramps, and that
 * belongs with the pack, not here.
 */
import { describe, expect, it } from 'vitest'
import {
  cobbleCell,
  COBBLE_CELL,
  FURROW_ANGLE,
  groundField,
  RAMPS,
  SEA_TILE_PX,
  seaFieldOptions,
  seaTile,
  terrainField,
} from './iso-terrain'

function rgb(c: number): [number, number, number] {
  return [(c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff]
}
function luma(c: number): number {
  const [r, g, b] = rgb(c)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function saturation(c: number): number {
  const [r, g, b] = rgb(c)
  const mx = Math.max(r, g, b)
  const mn = Math.min(r, g, b)
  return mx === 0 ? 0 : (mx - mn) / mx
}
function hueDeg(c: number): number {
  const [r, g, b] = rgb(c).map((v) => v / 255)
  const mx = Math.max(r, g, b)
  const mn = Math.min(r, g, b)
  const d = mx - mn
  if (d === 0) return 0
  let h: number
  if (mx === r) h = ((g - b) / d) % 6
  else if (mx === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return ((h * 60) % 360 + 360) % 360
}
function hueGap(a: number, b: number): number {
  const d = Math.abs(hueDeg(a) - hueDeg(b))
  return Math.min(d, 360 - d)
}

/** The colour of one block in a field buffer. */
function at(buf: ReturnType<typeof terrainField>, i: number, j: number): number {
  const p = (j * buf.w + i) * 4
  return (buf.rgba[p] << 16) | (buf.rgba[p + 1] << 8) | buf.rgba[p + 2]
}

describe('iso-terrain — the ground the reference computes', () => {
  it('every ramp is a SHADE FAMILY: monotone, muted, hue-continuous', () => {
    for (const [name, ramp] of Object.entries(RAMPS)) {
      expect(ramp.length, `${name} stops`).toBeGreaterThanOrEqual(3)
      for (let i = 1; i < ramp.length; i++) {
        expect(luma(ramp[i]), `${name} stop ${i} lighter than ${i - 1}`).toBeGreaterThan(
          luma(ramp[i - 1])
        )
        expect(hueGap(ramp[i], ramp[i - 1]), `${name} hue step ${i}`).toBeLessThan(30)
      }
      for (const c of ramp) {
        // The brief's palette is corpus-fitted and muted; a pure primary is a
        // hue no corpus ever fitted, and is what a careless edit looks like.
        expect(saturation(c), `${name} #${c.toString(16)} saturation`).toBeLessThan(0.62)
      }
    }
  })

  it('the ordered dither actually stipples — a half-step lands on BOTH stops', () => {
    // contrast 0 pins the noise out entirely, so v is a constant; the bias puts
    // it exactly half a ramp step above a stop. WITH the Bayer comparison half
    // the blocks in a 4x4 advance and the field carries two colours; without
    // it, every block takes the same stop and the ground bands.
    const k = RAMPS.grass.length
    const buf = terrainField(64, 64, {
      ramp: RAMPS.grass,
      seed: 1,
      contrast: 0,
      bias: 0.5 / (k - 1),
      block: 2,
    })
    const seen = new Set<number>()
    for (let j = 0; j < 4; j++) for (let i = 0; i < 4; i++) seen.add(at(buf, i, j))
    expect(seen.size).toBe(2)
    expect([...seen].sort((a, b) => a - b)).toEqual(
      [RAMPS.grass[2], RAMPS.grass[3]].sort((a, b) => a - b)
    )
  })

  it('a field is WORLD-ANCHORED: a sub-patch matches the whole where they overlap', () => {
    const opts = { ramp: RAMPS.grass, seed: 3, scale: 0.0045, octaves: 4, block: 2 } as const
    const whole = terrainField(256, 128, { ...opts, ox: 1000, oy: 2000 })
    const patch = terrainField(128, 64, { ...opts, ox: 1000 + 64, oy: 2000 + 32 })
    for (let j = 0; j < 32; j++) {
      for (let i = 0; i < 64; i++) {
        expect(at(patch, i, j), `patch ${i},${j}`).toBe(at(whole, i + 32, j + 16))
      }
    }
  })

  it('the same inputs give byte-identical ground, forever', () => {
    const a = groundField('grass', 96, 96, 11, 500, 500)
    const b = groundField('grass', 96, 96, 11, 500, 500)
    expect(Array.from(a.rgba)).toEqual(Array.from(b.rgba))
    const other = groundField('grass', 96, 96, 12, 500, 500)
    expect(Array.from(other.rgba)).not.toEqual(Array.from(a.rgba))
  })

  it('the open sea TILES — the column past the patch repeats column zero', () => {
    // The sea repeats in screen space, so a non-periodic field draws a grid
    // across the water at every patch edge. This walks two extra blocks past
    // the patch width and requires them to be the patch's own first two.
    const tile = seaTile(5)
    // …built from the SHIPPED options, not a hand-copied twin: a test that
    // re-declares `period` proves only that the test is periodic.
    const over = terrainField(SEA_TILE_PX + 8, 32, seaFieldOptions(5))
    const cols = SEA_TILE_PX / 2
    for (let j = 0; j < 16; j++) {
      for (let d = 0; d < 4; d++) {
        expect(at(over, cols + d, j), `wrap col ${d} row ${j}`).toBe(at(over, d, j))
      }
    }
    expect(tile.w).toBe(cols)
  })

  it('a flagstone is a RHOMBUS twice as wide as it is tall — the 2:1 ground', () => {
    // Measured as a SHAPE rather than by restating the formula: take the cell
    // under a point, sweep a window, and bound the pixels that belong to it.
    // On the isometric lattice that bounding box is 2:1; an axis-aligned
    // lattice gives a square, which is exactly the mutation this must catch.
    const px = 617
    const py = 431
    const home = cobbleCell(px, py)
    let x0 = Infinity
    let x1 = -Infinity
    let y0 = Infinity
    let y1 = -Infinity
    for (let y = py - 90; y <= py + 90; y++) {
      for (let x = px - 90; x <= px + 90; x++) {
        const c = cobbleCell(x, y)
        if (c.cu !== home.cu || c.cv !== home.cv) continue
        x0 = Math.min(x0, x)
        x1 = Math.max(x1, x)
        y0 = Math.min(y0, y)
        y1 = Math.max(y1, y)
      }
    }
    const w = x1 - x0
    const h = y1 - y0
    expect(w).toBeGreaterThan(10)
    expect(w / h).toBeGreaterThan(1.85)
    expect(w / h).toBeLessThan(2.15)
    // …and the paving the renderer bakes really uses that lattice: two points
    // one cell apart along the u axis carry different stone tones.
    const buf = groundField('cobble', 240, 240, 9, 0, 0)
    let differs = 0
    for (let j = 6; j < 54; j++) {
      if (at(buf, 20, j) !== at(buf, 20 + 30, j + 15)) differs++
    }
    expect(differs).toBeGreaterThan(0)
  })

  it('the cell size and furrow angle are the ISO axis, not arbitrary', () => {
    expect(COBBLE_CELL).toBe(30)
    // 26.5 degrees is atan(0.5) to within a tenth of a degree: the furrows run
    // along the ground axis of a 2:1 projection. A furrow off that axis reads
    // as a ploughed field someone rotated.
    expect(Math.tan(FURROW_ANGLE)).toBeCloseTo(0.5, 2)
  })

  it('the degenerate end: a one-block field, and a ramp too short to quantise', () => {
    const tiny = terrainField(1, 1, { ramp: RAMPS.sand, seed: 2, block: 2 })
    expect(tiny.w).toBe(1)
    expect(tiny.h).toBe(1)
    expect(tiny.rgba.length).toBe(4)
    expect(tiny.rgba[3]).toBe(255)
    expect(() => terrainField(8, 8, { ramp: [0x112233], seed: 1 })).toThrow(/two stops/)
  })

  it('every ground class produces opaque pixels drawn only from its own ramp', () => {
    const classes = ['grass', 'grass_dark', 'dirt', 'dirt_worn', 'gravel', 'sand', 'sea', 'ploughed', 'crop'] as const
    const ramps: Record<string, readonly number[]> = {
      grass: RAMPS.grass,
      grass_dark: RAMPS.grassDark,
      dirt: RAMPS.dirt,
      dirt_worn: RAMPS.dirtWorn,
      gravel: RAMPS.gravel,
      sand: RAMPS.sand,
      sea: RAMPS.sea,
      ploughed: RAMPS.ploughed,
      crop: RAMPS.crop,
    }
    for (const cls of classes) {
      const buf = groundField(cls, 64, 64, 4, 300, 300)
      const legal = new Set(ramps[cls])
      for (let j = 0; j < buf.h; j++) {
        for (let i = 0; i < buf.w; i++) {
          expect(legal.has(at(buf, i, j)), `${cls} ${i},${j}`).toBe(true)
          expect(buf.rgba[(j * buf.w + i) * 4 + 3]).toBe(255)
        }
      }
    }
  })
})
