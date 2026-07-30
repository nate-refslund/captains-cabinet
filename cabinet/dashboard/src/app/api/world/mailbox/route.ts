/**
 * GET /api/world/mailbox — the crossroads mailbox's pending view (T3).
 *
 * NOW AN ALIAS of the attention-queue census (command-center Stage 1,
 * SURFACE-PARITY-LAW): when the framework's census artifact is live, the
 * mailbox renders the SAME deduped, ranked situations as /api/attention/
 * queue and the /queue page — one census, N skins (this resolves world-spec
 * §14 open call #5 in code). When the census is absent (H0 pending / fresh
 * box), the original live-Redis view of cabinet:action:* answers unchanged.
 *
 * Captain ruling 2026-07-09 carries verbatim: mailbox click → READ-only
 * render + a deep-link out. No actuation in-world, ever (the killswitch
 * lever is the ONE actuator). Pure reader; CI ratchet #2 pins it GET-only.
 *
 * Free text (subjects) rides ONLY this authed response (§5.3 free-text law).
 * Deep-link: WORLD_DECISION_QUEUE_URL (optional env) supplies the out-link;
 * absent → queueHref null and the card states the honest actuation channel.
 */
import { NextRequest, NextResponse } from 'next/server'
import { type DecisionQueueItem } from '@/lib/world/ui-cards'
import { readQueue } from '@/lib/attention/queue'

export const dynamic = 'force-dynamic'

const MAX_ITEMS = 50

export interface MailboxPayload {
  items: DecisionQueueItem[]
  /**
   * Total pending cards (may exceed items.length — capped render).
   * NULL = nothing measured it; the card must render an absence, not a 0.
   */
  pendingTotal: number | null
  /** Why there is no count, in plain words. Null on a measured payload. */
  unknownReason: string | null
  /** Out-link to the real queue surface; null = Telegram-binder-only. */
  queueHref: string | null
  proof: { keyPattern: string }
}

export async function GET(_req: NextRequest) {
  // Auth gate cloned from /api/world/stream (ratchet #7 pattern).
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const queueHref = process.env.WORLD_DECISION_QUEUE_URL || '/queue'

  try {
    const queue = await readQueue()
    if (queue.source === 'census') {
      // Census-aliased: one situation = one row, framework-ranked order
      // (Decisions shelf first, then Directions).
      const items: DecisionQueueItem[] = [
        ...queue.decisions,
        ...queue.directions,
      ].map((row) => ({
        cid: row.id,
        subject: row.what ?? '(no subject)',
        lane: row.lane ?? '?',
        urgency: row.urgency ?? '?',
        confidence: null,
        evidenceCount: row.refs.length,
        ts: '',
      }))
      return NextResponse.json({
        items: items.slice(0, MAX_ITEMS),
        pendingTotal: queue.pendingTotal,
        unknownReason: null,
        queueHref,
        proof: { keyPattern: 'attention-census' },
      } satisfies MailboxPayload)
    }

    // Nothing was measured: the flag stays UNKNOWN, never down. `pendingTotal:
    // 0` here was the world's half of the 2026-07-30 defect — the card read
    // "no pending decisions — the queue is honestly empty (flag down)" off a
    // reading that did not exist.
    if (queue.source === 'unknown') {
      return NextResponse.json({
        items: [],
        pendingTotal: null,
        unknownReason: queue.unknownReason,
        queueHref,
        proof: { keyPattern: 'attention-census (no current reading)' },
      } satisfies MailboxPayload)
    }

    // Degraded live view. The rows are ALREADY on `queue` — re-reading Redis
    // here was a second chance to fail: `readPendingCards()` maps a failed or
    // raced read to `[]`, which would have emitted `pendingTotal: 0` and put
    // "the queue is honestly empty (flag down)" on the card off a read that
    // did not happen (found by adversarial review, 2026-07-30).
    const items: DecisionQueueItem[] = queue.decisions.map((row) => ({
      cid: row.id,
      subject: row.what ?? '(no subject)',
      lane: row.lane ?? '?',
      urgency: row.urgency ?? '?',
      confidence: null,
      evidenceCount: row.refs.length,
      ts: '',
    }))
    return NextResponse.json({
      items: items.slice(0, MAX_ITEMS),
      pendingTotal: queue.pendingTotal,
      unknownReason: null,
      queueHref,
      proof: { keyPattern: 'cabinet:action:*' },
    } satisfies MailboxPayload)
  } catch {
    return NextResponse.json({
      items: [],
      pendingTotal: null,
      unknownReason: 'the mailbox could not read the list at all',
      queueHref,
      proof: { keyPattern: 'cabinet:action:*' },
    } satisfies MailboxPayload)
  }
}
