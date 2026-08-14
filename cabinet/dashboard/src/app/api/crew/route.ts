/**
 * GET /api/crew — the crew's state, for the one place a page needs to WATCH it.
 *
 * The home card renders this server-side and does not need a route. The wake
 * flow does: after the commands come back, the operator is waiting for the
 * first heartbeat, and a page that says "waking up" and then never changes has
 * told them nothing. This is what the flow polls until a chip flips.
 *
 * READ-ONLY and auth-gated. Everything it returns is already on the page for a
 * signed-in operator; the gate is here because "already visible to someone
 * else" is not a reason to hand the fleet's shape to an unauthenticated
 * caller.
 *
 * The gate is `requireDashboardAuth`, not `verifySession` — the SHARED
 * predicate `lib/auth-posture.ts` exists for exactly this: on a build that has
 * deliberately taken the door off, middleware renders the page with no session
 * cookie, and a raw `verifySession` here would 401 the poll behind a page that
 * rendered fine. The flow would then sit on "waiting for the first sign of
 * life" forever over an officer that had already reported. Caught by driving
 * it (2026-08-14).
 */

import { NextResponse } from 'next/server'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { readCrew } from '@/lib/crew-state'

export const dynamic = 'force-dynamic'

export async function GET() {
  if (!(await requireDashboardAuth())) {
    return NextResponse.json({ ok: false, message: 'Unauthorized' }, { status: 401 })
  }
  const crew = await readCrew()
  return NextResponse.json({
    ok: true,
    unreadable: crew.unreadable,
    anyAwake: crew.anyAwake,
    neverWoken: crew.neverWoken,
    members: crew.members.map((m) => ({
      slug: m.slug,
      name: m.name,
      state: m.state,
      reason: m.reason,
      folded: m.folded,
    })),
  })
}
