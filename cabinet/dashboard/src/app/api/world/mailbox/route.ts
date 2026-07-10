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
import { sortDecisionQueue, type DecisionQueueItem } from '@/lib/world/ui-cards'
import { readPendingCards, readQueue } from '@/lib/attention/queue'

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
        queueHref,
        proof: { keyPattern: 'attention-census' },
      } satisfies MailboxPayload)
    }

    // Pre-census fallback: the original live cabinet:action:* read, verbatim.
    const sorted = sortDecisionQueue(await readPendingCards())
    return NextResponse.json({
      items: sorted.slice(0, MAX_ITEMS),
      pendingTotal: sorted.length,
      queueHref,
      proof: { keyPattern: 'cabinet:action:*' },
    } satisfies MailboxPayload)
  } catch {
    return NextResponse.json({
      items: [],
      pendingTotal: 0,
      queueHref,
      proof: { keyPattern: 'cabinet:action:*' },
    } satisfies MailboxPayload)
  }
}
