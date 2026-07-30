/**
 * ambience.test.ts — THE AMBIENCE STRUCTURE LAW, and the measurements that
 * derive it.
 *
 * WHAT THIS EXISTS TO CATCH. On 2026-07-30 the shipped night ambience replaced
 * 42% of every screen pixel with one of three navies. Measured on live browser
 * frames of /world at a pinned 02:13 clock, against the same frame with no
 * ambience at all, the mean |Δluminance| between horizontally adjacent pixels
 * went 5.5 → 31.8 on open sea, 5.4 → 25.3 on grass and 6.7 → 28.3 on a roof, and
 * per-pixel luminance correlation with the unveiled frame fell to 0.525. The
 * island read as blue static. Nothing went red:
 *
 *   - veil.test.ts bounded the veil's HUES (nothing brighter than open water,
 *     nothing more colourful than the water it shades). Both bounds were, and
 *     are, correct; neither says anything about how much of the art the pass is
 *     allowed to delete. Its one dose arm asserted `coverage < 0.5`, a number
 *     chosen after the fact so that 0.42 would pass — a ceiling that could not
 *     fire is a disabled sensor.
 *   - PALETTE_FOREIGN_MASS asks whether each pixel is a corpus colour; three
 *     in-bin navies pass it perfectly however many pixels they take.
 *   - the twelve world-capture invariants judge a Python re-draw of the LAYOUT,
 *     which has no day bucket and no compositor, so no screen-space pass is
 *     inside their reach at any zoom.
 *
 * TWO NEAR-MISS ARMS, RECORDED so they are not re-proposed as the fix. Neither
 * would have caught it, and both look like they should:
 *
 *   "the veil may not raise a patch's distinct-colour count above the surface's
 *   own palette" — measured on the same crops, the night dither LOWERED it, 205
 *   → 177, because a replace-dither deletes tones as well as adding three.
 *
 *   "the veil may not invert the luminance order of the ramps it covers" — a
 *   uniform replace at coverage c composites to `(1−c)·source + c·veil`, an
 *   affine map with positive slope, so order survives by construction.
 *
 * The defect is neither the count nor the order. It is that the pass decided what
 * to paint from WHERE A PIXEL SAT. So that is what the first arm below tests, and
 * it is threshold-free: the test asks whether ambience is a function of colour.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  RAMP_SHADE,
  ambienceLut,
  ambientLight,
  binToRgb,
  chroma,
  luma,
  lutPixels,
  LUT_TEX_H,
  LUT_TEX_W,
  nativeColors,
  remap,
  snapNative,
} from './ambience'
import { CORPUS_PALETTE_BINS, PALETTE_NEIGHBOR_RADIUS, PALETTE_QUANT_BITS } from './corpus-palette'
import { fnv1a } from './hash'
import { RAMPS } from './iso-terrain'
import { WINDOW_SKY, type DayBucket } from './lighting'

const BUCKETS: readonly DayBucket[] = ['dawn', 'day', 'dusk', 'night'] as const
const LIT: readonly DayBucket[] = ['dawn', 'dusk', 'night'] as const

const CALIBRATION = join(
  process.cwd(),
  '..',
  'scripts',
  'world-aesthetic',
  'calibration',
  'palette.json'
)

/** Mean |Δluminance| between horizontally adjacent pixels — the same statistic
 *  the live-frame measurement in the header used, so the numbers are comparable. */
function textureEnergy(rows: readonly (readonly number[])[]): number {
  let sum = 0
  let n = 0
  for (const row of rows) {
    for (let i = 1; i < row.length; i++) {
      sum += Math.abs(luma(row[i]) - luma(row[i - 1]))
      n++
    }
  }
  return n === 0 ? 0 : sum / n
}

/**
 * A patch of the art, drawn the way the art draws it: a ramp Bayer-dithered
 * across a gradient, which is what `terrainField` produces and what gives ground
 * its own grain. Deterministic — no clock, no RNG.
 */
function artPatch(ramp: readonly number[], w = 48, h = 48): number[][] {
  const BAYER = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
  ]
  const out: number[][] = []
  for (let y = 0; y < h; y++) {
    const row: number[] = []
    for (let x = 0; x < w; x++) {
      const t = ((x + y) / (w + h)) * (ramp.length - 1)
      const i = Math.floor(t)
      const frac = t - i
      const step = frac * 16 > BAYER[y & 3][x & 3] ? Math.min(ramp.length - 1, i + 1) : i
      row.push(ramp[step])
    }
    out.push(row)
  }
  return out
}

describe('the ambience structure law', () => {
  it('THE LAW: ambience is a function of the pixel, never of its position', () => {
    // The arm the dither could not pass. Every pixel of an art patch goes through
    // the pass; group the results by the colour that went IN. A colour map yields
    // exactly one output per input. A pass that consults x,y — a dither, a noise
    // field, a screen-space texture — yields more than one, and every extra
    // output is an edge the art did not draw.
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)
      expect(lut, `${bucket} has no ambience LUT`).not.toBeNull()
      const seen = new Map<number, Set<number>>()
      for (const ramp of Object.values(RAMPS)) {
        for (const row of artPatch(ramp)) {
          for (const px of row) {
            const got = remap(lut!, px)
            const bag = seen.get(px) ?? new Set<number>()
            bag.add(got)
            seen.set(px, bag)
          }
        }
      }
      expect(seen.size, `${bucket}: the patches carried no colours`).toBeGreaterThan(20)
      const split = [...seen.entries()].filter(([, outs]) => outs.size > 1)
      expect(
        split.map(([src, outs]) => `#${src.toString(16)} -> ${outs.size} colours`),
        `${bucket}: ambience is position-dependent — these source colours came out ` +
          'as more than one colour, and every extra one is grain the art did not draw'
      ).toEqual([])
    }
  })

  it('a colour map creates no edge the art did not draw', () => {
    // The law's sharpest consequence, and it needs no tolerance at all: where two
    // neighbouring pixels were the SAME colour, ambience cannot have made them
    // different, because it never saw where they were. This is the count the night
    // dither could not keep at zero — at coverage 0.42 it decided independently for
    // each of them.
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      let flat = 0
      const created: string[] = []
      for (const [name, ramp] of Object.entries(RAMPS)) {
        const patch = artPatch(ramp)
        const lit = patch.map((row) => row.map((px) => remap(lut, px)))
        for (let y = 0; y < patch.length; y++) {
          for (let x = 1; x < patch[y].length; x++) {
            if (patch[y][x] !== patch[y][x - 1]) continue
            flat++
            if (lit[y][x] !== lit[y][x - 1]) created.push(`${name}@${x},${y}`)
          }
        }
      }
      expect(flat, `${bucket}: the patches had no flat neighbours to test`).toBeGreaterThan(1000)
      expect(created.slice(0, 5), `${bucket}: ambience split ${created.length} flat pairs`).toEqual(
        []
      )
    }
  })

  it('grain does not grow: the art’s own dither is the bound', () => {
    // The measurable consequence, over the art's whole ramp set. Aggregate rather
    // than per-ramp on purpose and with the reason recorded: a colour map cannot
    // CREATE an edge (arm above) but it can STEEPEN one, when two neighbouring ramp
    // steps happen to snap further apart than they were. On dirtWorn — the thinnest
    // ramp there is, 33 luminance across five steps — dawn does exactly that, by
    // 1.4%. A per-ramp bound would have to carry a tolerance for it, and a
    // tolerance is a number somebody picked. Over the eleven shipped ramps the
    // bound needs none: measured 0.87 dawn, 0.82 dusk, 0.38 night, against the
    // 4.2-5.8x the dither posted.
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      let before = 0
      let after = 0
      for (const ramp of Object.values(RAMPS)) {
        const patch = artPatch(ramp)
        before += textureEnergy(patch)
        after += textureEnergy(patch.map((row) => row.map((px) => remap(lut, px))))
      }
      expect(before, 'the art patches have no grain to compare against').toBeGreaterThan(0)
      expect(
        after / before,
        `${bucket}: ambience raised the art's own grain by ` +
          `${((after / before - 1) * 100).toFixed(1)}% — it is adding texture, not light`
      ).toBeLessThanOrEqual(1)
    }
  })

  it('no ramp goes blank, and no ramp inverts', () => {
    // The other way a colour map goes wrong: not adding grain but ERASING it. Some
    // tonal loss at night is the art behaving correctly — you see less in the dark,
    // and the two thinnest ramps (dirtWorn spans 33 luminance, ploughed 48) cannot
    // hold five steps at 44% light. What is NOT allowed is the degenerate end: a
    // ramp down to ONE tone is a blanked surface, not a shaded one.
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      for (const [name, ramp] of Object.entries(RAMPS)) {
        const got = ramp.map((c) => remap(lut, c))
        expect(
          new Set(got).size,
          `${bucket}/${name}: ${ramp.length} art steps collapsed to one tone — ` +
            'that surface is blank, not dark'
        ).toBeGreaterThanOrEqual(2)
        for (let i = 1; i < got.length; i++) {
          expect(
            luma(got[i]),
            `${bucket}/${name}: step ${i} came out darker than step ${i - 1} — ` +
              'ambience inverted the ramp the art declared'
          ).toBeGreaterThanOrEqual(luma(got[i - 1]))
        }
      }
    }
  })

  it('the depth sits at the palette’s knee: one ramp deeper blanks a surface', () => {
    // WHY NIGHT IS TWO RAMPS OF SHADE AND NOT THREE, as a measurement rather than
    // a sentence in a docstring. Both directions, so neither can rot: at the
    // shipped depth nothing is blank, and one ramp deeper something is. If a
    // re-fitted palette ever makes three ramps safe, this arm fails and the
    // docstring's table gets re-measured instead of being trusted.
    const light = ambientLight('night')!
    const shipped = 0.2126 * light[0] + 0.7152 * light[1] + 0.0722 * light[2]
    expect(shipped).toBeCloseTo(RAMP_SHADE * RAMP_SHADE, 2)

    const native = nativeColors()
    const snapTo = (pool: readonly number[], hex: number, l: readonly number[]) => {
      const t = [
        Math.min(255, ((hex >> 16) & 0xff) * l[0]),
        Math.min(255, ((hex >> 8) & 0xff) * l[1]),
        Math.min(255, (hex & 0xff) * l[2]),
      ]
      let best = pool[0]
      let bestD = Infinity
      for (const key of pool) {
        const rgb = binToRgb(key)
        const d =
          0.6378 * (t[0] - ((rgb >> 16) & 0xff)) ** 2 +
          2.1456 * (t[1] - ((rgb >> 8) & 0xff)) ** 2 +
          0.2166 * (t[2] - (rgb & 0xff)) ** 2
        if (d < bestD) {
          bestD = d
          best = key
        }
      }
      return binToRgb(best)
    }
    /** thinnest surviving ramp at a depth of `ramps` shades, same hue direction */
    const thinnestAt = (ramps: number) => {
      // walk the SAME chromatic direction, the way ambientLight's clamp does
      const t = Math.log(RAMP_SHADE ** ramps) / Math.log(shipped)
      const l = light.map((v) => v ** t)
      return Math.min(
        ...Object.values(RAMPS).map((r) => new Set(r.map((c) => snapTo(native, c, l))).size)
      )
    }
    expect(thinnestAt(2), 'the shipped depth blanks a ramp').toBeGreaterThanOrEqual(2)
    expect(
      thinnestAt(3),
      'three ramps of shade no longer blanks any surface — the palette changed, ' +
        're-measure the depth table in ambience.ts'
    ).toBe(1)
  })

  it('bin centres alone are NOT enough — the gate’s own radius is load-bearing', () => {
    // The measurement that decides the output set, kept as an arm so a later
    // simplification to "snap to the 342 bins" is caught rather than shipped: the
    // palette is fitted from day-lit art and is sparse where night lands.
    const centres = new Set(CORPUS_PALETTE_BINS)
    const native = nativeColors()
    expect(native.length).toBeGreaterThan(centres.size * 5)
    const light = ambientLight('night')!
    const snapTo = (pool: readonly number[], hex: number) => {
      const t = [
        Math.min(255, ((hex >> 16) & 0xff) * light[0]),
        Math.min(255, ((hex >> 8) & 0xff) * light[1]),
        Math.min(255, (hex & 0xff) * light[2]),
      ]
      let best = pool[0]
      let bestD = Infinity
      for (const key of pool) {
        const rgb = binToRgb(key)
        const d =
          0.6378 * (t[0] - ((rgb >> 16) & 0xff)) ** 2 +
          2.1456 * (t[1] - ((rgb >> 8) & 0xff)) ** 2 +
          0.2166 * (t[2] - (rgb & 0xff)) ** 2
        if (d < bestD) {
          bestD = d
          best = key
        }
      }
      return binToRgb(best)
    }
    const onCentres = new Set(RAMPS.sea.map((c) => snapTo(CORPUS_PALETTE_BINS, c))).size
    const onNative = new Set(RAMPS.sea.map((c) => snapTo(native, c))).size
    expect(
      onNative,
      'the gate-native set no longer resolves the sea ramp better than the bare ' +
        'bin centres — re-measure the claim in ambience.ts before trusting it'
    ).toBeGreaterThan(onCentres)
    expect(onCentres, 'bin centres alone resolve the sea ramp now').toBeLessThan(RAMPS.sea.length)
  })

  it('every colour ambience can emit is one the palette gate calls native', () => {
    // This is what replaced the two veil HUE laws, and it is stronger than both:
    // an output that is a colour the art contains cannot be brighter than the
    // brightest tone the art contains, nor more colourful than the art's most
    // colourful. It is enforced by construction, so the arm is a check that the
    // construction is really in the path.
    const centres = new Set(CORPUS_PALETTE_BINS)
    const bits = PALETTE_QUANT_BITS
    const isNative = (rgb: number) => {
      const r0 = ((rgb >> 16) & 0xff) >> (8 - bits)
      const g0 = ((rgb >> 8) & 0xff) >> (8 - bits)
      const b0 = (rgb & 0xff) >> (8 - bits)
      const rad = PALETTE_NEIGHBOR_RADIUS
      for (let dr = -rad; dr <= rad; dr++) {
        for (let dg = -rad; dg <= rad; dg++) {
          for (let db = -rad; db <= rad; db++) {
            const k = ((r0 + dr) << (2 * bits)) | ((g0 + dg) << bits) | (b0 + db)
            if (centres.has(k)) return true
          }
        }
      }
      return false
    }
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      const foreign = [...new Set(lut)].filter((rgb) => !isNative(rgb))
      expect(
        foreign.map((c) => `#${c.toString(16)}`),
        `${bucket}: ambience can emit colours the gate calls foreign`
      ).toEqual([])
    }
  })

  it('never brightens past the art, and never lands on a reserved signal hue', () => {
    // The one-sided luminance law, restated for a colour map: pixel art has no
    // bloom, so ambience may fall below the ground band and never rise above it.
    // And 0xffc890 is the ADRIFT course line — an ambience that can PRODUCE a
    // state colour destroys that state's salience just as surely as one that
    // paints in it.
    const canvas = readFileSync(
      join(process.cwd(), 'src', 'components', 'world', 'engine-canvas.tsx'),
      'utf8'
    )
    const adrift = [...canvas.matchAll(/'adrift'\s*\n?\s*\?\s*(0x[0-9a-f]{6})/g)].map((m) =>
      Number(m[1])
    )
    expect(adrift.length, 'the adrift course colour was not found — regrep').toBeGreaterThan(0)
    const ceiling = Math.max(...RAMPS.sea.map(luma))
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      for (const seaTone of RAMPS.sea) {
        expect(
          luma(remap(lut, seaTone)),
          `${bucket}: open water came out brighter than the brightest sea tone`
        ).toBeLessThanOrEqual(ceiling)
      }
      for (const hex of adrift) {
        expect([...new Set(lut)], `${bucket}: ambience can emit the adrift signal hue`).not.toContain(
          hex
        )
      }
    }
  })
})

describe('the inverted arm — the mechanism this replaced still fails the law', () => {
  /**
   * A NEW ARM THAT HAS NEVER FAILED IS AN ASSUMPTION. These two cases run the
   * DELETED mechanism — the opaque seeded dither, reproduced here exactly as
   * `veilDots` + the canvas composition performed it at origin/master d9cc1494 —
   * through the arms above, and assert that both still catch it.
   *
   * It is a fixture and not an import on purpose: the production copy is gone, and
   * a live export whose only reader is a test is dead code with a green light over
   * it (ratchets.test.ts ratchet 11 exists for exactly that).
   *
   * Measured here, over the eleven shipped ramps, 12793 flat neighbour pairs:
   *
   *   bucket  coverage   flat pairs split      grain vs the art
   *   dawn      0.08     1805  (14%)                1.47x
   *   dusk      0.16     3448  (27%)                2.00x
   *   night     0.42     7815  (61%)                6.89x
   *
   * Note dawn and dusk. Their HUES were fixed the day before this; the mechanism
   * was still adding half again and double the art's own grain underneath, which
   * no hue law could see.
   */
  const SHIPPED = {
    dawn: { colors: [0x8c8c94, 0xa79c8f], coverage: 0.08 },
    dusk: { colors: [0x7c7c84, 0x6c6c74, 0x4c7c6c], coverage: 0.16 },
    night: { colors: [0x24344c, 0x34344c, 0x2c344c], coverage: 0.42 },
  } as const
  const PATTERN = 320 // PATTERN_TILES * TILE_PX, the veil sprite's tile

  /** terrain-pattern.ts `veilDots` + engine-canvas.tsx's 1px opaque fill. */
  function dither(spec: { colors: readonly number[]; coverage: number }) {
    const cover = new Map<number, number>()
    const salt = `veil:${spec.colors.join('-')}:${spec.coverage}`
    for (let y = 0; y < PATTERN; y++) {
      for (let x = 0; x < PATTERN; x++) {
        const h = fnv1a(`${salt}:${x},${y}`)
        if (h % 1000 < spec.coverage * 1000) {
          cover.set(y * PATTERN + x, spec.colors[(h >>> 12) % spec.colors.length])
        }
      }
    }
    return (px: number, x: number, y: number) =>
      cover.get((y % PATTERN) * PATTERN + (x % PATTERN)) ?? px
  }

  for (const [bucket, spec] of Object.entries(SHIPPED)) {
    it(`${bucket}: the dither splits flat neighbours — arm 1 fires`, () => {
      const paint = dither(spec)
      let flat = 0
      let created = 0
      for (const ramp of Object.values(RAMPS)) {
        const patch = artPatch(ramp)
        const lit = patch.map((row, y) => row.map((px, x) => paint(px, x, y)))
        for (let y = 0; y < patch.length; y++) {
          for (let x = 1; x < patch[y].length; x++) {
            if (patch[y][x] !== patch[y][x - 1]) continue
            flat++
            if (lit[y][x] !== lit[y][x - 1]) created++
          }
        }
      }
      expect(flat).toBeGreaterThan(1000)
      expect(created, `${bucket}: arm 1 no longer detects the dither`).toBeGreaterThan(0)
    })

    it(`${bucket}: the dither raises the art's grain — arm 2 fires`, () => {
      const paint = dither(spec)
      let before = 0
      let after = 0
      for (const ramp of Object.values(RAMPS)) {
        const patch = artPatch(ramp)
        before += textureEnergy(patch)
        after += textureEnergy(patch.map((row, y) => row.map((px, x) => paint(px, x, y))))
      }
      expect(after / before, `${bucket}: arm 2 no longer detects the dither`).toBeGreaterThan(1)
    })
  }
})

describe('the canvas runs this module and nothing else', () => {
  /**
   * THE ARM THAT KEPT THE OLD HUE LAWS BINDING, carried forward. Its first version
   * was a name grep and an adversarial review walked through it four ways in ten
   * minutes: `const VEIL_TABLE` (\b does not fire before `_`), `const veilTable`
   * (case), a ternary at the draw call that declares no table at all, and a COMMENT
   * containing the string the "must call" half searched for. So it is structural:
   * ambience must reach the frame through exactly one call, that call must be fed
   * the bucket, and no colour table may sit in the renderer at all. A local table
   * is then unreachable rather than merely un-grepped.
   */
  const CANVAS = join(process.cwd(), 'src', 'components', 'world', 'engine-canvas.tsx')
  const FILTER = join(process.cwd(), 'src', 'components', 'world', 'ambience-filter.ts')

  it('exactly one ambience call site, fed the bucket', () => {
    const raw = readFileSync(CANVAS, 'utf8')
    const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1')
    const calls = [...src.matchAll(/ambienceFilter\(([^)]*)\)/g)].map((m) => m[1].trim())
    expect(calls, 'engine-canvas.tsx must apply ambience exactly once').toHaveLength(1)
    expect(calls[0]).toBe('bucket, app.renderer')
    expect(src, 'ambienceFilter must be imported, not shadowed locally').toMatch(
      /import\s*\{[^}]*\bambienceFilter\b[^}]*\}\s*from\s*'\.\/ambience-filter'/
    )
  })

  it('no colour table and no dither survives in the renderer', () => {
    const raw = readFileSync(CANVAS, 'utf8')
    const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1')
    // the veil spec's shape, and the deleted dither's name
    expect([...src.matchAll(/\bcolors\s*:\s*\[/g)], 'a veil spec is back in the canvas').toHaveLength(
      0
    )
    expect(src, 'the seeded dither is back in the canvas').not.toMatch(/\bveilDots\b/)
    expect(src, 'ambience must not be re-derived at the call site').not.toMatch(/\bambienceLut\b/)
  })

  it('the filter carries the table and none of the decision', () => {
    // No colour arithmetic in the GPU half: a second opinion about what night
    // looks like, in a file no unit test can execute, is how the dusk hue shipped
    // wrong. The only hex the filter may contain is none.
    const raw = readFileSync(FILTER, 'utf8')
    const src = raw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1')
    expect([...src.matchAll(/0x[0-9a-fA-F]{6}/g)], 'the filter declares colours').toHaveLength(0)
    expect(src, 'the filter must take its table from lib/world/ambience').toMatch(
      /\bambienceLut\b/
    )
  })
})

describe('the ambience derivation', () => {
  it('the depth comes from the shipped ramps, and the ramps are real', () => {
    // Vacuity guard: an empty or stubbed RAMPS makes every arm above pass.
    expect(Object.keys(RAMPS).length).toBeGreaterThanOrEqual(10)
    for (const [name, ramp] of Object.entries(RAMPS)) {
      expect(ramp.length, `${name} is not a ramp`).toBeGreaterThanOrEqual(3)
      expect(luma(ramp[0]), `${name} is not ordered dark->light`).toBeLessThan(
        luma(ramp[ramp.length - 1])
      )
    }
    expect(RAMP_SHADE).toBeGreaterThan(0.5)
    expect(RAMP_SHADE).toBeLessThan(0.8)
  })

  const skyRatio = (bucket: DayBucket) => {
    const ch = (hex: number, s: number) => (hex >> s) & 0xff
    return [
      ch(WINDOW_SKY[bucket], 16) / ch(WINDOW_SKY.day, 16),
      ch(WINDOW_SKY[bucket], 8) / ch(WINDOW_SKY.day, 8),
      ch(WINDOW_SKY[bucket], 0) / ch(WINDOW_SKY.day, 0),
    ]
  }
  const gainOf = (l: readonly number[]) => 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]
  /** worst chroma any shipped ramp colour GAINS under a light factor */
  const worstChromaGain = (l: readonly number[]) => {
    let worst = 0
    for (const ramp of Object.values(RAMPS)) {
      for (const c of ramp) {
        const before = chroma(c)
        if (before < 1) continue
        worst = Math.max(worst, chroma(snapNative(c, l)) / before)
      }
    }
    return worst
  }

  it('the hue direction comes from WINDOW_SKY, and day is the identity', () => {
    expect(ambientLight('day')).toBeNull()
    expect(ambienceLut('day')).toBeNull()
    for (const bucket of LIT) {
      const light = ambientLight(bucket)
      expect(light, `${bucket} has no light factor`).not.toBeNull()
      // the DIRECTION is the sky's: the ordering of the three channel factors
      // survives both the depth clamp and the chroma pull-back, so the tint is
      // still the art's statement about that hour and not a taste.
      const order = (v: readonly number[]) => [0, 1, 2].sort((a, b) => v[a] - v[b]).join('')
      expect(order(light!), `${bucket}: the sky's hue direction was lost`).toBe(
        order(skyRatio(bucket))
      )
    }
    // and light falls monotonically across the day
    expect(gainOf(ambientLight('night')!)).toBeLessThan(gainOf(ambientLight('dusk')!))
    expect(gainOf(ambientLight('dusk')!)).toBeLessThan(gainOf(ambientLight('dawn')!))
    expect(gainOf(ambientLight('dawn')!)).toBeLessThan(1)
  })

  it('the depth is the sky ratio, floored at the art’s own deepest shade', () => {
    for (const bucket of LIT) {
      const want = Math.max(gainOf(skyRatio(bucket)), RAMP_SHADE * RAMP_SHADE)
      expect(gainOf(ambientLight(bucket)!), `${bucket}: wrong depth`).toBeCloseTo(want, 2)
    }
    // the floor binds on NIGHT and only night — the sky says 0.19 there
    expect(gainOf(skyRatio('night'))).toBeLessThan(RAMP_SHADE * RAMP_SHADE)
    expect(gainOf(skyRatio('dusk'))).toBeGreaterThan(RAMP_SHADE * RAMP_SHADE)
    expect(gainOf(skyRatio('dawn'))).toBeGreaterThan(RAMP_SHADE * RAMP_SHADE)
  })

  it('light drains colour: no tint paints harder than a neutral darkening', () => {
    // THE CLAUSE THAT SAVED DUSK. Unbounded, the dusk sky ratio (1.215, 0.740,
    // 0.397) turned open water olive and a grey cobble tone into a 54-chroma
    // orange — a 6.4x chroma gain where a neutral darkening of the same depth
    // costs 1.59. Both ends are arms: the shipped factor is within neutral, and
    // the raw sky ratio is NOT, so the clause is doing work rather than passing.
    for (const bucket of LIT) {
      const light = ambientLight(bucket)!
      const g = gainOf(light)
      const neutral = worstChromaGain([g, g, g])
      expect(
        worstChromaGain(light),
        `${bucket}: the tint makes a surface more colourful than a neutral ` +
          'darkening of the same depth — that is painting, not shading'
      ).toBeLessThanOrEqual(neutral + 1e-9)
    }
    const dusk = skyRatio('dusk')
    const dg = gainOf(dusk)
    expect(
      worstChromaGain(dusk),
      'the raw dusk sky ratio no longer breaks the chroma clause — the clause ' +
        'has stopped doing work, re-measure before trusting it'
    ).toBeGreaterThan(worstChromaGain([dg, dg, dg]))
  })

  it('the derived artifact the Python side reads is this module’s own output', () => {
    /**
     * ONE AUTHORITY FOR THREE CONSUMERS. The renderer is not the only thing that
     * has to know what night looks like: cabinet/scripts/world-capture/
     * live-frame-probe.py judges live PNGs and world-growth-backtest.py paints
     * Pillow timelapse strips, and neither can run TypeScript. Before 2026-07-30
     * both carried their own hand-copied veil hue table, and `change one, change
     * both` was a comment — which is how a third copy of a hue table exists in a
     * repo whose whole finding was that un-reachable hue tables drift.
     *
     * So the TS derivation emits `ambience-derived.json` and both Python
     * consumers read it. This arm is what makes it an artifact rather than a
     * fourth copy: regenerate it with
     *
     *     npx vitest run src/lib/world/ambience.test.ts   # then fix the diff
     *
     * It is checked in because the Python side runs in a CI job with no node.
     */
    const path = join(process.cwd(), 'src', 'lib', 'world', 'ambience-derived.json')
    const got = JSON.parse(readFileSync(path, 'utf8')) as {
      buckets: Record<
        string,
        { light: number[]; sea: number[][]; ramps: Record<string, number[][]> }
      >
    }
    expect(Object.keys(got.buckets).sort()).toEqual([...LIT].sort())
    const rgb = (hex: number) => [(hex >> 16) & 0xff, (hex >> 8) & 0xff, hex & 0xff]
    for (const bucket of LIT) {
      const lut = ambienceLut(bucket)!
      const row = got.buckets[bucket]
      expect(row.light.map((v) => +v.toFixed(6)), `${bucket}: stale light factor`).toEqual(
        ambientLight(bucket)!.map((v) => +v.toFixed(6))
      )
      expect(row.sea, `${bucket}: stale sea ramp`).toEqual(RAMPS.sea.map((c) => rgb(remap(lut, c))))
      expect(Object.keys(row.ramps).sort(), `${bucket}: ramp set changed`).toEqual(
        Object.keys(RAMPS).sort()
      )
      for (const [name, ramp] of Object.entries(RAMPS)) {
        expect(row.ramps[name], `${bucket}/${name}: stale`).toEqual(ramp.map((c) => rgb(remap(lut, c))))
      }
      // vacuity guard: an artifact of empty arrays would satisfy nothing above
      expect(row.sea.length).toBe(RAMPS.sea.length)
      expect(row.sea.flat().some((v) => v > 0)).toBe(true)
    }
  })

  it('the palette mirror still matches the calibration it was cut from', () => {
    // MIRROR, NOT A FORK. corpus-palette.ts is a copy of the gate's own fitted
    // palette; a re-fit that lands in one and not the other silently changes what
    // "native" means for ambience only.
    const cal = JSON.parse(readFileSync(CALIBRATION, 'utf8')) as {
      quant_bits: number
      neighbor_radius: number
      bins: number[]
    }
    expect(PALETTE_QUANT_BITS).toBe(cal.quant_bits)
    expect(PALETTE_NEIGHBOR_RADIUS).toBe(cal.neighbor_radius)
    expect([...CORPUS_PALETTE_BINS]).toEqual([...cal.bins].sort((a, b) => a - b))
  })

  it('the LUT texture payload round-trips every entry', () => {
    // The GPU reads the LUT through this packing, so a wrong slice stride is a
    // silently wrong night with no error anywhere. Check the packing against the
    // table it packs, at every blue slice.
    const lut = ambienceLut('night')!
    const px = lutPixels(lut)
    expect(px.length).toBe(LUT_TEX_W * LUT_TEX_H * 4)
    const levels = 1 << PALETTE_QUANT_BITS
    const perRow = LUT_TEX_W / levels
    let checked = 0
    for (let b = 0; b < levels; b++) {
      for (const [r, g] of [
        [0, 0],
        [1, 7],
        [levels - 1, levels - 1],
        [13, 21],
      ]) {
        const ox = (b % perRow) * levels
        const oy = ((b / perRow) | 0) * levels
        const o = ((oy + g) * LUT_TEX_W + (ox + r)) * 4
        const want = lut[(r << (2 * PALETTE_QUANT_BITS)) | (g << PALETTE_QUANT_BITS) | b]
        expect((px[o] << 16) | (px[o + 1] << 8) | px[o + 2]).toBe(want)
        expect(px[o + 3]).toBe(255)
        checked++
      }
    }
    expect(checked).toBe(levels * 4)
  })
})
