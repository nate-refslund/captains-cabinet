'use client'

/**
 * The home card for the update path: one line of plain language, one button.
 *
 * What the Captain sees is the whole point of this leg — an improvement the
 * org made about itself reaching the machine he actually runs, without a
 * terminal. So: "Update ready — N files changed", the changelog underneath,
 * Apply. After it lands: "Updated to <sha>: N changes", Roll back.
 *
 * The card never claims a state it did not read. While an apply is in flight
 * the dashboard is being restarted underneath it, so the button goes to a
 * waiting line rather than a spinner that would outlive the process.
 *
 * THE PROVENANCE LINE carries all three facts about a waiting bundle: when it
 * was BUILT, who put it in the inbox, and when. The inbox is same-uid
 * writable (A5.11), so "where did this come from" is a question the Captain
 * must be able to answer from the card before tapping Apply — and the build
 * time is the half that says whether the thing waiting is newer than what is
 * running.
 */

import { useState, useTransition } from 'react'
import { applyUpdate, rollbackUpdate } from '@/actions/updates'
import type { UpdateStatus } from '@/lib/updates'

export default function UpdateCard({
  status,
  headline,
}: {
  status: UpdateStatus
  headline: string
}) {
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState('')
  const [launched, setLaunched] = useState('')

  const waiting = status.latest
  const applied = status.phase === 'applied' && status.last?.to_sha
  const canRollBack = status.snapshots.length > 0

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-white">{headline}</p>
          {waiting && waiting.changelog.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-zinc-400">
              {waiting.changelog.slice(0, 5).map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
          {waiting && (
            <p className="mt-2 text-xs text-zinc-500">
              Built {waiting.built_at || 'at an unrecorded time'} · placed by{' '}
              {waiting.owner || 'an unknown account'} at {waiting.mtime}
            </p>
          )}
          {applied && (status.last?.skipped_preserved?.length ?? 0) > 0 && (
            <p className="mt-2 text-xs text-amber-300">
              Kept your own copy of {status.last?.skipped_preserved?.length} file(s)
              instead of the shipped one.
            </p>
          )}
          {launched && <p className="mt-2 text-xs text-zinc-400">{launched}</p>}
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </div>

        <div className="flex shrink-0 gap-2">
          {waiting && (
            <button
              disabled={isPending}
              onClick={() =>
                startTransition(async () => {
                  setError('')
                  const r = await applyUpdate(waiting.sha)
                  if (!r.ok) setError(r.error || 'could not start the update')
                  else setLaunched('Taking it now — this page restarts when it lands.')
                })
              }
              className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              Apply
            </button>
          )}
          {canRollBack && (
            <button
              disabled={isPending}
              onClick={() =>
                startTransition(async () => {
                  setError('')
                  const r = await rollbackUpdate()
                  if (!r.ok) setError(r.error || 'could not start the rollback')
                  else setLaunched('Putting the previous bytes back.')
                })
              }
              className="rounded border border-zinc-600 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
            >
              Roll back
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
