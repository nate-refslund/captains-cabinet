import { NextRequest, NextResponse } from 'next/server'
import { searchRecords } from '@/lib/library'
import { searchMemory } from '@/lib/memory-search'
import { allowSearch, searchRateKey } from '@/lib/search-rate-limit'

export const dynamic = 'force-dynamic'

/** Hard cap on q before it reaches the engine (review fix 2026-07-17):
 *  defense-in-depth for the lexical arm's plainto_tsquery bind — the embed
 *  arm already cuts at 32000 chars (memory.sh parity), but the raw q used
 *  to flow into the tsquery bind untruncated, bounded only by URL-length
 *  limits. 2KB is far beyond any real search-box query. */
const MAX_Q_CHARS = 2048

/**
 * GET /api/library/search?q=…&limit=… — the Library search (Captain-ratified
 * 2026-07-17: expose the EXISTING cabinet_memory search to the UI/world; the
 * engine parity lives in @/lib/memory-search, mirroring memory.sh).
 *
 * READ-ONLY; auth = the dashboard middleware cookie gate (this route is
 * inside the matcher — pinned by middleware.test.ts); q is untrusted and
 * only ever a bind parameter; light per-session rate limit (429).
 * Contract documented in docs/runbooks/library-search-2026-07-17.md
 * ("Querying the Library programmatically").
 */
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url)
    const q = (url.searchParams.get('q') ?? '').trim().slice(0, MAX_Q_CHARS)
    if (!q) {
      // Empty query short-circuit — no DB hit, no rate-limit charge.
      return NextResponse.json({ results: [], degraded: false })
    }

    const limRaw = Number.parseInt(url.searchParams.get('limit') ?? '', 10)
    const limit = Number.isFinite(limRaw)
      ? Math.min(Math.max(limRaw, 1), 20)
      : 20

    const key = searchRateKey(
      req.cookies?.get?.('cabinet_session')?.value,
      req.headers?.get?.('x-forwarded-for')
    )
    if (!allowSearch(key)) {
      // Retry-After = the full sliding window — a polite upper bound (the
      // budget frees as soon as the oldest stamp ages out).
      return NextResponse.json(
        { error: 'Rate limited' },
        { status: 429, headers: { 'Retry-After': '60' } }
      )
    }

    const { hits, degraded } = await searchMemory(q, limit)
    return NextResponse.json({ results: hits, degraded })
  } catch (err) {
    // Generic error only — never echo the query text or internals.
    console.error('[library] GET /api/library/search failed', err)
    return NextResponse.json({ error: 'Search failed' }, { status: 500 })
  }
}

/**
 * POST — LEGACY arm: keyword ILIKE over the retired library_records tables
 * (read-only; tables stay dormant per the 2026-07-16 retirement). Kept only
 * because CommandPalette still calls it; new callers use GET above.
 */
export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as {
      query: string
      space_id?: string
      labels?: string[]
      limit?: number
    }

    if (!body.query?.trim()) {
      return NextResponse.json({ error: 'query is required' }, { status: 400 })
    }

    const results = await searchRecords({
      query: body.query.trim(),
      space_id: body.space_id,
      labels: body.labels,
      limit: body.limit ?? 10,
    })

    return NextResponse.json({ results })
  } catch (err) {
    console.error('[library] POST /api/library/search', err)
    return NextResponse.json({ error: 'Search failed' }, { status: 500 })
  }
}
