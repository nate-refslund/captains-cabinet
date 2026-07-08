/**
 * Wardroom set dressing — the cozy pass (world-alive direction 2026-07-08 §2).
 *
 * PURE DATA + seeded pickers; no rendering here. Doctrine:
 *  - Every sheet named below is a content-addressed manifest row (LimeZu
 *    packs, gated by cabinet/scripts/world-asset-gate.py); sprites.ts unions
 *    these ids into requiredSheets() so a missing sheet trips the SAME
 *    loud missing→badge chain as every other asset class.
 *  - All decor is DECORATIVE: zero information (inspect says so). Stardew
 *    density is phenotype and legal; the reserved salience palette is
 *    untouched (paper-pin hues below are cream/tan/blue — never the alarm
 *    hues).
 *  - Determinism: per-desk personalization (lamp variant + 2 flair items) is
 *    seeded from fnv1a(slug…) — the same slug renders the same desk forever;
 *    no two desks match, nothing reshuffles between sessions.
 *  - Pixel cuts below were verified against the shipped sheets on 2026-07-08
 *    with the grid-overlay/alpha-bbox method documented in sprites.ts.
 *
 * Layout constants this module places against: room 40×24, wall band rows
 * 0–1, desk band y=8, bunk row y=17 (lib/world/layout.ts).
 */
import { fnv1a } from './hash'
import type { SpriteCut } from './sprites'

const SINGLE = (n: number) => `office/singles/Modern_Office_Singles_${n}`

// ── big-sheet cuts (verified 2026-07-08, alpha-bbox) ────────────────────────
export const CONF_SHEET = 'interiors/13_Conference_Hall_16x16'
export const LIBRARY_SHEET = 'interiors/5_Classroom_and_library_16x16'

/** Conference oval table (grammar v2 `table` station; ~4×2.3 tiles). */
export const CONF_TABLE_CUT: SpriteCut = { x: 10, y: 24, w: 62, h: 37 }
/** Sideboard with a coffee cup — the kettle nook's coffee surface. */
export const SIDEBOARD_COFFEE_CUT: SpriteCut = { x: 141, y: 76, w: 54, h: 23 }
/** Beanbag poufs for the dojo reading corner (tan + dark). */
export const POUF_TAN_CUT: SpriteCut = { x: 208, y: 99, w: 16, h: 13 }
export const POUF_DARK_CUT: SpriteCut = { x: 176, y: 118, w: 20, h: 22 }
/** One library shelf unit, books in — the org's journal wall. */
export const BOOKSHELF_CUT: SpriteCut = { x: 64, y: 116, w: 32, h: 36 }

/**
 * Wall window (office/Room_Builder_Office_16x16): framed pane whose glass
 * pixels are TRANSPARENT — the day/night sky renders as a lighting fill
 * BEHIND the sprite and shows through the glass (lib/world/lighting.ts).
 */
export const WINDOW_CUT: SpriteCut = { x: 120, y: 16, w: 32, h: 40 }
/** Glass rect relative to WINDOW_CUT's origin (the see-through pane). */
export const WINDOW_GLASS = { dx: 8, dy: 6, w: 16, h: 26 }

// ── kettle nook / noticeboard singles ───────────────────────────────────────
/** Coffee-machine table — the kettle fixture itself (station sprite). */
export const KETTLE_SHEET = SINGLE(320)
/** Cork noticeboard panel (station sprite). */
export const NOTICEBOARD_SHEET = SINGLE(194)

// ── static decor (flat = under officers; upright props y-sort) ─────────────
export interface DecorProp {
  /** Stable id (cache key; also the seed for any per-prop variation). */
  id: string
  sheet: string
  cut?: SpriteCut
  /** Tile position (float tiles allowed; positions fix at authoring time). */
  x: number
  y: number
  flat: boolean
  /** Wall-hung props anchor to the wall band instead of the floor foot. */
  wall?: boolean
}

/**
 * The Wardroom decor set (§2): warmth outside the reserved hues — tan rug
 * runner under the desk band, plants (max one per ~8 tiles), kettle-nook
 * counters + vending + sideboard, posters on the top wall, dojo beanbags,
 * postbox paper dressing, board flip-chart.
 */
export const DECOR: DecorProp[] = [
  // kettle nook (around the kettle station at 5,5)
  { id: 'decor:vending', sheet: SINGLE(175), x: 3, y: 5, flat: false },
  { id: 'decor:counter:1', sheet: SINGLE(190), x: 7, y: 5, flat: false },
  { id: 'decor:counter:2', sheet: SINGLE(191), x: 8.4, y: 5, flat: false },
  { id: 'decor:sideboard', sheet: CONF_SHEET, cut: SIDEBOARD_COFFEE_CUT, x: 11.5, y: 5, flat: false },
  { id: 'decor:plant:kettle', sheet: SINGLE(99), x: 9.6, y: 4.6, flat: false },
  { id: 'decor:chair:kettle:1', sheet: SINGLE(107), x: 4, y: 7, flat: false },
  { id: 'decor:chair:kettle:2', sheet: SINGLE(111), x: 6.2, y: 7.2, flat: false },
  // plants (door / board / NE corner)
  { id: 'decor:plant:door', sheet: SINGLE(98), x: 3, y: 11, flat: false },
  { id: 'decor:plant:board', sheet: SINGLE(98), x: 24.2, y: 4.2, flat: false },
  { id: 'decor:plant:ne', sheet: SINGLE(100), x: 38.6, y: 5, flat: false },
  // wall life (top wall band)
  { id: 'decor:poster:1', sheet: SINGLE(96), x: 8, y: 2, flat: false, wall: true },
  { id: 'decor:poster:2', sheet: SINGLE(114), x: 25, y: 2, flat: false, wall: true },
  { id: 'decor:poster:3', sheet: SINGLE(115), x: 32, y: 2, flat: false, wall: true },
  // board dressing
  { id: 'decor:flipchart', sheet: SINGLE(171), x: 22.2, y: 3, flat: false },
  // dojo reading corner (beanbags are decor; the dojo stays the dojo)
  { id: 'decor:pouf:tan', sheet: CONF_SHEET, cut: POUF_TAN_CUT, x: 17.6, y: 21.4, flat: false },
  { id: 'decor:pouf:dark', sheet: CONF_SHEET, cut: POUF_DARK_CUT, x: 22.6, y: 21.2, flat: false },
  // postbox dispatch corner
  { id: 'decor:papers:1', sheet: SINGLE(153), x: 33.2, y: 12.4, flat: false },
  { id: 'decor:papers:2', sheet: SINGLE(154), x: 36.4, y: 13, flat: false },
]

/**
 * Warm rug runner under the desk band (§2 floor warmth): a tileable field,
 * rendered as one TilingSprite from the 16×16 mat tile inside single 86.
 */
export const RUG_RUNNER = {
  sheet: SINGLE(86),
  /** The mat tile inside the 32×48 single canvas (verified alpha-bbox). */
  cut: { x: 0, y: 32, w: 16, h: 16 } as SpriteCut,
  /** Tile-space rect the runner covers (under the desk band). */
  rect: { x: 7, y: 7.5, w: 26, h: 3 },
}

// ── rest alcove (per-bunk, dynamic — placed from layout.bunks) ──────────────
export const ALCOVE = {
  rugSheet: SINGLE(95),
  cabinetSheet: SINGLE(181),
  /** Offsets in tiles relative to the bunk station. */
  rugOffset: { dx: 0, dy: 0.4 },
  cabinetOffset: { dx: -1.3, dy: -0.35 },
}

// ── per-desk personalization (seeded, zero-info) ────────────────────────────
/** Articulated desk lamps 141–146 — variant is seeded per slug. */
export const LAMP_SHEETS = [141, 142, 143, 144, 145, 146].map(SINGLE)

export function lampSheetFor(slug: string): string {
  return LAMP_SHEETS[fnv1a(`${slug}:lamp`) % LAMP_SHEETS.length]
}

/** Lamp position relative to the desk station (left edge of the desk). */
export const LAMP_OFFSET = { dx: -0.75, dy: 0.9 }

export interface FlairItem {
  sheet: string
  /** Placement relative to the desk station, in tiles. */
  dx: number
  dy: number
}

/**
 * Flair pool (§2): small plant, snake plant, paper stack, tablet, second
 * monitor, three backpack colors. Two DISTINCT items per desk, seeded by
 * slug — same slug renders identically forever.
 */
export const FLAIR_POOL: ReadonlyArray<FlairItem> = [
  { sheet: SINGLE(99), dx: 1.2, dy: 0.9 },
  { sheet: SINGLE(100), dx: 1.2, dy: 0.9 },
  { sheet: SINGLE(153), dx: 1.15, dy: 0.85 },
  { sheet: SINGLE(136), dx: 1.15, dy: 0.85 },
  { sheet: SINGLE(131), dx: 1.2, dy: 0.8 },
  { sheet: SINGLE(331), dx: 1.05, dy: 1.15 }, // backpack leaning on the desk leg
  { sheet: SINGLE(333), dx: 1.05, dy: 1.15 },
  { sheet: SINGLE(335), dx: 1.05, dy: 1.15 },
]

/** Two distinct flair items for a desk, deterministically picked per slug. */
export function deskFlairFor(slug: string): [FlairItem, FlairItem] {
  const n = FLAIR_POOL.length
  const first = fnv1a(`${slug}:flair`) % n
  const second = (first + 1 + (fnv1a(`${slug}:flair:2`) % (n - 1))) % n
  return [FLAIR_POOL[first], FLAIR_POOL[second]]
}

/** The second flair item sits on the desk's other flank. */
export const FLAIR_SECOND_OFFSET = { dx: -1.15, dy: 1.1 }

// ── noticeboard pins (chronicle-driven TEXTURE) ─────────────────────────────
/**
 * Pinned-note hues: paper colors (cream/tan/sky/sand) — deliberately outside
 * the reserved salience palette (no green/amber/red/grey/purple semantics).
 */
export const NOTE_PIN_COLORS = [0xf2e4c2, 0xd9c8a0, 0xaec6e8, 0xe8d0b0]

/** Pin size in px (tiny pinned note squares on the cork face). */
export const NOTE_PIN_SIZE = 2

/** Cork face inset of single 194, relative to its bottom-center anchor
 * (art bbox x10..31, y18..43 in the 32×48 canvas; 3px face inset). */
export const PIN_AREA = { x0: -3, y0: -27, w: 15, h: 19 }

/** Cap: the board renders at most the last N chronicle headlines as pins. */
export const NOTE_PIN_MAX = 12

/**
 * Deterministic pin placement + color for one chronicle record iid. Same
 * record pins to the same spot in the same paper hue forever.
 */
export function pinPlacement(iid: number): { dx: number; dy: number; color: number } {
  return {
    dx: PIN_AREA.x0 + (fnv1a(`pin:${iid}:x`) % PIN_AREA.w),
    dy: PIN_AREA.y0 + (fnv1a(`pin:${iid}:y`) % PIN_AREA.h),
    color: NOTE_PIN_COLORS[fnv1a(`pin:${iid}:c`) % NOTE_PIN_COLORS.length],
  }
}

/** Anchor tile for the DOM clock chip (numbers are text; text is DOM). */
export const CLOCK_CHIP_ANCHOR = { x: 23, y: 2 }

// ── sheet universe (unioned into sprites.requiredSheets) ────────────────────
/** Every sheet the cozy pass may draw — feeds the loud missing→badge chain. */
export function setDressingSheets(): string[] {
  const ids = new Set<string>()
  for (const d of DECOR) ids.add(d.sheet)
  ids.add(RUG_RUNNER.sheet)
  ids.add(ALCOVE.rugSheet)
  ids.add(ALCOVE.cabinetSheet)
  for (const s of LAMP_SHEETS) ids.add(s)
  for (const f of FLAIR_POOL) ids.add(f.sheet)
  ids.add(KETTLE_SHEET)
  ids.add(NOTICEBOARD_SHEET)
  ids.add(CONF_SHEET)
  ids.add(LIBRARY_SHEET)
  return [...ids].sort()
}
