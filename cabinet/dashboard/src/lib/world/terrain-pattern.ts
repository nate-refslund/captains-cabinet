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
