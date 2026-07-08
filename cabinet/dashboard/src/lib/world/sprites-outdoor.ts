/**
 * Outdoor sprite resolution — Z1 street + Z0 island (world-alive §3, T3).
 *
 * Same doctrine as sprites.ts (the Wardroom binder):
 *  - Every sheet resolves ONLY through the content-addressed manifest
 *    (public/world-assets/manifest.json, gated by world-asset-gate.py). No
 *    URL is ever constructed from anything but a manifest row's path.
 *  - Configured-but-dead must be LOUD: `resolveOutdoorSprites` reports every
 *    required-but-absent (or dimension-invalid) sheet in `missing`, feeding
 *    the SAME onIssues → DOM badge chain (ratchets #8/#9 pattern extends to
 *    every new asset class — the loud-failure contract).
 *  - Determinism: cut choices key on fnv1a(stableId) only; no clocks here.
 *
 * Every pixel cut below was verified visually on 2026-07-08 with the same
 * grid-overlay method the sprites.ts header documents (4x sips crops of the
 * shipped PNGs — Serene_Village 304x720, farm props 512x2240, crop strips
 * 112xN). Bases/sheet geometry are facts of the LimeZu packs, recorded here
 * as constants so the renderer never guesses.
 */
import type { ManifestRow, SpriteCut, WorldAssetManifest } from './sprites'
import { ASSET_BASE } from './sprites'

// ── street kit (whole-file singles; dims pinned from the manifest gate) ────
const STREET = (n: string) => `exteriors/street/${n}`

export const ASPHALT_SHEETS = [
  STREET('ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_1'),
  STREET('ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_4'),
  STREET('ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_7'),
  STREET('ME_Singles_City_Terrains_16x16_Asphalt_1_Variation_12'),
]
export const SIDEWALK_SHEETS = [
  STREET('ME_Singles_City_Terrains_16x16_Sidewalk_1_1'),
  STREET('ME_Singles_City_Terrains_16x16_Sidewalk_1_2'),
]
export const STREET_PROPS = {
  lamp1: STREET('ME_Singles_City_Props_16x16_Street_Lamp_1'),
  lamp2: STREET('ME_Singles_City_Props_16x16_Street_Lamp_2'),
  bench: STREET('ME_Singles_City_Props_16x16_Bench_1'),
  hydrant: STREET('ME_Singles_City_Props_16x16_Hydrant_1'),
  trash: STREET('ME_Singles_City_Props_16x16_Black_Closed_Trash_Can'),
  tree1: STREET('ME_Singles_City_Props_16x16_Tree_1'),
  tree2: STREET('ME_Singles_City_Props_16x16_Tree_2'),
  carLeft: STREET('ME_Singles_Vehicles_16x16_Car_Left_1'),
  carRight: STREET('ME_Singles_Vehicles_16x16_Car_Right_1'),
  boat: STREET('ME_Singles_Vehicles_16x16_Boat_1_Down_1'),
  airDuct: STREET('ME_Singles_Office_16x16_Air_Duct_1_Roof_Prop'),
  sign: STREET('ME_Singles_Office_16x16_Building_Sign_1'),
  mailbox: 'exteriors/22_Post_Office_16x16_Big_Blue_Mailbox',
} as const

/** HQ modular building — one Middle_Floor per commits tier (§3.1). */
export const HQ_GROUND = STREET('ME_Singles_Floor_Modular_Building_16x16_Ground_Floor_Shop_1')
export const HQ_MIDDLE_FLOORS = [
  STREET('ME_Singles_Floor_Modular_Building_16x16_Middle_Floor_1'),
  STREET('ME_Singles_Floor_Modular_Building_16x16_Middle_Floor_5'),
  STREET('ME_Singles_Floor_Modular_Building_16x16_Middle_Floor_9'),
]
export const HQ_ROOF = STREET('ME_Singles_Floor_Modular_Building_16x16_Roof_1')
export const NEIGHBOR_GROUND = [
  STREET('ME_Singles_Floor_Modular_Building_16x16_Ground_Floor_Condo_1'),
  STREET('ME_Singles_Floor_Modular_Building_16x16_Ground_Floor_Bakery_1'),
]
export const NEIGHBOR_ROOF = [
  STREET('ME_Singles_Floor_Modular_Building_16x16_Roof_2'),
  STREET('ME_Singles_Floor_Modular_Building_16x16_Roof_5'),
]
/** Modular prefab geometry (px): all pieces are 112 wide = 7 tiles. */
export const MODULAR_W = 112
export const GROUND_H = 48
export const MIDDLE_H = 64
export const ROOF_H = 96

// ── village sheet cuts (Serene_Village_16x16, 304x720) ─────────────────────
export const VILLAGE_SHEET = 'village/Serene_Village_16x16'
export const V = {
  grass: { x: 64, y: 16, w: 16, h: 16 } as SpriteCut,
  dirt: { x: 96, y: 32, w: 16, h: 16 } as SpriteCut,
  water: { x: 192, y: 16, w: 16, h: 16 } as SpriteCut,
  sand: { x: 272, y: 56, w: 16, h: 16 } as SpriteCut,
  pebbles: { x: 16, y: 48, w: 16, h: 16 } as SpriteCut, // transparent decal
  /** Gabled cottage, roof palettes seeded per slug (§3.2 residential W). */
  cottage: [
    { x: 99, y: 336, w: 56, h: 59 } as SpriteCut, // red
    { x: 99, y: 464, w: 56, h: 59 } as SpriteCut, // green
    { x: 99, y: 592, w: 56, h: 59 } as SpriteCut, // blue
  ],
  /** The HQ large cottage (red, side wing) — click → Z1. */
  hq: { x: 165, y: 336, w: 70, h: 60 } as SpriteCut,
  treeRow: { x: 144, y: 154, w: 128, h: 38 } as SpriteCut,
  treeRow2: { x: 144, y: 245, w: 128, h: 43 } as SpriteCut,
  hedge: { x: 96, y: 128, w: 32, h: 32 } as SpriteCut,
  /** Stone-fenced plot with gate — Law N (the Keep-to-be anchor). */
  lawPlot: { x: 2, y: 117, w: 91, h: 59 } as SpriteCut,
  signpost: { x: 4, y: 212, w: 24, h: 28 } as SpriteCut,
  flowerbed: { x: 33, y: 194, w: 14, h: 13 } as SpriteCut,
  rock: { x: 3, y: 298, w: 24, h: 22 } as SpriteCut,
  pier: { x: 196, y: 53, w: 48, h: 34 } as SpriteCut,
  dock: { x: 192, y: 96, w: 48, h: 16 } as SpriteCut,
}

// ── farm sheet cuts (3_Props_and_Buildings_16x16, 512x2240) ────────────────
export const FARM_SHEET = 'farm/3_Props_and_Buildings_16x16'
export const F = {
  /** THE dark beacon (interim silo sprite; unlit until cells_graduated>0). */
  silo: { x: 432, y: 1368, w: 78, h: 232 } as SpriteCut,
  barn: { x: 56, y: 948, w: 128, h: 124 } as SpriteCut,
  kilnShed: { x: 250, y: 88, w: 66, h: 88 } as SpriteCut,
  furnace: { x: 428, y: 236, w: 42, h: 60 } as SpriteCut,
  well: { x: 384, y: 132, w: 32, h: 30 } as SpriteCut,
  stall: { x: 188, y: 304, w: 48, h: 40 } as SpriteCut,
  scarecrow: { x: 0, y: 130, w: 40, h: 46 } as SpriteCut,
  crate: { x: 444, y: 107, w: 18, h: 17 } as SpriteCut,
  crate2: { x: 444, y: 107, w: 18, h: 32 } as SpriteCut, // stacked pair
}

// ── crop growth strips (7 stages × 16px wide; label band excluded) ─────────
export const CROP_SHEETS = [
  'farm/crops/Wheat_Growth_Stages_16x16',
  'farm/crops/Corn_Growth_Stages_16x16',
  'farm/crops/Pumpkin_Growth_Stages_16x16',
  'farm/crops/Strawberry_Growth_Stages_16x16',
]
export const CROP_STAGES = 7
/** Sprite height per strip: short strips (h=32) 18px, tall (h=64) 33px. */
export function cropCut(sheetH: number, stage: number): SpriteCut {
  const s = Math.max(0, Math.min(CROP_STAGES - 1, stage))
  return { x: s * 16, y: 0, w: 16, h: sheetH >= 64 ? 33 : 18 }
}

/** Muted per-slug mote color — same palette band as the Wardroom placeholder
 * markers (away from every reserved salience hue; zero information). */
export function moteColor(h: number): number {
  const r = 90 + (h % 90)
  const g = 90 + ((h >> 8) % 90)
  const b = 120 + ((h >> 16) % 100)
  return (r << 16) | (g << 8) | b
}

export type OutdoorScene = 'street' | 'island'

// ── pure scene dynamics (shared by renderer + tests; NO clocks here) ──────

/** Day/night bucket from the SERVER-stamped snapshot clock (§2 lighting).
 * The render path never reads a wall clock — hour arrives as data. */
export type DayBucket = 'dawn' | 'day' | 'dusk' | 'night'
export function bucketOf(hour: number | null): DayBucket {
  if (hour === null || !Number.isFinite(hour)) return 'day'
  if (hour >= 6 && hour < 8) return 'dawn'
  if (hour >= 8 && hour < 18) return 'day'
  if (hour >= 18 && hour < 21) return 'dusk'
  return 'night'
}

/** Street badge-mote patrol: pure triangle-wave drift (4 ticks per tile)
 * while the officer's verb is live; seeded phase, deterministic forever. */
export function motePatrolX(
  baseX: number,
  span: number,
  phase: number,
  tick: number
): number {
  const period = span * 8 // out and back, 4 ticks per tile
  const p = (tick + phase) % (2 * period)
  const t = p < period ? p : 2 * period - p
  return baseX - span + t / 4
}

/** Every sheet a scene may draw (loud-failure universe per scene). */
export function requiredOutdoorSheets(scene: OutdoorScene): string[] {
  if (scene === 'street') {
    return [
      ...ASPHALT_SHEETS,
      ...SIDEWALK_SHEETS,
      ...Object.values(STREET_PROPS),
      HQ_GROUND,
      ...HQ_MIDDLE_FLOORS,
      HQ_ROOF,
      ...NEIGHBOR_GROUND,
      ...NEIGHBOR_ROOF,
    ]
  }
  return [
    VILLAGE_SHEET,
    FARM_SHEET,
    ...CROP_SHEETS,
    STREET_PROPS.boat,
    STREET_PROPS.mailbox,
  ]
}

/** Cuts taken from multi-sprite sheets, for dimension validation. */
const SHEET_CUTS: Record<string, SpriteCut[]> = {
  [VILLAGE_SHEET]: [
    V.grass, V.dirt, V.water, V.sand, V.pebbles, ...V.cottage, V.hq,
    V.treeRow, V.treeRow2, V.hedge, V.lawPlot, V.signpost, V.flowerbed,
    V.rock, V.pier, V.dock,
  ],
  [FARM_SHEET]: [
    F.silo, F.barn, F.kilnShed, F.furnace, F.well, F.stall, F.scarecrow,
    F.crate, F.crate2,
  ],
}

function cutFits(row: ManifestRow, cut: SpriteCut): boolean {
  return cut.x + cut.w <= row.w && cut.y + cut.h <= row.h
}

export interface ResolvedOutdoor {
  urls: Record<string, string>
  missing: string[]
}

/**
 * Bind a scene's sheet universe against the manifest. Absent rows and rows
 * that cannot contain the cuts we take from them land in `missing` — the
 * renderer badges them and draws visibly-placeholder geometry instead
 * (never fake art, never invisible).
 */
export function resolveOutdoorSprites(
  manifest: WorldAssetManifest,
  scene: OutdoorScene
): ResolvedOutdoor {
  const byId = new Map(manifest.assets.map((r) => [r.id, r]))
  const urls: Record<string, string> = {}
  const missing: string[] = []
  for (const id of requiredOutdoorSheets(scene)) {
    const row = byId.get(id)
    if (!row) {
      missing.push(id)
      continue
    }
    let ok = true
    for (const cut of SHEET_CUTS[id] ?? []) {
      if (!cutFits(row, cut)) ok = false
    }
    if (id.startsWith('farm/crops/')) {
      ok = row.w >= CROP_STAGES * 16 && row.h >= 18
    }
    if (!ok) {
      missing.push(id)
      continue
    }
    urls[id] = ASSET_BASE + row.path
  }
  return { urls, missing }
}
