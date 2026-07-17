/**
 * PER-LANE COURSE STATE — the pure fold behind the chart table and the
 * voyage surface (grammar v4: morphology lane_course_state /
 * harbor_boat_voyage; show-grammar chart_table_view / voyage — per Captain
 * ratifications 2026-07-17).
 *
 * LEDGER-STATE SEMANTICS ONLY (the reduced honest set, declared in the
 * lane_course_state codex):
 *   docked_refitting — ≥1 active outcome: an OPEN WINDOW in the ledger.
 *                      A ledger claim, never a work claim.
 *   tacking          — an achieved flip within TACKING_WINDOW_DAYS (port-calls
 *                      artifact) AND an active successor window.
 *   adrift           — the lane holds a direction with zero active outcomes
 *                      and is not retired: the renewal-loop gap made visible.
 * Whether crew is ACTUALLY working a lane this week is UNMEASURED (no
 * per-lane work signal exists — org_events.product_slug carries only
 * captains-cabinet|default) and renders grey on the card, never a state.
 *
 * PURE by doctrine: no clocks (todayISO arrives as server data through the
 * engine route — the sanctioned clock door), no randomness, no IO. The
 * join universe is berth-declared lanes only: (direction lanes ∪ outcome
 * lanes) ∩ declaredLanes, minus MAIN_ISLAND_LANE (its course IS the main
 * island / chart table), minus retired and instance-test lanes (already
 * honest reef buoys via laneRung). Undeclared pseudo-lanes never get a
 * course.
 */
import { MAIN_ISLAND_LANE, type LaneRecord } from './era-engine'
import type { DirectionsDoc, PortCall, PortCallsArtifact } from './directions'

/** An achieved flip younger than this (inclusive) counts as tacking. */
export const TACKING_WINDOW_DAYS = 14

export type CourseState = 'docked_refitting' | 'tacking' | 'adrift'

export interface LaneCourse {
  lane: string
  state: CourseState
  /** The date the state is anchored to (tacking: the port-call flip date);
   * null when the ledger holds no honest anchor date. */
  since: string | null
  /** Every dated port call this lane has ever made (oldest first). */
  portCallDates: string[]
  /** Whole days since the newest port call, per the server-stamped today;
   * null when the lane has never made port. */
  daysSinceLastPortCall: number | null
}

/** Whole-day difference between two ISO dates (UTC); null if unparseable
 * or negative (a future-dated stamp is not an honest elapsed reading). */
export function daysBetween(fromISO: string, toISO: string): number | null {
  const a = Date.parse(`${fromISO}T00:00:00Z`)
  const b = Date.parse(`${toISO}T00:00:00Z`)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return null
  return Math.floor((b - a) / 86_400_000)
}

export interface CourseInput {
  /** Lane ids carrying a Captain-authored direction (directions.yml). */
  directionLanes: readonly string[]
  /** Per-lane outcome records (instance-lanes outcomeLanes fold). */
  outcomeLanes: Record<string, LaneRecord>
  /** Declared lane universe (contexts/*.yml slugs) — berth law. */
  declaredLanes: readonly string[]
  /** Per-lane port calls from the artifact; null = no artifact on box. */
  portCalls: Record<string, PortCall[]> | null
  /** Server-stamped YYYY-MM-DD (engine route — never a render-path clock). */
  todayISO: string
}

/**
 * The course fold. Returns one LaneCourse per lane that can honestly carry
 * one; lanes with no direction AND no open window are omitted (nothing to
 * plot — their isle/buoy render already tells their story).
 */
export function laneCourseState(input: CourseInput): Record<string, LaneCourse> {
  const declared = new Set(input.declaredLanes)
  const universe = new Set<string>()
  for (const lane of input.directionLanes) universe.add(lane)
  for (const lane of Object.keys(input.outcomeLanes)) universe.add(lane)
  const out: Record<string, LaneCourse> = {}
  for (const lane of [...universe].sort()) {
    if (lane === MAIN_ISLAND_LANE) continue // its course IS the main island
    if (!declared.has(lane)) continue // undeclared pseudo-lanes never berth
    const rec = input.outcomeLanes[lane]
    if (rec?.instanceTest) continue // reef buoy law — never a course
    const retired = rec ? rec.active === 0 && rec.retired > 0 : false
    if (retired) continue // reef buoy law — never a course
    const hasDirection = input.directionLanes.includes(lane)
    const active = rec?.active ?? 0
    const calls = (input.portCalls?.[lane] ?? [])
      .slice()
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    const lastCall = calls.length > 0 ? calls[calls.length - 1].date : null
    const daysSince = lastCall ? daysBetween(lastCall, input.todayISO) : null
    let state: CourseState | null = null
    let since: string | null = null
    if (
      active >= 1 &&
      daysSince !== null &&
      daysSince <= TACKING_WINDOW_DAYS
    ) {
      state = 'tacking' // fresh port call + an active successor window
      since = lastCall
    } else if (active >= 1) {
      state = 'docked_refitting' // open window — a ledger claim only
    } else if (hasDirection) {
      state = 'adrift' // direction present, zero active, not retired
    }
    if (state === null) continue // nothing honest to plot
    out[lane] = {
      lane,
      state,
      since,
      portCallDates: calls.map((c) => c.date),
      daysSinceLastPortCall: daysSince,
    }
  }
  return out
}

// ── voyage render fold (show-grammar v4 voyage law) ─────────────────────────

export interface VoyageRender {
  /** True = the boat renders ON a course line (tacking); false = moored. */
  underway: boolean
  /** The tacking lane the boat sails toward (newest port call wins;
   * deterministic lane-name tie-break). */
  lane: string | null
  /** Pure progress ∈ [0,1] of the out-and-back voyage: flip-day 0 → window
   * end 1 (out at ≤0.5, back at >0.5 — the render folds the triangle). */
  progress: number
}

export function voyageRender(
  courses: Record<string, LaneCourse>
): VoyageRender {
  let best: LaneCourse | null = null
  for (const c of Object.values(courses)) {
    if (c.state !== 'tacking' || c.daysSinceLastPortCall === null) continue
    if (
      !best ||
      c.daysSinceLastPortCall < (best.daysSinceLastPortCall as number) ||
      (c.daysSinceLastPortCall === best.daysSinceLastPortCall &&
        c.lane < best.lane)
    ) {
      best = c
    }
  }
  if (!best) return { underway: false, lane: null, progress: 0 }
  const p = Math.max(
    0,
    Math.min(1, (best.daysSinceLastPortCall as number) / TACKING_WINDOW_DAYS)
  )
  return { underway: true, lane: best.lane, progress: p }
}

// ── chart-table card content (pure — vitest pins the card copy) ─────────────

export interface CardRow {
  label: string
  value: string
  /** True = reserved-palette grey styling (unmeasured ONLY — never data). */
  grey?: boolean
}

export interface ChartTableCard {
  title: string
  nowRows: CardRow[]
  proofLines: string[]
}

/** The exact grey drift-gauge copy (honest-zero law: the missing emitter is
 * NAMED, the gauge never invents a reading). */
export const DRIFT_UNMEASURED_COPY =
  'unmeasured — no per-lane work-distribution signal exists yet ' +
  '(org_events.product_slug carries only captains-cabinet|default)'

/**
 * Build the direction-chart card content (WHAT arrives separately as the
 * manor_chart_table codex from the grammar feed). Free text — apex mission,
 * lane names, dates — lives ONLY in this authed card, never world-space.
 */
export function buildChartTableCard(
  directions: DirectionsDoc | null,
  courses: Record<string, LaneCourse>,
  portCalls: PortCallsArtifact | null
): ChartTableCard {
  const nowRows: CardRow[] = []
  if (directions?.apex) {
    nowRows.push({ label: 'apex', value: directions.apex.mission })
    if (directions.apex.instruments.length > 0) {
      nowRows.push({
        label: 'apex instruments',
        value: directions.apex.instruments.join(', '),
      })
    }
  } else {
    nowRows.push({
      label: 'apex',
      value:
        "uncharted — this deployment's directions.yml carries no org: apex block " +
        '(honest absence, never an invented direction)',
      grey: true,
    })
  }
  for (const lane of Object.keys(courses).sort()) {
    const c = courses[lane]
    nowRows.push({
      label: `course · ${lane}`,
      value:
        `${c.state}` +
        (c.since ? ` · since ${c.since}` : '') +
        ` · port calls ${c.portCallDates.length}`,
    })
  }
  // directions with no plottable course still surface (adrift is computed in
  // the fold; a direction lane missing from courses means it was excluded by
  // berth law — say so rather than render nothing).
  for (const lane of Object.keys(directions?.lanes ?? {}).sort()) {
    if (lane === MAIN_ISLAND_LANE || courses[lane]) continue
    nowRows.push({
      label: `course · ${lane}`,
      value: 'no berth on this deployment (undeclared or reef-buoy lane)',
      grey: true,
    })
  }
  nowRows.push({ label: 'drift', value: DRIFT_UNMEASURED_COPY, grey: true })

  const proofLines: string[] = []
  if (portCalls) {
    for (const lane of Object.keys(portCalls.lanes).sort()) {
      const calls = portCalls.lanes[lane]
      if (calls.length === 0) continue
      proofLines.push(
        `${lane}: ${calls.map((c) => `${c.date} (${c.outcome_id})`).join(', ')}`
      )
    }
    proofLines.push(
      `as-of: port-calls artifact generated_at ${portCalls.generated_at ?? '—'}` +
        ` · source_git_head ${portCalls.source_git_head ?? '—'}` +
        ' · replay = git (regenerate world-port-calls.py and diff)'
    )
  } else {
    proofLines.push(
      'no port-calls artifact on this box — stamps absent ' +
        '(run cabinet/scripts/world-port-calls.py; honest absence, not an error)'
    )
  }
  return { title: 'chart table — the direction surface', nowRows, proofLines }
}
