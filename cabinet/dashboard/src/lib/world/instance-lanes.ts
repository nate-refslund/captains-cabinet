/**
 * INSTANCE LANE READERS (server-side) — the dashboard's TS twin of the
 * Wave-G resolver law: lane names are INSTANCE DATA, read from the
 * instance config, never baked into shared code.
 *
 * Three read-only folds over fixed repo paths under `root` (the engine
 * route passes its CABINET_ROOT resolution; tests pass a tmpdir):
 *  - outcomeLanes():   per-lane outcome records from
 *                      instance/config/outcomes.yml — key order IS lane
 *                      birth order (first ratified appearance in the
 *                      ledger), which the berth fold depends on;
 *  - declaredLanes():  the declared lane universe — first `slug:` scalar
 *                      per instance/config/contexts/*.yml (byte-mirror of
 *                      framework run_action_lane._context_slugs: minimal
 *                      line parse, no active:-filtering — the active flag
 *                      is a R2-activation gate, NEVER a lane filter);
 *  - probeWiredLanes(): lanes whose projects/<lane>.yml product.repo
 *                      matches a probes.yml github repo or vercel app —
 *                      the isle why-string's provenance.
 *
 * FAIL-HONEST: every reader degrades to an EMPTY result on unreadable or
 * malformed config — consumers then render honest absence (mist slots,
 * unverified-by-probe) — never an invented default, never a baked name.
 * No network, no exec, no user-supplied path segments (Corridor: fixed
 * base paths + js-yaml JSON_SCHEMA safe parsing).
 */
import fs from 'node:fs'
import path from 'node:path'
import yaml from 'js-yaml'
import type { LaneRecord } from './era-engine'

/** Instance-only test lanes (Captain ruling 2026-07-09: 'sensed' is an
 * instance-test app, never foundation — reef-buoy render). Instance data
 * pending its own config field — tracked as ledger row R163
 * (instance_test_lanes -> instance config, read fail-honest to the EMPTY
 * set); kept verbatim from the engine route it moved out of. */
const INSTANCE_TEST_LANES = new Set(['sensed'])

interface OutcomeRow {
  id?: string
  lane?: string
  status?: string
}

/** Lane of an outcome: explicit lane: else the outcome-<lane>-NNN id. */
function laneOf(o: OutcomeRow): string | null {
  if (typeof o.lane === 'string' && o.lane) return o.lane
  const m = /^outcome-(.+)-\d+$/.exec(o.id ?? '')
  return m ? m[1] : null
}

export interface OutcomeLanes {
  /** Key order = lane birth order (first non-draft row in the ledger). */
  lanes: Record<string, LaneRecord>
  achieved: number
  active: number
  activeSystemSelf: number
  activeLanesEver: number
}

/** Fold instance/config/outcomes.yml into per-lane records (moved verbatim
 * from the engine route — Wave G, so the fold is import-testable). */
export function outcomeLanes(root: string): OutcomeLanes {
  const lanes: Record<string, LaneRecord> = {}
  let achieved = 0
  let active = 0
  let activeSystemSelf = 0
  try {
    const raw = fs.readFileSync(
      path.join(root, 'instance', 'config', 'outcomes.yml'),
      'utf8'
    )
    const doc = (yaml.load(raw, { schema: yaml.JSON_SCHEMA }) ?? {}) as {
      outcomes?: OutcomeRow[]
    }
    for (const o of doc.outcomes ?? []) {
      const lane = laneOf(o)
      if (!lane) continue
      const status = o.status ?? 'draft'
      if (status === 'draft') continue // never ratified — not "ever"
      const rec = (lanes[lane] ??= {
        ever: 0,
        active: 0,
        achieved: 0,
        retired: 0,
        instanceTest: INSTANCE_TEST_LANES.has(lane),
      })
      rec.ever += 1
      if (status === 'active') {
        rec.active += 1
        active += 1
        if (lane === 'system-self') activeSystemSelf += 1
      }
      if (status === 'achieved') {
        rec.achieved += 1
        achieved += 1
      }
      if (status === 'retired') rec.retired += 1
    }
  } catch {
    /* honest absence: empty lanes → everything unmeasured/reef */
  }
  return {
    lanes,
    achieved,
    active,
    activeSystemSelf,
    activeLanesEver: Object.keys(lanes).length,
  }
}

/**
 * Declared lanes: the first top-level `slug:` scalar per
 * instance/config/contexts/*.yml. Semantics mirror the framework's
 * _context_slugs byte-for-byte: strip quote RUNS (double then single —
 * the python strip('"').strip("'") order), lowercase, the first
 * `slug:`-prefixed line ends that file's scan (empty value ⇒ the file
 * contributes nothing — e.g. _default.yml has no slug and is skipped);
 * an unreadable file is skipped; an unreadable dir ⇒ []. Sorted for
 * determinism — berth ORDER comes from the outcomes ledger, membership
 * from here.
 */
export function declaredLanes(root: string): string[] {
  const slugs = new Set<string>()
  try {
    const dir = path.join(root, 'instance', 'config', 'contexts')
    for (const f of fs.readdirSync(dir).sort()) {
      if (!f.endsWith('.yml')) continue
      try {
        for (const line of fs
          .readFileSync(path.join(dir, f), 'utf8')
          .split('\n')) {
          const s = line.trim()
          if (s.startsWith('slug:')) {
            const val = s
              .split(':')
              .slice(1)
              .join(':')
              .trim()
              .replace(/^"+|"+$/g, '')
              .replace(/^'+|'+$/g, '')
              .toLowerCase()
            if (val) slugs.add(val)
            break
          }
        }
      } catch {
        continue
      }
    }
  } catch {
    /* honest absence */
  }
  return [...slugs].sort()
}

/** Normalize a repo reference to a lowercase `owner/name` gh slug:
 * strips https://github.com/ or git@github.com: prefixes and .git. */
function repoSlug(repo: string): string | null {
  const t = repo
    .trim()
    .replace(/^https?:\/\/github\.com\//i, '')
    .replace(/^git@github\.com:/i, '')
    .replace(/\.git$/i, '')
    .replace(/\/+$/, '')
    .toLowerCase()
  return /^[^/\s]+\/[^/\s]+$/.test(t) ? t : null
}

/**
 * Probe-wired lanes: lane L is wired iff projects/L.yml's product.repo
 * (as an owner/name slug) matches a probes.yml github row, or its name
 * segment matches a probes.yml vercel app. This is the machine-readable
 * form of the isle why-string's own citation ("probes.yml has no row").
 * Missing/malformed probes.yml or projects ⇒ [] — every isle then says
 * "unverified by probe", the honest degradation.
 */
export function probeWiredLanes(root: string): string[] {
  const githubRepos = new Set<string>()
  const vercelApps = new Set<string>()
  try {
    const raw = fs.readFileSync(
      path.join(root, 'instance', 'config', 'probes.yml'),
      'utf8'
    )
    const doc = (yaml.load(raw, { schema: yaml.JSON_SCHEMA }) ?? {}) as {
      github?: Array<{ repo?: string }>
      vercel?: Array<{ app?: string }>
    }
    for (const g of Array.isArray(doc.github) ? doc.github : []) {
      const s = typeof g?.repo === 'string' ? repoSlug(g.repo) : null
      if (s) githubRepos.add(s)
    }
    for (const v of Array.isArray(doc.vercel) ? doc.vercel : []) {
      if (typeof v?.app === 'string' && v.app.trim()) {
        vercelApps.add(v.app.trim().toLowerCase())
      }
    }
  } catch {
    return [] // no probes.yml → nothing is probe-verified
  }
  if (githubRepos.size === 0 && vercelApps.size === 0) return []
  const wired: string[] = []
  try {
    const dir = path.join(root, 'instance', 'config', 'projects')
    for (const f of fs.readdirSync(dir).sort()) {
      if (!f.endsWith('.yml') || f.startsWith('_')) continue // _template is not a lane
      const lane = f.replace(/\.yml$/, '')
      try {
        const doc = (yaml.load(
          fs.readFileSync(path.join(dir, f), 'utf8'),
          { schema: yaml.JSON_SCHEMA }
        ) ?? {}) as { product?: { repo?: string } }
        const repo = typeof doc.product?.repo === 'string' ? doc.product.repo : null
        const slug = repo ? repoSlug(repo) : null
        if (!slug) continue
        const name = slug.split('/')[1]
        if (githubRepos.has(slug) || vercelApps.has(name)) wired.push(lane)
      } catch {
        continue
      }
    }
  } catch {
    return []
  }
  return wired
}
