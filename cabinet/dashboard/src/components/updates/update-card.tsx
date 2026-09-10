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
 * A REFUSAL IS A STATE THIS CARD RENDERS (A5.15), not an absence of one.
 * Measured on the installed Cabinet 2026-09-08: an apply refused because one
 * constitutional file differed, wrote nothing down, and this card would have
 * gone on offering "Update ready" for that same bundle — an Apply button that
 * fails identically every time it is tapped, with nothing anywhere saying why.
 * So the refused headline names the count, the card names the FILES, and the
 * Apply button is withdrawn for exactly the refusal a retry cannot fix.
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
import { applyTarget, refusalToShow, type UpdateStatus } from '@/lib/updates-view'

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

  // A5.15. The refusal comes from the SAME helper the headline used, so the
  // card can never name files under a sentence that says something else.
  const refusal = refusalToShow(status)
  // A constitutional refusal is the one an operator cannot retry into
  // succeeding: those bytes change by a deliberate unlock-and-relock, and an
  // Apply button there is a button that fails identically every time it is
  // tapped. A refusal with no paths — a bad digest, an unreadable bundle — and
  // a bundle this box rolled back say what happened and LEAVE the button,
  // because a retry re-tests. The gate is `applyTarget` rather than an
  // expression here so the oracle can drive it: `apply_live` is a column on
  // all 5250 rows, and an inline condition cannot be held to a table.
  const waiting = applyTarget(status)
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
          {refusal && refusal.paths.length > 0 && (
            <>
              <ul className="mt-2 list-disc pl-5 text-xs text-amber-300">
                {refusal.paths.slice(0, 5).map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-zinc-400">
                Nothing was applied. These files change by a deliberate unlock,
                apply and lock in one sitting — not by an update.
              </p>
            </>
          )}
          {refusal && refusal.paths.length === 0 && (
            <p className="mt-2 text-xs text-zinc-400">
              Nothing was applied.
            </p>
          )}
          {/* A5.16. Two causes, one of which heals itself and one of which
              does not, so they get two sentences. Round 1 gave a full disk
              the reassuring one. */}
          {status.ledger_error ? (
            <p className="mt-2 text-xs text-amber-300">
              The record of this is held on disk — ledger fault:{' '}
              {status.ledger_error}. No update files this one; the ledger
              itself needs looking at.
            </p>
          ) : status.event_fallback ? (
            <p className="mt-2 text-xs text-zinc-500">
              The record of this is held on disk — this Cabinet&apos;s ledger does
              not know the update events yet, and the next update files it.
            </p>
          ) : null}
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
