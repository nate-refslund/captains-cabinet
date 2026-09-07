/**
 * /receipts — READ-ONLY browser over the undo journal (perfect-cabinet
 * Wave B: governance becomes the visible product).
 *
 * Every unattended act the cabinet takes journals a write-ahead row
 * (framework/frontdoor/action_undo.py); this page renders those rows as
 * receipts — what / why / cost / undo — newest first. Doctrine mirrored
 * from decision-queue-card.tsx: render truth + deep-link out, NO buttons,
 * NO mutation endpoints, ever. Undo happens by replying in the Captain's
 * Telegram binder. Honest empties over invented data: a missing journal is
 * said plainly, corrupt lines AND unreadable journal files are counted (an
 * unreadable file must never render as "honestly empty"), seeded demo rows
 * wear a DEMO badge.
 */
import { listReceipts } from '@/actions/receipts'
import ReceiptRow from '@/components/receipts/receipt-row'
import { DOOR_LABEL, newestFirst, readReceipts } from '@/lib/work-receipts'

export const dynamic = 'force-dynamic'

/** Render cap for the work section — the same shape as the journal's. */
const WORK_CAP = 100

export default async function ReceiptsPage() {
  const payload = await listReceipts()
  const { receipts, total, skipped, skippedFiles, missingDir, error, journalDir, cap } =
    payload
  // The SECOND record, deliberately not merged into the first: the undo
  // journal is about acts the cabinet took, this is about the life of a
  // responsibility — taken on, claimed, finished, or missing something.
  const work = await readReceipts()
  const workRows = newestFirst(work.receipts, WORK_CAP)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <div>
        <h1 className="text-2xl font-bold text-white">Receipts</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every acted step the cabinet journals, rendered read-only: what /
          why / cost / undo. This page changes nothing — undo is a reply verb
          in the Captain&apos;s Telegram binder.
        </p>
      </div>

      <div className="max-w-3xl">
        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            journal unreadable ({error}) — showing nothing rather than a guess.
          </p>
        )}

        {/* "honestly empty" may only render when NOTHING was unreadable —
            zero rows with an unreadable file on disk is not an empty journal,
            and the skippedFiles note below carries that state instead. */}
        {!error && receipts.length === 0 && skippedFiles === 0 && (
          <p className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm text-zinc-400">
            no receipts yet — the journal is honestly empty
            {missingDir ? ' (no journal directory exists on this machine yet)' : ''}.
            The first unattended act writes the first row.
          </p>
        )}

        {!error && receipts.length > 0 && (
          <ul className="space-y-3">
            {receipts.map((r) => (
              <ReceiptRow key={r.jid} receipt={r} />
            ))}
          </ul>
        )}

        {skippedFiles > 0 && (
          <p className="mt-3 text-xs text-amber-400">
            {skippedFiles} journal file{skippedFiles === 1 ? '' : 's'} unreadable
            — skipped, never guessed at; rows may exist that this page cannot
            show.
          </p>
        )}

        {skipped > 0 && (
          <p className="mt-3 text-xs text-amber-400">
            {skipped} unparseable journal line{skipped === 1 ? '' : 's'} skipped
            — counted, never guessed at.
          </p>
        )}

        {total > receipts.length && (
          <p className="mt-3 text-xs text-zinc-500">
            showing latest {receipts.length} of {total} receipts (render capped
            at {cap}).
          </p>
        )}

        <p className="mt-6 break-all font-mono text-[10px] text-zinc-600">
          PROOF: journal {journalDir} · {total} row{total === 1 ? '' : 's'}
          {skipped > 0 ? ` · ${skipped} skipped` : ''}
          {skippedFiles > 0 ? ` · ${skippedFiles} file(s) unreadable` : ''} ·
          undo pointer in Redis is only an index — this page reads the durable
          JSONL.
        </p>
      </div>

      <div className="max-w-3xl">
        <h2 className="text-lg font-semibold text-white">Work</h2>
        <p className="mt-1 text-sm text-zinc-500">
          The life of each responsibility, off the event ledger: taken on,
          claimed, finished, verified — or a gap where a silence used to be.
          Read-only, like everything on this page.
        </p>

        {work.unreadable && (
          <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            {work.unreadable} — showing nothing rather than a guess.
          </p>
        )}

        {!work.unreadable && workRows.length === 0 && (
          <p className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm text-zinc-400">
            no work receipts yet — the ledger is honestly empty. The first
            ratified outcome writes the first row.
          </p>
        )}

        {workRows.length > 0 && (
          <ul className="mt-4 space-y-2">
            {workRows.map((row, index) => (
              <li
                key={row.event_id || `${row.kind}-${index}`}
                className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3 text-sm"
              >
                <p className="text-zinc-200">
                  <span className="font-medium text-zinc-100">{row.kind}</span>
                  {row.outcome_id ? <span className="text-zinc-400"> · {row.outcome_id}</span> : null}
                  {row.task_id ? <span className="text-zinc-400"> · {row.task_id}</span> : null}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  {row.actor || 'unattributed'}
                  {row.door ? ` · via ${DOOR_LABEL[row.door] || row.door}` : ''}
                  {row.holder ? ` · held by ${row.holder}` : ''}
                  {row.ts ? ` · ${row.ts}` : ''}
                </p>
                {row.evidence_path && (
                  <p className="mt-1 break-all font-mono text-[10px] text-zinc-600">
                    {row.evidence_path}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}

        {work.receipts.length > workRows.length && (
          <p className="mt-3 text-xs text-zinc-500">
            showing latest {workRows.length} of {work.receipts.length} work
            receipts (render capped at {WORK_CAP}).
          </p>
        )}
      </div>
    </div>
  )
}
