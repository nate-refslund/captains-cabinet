/**
 * T2 LIFE — the visible-work construction pipeline (unified spec v2 §3.3,
 * D4; Captain ruling 2026-07-09 "Growth = VISIBLE WORK").
 *
 * Structure never pops in: every quick work runs its minutes-scale site,
 * every great work runs its 24 h scaffold WITH a crew — both PURE functions
 * of (T0, now_tick), replay-identical. Sprites move only when real events
 * fire; high-rate events can never start buildings (T0-from-keyframe
 * enforces rate-routing).
 *
 * The crew sprites are DECORATIVE-HONEST: staging of a real witnessed
 * transition, never officer claims — the site sign's codex says exactly
 * that (§15.5 confirms site crews are scenery of a real event, not implied
 * agents).
 *
 * This module never writes: the append-only site ledger (P-SITES,
 * world-sites.jsonl) is read server-side elsewhere and arrives here as
 * parsed data. foldSiteLedger() is the pure normalizer.
 */
import { fnv1a } from '../hash'

// ── durations (1 tick = 250 ms) ─────────────────────────────────────────────
export type SiteClass = 'quick_small' | 'quick_large' | 'great'
export const SITE_DURATION_TICKS: Record<SiteClass, number> = {
  quick_small: 15 * 60 * 4, // 15 min (small props: berth chalk, tool pip)
  quick_large: 90 * 60 * 4, // 90 min (large props: lantern post, field plot)
  great: 24 * 60 * 60 * 4, // 24 h scaffold (buildings + land)
}

export type SitePhase = 'clearing' | 'raising' | 'finishing' | 'reveal'

/** Phase thresholds (spec §3.3). */
export const PHASE_CLEARING_LT = 0.25
export const PHASE_RAISING_LT = 0.75

export type WitnessKind = 'chronicle' | 'keyframe' | 'config_first_seen'

export interface SiteWitness {
  kind: WitnessKind
  /** Chronicle iid / census keyframe field old→new / config path. */
  ref: string
}

export interface WorkSite {
  /** Stable site id (element + target stage — never reused). */
  id: string
  /** Growth element under construction (growth-ladders.yml element id). */
  element: string
  /** Target rung/stage label. */
  targetStage: string
  siteClass: SiteClass
  /** Tick of the WITNESS record (chronicle ts for verb-witnessed quick
   * works; first-seen snapshot tick for config flips; FIRST keyframe
   * showing the new tier for great works). */
  t0Tick: number
  /** Lot rectangle in tiles. */
  footprint: { x: number; y: number; w: number; h: number }
  witness: SiteWitness
}

export interface SiteProgress {
  progress: number
  phase: SitePhase
}

/** progress = clamp((now_tick − T0) / D, 0, 1) — pure, replay-identical. */
export function siteProgress(site: WorkSite, tick: number): SiteProgress {
  const d = SITE_DURATION_TICKS[site.siteClass]
  const progress = Math.min(1, Math.max(0, (tick - site.t0Tick) / d))
  const phase: SitePhase =
    progress >= 1
      ? 'reveal'
      : progress < PHASE_CLEARING_LT
        ? 'clearing'
        : progress < PHASE_RAISING_LT
          ? 'raising'
          : 'finishing'
  return { progress, phase }
}

// ── the crew ────────────────────────────────────────────────────────────────

/** log2 footprint tier, base 4 tiles (crew = 1 + tier, cap 4 — spec §3.3). */
export function footprintTier(tiles: number): number {
  const t = Math.max(1, tiles)
  return Math.min(3, Math.floor(Math.log2(t / 4 + 1)))
}

export function crewSize(footprint: WorkSite['footprint']): number {
  return 1 + footprintTier(footprint.w * footprint.h)
}

export type WrightAction = 'fell' | 'hammer' | 'sweep'

export interface WrightSprite {
  id: string
  x: number
  y: number
  action: WrightAction
  /** Seeded anim phase — no two wrights swing in lockstep. */
  phase: number
  /** Current swing frame (pure f(tick)). */
  frame: number
  facing: 'left' | 'right' | 'up' | 'down'
}

export const WRIGHT_SWING_PERIOD = 8

/** Perimeter tiles of a lot, in stable clockwise order from the NW corner. */
export function lotPerimeter(
  f: WorkSite['footprint']
): Array<{ x: number; y: number }> {
  const out: Array<{ x: number; y: number }> = []
  const x1 = f.x - 1
  const y1 = f.y - 1
  const x2 = f.x + f.w
  const y2 = f.y + f.h
  for (let x = x1; x <= x2; x++) out.push({ x, y: y1 })
  for (let y = y1 + 1; y <= y2; y++) out.push({ x: x2, y })
  for (let x = x2 - 1; x >= x1; x--) out.push({ x, y: y2 })
  for (let y = y2 - 1; y >= y1 + 1; y--) out.push({ x: x1, y })
  return out
}

const PHASE_ACTION: Record<Exclude<SitePhase, 'reveal'>, WrightAction> = {
  clearing: 'fell',
  raising: 'hammer',
  finishing: 'sweep',
}

/**
 * The seeded "wright" crew for a site at a tick. Empty at REVEAL (quiet
 * frame — site retired) and for STRUCK sites (crew departs). Positions are
 * seeded perimeter slots (linear-probed, collision-free); swing phases are
 * per-wright staggered.
 */
export function crewFor(
  site: WorkSite,
  tick: number,
  resolution: GreatWorkResolution = 'confirmed'
): WrightSprite[] {
  const { phase } = siteProgress(site, tick)
  if (phase === 'reveal' || resolution === 'struck') return []
  const n = crewSize(site.footprint)
  const perim = lotPerimeter(site.footprint)
  const taken = new Set<number>()
  const out: WrightSprite[] = []
  const cx = site.footprint.x + site.footprint.w / 2
  const cy = site.footprint.y + site.footprint.h / 2
  for (let i = 0; i < n; i++) {
    let slot = fnv1a(`${site.id}:crew:${i}`) % perim.length
    while (taken.has(slot)) slot = (slot + 1) % perim.length
    taken.add(slot)
    const p = perim[slot]
    const swingPhase = fnv1a(`${site.id}:swing:${i}`) % WRIGHT_SWING_PERIOD
    const dx = cx - p.x
    const dy = cy - p.y
    out.push({
      id: `${site.id}:wright:${i}`,
      x: p.x,
      y: p.y,
      action: PHASE_ACTION[phase],
      phase: swingPhase,
      frame: (tick + swingPhase) % WRIGHT_SWING_PERIOD,
      facing:
        Math.abs(dx) >= Math.abs(dy)
          ? dx < 0
            ? 'left'
            : 'right'
          : dy < 0
            ? 'up'
            : 'down',
    })
  }
  return out
}

// ── great-work 2-keyframe resolution (confirm or STRIKE) ────────────────────

export type GreatWorkResolution = 'building' | 'confirmed' | 'struck'

export interface KeyframeObs {
  /** Snapshot tick the keyframe was observed at. */
  tick: number
  /** The bound census value at that keyframe. */
  value: number
}

/**
 * Great works need TWO keyframes: T0 = the first keyframe showing the new
 * tier; the NEXT keyframe must still show it, else the site is STRUCK —
 * crew departs, scaffold comes down, lot reverts (an honest false start;
 * spec §3.3). Keyframes must be tick-ascending.
 */
export function resolveGreatWork(
  targetValue: number,
  keyframes: KeyframeObs[]
): GreatWorkResolution {
  let first: KeyframeObs | null = null
  for (const kf of keyframes) {
    if (first === null) {
      if (kf.value >= targetValue) first = kf
      continue
    }
    return kf.value >= targetValue ? 'confirmed' : 'struck'
  }
  return 'building'
}

/** Struck-site codex — cites BOTH keyframes (spec §3.3). */
export function struckCodex(
  site: WorkSite,
  first: KeyframeObs,
  second: KeyframeObs
): string {
  return (
    `Struck: ${site.element} → ${site.targetStage} was witnessed at keyframe ` +
    `tick ${first.tick} (value ${first.value}) but keyframe tick ${second.tick} ` +
    `(value ${second.value}) did not confirm it. Crew departed, lot reverted — ` +
    `an honest false start.`
  )
}

// ── the site sign (WHAT / NOW / PROOF) ──────────────────────────────────────

export interface SiteSign {
  what: string
  now: string
  proof: string
}

const WITNESS_LABEL: Record<WitnessKind, string> = {
  chronicle: 'chronicle iid',
  keyframe: 'census keyframe',
  config_first_seen: 'config flip (first-seen snapshot tick — T0 is the observation, not the flip instant)',
}

export function siteSign(site: WorkSite, tick: number): SiteSign {
  const { progress, phase } = siteProgress(site, tick)
  return {
    what: `${site.element} → ${site.targetStage}`,
    now: `${phase} · ${Math.round(progress * 100)}%`,
    proof: `${WITNESS_LABEL[site.witness.kind]}: ${site.witness.ref}`,
  }
}

/** Crew codex — decorative-honest, verbatim law (spec §3.3/§15.5). */
export const CREW_CODEX =
  'Construction crew: decorative-honest staging of a real witnessed ' +
  'transition — never an officer claim. The site exists because the cited ' +
  'witness record exists; the sprites are scenery of that event.'

// ── ledger fold (P-SITES entries arrive as data; this never writes) ─────────

export interface SiteLedgerFold {
  sites: WorkSite[]
  /** Honest rejections (rendered as validation problems, never dropped
   * silently). */
  problems: string[]
}

/**
 * Normalize parsed site-ledger entries: dedupe by id keeping the EARLIEST
 * T0 (T0 persistence is the ledger's whole job), reject malformed lots and
 * rate-routing violations — a great work whose witness is not a census
 * keyframe is refused (high-rate events can never start buildings).
 */
export function foldSiteLedger(entries: WorkSite[]): SiteLedgerFold {
  const byId = new Map<string, WorkSite>()
  const problems: string[] = []
  for (const e of entries) {
    if (
      !e.id ||
      !Number.isFinite(e.t0Tick) ||
      !e.footprint ||
      e.footprint.w <= 0 ||
      e.footprint.h <= 0 ||
      !(e.siteClass in SITE_DURATION_TICKS)
    ) {
      problems.push(`site ${e.id || '?'}: malformed entry rejected`)
      continue
    }
    if (e.siteClass === 'great' && e.witness.kind !== 'keyframe') {
      problems.push(
        `site ${e.id}: great work with ${e.witness.kind} witness refused ` +
          '(rate-routing: T0-from-keyframe only)'
      )
      continue
    }
    const prev = byId.get(e.id)
    if (!prev || e.t0Tick < prev.t0Tick) byId.set(e.id, e)
  }
  return {
    sites: [...byId.values()].sort((a, b) => (a.id < b.id ? -1 : 1)),
    problems,
  }
}
