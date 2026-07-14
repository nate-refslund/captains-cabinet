/**
 * ERA × RUNG growth engine — the TS twin of the calibrated replay math in
 * cabinet/scripts/world-growth-backtest.py (WORLD-GROWTH-CALIBRATION gate),
 * consuming cabinet/world/growth-ladders.yml as DATA.
 *
 * Spec of record: docs/plans/world-unified-spec-v2-2026-07-09.md §15.1–15.4
 * (Captain addendum 2 — balance made structural):
 *  - ERA: one org-maturity index over a weighted basket of REAL metrics
 *    gates WHICH vocabulary everything renders with (torches before
 *    streetlights) — with mandatory advance/demote hysteresis.
 *  - RUNG: within the era, each element's magnitude tracks its OWN real
 *    metric (tier/count/flag/per_lane modes) under hold-eval hysteresis.
 *  - UNMEASURED: a metric with no real measurement renders its baseline
 *    rung and is flagged — never interpolated, never invented.
 *
 * PURE by doctrine: no clocks, no randomness, no IO. The server-side
 * loader (ladders-loader.ts) owns the file read + hot-reload; this module
 * owns validation + resolution only, so vitest pins the math exactly.
 */

export type Curve = 'linear' | 'log2' | 'log10'
export type LadderMode = 'tier' | 'count' | 'flag' | 'per_lane'

export interface EraBasketSpec {
  weight: number
  curve: Curve
  cap: number
  /** Named real feed (census_keyframe / outcomes_yml / …) — provenance. */
  source: string
}

export interface EraConfig {
  names: string[]
  basket: Record<string, EraBasketSpec>
  thresholds: Record<string, number>
  hysteresis: { advance_hold_evals: number; demote_margin: number }
}

export interface LadderSpec {
  metric: string
  source: string
  mode: LadderMode
  /** log2 tier base (mode=tier). Grammar-PR constant. */
  base?: number
  /** flag threshold (mode=flag, default 1). */
  at?: number
  rungs: string[]
  hysteresis_evals?: number
  class?: string
  /** ERA → sprite-family vocabulary (era styles, rung measures). */
  vocab?: Record<string, string>
}

export interface GrowthLaddersConfig {
  schema: string
  version?: number
  era: EraConfig
  ladders: Record<string, LadderSpec>
}

/**
 * The org's own lane — the main island itself. Framework vocabulary (every
 * instance has a system-self lane: the org working on the org), NOT instance
 * data, so it is the one lane name allowed in shared world code. It never
 * earns an isle berth and the per_lane engine loop skips it.
 */
export const MAIN_ISLAND_LANE = 'system-self'

/** Per-lane record derived from outcomes.yml (v1 isle-ring feed). */
export interface LaneRecord {
  ever: number
  active: number
  achieved: number
  retired: number
  /**
   * Captain ruling 2026-07-09: instance-only test lanes ('sensed') are
   * NEVER foundation — they render as reef-buoys regardless of outcomes.
   */
  instanceTest?: boolean
}

// ── validation (fail-closed: a malformed config resolves to null) ──────────

const SCHEMA_ID = 'cabinet.world.growth-ladders/v1'

export function validateGrowthLadders(doc: unknown): {
  config: GrowthLaddersConfig | null
  problems: string[]
} {
  const problems: string[] = []
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    return { config: null, problems: ['config is not a mapping'] }
  }
  const d = doc as Record<string, unknown>
  if (d.schema !== SCHEMA_ID) {
    problems.push(`schema must be ${SCHEMA_ID} (got ${String(d.schema)})`)
  }
  const era = d.era as EraConfig | undefined
  if (!era || !Array.isArray(era.names) || era.names.length < 2) {
    problems.push('era.names missing or too short')
  }
  if (era?.basket && typeof era.basket === 'object') {
    let sum = 0
    for (const [m, spec] of Object.entries(era.basket)) {
      if (typeof spec.weight !== 'number' || spec.weight <= 0) {
        problems.push(`era.basket.${m}.weight must be > 0`)
      } else sum += spec.weight
      if (!['linear', 'log2', 'log10'].includes(spec.curve)) {
        problems.push(`era.basket.${m}.curve unknown: ${String(spec.curve)}`)
      }
      if (typeof spec.cap !== 'number' || spec.cap <= 0) {
        problems.push(`era.basket.${m}.cap must be > 0`)
      }
      if (typeof spec.source !== 'string' || spec.source.length === 0) {
        problems.push(`era.basket.${m}.source must cite a real feed`)
      }
    }
    if (Math.abs(sum - 1) > 0.001) {
      problems.push(`era.basket weights must sum to 1.0 (got ${sum.toFixed(3)})`)
    }
  } else {
    problems.push('era.basket missing')
  }
  if (era?.thresholds && era.names) {
    for (const name of era.names) {
      if (typeof era.thresholds[name] !== 'number') {
        problems.push(`era.thresholds.${name} missing`)
      }
    }
  } else {
    problems.push('era.thresholds missing')
  }
  const hys = era?.hysteresis
  if (
    !hys ||
    typeof hys.advance_hold_evals !== 'number' ||
    hys.advance_hold_evals < 1 ||
    typeof hys.demote_margin !== 'number'
  ) {
    problems.push('era.hysteresis malformed (advance_hold_evals ≥ 1 + demote_margin required)')
  }
  const ladders = d.ladders as Record<string, LadderSpec> | undefined
  if (!ladders || typeof ladders !== 'object' || Object.keys(ladders).length === 0) {
    problems.push('ladders missing')
  } else {
    for (const [name, lad] of Object.entries(ladders)) {
      if (typeof lad.metric !== 'string' || lad.metric.length === 0) {
        problems.push(`ladders.${name}.metric must cite a real field`)
      }
      if (typeof lad.source !== 'string' || lad.source.length === 0) {
        problems.push(`ladders.${name}.source must cite a real feed`)
      }
      if (!['tier', 'count', 'flag', 'per_lane'].includes(lad.mode)) {
        problems.push(`ladders.${name}.mode unknown: ${String(lad.mode)}`)
      }
      if (!Array.isArray(lad.rungs) || lad.rungs.length < 1) {
        problems.push(`ladders.${name}.rungs missing`)
      }
      if (lad.mode === 'tier' && (typeof lad.base !== 'number' || lad.base <= 0)) {
        problems.push(`ladders.${name}.base must be > 0 for mode=tier`)
      }
      if (lad.mode === 'flag' && lad.rungs && lad.rungs.length !== 2) {
        problems.push(`ladders.${name}: mode=flag needs exactly 2 rungs`)
      }
    }
  }
  if (problems.length > 0) return { config: null, problems }
  return { config: d as unknown as GrowthLaddersConfig, problems: [] }
}

// ── basket → maturity index ────────────────────────────────────────────────

/** norm: linear = min(v/cap, 1); logN = min(logN(v+1)/logN(cap+1), 1). */
export function normMetric(v: number | null, curve: Curve, cap: number): number {
  if (v === null || !Number.isFinite(v) || v <= 0) return 0
  if (curve === 'linear') return Math.min(v / cap, 1)
  if (curve === 'log2') return Math.min(Math.log2(v + 1) / Math.log2(cap + 1), 1)
  return Math.min(Math.log10(v + 1) / Math.log10(cap + 1), 1)
}

export interface EraIndexResult {
  index: number
  norms: Record<string, number>
  /** Metrics absent from the input (unmeasured — contributed 0, flagged). */
  unmeasured: string[]
}

export function eraIndex(
  metrics: Record<string, number | null>,
  era: EraConfig
): EraIndexResult {
  let index = 0
  const norms: Record<string, number> = {}
  const unmeasured: string[] = []
  for (const [metric, spec] of Object.entries(era.basket)) {
    const v = metric in metrics ? metrics[metric] : null
    if (v === null || v === undefined) unmeasured.push(metric)
    const nv = normMetric(v ?? null, spec.curve, spec.cap)
    norms[metric] = nv
    index += nv * spec.weight
  }
  return { index, norms, unmeasured }
}

// ── era state machine (mandatory hysteresis, advance AND demote) ───────────

export interface EraState {
  eraIdx: number
  advStreak: number
  demStreak: number
}

export function initialEraState(): EraState {
  return { eraIdx: 0, advStreak: 0, demStreak: 0 }
}

export interface EraStepResult {
  state: EraState
  era: string
  transition: { from: string; to: string; demotion?: boolean } | null
}

/** One eval step (e.g. one daily keyframe) of the era machine. */
export function eraStep(state: EraState, index: number, era: EraConfig): EraStepResult {
  const names = era.names
  const hold = Math.max(1, era.hysteresis.advance_hold_evals)
  const margin = era.hysteresis.demote_margin
  let { eraIdx, advStreak, demStreak } = state
  if (eraIdx + 1 < names.length && index >= era.thresholds[names[eraIdx + 1]]) {
    advStreak += 1
  } else {
    advStreak = 0
  }
  if (eraIdx > 0 && index < era.thresholds[names[eraIdx]] - margin) {
    demStreak += 1
  } else {
    demStreak = 0
  }
  let transition: EraStepResult['transition'] = null
  if (advStreak >= hold) {
    transition = { from: names[eraIdx], to: names[eraIdx + 1] }
    eraIdx += 1
    advStreak = 0
  } else if (demStreak >= hold) {
    transition = { from: names[eraIdx], to: names[eraIdx - 1], demotion: true }
    eraIdx -= 1
    demStreak = 0
  }
  return { state: { eraIdx, advStreak, demStreak }, era: names[eraIdx], transition }
}

// ── rung resolution (tier / count / flag / per_lane) ───────────────────────

/** Raw (pre-hysteresis) rung for a measured value; null = unmeasured. */
export function rawRung(lad: LadderSpec, v: number | null): number | null {
  if (v === null || !Number.isFinite(v)) return null
  const nr = lad.rungs.length
  if (lad.mode === 'tier') {
    if (v <= 0) return 0
    const base = lad.base as number
    return Math.max(0, Math.min(Math.floor(Math.log2(v / base + 1)), nr - 1))
  }
  if (lad.mode === 'count') return Math.max(0, Math.min(Math.floor(v), nr - 1))
  if (lad.mode === 'flag') return v >= (lad.at ?? 1) ? 1 : 0
  throw new Error(`rawRung does not resolve mode=${lad.mode} (use laneRung)`)
}

/**
 * v1 isle rings from outcomes.yml only (per_lane mode):
 * reef 0 / dock r0=1 / warehouses r1=2 (r2/r3 gated on P3/P5 feeds).
 * Retired lanes AND instance-test lanes → reef_buoy (Captain ruling
 * 2026-07-09: honest marker; inspect card says retired/instance).
 */
export function laneRung(rec: LaneRecord | null | undefined): number {
  if (!rec || rec.ever === 0) return 0
  if (rec.instanceTest) return 0
  if (rec.active === 0 && rec.retired > 0) return 0
  return rec.achieved >= 1 ? 2 : 1
}

/** Hysteresis holder — a candidate rung must persist `evals` consecutive
 * evals before the VISIBLE rung moves (the 24h crewed scaffold shows the
 * wait). Twin of backtest _Hold. */
export interface HoldState {
  visible: number | null
  cand: number | null
  streak: number
}

export function initialHold(): HoldState {
  return { visible: null, cand: null, streak: 0 }
}

export function holdStep(h: HoldState, raw: number | null, evals: number): HoldState {
  const need = Math.max(1, evals)
  if (raw === null) return h
  if (h.visible === null) return { visible: raw, cand: null, streak: 0 }
  if (raw === h.visible) return { visible: h.visible, cand: null, streak: 0 }
  const streak = raw === h.cand ? h.streak + 1 : 1
  if (streak >= need) return { visible: raw, cand: null, streak: 0 }
  return { visible: h.visible, cand: raw, streak }
}

// ── whole-world resolution over an eval sequence ───────────────────────────

export interface EngineState {
  era: EraState
  holds: Record<string, HoldState>
  laneHolds: Record<string, HoldState>
}

export function initialEngineState(): EngineState {
  return { era: initialEraState(), holds: {}, laneHolds: {} }
}

export interface EngineEval {
  /** Real metric values for this eval (absent/null = unmeasured). */
  metrics: Record<string, number | null>
  /** Per-lane outcome records (per_lane ladders). */
  lanes?: Record<string, LaneRecord>
}

export interface ElementResolution {
  /** Visible rung index (post-hysteresis); baseline 0 when unmeasured. */
  rung: number
  rungName: string
  /** Era-selected sprite family for this element (vocab law §15.2). */
  vocab: string | null
  /** Incoming rung held back by hysteresis (scaffold overlay), or null. */
  pending: number | null
  /** False = no real measurement yet → grey "unmeasured" card, never
   * interpolated. */
  measured: boolean
  /** Raw metric value cited on the inspect card (null = unmeasured). */
  value: number | null
}

export interface WorldResolution {
  era: string
  eraIndex: number
  /** Basket metrics with no measurement this eval. */
  eraUnmeasured: string[]
  transition: EraStepResult['transition']
  elements: Record<string, ElementResolution>
  /** per_lane ladders: lane → visible ring rung. */
  lanes: Record<string, { rung: number; rungName: string }>
}

/**
 * One engine eval: feed a keyframe-shaped observation, get the resolved
 * world. Deterministic reducer — identical eval sequences resolve
 * identically forever (vitest replays exactly this).
 */
export function engineStep(
  state: EngineState,
  ev: EngineEval,
  config: GrowthLaddersConfig
): { state: EngineState; out: WorldResolution } {
  const { index, unmeasured } = eraIndex(ev.metrics, config.era)
  const eraRes = eraStep(state.era, index, config.era)
  const holds: Record<string, HoldState> = { ...state.holds }
  const laneHolds: Record<string, HoldState> = { ...state.laneHolds }
  const elements: Record<string, ElementResolution> = {}
  const lanesOut: Record<string, { rung: number; rungName: string }> = {}

  for (const [name, lad] of Object.entries(config.ladders)) {
    if (lad.mode === 'per_lane') {
      const lanes = ev.lanes ?? {}
      for (const lane of Object.keys(lanes).sort()) {
        if (lane === MAIN_ISLAND_LANE) continue // system-self IS the main island
        const h = laneHolds[lane] ?? initialHold()
        const next = holdStep(h, laneRung(lanes[lane]), lad.hysteresis_evals ?? 2)
        laneHolds[lane] = next
        const rung = next.visible ?? 0
        lanesOut[lane] = { rung, rungName: lad.rungs[rung] }
      }
      continue
    }
    const v = lad.metric in ev.metrics ? ev.metrics[lad.metric] : null
    const raw = rawRung(lad, v ?? null)
    const h = holds[name] ?? initialHold()
    const next = holdStep(h, raw, lad.hysteresis_evals ?? 2)
    holds[name] = next
    const visible = next.visible ?? 0
    elements[name] = {
      rung: visible,
      rungName: lad.rungs[visible],
      vocab: lad.vocab?.[eraRes.era] ?? null,
      pending: next.cand !== null && next.cand > visible ? next.cand : null,
      measured: next.visible !== null,
      value: v ?? null,
    }
  }

  return {
    state: { era: eraRes.state, holds, laneHolds },
    out: {
      era: eraRes.era,
      eraIndex: index,
      eraUnmeasured: unmeasured,
      transition: eraRes.transition,
      elements,
      lanes: lanesOut,
    },
  }
}
