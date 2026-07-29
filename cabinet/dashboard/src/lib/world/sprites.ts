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

const SINGLE = (n: number) => `office/singles/Modern_Office_Singles_${n}`

/** Officer workstation variants — picked deterministically per slug. */
export const DESK_SHEETS = [SINGLE(225), SINGLE(227), SINGLE(231)]

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
 *                          licensed, do-not-redistribute, gitignored.
 * 'originals/characters' = LIVE (Captain ruling 2026-07-28). The owned
 *                          actor_officer family: 20 sheets, same
 *                          896x656-compatible 16x32 cell layout, same file
 *                          names, license "owned — org-original", committed.
 *
 * The world now draws art the org owns. Known and accepted at the ruling: the
 * walk reads as a sway rather than a stride — improvable in place, and the
 * revert stays this one line.
 *
 * It also ships: egg-export-manifest.txt expects public/world-assets/
 * originals PRESENT since 2026-07-28 ("ALL OUT of LimeZu"), so a stranger who
 * hatches from the public egg now gets a world with people in it — which the
 * licensed set, gitignored and absent from HEAD, could never give them.
 *
 * Both sets are in the manifest; changing this constant changes which one the
 * renderer binds. Nothing else in the engine knows the difference — EXCEPT the
 * art credit, which must not name LimeZu for pixels LimeZu did not draw: it
 * reads this constant's licence back off the manifest (lib/world/credit.ts),
 * so reverting this line restores the credit under iso by itself.
 */
export const CHARACTER_DIR = 'originals/characters'

export function characterSheetFor(slug: string): string {
  const n = (fnv1a(slug) % CHARACTER_COUNT) + 1
  return `${CHARACTER_DIR}/Premade_Character_${String(n).padStart(2, '0')}`
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
