'use server'

/**
 * THE WEB DOOR of the tap — the Captain's Ratify button on a proposed card.
 *
 * Until this action existed, a proposed outcome card ended with an instruction
 * to open a YAML file and move a row by hand. That is a control nobody can
 * reach from a phone, which makes it not a control at all.
 *
 * TWO THINGS THIS FILE DELIBERATELY DOES NOT DO:
 *
 *  1. It composes no YAML. The single writer is
 *     `framework/outcomes/ratify.py`; this action validates an id and calls
 *     it. That is mechanically checked — the outcomes filename appears
 *     nowhere in this file, and a test asserts so.
 *  2. It does not route through `dockerExec`. That transport refuses whenever
 *     the store is not live, and an installed Cabinet with no `REDIS_URL` is
 *     the normal state of the deployment this ships to — the one control the
 *     no-terminal law exists for would have thrown before it ran. Ratifying
 *     writes two files and one ledger line and needs no store, so it uses the
 *     plain seam (`lib/local-exec.ts`, which carries the reasoning).
 *
 * `requireDashboardAuth()` is the FIRST statement: a Server Action is a global
 * POST endpoint and middleware never covers action dispatch.
 */

import { revalidatePath } from 'next/cache'
import { CABINET_PYTHON, localExec } from '@/lib/local-exec'
import { requireDashboardAuth } from '@/lib/provisioning/guard'

/** The org's id charset, anchored at both ends. */
const OUTCOME_ID_RE = /^[A-Za-z0-9._-]{1,64}$/

export interface RatifyResult {
  ok: boolean
  /** The writer's own status word, when it got that far. */
  status?: string
  outcomeId?: string
  error?: string
}

export async function ratifyOutcome(id: string): Promise<RatifyResult> {
  if (!(await requireDashboardAuth())) return { ok: false, error: 'unauthorized' }
  if (typeof id !== 'string' || !OUTCOME_ID_RE.test(id)) {
    return { ok: false, error: 'invalid outcome id' }
  }
  try {
    const { stdout } = await localExec([
      CABINET_PYTHON, '-m', 'framework.outcomes.ratify',
      id, '--door', 'web', '--principal', 'dashboard-session', '--json',
    ])
    const result = stdout ? JSON.parse(stdout) : null
    const status = result && typeof result.status === 'string' ? result.status : ''
    if (status !== 'ratified' && status !== 'already_ratified') {
      return {
        ok: false,
        status: status || undefined,
        outcomeId: id,
        error: (result && result.reason) || status || 'ratify failed',
      }
    }
    revalidatePath('/briefing')
    revalidatePath('/receipts')
    revalidatePath('/')
    return { ok: true, status, outcomeId: id }
  } catch (err) {
    // A non-zero exit lands here with its own message — the writer's refusal
    // words, not a guess at what happened.
    const detail = err instanceof Error ? err.message : String(err)
    return { ok: false, outcomeId: id, error: detail.split('\n').filter(Boolean).slice(-1)[0] || detail }
  }
}
