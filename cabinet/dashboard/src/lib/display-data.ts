/**
 * display-data.ts — server-side aggregator for the wall-monitor kiosk view.
 *
 * Composes EXISTING lib functions into one typed snapshot for `/display`.
 * It does NOT reimplement any data logic — it calls:
 *   - getAllOfficerBoards / getBoardStats / WIP_CAP   (@/lib/tasks)
 *   - listClaudeNativeTasks / countDrift              (@/lib/claude-native-tasks)
 *   - redis.keys / redis.get                          (@/lib/redis)
 *   - dockerExec                                       (@/lib/docker, for OVI/events CLI)
 *   - resolveActiveContextOrNull                       (@/lib/active-context)
 *   - getActiveProjectSlug                             (@/lib/config, fallback)
 *
 * Hard rule for a wall display: NEVER throw. Every source is wrapped in
 * try/catch and degrades to a safe default ("—" / null / []) so the page
 * always renders. A blank screen in the office is worse than a stale number.
 */

import { resolveActiveContextOrNull } from '@/lib/active-context'
import { getAllOfficerBoards, getBoardStats, WIP_CAP, type OfficerTask } from '@/lib/tasks'
import { listClaudeNativeTasks, countDrift } from '@/lib/claude-native-tasks'
import { dockerExec } from '@/lib/docker'
import { getActiveProjectSlug } from '@/lib/config'
import redis from '@/lib/redis'
import { freshnessOf } from '@/lib/liveness'

// ---------------------------------------------------------------------------
// Public shape
// ---------------------------------------------------------------------------

export interface DisplayOfficer {
  slug: string
  online: boolean
  /** true when alive (heartbeat present) but stale (>15min) — amber state */
  stale: boolean
  /** true when the heartbeat could not be READ (unparseable / future-dated).
   *  Neither online nor offline: the wall must not pick one. */
  unknown: boolean
  wipCount: number
  currentTaskTitle: string | null
  blockedCount: number
}

export interface DisplayActiveTask {
  id: number
  officer: string
  title: string
  /** human-readable age, e.g. "12m", "3h", "2d" — null if no start time */
  age: string | null
  blocked: boolean
}

export interface DisplaySubagentActivity {
  inFlight: number
  completedToday: number
  drift: number
}

export interface DisplayOvi {
  score: number | null
  trend: 'up' | 'flat' | 'down' | null
}

export interface DisplayEvent {
  type: string
  at: string | null
  summary: string
}

export interface DisplayData {
  officers: DisplayOfficer[]
  activeTasks: DisplayActiveTask[]
  subagentActivity: DisplaySubagentActivity
  ovi: DisplayOvi
  recentEvents: DisplayEvent[]
  meta: {
    activeProject: string
    generatedAt: string
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const OFFLINE_THRESHOLD_MS = 15 * 60 * 1000

/** Resolve the active context slug. Uses the shared preset-aware resolver
 *  (@/lib/active-context: env > active-project.txt > single-declared-lane >
 *  lane_default — same chain as /tasks page + my-tasks.sh) but NEVER throws —
 *  falls back to config getActiveProjectSlug(), then 'demo', so the display
 *  always has a context. */
async function resolveActiveContext(): Promise<string> {
  const shared = await resolveActiveContextOrNull()
  if (shared) return shared
  try {
    return getActiveProjectSlug()
  } catch {
    return 'demo'
  }
}

/**
 * officer_slug → { online, stale, unknown } from heartbeat keys (<15min = online).
 *
 * `ageMs < TH` was TRUE for every future-dated stamp, so clock skew painted a
 * dead officer online on the office wall permanently; and an unparseable stamp
 * made `ageMs` NaN, so BOTH comparisons were false and the officer rendered
 * with no state at all rather than an honest one. `unknown` is now its own
 * answer and travels to the tile.
 */
async function getOfficerOnlineStatus(): Promise<
  Record<string, { online: boolean; stale: boolean; unknown: boolean }>
> {
  const out: Record<string, { online: boolean; stale: boolean; unknown: boolean }> = {}
  try {
    const heartbeatKeys = await redis.keys('cabinet:heartbeat:*')
    const now = Date.now()
    await Promise.all(
      heartbeatKeys.map(async (key) => {
        const slug = key.replace('cabinet:heartbeat:', '')
        if (slug.includes(':')) return
        const val = await redis.get(key)
        const f = freshnessOf(val, now, OFFLINE_THRESHOLD_MS)
        out[slug] = {
          online: f.state === 'fresh',
          stale: f.state === 'stale',
          unknown: f.state === 'unknown',
        }
      })
    )
  } catch {
    // empty map → all officers render offline; page still draws
  }
  return out
}

/** Compact relative age from an ISO timestamp. "—" handled by caller (null). */
function relativeAge(iso: string | null): string | null {
  if (!iso) return null
  // A future stamp used to clamp to "0s" — a fabricated recency on the wall.
  // Unreadable AND future both return null, which the caller already renders
  // as the honest em-dash.
  const f = freshnessOf(iso, Date.now(), Number.MAX_SAFE_INTEGER)
  if (f.state !== 'fresh' && f.state !== 'stale') return null
  const then = new Date(iso).getTime()
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h`
  const day = Math.floor(hr / 24)
  return `${day}d`
}

/** Pick the "current" WIP task title for an officer: most recently started,
 *  preferring a non-blocked one if present (a blocked task isn't "active work"). */
function currentTaskOf(wip: OfficerTask[]): string | null {
  if (!wip.length) return null
  const active = wip.find((t) => !t.blocked) ?? wip[0]
  return active?.title ?? null
}

function isSameLocalDay(iso: string, now: Date): boolean {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return false
  return (
    d.getUTCFullYear() === now.getUTCFullYear() &&
    d.getUTCMonth() === now.getUTCMonth() &&
    d.getUTCDate() === now.getUTCDate()
  )
}

/** Shell to org-runtime for the latest OVI. There is no "read latest OVI"
 *  CLI command (ovi compute needs many manual inputs), so we read the most
 *  recent `ovi.week_published` org-event and pull its payload. Best-effort:
 *  returns {null,null} on any failure or in mock mode. */
async function getOviSnapshot(productSlug: string): Promise<DisplayOvi> {
  try {
    const slug = productSlug.replace(/[^a-z0-9_-]/g, '')
    const cmd = `python3 cabinet/scripts/org-runtime.py org-event list --product-slug '${slug}' --limit 50`
    const { stdout } = await dockerExec(cmd)
    if (!stdout) return { score: null, trend: null }

    // Output is newline-delimited JSON (one event per line), newest first.
    const lines = stdout.split('\n').map((l) => l.trim()).filter(Boolean)
    for (const line of lines) {
      let ev: Record<string, unknown>
      try {
        ev = JSON.parse(line)
      } catch {
        continue
      }
      // event type column name is defensive: accept event_type | type | event.
      const type = String(ev.event_type ?? ev.type ?? ev.event ?? '')
      if (type !== 'ovi.week_published') continue

      // payload may be an object or a JSON string depending on store shape.
      let payload: Record<string, unknown> = {}
      const rawPayload = ev.payload ?? ev.payload_json ?? ev.data
      if (rawPayload && typeof rawPayload === 'object') {
        payload = rawPayload as Record<string, unknown>
      } else if (typeof rawPayload === 'string') {
        try {
          payload = JSON.parse(rawPayload)
        } catch {
          payload = {}
        }
      }

      const rawScore = payload.ovi
      const score = typeof rawScore === 'number' ? rawScore : Number(rawScore)
      if (!Number.isFinite(score)) return { score: null, trend: null }

      const rawTrend = payload.trend_vs_prior
      const trendNum =
        typeof rawTrend === 'number' ? rawTrend : rawTrend == null ? null : Number(rawTrend)
      let trend: DisplayOvi['trend'] = null
      if (trendNum != null && Number.isFinite(trendNum)) {
        if (trendNum > 0.0001) trend = 'up'
        else if (trendNum < -0.0001) trend = 'down'
        else trend = 'flat'
      }
      return { score, trend }
    }
    return { score: null, trend: null }
  } catch {
    return { score: null, trend: null }
  }
}

/** Last ~8 org events as cheap human-readable lines. Best-effort → []. */
async function getRecentEvents(productSlug: string, limit = 8): Promise<DisplayEvent[]> {
  try {
    const slug = productSlug.replace(/[^a-z0-9_-]/g, '')
    const cmd = `python3 cabinet/scripts/org-runtime.py org-event list --product-slug '${slug}' --limit ${limit}`
    const { stdout } = await dockerExec(cmd)
    if (!stdout) return []
    const lines = stdout.split('\n').map((l) => l.trim()).filter(Boolean)
    const events: DisplayEvent[] = []
    for (const line of lines) {
      try {
        const ev = JSON.parse(line) as Record<string, unknown>
        const type = String(ev.event_type ?? ev.type ?? ev.event ?? 'event')
        const at =
          (typeof ev.created_at === 'string' && ev.created_at) ||
          (typeof ev.timestamp === 'string' && ev.timestamp) ||
          null
        const aggId = ev.aggregate_id ?? ev.aggregate_type
        const summary = aggId ? `${type} · ${String(aggId)}` : type
        events.push({ type, at, summary })
      } catch {
        // skip malformed line
      }
      if (events.length >= limit) break
    }
    return events
  } catch {
    return []
  }
}

// ---------------------------------------------------------------------------
// Aggregator
// ---------------------------------------------------------------------------

export async function getDisplayData(): Promise<DisplayData> {
  const generatedAt = new Date().toISOString()
  const contextSlug = await resolveActiveContext()

  // Each source is independently guarded so one failure can't sink the page.
  const boardsP = getAllOfficerBoards(contextSlug).catch(
    () => ({}) as Record<string, Awaited<ReturnType<typeof getAllOfficerBoards>>[string]>
  )
  const statusP = getOfficerOnlineStatus()
  const inFlightP = listClaudeNativeTasks({ status: 'created', limit: 200 }).catch(() => [])
  const completedP = listClaudeNativeTasks({ status: 'completed', limit: 200 }).catch(() => [])
  const oviP = getOviSnapshot(contextSlug)
  const eventsP = getRecentEvents(contextSlug, 8)

  const [boards, status, inFlightTasks, completedTasks, ovi, recentEvents] = await Promise.all([
    boardsP,
    statusP,
    inFlightP,
    completedP,
    oviP,
    eventsP,
  ])

  // --- Officers (canonical roster comes from the boards keys; status overlays) ---
  const officerSlugs = Object.keys(boards).sort()
  const officers: DisplayOfficer[] = officerSlugs.map((slug) => {
    const board = boards[slug]
    const wip = board?.wip ?? []
    const st = status[slug] ?? { online: false, stale: false, unknown: false }
    return {
      slug,
      online: st.online,
      stale: st.stale,
      unknown: st.unknown,
      wipCount: wip.length,
      currentTaskTitle: currentTaskOf(wip),
      blockedCount: wip.filter((t) => t.blocked).length,
    }
  })

  // --- Active (WIP) tasks flattened, blocked last, then by age (oldest first) ---
  const activeTasks: DisplayActiveTask[] = []
  for (const slug of officerSlugs) {
    for (const t of boards[slug]?.wip ?? []) {
      activeTasks.push({
        id: typeof t.id === 'number' ? t.id : Number(t.id) || 0,
        officer: slug,
        title: t.title,
        age: relativeAge(t.started_at ?? t.created_at ?? null),
        blocked: Boolean(t.blocked),
      })
    }
  }
  activeTasks.sort((a, b) => {
    if (a.blocked !== b.blocked) return a.blocked ? 1 : -1
    return 0
  })

  // --- Subagent activity ---
  const now = new Date()
  const completedToday = completedTasks.filter((t) =>
    isSameLocalDay(t.updated_at || t.created_at, now)
  ).length
  const subagentActivity: DisplaySubagentActivity = {
    inFlight: inFlightTasks.length,
    completedToday,
    drift: countDrift(inFlightTasks),
  }

  return {
    officers,
    activeTasks,
    subagentActivity,
    ovi,
    recentEvents,
    meta: { activeProject: contextSlug, generatedAt },
  }
}

/** Re-exported so page/components share one WIP cap constant. */
export { WIP_CAP }
