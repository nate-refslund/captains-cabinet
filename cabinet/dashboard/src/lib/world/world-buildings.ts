/**
 * WORLD BUILDINGS — authored anchors × era×rung resolution → render list.
 *
 * layout_fold law: every anchor below is FINAL from birth (main-island
 * local tiles, translated by the archipelago offset); growth changes an
 * element's SIZE/vocab, never its position. Rung 0 of a `none`-rooted
 * ladder renders nothing (honest absence — reserved slot, not placeholder).
 *
 * PURE: f(resolution, geo) only. The renderer maps `sprite` hints to real
 * pack cuts (sprites-outdoor.ts); the cutaway resolver consumes the bbox
 * list in birth order (array order = deterministic tie-break).
 */
import type { WorldResolution } from './era-engine'
import type { WorldGeo } from './world-geo'
import { MAIN_OFFSET } from './world-geo'
import type { BuildingBox } from './lod'

/** Sprite hint the renderer resolves (kept abstract — cuts live with the
 * sprite binder, not here). */
export type SpriteHint =
  | 'great_house'
  | 'cottage'
  | 'library'
  | 'workshop'
  | 'well'
  | 'observatory'
  | 'barn'
  | 'law_plot'
  | 'warehouse'
  | 'hut'
  | 'lighthouse'
  | 'silo'
  | 'stall'
  | 'firepit'
  | 'water_store'
  | 'pen'
  | 'buoy_red'
  | 'buoy_grey'
  | 'mailbox'

export interface WorldBuilding extends BuildingBox {
  /** Ladder element this building renders (inspect card cites it). */
  element: string
  sprite: SpriteHint
  /** Rung + era vocab for the card ("NOW"). */
  rung: number
  rungName: string
  vocab: string | null
  /** Pending rung under hysteresis → construction-scaffold overlay. */
  pending: boolean
  /** False → grey "unmeasured" chip on the card. */
  measured: boolean
  /** True → officers render inside on cutaway (the Great House wardroom). */
  interior: boolean
}

/** Authored anchor table (main-island local tiles; birth order = row order). */
const ANCHORS: ReadonlyArray<{
  element: string
  sprite: SpriteHint
  lx: number
  ly: number
  w: number
  h: number
  interior?: boolean
  /** Rung names that mean "nothing renders yet". */
  noneRungs?: readonly string[]
}> = [
  { element: 'great_house', sprite: 'great_house', lx: 26, ly: 7, w: 6, h: 5, interior: true },
  { element: 'library', sprite: 'library', lx: 35, ly: 10, w: 4, h: 4, interior: true, noneRungs: [] },
  { element: 'workshop', sprite: 'workshop', lx: 20, ly: 12, w: 4, h: 3, interior: true },
  { element: 'well', sprite: 'well', lx: 32, ly: 16, w: 2, h: 2, noneRungs: ['none'] },
  { element: 'firepit', sprite: 'firepit', lx: 28, ly: 17, w: 2, h: 2 },
  { element: 'law_plot', sprite: 'law_plot', lx: 24, ly: 2, w: 6, h: 4 },
  { element: 'observatory', sprite: 'observatory', lx: 40, ly: 6, w: 3, h: 3 },
  { element: 'outbuildings', sprite: 'barn', lx: 42, ly: 14, w: 6, h: 5, noneRungs: ['none'] },
  { element: 'pens', sprite: 'pen', lx: 44, ly: 22, w: 4, h: 3 },
  { element: 'water_store', sprite: 'water_store', lx: 38, ly: 18, w: 2, h: 2 },
  { element: 'journal_desk', sprite: 'stall', lx: 33, ly: 13, w: 2, h: 2 },
  // harbor (Lantern Quay)
  { element: 'warehouse', sprite: 'warehouse', lx: 22, ly: 40, w: 5, h: 4, interior: true, noneRungs: ['none'] },
  { element: 'harbormaster_hut', sprite: 'hut', lx: 36, ly: 40, w: 3, h: 3, interior: true, noneRungs: ['none'] },
  { element: 'lighthouse', sprite: 'lighthouse', lx: 44, ly: 42, w: 3, h: 5 },
] as const

/** Officer dwellings: one per role, birth-order slots on the west path. */
export function dwellingBoxes(count: number): WorldBuilding[] {
  const out: WorldBuilding[] = []
  for (let i = 0; i < count; i++) {
    out.push({
      id: `dwelling:${i}`,
      element: 'officer_dwellings',
      sprite: 'cottage',
      x: MAIN_OFFSET.x + 16 - (i % 2) * 5,
      y: MAIN_OFFSET.y + 14 + Math.floor(i / 2) * 6,
      w: 4,
      h: 3,
      bound: true,
      rung: count,
      rungName: `dwellings_${count}`,
      vocab: null,
      pending: false,
      measured: true,
      interior: true,
    })
  }
  return out
}

/**
 * The bound building list for one resolved world, in BIRTH ORDER (anchors
 * first, dwellings appended — cutaway tie-break law rides this order).
 */
export function buildWorldBuildings(
  res: WorldResolution,
  _geo: WorldGeo
): WorldBuilding[] {
  const out: WorldBuilding[] = []
  for (const a of ANCHORS) {
    const el = res.elements[a.element]
    if (!el) continue
    const noneRungs = a.noneRungs ?? ['none']
    if (noneRungs.includes(el.rungName)) continue // honest absence
    out.push({
      id: a.element,
      element: a.element,
      sprite: a.sprite,
      x: MAIN_OFFSET.x + a.lx,
      y: MAIN_OFFSET.y + a.ly,
      w: a.w,
      h: a.h,
      bound: true,
      rung: el.rung,
      rungName: el.rungName,
      vocab: el.vocab,
      pending: el.pending !== null,
      measured: el.measured,
      interior: a.interior ?? false,
    })
  }
  const dwellings = res.elements.officer_dwellings
  if (dwellings && dwellings.rung > 0) {
    // count-mode: rung ≈ dwelling count (rungs: none, 1, 2, 3, 4, 5plus)
    out.push(...dwellingBoxes(Math.min(dwellings.rung, 5)))
  }
  return out
}
