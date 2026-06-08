'use client'

/**
 * One-click Approve / Decline for a pending capability-gap proposal.
 *
 * This is the "no tech knowledge needed" surface — the Captain reads the
 * proposed approach and taps Approve, no CLI. Approve emits the
 * capability_gap_approved event that unlocks the fail-closed install gate;
 * CTO then builds the proposed MCP. Decline closes the gap with a reason
 * (which feeds the learning loop).
 */

import { useState, useTransition } from 'react'
import { approveGap, declineGap } from '@/actions/gaps'

export default function GapApproval({ gapId }: { gapId: string }) {
  const [isPending, startTransition] = useTransition()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  if (declining) {
    return (
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why decline? (feeds the learning loop)"
          className="flex-1 rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
        />
        <div className="flex gap-2">
          <button
            disabled={isPending}
            onClick={() =>
              startTransition(async () => {
                const r = await declineGap(gapId, reason)
                if (!r.ok) setError(r.error || 'failed')
                else setDeclining(false)
              })
            }
            className="rounded bg-red-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-50"
          >
            {isPending ? '…' : 'Confirm decline'}
          </button>
          <button
            onClick={() => { setDeclining(false); setError('') }}
            className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-700"
          >
            Cancel
          </button>
        </div>
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>
    )
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <button
        disabled={isPending}
        onClick={() =>
          startTransition(async () => {
            const r = await approveGap(gapId)
            if (!r.ok) setError(r.error || 'failed')
          })
        }
        className="rounded bg-green-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-600 disabled:opacity-50"
      >
        {isPending ? 'Approving…' : 'Approve'}
      </button>
      <button
        disabled={isPending}
        onClick={() => setDeclining(true)}
        className="rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
      >
        Decline
      </button>
      {error && <span className="text-xs text-red-500">{error}</span>}
    </div>
  )
}
