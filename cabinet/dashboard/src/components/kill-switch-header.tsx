'use client'

/**
 * KillSwitchHeader — Spec 032 §5 persistent kill switch.
 *
 * Always mounted in the layout header area (both Consumer and Advanced modes).
 * Spec §5: "Persistent header button on desktop (always-visible red '⏸ Stop All' pill)"
 * "NOT in hamburger" — this lives in the mobile top chrome too.
 *
 * Consumer mode: one-tap shows confirmation step (Spec 032 OPPORTUNITY absorbed per CRO).
 * Advanced mode: same one-tap + confirm behavior (consistent across modes).
 *
 * Fires the existing cabinet:killswitch Redis key via toggleKillSwitch server action.
 *
 * TWO FIXES, 2026-07-31, both the same class — a claim with no measurement
 * behind it:
 *
 *  1. THE STATE. The prop was `active: boolean`, read from
 *     `value === 'active'` with no try/catch and no mock-mode disclosure, so a
 *     dead store, a mock store and a verified-clear switch all rendered the
 *     same "⏸ Stop All" pill — which reads as "the fleet is running". It now
 *     takes a `KillswitchGlance`, and the unknown state says so on the pill.
 *  2. THE RESULT. `await toggleKillSwitch()` discarded its return value and
 *     flipped the label optimistically, so an Unauthorized or a Redis error
 *     still showed "▶ Resume" — the pill claiming the fleet was halted when
 *     nothing had been written. It now reports what the action returned, and
 *     a failure prints the exact CLI fallback rather than a silent lie.
 */

import { useState, useTransition } from 'react'
import { toggleKillSwitch } from '@/actions/killswitch'
import {
  fallbackCommandFor,
  intentFor,
  killswitchGlance,
  type KillswitchGlance,
} from '@/lib/world/killswitch'

interface KillSwitchHeaderProps {
  state: KillswitchGlance
}

export default function KillSwitchHeader({ state }: KillSwitchHeaderProps) {
  const [confirming, setConfirming] = useState(false)
  const [isPending, startTransition] = useTransition()
  /** Local echo of a CONFIRMED write only — never an optimistic flip. */
  const [written, setWritten] = useState<KillswitchGlance | null>(null)
  const [error, setError] = useState<string | null>(null)

  const shown = written ?? state
  const engaged = shown.state === 'engaged'
  const unknown = shown.state === 'unknown'

  function act(intent: 'activate' | 'deactivate') {
    setError(null)
    startTransition(async () => {
      const r = await toggleKillSwitch(intent)
      if (r?.success) {
        setWritten(killswitchGlance(intent === 'activate'))
        setConfirming(false)
      } else {
        // The action reads the key back before reporting success, so a failure
        // here means the stop is NOT provably in the state you asked for. Say
        // that, and give the command that can prove it.
        setError(
          `${r?.error ?? 'the write could not be verified'} — run: ${fallbackCommandFor(intent)}`
        )
      }
    })
  }

  function handleClick() {
    if (!confirming) {
      setConfirming(true)
      return
    }
    // Under an unknown reading there is no direction to derive, so the two
    // verbs are offered explicitly instead of a toggle.
    const intent = intentFor(shown)
    if (intent) act(intent)
  }

  function handleCancel() {
    setConfirming(false)
    setError(null)
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="hidden text-xs sm:block">
          {error ? (
            <span className="font-mono text-[11px] text-red-400">{error}</span>
          ) : (
            <span className="text-zinc-400">
              {unknown
                ? 'State unknown — choose:'
                : engaged
                  ? 'Resume officers?'
                  : 'Stop all officers?'}
            </span>
          )}
        </span>
        <button
          onClick={handleCancel}
          disabled={isPending}
          className="min-h-[44px] rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800 disabled:opacity-50"
          aria-label="Cancel"
        >
          Cancel
        </button>
        {unknown ? (
          <>
            <button
              onClick={() => act('activate')}
              disabled={isPending}
              className="min-h-[44px] rounded-lg bg-red-600 px-4 py-1.5 text-xs font-bold text-white transition-colors hover:bg-red-500 disabled:opacity-50"
              aria-label="Engage the kill switch"
            >
              {isPending ? '...' : 'Engage Stop'}
            </button>
            <button
              onClick={() => act('deactivate')}
              disabled={isPending}
              className="min-h-[44px] rounded-lg bg-green-600 px-4 py-1.5 text-xs font-bold text-white transition-colors hover:bg-green-500 disabled:opacity-50"
              aria-label="Release the kill switch"
            >
              {isPending ? '...' : 'Release Stop'}
            </button>
          </>
        ) : (
          <button
            onClick={handleClick}
            disabled={isPending}
            className={`min-h-[44px] rounded-lg px-4 py-1.5 text-xs font-bold transition-colors disabled:opacity-50 ${
              engaged
                ? 'bg-green-600 text-white hover:bg-green-500'
                : 'bg-red-600 text-white hover:bg-red-500'
            }`}
            aria-label={engaged ? 'Confirm resume' : 'Confirm stop all officers'}
          >
            {isPending ? '...' : engaged ? 'Confirm Resume' : 'Confirm Stop'}
          </button>
        )}
      </div>
    )
  }

  return (
    <button
      onClick={handleClick}
      disabled={isPending}
      data-killswitch-pill={engaged ? 'engaged' : unknown ? 'unknown' : 'clear'}
      className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-bold transition-colors disabled:opacity-50 ${
        engaged
          ? 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
          : unknown
            ? 'border border-dashed border-amber-400 bg-amber-600/10 text-amber-300 hover:bg-amber-600/20'
            : 'bg-red-600/20 text-red-400 hover:bg-red-600/30'
      }`}
      title={
        engaged
          ? 'Kill switch is active — officers halted. Click to resume.'
          : shown.state === 'unknown'
            ? `Kill switch state UNKNOWN: ${shown.reason}. This is not "off" — nobody could read it.`
            : 'Stop all officers'
      }
      aria-label={
        engaged
          ? 'Kill switch active — click to resume officers'
          : unknown
            ? 'Kill switch state unknown — nobody could read it'
            : 'Stop all officers'
      }
    >
      <span aria-hidden="true">{engaged ? '▶' : unknown ? '?' : '⏸'}</span>
      <span>{engaged ? 'Resume' : unknown ? 'Stop — state unknown' : 'Stop All'}</span>
    </button>
  )
}
