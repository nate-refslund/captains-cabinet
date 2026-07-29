/**
 * veil.test.ts — THE VEIL LUMINANCE LAW, and the wiring that makes it binding.
 *
 * WHAT THIS EXISTS TO CATCH. On 2026-07-29 the shipped dusk veil replaced 16%
 * of every screen pixel with 0xffc890 (relative luminance 208) and the shipped
 * dawn veil replaced 8% with 0xf2ecde (236). The brightest tone the open sea
 * has is 0x6faea6, luminance 160. Measured on live browser frames of /world at
 * five zooms, at a pinned dusk clock, the sea came back 15.5–15.6% apricot at
 * EVERY one of them (0.35 / 0.50 / 0.60 / 1.00) and grass 20.2%; the ocean read
 * as orange static. Nothing went red:
 *
 *   - the twelve world-capture invariants judge a Python re-draw of the
 *     LAYOUT (raster.py), which has no day bucket and no compositor, so no
 *     screen-space pass — veil, weather, killswitch wash — is inside their
 *     reach at any zoom;
 *   - PALETTE_FOREIGN_MASS asks whether each pixel is a corpus color and never
 *     whether it is a plausible NEIGHBOUR of the surface it landed on, so an
 *     "in-bin" apricot dropped onto teal water passes it perfectly.
 *
 * So the sensor has to be a rule about the hues themselves, and it has to read
 * the SHIPPED tables — `ambientVeil` and `RAMPS.sea` — never a copy of either.
 * The final arm greps the canvas, because a second veil table at the call site
 * would silently take these tests out of the loop, which is how the first one
 * survived: it was a `const VEIL` inside a 3000-line component.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ambientVeil, type DayBucket } from './lighting'
import { RAMPS } from './iso-terrain'
import { veilDots } from './terrain-pattern'

const BUCKETS: readonly DayBucket[] = ['dawn', 'day', 'dusk', 'night'] as const

/** ITU-R BT.709 relative luminance of a packed 0xRRGGBB. */
function luma(hex: number): number {
  return (
    0.2126 * ((hex >> 16) & 0xff) + 0.7152 * ((hex >> 8) & 0xff) + 0.0722 * (hex & 0xff)
  )
}

/** CIE Lab chroma — how COLOURFUL a hue is, independent of how light it is. */
function chroma(hex: number): number {
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  const r = lin(((hex >> 16) & 0xff) / 255)
  const g = lin(((hex >> 8) & 0xff) / 255)
  const b = lin((hex & 0xff) / 255)
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
  const fx = f((r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047)
  const fy = f(r * 0.2126 + g * 0.7152 + b * 0.0722)
  const fz = f((r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883)
  return Math.hypot(500 * (fx - fy), 200 * (fy - fz))
}

/** Both caps DERIVED from the shipped sea ramp — never typed-in numbers. */
const WATER_CEILING = Math.max(...RAMPS.sea.map(luma))
const WATER_CHROMA = Math.max(...RAMPS.sea.map(chroma))

const CANVAS = join(
  process.cwd(),
  'src',
  'components',
  'world',
  'engine-canvas.tsx'
)

describe('the veil luminance law', () => {
  it('the ceiling comes from the shipped sea ramp, and the ramp is real', () => {
    // Vacuity guard: an empty or stubbed ramp would make every arm below pass.
    expect(RAMPS.sea.length).toBeGreaterThanOrEqual(5)
    expect(WATER_CEILING).toBeGreaterThan(150)
    expect(WATER_CEILING).toBeLessThan(170)
    expect(WATER_CHROMA).toBeGreaterThan(15)
    expect(WATER_CHROMA).toBeLessThan(30)
  })

  it('every bucket resolves — the table is total, not partial', () => {
    // Without this, a bucket that fell out of the switch would return undefined
    // and every luminance arm would skip it while reporting green.
    const seen = BUCKETS.map((b) => ambientVeil(b))
    expect(seen).toHaveLength(4)
    expect(seen.filter((v) => v === null)).toHaveLength(1) // day, and only day
    expect(ambientVeil('day')).toBeNull()
  })

  for (const bucket of BUCKETS) {
    it(`${bucket}: no veil hue is brighter than open water`, () => {
      const veil = ambientVeil(bucket)
      if (veil === null) return
      expect(veil.colors.length).toBeGreaterThan(0)
      for (const hex of veil.colors) {
        expect(
          luma(hex),
          `${bucket} veil #${hex.toString(16)} is brighter than the brightest ` +
            `sea tone (${WATER_CEILING.toFixed(1)}) — a dot that bright cannot ` +
            'read as lit water, it reads as a speck ON the water'
        ).toBeLessThanOrEqual(WATER_CEILING)
      }
    })

    it(`${bucket}: no veil hue is more colourful than the water it shades`, () => {
      // Law 1 alone passed a set of in-bin warm browns (chroma 29-34) whose
      // grain was still plainly visible on open water at 1:1. Ambience is a
      // SHADING pass: a dot with more chroma than the ground competes with the
      // surface's own hue instead of shading it, and the eye reads that as
      // grain. The bound is the sea's own chroma, derived from the same ramp.
      const veil = ambientVeil(bucket)
      if (veil === null) return
      for (const hex of veil.colors) {
        expect(
          chroma(hex),
          `${bucket} veil #${hex.toString(16)} is more colourful than the water ` +
            `it shades (${WATER_CHROMA.toFixed(1)}) — it will read as grain, not light`
        ).toBeLessThanOrEqual(WATER_CHROMA)
      }
    })
  }

  it('no veil hue is a reserved salience colour', () => {
    // 0xffc890 is the ADRIFT course line. A veil that paints a sixth of the
    // frame in a state colour destroys that state's salience — and this is
    // read out of the canvas, so it tracks the signal if the signal moves.
    const src = readFileSync(CANVAS, 'utf8')
    const adrift = [...src.matchAll(/'adrift'\s*\n?\s*\?\s*(0x[0-9a-f]{6})/g)].map((m) =>
      Number(m[1])
    )
    expect(adrift.length, 'the adrift course colour was not found — regrep').toBeGreaterThan(0)
    for (const bucket of BUCKETS) {
      for (const hex of ambientVeil(bucket)?.colors ?? []) {
        expect(adrift, `${bucket} veil reuses the adrift signal hue`).not.toContain(hex)
      }
    }
  })

  it('open water stays water: composing the veil leaves only lawful tones', () => {
    // The renderer's composition, exactly: a covered pixel becomes the veil hue
    // outright (opaque 1px rects), an uncovered one keeps its true colour. So
    // the colour SET over open water is the sea ramp plus the veil hues, and
    // every member of it must sit at or below the water ceiling.
    for (const bucket of BUCKETS) {
      const veil = ambientVeil(bucket)
      if (veil === null) continue
      const dots = veilDots(`veil:${veil.colors.join('-')}:${veil.coverage}`, veil.coverage, veil.colors.length)
      expect(dots.length, `${bucket} veil covered nothing`).toBeGreaterThan(0)
      const water = new Set<number>([...RAMPS.sea, ...veil.colors])
      for (const hex of water) {
        expect(
          luma(hex),
          `${bucket}: open water would contain #${hex.toString(16)}, above the ceiling`
        ).toBeLessThanOrEqual(WATER_CEILING)
      }
    }
  })

  it('the canvas has no veil table of its own — this test stays in the loop', () => {
    const src = readFileSync(CANVAS, 'utf8')
    expect(src, 'engine-canvas.tsx must call ambientVeil()').toContain('ambientVeil(bucket)')
    // A re-declared table would route around every arm above.
    expect(
      src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1'),
      'engine-canvas.tsx re-declares a veil hue table — put it in lighting.ts'
    ).not.toMatch(/const\s+VEIL\b/)
  })
})
