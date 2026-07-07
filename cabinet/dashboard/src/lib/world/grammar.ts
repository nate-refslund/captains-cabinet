/**
 * Grammar loading — show-grammar.yml + morphology.yml (grammar-as-law).
 *
 * DOCTRINE: grammar files are the ONLY path to pixels, and NO grammar change
 * auto-merges — cosmetic included (ratification record 2026-07-07). The v1
 * files land via a PR the Captain merges (kickoff Captain to-do 2). Until
 * that merge this loader returns the FAIL-CLOSED pending state: the renderer
 * shows presence markers + text labels only (nothing grammar-driven, nothing
 * invented) plus an honest "grammar pending Captain merge" banner.
 *
 * Server-side only (reads repo files). The client receives the parsed,
 * validated result through /api/world/* — never raw YAML.
 */
import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'

export interface VerbMapping {
  station: string
  anim: 'work' | 'walk' | 'idle'
  salience: number
  codex?: GrammarCodex
}

export interface GrammarCodex {
  represents: string
  mechanism_path: string
  day0: string
}

export interface ShowGrammar {
  version: number
  verbs: Record<string, VerbMapping>
  fallback: { station: string; anim: 'work' | 'walk' | 'idle' }
}

export interface MorphologyEntry {
  id: string
  represents: string
  source_binding: string
  scope: 'org-global' | 'per-officer' | 'dark'
  tier: 'T0' | 'T1' | 'T2' | 'T3'
  replay: 'ledger' | 'git' | 'none'
  base?: number
  codex?: GrammarCodex
}

export interface Morphology {
  version: number
  entries: MorphologyEntry[]
}

export interface LoadedGrammar {
  pending: boolean
  showGrammar: ShowGrammar | null
  morphology: Morphology | null
  codexCoverage: number | null
  problems: string[]
}

/** Repo-root resolution mirroring lib/cabinet-root.ts semantics. */
function repoRoot(): string {
  const env = process.env.CABINET_ROOT
  if (env && fs.existsSync(env)) return env
  // dashboard lives at <root>/cabinet/dashboard
  return path.resolve(process.cwd(), '..', '..')
}

export const GRAMMAR_DIR = () =>
  process.env.CABINET_WORLD_GRAMMAR_DIR ??
  path.join(repoRoot(), 'cabinet', 'world')

const ANIMS = new Set(['work', 'walk', 'idle'])

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

function parseShowGrammar(text: string, problems: string[]): ShowGrammar | null {
  let doc: unknown
  try {
    // JSON_SCHEMA: plain data only — no custom tags, no type construction
    // (js-yaml v4 load is safe-by-default; the pin makes it explicit).
    doc = yaml.load(text, { schema: yaml.JSON_SCHEMA })
  } catch (e) {
    problems.push(`show-grammar.yml unparseable: ${String(e).slice(0, 120)}`)
    return null
  }
  if (typeof doc !== 'object' || doc === null) {
    problems.push('show-grammar.yml is not a mapping')
    return null
  }
  const d = doc as Record<string, unknown>
  const version = typeof d.version === 'number' ? d.version : NaN
  if (!Number.isInteger(version)) {
    problems.push('show-grammar.yml missing integer version')
    return null
  }
  const verbs: Record<string, VerbMapping> = {}
  const rawVerbs = (d.verbs ?? {}) as Record<string, unknown>
  for (const [verb, rawM] of Object.entries(rawVerbs)) {
    if (typeof rawM !== 'object' || rawM === null) continue
    const m = rawM as Record<string, unknown>
    const station = typeof m.station === 'string' ? m.station : null
    const anim = typeof m.anim === 'string' && ANIMS.has(m.anim) ? m.anim : null
    if (!station || !anim) {
      problems.push(`verb ${verb}: missing station/anim`)
      continue
    }
    const codex = parseCodex(m.codex)
    if (!codex) {
      // codex: required on every entry (kickoff step 3) — entry loads but
      // counts against coverage and renders "codex pending" (UI-F6 fallback 3).
      problems.push(`verb ${verb}: codex missing/incomplete`)
    }
    verbs[verb] = {
      station,
      anim: anim as VerbMapping['anim'],
      salience:
        typeof m.salience === 'number' && m.salience >= 0 && m.salience <= 5
          ? m.salience
          : 0,
      codex,
    }
  }
  const rawFb = (d.fallback ?? {}) as Record<string, unknown>
  const fallback = {
    station: typeof rawFb.station === 'string' ? rawFb.station : 'floor',
    anim: (typeof rawFb.anim === 'string' && ANIMS.has(rawFb.anim)
      ? rawFb.anim
      : 'idle') as VerbMapping['anim'],
  }
  return { version, verbs, fallback }
}

const SCOPES = new Set(['org-global', 'per-officer', 'dark'])
const TIERS = new Set(['T0', 'T1', 'T2', 'T3'])
const REPLAYS = new Set(['ledger', 'git', 'none'])

function parseMorphology(text: string, problems: string[]): Morphology | null {
  let doc: unknown
  try {
    doc = yaml.load(text, { schema: yaml.JSON_SCHEMA })
  } catch (e) {
    problems.push(`morphology.yml unparseable: ${String(e).slice(0, 120)}`)
    return null
  }
  if (typeof doc !== 'object' || doc === null) {
    problems.push('morphology.yml is not a mapping')
    return null
  }
  const d = doc as Record<string, unknown>
  const version = typeof d.version === 'number' ? d.version : NaN
  if (!Number.isInteger(version)) {
    problems.push('morphology.yml missing integer version')
    return null
  }
  const entries: MorphologyEntry[] = []
  for (const raw of Array.isArray(d.entries) ? d.entries : []) {
    if (typeof raw !== 'object' || raw === null) continue
    const e = raw as Record<string, unknown>
    const ok =
      typeof e.id === 'string' &&
      typeof e.represents === 'string' &&
      typeof e.source_binding === 'string' &&
      typeof e.scope === 'string' &&
      SCOPES.has(e.scope) &&
      typeof e.tier === 'string' &&
      TIERS.has(e.tier) &&
      typeof e.replay === 'string' &&
      REPLAYS.has(e.replay)
    if (!ok) {
      problems.push(
        `morphology entry ${String(e.id ?? '?')}: schema violation (untiered/unreplayed bindings are rejected)`
      )
      continue
    }
    entries.push({
      id: e.id as string,
      represents: e.represents as string,
      source_binding: e.source_binding as string,
      scope: e.scope as MorphologyEntry['scope'],
      tier: e.tier as MorphologyEntry['tier'],
      replay: e.replay as MorphologyEntry['replay'],
      base: typeof e.base === 'number' ? e.base : undefined,
      codex: parseCodex(e.codex),
    })
  }
  return { version, entries }
}

/** Load grammar law from disk. Absent/invalid → pending (fail-closed). */
export function loadGrammar(): LoadedGrammar {
  const dir = GRAMMAR_DIR()
  const problems: string[] = []
  let showGrammar: ShowGrammar | null = null
  let morphology: Morphology | null = null
  try {
    const sgPath = path.join(dir, 'show-grammar.yml')
    if (fs.existsSync(sgPath)) {
      showGrammar = parseShowGrammar(fs.readFileSync(sgPath, 'utf8'), problems)
    }
  } catch (e) {
    problems.push(`show-grammar read failed: ${String(e).slice(0, 120)}`)
  }
  try {
    const moPath = path.join(dir, 'morphology.yml')
    if (fs.existsSync(moPath)) {
      morphology = parseMorphology(fs.readFileSync(moPath, 'utf8'), problems)
    }
  } catch (e) {
    problems.push(`morphology read failed: ${String(e).slice(0, 120)}`)
  }

  let codexCoverage: number | null = null
  const denomEntries: Array<{ hasCodex: boolean }> = []
  if (showGrammar) {
    for (const v of Object.values(showGrammar.verbs)) {
      denomEntries.push({ hasCodex: Boolean(v.codex) })
    }
  }
  if (morphology) {
    for (const e of morphology.entries) {
      denomEntries.push({ hasCodex: Boolean(e.codex) })
    }
  }
  if (denomEntries.length > 0) {
    codexCoverage =
      denomEntries.filter((e) => e.hasCodex).length / denomEntries.length
  }

  return {
    pending: showGrammar === null,
    showGrammar,
    morphology,
    codexCoverage,
    problems,
  }
}
