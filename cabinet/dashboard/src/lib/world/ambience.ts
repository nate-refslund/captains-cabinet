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
 * THE CAPTAIN'S CYCLE RULING, 2026-07-30 — THE DAY IS STYLIZED, NOT REPORTED.
 *
 * Until this ruling every number below was `WINDOW_SKY[bucket] / WINDOW_SKY.day`,
 * the art's own sky table, and the cycle was therefore a strict function of it.
 * Measured on live frames that put dawn at 88% and dusk at 82% of noon: the two
 * hours that are supposed to be the most beautiful in the day were, to the eye,
 * noon. The Captain was shown that, was told plainly that they are shallow
 * BECAUSE the sky table says they are, and ruled:
 *
 *     "deepen them so the day visibly turns — warm low light at dawn, amber at
 *      dusk, the way the cozy pixel games we're aiming at do it. The cycle
 *      should read at a glance."
 *
 * So `CYCLE_SHADE` and `CYCLE_TONE` below are a RULING, deliberately NOT the sky
 * table, and a later session that "fixes" them back to `sky[bucket]/sky.day`
 * because the numbers do not match has broken the thing the Captain asked for.
 * That has happened in this codebase; hence this paragraph and the arms in
 * ambience.test.ts that pin the ruling and the divergence from the sky together.
 *
 * The sky table is not wrong and is not superseded: it still draws the sky behind
 * the window glass, which is what it was fitted for. It is simply a different
 * quantity from the light falling on the ground. At dawn the zenith IS cool blue
 * while the low sun on a wall is warm; a table of one cannot state the other.
 *
 * WHERE EVERY NUMBER COMES FROM (the two the Captain owns are marked RULED)
 *
 *  1. DEPTH — RULED, in the art's own unit. `CYCLE_SHADE` counts RAMPS OF SHADE:
 *     dawn one, dusk one and a half, night two, where one ramp is RAMP_SHADE
 *     (0.663), the median lightest→darkest ratio of the shipped terrain ramps.
 *     The unit is the art's, the count is the Captain's. Night's two is exactly
 *     what the sky-derived floor already produced, so NIGHT IS UNCHANGED BY THIS
 *     RULING, to the last bit of its light factor — an arm pins that.
 *
 *  2. THE FLOOR still clamps the ruling. The palette can only resolve so much
 *     darkness: measured through this module's own shipping path (quantize →
 *     light → snap) over all eleven ramps, 52 steps,
 *
 *       depth        light factor   surviving steps   thinnest ramp
 *       1 ramp           0.663          51 / 52         3 tones   <- dawn
 *       1.5 ramps        0.539          48 / 52         3 tones   <- dusk
 *       2 ramps          0.439          47 / 52         3 tones   <- night
 *       3 ramps          0.291          32 / 52         1 tone    <- blank
 *
 *     TWO ramps is the deepest depth at which no shipped ramp goes BLANK, and a
 *     surface whose ramp has collapsed to one tone is not darker, it is blank. So
 *     `ambientDepth` floors at RAMP_SHADE² whatever `CYCLE_SHADE` asks for. Both
 *     ends of that knee are arms, including one that asks for three ramps and
 *     watches the floor hold it at two.
 *
 *  3. HUE — RULED, as a SPLIT TONE: `CYCLE_TONE` names two illuminants per
 *     bucket, one for the shadow end of the art's tonal range and one for the lit
 *     end, and a source colour takes the light its own luminance points at
 *     (`CYCLE_CURVE`). Night names the same illuminant twice — the art's own moon
 *     sky — so night is a flat multiply exactly as before.
 *
 *     A SPLIT AND NOT A FLAT WARM MULTIPLY, and this is the measurement that
 *     decides it rather than a preference. A flat amber light drains blue from
 *     every pixel it touches, and most of this frame is a blue-green sea. Every
 *     flat warm illuminant tried, at every strength strong enough to see, turned
 *     open water brown — the sea ramp came out #3c3424 #3c3424 #444c2c #444c34
 *     #645434 under a mid-amber at 1.5 ramps of shade, which is mud, and it is
 *     the same failure ("dusk turned open water olive") that the chroma clause
 *     this ruling replaces was derived from. Split by tone, the warm half lands
 *     where the light actually falls: sand goes #9c5c34 → #c46c3c at dusk while
 *     the sea holds #34344c → #4c5454. That is what a cozy pixel game does at
 *     golden hour, and it is still a pure function of the pixel — the source
 *     colour's own luminance picks the light, never the pixel's position, so THE
 *     AMBIENCE STRUCTURE LAW above is untouched.
 *
 *     `CYCLE_CURVE` = 2 is part of the ruling: the warm half engages on the lit
 *     tones only. Linear reaches too far down. Measured on the shipped dusk
 *     illuminants, the strongest tint the clamp below admits is 0.218 at curve 1
 *     and 0.682 at curve 1.5; at curve 2 the full ruled tint survives, 1.000.
 *
 *  4. OPEN WATER STAYS WATER — the clamp on the ruling, and what replaced the
 *     chroma clause. THE FINDING, recorded because it is the one place this
 *     ruling could not keep an existing bound: the old clause said a tint may not
 *     make any surface MORE colourful than a neutral darkening of the same depth
 *     does. Its reference is a COLOURLESS light, which casts no colour on a
 *     neutral surface, so any illuminant colour at all registers as painting.
 *     Measured on the ruled LIT illuminants at the ruled depths, the largest
 *     tint it admits is 0.025 at dawn and 0.033 at dusk — a mid grey comes out
 *     #545454 and #44444c, which is the neutral darkening itself. It is not a
 *     tight bound on warmth, it is a statement that ambience must be colourless
 *     — which the Captain has now ruled against. It could not be kept.
 *
 *     What it was derived FROM can be, and is stated directly: the failure it
 *     caught was open water going olive. So the clamp is now open water itself —
 *     `toneStrength` pulls the tint back until every tone of the sea ramp still
 *     comes out with at least one palette bin more blue than red, measured on the
 *     shipping path (quantize → light → snap), plus the clause the old one
 *     carried implicitly: a light may only REMOVE light, never amplify a channel
 *     past 1. Both are threshold-free and both bite — the raw dusk sky ratio that
 *     produced the olive has r = 1.215 and fails the second outright, a flat warm
 *     multiply fails the first at every visible strength, and a hotter dusk
 *     illuminant than the ruled one is pulled back below 1. Arms in
 *     ambience.test.ts run all three.
 *
 *  5. THE OUTPUT SET — `CORPUS_PALETTE_BINS`, widened by the palette gate's own
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

const LUMA_W = [0.2126, 0.7152, 0.0722] as const
const gainOf = (l: readonly number[]) => LUMA_W[0] * l[0] + LUMA_W[1] * l[1] + LUMA_W[2] * l[2]

type Light = readonly [number, number, number]

/**
 * RULED (Captain, 2026-07-30). How deep each hour goes, counted in the art's own
 * RAMPS OF SHADE — one ramp is RAMP_SHADE, the median lightest→darkest ratio of
 * the shipped terrain ramps. The unit is the art's; the count is the ruling.
 *
 * NOT `WINDOW_SKY[bucket] / WINDOW_SKY.day`. That table put dawn at 0.88 and dusk
 * at 0.82 — measured on live frames, indistinguishable from noon. See the header.
 * Night's two ramps is what the sky-derived floor already produced, so night's
 * light factor is unchanged to the last bit.
 */
export const CYCLE_SHADE: Record<DayBucket, number> = {
  dawn: 1,
  day: 0,
  dusk: 1.5,
  night: 2,
}

/**
 * RULED (Captain, 2026-07-30). The two illuminants each hour lights by: the one
 * that reaches its SHADOW tones and the one that reaches its LIT tones. Same
 * units as WINDOW_SKY — a colour, read against `WINDOW_SKY.day` as noon.
 *
 * Night names its illuminant twice (the art's own moon sky), so night stays the
 * flat multiply it already was. Dawn and dusk are the ruling: a cool shadow and a
 * warm light, which is what golden hour IS and what a flat warm multiply cannot
 * be — measured, a flat amber turns the sea brown at every visible strength.
 */
export const CYCLE_TONE: Record<DayBucket, readonly [number, number]> = {
  dawn: [0x8098c8, 0xb89870],
  day: [WINDOW_SKY.day, WINDOW_SKY.day],
  dusk: [0x7080b8, 0xb88848],
  night: [WINDOW_SKY.night, WINDOW_SKY.night],
}

/**
 * RULED (Captain, 2026-07-30). Where the split sits: a source tone at relative
 * luminance `u` takes the light `u ** CYCLE_CURVE` of the way from the shadow
 * illuminant to the lit one. 2, not 1, so the warm half engages on the lit tones
 * only — linear reaches too far down and takes the blue out of open water.
 */
export const CYCLE_CURVE = 2

/**
 * A depth in ramps of shade, floored at what the palette can still resolve.
 * RAMP_SHADE² is the deepest depth at which no shipped ramp collapses to one
 * tone; a ruling that asks for more gets this, not a blanked surface. `null` for
 * a depth that changes nothing. Split out from `ambientDepth` so the floor is
 * reachable by a test at a depth no bucket ships.
 */
export function depthForSteps(steps: number): number | null {
  if (steps <= 0) return null
  return Math.max(RAMP_SHADE ** steps, RAMP_SHADE * RAMP_SHADE)
}

/** The bucket's overall light gain — the ruled depth, floored. `null` for a
 *  bucket that changes nothing (day). */
export function ambientDepth(bucket: DayBucket): number | null {
  return depthForSteps(CYCLE_SHADE[bucket])
}

/** An illuminant as a per-channel factor against noon. */
function illuminantRatio(hex: number): Light {
  const day = WINDOW_SKY.day
  const ch = (h: number, shift: number) => (h >> shift) & 0xff
  return [ch(hex, 16) / ch(day, 16), ch(hex, 8) / ch(day, 8), ch(hex, 0) / ch(day, 0)]
}

/** Walk a chromatic direction along its OWN power curve until it removes exactly
 *  `depth` of the light. Exponent interpolation, not a lerp to white, so the hue
 *  the illuminant states survives the depth it is put at. */
function walkToDepth(raw: Light, depth: number): Light {
  const e = Math.log(depth) / Math.log(gainOf(raw))
  return [raw[0] ** e, raw[1] ** e, raw[2] ** e]
}

/** The bucket's two illuminants, each walked to the ruled depth — the split
 *  BEFORE the clamp below has had its say. */
const rawEndsCache = new Map<DayBucket, readonly [Light, Light] | null>()
function rawEnds(bucket: DayBucket): readonly [Light, Light] | null {
  const hit = rawEndsCache.get(bucket)
  if (hit !== undefined) return hit
  const depth = ambientDepth(bucket)
  const value: readonly [Light, Light] | null =
    depth === null
      ? null
      : [
          walkToDepth(illuminantRatio(CYCLE_TONE[bucket][0]), depth),
          walkToDepth(illuminantRatio(CYCLE_TONE[bucket][1]), depth),
        ]
  rawEndsCache.set(bucket, value)
  return value
}

/**
 * One end of the split at a tint strength: 0 is a colourless darkening of the
 * same gain, 1 is the ruled illuminant in full. Applied to the ENDS and not to
 * the interpolated result, so the shipped light is completely described by its
 * two ends plus `CYCLE_CURVE` — which is exactly what the emitted artifact
 * carries, and why the Python twin needs no strength of its own.
 */
function atStrength(end: Light, strength: number): Light {
  const g = gainOf(end)
  return [g * (end[0] / g) ** strength, g * (end[1] / g) ** strength, g * (end[2] / g) ** strength]
}

/** The light falling on ONE source tone: its own luminance picks the point
 *  between the shadow end and the lit end. */
function lightAt(ends: readonly [Light, Light], source: number): Light {
  const u = Math.min(1, Math.max(0, luma(source) / 255)) ** CYCLE_CURVE
  const [s, w] = ends
  return [s[0] + (w[0] - s[0]) * u, s[1] + (w[1] - s[1]) * u, s[2] + (w[2] - s[2]) * u]
}

/** The bucket's split as it ships: both ends, clamped. */
const endsCache = new Map<DayBucket, readonly [Light, Light] | null>()
function shippedEnds(bucket: DayBucket): readonly [Light, Light] | null {
  const hit = endsCache.get(bucket)
  if (hit !== undefined) return hit
  const raw = rawEnds(bucket)
  const t = toneStrength(bucket)
  const value: readonly [Light, Light] | null =
    raw === null ? null : [atStrength(raw[0], t), atStrength(raw[1], t)]
  endsCache.set(bucket, value)
  return value
}

/** A colour quantized to the palette's own bit depth — the GPU's first act, so
 *  the clamp below and the LUT are measuring the same colour. */
export function quantize(hex: number): number {
  const q = (c: number) => ((c >> (8 - BITS)) << (8 - BITS)) | CENTRE
  return (q((hex >> 16) & 0xff) << 16) | (q((hex >> 8) & 0xff) << 8) | q(hex & 0xff)
}

/** One source colour through the shipping path: quantize → light → snap. */
function shadeWith(hex: number, ends: readonly [Light, Light]): number {
  const q = quantize(hex)
  return snapNative(q, lightAt(ends, q))
}

/**
 * How much of the ruled split actually survives — the clamp on the ruling, and
 * what replaced the chroma clause (header §4 records why that one could not be
 * kept, with the measurement). Two conditions, both threshold-free:
 *
 *   OPEN WATER STAYS WATER — every tone of the sea ramp comes out with at least
 *   one palette bin more blue than red. This is the failure the old clause was
 *   derived from ("dusk turned open water olive"), stated directly instead of
 *   inferred from a chroma statistic.
 *
 *   A LIGHT MAY ONLY REMOVE LIGHT — no channel factor above 1, checked at both
 *   ends of the split, which bounds every colour in the cube because the split is
 *   linear between them. The raw dusk sky ratio that produced the olive has
 *   r = 1.215 and fails this outright.
 *
 * 1 when the ruling ships as stated (it does, for all three lit buckets). Cached:
 * the search snaps the sea ramp, which is not free.
 */
const strengthCache = new Map<DayBucket, number>()
export function toneStrength(bucket: DayBucket): number {
  const hit = strengthCache.get(bucket)
  if (hit !== undefined) return hit
  const raw = rawEnds(bucket)
  const value = raw === null ? 0 : strengthFor(CYCLE_TONE[bucket][0], CYCLE_TONE[bucket][1], raw)
  strengthCache.set(bucket, value)
  return value
}

/**
 * The clamp, reachable with illuminants no bucket ships. Split out from
 * `toneStrength` for the same reason `depthForSteps` is split out of
 * `ambientDepth`: a guard that does not bind on any shipped value cannot be
 * tested through the shipped values, and an arm that only checks today's output
 * would stay green if the guard were deleted. Measured 2026-07-30 by mutation:
 * it did.
 *
 * `ends` is optional so callers that already walked the illuminants to a depth
 * do not walk them twice; pass the depth instead and it walks them.
 */
export function strengthFor(
  shadow: number,
  highlight: number,
  endsOrDepth: readonly [Light, Light] | number
): number {
  const ends: readonly [Light, Light] =
    typeof endsOrDepth === 'number'
      ? [
          walkToDepth(illuminantRatio(shadow), endsOrDepth),
          walkToDepth(illuminantRatio(highlight), endsOrDepth),
        ]
      : endsOrDepth
  return solveStrength(ends)
}

/** One palette bin of channel, the finest distinction the output set can make. */
const PALETTE_BIN = 1 << (8 - PALETTE_QUANT_BITS)

function solveStrength(raw: readonly [Light, Light]): number {
  const ok = (t: number) => {
    const ends: readonly [Light, Light] = [atStrength(raw[0], t), atStrength(raw[1], t)]
    // both ends bound the whole colour cube: the split is linear between them
    for (const end of ends) if (Math.max(...end) > 1) return false
    for (const tone of RAMPS.sea) {
      const out = shadeWith(tone, ends)
      if ((out & 0xff) - ((out >> 16) & 0xff) < PALETTE_BIN) return false
    }
    return true
  }
  if (ok(1)) return 1
  let lo = 0
  let hi = 1
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (ok(mid)) lo = mid
    else hi = mid
  }
  return lo
}

/**
 * The per-channel light factor a source colour stands in, for a bucket. `null`
 * for a bucket that changes nothing (day).
 *
 * It takes the SOURCE because the light is split by tone (header §3): shadows get
 * one illuminant, lit surfaces the other. Still a pure function of the pixel — the
 * source colour's own luminance picks the light, never the pixel's position.
 */
export function ambientLight(bucket: DayBucket, source: number): Light | null {
  const ends = shippedEnds(bucket)
  return ends === null ? null : lightAt(ends, source)
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
 *  The single-value form of `ambienceLut`'s inner loop, so the clamp in
 *  `solveStrength` and the table it gates cannot disagree about the metric. */
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
  if (shippedEnds(bucket) === null) {
    lutCache.set(bucket, null)
    return null
  }
  const { r: nr, g: ng, b: nb } = nativeRgb()
  const n = nr.length
  const out = new Uint32Array(LEVELS * LEVELS * LEVELS)
  const centre = (level: number) => (level << (8 - BITS)) | CENTRE
  for (let r = 0; r < LEVELS; r++) {
    for (let g = 0; g < LEVELS; g++) {
      for (let b = 0; b < LEVELS; b++) {
        // the light this SOURCE TONE stands in — the split is by luminance, so
        // it is read here, per entry, from the entry's own colour
        const src = (centre(r) << 16) | (centre(g) << 8) | centre(b)
        const light = ambientLight(bucket, src)!
        const sr = Math.min(255, centre(r) * light[0])
        const sg = Math.min(255, centre(g) * light[1])
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
