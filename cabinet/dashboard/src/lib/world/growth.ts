/**
 * Growth read-model — pure client fn from census keyframes to render tiers
 * (world-alive direction 2026-07-08 §4; morphology law: tier_i =
 * clamp(floor(log2(S_i / base_i + 1)), 0, 7)).
 *
 * Doctrine:
 *  - PURE: no clocks, no randomness, no fetches. Input = the census keyframe
 *    tail served by /api/world/grammar (server reads the same fenced
 *    shared/interfaces/world-chronicle.jsonl the binding validator executes
 *    against — no DB creds, no Redis in the render path).
 *  - HYSTERESIS (morphology law): a tier change must hold 2 consecutive
 *    daily keyframes; until then the OLD tier renders and `pendingTier`
 *    carries the incoming one (construction-scaffold overlay + inspect chip).
 *  - HONEST ZEROS: absent/short keyframe file → `available: false` and every
 *    surface renders day-0; the beacon stays dark until cells_graduated > 0.
 *  - Numbers here mirror cabinet/world/morphology.yml v2 entries (bases are
 *    LAW — a base change is a grammar PR, never a code tweak).
 */

/** One census keyframe line from shared/interfaces/world-chronicle.jsonl. */
export type CensusKeyframe = Record<string, number | string | null>

/** Morphology tier law: clamp(floor(log2(S/base + 1)), 0, 7). */
export function tier(S: number, base: number): number {
  if (!Number.isFinite(S) || !Number.isFinite(base) || base <= 0 || S <= 0) {
    return 0
  }
  return Math.max(0, Math.min(7, Math.floor(Math.log2(S / base + 1))))
}

/** Island fold law: land radius R = 24 + 6*floor(log10(total_events+1)). */
export function landRadius(totalEvents: number): number {
  const n = Number.isFinite(totalEvents) && totalEvents > 0 ? totalEvents : 0
  return 24 + 6 * Math.floor(Math.log10(n + 1))
}

/** A tiered growth surface with the hysteresis pair. */
export interface GrowthSurface {
  /** The tier that RENDERS now (the older of the pair under hysteresis). */
  tier: number
  /** Incoming tier not yet held 2 keyframes (scaffold overlay), or null. */
  pendingTier: number | null
  /** Raw S from the latest keyframe (inspect card cites it). */
  value: number
}

function num(k: CensusKeyframe | undefined, field: string): number {
  const v = k?.[field]
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

/** Hysteresis pair for one surface across [prev, latest]. */
export function surfaceGrowth(
  prev: CensusKeyframe | undefined,
  latest: CensusKeyframe | undefined,
  field: string,
  base: number
): GrowthSurface {
  const sLatest = num(latest, field)
  const tLatest = tier(sLatest, base)
  if (!prev) {
    // Single keyframe: day one of hysteresis is itself honest — render it.
    return { tier: tLatest, pendingTier: null, value: sLatest }
  }
  const tPrev = tier(num(prev, field), base)
  if (tPrev === tLatest) return { tier: tLatest, pendingTier: null, value: sLatest }
  return { tier: tPrev, pendingTier: tLatest, value: sLatest }
}

/**
 * Street set-dressing unlock band by org age (street_liveliness, TEXTURE).
 *
 * UNCONSUMED SINCE 2026-07-29, said out loud rather than left to be discovered.
 * Its only reader was `street-layout.ts` in the legacy three-scene shell, which
 * was deleted that day. The field STAYS because `street_liveliness` is a
 * ratified row in cabinet/world/morphology.yml — that grammar is LAW and
 * changes by grammar PR, not by a renderer deletion — and because the band is
 * computed honestly from census dates either way. Nothing on the live path
 * reads `streetBand` today; a future surface that wants an org-age texture
 * should bind THIS rather than derive a second one.
 */
export type StreetAgeBand = 'bare' | 'benches' | 'planters'

/** Age in whole days between two census date strings (server data, not a clock). */
export function ageDays(firstDate: string | null, latestDate: string | null): number {
  if (!firstDate || !latestDate) return 0
  const a = Date.parse(firstDate)
  const b = Date.parse(latestDate)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 0
  return Math.floor((b - a) / 86_400_000)
}

export function streetAgeBand(days: number): StreetAgeBand {
  if (days > 30) return 'planters'
  if (days >= 7) return 'benches'
  return 'bare'
}

/**
 * The whole-world growth model both outdoor scenes consume.
 * Field names mirror morphology.yml v2 ids (street_hq_floors, island_*).
 */
export interface GrowthModel {
  /** False when the census file is missing/empty — day-0 renders + amber badge. */
  available: boolean
  /** Latest census date (inspect provenance), or null. */
  date: string | null
  /** island_land_radius — R in tiles from org_events_total. */
  radius: number
  /** street_hq_floors — modular floors above ground = commits tier. */
  hqFloors: GrowthSurface
  /** island_officer_houses — cottages on the west path (ev_role_defined). */
  officerHouses: number
  /** island_fields — tilled plots (outcomes_total). */
  fieldPlots: number
  /** island_fields crop stage 0..6 = min(6, work_completed tier). */
  cropStage: GrowthSurface
  /** island_harbor_beacon — beam ONLY when cells_graduated > 0 (honest zero). */
  beaconLit: boolean
  cellsGraduated: number
  /** island_harbor_crates — dock crates (packs_dirs). */
  dockCrates: number
  /** island_services_mill_row — total/disabled service rows (Works E). */
  millsTotal: number
  millsDisabled: number
  /** Dojo NW: golden_evals_delta_vs_seed ≤ 0 → scarecrow only (honest ≤0). */
  goldenEvalsDelta: number
  /** street_liveliness TEXTURE band from first-keyframe age. */
  streetBand: StreetAgeBand
  /** Plaza paving tier (subagents lifetime — dirt→gravel→cobble→flagstone). */
  plazaTier: GrowthSurface
}

/** Bases mirror cabinet/world/morphology.yml v2 (LAW — change via grammar PR). */
export const GROWTH_BASES = {
  commits_total: 120,
  ev_work_item_completed: 850,
  ev_subagent_completed: 140,
} as const

export function buildGrowth(
  keyframes: CensusKeyframe[],
  firstDate: string | null
): GrowthModel {
  const latest = keyframes.length > 0 ? keyframes[keyframes.length - 1] : undefined
  const prev = keyframes.length > 1 ? keyframes[keyframes.length - 2] : undefined
  const available = latest !== undefined
  const date = typeof latest?.date === 'string' ? latest.date : null
  const crop = surfaceGrowth(prev, latest, 'ev_work_item_completed',
    GROWTH_BASES.ev_work_item_completed)
  return {
    available,
    date,
    radius: landRadius(num(latest, 'org_events_total')),
    hqFloors: surfaceGrowth(prev, latest, 'commits_total', GROWTH_BASES.commits_total),
    officerHouses: num(latest, 'ev_role_defined'),
    fieldPlots: num(latest, 'outcomes_total'),
    cropStage: {
      ...crop,
      tier: Math.min(6, crop.tier),
      pendingTier: crop.pendingTier === null ? null : Math.min(6, crop.pendingTier),
    },
    beaconLit: num(latest, 'cells_graduated') > 0,
    cellsGraduated: num(latest, 'cells_graduated'),
    dockCrates: num(latest, 'packs_dirs'),
    millsTotal: num(latest, 'services_rows_total'),
    millsDisabled: num(latest, 'services_rows_disabled'),
    goldenEvalsDelta: num(latest, 'golden_evals_delta_vs_seed'),
    streetBand: streetAgeBand(ageDays(firstDate, date)),
    plazaTier: surfaceGrowth(prev, latest, 'ev_subagent_completed',
      GROWTH_BASES.ev_subagent_completed),
  }
}
