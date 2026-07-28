/**
 * LOD CAMERA + ROOF CUTAWAY — one continuous world, never a scene swap.
 *
 * Doctrine (spec v2 D1/D3, supersession #5): the camera is pan + zoom over
 * the ONE world; zooming out reaches the archipelago as LOD (coarser
 * sampling of the same world), zooming close over a bound building fades
 * its roof IN PLACE (at most ONE interior open at a time; the world keeps
 * ticking around it). The old scenes: enum (wardroom|street|island) is
 * retired — this module is what replaced it.
 *
 * PURE: every resolver is a function of (state, inputs, logical tick).
 * No wall clock — fade timing derives from tick × TICK_MS.
 */

/** Continuous zoom bounds: ×3 close … ×1/4 archipelago (D1 ladder). */
export const ZOOM_MIN = 0.25
export const ZOOM_MAX = 3

export function clampZoom(z: number): number {
  if (!Number.isFinite(z)) return 1
  return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z))
}

/** Continuous camera — world-tile center + continuous zoom. */
import { TOPDOWN_TILE } from './projection'

export interface EngineCamera {
  z: number
  x: number
  y: number
}

/** LOD tiers quantized from the continuous zoom (D1 ladder:
 * ×3 close / ×2 mid / ×1 island / ×1/2 coast / ×1/4 archipelago). */
export type LodTier = 'close' | 'mid' | 'island' | 'coast' | 'archipelago'

export function lodTier(z: number): LodTier {
  const zz = clampZoom(z)
  if (zz >= 2.5) return 'close'
  if (zz >= 1.5) return 'mid'
  if (zz >= 0.75) return 'island'
  if (zz >= 0.375) return 'coast'
  return 'archipelago'
}

/** Per-tier cull/aggregate rules — data, not branches (renderer samples). */
export interface LodRules {
  /** Render loose props (benches, crates, flowers). */
  props: boolean
  /** Render officers/commuters as sprites (false = cull / motes only). */
  officers: boolean
  /** Buildings collapse to seeded footprint blocks (silhouettes). */
  buildingsAsFootprints: boolean
  /** Ships persist as 4-px silhouettes (ships NEVER cull — law). */
  shipsSilhouette: boolean
  /** Windows/lamps aggregate to one light mass per district/isle. */
  lightMassAggregate: boolean
  /** Cutaway may activate (close zoom only). */
  cutawayEligible: boolean
}

export const LOD_RULES: Record<LodTier, LodRules> = {
  close: {
    props: true,
    officers: true,
    buildingsAsFootprints: false,
    shipsSilhouette: false,
    lightMassAggregate: false,
    cutawayEligible: true,
  },
  mid: {
    props: true,
    officers: true,
    buildingsAsFootprints: false,
    shipsSilhouette: false,
    lightMassAggregate: false,
    cutawayEligible: false,
  },
  island: {
    props: true,
    officers: true,
    buildingsAsFootprints: false,
    shipsSilhouette: false,
    lightMassAggregate: false,
    cutawayEligible: false,
  },
  coast: {
    props: false,
    officers: false,
    buildingsAsFootprints: true,
    shipsSilhouette: true,
    lightMassAggregate: true,
    cutawayEligible: false,
  },
  archipelago: {
    props: false,
    officers: false,
    buildingsAsFootprints: true,
    shipsSilhouette: true,
    lightMassAggregate: true,
    cutawayEligible: false,
  },
}

// ── roof cutaway (spec v2 §5.1 — single-active, in place) ───────────────────

/** A bound building's world-tile bbox (birth order = array order). */
export interface BuildingBox {
  id: string
  x: number
  y: number
  w: number
  h: number
  /** False = unbound decor: never cutaway-eligible. */
  bound: boolean
}

/** Logical ms per tick (mirrors the shell's TICK_MS). */
export const TICK_MS = 250
/** Roof fade duration (§5.1: 300 ms, 1 → 0.08 in place). */
export const CUTAWAY_FADE_MS = 300
export const ROOF_ALPHA_OPEN = 0.08
/** Candidate must cover ≥40% of the viewport's central third. */
export const CUTAWAY_COVER_MIN = 0.4
/** Candidate must hold this many consecutive ticks before opening. */
export const CUTAWAY_HOLD_TICKS = 2

export interface Viewport {
  /** Viewport size in screen px. */
  w: number
  h: number
}

/**
 * Project a world-tile rect to screen px under a centered camera.
 *
 * The tile comes from the ONE kernel module. It was a private TILE_PX = 16
 * here — the fifth copy of a transform that existed five times and disagreed
 * with itself, and the one nobody would have thought to look at.
 *
 * IT IS DELIBERATELY TOP-DOWN ONLY, and that is a stated limit rather than an
 * oversight: the only caller is cutawayCandidate, whose 40%-of-the-central-third
 * coverage rule is calibrated to axis-aligned rects and would misfire on ground
 * diamonds. The iso path draws no cutaway this round, so a kernel parameter
 * here would be a lever with no correct setting behind it.
 */
function screenRect(
  b: BuildingBox,
  cam: EngineCamera,
  vp: Viewport
): { x0: number; y0: number; x1: number; y1: number } {
  const s = TOPDOWN_TILE.w * cam.z
  return {
    x0: vp.w / 2 + (b.x - cam.x) * s,
    y0: vp.h / 2 + (b.y - cam.y) * s,
    x1: vp.w / 2 + (b.x + b.w - cam.x) * s,
    y1: vp.h / 2 + (b.y + b.h - cam.y) * s,
  }
}

/**
 * The cutaway CANDIDATE this tick: the FIRST (birth-order) bound building
 * whose bbox covers ≥40% of the viewport's central third — deterministic
 * tie-break by birth order (array order), per §5.1. Null when the camera
 * is not close or nothing qualifies.
 */
export function cutawayCandidate(
  buildings: BuildingBox[],
  cam: EngineCamera,
  vp: Viewport
): string | null {
  if (!LOD_RULES[lodTier(cam.z)].cutawayEligible) return null
  const cx0 = vp.w / 3
  const cx1 = (2 * vp.w) / 3
  const cy0 = vp.h / 3
  const cy1 = (2 * vp.h) / 3
  const boxArea = (cx1 - cx0) * (cy1 - cy0)
  if (boxArea <= 0) return null
  for (const b of buildings) {
    if (!b.bound) continue
    const r = screenRect(b, cam, vp)
    const ix = Math.max(0, Math.min(r.x1, cx1) - Math.max(r.x0, cx0))
    const iy = Math.max(0, Math.min(r.y1, cy1) - Math.max(r.y0, cy0))
    if ((ix * iy) / boxArea >= CUTAWAY_COVER_MIN) return b.id
  }
  return null
}

export interface CutawayState {
  /** The open interior (roof faded), or null. */
  openId: string | null
  /** Tick at which openId opened (fade-in anchor). */
  openedAt: number | null
  /** The building whose roof is fading BACK (just closed), or null. */
  closingId: string | null
  closedAt: number | null
  /** Hold tracking: current candidate + consecutive ticks seen. */
  candId: string | null
  candTicks: number
}

export function initialCutaway(): CutawayState {
  return {
    openId: null,
    openedAt: null,
    closingId: null,
    closedAt: null,
    candId: null,
    candTicks: 0,
  }
}

/**
 * One tick of the cutaway machine: a candidate must hold
 * CUTAWAY_HOLD_TICKS consecutive ticks before it opens (and before the
 * open one closes). Pure reducer — replay-identical.
 */
export function cutawayStep(
  state: CutawayState,
  candidate: string | null,
  tick: number
): CutawayState {
  const candTicks = candidate !== null && candidate === state.candId ? state.candTicks + 1 : 1
  const held = candTicks >= CUTAWAY_HOLD_TICKS
  // Note: a null candidate also needs the hold (pan-away flicker guard).
  const nullTicks = candidate === null && state.candId === null ? state.candTicks + 1 : 1
  if (candidate === state.openId) {
    // Steady state (incl. both null): clear any finished closing fade.
    const fadeDone =
      state.closedAt !== null && (tick - state.closedAt) * TICK_MS >= CUTAWAY_FADE_MS
    return {
      ...state,
      candId: candidate,
      candTicks: candidate === null ? nullTicks : candTicks,
      closingId: fadeDone ? null : state.closingId,
      closedAt: fadeDone ? null : state.closedAt,
    }
  }
  if (candidate === null) {
    if (nullTicks >= CUTAWAY_HOLD_TICKS && state.openId !== null) {
      return {
        openId: null,
        openedAt: null,
        closingId: state.openId,
        closedAt: tick,
        candId: null,
        candTicks: 0,
      }
    }
    return { ...state, candId: null, candTicks: nullTicks }
  }
  if (held) {
    return {
      openId: candidate,
      openedAt: tick,
      closingId: state.openId,
      closedAt: state.openId !== null ? tick : null,
      candId: candidate,
      candTicks,
    }
  }
  return { ...state, candId: candidate, candTicks }
}

/**
 * Roof alpha for a building at a tick: 1 (roof on) → ROOF_ALPHA_OPEN over
 * CUTAWAY_FADE_MS for the open building; the reverse ramp for the one just
 * closed. Pure — same (state, id, tick) always yields the same alpha.
 */
export function roofAlpha(state: CutawayState, id: string, tick: number): number {
  if (state.openId === id && state.openedAt !== null) {
    const t = Math.min(1, ((tick - state.openedAt) * TICK_MS) / CUTAWAY_FADE_MS)
    return 1 - (1 - ROOF_ALPHA_OPEN) * t
  }
  if (state.closingId === id && state.closedAt !== null) {
    const t = Math.min(1, ((tick - state.closedAt) * TICK_MS) / CUTAWAY_FADE_MS)
    return ROOF_ALPHA_OPEN + (1 - ROOF_ALPHA_OPEN) * t
  }
  return 1
}
