'use client'

import { useState, useTransition } from 'react'
import { updateCaptainAvailability } from '@/actions/config'
import {
  AVAILABILITY_MAX_MINUTES,
  AVAILABILITY_MODES,
  AVAILABILITY_REFUSAL,
  parseAvailabilityValue,
  renderAvailability,
} from '@/lib/availability'
import type { CaptainAvailability } from '@/lib/config'

/**
 * "Time for the cabinet" — the Captain's declared time budget, editable here.
 *
 * Until 2026-07-27 this row was display-only and the text told him to go to
 * Telegram. That failed the captain-controls rule: a control that exists on one
 * device is not a control he has. The write path is the same one the phone
 * uses — the store's own recorder — so a dashboard change and a phone change
 * are the same append to the same append-only file, and neither can win by
 * being newer in a different place.
 *
 * WHAT IT SHOWS. The current value, WHERE it came from (his own later ruling,
 * or what onboarding stamped), and the whole mode table — he should not have to
 * remember the verbs to use the dial.
 *
 * UNKNOWN STAYS UNKNOWN. When nothing has been declared, the picker opens on
 * "Choose…" with Save disabled. It does not preselect a band: a default that
 * looks like an answer nobody gave is the exact failure this dial's own
 * onboarding step refuses (skip writes nothing).
 *
 * This is a value he declared about himself — a budget the org fits itself to.
 * It is never a measure of him or of anyone, and nothing here renders it as one.
 */

const CUSTOM = '__custom__'

function sourceLine(a: CaptainAvailability): string {
  if (a.minutesPerDay === null) {
    return 'Nobody has said how much of your day the cabinet may use, so it keeps its quiet defaults.'
  }
  const when = a.setAt ? ` (${a.setAt.slice(0, 10)})` : ''
  if (a.source === 'adjusted') {
    return `Your latest setting${when}. The org fits this budget — it never asks you to fit the org.`
  }
  if (a.source === 'onboarding') {
    return 'From onboarding. The org fits this budget — it never asks you to fit the org.'
  }
  return 'The org fits this budget — it never asks you to fit the org.'
}

export function AvailabilityField({ availability }: { availability: CaptainAvailability }) {
  const [editing, setEditing] = useState(false)
  const [choice, setChoice] = useState('')
  const [minutes, setMinutes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleEdit() {
    // Preselect only what he actually declared. A band whose minutes match the
    // current value selects that band; any other number opens the exact-minutes
    // input on it; UNKNOWN opens on "Choose…".
    const current = availability.minutesPerDay
    const band = AVAILABILITY_MODES.find((m) => m.minutes === current)
    if (current === null) {
      setChoice('')
      setMinutes('')
    } else if (band && (availability.mode === null || availability.mode === band.mode)) {
      setChoice(band.mode)
      setMinutes(String(current))
    } else {
      setChoice(CUSTOM)
      setMinutes(String(current))
    }
    setError(null)
    setEditing(true)
  }

  function handleCancel() {
    setEditing(false)
    setError(null)
  }

  function handleSave() {
    const raw = choice === CUSTOM ? minutes : choice
    // The client refuses first so an impossible value costs no round trip; the
    // server refuses again, and the server is the gate.
    if (!parseAvailabilityValue(raw)) {
      setError(AVAILABILITY_REFUSAL)
      return
    }
    startTransition(async () => {
      const result = await updateCaptainAvailability(raw)
      if (result.success) {
        setEditing(false)
        setError(null)
      } else {
        setError(result.error || 'Failed to save')
      }
    })
  }

  if (!editing) {
    return (
      <div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-zinc-300">Time for the cabinet</span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-500">{renderAvailability(availability)}</span>
            <button
              onClick={handleEdit}
              className="shrink-0 text-zinc-600 transition-colors hover:text-zinc-400"
              title="Edit"
              aria-label="Edit time for the cabinet"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125" />
              </svg>
            </button>
          </div>
        </div>
        <p className="mt-1 text-xs text-zinc-600">{sourceLine(availability)}</p>
      </div>
    )
  }

  const saveDisabled = isPending || choice === '' || (choice === CUSTOM && minutes.trim() === '')

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm text-zinc-500" htmlFor="availability-choice">
        Time for the cabinet
      </label>
      <select
        id="availability-choice"
        value={choice}
        onChange={(e) => {
          setChoice(e.target.value)
          setError(null)
        }}
        disabled={isPending}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none disabled:opacity-50"
        style={{ padding: '8px 12px' }}
      >
        <option value="">Choose…</option>
        {AVAILABILITY_MODES.map((m) => (
          <option key={m.mode} value={m.mode}>
            {m.label}
          </option>
        ))}
        <option value={CUSTOM}>Exact minutes a day…</option>
      </select>
      {choice === CUSTOM && (
        <input
          type="number"
          min={0}
          max={AVAILABILITY_MAX_MINUTES}
          step={1}
          value={minutes}
          onChange={(e) => {
            setMinutes(e.target.value)
            setError(null)
          }}
          disabled={isPending}
          placeholder={`Whole minutes, 0–${AVAILABILITY_MAX_MINUTES}`}
          aria-label="Exact minutes a day"
          className="w-full rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none"
          style={{ padding: '8px 12px' }}
        />
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
      <p className="text-xs text-zinc-600">
        Same dial as Telegram (&quot;availability 20m&quot;) — one value, wherever you set it.
      </p>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saveDisabled}
          className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-green-500 disabled:opacity-50"
        >
          {isPending ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={handleCancel}
          disabled={isPending}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
