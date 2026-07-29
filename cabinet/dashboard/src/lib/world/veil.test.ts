/**
 * veil.test.ts — THE VEIL LAWS, and the wiring that makes them binding.
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
 * The final arm is STRUCTURAL rather than a name grep: it pins the canvas to a
 * single veil call site fed by exactly this module's output, because a second
 * table at the call site would silently take every arm above out of the loop,
 * and that is how the first one survived — a `const VEIL` inside a 3000-line
 * component. The name-grep version of that arm was walked through four ways by
 * an adversarial review before it ever ran in CI; the shapes it missed are
 * listed at the arm.
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

describe('the veil laws', () => {
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
      expect(veil.colors.length).toBeGreaterThan(0)
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

  it('open water stays water: the composed frame contains only lawful tones', () => {
    // The renderer's composition, run for real rather than described: veilDots
    // decides WHICH pixels are covered and with WHICH hue index, and the canvas
    // fills each with colors[d.hue] outright (opaque 1px rects). So we resolve
    // the indices the same way and collect the colour set an open-water region
    // would actually contain. Resolving them is what makes this arm non-vacuous
    // — an out-of-range hue index yields undefined here and nowhere else.
    for (const bucket of BUCKETS) {
      const veil = ambientVeil(bucket)
      if (veil === null) continue
      const dots = veilDots(
        `veil:${veil.colors.join('-')}:${veil.coverage}`,
        veil.coverage,
        veil.colors.length
      )
      expect(dots.length, `${bucket} veil covered nothing`).toBeGreaterThan(0)
      const painted = new Set<number>()
      for (const d of dots) {
        const hex = veil.colors[d.hue]
        expect(hex, `${bucket}: veilDots emitted hue index ${d.hue}, out of range`).toBeTypeOf(
          'number'
        )
        painted.add(hex)
      }
      // every hue in the table must actually reach the frame — a rotation that
      // silently collapses to one hue is the CLUSTER dominance the rotation
      // exists to prevent, and nothing else in the suite would notice.
      expect(painted.size, `${bucket}: rotation collapsed`).toBe(veil.colors.length)
      // the coverage is a DOSE, and an unbounded one stops being a dither and
      // becomes a repaint. Night, the densest veil there is, sits at 0.42.
      expect(veil.coverage).toBeGreaterThan(0)
      expect(veil.coverage, `${bucket}: a veil over half the frame is a wash`).toBeLessThan(0.5)
      for (const hex of new Set<number>([...RAMPS.sea, ...painted])) {
        expect(
          luma(hex),
          `${bucket}: open water would contain #${hex.toString(16)}, above the ceiling`
        ).toBeLessThanOrEqual(WATER_CEILING)
      }
    }
  })

  it('the canvas sources its veil from here and nowhere else — structurally', () => {
    // THE FIRST VERSION OF THIS ARM WAS A NAME GREP, and an adversarial review
    // walked through it four ways in ten minutes: `const VEIL_TABLE` (\b does
    // not fire before `_`), `const veilTable` (case), a ternary at the draw
    // call that never declares a table at all, and a COMMENT containing the
    // string the "must call" half searched for. So it is structural now: the
    // veil texture must be built from exactly one call site, and that call site
    // must pass exactly this module's output. A local table is then unreachable
    // rather than merely un-grepped.
    const raw = readFileSync(CANVAS, 'utf8')
    const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1')

    // exactly one place builds the veil texture, and its arguments are ours
    const built = [...src.matchAll(/(function\s+)?veilTexture\(([^)]*)\)/g)]
      .filter((m) => !m[1]) // the declaration is not a call site
      .map((m) => m[2].trim())
    expect(built, 'engine-canvas.tsx must build the veil texture exactly once').toHaveLength(1)
    expect(built[0]).toBe('veil.colors, veil.coverage')

    // ...and `veil` is bound from ambientVeil, in code, not in a comment
    const bindings = [...src.matchAll(/const\s+veil\s*=\s*([^\n]+)/g)].map((m) => m[1].trim())
    expect(bindings, 'one binding for the veil').toHaveLength(1)
    expect(bindings[0]).toBe('ambientVeil(bucket)')
    expect(src, 'ambientVeil must be imported, not shadowed locally').toMatch(
      /import\s*\{[^}]*\bambientVeil\b[^}]*\}\s*from\s*'@\/lib\/world\/lighting'/
    )

    // no hue table of any name may sit in the canvas: the veil spec shape is
    // `colors: [...]`, and the only legitimate occurrence is veilTexture's own
    // parameter list.
    const specs = [...src.matchAll(/\bcolors\s*:\s*\[/g)]
    expect(specs, 'engine-canvas.tsx declares a veil spec — put it in lighting.ts').toHaveLength(
      0
    )
  })
})
