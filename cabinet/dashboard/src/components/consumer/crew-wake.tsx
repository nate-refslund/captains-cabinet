'use client'

/**
 * WAKE YOUR CABINET — the one control, and its undo, on the card that shows
 * the crew.
 *
 * THE SHAPE, AND WHY. Starting background agents on somebody's own computer is
 * a consequential thing to do, and consequence earns a sentence, not a modal
 * with an OK. So the control opens IN PLACE: the same card grows a short panel
 * that says what starts, where it runs, what it may do without asking, and
 * what it costs — then one button that does exactly what its label says.
 * Nothing is hidden behind a hover, and nothing happens on the first click.
 *
 * THE PROOF IS THE POINT. The connect-Telegram flow ends by showing the
 * operator the message that just landed on their phone. This one ends the same
 * way: it keeps looking until the officer's own state changes, and says so
 * plainly if it never does. "Started" is a claim about a command; "awake" is a
 * measurement, and only the second one is worth showing.
 *
 * NO DEAD ENDS. Every failing path keeps the retry, keeps the detail one
 * disclosure away, and never leaves the operator on a screen whose only
 * remaining move is the back button.
 *
 * The visual system is the dashboard's — the same token object the Telegram
 * flow uses, kept local for the same reason it is local there.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { sleepCrew, wakeCrew } from '@/actions/crew'
import type { CrewOpOutcome, CrewStep } from '@/lib/crew'

const T = {
  panel: 'rounded-xl border border-zinc-800 bg-zinc-950/60',
  title: 'text-zinc-50',
  muted: 'text-zinc-400',
  faint: 'text-zinc-500',
  primary: 'bg-violet-600 text-white hover:bg-violet-500 shadow-lg shadow-violet-950/40',
  ghost: 'text-zinc-300 hover:bg-zinc-800/60 hover:text-white',
  quiet: 'border border-zinc-700 bg-zinc-800/70 text-zinc-100 hover:bg-zinc-800 hover:border-zinc-600',
  ok: 'rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  warn: 'rounded-xl border border-amber-500/40 bg-amber-950/20 text-amber-200',
}

/** How long the flow keeps watching for a first heartbeat, and how often. */
export const WATCH_INTERVAL_MS = 4000
export const WATCH_MAX_TRIES = 20

type Phase = 'idle' | 'confirm' | 'running' | 'watching' | 'settled'

export interface CrewWakePosture {
  sentence: string
  /** True when the probe failed — the sentence is the fail-closed default. */
  unreadable: boolean
  always: string
}

function StepList({ steps }: { steps: CrewStep[] }) {
  return (
    <ol className="mt-3 space-y-1.5" aria-live="polite">
      {steps.map((step) => (
        <li key={step.id} className="flex items-start gap-2 text-sm leading-6">
          <span
            aria-hidden
            className={step.ok ? 'text-emerald-400' : 'text-amber-300'}
          >
            {step.ok ? '✓' : '!'}
          </span>
          <span className={step.ok ? 'text-zinc-300' : 'text-amber-200'}>{step.label}</span>
        </li>
      ))}
    </ol>
  )
}

function Detail({ steps }: { steps: CrewStep[] }) {
  const withDetail = steps.filter((s) => s.detail)
  if (withDetail.length === 0) return null
  return (
    <details className="mt-3">
      <summary className={`cursor-pointer text-xs ${T.faint} hover:text-zinc-300`}>
        What the setup step said
      </summary>
      <ul className="mt-2 space-y-1">
        {withDetail.map((s) => (
          <li key={s.id} className="font-mono text-[0.7rem] leading-5 text-zinc-400">
            {s.detail}
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function CrewWake({
  awake,
  names,
  posture,
}: {
  awake: boolean
  names: string[]
  posture: CrewWakePosture
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [intent, setIntent] = useState<'wake' | 'sleep'>('wake')
  const [outcome, setOutcome] = useState<CrewOpOutcome | null>(null)
  const [sawLife, setSawLife] = useState(false)
  const [gaveUpWatching, setGaveUpWatching] = useState(false)
  const cancelled = useRef(false)

  useEffect(() => () => { cancelled.current = true }, [])

  const who = names.length === 0
    ? 'Your crew'
    : names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`

  /** Watch until an officer actually reports, or until we stop claiming to. */
  const watch = useCallback(async () => {
    setPhase('watching')
    for (let i = 0; i < WATCH_MAX_TRIES; i++) {
      await new Promise((r) => setTimeout(r, WATCH_INTERVAL_MS))
      if (cancelled.current) return
      try {
        const res = await fetch('/api/crew', { cache: 'no-store' })
        if (res.ok) {
          const body = (await res.json()) as { anyAwake?: boolean }
          if (body.anyAwake) {
            setSawLife(true)
            setPhase('settled')
            return
          }
        }
      } catch {
        // A failed poll is not a failed wake. Keep looking; the bound below is
        // what stops this from watching forever and calling that a result.
      }
    }
    setGaveUpWatching(true)
    setPhase('settled')
  }, [])

  const run = useCallback(
    async (op: 'wake' | 'sleep') => {
      setIntent(op)
      setOutcome(null)
      setSawLife(false)
      setGaveUpWatching(false)
      setPhase('running')
      const result = op === 'wake' ? await wakeCrew() : await sleepCrew()
      if (cancelled.current) return
      setOutcome(result)
      if (op === 'wake' && result.ok) {
        await watch()
        return
      }
      setPhase('settled')
    },
    [watch]
  )

  // --- The control, when nothing is in flight -----------------------------
  if (phase === 'idle') {
    return (
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {awake ? (
          <button
            type="button"
            onClick={() => { setIntent('sleep'); setPhase('confirm') }}
            className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${T.ghost}`}
          >
            Put the crew to sleep
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => { setIntent('wake'); setPhase('confirm') }}
              className={`min-h-11 rounded-xl px-4 py-2.5 text-sm font-semibold ${T.primary}`}
            >
              Wake your Cabinet
            </button>
            <span className={`text-xs ${T.faint}`}>
              You can put them back to sleep from here too.
            </span>
          </>
        )}
      </div>
    )
  }

  // --- Consent ------------------------------------------------------------
  if (phase === 'confirm') {
    const waking = intent === 'wake'
    return (
      <div className={`mt-4 p-4 ${T.panel}`}>
        <h3 className={`text-base font-semibold ${T.title}`}>
          {waking ? 'Wake your Cabinet?' : 'Put the crew to sleep?'}
        </h3>
        <ul className={`mt-2 space-y-1.5 text-sm leading-6 ${T.muted}`}>
          {waking ? (
            <>
              <li>{who} starts working in the background on this Mac.</li>
              <li>It keeps working whenever this Mac is on — closing this page does not stop it.</li>
              <li>
                {posture.sentence}
                {posture.unreadable && (
                  <span className="ml-1 text-amber-300">
                    (Its permission setting could not be read just now, so this is the
                    careful default it falls back to.)
                  </span>
                )}
              </li>
              <li>{posture.always}</li>
              <li>It uses your Claude subscription while it works.</li>
            </>
          ) : (
            <>
              <li>{who} stops working in the background.</li>
              <li>Nothing runs on this Mac until you wake them again.</li>
              <li>Nothing is deleted — waking them again puts everything back.</li>
            </>
          )}
        </ul>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => run(intent)}
            className={`min-h-11 rounded-xl px-4 py-2.5 text-sm font-semibold ${
              waking ? T.primary : T.quiet
            }`}
          >
            {waking ? 'Yes, wake them' : 'Yes, put them to sleep'}
          </button>
          <button
            type="button"
            onClick={() => setPhase('idle')}
            className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${T.ghost}`}
          >
            Not now
          </button>
        </div>
      </div>
    )
  }

  // --- Working ------------------------------------------------------------
  if (phase === 'running' || phase === 'watching') {
    return (
      <div className={`mt-4 p-4 ${T.panel}`} aria-busy="true">
        <p className={`text-sm font-medium ${T.title}`}>
          {phase === 'watching'
            ? 'Waiting for the first sign of life…'
            : intent === 'wake'
              ? 'Waking your Cabinet…'
              : 'Putting your crew to sleep…'}
        </p>
        {outcome && <StepList steps={outcome.steps} />}
        {phase === 'watching' && (
          <p className={`mt-2 text-sm leading-6 ${T.muted}`}>
            The first minute is your Cabinet loading itself. You can leave this page —
            it keeps going.
          </p>
        )}
      </div>
    )
  }

  // --- Settled ------------------------------------------------------------
  const failed = !outcome?.ok
  const wakingButQuiet = intent === 'wake' && outcome?.ok && gaveUpWatching
  const tone = failed || wakingButQuiet ? T.warn : T.ok

  return (
    <div className={`mt-4 p-4 ${tone}`} role="status">
      <p className="text-sm font-medium">
        {failed
          ? outcome?.message
          : intent === 'sleep'
            ? outcome?.message
            : sawLife
              ? `${who} is awake and working.`
              : 'Your Cabinet started, but nothing has reported in yet.'}
      </p>
      {wakingButQuiet && (
        <p className="mt-1 text-sm leading-6">
          That is normal on a first start and can take a few minutes. This card shows
          their real state — reload it in a moment.
        </p>
      )}
      {outcome && <StepList steps={outcome.steps} />}
      {outcome && <Detail steps={outcome.steps} />}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {(failed || wakingButQuiet) && (
          <button
            type="button"
            onClick={() => run(intent)}
            className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold ${T.quiet}`}
          >
            Try again
          </button>
        )}
        <button
          type="button"
          onClick={() => { setPhase('idle'); setOutcome(null) }}
          className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${T.ghost}`}
        >
          Done
        </button>
      </div>
    </div>
  )
}
