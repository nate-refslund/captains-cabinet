/**
 * GET /api/attention/queue — the ONE attention API (SURFACE-PARITY-LAW).
 *
 * Serves the war-room census (Decisions shelf + Directions, ranked by the
 * framework's deterministic tuple) from the private census artifact the
 * 300s surface drain writes, with the mailbox's live-Redis binder-card view
 * as the degradation path. The classic /queue page, the header strip, the
 * world mailbox alias, and (Stage 2) the wardroom war-table all render from
 * THIS payload — one census, N skins.
 *
 * This route stays GET-only. Decisions go through the ONE write door,
 * POST /api/attention/verdict (Ruling A 2026-07-10: WRITE-CLASS-2 = YES,
 * equal-authority-door — same gate + reply grammar as Telegram; the CI
 * ratchet pins exactly one write route under /api/attention). Free text
 * (subjects, why-now lines) rides ONLY this cookie-authed response; the
 * shared/interfaces artifact stays PII-scrubbed (ids only).
 */
import { NextRequest, NextResponse } from 'next/server'
import { readQueue, type QueuePayload } from '@/lib/attention/queue'
import { COOKIE_NAME, verifySessionValue } from '@/lib/attention/verdict'

export const dynamic = 'force-dynamic'

export interface AttentionQueuePayload extends QueuePayload {
  /** Deep-link targets (env-supplied; null = binder-only, stated honestly). */
  links: {
    telegram: string | null
    world: string
    queue: string
  }
}

export async function GET(_req: NextRequest) {
  // Auth gate: full HMAC signature verify, matching the write door's session
  // check (equal-authority-door law cuts both ways — this census carries
  // un-scrubbed free text, so a forged/unsigned cookie must not read it;
  // cookie-PRESENCE-only was the /api/world/stream clone's weaker gate).
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!verifySessionValue(cookieStore.get(COOKIE_NAME)?.value)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const queue = await readQueue()
  const bot = process.env.HQ_CHAIR_BOT_USERNAME || null
  const payload: AttentionQueuePayload = {
    ...queue,
    links: {
      telegram: bot ? `https://t.me/${bot}` : null,
      world: '/world?focus=wardroom',
      queue: '/queue',
    },
  }
  return NextResponse.json(payload)
}
