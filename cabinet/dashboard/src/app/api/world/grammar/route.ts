/**
 * GET /api/world/grammar — the parsed grammar law + auto-legend (read-only).
 *
 * Serves the validated show-grammar/morphology content (grammar-as-law files
 * under cabinet/world/, which land ONLY via Captain-merged PRs) plus the
 * Legend Law payload: every mapping, its binding, its codex — one click
 * from anywhere. GET only; the world never grows a write path.
 */
import { NextRequest, NextResponse } from 'next/server'
import { loadGrammar } from '@/lib/world/grammar'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  void req
  const g = loadGrammar()
  return NextResponse.json({
    pending: g.pending,
    showGrammar: g.showGrammar,
    morphology: g.morphology,
    codexCoverage: g.codexCoverage,
    problems: g.problems,
  })
}
