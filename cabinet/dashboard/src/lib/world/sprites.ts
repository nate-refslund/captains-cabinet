/**
 * Wardroom sprite resolution — PURE manifest→sprite binding (E1, LimeZu).
 *
 * Doctrine:
 *  - Every sheet the renderer may load MUST resolve through the
 *    content-addressed manifest (public/world-assets/manifest.json, gated by
 *    cabinet/scripts/world-asset-gate.py). No URL is ever constructed from
 *    anything but a manifest row's path.
 *  - Configured-but-dead must be LOUD: `resolveWorldSprites` returns every
 *    required-but-absent (or dimension-invalid) sheet id in `missing` so the
 *    renderer can badge + console.error them — a silent empty draw is the
 *    recorded failure mode (2026-07-08 black-canvas incident).
 *  - Determinism: sheet/frame choices key on fnv1a(slug) + the logical tick
 *    only (CI ratchet greps this tree for Math.random / Date.now).
 *
 * Sheet geometry facts below were verified visually against the LimeZu packs
 * on 2026-07-08 (grid-overlay inspection of the shipped PNGs):
 *  - Room_Builder_Office_16x16: grey office floor block at px(160,80),
 *    lavender wall trim+face band at px(0,80) spanning 64x32.
 *  - Modern_Office_Singles_N: every single is a 32x48 canvas, prop resting
 *    on the bottom edge (anchor bottom-center).
 *  - Premade_Character_NN (896x656, identical generator layout):
 *      y=0   four static 16x32 frames — R,U,L,D at x=0,16,32,48
 *      y=32  idle strips, 6 frames/direction — R@x0, U@x96, L@x192, D@x288
 *      y=64  walk strips, 6 frames/direction — same direction origins
 */
import { fnv1a } from './hash'
import type { OfficerScene } from './types'
import {
  BOOKSHELF_CUT,
  CONF_SHEET,
  CONF_TABLE_CUT,
  KETTLE_SHEET,
  LIBRARY_SHEET,
  NOTICEBOARD_SHEET,
  POUF_DARK_CUT,
  POUF_TAN_CUT,
  setDressingSheets,
  SIDEBOARD_COFFEE_CUT,
  WINDOW_CUT,
} from './set-dressing'

export const ASSET_BASE = '/world-assets/'

export interface ManifestRow {
  id: string
  path: string
  w: number
  h: number
  grid: number
  sha256: string
  /** Provenance, written by world-asset-install.py / world-asset-intake.py.
   * Optional because the renderer never reads them — but they are on every row
   * in the committed manifest, and the owned-vs-licensed distinction lives in
   * `license` ("owned — org-original" vs the LimeZu commercial terms). */
  pack?: string
  license?: string
}

export interface WorldAssetManifest {
  version: number
  assets: ManifestRow[]
}

/** A pixel-space cut out of a manifest sheet. */
export interface SpriteCut {
  x: number
  y: number
  w: number
  h: number
}

// ── room builder (floor + wall) ─────────────────────────────────────────────
export const ROOM_SHEET = 'office/Room_Builder_Office_16x16'
/** Smooth grey office floor, 2x2 tiles (tileable). */
export const FLOOR_CUT: SpriteCut = { x: 160, y: 80, w: 32, h: 32 }
/** Lavender wall — white trim + textured face, 3x2 tiles (tileable; the
 * sheet's 4th column carries the block-separator seam, so stop at 48px). */
export const WALL_CUT: SpriteCut = { x: 0, y: 80, w: 48, h: 32 }
/** Wall band height in tiles (drawn inside the room's top edge). */
export const WALL_TILES = 2

const SINGLE = (n: number) => `office/singles/Modern_Office_Singles_${n}`

/** One fixed civic station's sprite binding. */
export interface StationSprite {
  sheet: string
  flat: boolean
  /** Optional pixel cut out of a big sheet (whole single otherwise). */
  cut?: SpriteCut
  /** Wall-hung fixtures anchor to the wall band, not the floor foot. */
  wall?: boolean
}

/**
 * Fixed civic stations → Modern Office singles / verified big-sheet cuts.
 * flat=true renders under officers (mats/rugs); upright props y-sort.
 * v2 (cozy pass §2): table, kettle, bookshelf, windows, noticeboard.
 */
export const STATION_SPRITES: Record<string, StationSprite> = {
  board: { sheet: SINGLE(172), flat: false }, // analytics board on stand
  postbox: { sheet: SINGLE(325), flat: false }, // printer desk — the dispatch fixture
  door: { sheet: SINGLE(93), flat: true }, // doormat
  dojo: { sheet: SINGLE(87), flat: true }, // red rug
  floor: { sheet: SINGLE(92), flat: true }, // centre rug
  lever: { sheet: SINGLE(176), flat: false }, // server rack (red lamp overlay when killswitch)
  table: { sheet: CONF_SHEET, cut: CONF_TABLE_CUT, flat: false }, // conference oval table
  kettle: { sheet: KETTLE_SHEET, flat: false }, // coffee-machine table (break nook core)
  bookshelf: { sheet: LIBRARY_SHEET, cut: BOOKSHELF_CUT, flat: false }, // journal wall
  'window:1': { sheet: ROOM_SHEET, cut: WINDOW_CUT, flat: false, wall: true },
  'window:2': { sheet: ROOM_SHEET, cut: WINDOW_CUT, flat: false, wall: true },
  noticeboard: { sheet: NOTICEBOARD_SHEET, flat: false, wall: true }, // cork panel
}

/** Officer workstation variants — picked deterministically per slug. */
export const DESK_SHEETS = [SINGLE(225), SINGLE(227), SINGLE(231)]
/** Bunk rest chair. */
export const BUNK_SHEET = SINGLE(197)

/** Singles are normalized 32x48 canvases, prop on the bottom edge. */
export const SINGLE_W = 32
export const SINGLE_H = 48

// ── characters ──────────────────────────────────────────────────────────────
export const CHARACTER_COUNT = 20
export const CHAR_FRAME_W = 16
export const CHAR_FRAME_H = 32
/** Minimum sheet area the frame math below may touch (bounds-validated). */
export const CHAR_SHEET_MIN_W = 384
export const CHAR_SHEET_MIN_H = 96

/**
 * WHICH character art the world draws — the ONE line that swaps the whole cast.
 *
 * 'characters'           = the purchased LimeZu Premade sheets. Commercially
 *                          licensed, do-not-redistribute, gitignored — so a
 *                          stranger who hatches a cabinet from the public egg
 *                          gets a world with no people in it.
 * 'originals/characters' = the owned actor_officer family (20 sheets, same
 *                          896x656-compatible 16x32 cell layout, same file
 *                          names, license "owned — org-original"), committed
 *                          and exported.
 *
 * Both sets are in the manifest; changing this constant changes which one the
 * renderer binds. Nothing else in the engine knows the difference.
 */
export const CHARACTER_DIR = 'characters'

export function characterSheetFor(slug: string): string {
  const n = (fnv1a(slug) % CHARACTER_COUNT) + 1
  return `${CHARACTER_DIR}/Premade_Character_${String(n).padStart(2, '0')}`
}

export function deskSheetFor(slug: string): string {
  return DESK_SHEETS[fnv1a(slug) % DESK_SHEETS.length]
}

/** Render-facing: the director's left/right plus the renderer's up/down. */
export type CharFacing = 'right' | 'up' | 'left' | 'down'

/**
 * Static up-facing frame (row 0, U at x=16) — the §1.1 "stretch" micro-loop
 * hold: reads as leaning back from the desk. Verified against the Premade
 * Character generator layout documented in this file's header.
 */
export const CHAR_STRETCH_CUT: SpriteCut = {
  x: 16,
  y: 0,
  w: CHAR_FRAME_W,
  h: CHAR_FRAME_H,
}

/** Direction origin (px) of the 6-frame strips at y=32 (idle) / y=64 (walk). */
const DIR_X: Record<CharFacing, number> = {
  right: 0,
  up: 96,
  left: 192,
  down: 288,
}

/**
 * Frame rect within an officer's character sheet for one logical tick.
 * Pure: (anim, facing, tick, slug-phase) → rect. Never reads a clock.
 */
export function charFrame(
  anim: OfficerScene['anim'],
  facing: CharFacing,
  tick: number,
  phase: number
): SpriteCut {
  if (anim === 'asleep') {
    // Static front-facing frame (row 0, D at x=48); renderer dims it.
    return { x: 48, y: 0, w: CHAR_FRAME_W, h: CHAR_FRAME_H }
  }
  if (anim === 'walk') {
    const frame = (tick + phase) % 6
    return {
      x: DIR_X[facing] + frame * CHAR_FRAME_W,
      y: 64,
      w: CHAR_FRAME_W,
      h: CHAR_FRAME_H,
    }
  }
  // idle/work — 6-frame idle strip toward `facing` (renderer passes 'down'
  // at desks, 'up' at civic fixtures); half-tick idle cadence.
  const frame = Math.floor((tick + phase) / 2) % 6
  return {
    x: DIR_X[facing] + frame * CHAR_FRAME_W,
    y: 32,
    w: CHAR_FRAME_W,
    h: CHAR_FRAME_H,
  }
}

// ── resolution ──────────────────────────────────────────────────────────────

/**
 * Every sheet the Wardroom may draw. The full universe loads at boot (~30
 * small PNGs) so draw() stays synchronous and officer churn never triggers
 * mid-frame network fetches.
 */
export function requiredSheets(): string[] {
  const chars = Array.from({ length: CHARACTER_COUNT }, (_, i) =>
    `${CHARACTER_DIR}/Premade_Character_${String(i + 1).padStart(2, '0')}`
  )
  return [
    ...new Set([
      ROOM_SHEET,
      ...Object.values(STATION_SPRITES).map((s) => s.sheet),
      ...DESK_SHEETS,
      BUNK_SHEET,
      ...chars,
      // Cozy pass (§2): decor/lamps/flair/pins — same loud missing→badge
      // chain as every other asset class.
      ...setDressingSheets(),
    ]),
  ]
}

export interface ResolvedSprites {
  /** sheet id → same-origin URL (ASSET_BASE + manifest path). */
  urls: Record<string, string>
  /** Required sheet ids that are absent or fail dimension validation — LOUD. */
  missing: string[]
}

function cutFits(row: ManifestRow, cut: SpriteCut): boolean {
  return cut.x + cut.w <= row.w && cut.y + cut.h <= row.h
}

/**
 * Bind the required sheet universe against the manifest. Absent rows and
 * rows whose real dimensions cannot contain the cuts we take from them are
 * reported in `missing` — the renderer badges them and falls back to
 * visible placeholders (never silent, never invisible).
 */
export function resolveWorldSprites(manifest: WorldAssetManifest): ResolvedSprites {
  const byId = new Map(manifest.assets.map((r) => [r.id, r]))
  const urls: Record<string, string> = {}
  const missing: string[] = []
  for (const id of requiredSheets()) {
    const row = byId.get(id)
    if (!row) {
      missing.push(id)
      continue
    }
    let ok = true
    if (id === ROOM_SHEET) {
      ok = cutFits(row, FLOOR_CUT) && cutFits(row, WALL_CUT) && cutFits(row, WINDOW_CUT)
    } else if (id === CONF_SHEET) {
      ok =
        cutFits(row, CONF_TABLE_CUT) &&
        cutFits(row, SIDEBOARD_COFFEE_CUT) &&
        cutFits(row, POUF_TAN_CUT) &&
        cutFits(row, POUF_DARK_CUT)
    } else if (id === LIBRARY_SHEET) {
      ok = cutFits(row, BOOKSHELF_CUT)
    } else if (id.startsWith(`${CHARACTER_DIR}/`)) {
      ok = row.w >= CHAR_SHEET_MIN_W && row.h >= CHAR_SHEET_MIN_H
    } else if (id.startsWith('office/singles/')) {
      ok = row.w === SINGLE_W && row.h === SINGLE_H
    }
    if (!ok) {
      missing.push(id)
      continue
    }
    urls[id] = ASSET_BASE + row.path
  }
  return { urls, missing }
}
