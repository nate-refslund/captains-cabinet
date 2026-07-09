/**
 * T2 LIFE — fail-closed parser for the show-grammar.yml v3 LIFE blocks
 * (grammar-as-law: the yml entries land via the feat/world-grammar-v3 PR
 * the Captain merges; until then every block parses ABSENT and the
 * corresponding behavior stays OFF — no pixels without law).
 *
 * Block shapes this parser defines (the contract the grammar PR fulfils —
 * closed enums, codex required, values are grammar-PR constants):
 *
 *   commute:
 *     window_s: 150            # dominant-focus window
 *     half_life_s: 75          # recency weight half-life
 *     eval_every_s: 15         # classifier cadence
 *     switch_share: 0.6        # hysteresis share threshold
 *     switch_evals: 2          # consecutive evaluations required
 *     min_dwell_s: 180         # min dwell since arrival
 *     bubble: pixel            # closed enum — the bubble is pixel, not DOM
 *     codex: {represents, mechanism_path, day0}
 *
 *   sites:
 *     quick_small_min: 15
 *     quick_large_min: 90
 *     great_h: 24
 *     crew_base: 4             # footprint-tier base (crew = 1 + tier)
 *     codex: {…}
 *
 *   fauna:
 *     kinds: [bird, butterfly, fish, cat, dog]   # closed enum subset
 *     day_only: [bird, butterfly]
 *     codex: {…}               # "carries no data — exists for joy"
 *
 *   apprentices:
 *     spawn_verb: tool.call
 *     spawn_tools: [Agent, Task]
 *     end_verb: crew.completed
 *     ttl_ticks: 4800
 *     cap: 4
 *     codex: {…}
 *
 * Server-side only (mirrors grammar.ts: reads repo files; the client gets
 * parsed data through the existing authed GET routes). Malformed block →
 * problem + OFF; unknown keys inside a block are ignored-with-problem.
 */
import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import { GRAMMAR_DIR, type GrammarCodex } from '../grammar'

export interface CommuteGrammar {
  windowS: number
  halfLifeS: number
  evalEveryS: number
  switchShare: number
  switchEvals: number
  minDwellS: number
  bubble: 'pixel'
  codex?: GrammarCodex
}

export interface SitesGrammar {
  quickSmallMin: number
  quickLargeMin: number
  greatH: number
  crewBase: number
  codex?: GrammarCodex
}

export type FaunaKindName = 'bird' | 'butterfly' | 'fish' | 'cat' | 'dog'

export interface FaunaGrammar {
  kinds: FaunaKindName[]
  dayOnly: FaunaKindName[]
  codex?: GrammarCodex
}

export interface ApprenticeGrammar {
  spawnVerb: string
  spawnTools: string[]
  endVerb: string
  ttlTicks: number
  cap: number
  codex?: GrammarCodex
}

export interface LifeGrammar {
  commute?: CommuteGrammar
  sites?: SitesGrammar
  fauna?: FaunaGrammar
  apprentices?: ApprenticeGrammar
  problems: string[]
}

const FAUNA_KINDS = new Set(['bird', 'butterfly', 'fish', 'cat', 'dog'])

function parseCodex(raw: unknown): GrammarCodex | undefined {
  if (typeof raw !== 'object' || raw === null) return undefined
  const c = raw as Record<string, unknown>
  if (
    typeof c.represents === 'string' &&
    typeof c.mechanism_path === 'string' &&
    typeof c.day0 === 'string'
  ) {
    return {
      represents: c.represents,
      mechanism_path: c.mechanism_path,
      day0: c.day0,
    }
  }
  return undefined
}

function num(v: unknown, min: number): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v >= min ? v : null
}

function parseCommute(raw: unknown, problems: string[]): CommuteGrammar | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('commute: not a mapping')
    return undefined
  }
  const d = raw as Record<string, unknown>
  const windowS = num(d.window_s, 1)
  const halfLifeS = num(d.half_life_s, 1)
  const evalEveryS = num(d.eval_every_s, 1)
  const switchShare = num(d.switch_share, 0.5) // <0.5 could not be dominant
  const switchEvals = num(d.switch_evals, 1)
  const minDwellS = num(d.min_dwell_s, 0)
  if (
    windowS === null ||
    halfLifeS === null ||
    evalEveryS === null ||
    switchShare === null ||
    switchShare > 1 ||
    switchEvals === null ||
    minDwellS === null
  ) {
    problems.push('commute: missing/invalid window_s|half_life_s|eval_every_s|switch_share|switch_evals|min_dwell_s')
    return undefined
  }
  if (d.bubble !== 'pixel') {
    // Closed enum: the Captain's T2 ruling — pixel bubble, never DOM.
    problems.push('commute: bubble must be "pixel" (closed enum)')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('commute: codex missing/incomplete')
  return {
    windowS,
    halfLifeS,
    evalEveryS,
    switchShare,
    switchEvals,
    minDwellS,
    bubble: 'pixel',
    codex,
  }
}

function parseSites(raw: unknown, problems: string[]): SitesGrammar | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('sites: not a mapping')
    return undefined
  }
  const d = raw as Record<string, unknown>
  const quickSmallMin = num(d.quick_small_min, 1)
  const quickLargeMin = num(d.quick_large_min, 1)
  const greatH = num(d.great_h, 1)
  const crewBase = num(d.crew_base, 1)
  if (
    quickSmallMin === null ||
    quickLargeMin === null ||
    greatH === null ||
    crewBase === null
  ) {
    problems.push('sites: missing/invalid quick_small_min|quick_large_min|great_h|crew_base')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('sites: codex missing/incomplete')
  return { quickSmallMin, quickLargeMin, greatH, crewBase, codex }
}

function parseFauna(raw: unknown, problems: string[]): FaunaGrammar | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('fauna: not a mapping')
    return undefined
  }
  const d = raw as Record<string, unknown>
  const kindsRaw = Array.isArray(d.kinds) ? d.kinds : null
  if (!kindsRaw || kindsRaw.length === 0) {
    problems.push('fauna: kinds missing/empty')
    return undefined
  }
  const kinds: FaunaKindName[] = []
  for (const k of kindsRaw) {
    if (typeof k === 'string' && FAUNA_KINDS.has(k)) {
      kinds.push(k as FaunaKindName)
    } else {
      // Closed enum: a stranger species is refused, never rendered.
      problems.push(`fauna: unknown kind ${String(k)} (closed enum)`)
    }
  }
  if (kinds.length === 0) return undefined
  const dayOnly: FaunaKindName[] = []
  for (const k of Array.isArray(d.day_only) ? d.day_only : []) {
    if (typeof k === 'string' && kinds.includes(k as FaunaKindName)) {
      dayOnly.push(k as FaunaKindName)
    } else {
      problems.push(`fauna: day_only kind ${String(k)} not in kinds`)
    }
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('fauna: codex missing/incomplete')
  return { kinds, dayOnly, codex }
}

function parseApprentices(
  raw: unknown,
  problems: string[]
): ApprenticeGrammar | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('apprentices: not a mapping')
    return undefined
  }
  const d = raw as Record<string, unknown>
  const spawnVerb = typeof d.spawn_verb === 'string' ? d.spawn_verb : null
  const endVerb = typeof d.end_verb === 'string' ? d.end_verb : null
  const ttlTicks = num(d.ttl_ticks, 1)
  const cap = num(d.cap, 1)
  const spawnTools = Array.isArray(d.spawn_tools)
    ? d.spawn_tools.filter((t): t is string => typeof t === 'string')
    : []
  if (!spawnVerb || !endVerb || ttlTicks === null || cap === null || spawnTools.length === 0) {
    problems.push('apprentices: missing/invalid spawn_verb|spawn_tools|end_verb|ttl_ticks|cap')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('apprentices: codex missing/incomplete')
  return { spawnVerb, spawnTools, endVerb, ttlTicks, cap, codex }
}

/** Parse the LIFE blocks out of a show-grammar.yml text (pure — testable). */
export function parseLifeGrammar(text: string): LifeGrammar {
  const problems: string[] = []
  let doc: unknown
  try {
    doc = yaml.load(text, { schema: yaml.JSON_SCHEMA })
  } catch (e) {
    return { problems: [`show-grammar.yml unparseable: ${String(e).slice(0, 120)}`] }
  }
  if (typeof doc !== 'object' || doc === null) {
    return { problems: ['show-grammar.yml is not a mapping'] }
  }
  const d = doc as Record<string, unknown>
  return {
    commute: parseCommute(d.commute, problems),
    sites: parseSites(d.sites, problems),
    fauna: parseFauna(d.fauna, problems),
    apprentices: parseApprentices(d.apprentices, problems),
    problems,
  }
}

/** Load from disk (server-side; absent file → everything OFF, honestly). */
export function loadLifeGrammar(): LifeGrammar {
  try {
    const p = path.join(GRAMMAR_DIR(), 'show-grammar.yml')
    if (!fs.existsSync(p)) return { problems: ['show-grammar.yml absent'] }
    return parseLifeGrammar(fs.readFileSync(p, 'utf8'))
  } catch (e) {
    return { problems: [`show-grammar read failed: ${String(e).slice(0, 120)}`] }
  }
}
