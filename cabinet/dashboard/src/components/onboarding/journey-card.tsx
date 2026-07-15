'use client'

import { FormEvent, useCallback, useEffect, useState } from 'react'
import type {
  OnboardingAction,
  OnboardingResponse,
  OnboardingSurface,
} from '@/lib/onboarding/types'

// A dedup/idempotency id that works in every context. crypto.randomUUID is
// SECURE-CONTEXT ONLY — undefined over plain HTTP on a LAN/tailnet address,
// which is a supported cabinet deploy mode — so calling it directly threw and
// broke every onboarding action. Fall back to getRandomValues (available in
// insecure contexts), then to a time+random id.
function newActionId(surface: string): string {
  const c: Crypto | undefined = globalThis.crypto
  if (typeof c?.randomUUID === 'function') return `${surface}-${c.randomUUID()}`
  if (typeof c?.getRandomValues === 'function') {
    const bytes = c.getRandomValues(new Uint8Array(16))
    return `${surface}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
  }
  return `${surface}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export default function OnboardingJourneyCard({
  surface = 'dashboard',
  variant = 'dashboard',
}: {
  surface?: Extract<OnboardingSurface, 'dashboard' | 'world'>
  variant?: 'dashboard' | 'world'
}) {
  const [journey, setJourney] = useState<OnboardingResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [editScope, setEditScope] = useState(false)
  const [purgeArmed, setPurgeArmed] = useState(false)
  const [purgeConfirmation, setPurgeConfirmation] = useState('')
  const [source, setSource] = useState('~/Documents')
  const [purpose, setPurpose] = useState('Find one useful thing I may be missing.')
  const [destination, setDestination] = useState<'earn' | 'reversible' | 'sovereign'>('reversible')

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/onboarding', { cache: 'no-store' })
      const body = (await response.json()) as OnboardingResponse
      if (!response.ok || !body.ok) throw new Error(body.error || 'Onboarding is unavailable.')
      setJourney(body)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Onboarding is unavailable.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const send = useCallback(
    async (action: OnboardingAction, extra: Record<string, unknown> = {}) => {
      if (!journey) return
      setWorking(true)
      setError(null)
      try {
        const response = await fetch('/api/onboarding', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            action_id: newActionId(surface),
            expected_revision: journey.card.revision,
            surface,
            ...extra,
          }),
        })
        const body = (await response.json()) as OnboardingResponse
        if (!response.ok || !body.ok) {
          if (response.status === 409) await load()
          throw new Error(body.error || 'That choice could not be completed.')
        }
        setJourney(body)
        setEditScope(false)
        setPurgeArmed(false)
        setPurgeConfirmation('')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'That choice could not be completed.')
      } finally {
        setWorking(false)
      }
    },
    [journey, load, surface]
  )

  function submitScope(event: FormEvent) {
    event.preventDefault()
    void send('propose_window', {
      source,
      purpose,
      relationship_destination: destination,
    })
  }

  function choose(action: OnboardingAction) {
    if (action === 'propose_window') {
      if (journey?.state.source?.root) setSource(journey.state.source.root)
      if (journey?.state.purpose) setPurpose(journey.state.purpose)
      if (journey?.state.relationship_destination) {
        setDestination(journey.state.relationship_destination)
      }
      setEditScope(true)
      return
    }
    if (action === 'ratify_charter') {
      void send(action, { charter_hash: journey?.state.charter?.hash })
      return
    }
    if (action === 'purge') {
      setPurgeArmed(true)
      setPurgeConfirmation('')
      return
    }
    void send(action)
  }

  const showForm = journey?.card.stage === 'welcome' || journey?.card.stage === 'purged' || editScope
  const shell = variant === 'world'
    ? 'w-[min(92vw,28rem)] border-4 border-amber-900 bg-[#f4dfaa] text-stone-900 shadow-[6px_6px_0_#3f2b1d]'
    : 'w-full border border-zinc-700 bg-zinc-900 text-zinc-100 shadow-xl'
  const muted = variant === 'world' ? 'text-stone-700' : 'text-zinc-400'
  const input = variant === 'world'
    ? 'border-stone-500 bg-[#fff4d2] text-stone-950 focus:border-stone-900'
    : 'border-zinc-600 bg-zinc-950 text-white focus:border-purple-400'

  if (variant === 'world' && collapsed) {
    return (
      <button
        type="button"
        aria-expanded="false"
        onClick={() => setCollapsed(false)}
        className="min-h-11 rounded-lg border-4 border-amber-900 bg-[#f4dfaa] px-4 py-2 font-semibold text-stone-900 shadow-[4px_4px_0_#3f2b1d]"
      >
        Open orientation
      </button>
    )
  }

  return (
    <section
      className={`rounded-xl p-5 ${shell}`}
      aria-labelledby={journey ? 'onboarding-card-title' : undefined}
      aria-label={journey ? undefined : 'Cabinet orientation'}
    >
      {loading ? (
        <p role="status" className={muted}>Opening your Cabinet orientation…</p>
      ) : journey ? (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className={`text-xs font-semibold uppercase tracking-[0.16em] ${muted}`}>
                First Window · {journey.card.stage.replaceAll('_', ' ')}
              </p>
              <h2 id="onboarding-card-title" className="mt-1 text-xl font-bold">
                {journey.card.title}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <span className={`shrink-0 rounded-full border px-2 py-1 text-xs ${variant === 'world' ? 'border-stone-500' : 'border-zinc-600'}`}>
                read-only
              </span>
              {variant === 'world' && (
                <button
                  type="button"
                  aria-label="Hide orientation card"
                  aria-expanded="true"
                  onClick={() => setCollapsed(true)}
                  className="min-h-11 min-w-11 rounded-md border border-stone-600 text-lg"
                >
                  −
                </button>
              )}
            </div>
          </div>

          <p className={`mt-3 text-sm leading-6 ${muted}`}>{journey.card.body}</p>

          {journey.card.evidence.length > 0 && (
            <div className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70 bg-amber-50/40' : 'border-zinc-700 bg-zinc-950'}`}>
              <h3 className="text-sm font-semibold">Receipt — where this came from</h3>
              <ul className="mt-2 space-y-2 text-sm">
                {journey.card.evidence.map((citation) => (
                  <li key={`${citation.path}:${citation.line}`}>
                    <code>{citation.path}:{citation.line}</code>
                    <span className={`block ${muted}`}>{citation.excerpt}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {showForm && (
            <form className="mt-5 space-y-4" onSubmit={submitScope}>
              <div>
                <label htmlFor={`${surface}-source`} className="block text-sm font-medium">
                  Folder to look through
                </label>
                <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                  <input
                    id={`${surface}-source`}
                    value={source}
                    onChange={(event) => setSource(event.target.value)}
                    className={`min-h-11 flex-1 rounded-md border px-3 py-2 text-sm outline-none ${input}`}
                    autoComplete="off"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setSource('~/Documents')}
                    className={`min-h-11 rounded-md border px-3 text-sm font-medium ${variant === 'world' ? 'border-stone-600 bg-amber-100' : 'border-zinc-600 bg-zinc-800'}`}
                  >
                    Use my Documents
                  </button>
                </div>
                <p className={`mt-1 text-xs ${muted}`}>Choose one specific folder. The whole home folder is refused.</p>
              </div>

              <div>
                <label htmlFor={`${surface}-purpose`} className="block text-sm font-medium">
                  What should I make easier first?
                </label>
                <textarea
                  id={`${surface}-purpose`}
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value)}
                  maxLength={300}
                  rows={2}
                  className={`mt-1 w-full rounded-md border px-3 py-2 text-sm outline-none ${input}`}
                  required
                />
              </div>

              <fieldset>
                <legend className="text-sm font-medium">How should the Cabinet earn your trust?</legend>
                <div className="mt-2 space-y-2 text-sm">
                  {([
                    ['earn', 'Earn every responsibility'],
                    ['reversible', 'Be proactive where actions are reversible — recommended'],
                    ['sovereign', 'Aim for broad autonomy after it is earned'],
                  ] as const).map(([value, label]) => (
                    <label key={value} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-current/20 px-3 py-2">
                      <input
                        type="radio"
                        name={`${surface}-destination`}
                        value={value}
                        checked={destination === value}
                        onChange={() => setDestination(value)}
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                <p className={`mt-1 text-xs ${muted}`}>This sets a destination only. It grants no authority.</p>
              </fieldset>

              <button
                type="submit"
                disabled={working}
                className={`min-h-11 w-full rounded-md px-4 py-2 text-sm font-semibold disabled:opacity-50 ${variant === 'world' ? 'bg-stone-900 text-amber-50' : 'bg-purple-600 text-white hover:bg-purple-500'}`}
              >
                {working ? 'Preparing the Charter…' : 'Show me the Charter first'}
              </button>
            </form>
          )}

          {!showForm && !purgeArmed && journey.card.options.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              {journey.card.options.map((option) => (
                <button
                  key={option.action}
                  type="button"
                  disabled={working}
                  onClick={() => choose(option.action)}
                  className={`min-h-11 rounded-md border px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                    option.danger
                      ? 'border-red-500/70 text-red-700 dark:text-red-300'
                      : variant === 'world'
                        ? 'border-stone-700 bg-amber-100'
                        : 'border-zinc-600 bg-zinc-800 hover:bg-zinc-700'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}

          {purgeArmed && (
            <form
              className={`mt-5 rounded-lg border p-4 ${variant === 'world' ? 'border-red-800/70 bg-red-50/40' : 'border-red-700/70 bg-red-950/30'}`}
              onSubmit={(event) => {
                event.preventDefault()
                void send('purge', { confirmation: purgeConfirmation })
              }}
            >
              <label htmlFor={`${surface}-purge-confirmation`} className="block text-sm font-semibold">
                Type PURGE to permanently delete this onboarding record
              </label>
              <p className={`mt-1 text-xs ${muted}`}>
                This removes the Charter, event history, manifest, and derived excerpts. It cannot be undone.
              </p>
              <input
                id={`${surface}-purge-confirmation`}
                value={purgeConfirmation}
                onChange={(event) => setPurgeConfirmation(event.target.value)}
                autoComplete="off"
                className={`mt-3 min-h-11 w-full rounded-md border px-3 py-2 text-sm outline-none ${input}`}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={working || purgeConfirmation !== 'PURGE'}
                  className="min-h-11 rounded-md border border-red-600 bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Permanently delete onboarding data
                </button>
                <button
                  type="button"
                  disabled={working}
                  onClick={() => {
                    setPurgeArmed(false)
                    setPurgeConfirmation('')
                  }}
                  className={`min-h-11 rounded-md border px-4 py-2 text-sm font-medium ${variant === 'world' ? 'border-stone-700 bg-amber-100' : 'border-zinc-600 bg-zinc-800'}`}
                >
                  Keep it
                </button>
              </div>
            </form>
          )}
        </>
      ) : (
        <div className="space-y-3">
          <p className={muted}>The Cabinet orientation could not be loaded.</p>
          <button
            type="button"
            onClick={() => { setError(null); setLoading(true); void load() }}
            className={`min-h-11 rounded-md border px-4 py-2 text-sm font-medium ${variant === 'world' ? 'border-stone-700 bg-amber-100' : 'border-zinc-600 bg-zinc-800 hover:bg-zinc-700'}`}
          >
            Try again
          </button>
        </div>
      )}

      <div aria-live="polite" className="mt-3 min-h-5 text-sm">
        {working && <span className={muted}>The Cabinet is working on that…</span>}
        {error && <span className="font-medium text-red-600 dark:text-red-300">{error}</span>}
      </div>
    </section>
  )
}
