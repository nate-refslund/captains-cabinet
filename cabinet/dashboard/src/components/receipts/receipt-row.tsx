/**
 * ReceiptRow — one undo-journal row, rendered READ-ONLY.
 *
 * Mirrors the decision-queue-card doctrine (Captain ruling 2026-07-09):
 * this surface renders truth and deep-links out — it NEVER grows
 * approve/skip/undo buttons, mutation endpoints, or client JS. The undo
 * handle is a NOTE pointing at the Captain's Telegram binder, and it teaches
 * ONLY the grammar the binder registers (binder_wire._UNDO_RE): reply "undo"
 * to the act's own ·pid·-marked receipt message, or "undo <n>" against its
 * digest line (manifest-or-nothing). A typed pid is NOT a selector — the
 * binder parses it as free-text "why", so the pid renders here purely as an
 * identifier for cross-checking. Pure server component: props in, markup out.
 */
import type { ReceiptView, UndoStateKind } from './journal'

const STATE_BADGE: Record<UndoStateKind, string> = {
  active: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  expired: 'border-zinc-600/40 bg-zinc-700/20 text-zinc-400',
  undone: 'border-blue-500/30 bg-blue-500/15 text-blue-300',
  'dead-letter': 'border-red-500/30 bg-red-500/15 text-red-300',
  'undo-failed': 'border-red-500/30 bg-red-500/10 text-red-300',
  void: 'border-zinc-600/40 bg-zinc-700/20 text-zinc-500',
  unconfirmed: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  unknown: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
}

export default function ReceiptRow({ receipt }: { receipt: ReceiptView }) {
  const badge = STATE_BADGE[receipt.state.kind] ?? STATE_BADGE.unknown

  return (
    <li className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      {/* What */}
      <div className="flex flex-wrap items-center gap-2">
        {receipt.demo && (
          <span
            className="rounded-full border border-fuchsia-500/40 bg-fuchsia-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-fuchsia-300"
            title="seeded demo receipt — explicitly labeled, not a real action"
          >
            DEMO
          </span>
        )}
        <span className="text-sm font-medium text-zinc-100">
          {receipt.action}
          {!receipt.actionMapped && (
            <span
              className="ml-1 text-xs text-zinc-500"
              title="no phrase-map entry for this action id — showing the raw slug"
            >
              (raw action id)
            </span>
          )}
        </span>
        {receipt.subject && (
          <span className="truncate text-sm text-zinc-400">— {receipt.subject}</span>
        )}
      </div>

      {/* Why (when the row captured one — never invented) */}
      {receipt.why && (
        <p className="mt-1.5 text-xs text-zinc-400">
          <span className="text-zinc-500">why:</span> {receipt.why}
        </p>
      )}

      {/* Time · lane · cost · undo state */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-500">
        <span>{receipt.timeLabel}</span>
        <span>lane {receipt.lane}</span>
        <span>cost {receipt.costLabel}</span>
        <span className={`rounded-full border px-2 py-0.5 ${badge}`}>
          {receipt.state.label}
        </span>
      </div>

      {/* Undo deep-link NOTE — text only; the binder holds the real verbs.
          Registered grammar only: bare "undo" binds via the ·pid· marker on
          the replied-to receipt message; "undo <n>" selects a digest line by
          index. Never teach "undo <pid>" — the binder reads a typed pid as
          free-text why, and the single-open-window fallback could then
          reverse a DIFFERENT act than the one named.
          DEMO rows (demo: true — seeded fixture/anatomy rows, inverse op
          none by contract) get the honest variant instead: there is no
          receipt message in the binder for them and nothing real to
          reverse, so teaching the undo grammar here would point at a verb
          that cannot bind (demo-kit cross-area suggestion, applied at
          Wave-B integration). */}
      {receipt.demo ? (
        <p className="mt-2 font-mono text-[11px] text-zinc-600">
          demo row — nothing real to reverse; reply-to-undo works on real
          receipts only — this row is {receipt.pid}; this page renders
          receipts, it never acts on them.
        </p>
      ) : (
        <p className="mt-2 font-mono text-[11px] text-zinc-600">
          undo in the Telegram binder: reply{' '}
          <span className="text-zinc-400">undo</span> to this act&apos;s receipt
          message, or <span className="text-zinc-400">undo &lt;n&gt;</span>{' '}
          against its digest line — this row is {receipt.pid}; this page renders
          receipts, it never acts on them.
        </p>
      )}
    </li>
  )
}
