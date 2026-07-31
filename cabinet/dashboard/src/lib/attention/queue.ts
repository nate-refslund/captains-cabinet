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
 * READ-ONLY LIB: this lib reads a file and GETs Redis — it exposes no write
 * verb of any kind. Decisions travel through the ONE write door,
 * POST /api/attention/verdict (Ruling A 2026-07-10: equal-authority-door;
 * the CI ratchet pins exactly one write route under /api/attention).
 *
 * ── UNMEASURED IS NOT ZERO (the defect this file was rewritten for) ────────
 *
 * Measured in a browser on 2026-07-30: the census artifact was 9 days old, the
 * org that writes it had been dead for five, and /queue rendered
 * "Nothing needs you. All clear — your team is handling the rest. ✅" over a
 * green tick. The last real reading, still on disk, said 2 decisions and 42
 * situations pending. Nothing on the page said it was old, because nothing
 * downstream could tell "nobody has measured this" from "somebody measured it
 * and the answer was none".
 *
 * The staleness bar was doing its job — `parseCensus` returned null exactly as
 * designed. The lie was the FLOOR under it: `EMPTY_QUEUE.pendingCaptainItems`
 * was the literal `0`, and `queue.test.ts` pinned that as "the honest zero".
 * A count that nobody took is not a zero, and `0` is the most dangerous guess
 * available here — it is indistinguishable from an all-clear, so it removes
 * the very alarm the surface exists to raise.
 *
 * So the count is now `number | null`, and NULL IS THE ONLY HONEST FLOOR. This
 * is the world's existing vocabulary, not a new one: `RenderCoverage.fraction`
 * is "0..1, or null when nothing is classified (never silently 1)"
 * (lib/world/law-render.ts), `formatMicro` renders a null cost as `—` rather
 * than $0.00-as-fact (lib/world/ui-cards.ts), and `LawUnrendered` carries a
 * "plain, checkable reason. Never 'TODO' — say what is missing". Every unknown
 * payload here carries the same kind of reason, and `attentionGlance()` is the
 * ONE place the three-way (unknown / clear / count) decision is made, so no
 * skin can quietly re-invent the guess.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {
  parseActionCard,
  sortDecisionQueue,
  type DecisionQueueItem,
} from '@/lib/world/ui-cards'
import { UNMEASURED_GLYPH } from './glance'
import { REQUEST_CLIENT_OPTIONS } from '@/lib/store-reachability'

// Re-exported so server callers have ONE import site, while `'use client'`
// components take them from ./glance (this module reads the filesystem and
// cannot be bundled for the browser).
export { UNMEASURED_GLYPH, badgeState, type BadgeState } from './glance'

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
  /**
   * |Decisions| incl. overflow — the ONE glance int (SSE parity).
   *
   * NULL = nobody measured it. Never 0-as-a-stand-in: 0 is an affirmative
   * "the org counted, and nothing is waiting", which is the one claim a dead
   * or stale reading must never be allowed to make.
   */
  pendingCaptainItems: number | null
  /** Total pending situations. NULL = unmeasured, same law as above. */
  pendingTotal: number | null
  byClass: Record<string, number>
  overflow: number
  cap: number | null
  admissionEnforced: boolean
  decisions: QueueRow[]
  directions: QueueRow[]
  /**
   * Where this payload came from. `unknown` means no reading was obtained —
   * it replaced the old `empty`, which named a measured emptiness the code
   * never actually had (the only zero-producing path was failure).
   */
  source: 'census' | 'redis-fallback' | 'unknown'
  /**
   * Why nothing was measured, in plain checkable words — same discipline as
   * `LawUnrendered.reason`: say what is missing, never "TODO". Null on every
   * measured payload.
   */
  unknownReason: string | null
  /** Age of the census reading at read time, when one was found at all. */
  censusAgeMs: number | null
}

/** Census artifact staleness bar: older than this = the reading is not usable. */
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

/** Why a census reading could not be used — each is a rendered sentence. */
export type CensusRejection =
  | 'malformed'
  | 'undated'
  | 'stale'
  | 'future-dated'

/** A census read: either a usable reading, or a named refusal to guess. */
export type CensusRead =
  | { ok: true; payload: QueuePayload; ageMs: number }
  | {
      ok: false
      why: CensusRejection
      /** Age of the rejected reading, when it carried a readable stamp. */
      ageMs: number | null
      generatedAt: string | null
    }

/**
 * Read the private census JSON (pure — unit-tested on fixtures).
 *
 * Every rejection arm is named rather than collapsed to null, because the
 * caller has to SAY which one happened: "the list stopped updating 9 days ago"
 * and "the list has never been written" are different truths for the Captain,
 * and both are different from "the file is corrupt".
 *
 * Two arms exist because the degenerate ends were open:
 *   - `undated` — a census with no parseable `generated_at` used to skip the
 *     staleness test entirely and be accepted as FRESH. An unbounded-age
 *     reading is exactly the thing this module refuses to render.
 *   - `future-dated` — a stamp further ahead than the bar means the clock that
 *     wrote it and the clock reading it disagree by more than the freshness
 *     window, so the age is not knowable. Ordinary small skew still passes.
 */
export function readCensus(raw: string, nowMs: number): CensusRead {
  let doc: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ok: false, why: 'malformed', ageMs: null, generatedAt: null }
    }
    doc = parsed as Record<string, unknown>
  } catch {
    return { ok: false, why: 'malformed', ageMs: null, generatedAt: null }
  }
  const generatedAt =
    typeof doc.generated_at === 'string' ? doc.generated_at : null
  const t = generatedAt ? Date.parse(generatedAt) : NaN
  if (!Number.isFinite(t)) {
    return { ok: false, why: 'undated', ageMs: null, generatedAt }
  }
  const ageMs = nowMs - t
  if (ageMs > CENSUS_MAX_AGE_MS) {
    return { ok: false, why: 'stale', ageMs, generatedAt }
  }
  if (-ageMs > CENSUS_MAX_AGE_MS) {
    return { ok: false, why: 'future-dated', ageMs, generatedAt }
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
  // The COUNTED FIELD has its own degenerate end, and closing four timestamp
  // arms while leaving this one open was the same guess one level in: a fresh
  // census whose `pending_captain_items` is absent, renamed or non-numeric used
  // to coerce to 0 and paint the green all-clear (found by adversarial review,
  // 2026-07-30). A reading that does not carry the number has not measured it.
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null
  const pendingCaptainItems = num(doc.pending_captain_items)
  const pendingTotal = num(doc.pending_total)
  return {
    ok: true,
    ageMs,
    payload: {
      generatedAt,
      pendingCaptainItems,
      pendingTotal,
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
      // The rows are still real data worth showing; only the summary int is
      // missing, so this stays a census payload and says what it lacks.
      unknownReason:
        pendingCaptainItems === null
          ? 'the attention list was written but carries no count of what is waiting'
          : null,
      censusAgeMs: ageMs,
    },
  }
}

/**
 * Back-compat thin wrapper: the usable payload, or null when there is none.
 *
 * Callers that only need "is there a reading" keep using this; anything that
 * has to TELL THE CAPTAIN why there isn't one must use `readCensus` and carry
 * the reason through, because null on its own is how the guess got in.
 */
export function parseCensus(raw: string, nowMs: number): QueuePayload | null {
  const r = readCensus(raw, nowMs)
  return r.ok ? r.payload : null
}

/** How long ago, in the words the Captain's surfaces use. */
export function humanAge(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 90) return `${s}s`
  const m = Math.round(s / 60)
  if (m < 90) return `${m} min`
  const h = m / 60
  if (h < 48) return `${h.toFixed(1)}h`
  return `${(h / 24).toFixed(1)} days`
}

/** The plain sentence for a refused reading — one per named rejection. */
export function censusRejectionReason(
  r: Extract<CensusRead, { ok: false }>
): string {
  switch (r.why) {
    case 'stale':
      return `the attention list stopped updating ${humanAge(r.ageMs ?? 0)} ago (it is rewritten every 5 min, and anything older than ${humanAge(CENSUS_MAX_AGE_MS)} is not a current reading)`
    case 'undated':
      return 'the attention list carries no timestamp, so how old it is cannot be established'
    case 'future-dated':
      return 'the attention list is stamped in the future — the clock that wrote it and this one disagree, so its age cannot be established'
    case 'malformed':
      return 'the attention list could not be read'
  }
}

/**
 * A payload that measures nothing, and says so.
 *
 * There is deliberately no zero-valued constant to reach for: every unknown is
 * constructed WITH its reason, so the reason can never be forgotten the way
 * `EMPTY_QUEUE`'s zero was.
 */
export function unknownQueue(
  reason: string,
  opts: { generatedAt?: string | null; censusAgeMs?: number | null } = {}
): QueuePayload {
  return {
    generatedAt: opts.generatedAt ?? null,
    pendingCaptainItems: null,
    pendingTotal: null,
    byClass: {},
    overflow: 0,
    cap: null,
    admissionEnforced: false,
    decisions: [],
    directions: [],
    source: 'unknown',
    unknownReason: reason,
    censusAgeMs: opts.censusAgeMs ?? null,
  }
}

/**
 * The three-way glance every skin renders from — the ONE place the
 * unknown/clear/count decision is made.
 *
 * `clear` is reachable ONLY from a real reading, which is the whole point: a
 * surface that switches on `n === 0` re-invents the defect the moment someone
 * adds a fourth skin.
 */
export type AttentionGlance =
  | { state: 'unknown'; reason: string }
  | { state: 'clear' }
  | { state: 'count'; n: number }

export function attentionGlance(q: QueuePayload): AttentionGlance {
  const n = q.pendingCaptainItems
  if (n === null || !Number.isFinite(n)) {
    return {
      state: 'unknown',
      reason: q.unknownReason ?? 'nothing measured what is waiting',
    }
  }
  return n > 0 ? { state: 'count', n } : { state: 'clear' }
}

/**
 * The masthead numeral, ALREADY A STRING.
 *
 * Defence in depth, and the reason it is here rather than in the page: a
 * surface that loses its unknown branch (a stray `false &&`, a refactor, a new
 * skin) still cannot print `0` for a reading nobody took — the worst it can do
 * is print the em-dash the world already uses for a missing number
 * (`formatMicro`, lib/world/ui-cards.ts). Static ratchets could not stop that
 * mutation; a value that never carries the digits can.
 */
export function mastheadCount(q: QueuePayload): string {
  const g = attentionGlance(q)
  return g.state === 'count' ? String(g.n) : g.state === 'clear' ? '0' : UNMEASURED_GLYPH
}

/**
 * The census count for callers that want the int and nothing else (the world
 * SSE snapshot). NULL when no current reading exists — never 0.
 */
export function censusCountOrNull(nowMs = Date.now()): number | null {
  try {
    const read = readCensus(fs.readFileSync(censusPath(), 'utf8'), nowMs)
    return read.ok ? read.payload.pendingCaptainItems : null
  } catch {
    return null
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
  if (rows.length === 0) return unknownQueue(NO_LIVE_CARDS_REASON)
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
    unknownReason: null,
    censusAgeMs: null,
  }
}

/**
 * Why an empty live read is NOT a zero.
 *
 * The fallback sees pending binder cards only — one of four classes the
 * attention list counts (the live 2026-07-30 reading held founder-actions,
 * ratifications and needs alongside them). "No binder cards" therefore cannot
 * establish that nothing is waiting; it can only establish that this narrower
 * channel is quiet. Stated here, and returned by `fallbackFromCards` itself,
 * so the claim is unreachable rather than merely unmade at the call site.
 */
export const NO_LIVE_CARDS_REASON =
  'the attention list is not current and the live standby view holds nothing — ' +
  'that view only sees one kind of item, so it cannot establish that nothing is waiting'

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

/** A live-card read that says whether it happened at all. */
export type LiveCardsRead =
  | { ok: true; items: DecisionQueueItem[] }
  | { ok: false; why: string }

/**
 * Live cabinet:action:* read (identical discipline to the mailbox route:
 * bounded SCAN passes, GET-only). Returns a RESULT rather than a list, because
 * `[]` was the second half of the same defect: an unreachable Redis and a Redis
 * holding nothing were the same value, so a dead box read as "nothing waiting".
 */
export async function readPendingCardsResult(): Promise<LiveCardsRead> {
  const REDIS_URL = process.env.REDIS_URL
  if (!REDIS_URL) {
    return { ok: false, why: 'no live standby view is configured on this box' }
  }
  let redis: RedisLike | null = null
  try {
    const { default: Redis } = await import('ioredis')
    // Bounded — this client is why /queue hung for 45s against a store that
    // accepts the connection and never answers. The try/catch below already
    // turns a rejection into an honest `ok: false`; it just never got one.
    redis = new Redis(REDIS_URL, REQUEST_CLIENT_OPTIONS) as unknown as RedisLike
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
    return { ok: true, items }
  } catch {
    return { ok: false, why: 'the live standby view could not be reached' }
  } finally {
    try {
      if (redis?.quit) await redis.quit()
      else redis?.disconnect?.()
    } catch {
      /* ignore */
    }
  }
}

/** Back-compat list form for the mailbox alias's verbatim pre-census path. */
export async function readPendingCards(): Promise<DecisionQueueItem[]> {
  const r = await readPendingCardsResult()
  return r.ok ? r.items : []
}

/**
 * The queue, for server routes/pages: the census reading first, the live
 * standby view as the degradation path, and an UNKNOWN that names its reason
 * last — never a zero nobody counted.
 */
export async function readQueue(nowMs = Date.now()): Promise<QueuePayload> {
  let censusWhy = 'no attention list has ever been written on this box'
  let generatedAt: string | null = null
  let ageMs: number | null = null
  try {
    const read = readCensus(fs.readFileSync(censusPath(), 'utf8'), nowMs)
    if (read.ok) return read.payload
    censusWhy = censusRejectionReason(read)
    generatedAt = read.generatedAt
    ageMs = read.ageMs
  } catch {
    /* absent artifact — the default reason above is the true one */
  }
  const live = await readPendingCardsResult()
  if (live.ok && live.items.length > 0) return fallbackFromCards(live.items)
  const liveWhy = live.ok
    ? 'the live standby view holds nothing, and it only sees one kind of item'
    : live.why
  return unknownQueue(`${censusWhy}; ${liveWhy}`, {
    generatedAt,
    censusAgeMs: ageMs,
  })
}
