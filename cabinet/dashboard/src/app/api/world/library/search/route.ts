/**
 * GET /api/world/library/search — the world Library card's search adapter
 * over the lane-2 library-search contract (spec v2 P6: "GET-only
 * library/product search into cards"; v3 acceptance: the library round-trip
 * is GET-only — and so is the whole chain here).
 *
 * The card issues a plain GET here; THIS route forwards the query
 * server-side to the LANDED lane-2 contract — GET
 * /api/library/search?q=…&limit=… over the cabinet_memory store
 * (docs/runbooks/library-search-2026-07-17.md) — passing the caller's OWN
 * session cookie through so the same-origin authed contract applies end to
 * end. No secret material is read, attached, or logged on this path —
 * DB/embedding credentials live entirely behind the lane-2 route.
 *
 * The query is UNTRUSTED text: length-capped here, carried as URL
 * search-param DATA exactly as the lane-2 contract specifies (the lane-2
 * route binds it as a pg parameter — never SQL text), and NEVER logged on
 * this path. The upstream response is UNTRUSTED data:
 * normalizeLane2Response type-checks and caps every field; upstream error
 * bodies are never relayed. Backend down/absent → an honest
 * { available: false }; upstream 429 → rateLimited: true (the card says
 * so). Browse/read stay independent of search availability.
 *
 * GET only (world ratchet #2); auth gate cloned (ratchet #7); READ-ONLY.
 */
import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import {
  buildLane2SearchUrl,
  LANE2_BACKEND_LABEL,
  lane2Degraded,
  normalizeLane2Response,
  type WorldLibrarySearchPayload,
} from '@/lib/world/library-panel'

export const dynamic = 'force-dynamic'

const MAX_QUERY_CHARS = 256
const DEFAULT_LIMIT = 10

export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const q = (req.nextUrl.searchParams.get('q') ?? '').trim()
  if (!q) {
    return NextResponse.json({ error: 'q is required' }, { status: 400 })
  }
  if (q.length > MAX_QUERY_CHARS) {
    return NextResponse.json({ error: 'q too long' }, { status: 400 })
  }
  const limitRaw = Number(req.nextUrl.searchParams.get('limit') ?? DEFAULT_LIMIT)
  const limit = Number.isFinite(limitRaw) ? limitRaw : DEFAULT_LIMIT

  const base: Pick<WorldLibrarySearchPayload, 'degraded' | 'rateLimited' | 'backend'> = {
    degraded: false,
    rateLimited: false,
    backend: LANE2_BACKEND_LABEL,
  }

  try {
    const res = await fetch(buildLane2SearchUrl(req.nextUrl.origin, q, limit), {
      headers: {
        // Same-origin auth passthrough: the caller's own session cookie —
        // never a credential of ours.
        cookie: req.headers.get('cookie') ?? '',
      },
      cache: 'no-store',
    })
    if (res.status === 429) {
      return NextResponse.json({
        ...base,
        available: true,
        rateLimited: true,
        hits: [],
      } satisfies WorldLibrarySearchPayload)
    }
    if (!res.ok) {
      // 404/405 = the lane-2 surface isn't reachable; any other status =
      // backend trouble. Either way: honest unavailable, no body relay.
      return NextResponse.json({
        ...base,
        available: false,
        hits: [],
      } satisfies WorldLibrarySearchPayload)
    }
    const json: unknown = await res.json().catch(() => null)
    return NextResponse.json({
      ...base,
      available: true,
      degraded: lane2Degraded(json),
      hits: normalizeLane2Response(json),
    } satisfies WorldLibrarySearchPayload)
  } catch {
    // Network failure — never log the query, never guess at results.
    return NextResponse.json({
      ...base,
      available: false,
      hits: [],
    } satisfies WorldLibrarySearchPayload)
  }
}
