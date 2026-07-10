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

export const dynamic = 'force-dynamic'

export default async function ReceiptsPage() {
  const payload = await listReceipts()
  const { receipts, total, skipped, skippedFiles, missingDir, error, journalDir, cap } =
    payload

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
    </div>
  )
}
