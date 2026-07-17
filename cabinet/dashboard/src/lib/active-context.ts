/**
 * active-context.ts — THE dashboard-side tasks/coordination context resolver
 * (config-split fix, 2026-07-17).
 *
 * Twin of `cabinet/scripts/lib/lanes.sh cabinet_resolve_context` and
 * `framework/env.py active_context()` — keep rung-for-rung parity. The
 * dashboard is deployment-scoped (no officer identity), so the officer→lane
 * rung does not exist here; the chain is:
 *
 *   1. `CABINET_CONTEXT` env                       (launchd/session scope)
 *   2. `instance/config/active-project.txt`        (single-product deployments)
 *   3. the single declared lane, when `instance/config/contexts/*.yml`
 *      declares exactly one
 *   4. the Captain-ruled `lane_default` (platform.yml / product.yml),
 *      only when it IS a declared lane
 *
 * Every candidate is shape-gated by SLUG_RE ([a-z0-9][a-z0-9-]{0,31} — the
 * FW-073 / Spec 038 §4.8 slug shape): config values are UNTRUSTED data, and a
 * non-conforming value skips its rung rather than reaching a path join or a
 * query. No resolution → `null` / a thrown Error naming the remedies —
 * NEVER an invented default (officer_tasks.context_slug is NOT NULL).
 *
 * The lane enum parse mirrors lanes.sh `cabinet_lanes` /
 * `run_action_lane._context_slugs`: per *.yml file, the FIRST line whose
 * trimmed form starts with `slug:` wins; value is whitespace/quote-stripped
 * and lowercased; an unreadable individual file is skipped (the readable
 * rest still enumerate).
 */

import path from 'node:path'
import { readFile, readdir } from 'node:fs/promises'
import { cabinetRoot } from '@/lib/cabinet-root'

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,31}$/

function slugOk(v: string | undefined | null): v is string {
  return !!v && SLUG_RE.test(v)
}

/** Strip quotes + whitespace from a YAML scalar remnant. */
function cleanScalar(raw: string): string {
  return raw
    .replace(/[ \t]+#.*$/, '')
    .trim()
    .replace(/^"+|"+$/g, '')
    .replace(/^'+|'+$/g, '')
    .trim()
}

/** Declared-lane enum: first top-level `slug:` per contexts/*.yml, sorted. */
async function laneEnum(root: string): Promise<string[]> {
  const dir = path.join(root, 'instance/config/contexts')
  const slugs = new Set<string>()
  let names: string[]
  try {
    names = await readdir(dir)
  } catch {
    return []
  }
  for (const name of names.filter((n) => n.endsWith('.yml')).sort()) {
    try {
      const text = await readFile(path.join(dir, name), 'utf-8')
      for (const line of text.split('\n')) {
        const s = line.trim()
        if (s.startsWith('slug:')) {
          const val = cleanScalar(s.slice('slug:'.length)).toLowerCase()
          if (val) slugs.add(val)
          break
        }
      }
    } catch {
      continue // unreadable individual file — the readable rest still count
    }
  }
  return [...slugs].sort()
}

/** `lane_default:` scalar — platform.yml first, else product.yml (top-level,
 *  or nested directly under `product:`). Same stricter-only divergence as the
 *  bash twin: plain block scalars only. */
async function laneDefault(root: string): Promise<string | null> {
  for (const rel of ['instance/config/platform.yml', 'instance/config/product.yml']) {
    let text: string
    try {
      text = await readFile(path.join(root, rel), 'utf-8')
    } catch {
      continue
    }
    let inProduct = false
    for (const line of text.split('\n')) {
      if (/^[^ \t#]/.test(line)) inProduct = /^product:\s*$/.test(line)
      const topLevel = line.match(/^lane_default:(.*)$/)
      const nested = inProduct ? line.match(/^[ \t]+lane_default:(.*)$/) : null
      const m = topLevel ?? nested
      if (m) {
        const val = cleanScalar(m[1])
        if (val) return val
      }
    }
  }
  return null
}

/** Resolve the deployment's active context slug, or null when no rung
 *  resolves. Callers that can render without a context use this. */
export async function resolveActiveContextOrNull(): Promise<string | null> {
  const env = process.env.CABINET_CONTEXT?.replace(/\s+/g, '')
  if (slugOk(env)) return env

  const root = cabinetRoot()
  try {
    const txt = (
      await readFile(path.join(root, 'instance/config/active-project.txt'), 'utf-8')
    ).replace(/\s+/g, '')
    if (slugOk(txt)) return txt
  } catch {
    // fall through to the preset-derived rungs
  }

  const lanes = await laneEnum(root)
  if (lanes.length === 1 && slugOk(lanes[0])) return lanes[0]
  if (lanes.length > 0) {
    const def = await laneDefault(root)
    if (slugOk(def) && lanes.includes(def)) return def
  }
  return null
}

/** Resolve the deployment's active context slug, or throw with the remedy
 *  one-liner (fail-LOUD — a per-(context,officer) board can't render without
 *  a context). */
export async function resolveActiveContext(): Promise<string> {
  const slug = await resolveActiveContextOrNull()
  if (!slug) {
    throw new Error(
      'cannot resolve active context: set $CABINET_CONTEXT, write ' +
        'instance/config/active-project.txt, or declare ' +
        'instance/config/contexts/<lane>.yml (+ lane_default in ' +
        'instance/config/platform.yml when more than one lane is declared)'
    )
  }
  return slug
}
