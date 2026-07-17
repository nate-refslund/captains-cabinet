/**
 * GET /api/world/engine — the world-engine data door (T1, read-only).
 *
 * Serves everything the continuous-world renderer needs that is not already
 * on the SSE stream:
 *  - the HOT-RELOADED growth-ladders config (cabinet/world/growth-ladders.yml,
 *    mtime-cached — Captain VALUE edits take effect without a restart, §15.3)
 *    with its problems surfaced honestly when validation refuses it;
 *  - the era×rung EVAL inputs: metric values from the fenced census keyframe
 *    tail (shared/interfaces/world-chronicle.jsonl — the same file the
 *    binding validator executes against) + per-lane outcome records parsed
 *    from instance/config/outcomes.yml (fixed repo paths, no user input);
 *  - the WEATHER signals per the Captain ruling (exact sources, honest
 *    nulls): killswitch key, doctor heartbeat age + verdict, probe verdicts
 *    (null until a probe feed is wired — fog/sun resolve honestly without).
 *
 * GET only — the world never grows a write path (CI ratchet). Auth: same
 * cookie check as the sibling world routes. This route (like the stream
 * route's clock stamp) is a sanctioned wall-clock DOOR: heartbeat age is
 * computed server-side and shipped as DATA; the render path never reads a
 * clock.
 */
import { NextRequest, NextResponse } from 'next/server'
import fs from 'node:fs'
import path from 'node:path'
import { cookies } from 'next/headers'
import { loadGrowthLadders } from '@/lib/world/ladders-loader'
import type { EngineEval } from '@/lib/world/era-engine'
import {
  declaredLanes,
  outcomeLanes,
  probeWiredLanes,
  type OutcomeLanes,
} from '@/lib/world/instance-lanes'
import { berthLanes } from '@/lib/world/world-geo'
import { readDirections, readPortCalls } from '@/lib/world/directions'
import { laneCourseState } from '@/lib/world/course'
import type { WeatherSignals } from '@/lib/world/weather'
import { loadLifeGrammar } from '@/lib/world/life/life-grammar'
import type { WorkSite } from '@/lib/world/life/sites'

export const dynamic = 'force-dynamic'

function repoRoot(): string {
  const env = process.env.CABINET_ROOT
  if (env && fs.existsSync(env)) return env
  return path.resolve(process.cwd(), '..', '..')
}

const REDIS_URL = process.env.REDIS_URL ?? 'redis://localhost:6379'

type RedisLike = {
  get(key: string): Promise<string | null>
  xlen(key: string): Promise<number>
  quit(): Promise<unknown>
}

/* The outcomes fold, declared-lane universe, and probe join live in
 * lib/world/instance-lanes.ts (Wave G instance-split: lane names are
 * instance data; the readers are import-testable there). */

/**
 * T2 LIFE data (v1a review fix: the life layer must reach the renderer).
 * Site ledger: shared/interfaces/world-sites.jsonl (P-SITES, append-only,
 * fixed repo path). Honest absence: file missing → [] — the world simply
 * has no sites yet; foldSiteLedger() validates entries client-side.
 */
function readSiteLedger(): WorkSite[] {
  try {
    const p = path.join(repoRoot(), 'shared', 'interfaces', 'world-sites.jsonl')
    if (!fs.existsSync(p)) return []
    const out: WorkSite[] = []
    for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as WorkSite
        if (row && typeof row === 'object' && !Array.isArray(row)) out.push(row)
      } catch {
        /* fold reports malformed entries; unparseable lines are skipped */
      }
    }
    return out
  } catch {
    return []
  }
}

/** Product lanes = lanes with a projects/<lane>.yml (instance data). */
function readProductLanes(): string[] {
  try {
    const dir = path.join(repoRoot(), 'instance', 'config', 'projects')
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith('.yml'))
      .map((f) => f.replace(/\.yml$/, ''))
      .sort()
  } catch {
    return []
  }
}

type Keyframe = Record<string, number | string | null>

function readCensus(): { keyframes: Keyframe[]; firstDate: string | null; lineCount: number } {
  try {
    const p = path.join(repoRoot(), 'shared', 'interfaces', 'world-chronicle.jsonl')
    const lines = fs
      .readFileSync(p, 'utf8')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
    const parsed: Keyframe[] = []
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as Keyframe
        if (row && typeof row === 'object' && !Array.isArray(row)) parsed.push(row)
      } catch {
        /* census writer owns file integrity */
      }
    }
    const firstDate =
      parsed.length > 0 && typeof parsed[0].date === 'string' ? parsed[0].date : null
    return { keyframes: parsed.slice(-2), firstDate, lineCount: parsed.length }
  } catch {
    return { keyframes: [], firstDate: null, lineCount: 0 }
  }
}

function num(k: Keyframe | undefined, field: string): number | null {
  const v = k?.[field]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function ageDays(a: string | null, b: string | null): number | null {
  if (!a || !b) return null
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (!Number.isFinite(ta) || !Number.isFinite(tb) || tb < ta) return null
  return Math.floor((tb - ta) / 86_400_000)
}

/** One era×rung eval from a keyframe + the outcomes ledger. Metric names
 * mirror growth-ladders.yml sources; absent fields stay null (unmeasured —
 * never interpolated). */
function buildEval(
  kf: Keyframe | undefined,
  firstDate: string | null,
  chronicleKeyframes: number,
  outcomes: OutcomeLanes,
  embedQueueLen: number | null
): EngineEval {
  const metrics: Record<string, number | null> = {}
  // census_keyframe-sourced metrics: pass every numeric field through.
  for (const [k, v] of Object.entries(kf ?? {})) {
    if (typeof v === 'number' && Number.isFinite(v)) metrics[k] = v
  }
  // commits_ledger source: the census commits_total series IS the ledger
  // count (world-census.py counts this repo's commits since genesis).
  metrics.commits_since_genesis = num(kf, 'commits_total')
  // world_chronicle source: keyframes written so far (file line count).
  metrics.world_chronicle_keyframes = chronicleKeyframes
  // outcomes_yml-sourced metrics.
  metrics.outcomes_achieved = outcomes.achieved
  metrics.outcomes_active = outcomes.active
  metrics.outcomes_active_system_self = outcomes.activeSystemSelf
  metrics.active_lanes = outcomes.activeLanesEver
  metrics.outcomes_by_lane = Object.keys(outcomes.lanes).length
  // org age from the census date span (server data, not a clock).
  metrics.org_age_days = ageDays(
    firstDate,
    typeof kf?.date === 'string' ? kf.date : null
  )
  // redis_snapshot source (P-TANK class): honest null when unavailable.
  metrics.memory_embed_queue_xlen = embedQueueLen
  return { metrics, lanes: outcomes.lanes }
}

export async function GET(_req: NextRequest) {
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const ladders = loadGrowthLadders()
  const census = readCensus()
  const outcomes = outcomeLanes(repoRoot())
  const declared = declaredLanes(repoRoot())

  // ── direction surface (grammar v4, Captain ratifications 2026-07-17) ─────
  // Fail-honest folds: no directions.yml → uncharted; no port-calls
  // artifact → no stamps, moored boat. todayISO is server data (this route
  // is a sanctioned wall-clock DOOR, like the heartbeat age above) — the
  // render path itself never reads a clock.
  const directions = readDirections(repoRoot())
  const portCalls = readPortCalls(repoRoot())
  const todayISO = new Date().toISOString().slice(0, 10)
  const courses = laneCourseState({
    directionLanes: Object.keys(directions.lanes),
    outcomeLanes: outcomes.lanes,
    declaredLanes: declared,
    portCalls: portCalls?.lanes ?? null,
    todayISO,
  })

  // ── live signals (best-effort; every failure degrades to honest null) ────
  let killswitch = false
  let doctorAgeSecs: number | null = null
  let doctorGreen: boolean | null = null
  let embedQueueLen: number | null = null
  let redis: RedisLike | null = null
  try {
    const { default: Redis } = await import('ioredis')
    redis = new Redis(REDIS_URL, {
      lazyConnect: true,
      maxRetriesPerRequest: 1,
      connectTimeout: 900,
    }) as unknown as RedisLike
    killswitch = Boolean(await redis.get('cabinet:killswitch'))
    const hb = await redis.get('cabinet:doctor:heartbeat')
    if (hb) {
      // "<iso8601> GREEN|DEAD:<n>" (cabinet-doctor.sh contract)
      const [iso, verdict] = hb.trim().split(/\s+/, 2)
      const ts = Date.parse(iso)
      if (Number.isFinite(ts)) doctorAgeSecs = Math.max(0, (Date.now() - ts) / 1000)
      if (verdict === 'GREEN') doctorGreen = true
      else if (verdict?.startsWith('DEAD')) doctorGreen = false
    }
    try {
      embedQueueLen = await redis.xlen('cabinet:memory:embed_queue')
    } catch {
      embedQueueLen = null
    }
  } catch {
    /* redis down → nulls: fog is the honest sky */
  } finally {
    try {
      await redis?.quit()
    } catch {
      /* closing best-effort */
    }
  }

  const weather: WeatherSignals = {
    killswitch,
    doctorAgeSecs,
    doctorGreen,
    // No probe feed is wired to weather yet — null is the honest value
    // (weatherTarget renders sun-on-doctor-alone / fog accordingly).
    probesOk: null,
  }

  const [prevKf, latestKf] =
    census.keyframes.length > 1
      ? census.keyframes
      : [undefined, census.keyframes[0]]

  return NextResponse.json({
    ladders: {
      config: ladders.config,
      problems: ladders.problems,
      mtimeMs: ladders.mtimeMs,
    },
    evalPrev: prevKf
      ? buildEval(prevKf, census.firstDate, Math.max(0, census.lineCount - 1), outcomes, embedQueueLen)
      : null,
    eval: latestKf
      ? buildEval(latestKf, census.firstDate, census.lineCount, outcomes, embedQueueLen)
      : null,
    weather,
    orgEventsTotal: num(latestKf, 'org_events_total') ?? 0,
    // Isle berth bindings (instance world-state — Wave G): slot i ← the
    // i-th lane by BIRTH ORDER (first ratified appearance in outcomes.yml,
    // = the fold's key order) that is a declared context lane. Undeclared
    // pseudo-lanes and system-self (the main island) never berth. Empty
    // config ⇒ all-null ⇒ mist — honest absence, never invented names.
    berths: berthLanes(Object.keys(outcomes.lanes), declared),
    // Lanes with a probes.yml row (isle why-string provenance).
    probeWiredLanes: probeWiredLanes(repoRoot()),
    // ── direction surface (grammar v4): apex + per-lane courses + port
    // calls. Free text (missions, dates) is legal HERE — this is the authed
    // card's data door; the canvas renders none of it (no world-space text).
    directions,
    portCalls,
    courses,
    todayISO,
    // T2 LIFE feed (grammar-gated fail-closed: absent blocks → behavior OFF)
    life: {
      grammar: loadLifeGrammar(),
      siteEntries: readSiteLedger(),
      productLanes: readProductLanes(),
    },
  })
}
