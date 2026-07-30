/**
 * ambience.ts — DAY/NIGHT AS A COLOUR MAP, not as an overlay.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * THE AMBIENCE STRUCTURE LAW (paid 2026-07-30, measured on live /world frames)
 *
 *   Ambience is a function of the PIXEL, never of its POSITION.
 *
 * A lighting pass may change what a colour is. It may not decide, from where a
 * pixel sits, whether to keep it — because that decision is texture, and the
 * frame already has texture: the art's. Every position-dependent ambience pass
 * substitutes its own grain for the surface's own dither.
 *
 * WHY THE BOUND IS THE OPERATION AND NOT A DOSE. The pass this replaced was an
 * opaque seeded dither: at `coverage` c it repainted c of every screen pixel in a
 * fixed hue. For such a pass the light it removes and the grain it adds are the
 * SAME quantity — mean darkening is c·|L_art − L_veil| and the edge energy it
 * injects between neighbouring pixels is ≈ 2c(1−c)·|L_art − L_veil|, so
 *
 *     added grain  ≈  2(1 − c) × darkening
 *
 * There is no c that buys darkness cheaply. Measured on real frames of /world at
 * z=1.60, mean |Δluminance| between horizontally adjacent pixels:
 *
 *   surface   art's own    dither night (c=0.42)
 *   sea            5.5     31.8   (5.8×)
 *   grass          5.4     25.3   (4.7×)
 *   roof           6.7     28.3   (4.2×)
 *
 * and per-pixel luminance correlation with the unveiled frame fell to r=0.525:
 * night threw away half of what the frame said, and the island read as blue
 * static. The art's own grain is ~5–7, so a dither can buy about 5–7 luminance of
 * darkening before its grain outweighs the art's. Night needs ~40. The mechanism
 * was arithmetically incapable of the job, which is why no amount of retuning
 * `coverage` was ever going to be the fix.
 *
 * A colour map cannot fail that way. Identical input colours leave identical, so
 * no edge is created. Measured the same way, on live frames of this module at a
 * pinned 02:54 clock against the same 12:53 baseline:
 *
 *   surface   art's own    remap night      mean luminance
 *   sea            5.5     2.1  (0.4×)      112 → 60
 *   grass          5.4     1.6  (0.3×)      101 → 51
 *   roof           6.7     1.4  (0.2×)      113 → 48
 *
 * — night is now DEEPER than the dither ever got (−52 against its −26) while the
 * grain sits below the art's own everywhere, and the island reads as the same
 * island. Per-pixel luminance fidelity is 0.769, not 1.000, and the reason is
 * worth knowing: the LUT quantizes to the palette's own 5 bits, so the many
 * near-identical tones a non-integer zoom interpolates into a frame collapse onto
 * one output colour. That is smoothing lost, not structure — a distinct-colour
 * count on a grass patch goes 205 → 5 while the flat-neighbour count the law
 * measures stays at zero.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * WHERE EVERY NUMBER COMES FROM (nothing here is picked)
 *
 *  1. HUE DIRECTION — `WINDOW_SKY` in lighting.ts. That table is the art's own
 *     statement of what each hour's sky is, ratified with the direction doc, and
 *     `sky[bucket] / sky['day']` per channel is therefore the art's own statement
 *     of how much light of each colour that hour has. Night's is (0.15, 0.19,
 *     0.34): dim, and relatively blue — the moon-tint §12 asks for, taken from
 *     the art rather than invented beside it.
 *
 *  2. DEPTH — the art's own deepest shade, floored by what the palette can still
 *     resolve. Every ramp in `RAMPS` is a shading ladder the art declares, and
 *     their lightest→darkest luminance ratios have median RAMP_SHADE (0.663) —
 *     one ramp of shade. Night's own sky ratio asks for 0.19, far deeper, and the
 *     palette cannot pay it, so the floor is RAMP_SHADE². TWO, and not three,
 *     because two is the deepest depth at which no shipped ramp goes BLANK, and a
 *     surface whose ramp has collapsed to one tone is not darker, it is blank.
 *     Measured through this module, over all eleven ramps (52 steps):
 *
 *       depth        light factor   surviving steps   thinnest ramp
 *       1 ramp           0.663          52 / 52         3 tones
 *       2 ramps          0.439          45 / 52         3 tones   <- shipped
 *       3 ramps          0.291          31 / 52         1 tone    <- blank
 *       4 ramps          0.193          20 / 52         1 tone
 *
 *     Both ends of that knee are arms in ambience.test.ts, so the choice cannot
 *     drift without the measurement moving with it. Dawn and dusk are shallower
 *     than one ramp already — their own sky ratio (0.88 / 0.82) is the whole of
 *     it, and every one of the 52 steps survives at both.
 *
 *  3. CHROMA — a tint may not make a surface MORE colourful than a neutral
 *     darkening of the same depth already does. Light drains colour; it does not
 *     paint. The reference is neutral rather than "no gain at all" because the
 *     SNAP itself costs chroma: the palette is sparse in dark near-greys, so a
 *     grey cobble tone lands on the nearest slightly warmer native colour
 *     whatever the tint is (measured worst gain at neutral: 1.24 dawn, 1.59 dusk,
 *     1.43 night). Bounded that way, dawn and night take the sky's direction in
 *     full; dusk is pulled to 6.4% of it — (0.837, 0.811, 0.779), a neutral drain
 *     with a whisper of warmth. That is not a coincidence worth hiding: it is
 *     where the shipped dusk hues were already aimed by hand a day earlier
 *     ("warmth at dusk is the LAMPS coming on and the lit windows drawn above
 *     this pass — not a tint over the whole sea"), and it is why an unbounded
 *     sky tint is wrong rather than merely strong. Unbounded, dusk turned open
 *     water olive and a grey cobble tone into a 54-chroma orange, a 6.4x gain.
 *
 *  4. THE OUTPUT SET — `CORPUS_PALETTE_BINS`, widened by the palette gate's own
 *     `neighbor_radius`. Every colour this module can emit is a colour the gate
 *     calls native, so ambience stays palette-lawful BY CONSTRUCTION rather than
 *     by a hue table somebody has to keep checking. This is also what keeps the
 *     old veil laws (nothing brighter than open water, nothing more colourful
 *     than the water it shades) satisfied without asserting them: a remap can
 *     only ever land on a colour the art already contains.
 *
 * SNAPPING TO BIN CENTRES ALONE IS NOT ENOUGH, and this is the one thing to keep
 * if this file is ever rewritten. Against the 342 bare bin centres the sea ramp's
 * five steps collapse to two and grass's to three — the palette is fitted from
 * day-lit art and is sparse where night lands. Against the gate's native set
 * (2952 bins, 9% of colour space) all five survive, ordered. That is measured in
 * ambience.test.ts, both ways.
 */
import { CORPUS_PALETTE_BINS, PALETTE_NEIGHBOR_RADIUS, PALETTE_QUANT_BITS } from './corpus-palette'
import { RAMPS } from './iso-terrain'
import { WINDOW_SKY, type DayBucket } from './lighting'

/** ITU-R BT.709 relative luminance of a packed 0xRRGGBB. */
export function luma(hex: number): number {
  return 0.2126 * ((hex >> 16) & 0xff) + 0.7152 * ((hex >> 8) & 0xff) + 0.0722 * (hex & 0xff)
}

/**
 * The art's own deepest shade: the median lightest→darkest luminance ratio over
 * every shipped terrain ramp. DERIVED, so a re-fitted ramp moves it — which is
 * the point. `RAMPS` entries are ordered dark→light (iso-terrain.ts).
 */
export const RAMP_SHADE: number = (() => {
  const ratios = Object.values(RAMPS)
    .map((r) => luma(r[0]) / luma(r[r.length - 1]))
    .sort((a, b) => a - b)
  return ratios[ratios.length >> 1]
})()

/** CIE Lab chroma — how COLOURFUL a hue is, independent of how light it is. */
export function chroma(hex: number): number {
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

const LUMA_W = [0.2126, 0.7152, 0.0722] as const
const gainOf = (l: readonly number[]) => LUMA_W[0] * l[0] + LUMA_W[1] * l[1] + LUMA_W[2] * l[2]

/**
 * Per-channel light factor for a bucket. Three clauses, in order, each derived —
 * see the module header for where each number comes from and what it cost.
 *
 *   1. the art's own sky ratio, `WINDOW_SKY[bucket] / WINDOW_SKY.day`;
 *   2. floored at the art's own deepest shade (RAMP_SHADE²) so night cannot ask
 *      for more darkness than the palette has tones for;
 *   3. and pulled back toward neutral until the tint makes no surface MORE
 *      colourful than a neutral darkening of the same depth already does.
 *
 * `null` for a bucket that changes nothing (day). Cached: clause 3 snaps every
 * shipped ramp colour, which is not free.
 */
const lightCache = new Map<DayBucket, readonly [number, number, number] | null>()
export function ambientLight(bucket: DayBucket): readonly [number, number, number] | null {
  const hit = lightCache.get(bucket)
  if (hit !== undefined) return hit
  const value = deriveLight(bucket)
  lightCache.set(bucket, value)
  return value
}

function deriveLight(bucket: DayBucket): readonly [number, number, number] | null {
  const day = WINDOW_SKY.day
  const sky = WINDOW_SKY[bucket]
  if (sky === day) return null
  const ch = (hex: number, shift: number) => (hex >> shift) & 0xff
  const raw: [number, number, number] = [
    ch(sky, 16) / ch(day, 16),
    ch(sky, 8) / ch(day, 8),
    ch(sky, 0) / ch(day, 0),
  ]

  // ── clause 2: the palette's floor on how dark ambience may go ─────────────
  const skyGain = gainOf(raw)
  const floor = RAMP_SHADE * RAMP_SHADE
  // Walk the SAME chromatic direction back along its own power curve until it
  // removes exactly `floor` of the light. Exponent interpolation, not a lerp to
  // white, so the hue the sky states survives the clamp.
  const depth =
    skyGain >= floor
      ? raw
      : ([
          raw[0] ** (Math.log(floor) / Math.log(skyGain)),
          raw[1] ** (Math.log(floor) / Math.log(skyGain)),
          raw[2] ** (Math.log(floor) / Math.log(skyGain)),
        ] as [number, number, number])

  // ── clause 3: light drains colour, it does not paint ─────────────────────
  // `t` scales the tint's deviation from neutral at a FIXED depth: t=0 is a
  // neutral darkening, t=1 is the sky's full direction. The reference is neutral
  // and not zero-gain because the SNAP itself costs chroma — the palette is
  // sparse in dark near-greys, so a grey cobble tone lands on the nearest
  // slightly warmer native colour whatever the tint is.
  const g = gainOf(depth)
  const at = (t: number) => depth.map((v) => g * (v / g) ** t) as [number, number, number]
  const worstGain = (l: readonly number[]) => {
    let worst = 0
    for (const ramp of Object.values(RAMPS)) {
      for (const c of ramp) {
        const before = chroma(c)
        if (before < 1) continue // a pure grey has no chroma to gain FROM
        worst = Math.max(worst, chroma(snapNative(c, l)) / before)
      }
    }
    return worst
  }
  // The statistic is the WORST ratio and not a mean, and a second one was checked
  // rather than assumed: mean absolute chroma increase agrees on the case that
  // decides anything (dusk, 24.4 against neutral's 0.30) and differs only in
  // pulling night's blue back from t=1.00 to t=0.84, where nothing is visible.
  // Max-ratio keeps the night the art's sky asks for, so max-ratio is what runs.
  const neutral = worstGain(at(0))
  if (worstGain(at(1)) <= neutral) return at(1)
  let lo = 0
  let hi = 1
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (worstGain(at(mid)) <= neutral) lo = mid
    else hi = mid
  }
  return at(lo)
}

const BITS = PALETTE_QUANT_BITS
const LEVELS = 1 << BITS
/** Bin-centre value of a quantized channel — palette_coherence.py's own math. */
const CENTRE = 1 << (8 - BITS - 1)

/** Every colour the palette gate calls NATIVE: a palette bin, or within
 *  `neighbor_radius` of one. Built once; ~2952 of 32768 bins. */
export function nativeColors(radius = PALETTE_NEIGHBOR_RADIUS): number[] {
  const seen = new Set<number>()
  for (const key of CORPUS_PALETTE_BINS) {
    const r0 = (key >> (2 * BITS)) & (LEVELS - 1)
    const g0 = (key >> BITS) & (LEVELS - 1)
    const b0 = key & (LEVELS - 1)
    for (let dr = -radius; dr <= radius; dr++) {
      const r = r0 + dr
      if (r < 0 || r >= LEVELS) continue
      for (let dg = -radius; dg <= radius; dg++) {
        const g = g0 + dg
        if (g < 0 || g >= LEVELS) continue
        for (let db = -radius; db <= radius; db++) {
          const b = b0 + db
          if (b < 0 || b >= LEVELS) continue
          seen.add((r << (2 * BITS)) | (g << BITS) | b)
        }
      }
    }
  }
  return [...seen].sort((a, b) => a - b)
}

/** A native bin key as a packed 0xRRGGBB at its bin centre. */
export function binToRgb(key: number): number {
  const m = LEVELS - 1
  const r = (((key >> (2 * BITS)) & m) << (8 - BITS)) | CENTRE
  const g = (((key >> BITS) & m) << (8 - BITS)) | CENTRE
  const b = ((key & m) << (8 - BITS)) | CENTRE
  return (r << 16) | (g << 8) | b
}

/** One colour under a light factor, snapped to the nearest native colour.
 *  The single-value form of `ambienceLut`'s inner loop, so the derivation in
 *  `deriveLight` and the table it produces cannot disagree about the metric. */
export function snapNative(hex: number, light: readonly number[]): number {
  const { r: nr, g: ng, b: nb } = nativeRgb()
  const tr = Math.min(255, ((hex >> 16) & 0xff) * light[0])
  const tg = Math.min(255, ((hex >> 8) & 0xff) * light[1])
  const tb = Math.min(255, (hex & 0xff) * light[2])
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < nr.length; i++) {
    const dr = tr - nr[i]
    const dg = tg - ng[i]
    const db = tb - nb[i]
    const d = 0.6378 * dr * dr + 2.1456 * dg * dg + 0.2166 * db * db
    if (d < bestD) {
      bestD = d
      best = i
    }
  }
  return ((nr[best] & 0xff) << 16) | ((ng[best] & 0xff) << 8) | (nb[best] & 0xff)
}

/** Native colours as three parallel channel arrays — built once, reused. */
let nativeChannels: { r: Float64Array; g: Float64Array; b: Float64Array } | null = null
function nativeRgb() {
  if (nativeChannels) return nativeChannels
  const native = nativeColors()
  const n = native.length
  const r = new Float64Array(n)
  const g = new Float64Array(n)
  const b = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    const rgb = binToRgb(native[i])
    r[i] = (rgb >> 16) & 0xff
    g[i] = (rgb >> 8) & 0xff
    b[i] = rgb & 0xff
  }
  nativeChannels = { r, g, b }
  return nativeChannels
}

/**
 * The LUT: for every quantized source colour, the NATIVE colour nearest to that
 * colour under the bucket's light.
 *
 * Nearest is measured in Rec.709-weighted RGB so LUMINANCE error dominates — a
 * night that lands on the right brightness in a slightly wrong hue still reads as
 * night, whereas the reverse reads as a colour cast. The target is the CONTINUOUS
 * product `source × light`, never a re-quantized one: re-quantizing before the
 * snap throws away exactly the sub-bin ordering that keeps a five-step ramp five
 * steps, which is the property ambience.test.ts pins.
 *
 * Returns LEVELS³ packed 0xRRGGBB, indexed `(r << 2*BITS) | (g << BITS) | b` over
 * quantized channels — the same key space as the palette bins, so a caller can
 * index it straight from a quantized pixel. `null` for a bucket that is a no-op.
 * ~100ms per bucket; cached, and only the rendered bucket is ever built.
 */
const lutCache = new Map<DayBucket, Uint32Array | null>()
export function ambienceLut(bucket: DayBucket): Uint32Array | null {
  const hit = lutCache.get(bucket)
  if (hit !== undefined) return hit
  const light = ambientLight(bucket)
  if (light === null) {
    lutCache.set(bucket, null)
    return null
  }
  const { r: nr, g: ng, b: nb } = nativeRgb()
  const n = nr.length
  const out = new Uint32Array(LEVELS * LEVELS * LEVELS)
  const centre = (level: number) => (level << (8 - BITS)) | CENTRE
  for (let r = 0; r < LEVELS; r++) {
    const sr = Math.min(255, centre(r) * light[0])
    for (let g = 0; g < LEVELS; g++) {
      const sg = Math.min(255, centre(g) * light[1])
      for (let b = 0; b < LEVELS; b++) {
        const sb = Math.min(255, centre(b) * light[2])
        let best = 0
        let bestD = Infinity
        for (let i = 0; i < n; i++) {
          const dr = sr - nr[i]
          const dg = sg - ng[i]
          const db = sb - nb[i]
          const d = 0.6378 * dr * dr + 2.1456 * dg * dg + 0.2166 * db * db
          if (d < bestD) {
            bestD = d
            best = i
          }
        }
        out[(r << (2 * BITS)) | (g << BITS) | b] =
          ((nr[best] & 0xff) << 16) | ((ng[best] & 0xff) << 8) | (nb[best] & 0xff)
      }
    }
  }
  lutCache.set(bucket, out)
  return out
}

/** Apply the LUT to one packed 0xRRGGBB — the reference the tests measure. */
export function remap(lut: Uint32Array, rgb: number): number {
  const r = ((rgb >> 16) & 0xff) >> (8 - BITS)
  const g = ((rgb >> 8) & 0xff) >> (8 - BITS)
  const b = (rgb & 0xff) >> (8 - BITS)
  return lut[(r << (2 * BITS)) | (g << BITS) | b]
}

/**
 * The LUT as an RGBA texture payload: LEVELS slices of LEVELS×LEVELS laid out
 * left-to-right, top-to-bottom in a `SLICES_PER_ROW`-wide grid. The blue channel
 * picks the slice; red and green index inside it. Nearest sampling only — a
 * bilinear tap would bleed one slice into the next.
 */
export const LUT_SLICES_PER_ROW = 8
export const LUT_TEX_W = LEVELS * LUT_SLICES_PER_ROW
export const LUT_TEX_H = LEVELS * (LEVELS / LUT_SLICES_PER_ROW)

export function lutPixels(lut: Uint32Array): Uint8Array {
  const px = new Uint8Array(LUT_TEX_W * LUT_TEX_H * 4)
  for (let b = 0; b < LEVELS; b++) {
    const ox = (b % LUT_SLICES_PER_ROW) * LEVELS
    const oy = ((b / LUT_SLICES_PER_ROW) | 0) * LEVELS
    for (let g = 0; g < LEVELS; g++) {
      for (let r = 0; r < LEVELS; r++) {
        // asked through `remap`, not by indexing the array, so the CPU reference
        // the tests measure and the table the GPU reads cannot drift apart
        const rgb = remap(lut, binToRgb((r << (2 * BITS)) | (g << BITS) | b))
        const o = ((oy + g) * LUT_TEX_W + (ox + r)) * 4
        px[o] = (rgb >> 16) & 0xff
        px[o + 1] = (rgb >> 8) & 0xff
        px[o + 2] = rgb & 0xff
        px[o + 3] = 255
      }
    }
  }
  return px
}
