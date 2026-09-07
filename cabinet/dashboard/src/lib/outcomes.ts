/**
 * Server-side read model for proposed and ratified outcomes.
 *
 * The org proposes outcome cards; a Captain tap turns one into a
 * responsibility. This module reads BOTH sides through the framework's own one
 * writer (`framework.outcomes.ratify`), so the dashboard never parses or
 * composes the outcome YAML itself — there is exactly one writer and exactly
 * one reader of that file's shape, and this is neither.
 *
 * Every read degrades to an honest empty: a checkout that has never hatched
 * has no proposed cards, and that is a fact, not an error.
 */

import { CABINET_PYTHON, localExec } from './local-exec'
import { readReceipts, type WorkReceipt } from './work-receipts'

/** One proposed card, exactly the fields the writer's read model returns. */
export interface ProposedOutcome {
  id: string
  name: string
  what: string
  why: string
  proof_expected: string
  proposed_digest: string
}

/** Proposed cards awaiting a tap. Never throws. */
export async function listProposedOutcomes(): Promise<ProposedOutcome[]> {
  try {
    const { stdout } = await localExec([
      CABINET_PYTHON, '-m', 'framework.outcomes.ratify', '--list', '--json',
    ])
    if (!stdout) return []
    const parsed = JSON.parse(stdout)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((row) => row && typeof row.id === 'string' && row.id) as ProposedOutcome[]
  } catch (err) {
    console.warn('[outcomes] list failed:', err)
    return []
  }
}

/**
 * The line the home card shows after a tap.
 *
 * Pure, and separate from the read, because it is the sentence an operator
 * actually sees: "Taking on: <name>". A ratified receipt carries the outcome
 * id; the name comes from the card when it is still readable, and the id is
 * the honest fallback rather than a blank.
 */
export function takingOnLine(outcomeId: string, name?: string | null): string {
  const label = (name || '').trim() || outcomeId
  return `Taking on: ${label}`
}

export interface LatestRatified {
  outcomeId: string
  /** The line to render, already composed. */
  line: string
  /** When the tap landed (ISO), or null when the receipt carried no stamp. */
  ts: string | null
  /** Which door it came through, rendered distinctly from the actor. */
  door: string | null
  actor: string | null
}

/**
 * The most recent ratification, or null.
 *
 * Read off the RECEIPTS, not off the outcomes file: the receipt is what says
 * a tap happened, through which door, and when — the file only says the row is
 * active, which it would also say if somebody had edited it by hand.
 */
export async function latestRatified(
  receipts?: WorkReceipt[]
): Promise<LatestRatified | null> {
  const rows = receipts ?? (await readReceipts()).receipts
  let newest: WorkReceipt | null = null
  for (const row of rows) {
    if (row.kind !== 'ratified' || !row.outcome_id) continue
    newest = row // ledger order is oldest-first, so the last match is newest
  }
  if (!newest || !newest.outcome_id) return null
  return {
    outcomeId: newest.outcome_id,
    line: takingOnLine(newest.outcome_id),
    ts: newest.ts,
    door: newest.door,
    actor: newest.actor,
  }
}
