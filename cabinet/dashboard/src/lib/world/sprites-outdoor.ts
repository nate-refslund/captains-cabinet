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
  CHARACTER_DIR,
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
  (_, i) => `${CHARACTER_DIR}/Premade_Character_${String(i + 1).padStart(2, '0')}`
)

// ── street kit (whole-file singles; dims pinned from the manifest gate) ────
const STREET = (n: string) => `exteriors/street/${n}`

export const STREET_PROPS = {
  bench: STREET('ME_Singles_City_Props_16x16_Bench_1'),
  boat: STREET('ME_Singles_Vehicles_16x16_Boat_1_Down_1'),
  mailbox: 'exteriors/22_Post_Office_16x16_Big_Blue_Mailbox',
} as const


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

// ── COZY-DENSITY pass bindings (2026-07-09) ────────────────────────────────
// The approved 7.5 mockups are now the harness's positive class; these
// bindings close the density gap with the SAME pack pixels the mockups
// were composed from (installer `cozy` section). Cut provenance: farm
// terrain/animal coords ported 1:1 from the ratified compose_unified.py
// recipes (GRASS (3,2) · GVAR (8,8) · chicken rows idle/walk/peck at
// y=16/32/48 · dog sleep row y=384) — the mockups' own verified cuts.

/** The mockups' ground truth: farm terrain sheet (three-pass ground). */
export const FARM_TER = 'farm/1_Terrains_16x16'
export const TER_GRASS: SpriteCut = { x: 48, y: 32, w: 16, h: 16 }
export const TER_GVAR: SpriteCut = { x: 128, y: 128, w: 16, h: 16 }
/** 4 grass variant daubs recomposed to a strip (derived, pack pixels). */
export const GRASS_VARIANTS = 'derived/terrain/grass_variants'
export const GRASS_VARIANT_CUTS: readonly SpriteCut[] = [0, 1, 2, 3].map(
  (i) => ({ x: i * 16, y: 0, w: 16, h: 16 })
)

/** Grass tuft/flower decal singles (the mockup meadow's accent set). */
export const TUFT_SHEETS = Array.from(
  { length: 11 },
  (_, i) => `farm/tufts/Grass_Tufts_Flowers_16x16_${i + 1}`
)

/** Outdoor decor singles (all whole-file; quay/yard/forest-edge dressing). */
export const DECOR_PROPS = {
  boxSingle: 'farm/props/Box_Single_16x16',
  boxLoad: 'farm/props/Box_Load_16x16',
  trunkBig1: 'farm/props/Trunk_Big_1_16x16',
  trunkBig2: 'farm/props/Trunk_Big_2_16x16',
  trunkSmall: 'farm/props/Trunk_Small_1_16x16',
  hayPile: 'farm/props/Hay_Dry_Pile_16x16',
  haySmall: 'farm/props/Hay_Dry_Pile_Small_16x16',
  boardLoad: 'farm/props/Wood_Board_Load_16x16',
  rockSmall: 'farm/props/Rock_Small_16x16',
  rockMedium: 'farm/props/Rock_Medium_16x16',
  rockBig: 'farm/props/Rock_Big_16x16',
  barrel1: 'exteriors/harbor/ME_Singles_Camping_16x16_Pier_Barrel_1',
  barrel2: 'exteriors/harbor/ME_Singles_Camping_16x16_Pier_Barrel_2',
} as const

/** lantern_posts ladder art: the forged era torch post (dark/lit). */
export const TORCH_UNLIT = 'derived/props/torch_post_unlit'
export const TORCH_LIT = 'derived/props/torch_post_lit'

/** Fauna sheets (grammar fauna block: staged flipped OFF in this same
 * commit — dog, chicken_flock, fish now render). */
export const DOG_SHEET = 'farm/animals/Dog_Labrador_Brown_16x16'
export const CHICKEN_SHEETS = [
  'farm/animals/Chicken_Brown_16x16',
  'farm/animals/Chicken_White_16x16',
]
export const FISH_SHEET = 'derived/props/fish_leap2'
export const FISH_CUTS: readonly SpriteCut[] = [
  { x: 0, y: 0, w: 16, h: 16 },
  { x: 16, y: 0, w: 16, h: 16 },
]
/** Dog sleep frames (compose_unified dog_sleep: 48×32 at y=384). */
export function dogSleepCut(i: number): SpriteCut {
  return { x: (i % 2) * 48, y: 384, w: 48, h: 32 }
}
/** Chicken frames (compose_unified chick recipe: rows idle/walk/peck). */
export function chickenCut(anim: 'idle' | 'walk' | 'peck', i: number): SpriteCut {
  const y = anim === 'idle' ? 16 : anim === 'walk' ? 32 : 48
  return { x: (i % 6) * 16, y, w: 16, h: 16 }
}

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

/**
 * The scenes a caller may bind a sheet universe for.
 *
 * It was `'street' | 'island'`. The street scene belonged to the legacy
 * three-scene shell (`outdoor-canvas.tsx`, deleted 2026-07-29 with the rest of
 * that shell), and the engine has only ever bound `'island'`. Leaving the arm
 * behind would have kept ~28 licensed street sheets in a required set no
 * renderer can select — a loud-failure universe for a scene that cannot be
 * drawn, which is the same defect as a check with no subject.
 */
export type OutdoorScene = 'island'

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
export function requiredOutdoorSheets(_scene: OutdoorScene = 'island'): string[] {
  return [
    VILLAGE_SHEET,
    FARM_SHEET,
    ...CROP_SHEETS,
    STREET_PROPS.boat,
    STREET_PROPS.mailbox,
    // T1 engine additions (v1a review fixes): the recomposed lighthouse,
    // the staged-vocab worksite kit, era water store, officer characters
    // (real sprites at island/mid/close — Captain's E1 headline; the owned
    // actor_officer family since the 2026-07-28 flip),
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
    // cozy-density pass (2026-07-09): mockup-lineage ground + dressing +
    // first fauna art — same loud-failure contract as every sheet above.
    FARM_TER,
    GRASS_VARIANTS,
    ...TUFT_SHEETS,
    ...Object.values(DECOR_PROPS),
    STREET_PROPS.bench,
    TORCH_UNLIT,
    TORCH_LIT,
    DOG_SHEET,
    ...CHICKEN_SHEETS,
    FISH_SHEET,
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
  [FARM_TER]: [TER_GRASS, TER_GVAR],
  [GRASS_VARIANTS]: [...GRASS_VARIANT_CUTS],
  [DOG_SHEET]: [dogSleepCut(0), dogSleepCut(1)],
  [CHICKEN_SHEETS[0]]: [chickenCut('idle', 0), chickenCut('peck', 5)],
  [CHICKEN_SHEETS[1]]: [chickenCut('idle', 0), chickenCut('peck', 5)],
  [FISH_SHEET]: [...FISH_CUTS],
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
  scene: OutdoorScene,
  /**
   * The ids to resolve, when the caller knows better than the scene default.
   *
   * THE DEFECT THIS PARAMETER EXISTS FOR, measured in a browser 2026-07-29 on
   * the iso default: the canvas fetched the ENTIRE top-down LimeZu sheet
   * universe — farm, exteriors, office, village, derived — and drew none of it.
   * The iso pack's own load is gated on `isIso`; this one never was, so the
   * asymmetry read as deliberate and was not. 56 requests on a clone without
   * the gitignored binaries; on a real deployment, 56 successful loads of art
   * the kernel cannot put on screen.
   *
   * It also made `credit.ts` wrong in the direction that matters: that module
   * says the iso canvas binds the owned atlas and the cast and nothing else,
   * and computes the licence notice from exactly that claim. The loader
   * disagreed. Passing `canvasAssetIds(projection)` makes the credit module
   * the ONE authority for what a kernel binds — the notice and the network
   * requests now come from the same list, so they cannot drift apart again.
   */
  ids?: readonly string[]
): ResolvedOutdoor {
  const byId = new Map(manifest.assets.map((r) => [r.id, r]))
  const urls: Record<string, string> = {}
  const missing: string[] = []
  for (const id of ids ?? requiredOutdoorSheets(scene)) {
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
    if (id.startsWith(`${CHARACTER_DIR}/`)) {
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
