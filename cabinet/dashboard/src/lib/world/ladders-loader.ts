/**
 * growth-ladders.yml loader — SERVER-side, hot-reload on mtime.
 *
 * Captain-tunable contract (growth-ladders.yml header / spec §15.3): VALUE
 * edits to cabinet/world/growth-ladders.yml take effect WITHOUT a restart —
 * the renderer hot-reloads on mtime change, no orchestrator in the loop.
 *
 * Mechanics: every load() call stats the fixed file path (no user input in
 * the path — repo-root resolution mirrors lib/world/grammar.ts); the parsed
 * + validated config is cached keyed by mtimeMs, so the fs cost per request
 * is one stat. A malformed or untruthful config FAIL-CLOSES to null with
 * loud problem strings (the world renders its honest "growth config
 * refused" badge rather than stale or invented growth) — the previous good
 * config is deliberately NOT kept: a Captain edit that breaks validation
 * must be visible immediately, never silently shadowed by yesterday's law.
 */
import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import {
  validateGrowthLadders,
  type GrowthLaddersConfig,
} from './era-engine'

export interface LoadedLadders {
  config: GrowthLaddersConfig | null
  problems: string[]
  /** Config file mtimeMs (hot-reload key; provenance on the card). */
  mtimeMs: number | null
  /** True when this call re-read the file (fresh mtime). */
  reloaded: boolean
}

function repoRoot(): string {
  const env = process.env.CABINET_ROOT
  if (env && fs.existsSync(env)) return env
  // dashboard lives at <root>/cabinet/dashboard
  return path.resolve(process.cwd(), '..', '..')
}

export function laddersPath(root?: string): string {
  return path.join(root ?? repoRoot(), 'cabinet', 'world', 'growth-ladders.yml')
}

interface CacheEntry {
  mtimeMs: number
  config: GrowthLaddersConfig | null
  problems: string[]
}

/** Cache per absolute path (tests load from tmp fixtures). */
const cache = new Map<string, CacheEntry>()

/**
 * Load (or hot-reload) the growth-ladders config. `filePath` overrides the
 * default fixed path for tests only — callers in the app pass nothing.
 */
export function loadGrowthLadders(filePath?: string): LoadedLadders {
  const p = filePath ?? laddersPath()
  let mtimeMs: number
  try {
    mtimeMs = fs.statSync(p).mtimeMs
  } catch {
    cache.delete(p)
    return {
      config: null,
      problems: [`growth-ladders.yml unreadable at ${p}`],
      mtimeMs: null,
      reloaded: false,
    }
  }
  const hit = cache.get(p)
  if (hit && hit.mtimeMs === mtimeMs) {
    return { config: hit.config, problems: hit.problems, mtimeMs, reloaded: false }
  }
  let doc: unknown
  try {
    // js-yaml load() is safe-by-default since v4 (no custom types).
    doc = yaml.load(fs.readFileSync(p, 'utf8'))
  } catch (e) {
    const entry: CacheEntry = {
      mtimeMs,
      config: null,
      problems: [`growth-ladders.yml parse error: ${e instanceof Error ? e.message : String(e)}`],
    }
    cache.set(p, entry)
    return { ...entry, reloaded: true }
  }
  const { config, problems } = validateGrowthLadders(doc)
  const entry: CacheEntry = { mtimeMs, config, problems }
  cache.set(p, entry)
  return { ...entry, reloaded: true }
}

/** Test hook: drop the cache (never used by app code). */
export function resetLaddersCache(): void {
  cache.clear()
}
