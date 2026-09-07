'use client'

/**
 * A PROPOSED OUTCOME CARD, with the one control it was always missing.
 *
 * The card renders what the org proposed — what, why, and the proof it expects
 * to be judged by — and ends in a Ratify button. Before this, the card ended
 * in a sentence telling the operator to open a YAML file and move a row.
 *
 * Consequence earns a sentence, not a modal: ratifying turns a suggestion into
 * something the org will start doing, so the button says what it does and the
 * card says what changes. Nothing is hidden behind a hover, and the result is
 * a MEASUREMENT — the card reports the writer's own status word, never a
 * cheerful claim about a command that may not have run.
 */

import { useState, useTransition } from 'react'
import { ratifyOutcome } from '@/actions/outcomes'
import type { ProposedOutcome } from '@/lib/outcomes'

type Phase = 'idle' | 'done' | 'failed'

export default function ProposedCard({ outcome }: { outcome: ProposedOutcome }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [detail, setDetail] = useState<string>('')
  const [pending, startTransition] = useTransition()

  function onRatify() {
    startTransition(async () => {
      const res = await ratifyOutcome(outcome.id)
      if (res.ok) {
        setPhase('done')
        setDetail(res.status === 'already_ratified' ? 'it was already ratified' : '')
      } else {
        setPhase('failed')
        setDetail(res.error || 'nothing was written')
      }
    })
  }

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-5">
      <p className="text-xs uppercase tracking-widest text-zinc-500">Proposed</p>
      <h3 className="mt-1 text-lg font-semibold text-white">{outcome.name || outcome.id}</h3>

      {outcome.what && (
        <p className="mt-3 text-sm leading-relaxed text-zinc-300">{outcome.what}</p>
      )}
      {outcome.why && (
        <p className="mt-2 text-sm leading-relaxed text-zinc-400">
          <span className="text-zinc-500">Why: </span>
          {outcome.why}
        </p>
      )}
      {outcome.proof_expected && (
        <p className="mt-2 text-sm leading-relaxed text-zinc-400">
          <span className="text-zinc-500">Proof expected: </span>
          {outcome.proof_expected}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {phase !== 'done' && (
          <button
            type="button"
            onClick={onRatify}
            disabled={pending}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-violet-950/40 transition-colors hover:bg-violet-500 disabled:opacity-60"
          >
            {pending ? 'Ratifying…' : 'Ratify'}
          </button>
        )}
        <span className="font-mono text-[11px] text-zinc-600">{outcome.id}</span>
      </div>

      {phase === 'idle' && (
        <p className="mt-3 text-xs text-zinc-500">
          Ratifying makes this an active outcome your Cabinet may start working
          on, and writes a receipt saying you did it.
        </p>
      )}
      {phase === 'done' && (
        <p className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          Taking on: {outcome.name || outcome.id}
          {detail ? ` — ${detail}` : ''}. The receipt is on /receipts.
        </p>
      )}
      {phase === 'failed' && (
        <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200">
          Not ratified — {detail}. Nothing was changed.
        </p>
      )}
    </article>
  )
}
