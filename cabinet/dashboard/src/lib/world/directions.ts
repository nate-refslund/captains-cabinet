/**
 * DIRECTION-LAYER READERS (server-side) — the dashboard's fold over the
 * Captain-owned direction surface (grammar v4, per Captain ratifications
 * 2026-07-17):
 *
 *  - readDirections(): instance/config/directions.yml → the org apex
 *    direction (`org: apex:` block, Captain-ratified 2026-07-17) + the
 *    per-lane direction map. Framework consumers fold only the
 *    `directions:` key (action_lane.py) — the apex block is additive and
 *    read ONLY here.
 *  - readPortCalls(): shared/interfaces/world/port-calls.json — the
 *    rebuildable runtime read-model cabinet/scripts/world-port-calls.py
 *    materializes from outcomes.yml git history (replay = git).
 *
 * FAIL-HONEST (instance-lanes.ts law): every reader degrades to an EMPTY /
 * null result on unreadable or malformed input — consumers then render
 * honest absence (an 'uncharted' card, no stamps, a moored boat) — never an
 * invented default. No network, no exec, fixed repo paths under `root`
 * (js-yaml JSON_SCHEMA safe parsing; Corridor: no user-supplied path
 * segments).
 */
import fs from 'node:fs'
import path from 'node:path'
import yaml from 'js-yaml'

export interface DirectionSpec {
  mission: string
  instruments: string[]
}

export interface DirectionsDoc {
  /** The org apex direction; null = uncharted (deployments whose instance
   * overlay lacks the org: block degrade to an honest 'uncharted' card). */
  apex: DirectionSpec | null
  /** Captain-authored per-lane directions keyed by lane id. */
  lanes: Record<string, DirectionSpec>
}

function specOf(raw: unknown): DirectionSpec | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  if (typeof r.mission !== 'string' || r.mission.trim().length === 0) return null
  const instruments = Array.isArray(r.instruments)
    ? r.instruments.filter((v): v is string => typeof v === 'string' && v.length > 0)
    : []
  return { mission: r.mission.trim(), instruments }
}

/** Fold instance/config/directions.yml. Missing file, missing org: block,
 * or malformed YAML all degrade honestly (apex: null / lanes: {}). */
export function readDirections(root: string): DirectionsDoc {
  const empty: DirectionsDoc = { apex: null, lanes: {} }
  let doc: Record<string, unknown>
  try {
    const raw = fs.readFileSync(
      path.join(root, 'instance', 'config', 'directions.yml'),
      'utf8'
    )
    const parsed = yaml.load(raw, { schema: yaml.JSON_SCHEMA }) ?? {}
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return empty
    }
    doc = parsed as Record<string, unknown>
  } catch {
    return empty // honest absence: uncharted
  }
  const lanes: Record<string, DirectionSpec> = {}
  const dirs = doc.directions
  if (typeof dirs === 'object' && dirs !== null && !Array.isArray(dirs)) {
    for (const [lane, rawSpec] of Object.entries(dirs as Record<string, unknown>)) {
      const spec = specOf(rawSpec)
      if (spec) lanes[lane] = spec
    }
  }
  let apex: DirectionSpec | null = null
  const org = doc.org
  if (typeof org === 'object' && org !== null && !Array.isArray(org)) {
    apex = specOf((org as Record<string, unknown>).apex)
  }
  return { apex, lanes }
}

// ── port-calls artifact ─────────────────────────────────────────────────────

export const PORT_CALLS_SCHEMA = 'cabinet.world.port-calls/v1'

export interface PortCall {
  date: string
  outcome_id: string
}

export interface PortCallsArtifact {
  schema: string
  generated_at: string | null
  source_git_head: string | null
  port_calls_total: number
  last_port_call_date: string | null
  lanes: Record<string, PortCall[]>
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Read shared/interfaces/world/port-calls.json (readSiteLedger pattern:
 * fixed path, fail-honest). null = no artifact on this box — the honest
 * state for a deployment where world-port-calls.py has never run: no
 * stamps render, the boat stays moored, the card says so. Malformed rows
 * are skipped, never guessed.
 */
export function readPortCalls(root: string): PortCallsArtifact | null {
  try {
    const p = path.join(root, 'shared', 'interfaces', 'world', 'port-calls.json')
    if (!fs.existsSync(p)) return null
    const parsed: unknown = JSON.parse(fs.readFileSync(p, 'utf8'))
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return null
    }
    const d = parsed as Record<string, unknown>
    if (d.schema !== PORT_CALLS_SCHEMA) return null
    const lanes: Record<string, PortCall[]> = {}
    const rawLanes =
      typeof d.lanes === 'object' && d.lanes !== null && !Array.isArray(d.lanes)
        ? (d.lanes as Record<string, unknown>)
        : {}
    for (const [lane, rawCalls] of Object.entries(rawLanes)) {
      if (!Array.isArray(rawCalls)) continue
      const calls: PortCall[] = []
      for (const rawCall of rawCalls) {
        if (typeof rawCall !== 'object' || rawCall === null) continue
        const c = rawCall as Record<string, unknown>
        if (
          typeof c.date === 'string' &&
          ISO_DATE_RE.test(c.date) &&
          typeof c.outcome_id === 'string' &&
          c.outcome_id.length > 0
        ) {
          calls.push({ date: c.date, outcome_id: c.outcome_id })
        }
      }
      lanes[lane] = calls
    }
    const derivedTotal = Object.values(lanes).reduce((n, v) => n + v.length, 0)
    return {
      schema: PORT_CALLS_SCHEMA,
      generated_at: typeof d.generated_at === 'string' ? d.generated_at : null,
      source_git_head:
        typeof d.source_git_head === 'string' ? d.source_git_head : null,
      port_calls_total:
        typeof d.port_calls_total === 'number' &&
        Number.isFinite(d.port_calls_total)
          ? d.port_calls_total
          : derivedTotal,
      last_port_call_date:
        typeof d.last_port_call_date === 'string' &&
        ISO_DATE_RE.test(d.last_port_call_date)
          ? d.last_port_call_date
          : null,
      lanes,
    }
  } catch {
    return null // honest absence, never an invented voyage
  }
}
