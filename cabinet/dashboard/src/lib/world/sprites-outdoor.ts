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
import {
  ASSET_BASE,
  CHARACTER_COUNT,
  CHAR_SHEET_MIN_H,
  CHAR_SHEET_MIN_W,
  DESK_SHEETS,
  FLOOR_CUT,
  ROOM_SHEET,
  WALL_CUT,
} from './sprites'

/** The 20 premade character sheets (same universe the Wardroom binds —
 * characterSheetFor picks per slug; the engine draws walk/idle frames). */
export const ENGINE_CHARACTER_SHEETS = Array.from(
  { length: CHARACTER_COUNT },
  (_, i) => `characters/Premade_Character_${String(i + 1).padStart(2, '0')}`
)

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

// ── corpus tree canon (farm pack 6_Trees — the SAME trees the aesthetic
//    gate's palette positives were composed from; the Serene tree-row
//    strips measured ~11% palette-foreign per pixel and are retired from
//    the forest border) ─────────────────────────────────────────────────────
export const FARM_TREES = 'farm/6_Trees_16x16'
/** Verified 2026-07-09 (compose_unified TREECUTS ×16px; pines excluded —
 * their strips clip into neighboring sprites). */
export const TREE_CUTS: readonly SpriteCut[] = [
  { x: 0, y: 64, w: 48, h: 80 }, // oakS
  { x: 64, y: 48, w: 64, h: 96 }, // oakM
  { x: 128, y: 32, w: 80, h: 112 }, // oakL
]

// ── lighthouse pack (21_Beach — the RECOMPOSED tower, Captain ruling
//    2026-07-09: the lamp must fit the tower, NEVER the water-tank/silo
//    body; supersedes the interim F.silo beacon). The bound sheets are the
//    ratified t4 DERIVED variants (forge section of world-asset-install:
//    unlit = honest-zero; lit = lamp-room glass remapped to the proven warm
//    hue — swapped in ONLY when cells_graduated > 0). ──────────────────────
export const LIGHTHOUSE_SHEET = 'derived/lighthouse/lighthouse_unlit'
export const LIGHTHOUSE_LIT_SHEET = 'derived/lighthouse/lighthouse_lit'
/** Sheet geometry (verified 2026-07-09, grid-overlay method): 112x256 —
 * red/white banded tower, lamp gallery + red dome cap, door at the base. */
export const LIGHTHOUSE_FULL: SpriteCut = { x: 0, y: 0, w: 112, h: 256 }
/** Bottom 176px: banded body up to the gallery deck (tower_part rung). */
export const LIGHTHOUSE_PART: SpriteCut = { x: 0, y: 80, w: 112, h: 176 }
/** Bottom 96px: rounded masonry base + door (stone_base rung). */
export const LIGHTHOUSE_BASE: SpriteCut = { x: 0, y: 160, w: 112, h: 96 }

/**
 * Growth-ladder rung → lighthouse composition (ladder `lighthouse`, rungs
 * dark_cairn → stone_base → tower_part → tower_full). dark_cairn returns
 * null: the renderer composes the shore-rock cairn from V.rock (morphology
 * day0 "dark cairn on the shore rock"). The lamp overlay is a SEPARATE
 * element (lighthouse_lamp flag) — unlit until cells_graduated > 0.
 */
export function lighthouseCutFor(rungName: string): SpriteCut | null {
  if (rungName === 'stone_base') return LIGHTHOUSE_BASE
  if (rungName === 'tower_part') return LIGHTHOUSE_PART
  if (rungName === 'tower_full') return LIGHTHOUSE_FULL
  return null // dark_cairn / unknown → rock cairn composition
}

// ── worksite kit (staged-vocab markers + T2 construction sites) ────────────
const WORKSITE = (n: string) => `exteriors/worksite/ME_Singles_Worksite_16x16_${n}`
export const WORKSITE_KIT = {
  sign: WORKSITE('Sign_2'), // 16x48 round sign on post
  fenceA: WORKSITE('Fence_1_1'), // 16x32 striped barrier
  fenceB: WORKSITE('Fence_1_2'),
  ground: WORKSITE('Ground_1_1'), // 16x16 cleared-earth patch
  mounds: WORKSITE('Props_7'), // 48x16 dirt mounds
  cone: WORKSITE('Cone_2'), // 16x32
} as const

/** Era-appropriate water store: stacked buckets (farm props pack). */
export const BUCKET_LOAD = 'farm/props/Bucket_Load_16x16'

/** Elements whose era-vocab art is STAGED: the renderer draws the honest
 * worksite marker (fences + sign + cleared earth) instead of a wrong-object
 * substitution (v1a review: library→market-stall / observatory→signpost
 * dragged the era read below bar; markers are honest until proper art). */
export const STAGED_VOCAB_ELEMENTS: ReadonlySet<string> = new Set([
  'library',
  'observatory',
])

// ── commute bubble verb icons (Modern UI pack, grammar v3 bubble law:
//    PIXEL bubble carrying the verb's ICON — never text in world space).
//    Cuts verified visually 2026-07-09 (8x crops of the shipped sheet). ──
export const UI_SHEET = 'ui/16x16/Modern_UI_Style_1'
export const VERB_ICONS = {
  gear: { x: 465, y: 99, w: 14, h: 11 } as SpriteCut, // work-class default
  mail: { x: 433, y: 131, w: 14, h: 12 } as SpriteCut, // replying
  people: { x: 448, y: 99, w: 15, h: 11 } as SpriteCut, // coordinating
  up: { x: 497, y: 114, w: 13, h: 11 } as SpriteCut, // deploying/shipping
} as const

/** Closed verb → icon mapping (keys align with commute VERB_GLOSS). */
export function verbIconCut(verb: string): SpriteCut {
  if (verb === 'replying') return VERB_ICONS.mail
  if (verb === 'coordinating') return VERB_ICONS.people
  if (verb === 'deploying' || verb === 'shipping') return VERB_ICONS.up
  return VERB_ICONS.gear
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
    // T1 engine additions (v1a review fixes): the recomposed lighthouse,
    // the staged-vocab worksite kit, era water store, officer characters
    // (real LimeZu sprites at island/mid/close — Captain's E1 headline),
    // and the cutaway interior kit (floor/wall + desks).
    LIGHTHOUSE_SHEET,
    LIGHTHOUSE_LIT_SHEET,
    FARM_TREES,
    ...Object.values(WORKSITE_KIT),
    BUCKET_LOAD,
    ...ENGINE_CHARACTER_SHEETS,
    ROOM_SHEET,
    ...DESK_SHEETS,
    UI_SHEET,
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
  [LIGHTHOUSE_SHEET]: [LIGHTHOUSE_FULL, LIGHTHOUSE_PART, LIGHTHOUSE_BASE],
  [LIGHTHOUSE_LIT_SHEET]: [LIGHTHOUSE_FULL],
  [FARM_TREES]: [...TREE_CUTS],
  [ROOM_SHEET]: [FLOOR_CUT, WALL_CUT],
  [UI_SHEET]: Object.values(VERB_ICONS),
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
    if (id.startsWith('characters/')) {
      ok = row.w >= CHAR_SHEET_MIN_W && row.h >= CHAR_SHEET_MIN_H
    }
    if (DESK_SHEETS.includes(id)) {
      ok = row.w === 32 && row.h === 48 // office singles canvas
    }
    if (!ok) {
      missing.push(id)
      continue
    }
    urls[id] = ASSET_BASE + row.path
  }
  return { urls, missing }
}
