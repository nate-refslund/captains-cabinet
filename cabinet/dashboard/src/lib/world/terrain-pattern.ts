/**
 * TERRAIN PATTERN — deterministic compositor-grade ground/water texture
 * specs (v1a review must-fix: the live engine terrain sat far below the
 * offline compositor bar — near-flat TilingSprites over perfect circles
 * failed PALETTE_FOREIGN_MASS and CLUSTER_FLAT_VOID on every frame).
 *
 * This module is the ENGINE'S port of the proven compose_unified.py
 * three-pass ground painting + wave-dash water (the GREEN offline
 * compositor): base sheet tile + dense seeded speckle/flecks in hues
 * SAMPLED FROM THE SHIPPED LIMEZU SHEETS (palette-native by construction —
 * the aesthetic gate's corpus palette is fitted from these packs).
 *
 * Hue provenance (sampled 2026-07-09 from public/world-assets PNGs with
 * PIL, the same method compose_unified.py uses at run time):
 *   village/Serene_Village_16x16 water tile (192,16): base (80,167,232);
 *   sheet blue family: lite (94,200,252), dark (66,128,221),
 *   deep (64,106,197), foam-white family (226,236,246).
 *   grass tile (64,16): base (118,197,100)/(123,203,105); sheet green
 *   family: dark (86,141,97), mid (112,168,88), lite (184,208,64).
 *
 * PURE + deterministic: every primitive is fnv1a-seeded off (pattern name,
 * tile, index) — two runs emit byte-identical lists (determinism ratchet;
 * no clocks, no Math.random).
 */
import { fnv1a } from './hash'

/** Pattern square size in TILES (renderer bakes once, tiles infinitely). */
export const PATTERN_TILES = 8
export const TILE_PX = 16
export const PATTERN_PX = PATTERN_TILES * TILE_PX

// ── sheet-sampled hues (see provenance block above) ─────────────────────────
export const WATER_BASE = 0x50a7e8 // (80,167,232) — V.water body
/** Sparkle + trough hues re-fitted to the gate's corpus bins 2026-07-09:
 * the raw sheet lite (94,200,252) / deep (64,106,197) quantize OUTSIDE the
 * fitted palette, so the dashes pin the NEAREST in-bin blues instead
 * (calibration/palette.json representatives — palette-legal by check). */
export const WATER_LITE = 0x54dcf4 // (84,220,244) — nearest in-bin sparkle
export const WATER_MID = 0x4c9ce4 // (76,156,228) — in-bin tonal band
export const WATER_DARK = 0x4280dd // (66,128,221)
export const WATER_DEEP = 0x344ca4 // (52,76,164) — nearest in-bin trough
export const FOAM_WHITE = 0xe2ecf6 // (226,236,246)

export const GRASS_FLECK_DARK = 0x568d61 // (86,141,97)
export const GRASS_FLECK_MID = 0x70a858 // (112,168,88)
export const GRASS_FLECK_LITE = 0xb8d040 // (184,208,64)

/** Cozy-density pass hues (2026-07-09) — every one verified against the
 * refit corpus palette (mockups promoted to positives) with the same
 * quantize+neighbor test the gate runs. */
export const GRASS_TONE_MID = 0x6cb25c // (108,178,92) — in-bin green band
export const GRASS_TONE_DARK = 0x609e54 // (96,158,84)
export const DIRT_FLECK_DARK = 0x966c3e // (150,108,62) — worn-path speckle
export const DIRT_FLECK_LITE = 0xdeba82 // (222,186,130)
/**
 * THE VEIL HUE TABLES AND `veilDots` LIVED HERE until 2026-07-30. They were the
 * per-bucket dither the ambience pass used to paint over the frame, and their two
 * laws — no veil hue brighter than the brightest water tone, none more colourful
 * than the water it shades — were correct and are now kept STRUCTURALLY: ambience
 * is a remap into the fitted corpus palette (lib/world/ambience.ts), so every
 * colour it can emit is a colour the art already contains, which no in-bin hue
 * table could guarantee.
 *
 * THE LESSON THOSE LAWS PAID FOR, kept because the gate that missed it is still
 * the gate: dusk shipped as a single 0xffc890 apricot at 16% coverage (luminance
 * 208 over a sea whose brightest tone is 160) and dawn as 0xf2ecde cream at 8%.
 * Both are "in-bin" pixel-by-pixel, so PALETTE_FOREIGN_MASS stayed green — that
 * gate asks whether each pixel is a corpus colour and never whether it is a
 * plausible NEIGHBOUR of the surface it landed on. 15.6% of open water turned
 * apricot at dusk, identically at every zoom, and the ocean read as orange
 * static. 0xffc890 is also the ADRIFT course-line signal, so a sixth of every
 * frame was painted in a reserved salience hue.
 *
 * The whole pass was then replaced for a different reason: an opaque dither buys
 * darkness only by deleting the art's own dither, one for one. See THE AMBIENCE
 * STRUCTURE LAW in lib/world/ambience.ts for the arithmetic and the measurements.
 */
export const GLOW_WARM = 0xffc35c // (255,195,92) — in-bin lamp warmth
export const GLOW_CORE = 0xf2ecde // (242,236,222) — proven CREAM
export const SMOKE_LITE = 0x78747c // (120,116,124) — proven ash greys
export const SMOKE_MID = 0x58545c // (88,84,92)

/** Corpus-native neutrals for far-LOD footprints / silhouettes / buoys
 * (from the palette calibration's own colors_rgb_sample — quantized bins
 * proven present in the fitted corpus). */
export const FOOT_SLATE = 0x3c3c54 // (60,60,84)
export const FOOT_SLATE_2 = 0x44445c // (68,68,92)
export const MIST_GREY = 0x848c9c // (132,140,156)
export const INK_BLACK = 0x040404 // (4,4,4)
export const PLANK_BROWN = 0x7b5b3a // (123,91,58) — farm terrain plank

/** One opaque dash primitive (opaque on purpose: alpha blends can leave
 * the corpus palette; dither is the pack-native texture idiom). */
export interface DashSpec {
  x: number
  y: number
  /** Length in px along +x (1 = single pixel dot). */
  len: number
  /** Height in px (1 or 2). */
  h: number
  color: number
}

/**
 * Tonal wave BANDS for one PATTERN_PX² water pattern — blobby 2×2-tile
 * three-tone variation (base / mid / dark, all in-bin blues). Without it
 * an ocean-heavy archipelago frame collapses into ONE dominant color
 * (CLUSTER dominant_share) no matter how dense the dashes are; the pack's
 * own water bodies carry exactly this kind of tonal banding.
 */
export function waterTones(salt = 'water-v1'): DashSpec[] {
  const out: DashSpec[] = []
  for (let ty = 0; ty < PATTERN_TILES; ty++) {
    for (let tx = 0; tx < PATTERN_TILES; tx++) {
      const h = fnv1a(`${salt}:tone:${tx >> 1},${ty >> 1}`)
      const roll = h % 100
      if (roll < 38) continue // base texture shows through
      out.push({
        x: tx * TILE_PX,
        y: ty * TILE_PX,
        len: TILE_PX,
        h: TILE_PX,
        color: roll < 70 ? WATER_MID : WATER_DARK,
      })
    }
  }
  return out
}

/**
 * Dense wave dashes for one PATTERN_PX² water pattern — the compositor's
 * "no flat 8px block voids" law: 9..13 dashes + 3 ripple ticks per tile.
 */
export function waterDashes(salt = 'water-v1'): DashSpec[] {
  const out: DashSpec[] = []
  for (let ty = 0; ty < PATTERN_TILES; ty++) {
    for (let tx = 0; tx < PATTERN_TILES; tx++) {
      const n = 9 + (fnv1a(`${salt}:${tx},${ty}:n`) % 5)
      for (let i = 0; i < n; i++) {
        const h = fnv1a(`${salt}:${tx},${ty}:${i}`)
        const roll = h % 100
        const color =
          roll < 50 ? WATER_DARK : roll < 86 ? WATER_LITE : roll < 94 ? WATER_DEEP : FOAM_WHITE
        out.push({
          x: tx * TILE_PX + ((h >>> 8) % (TILE_PX - 7)),
          y: ty * TILE_PX + 1 + ((h >>> 16) % (TILE_PX - 3)),
          len: 3 + ((h >>> 24) % 4),
          h: 1,
          color,
        })
      }
      for (let i = 0; i < 3; i++) {
        const h = fnv1a(`${salt}:tick:${tx},${ty}:${i}`)
        out.push({
          x: tx * TILE_PX + (h % (TILE_PX - 2)),
          y: ty * TILE_PX + ((h >>> 12) % (TILE_PX - 1)),
          len: 1,
          h: 1,
          color: (h & 1) === 0 ? WATER_DARK : WATER_LITE,
        })
      }
    }
  }
  return out
}

/**
 * Grass-blade flecks for one PATTERN_PX² grass pattern — 4..7 contrasty
 * 1-2px blades per tile (the compositor's micro-speckle pass; kills the
 * CLUSTER_FLAT_VOID flat_mass on the cleared heart).
 */
export function grassFlecks(salt = 'grass-v1'): DashSpec[] {
  const out: DashSpec[] = []
  for (let ty = 0; ty < PATTERN_TILES; ty++) {
    for (let tx = 0; tx < PATTERN_TILES; tx++) {
      const n = 4 + (fnv1a(`${salt}:${tx},${ty}:n`) % 4)
      for (let i = 0; i < n; i++) {
        const h = fnv1a(`${salt}:${tx},${ty}:${i}`)
        const roll = h % 100
        const color =
          roll < 52 ? GRASS_FLECK_DARK : roll < 84 ? GRASS_FLECK_MID : GRASS_FLECK_LITE
        out.push({
          x: tx * TILE_PX + ((h >>> 8) % (TILE_PX - 1)),
          y: ty * TILE_PX + ((h >>> 16) % (TILE_PX - 2)),
          len: 1,
          h: 1 + ((h >>> 24) % 2),
          color,
        })
      }
    }
  }
  return out
}

/**
 * Grass tonal BANDS (cozy-density #12): blobby 2×2-tile two-tone variation
 * over the cleared heart — the twin of waterTones in in-bin greens. Without
 * it the lawn collapses into one dominant flat mass at coast/archipelago
 * zoom (the v1a live captures' CLUSTER_FLAT_VOID driver on land).
 */
export function grassTones(salt = 'grass-v1'): DashSpec[] {
  const out: DashSpec[] = []
  for (let ty = 0; ty < PATTERN_TILES; ty++) {
    for (let tx = 0; tx < PATTERN_TILES; tx++) {
      // staggered 2×2 cells (row-offset) — axis-aligned cells read as a
      // checkerboard grid; the stagger breaks the alignment into blobs
      const cx = (tx + ((ty >> 1) & 1)) >> 1
      const h = fnv1a(`${salt}:gtone:${cx},${ty >> 1}`)
      const roll = h % 100
      if (roll < 55) continue // base + daubs show through
      // seeded within-cell holes keep the blob organic, never a hard tile
      if (fnv1a(`${salt}:ghole:${tx},${ty}`) % 100 < 18) continue
      out.push({
        x: tx * TILE_PX,
        y: ty * TILE_PX,
        len: TILE_PX,
        h: TILE_PX,
        color: roll < 84 ? GRASS_TONE_MID : GRASS_TONE_DARK,
      })
    }
  }
  return out
}

/**
 * Worn-path speckle for ONE road tile (cozy-density #10t): the compositor's
 * tan_wear pass ported per-tile — dark grain dashes + paired light/dark
 * ticks so the carved dirt spine reads as walked earth, not a flat ribbon.
 * Offsets are relative to the tile's top-left px corner.
 */
export function dirtTileFlecks(tx: number, ty: number): DashSpec[] {
  const out: DashSpec[] = []
  const h0 = fnv1a(`dirtwear:${tx},${ty}`)
  if (h0 % 100 < 85) {
    out.push({
      x: 1 + (h0 % 11),
      y: 1 + ((h0 >>> 8) % 13),
      len: 1 + ((h0 >>> 16) % 4),
      h: 1,
      color: (h0 >>> 4) % 100 < 70 ? DIRT_FLECK_DARK : DIRT_FLECK_LITE,
    })
  }
  const n = 1 + ((h0 >>> 20) % 3)
  for (let i = 0; i < n; i++) {
    const h = fnv1a(`dirtwear:${tx},${ty}:${i}`)
    const x = 2 + (h % 11)
    const y = 2 + ((h >>> 8) % 11)
    out.push({ x, y, len: 1, h: 1, color: DIRT_FLECK_LITE })
    out.push({ x: x + 1, y, len: 1, h: 1, color: DIRT_FLECK_DARK })
  }
  return out
}

/**
 * Object drop shadow (cozy-density #13 — the single biggest flat-vs-cozy
 * delta after night): OPAQUE corpus-slate dither in a half-ellipse under an
 * anchor. Never an alpha blend (blends leave the fitted palette); the
 * mist-dots opaque-dither idiom is the lawful texture primitive. Offsets
 * are px relative to the anchor (sprite foot center).
 */
export function shadowDots(
  id: string,
  wPx: number
): Array<{ x: number; y: number; r: number }> {
  const out: Array<{ x: number; y: number; r: number }> = []
  const rx = Math.max(4, Math.floor(wPx / 2))
  const ry = Math.max(2, Math.floor(rx / 3))
  const n = Math.max(10, Math.floor(rx * ry * 0.9))
  for (let i = 0; i < n; i++) {
    const h = fnv1a(`shadow:${id}:${i}`)
    const dx = (h % (rx * 2 + 1)) - rx
    const dy = ((h >>> 10) % (ry * 2 + 1)) - ry
    // inside the ellipse only; seeded holes keep it a dither, not a blob
    const d2 = (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry)
    if (d2 > 1 || (h >>> 20) % 100 < 30) continue
    out.push({ x: dx, y: dy, r: 1 + ((h >>> 26) % 2) })
  }
  return out
}

/**
 * Wave rings around a fixed water anchor (cozy-density #7r): 2–3 broken
 * concentric arc dashes in in-bin blues — pier posts and the moored boat
 * sit IN the water, not on it. Pure f(id); px offsets relative to anchor.
 */
export function waveRingDashes(id: string): DashSpec[] {
  const out: DashSpec[] = []
  const h0 = fnv1a(`ring:${id}`)
  const rings = 2 + (h0 % 2)
  for (let ri = 0; ri < rings; ri++) {
    const r = 4 + ri * 4
    const segs = 5 + ri * 2
    for (let s = 0; s < segs; s++) {
      const h = fnv1a(`ring:${id}:${ri}:${s}`)
      if (h % 100 < 25) continue // broken arcs, never full circles
      const a = ((s + (h % 3) * 0.2) / segs) * Math.PI * 2
      out.push({
        x: Math.round(Math.cos(a) * r),
        y: Math.round(Math.sin(a) * r * 0.55),
        len: 2 + (h >>> 8) % 3,
        h: 1,
        color: (h >>> 4) % 100 < 60 ? WATER_LITE : FOAM_WHITE,
      })
    }
  }
  return out
}

/**
 * Chimney smoke puffs (cozy-density #14): tick-driven seeded drift over a
 * lived-in chimney. Opaque proven ash greys (compose_unified smoke family),
 * 1–3px puffs rising + drifting east, phase seeded per building. Pure
 * f(id, tick) — freezes with the killswitch tick like all life.
 */
export function smokePuffs(
  id: string,
  tick: number
): Array<{ x: number; y: number; r: number; color: number }> {
  const out: Array<{ x: number; y: number; r: number; color: number }> = []
  const phase = fnv1a(`smoke:${id}`) % 97
  for (let i = 0; i < 4; i++) {
    const t = (tick / 2 + phase + i * 11) % 44
    if (t > 34) continue // gap between puff trains
    const h = fnv1a(`smoke:${id}:${i}`)
    out.push({
      x: Math.round(t * 0.35 + ((h % 3) - 1)),
      y: -Math.round(t * 0.8),
      r: t < 8 ? 1 : t < 22 ? 2 : 3,
      color: t < 18 ? SMOKE_MID : SMOKE_LITE,
    })
  }
  return out
}

/**
 * GROWTH-FOG horizon band (cozy-density #3 / spec §2.4 "mist beyond"):
 * dithered OPAQUE dashes in corpus mist hues across the unmeasured sea
 * south of the earned world — density ramps toward the horizon exactly
 * like the egg compositor's mist_band. Derived from the SAME growth
 * geometry (the band starts below the grown coastline), so the fog
 * recedes as the world grows — true by construction. Returns dashes in
 * WORLD-TILE space (caller multiplies by TILE px).
 */
export function mistBandDashes(
  y0Tile: number,
  y1Tile: number,
  x0Tile: number,
  x1Tile: number,
  salt = 'mist-band'
): DashSpec[] {
  const out: DashSpec[] = []
  const rows = Math.max(1, y1Tile - y0Tile)
  for (let ty = y0Tile; ty <= y1Tile; ty++) {
    const f = (ty - y0Tile) / rows
    const nRow = Math.round(1 + f * 7)
    for (let tx = x0Tile; tx <= x1Tile; tx++) {
      for (let i = 0; i < nRow; i++) {
        const h = fnv1a(`${salt}:${tx},${ty}:${i}`)
        out.push({
          x: tx * TILE_PX + (h % (TILE_PX - 8)),
          y: ty * TILE_PX + ((h >>> 8) % (TILE_PX - 1)),
          len: 3 + ((h >>> 16) % 6),
          h: 1,
          color: (h >>> 24) % 100 < 55 ? MIST_GREY : FOAM_WHITE,
        })
      }
    }
  }
  return out
}

/**
 * Mist dither dots for a reserved-slot pocket — OPAQUE corpus grey dither
 * (replaces the alpha-blended dots whose blends left the palette).
 */
export function mistDots(slot: number): Array<{ x: number; y: number; r: number }> {
  const out: Array<{ x: number; y: number; r: number }> = []
  const h0 = fnv1a(`mist:${slot}`)
  for (let i = 0; i < 30; i++) {
    const a = (((h0 >>> (i % 24)) + i * 37) % 360) * (Math.PI / 180)
    const rr = (fnv1a(`mist:${slot}:${i}`) % 60) + 12
    out.push({
      x: Math.cos(a) * rr,
      y: Math.sin(a) * rr,
      r: 1 + (fnv1a(`mist:${slot}:r:${i}`) % 2),
    })
  }
  return out
}
