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

export const ASSET_BASE = '/world-assets/'

export interface ManifestRow {
  id: string
  path: string
  w: number
  h: number
  grid: number
  sha256: string
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

/**
 * Fixed civic stations → Modern Office singles.
 * flat=true renders under officers (mats/rugs); upright props y-sort.
 */
export const STATION_SPRITES: Record<string, { sheet: string; flat: boolean }> = {
  board: { sheet: SINGLE(172), flat: false }, // analytics board on stand
  postbox: { sheet: SINGLE(325), flat: false }, // printer desk — the dispatch fixture
  door: { sheet: SINGLE(93), flat: true }, // doormat
  dojo: { sheet: SINGLE(87), flat: true }, // red rug
  floor: { sheet: SINGLE(92), flat: true }, // centre rug
  lever: { sheet: SINGLE(176), flat: false }, // server rack (red lamp overlay when killswitch)
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

export function characterSheetFor(slug: string): string {
  const n = (fnv1a(slug) % CHARACTER_COUNT) + 1
  return `characters/Premade_Character_${String(n).padStart(2, '0')}`
}

export function deskSheetFor(slug: string): string {
  return DESK_SHEETS[fnv1a(slug) % DESK_SHEETS.length]
}

/** Render-facing: the director's left/right plus the renderer's up/down. */
export type CharFacing = 'right' | 'up' | 'left' | 'down'

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
    `characters/Premade_Character_${String(i + 1).padStart(2, '0')}`
  )
  return [
    ROOM_SHEET,
    ...Object.values(STATION_SPRITES).map((s) => s.sheet),
    ...DESK_SHEETS,
    BUNK_SHEET,
    ...chars,
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
      ok = cutFits(row, FLOOR_CUT) && cutFits(row, WALL_CUT)
    } else if (id.startsWith('characters/')) {
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
