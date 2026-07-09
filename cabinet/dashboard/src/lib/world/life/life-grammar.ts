/**
 * T2 LIFE — fail-closed parser for the show-grammar.yml v3 LIFE blocks
 * (grammar-as-law: the yml entries ride the feat/world-grammar-v3 PR,
 * Captain-ratified 2026-07-09; until that file is present every block
 * parses ABSENT and the corresponding behavior stays OFF — no pixels
 * without law).
 *
 * The shapes below mirror the RATIFIED grammar v3 blocks byte-for-byte
 * (branch feat/world-grammar-v3, commit "world: grammar v3 — the living
 * island"):
 *
 *   commute:
 *     switch_share: 0.6
 *     switch_evals: 2
 *     dwell_s: 180
 *     walk_s: [20, 30]          # duration band — distance ÷ speed lands here
 *     bubble: verb_icon         # closed enum — the bubble renders the verb's
 *                               # ICON only; never free text in world-space
 *     codex: {represents, mechanism_path, day0}
 *
 *   construction:
 *     quick_small_min: 15
 *     quick_large_min: 90
 *     great_hours: 24
 *     phases: {clearing: 0.25, raising: 0.75, finishing: 1.0}
 *     site_ledger: shared/interfaces/world-sites.jsonl
 *     codex: {…}
 *
 *   fauna:                      # per-species maps, every one decorative
 *     <species>: {home, decorative: true, codex}
 *
 *   apprentices:
 *     cap_per_officer: 3
 *     codex: {…}
 *
 * Server-side only (mirrors grammar.ts: reads repo files; the client gets
 * parsed data through the existing authed GET routes). Malformed block →
 * problem + OFF; closed enums refused loudly.
 */
import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import { GRAMMAR_DIR, type GrammarCodex } from '../grammar'

export interface CommuteGrammar {
  switchShare: number
  switchEvals: number
  dwellS: number
  /** Commute duration band in seconds [min, max]. */
  walkS: [number, number]
  /** Closed enum: the world-space bubble is the verb's pixel ICON only. */
  bubble: 'verb_icon'
  codex?: GrammarCodex
}

export interface ConstructionGrammar {
  quickSmallMin: number
  quickLargeMin: number
  greatHours: number
  phases: { clearing: number; raising: number; finishing: number }
  siteLedger: string | null
  codex?: GrammarCodex
}

export interface FaunaSpeciesGrammar {
  home: string
  decorative: true
  /**
   * STAGED scope (grammar v3 amendment, 2026-07-09): true = the species'
   * pack art is not installed yet, so the renderer draws NOTHING for it —
   * grammar and render stay truth-aligned (no invented pixels, no untrue
   * day0 claims) until the art lands in the world-asset manifest.
   */
  staged?: boolean
  codex?: GrammarCodex
}

export interface ApprenticeGrammar {
  capPerOfficer: number
  codex?: GrammarCodex
}

export interface LifeGrammar {
  commute?: CommuteGrammar
  construction?: ConstructionGrammar
  /** species name → entry (closed to what the law names; renderer maps
   * species → sprite kinds). */
  fauna?: Record<string, FaunaSpeciesGrammar>
  apprentices?: ApprenticeGrammar
  problems: string[]
}

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
  const switchShare = num(d.switch_share, 0.5) // <0.5 could not be dominant
  const switchEvals = num(d.switch_evals, 1)
  const dwellS = num(d.dwell_s, 0)
  if (
    switchShare === null ||
    switchShare > 1 ||
    switchEvals === null ||
    dwellS === null
  ) {
    problems.push('commute: missing/invalid switch_share|switch_evals|dwell_s')
    return undefined
  }
  const w = d.walk_s
  const walkS: [number, number] | null =
    Array.isArray(w) &&
    w.length === 2 &&
    typeof w[0] === 'number' &&
    typeof w[1] === 'number' &&
    w[0] > 0 &&
    w[1] >= w[0]
      ? [w[0], w[1]]
      : null
  if (!walkS) {
    problems.push('commute: walk_s must be an ascending [min_s, max_s] band')
    return undefined
  }
  if (d.bubble !== 'verb_icon') {
    // Closed enum (ratified law): the bubble is the verb's pixel ICON —
    // never free text in world-space, never a DOM chip.
    problems.push('commute: bubble must be "verb_icon" (closed enum)')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('commute: codex missing/incomplete')
  return { switchShare, switchEvals, dwellS, walkS, bubble: 'verb_icon', codex }
}

function parseConstruction(
  raw: unknown,
  problems: string[]
): ConstructionGrammar | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('construction: not a mapping')
    return undefined
  }
  const d = raw as Record<string, unknown>
  const quickSmallMin = num(d.quick_small_min, 1)
  const quickLargeMin = num(d.quick_large_min, 1)
  const greatHours = num(d.great_hours, 1)
  if (quickSmallMin === null || quickLargeMin === null || greatHours === null) {
    problems.push('construction: missing/invalid quick_small_min|quick_large_min|great_hours')
    return undefined
  }
  const p = (d.phases ?? {}) as Record<string, unknown>
  const clearing = num(p.clearing, 0)
  const raising = num(p.raising, 0)
  const finishing = num(p.finishing, 0)
  if (
    clearing === null ||
    raising === null ||
    finishing === null ||
    !(clearing < raising && raising < finishing && finishing <= 1)
  ) {
    problems.push('construction: phases must ascend clearing < raising < finishing ≤ 1')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('construction: codex missing/incomplete')
  return {
    quickSmallMin,
    quickLargeMin,
    greatHours,
    phases: { clearing, raising, finishing },
    siteLedger: typeof d.site_ledger === 'string' ? d.site_ledger : null,
    codex,
  }
}

function parseFauna(
  raw: unknown,
  problems: string[]
): Record<string, FaunaSpeciesGrammar> | undefined {
  if (raw === undefined) return undefined
  if (typeof raw !== 'object' || raw === null) {
    problems.push('fauna: not a mapping')
    return undefined
  }
  const out: Record<string, FaunaSpeciesGrammar> = {}
  for (const [species, rawS] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof rawS !== 'object' || rawS === null) {
      problems.push(`fauna.${species}: not a mapping`)
      continue
    }
    const s = rawS as Record<string, unknown>
    if (s.decorative !== true) {
      // Population law: fauna is decorative-honest BY SCHEMA — an entry
      // claiming otherwise is refused (a bound creature is bestiary/
      // morphology territory, never this block).
      problems.push(`fauna.${species}: decorative must be true (population law)`)
      continue
    }
    const home = typeof s.home === 'string' ? s.home : null
    if (!home) {
      problems.push(`fauna.${species}: home missing`)
      continue
    }
    const codex = parseCodex(s.codex)
    if (!codex) problems.push(`fauna.${species}: codex missing/incomplete`)
    out[species] = { home, decorative: true, staged: s.staged === true, codex }
  }
  return Object.keys(out).length > 0 ? out : undefined
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
  const capPerOfficer = num(d.cap_per_officer, 1)
  if (capPerOfficer === null) {
    problems.push('apprentices: cap_per_officer missing/invalid')
    return undefined
  }
  const codex = parseCodex(d.codex)
  if (!codex) problems.push('apprentices: codex missing/incomplete')
  return { capPerOfficer, codex }
}

/** Parse the LIFE blocks out of a show-grammar.yml text (pure — testable). */
export function parseLifeGrammar(text: string): LifeGrammar {
  const problems: string[] = []
  let doc: unknown
  try {
    // js-yaml v4 load is safe-by-default; JSON_SCHEMA pins plain data only
    // (no custom tags, no type construction) — same posture as grammar.ts.
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
    construction: parseConstruction(d.construction, problems),
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
