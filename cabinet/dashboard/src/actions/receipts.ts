'use server'

/**
 * receipts.ts — the /receipts read model (perfect-cabinet Wave B).
 *
 * READ-ONLY by doctrine: this module exposes exactly one lookup over the
 * undo-journal JSONL (`framework/frontdoor/action_undo.py` owns the journal;
 * dir resolution + parsing live in `@/components/receipts/journal`). It
 * never writes the journal, never touches Redis (the pointer is only an
 * index — the JSONL is the durable truth, so this page works with Redis
 * absent), and never exposes an undo/approve mutation — undo happens in the
 * Captain's Telegram binder. Takes no arguments: no caller input can reach
 * a path or a filter.
 */

import { readJournal, shapeReceipt, type ReceiptView } from '@/components/receipts/journal'
import { requireDashboardAuth } from '@/lib/provisioning/guard'

/** Render cap — newest first; the page says "showing latest N of M". */
const SHOW_CAP = 100

export interface ReceiptsPayload {
  /** Newest-first, capped at `cap`. */
  receipts: ReceiptView[]
  /** Total collapsed journal rows on disk. */
  total: number
  /** Corrupt journal lines skipped (counted honestly, never crashed on). */
  skipped: number
  /** Journal files present but unreadable — counted so the page never claims
   * "honestly empty" over rows it could not read. */
  skippedFiles: number
  /** Journal dir absent — an honest "no receipts yet", not an error. */
  missingDir: boolean
  /** Journal dir present but unreadable — rendered loudly, never guessed. */
  error: string | null
  /** Resolved journal dir (the page's proof line). */
  journalDir: string
  cap: number
}

export async function listReceipts(): Promise<ReceiptsPayload> {
  // The undo journal is a full record of every sensitive action taken — gate
  // it. On unauth, return an empty, well-formed payload with an honest error
  // (the page already renders `error` loudly), never the journal rows.
  if (!(await requireDashboardAuth())) {
    return {
      receipts: [],
      total: 0,
      skipped: 0,
      skippedFiles: 0,
      missingDir: false,
      error: 'Unauthorized',
      journalDir: '',
      cap: SHOW_CAP,
    }
  }
  const { rows, skipped, skippedFiles, missingDir, error, journalDir } =
    await readJournal()
  const nowMs = Date.now()
  const newestFirst = [...rows].sort((a, b) => {
    const ta = String(a.ts ?? '')
    const tb = String(b.ts ?? '')
    return ta < tb ? 1 : ta > tb ? -1 : 0
  })
  return {
    receipts: newestFirst.slice(0, SHOW_CAP).map((r) => shapeReceipt(r, nowMs)),
    total: rows.length,
    skipped,
    skippedFiles,
    missingDir,
    error,
    journalDir,
    cap: SHOW_CAP,
  }
}
