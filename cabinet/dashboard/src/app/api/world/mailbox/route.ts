/**
 * GET /api/world/mailbox — the crossroads mailbox's pending view (T3).
 *
 * Captain ruling 2026-07-09: mailbox click → READ-only render of the
 * dashboard decision-queue + a deep-link out to the real queue. No
 * actuation in-world, ever (the killswitch lever is the ONE actuator).
 *
 * Source of record: the pending action cards the binder wire parks under
 * cabinet:action:* (framework/frontdoor/binder_wire.py — proposal chains
 * awaiting the Captain's approve / edit: / skip: verdict). This route is a
 * pure Redis reader (SCAN + GET); CI ratchet #2 pins it GET-only.
 *
 * Free text (subjects) rides ONLY this authed response (§5.3 free-text law:
 * never world-space, never unauthenticated).
 *
 * Deep-link: the queue is ACTED on in the Captain's Telegram binder (HQ
 * Chair). WORLD_DECISION_QUEUE_URL (optional env) supplies an out-link when
 * a URL-addressable queue surface exists; absent → queueHref null and the
 * card states the honest actuation channel instead of guessing a link.
 */
import { NextRequest, NextResponse } from 'next/server'
import {
  parseActionCard,
  sortDecisionQueue,
  type DecisionQueueItem,
} from '@/lib/world/ui-cards'

export const dynamic = 'force-dynamic'

const MAX_ITEMS = 50

export interface MailboxPayload {
  items: DecisionQueueItem[]
  /** Total pending cards (may exceed items.length — capped render). */
  pendingTotal: number
  /** Out-link to the real queue surface; null = Telegram-binder-only. */
  queueHref: string | null
  proof: { keyPattern: string }
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

export async function GET(_req: NextRequest) {
  // Auth gate cloned from /api/world/stream (ratchet #7 pattern).
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const queueHref = process.env.WORLD_DECISION_QUEUE_URL || null
  const empty: MailboxPayload = {
    items: [],
    pendingTotal: 0,
    queueHref,
    proof: { keyPattern: 'cabinet:action:*' },
  }

  const REDIS_URL = process.env.REDIS_URL
  if (!REDIS_URL) return NextResponse.json(empty)

  let redis: RedisLike | null = null
  try {
    const { default: Redis } = await import('ioredis')
    redis = new Redis(REDIS_URL) as unknown as RedisLike
    // Non-blocking SCAN (never KEYS on an unbounded pattern in a request
    // path); bounded passes so a runaway keyspace cannot wedge the route.
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
      const raw = await redis.get(key)
      if (!raw) continue
      const item = parseActionCard(key, raw)
      if (item) items.push(item)
    }
    const sorted = sortDecisionQueue(items)
    return NextResponse.json({
      items: sorted.slice(0, MAX_ITEMS),
      pendingTotal: sorted.length,
      queueHref,
      proof: { keyPattern: 'cabinet:action:*' },
    } satisfies MailboxPayload)
  } catch {
    return NextResponse.json(empty)
  } finally {
    try {
      if (redis?.quit) await redis.quit()
      else redis?.disconnect?.()
    } catch {
      /* ignore */
    }
  }
}
