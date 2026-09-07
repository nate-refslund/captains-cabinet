/**
 * Server-side reader for the org's WORK receipts — the second section on
 * /receipts.
 *
 * The page's first section renders the undo journal (what the cabinet DID and
 * how to reverse it). This one renders the responsibility's life off the event
 * ledger: taken on, claimed, completed, verified, or a gap where a silence
 * used to be. Two different records, deliberately side by side and never
 * merged — one is about acts, the other about work.
 *
 * Shells to `framework.missions.receipts --json` (the same shape as
 * `lib/capability-gaps.ts`, which reads the gap ledger through its CLI) so the
 * page and the framework agree on the vocabulary by construction.
 *
 * NEVER throws, and never renders an unreadable ledger as an empty one: the
 * reason comes back with the rows and the page says it.
 */

import { CABINET_PYTHON, localExec } from './local-exec'

/** The declared kind vocabulary — mirrors framework/missions/receipts.py. */
export type WorkReceiptKind =
  | 'ratified'
  | 'started'
  | 'renewed'
  | 'released'
  | 'completed'
  | 'failed'
  | 'verified'
  | 'gap'
  | 'update_applied'
  | 'update_refused'
  | 'update_rolled_back'

export interface WorkReceipt {
  ts: string | null
  kind: WorkReceiptKind
  actor: string | null
  event_id: string | null
  outcome_id: string | null
  task_id: string | null
  claim_id: string | null
  holder: string | null
  door: string | null
  evidence_path: string | null
}

export interface WorkReceiptsReading {
  /** Oldest-first, exactly as the ledger holds them. */
  receipts: WorkReceipt[]
  /** Why nothing could be read, in plain words — null when the count is real. */
  unreadable: string | null
}

const KINDS: ReadonlySet<string> = new Set<WorkReceiptKind>([
  'ratified', 'started', 'renewed', 'released', 'completed', 'failed',
  'verified', 'gap', 'update_applied', 'update_refused', 'update_rolled_back',
])

/** How the door reads to a person — the tap's own distinction, kept visible. */
export const DOOR_LABEL: Record<string, string> = {
  terminal: 'terminal',
  web: 'this dashboard',
  chat: 'chat',
}

export async function readReceipts(): Promise<WorkReceiptsReading> {
  try {
    const { stdout } = await localExec([
      CABINET_PYTHON, '-m', 'framework.missions.receipts', '--json',
    ])
    if (!stdout) return { receipts: [], unreadable: null }
    const parsed = JSON.parse(stdout)
    if (!Array.isArray(parsed)) {
      return { receipts: [], unreadable: 'the receipts reader answered something that is not a list' }
    }
    const rows = parsed.filter(
      (row) => row && typeof row.kind === 'string' && KINDS.has(row.kind)
    ) as WorkReceipt[]
    return { receipts: rows, unreadable: null }
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err)
    return {
      receipts: [],
      // An empty list here would read as "no work has ever happened", which is
      // a claim about a ledger this process just failed to open.
      unreadable: `the work ledger could not be read — ${detail.split('\n').filter(Boolean).slice(-1)[0] || detail}`,
    }
  }
}

/** Newest first, capped — the render order the page wants. */
export function newestFirst(rows: WorkReceipt[], cap: number): WorkReceipt[] {
  return [...rows].reverse().slice(0, cap)
}
