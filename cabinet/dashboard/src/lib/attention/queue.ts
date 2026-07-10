/**
 * Attention-queue shared reader — the ONE census under every skin
 * (SURFACE-PARITY-LAW; command-center proposal 2026-07-10 §2/§4).
 *
 * Source of truth: the PRIVATE census artifact the framework's 300s surface
 * drain writes at $CABINET_ATTENTION_DIR/queue.json
 * (framework/attention/queue.py write_artifacts — free-text `what` lines +
 * pids live there, served ONLY behind the session cookie). When the artifact
 * is absent/stale (H0 pending, fresh box), the reader degrades to the
 * mailbox's live-Redis view of cabinet:action:* (pending binder cards) so
 * the strip/queue page never lie dark while the binder is live.
 *
 * READ-ONLY BY DOCTRINE: this lib reads a file and GETs Redis — it exposes
 * no write verb of any kind (the GET-only vitest ratchet covers its routes;
 * approve buttons in the dashboard would be a second door, gateway §4.4).
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {
  parseActionCard,
  sortDecisionQueue,
  type DecisionQueueItem,
} from '@/lib/world/ui-cards'

/** One normalized queue row (private-census projection, authed surfaces). */
export interface QueueRow {
  id: string
  kind: string
  state: string
  class: string | null
  urgency: string | null
  deadline_iso: string | null
  harm_class: string | null
  age_h: number | null
  blast: { class: string; reach: string } | null
  decay_stage: string | null
  admission: string | null
  pid: string | null
  h: string | null
  what: string | null
  why_now: {
    cost_of_delay?: string
    decay?: string
    deadline_iso?: string | null
  } | null
  refs: string[]
  one_tap: Record<string, string> | null
  blast_worst_case: string | null
  filed_by: string | null
  lane: string | null
}

export interface QueuePayload {
  generatedAt: string | null
  /** |Decisions| incl. overflow — the ONE glance int (SSE parity). */
  pendingCaptainItems: number
  pendingTotal: number
  byClass: Record<string, number>
  overflow: number
  cap: number | null
  admissionEnforced: boolean
  decisions: QueueRow[]
  directions: QueueRow[]
  /** Where this payload came from: census artifact or the Redis fallback. */
  source: 'census' | 'redis-fallback' | 'empty'
}

/** Census artifact staleness bar: older than this = fall back to Redis. */
export const CENSUS_MAX_AGE_MS = 30 * 60 * 1000

export function censusPath(): string {
  const dir =
    process.env.CABINET_ATTENTION_DIR ||
    path.join(os.homedir(), 'Library', 'Application Support', 'cabinet', 'attention')
  return path.join(dir, 'queue.json')
}

function normalizeRow(raw: Record<string, unknown>): QueueRow {
  const blast =
    typeof raw.blast === 'object' && raw.blast !== null
      ? (raw.blast as { class?: unknown; reach?: unknown })
      : null
  return {
    id: typeof raw.id === 'string' ? raw.id : '',
    kind: typeof raw.kind === 'string' ? raw.kind : '?',
    state: typeof raw.state === 'string' ? raw.state : 'open',
    class: typeof raw.class === 'string' ? raw.class : null,
    urgency: typeof raw.urgency === 'string' ? raw.urgency : null,
    deadline_iso: typeof raw.deadline_iso === 'string' ? raw.deadline_iso : null,
    harm_class: typeof raw.harm_class === 'string' ? raw.harm_class : null,
    age_h: typeof raw.age_h === 'number' ? raw.age_h : null,
    blast: blast
      ? {
          class: typeof blast.class === 'string' ? blast.class : 'low',
          reach: typeof blast.reach === 'string' ? blast.reach : 'internal',
        }
      : null,
    decay_stage: typeof raw.decay_stage === 'string' ? raw.decay_stage : null,
    admission: typeof raw.admission === 'string' ? raw.admission : null,
    pid: typeof raw.pid === 'string' ? raw.pid : null,
    h: typeof raw.h === 'string' ? raw.h : null,
    what: typeof raw.what === 'string' ? raw.what : null,
    why_now:
      typeof raw.why_now === 'object' && raw.why_now !== null
        ? (raw.why_now as QueueRow['why_now'])
        : null,
    refs: Array.isArray(raw.refs)
      ? raw.refs.filter((r): r is string => typeof r === 'string')
      : [],
    one_tap:
      typeof raw.one_tap === 'object' && raw.one_tap !== null
        ? (raw.one_tap as Record<string, string>)
        : null,
    blast_worst_case:
      typeof raw.blast_worst_case === 'string' ? raw.blast_worst_case : null,
    filed_by: typeof raw.filed_by === 'string' ? raw.filed_by : null,
    lane: typeof raw.lane === 'string' ? raw.lane : null,
  }
}

/** Parse the private census JSON (pure — unit-tested on fixtures). */
export function parseCensus(raw: string, nowMs: number): QueuePayload | null {
  let doc: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return null
    }
    doc = parsed as Record<string, unknown>
  } catch {
    return null
  }
  const generatedAt =
    typeof doc.generated_at === 'string' ? doc.generated_at : null
  if (generatedAt) {
    const t = Date.parse(generatedAt)
    if (Number.isFinite(t) && nowMs - t > CENSUS_MAX_AGE_MS) return null // stale
  }
  const rows = (v: unknown): QueueRow[] =>
    Array.isArray(v)
      ? v
          .filter(
            (r): r is Record<string, unknown> =>
              typeof r === 'object' && r !== null
          )
          .map(normalizeRow)
      : []
  return {
    generatedAt,
    pendingCaptainItems:
      typeof doc.pending_captain_items === 'number'
        ? doc.pending_captain_items
        : 0,
    pendingTotal:
      typeof doc.pending_total === 'number' ? doc.pending_total : 0,
    byClass:
      typeof doc.by_class === 'object' && doc.by_class !== null
        ? (doc.by_class as Record<string, number>)
        : {},
    overflow: typeof doc.overflow === 'number' ? doc.overflow : 0,
    cap: typeof doc.cap === 'number' ? doc.cap : null,
    admissionEnforced: doc.admission_enforced === true,
    decisions: rows(doc.decisions),
    directions: rows(doc.directions),
    source: 'census',
  }
}

/** Redis-fallback: pending binder cards as Directions-shaped rows (no
 * ranking inputs beyond ts — honest degradation, never invented clocks). */
export function fallbackFromCards(items: DecisionQueueItem[]): QueuePayload {
  const sorted = sortDecisionQueue(items)
  const rows: QueueRow[] = sorted.map((c) => ({
    id: c.cid || c.subject,
    kind: 'action-proposal',
    state: 'pending',
    class: null,
    urgency: c.urgency || null,
    deadline_iso: null,
    harm_class: null,
    age_h: null,
    blast: null,
    decay_stage: null,
    admission: null,
    pid: null,
    h: null,
    what: c.subject,
    why_now: null,
    refs: [],
    one_tap: null,
    blast_worst_case: null,
    filed_by: null,
    lane: c.lane || null,
  }))
  return {
    generatedAt: null,
    pendingCaptainItems: rows.length,
    pendingTotal: rows.length,
    byClass: { 'action-proposal': rows.length },
    overflow: 0,
    cap: null,
    admissionEnforced: false,
    decisions: rows,
    directions: [],
    source: 'redis-fallback',
  }
}

export const EMPTY_QUEUE: QueuePayload = {
  generatedAt: null,
  pendingCaptainItems: 0,
  pendingTotal: 0,
  byClass: {},
  overflow: 0,
  cap: null,
  admissionEnforced: false,
  decisions: [],
  directions: [],
  source: 'empty',
}

type RedisLike = {
  scan: (
    cursor: string,
    matchToken: 'MATCH',
    pattern: string,
    countToken: 'COUNT',
    count: number
  ) => Promise<[string, string[]]>
  get: (key: string) => Promise<string | null>
  quit?: () => Promise<unknown>
  disconnect?: () => void
}

/** Live cabinet:action:* read (identical discipline to the mailbox route:
 * bounded SCAN passes, GET-only, silent-empty on failure). Exported so the
 * mailbox alias keeps its exact pre-census behavior on the fallback path. */
export async function readPendingCards(): Promise<DecisionQueueItem[]> {
  const REDIS_URL = process.env.REDIS_URL
  if (!REDIS_URL) return []
  let redis: RedisLike | null = null
  try {
    const { default: Redis } = await import('ioredis')
    redis = new Redis(REDIS_URL) as unknown as RedisLike
    const keys: string[] = []
    let cursor = '0'
    let passes = 0
    do {
      const [next, batch] = await redis.scan(
        cursor,
        'MATCH',
        'cabinet:action:*',
        'COUNT',
        200
      )
      cursor = next
      keys.push(...batch)
      passes += 1
    } while (cursor !== '0' && passes < 50)
    const items: DecisionQueueItem[] = []
    for (const key of keys) {
      if (key.startsWith('cabinet:action:asks:')) continue
      const raw = await redis.get(key)
      if (!raw) continue
      const item = parseActionCard(key, raw)
      if (item) items.push(item)
    }
    return items
  } catch {
    return []
  } finally {
    try {
      if (redis?.quit) await redis.quit()
      else redis?.disconnect?.()
    } catch {
      /* ignore */
    }
  }
}

/** The queue, for server routes/pages: census artifact first, live Redis
 * cards as the degradation path, honest-empty last. */
export async function readQueue(nowMs = Date.now()): Promise<QueuePayload> {
  try {
    const raw = fs.readFileSync(censusPath(), 'utf8')
    const parsed = parseCensus(raw, nowMs)
    if (parsed) return parsed
  } catch {
    /* absent artifact — fall through */
  }
  const cards = await readPendingCards()
  if (cards.length > 0) return fallbackFromCards(cards)
  return EMPTY_QUEUE
}
