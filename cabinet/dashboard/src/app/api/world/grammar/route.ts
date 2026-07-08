/**
 * GET /api/world/grammar — the parsed grammar law + auto-legend (read-only).
 *
 * Serves the validated show-grammar/morphology content (grammar-as-law files
 * under cabinet/world/, which land ONLY via Captain-merged PRs) plus the
 * Legend Law payload: every mapping, its binding, its codex — one click
 * from anywhere. GET only; the world never grows a write path.
 *
 * v2 (world-alive direction 2026-07-08 §4 data path): also serves the census
 * keyframe tail `keyframes: [prev, latest]` + `firstCensusDate`, read from
 * shared/interfaces/world-chronicle.jsonl — the SAME fenced file the binding
 * validator executes against (no DB creds, no Redis in the render path).
 * Missing/short file → keyframes: [] and the client renders day-0 growth +
 * ONE "census unavailable" badge through the existing issues chain.
 */
import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import { loadGrammar } from '@/lib/world/grammar'
import type { CensusKeyframe } from '@/lib/world/growth'

export const dynamic = 'force-dynamic'

/** Repo-root resolution mirroring lib/world/grammar.ts semantics. */
function repoRoot(): string {
  const env = process.env.CABINET_ROOT
  if (env && fs.existsSync(env)) return env
  // dashboard lives at <root>/cabinet/dashboard
  return path.resolve(process.cwd(), '..', '..')
}

/** Last two census keyframes + first census date (honest [] when absent). */
function readCensusTail(): {
  keyframes: CensusKeyframe[]
  firstCensusDate: string | null
} {
  try {
    const p = path.join(
      repoRoot(),
      'shared',
      'interfaces',
      'world-chronicle.jsonl'
    )
    const lines = fs
      .readFileSync(p, 'utf8')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0)
    const parsed: CensusKeyframe[] = []
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as CensusKeyframe
        if (row && typeof row === 'object' && !Array.isArray(row)) {
          parsed.push(row)
        }
      } catch {
        /* skip unparseable line — the census writer owns file integrity */
      }
    }
    if (parsed.length === 0) return { keyframes: [], firstCensusDate: null }
    const first = parsed[0]
    return {
      keyframes: parsed.slice(-2),
      firstCensusDate: typeof first.date === 'string' ? first.date : null,
    }
  } catch {
    return { keyframes: [], firstCensusDate: null }
  }
}

export async function GET(req: NextRequest) {
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  void req
  const g = loadGrammar()
  const census = readCensusTail()
  return NextResponse.json({
    pending: g.pending,
    showGrammar: g.showGrammar,
    morphology: g.morphology,
    codexCoverage: g.codexCoverage,
    problems: g.problems,
    keyframes: census.keyframes,
    firstCensusDate: census.firstCensusDate,
  })
}
