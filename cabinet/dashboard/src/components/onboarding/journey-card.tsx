'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import type {
  OnboardingAction,
  OnboardingIdentityAsk,
  OnboardingResponse,
  OnboardingSurface,
  OwnershipClass,
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

// The identity picker's empty starting value, module-level and frozen so it has
// a STABLE identity. journey-card.test.ts scripts the hook order and asserts
// each initial value with Object.is — deliberately, so a hook added, removed or
// reordered fails loudly there instead of silently testing the wrong state — and
// a fresh `{}` per render would make that assertion unsatisfiable.
export const NO_IDENTITY_PICKS: Readonly<Record<string, string>> = Object.freeze({})

// How many of a connector's accounts lead the picker before the rest go behind
// a disclosure. A LAYOUT number and nothing else — the core decides who is
// offered, and every account it offers is reachable here without scripting.
export const IDENTITY_SHOWN = 8

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
  // No initial value, deliberately: an unclassified source is REFUSED by the
  // core, so pre-selecting "mine" here would answer the operator's question for
  // them and defeat the whole gate.
  const [ownership, setOwnership] = useState<OwnershipClass | ''>('')
  const [authorityBasis, setAuthorityBasis] = useState('')
  // The seed answer. The core PRINTED its question on this card and offered no
  // field to answer it, so a few words about the operator's work had nowhere to
  // go and the discovery path they are supposed to start could never start.
  const [seed, setSeed] = useState('')
  const [feedbackRecorded, setFeedbackRecorded] = useState<string | null>(null)
  // Which account is the operator, per connector. Empty until they pick: the
  // core resolves the operator ONLY from what they say, so pre-selecting the
  // likeliest-looking candidate here would answer for them — and a wrong
  // attribution reads exactly like a right one.
  const [handles, setHandles] = useState<Readonly<Record<string, string>>>(NO_IDENTITY_PICKS)
  const effectiveSurface = useRef<Extract<OnboardingSurface, 'dashboard' | 'world' | 'companion'>>(surface)
  const handoffIds = useRef<{ trace_id?: string; correlation_id?: string }>({})
  const seedFieldRef = useRef<HTMLTextAreaElement | null>(null)

  const reportEvidence = useCallback(async (
    phase: 'transport' | 'ui' | 'feedback',
    status: 'started' | 'succeeded' | 'failed' | 'retried' | 'interrupted' | 'recovered' | 'useful' | 'not_useful' | 'corrected',
    detail: Record<string, unknown>,
    ids: { action_id?: string; trace_id?: string; correlation_id?: string } = {}
  ): Promise<boolean> => {
    try {
      const response = await fetch('/api/onboarding/evidence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
        body: JSON.stringify({
          phase,
          status,
          surface: effectiveSurface.current,
          action_id: ids.action_id || newActionId('observe'),
          trace_id: ids.trace_id || newActionId('trace'),
          correlation_id: ids.correlation_id || newActionId('corr'),
          detail,
        }),
      })
      if (!response.ok) return false
      const body = await response.json() as { ok?: boolean }
      return body.ok === true
    } catch {
      console.error('[onboarding-ui] evidence endpoint unavailable')
      return false
    }
  }, [])

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/onboarding', { cache: 'no-store' })
      const body = (await response.json()) as OnboardingResponse
      if (!response.ok || !body.ok) throw new Error(body.error || 'Onboarding is unavailable.')
      setJourney(body)
      setError(null)
      if (body.card.stage !== 'purged') {
        void reportEvidence('ui', 'succeeded', {
          rendered_stage: body.card.stage,
          app_shell_handoff: effectiveSurface.current === 'companion',
        }, handoffIds.current)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Onboarding is unavailable.')
      void reportEvidence('transport', 'failed', { error_code: 'onboarding_load_failed' }, handoffIds.current)
    } finally {
      setLoading(false)
    }
  }, [reportEvidence])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('from') === 'companion') {
      effectiveSurface.current = 'companion'
      handoffIds.current = {
        trace_id: params.get('trace_id') || undefined,
        correlation_id: params.get('correlation_id') || undefined,
      }
      void reportEvidence('ui', 'started', { app_shell_handoff: true }, handoffIds.current)
    }
    void load()
  }, [load, reportEvidence])

  useEffect(() => {
    const onWindowError = () => {
      void reportEvidence('ui', 'failed', { error_code: 'window_error' })
    }
    const onUnhandledRejection = () => {
      void reportEvidence('ui', 'failed', { error_code: 'unhandled_rejection' })
    }
    window.addEventListener('error', onWindowError)
    window.addEventListener('unhandledrejection', onUnhandledRejection)
    return () => {
      window.removeEventListener('error', onWindowError)
      window.removeEventListener('unhandledrejection', onUnhandledRejection)
    }
  }, [reportEvidence])

  const send = useCallback(
    async (action: OnboardingAction, extra: Record<string, unknown> = {}) => {
      if (!journey) return
      setWorking(true)
      setError(null)
      const ids = {
        action_id: newActionId(effectiveSurface.current),
        trace_id: newActionId('trace'),
        correlation_id: newActionId('corr'),
      }
      void reportEvidence('ui', 'started', { action }, ids)
      try {
        const response = await fetch('/api/onboarding', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            ...ids,
            expected_revision: journey.card.revision,
            surface: effectiveSurface.current,
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
        setFeedbackRecorded(null)
        if (action !== 'purge') {
          void reportEvidence('ui', 'succeeded', { action, rendered_stage: body.card.stage }, body.evidence || ids)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'That choice could not be completed.')
        if (action !== 'purge') {
          void reportEvidence('transport', 'failed', { action, error_code: 'action_request_failed' }, ids)
        }
      } finally {
        setWorking(false)
      }
    },
    [journey, load, reportEvidence]
  )

  async function recordFeedback(status: 'useful' | 'not_useful' | 'corrected', category: string) {
    const ids = {
      action_id: newActionId('feedback'),
      trace_id: newActionId('trace'),
      correlation_id: journey?.evidence?.correlation_id || newActionId('corr'),
    }
    const recorded = await reportEvidence('feedback', status, {
      feedback_rating: status,
      feedback_category: category,
      rendered_stage: journey?.card.stage,
    }, ids)
    if (recorded) {
      setFeedbackRecorded(status)
    } else {
      setError('Your feedback could not be preserved yet. Please try again.')
    }
  }

  function submitScope(event: FormEvent) {
    event.preventDefault()
    void send('propose_window', {
      source,
      purpose,
      relationship_destination: destination,
      ownership: ownership || undefined,
      authority_basis: authorityBasis,
    })
  }

  function submitSeed(event: FormEvent) {
    event.preventDefault()
    void send('answer_seed', { seed })
  }

  function submitIdentity(event: FormEvent) {
    event.preventDefault()
    const picked = Object.entries(handles)
      .filter(([, identifier]) => identifier.trim())
      .map(([connector, identifier]) => [connector, [identifier.trim()]] as const)
    if (picked.length === 0) return
    void send('record_operator_identity', { handles: Object.fromEntries(picked) })
  }

  // One account, offered as a tap. The picked value lives in the same `handles`
  // entry a typed answer writes to, so tapping and typing are one field: type
  // over a pick and the radio releases, tap and the text follows. Two states
  // would let a surface submit a stale spelling the operator had corrected.
  function identityChoice(
    ask: OnboardingIdentityAsk,
    candidate: { identifier: string; rows: number }
  ) {
    return (
      <label
        key={candidate.identifier}
        className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-current/20 px-3 py-2"
      >
        <input
          type="radio"
          name={`${surface}-identity-${ask.connector}`}
          value={candidate.identifier}
          checked={handles[ask.connector] === candidate.identifier}
          onChange={() =>
            setHandles((current) => ({ ...current, [ask.connector]: candidate.identifier }))
          }
        />
        <span>
          {candidate.identifier}
          <span className={`block text-xs ${muted}`}>{candidate.rows} of {ask.rows} here</span>
        </span>
      </label>
    )
  }

  function choose(action: OnboardingAction) {
    if (action === 'answer_seed') {
      // Focus the field rather than firing an empty action: this option exists
      // to point at the input, and sending it bare would only earn a refusal.
      seedFieldRef.current?.focus()
      return
    }
    if (action === 'propose_window') {
      if (journey?.state.source?.root) setSource(journey.state.source.root)
      if (journey?.state.purpose) setPurpose(journey.state.purpose)
      if (journey?.state.relationship_destination) {
        setDestination(journey.state.relationship_destination)
      }
      if (journey?.state.source?.ownership) setOwnership(journey.state.source.ownership)
      if (journey?.state.source?.authority_basis) {
        setAuthorityBasis(journey.state.source.authority_basis)
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

  const showForm = journey?.card.stage === 'welcome' || editScope
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

          {journey.card.entry?.seed_question && (
            <form
              className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70 bg-amber-50/40' : 'border-zinc-700 bg-zinc-950'}`}
              onSubmit={submitSeed}
            >
              <label htmlFor={`${surface}-seed`} className="block text-sm font-semibold">
                {journey.card.entry.seed_question}
              </label>
              <p className={`mt-1 text-xs ${muted}`}>
                A sentence is enough. I take it as a starting point and go looking — not as the answer.
              </p>
              <textarea
                id={`${surface}-seed`}
                ref={seedFieldRef}
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                rows={2}
                maxLength={500}
                className={`mt-2 w-full rounded-md border px-3 py-2 text-sm outline-none ${input}`}
              />
              <button
                type="submit"
                disabled={working || !seed.trim()}
                className={`mt-2 min-h-11 rounded-md border px-3 py-2 text-sm font-medium disabled:opacity-50 ${variant === 'world' ? 'border-stone-600 bg-amber-100' : 'border-zinc-600 bg-zinc-800'}`}
              >
                Go and look
              </button>
            </form>
          )}

          {journey.card.entry?.identity_question && (
            <form
              className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70 bg-amber-50/40' : 'border-zinc-700 bg-zinc-950'}`}
              onSubmit={submitIdentity}
            >
              <h3 className="text-sm font-semibold">{journey.card.entry.identity_question.question}</h3>
              {journey.card.entry.identity_question.connectors.map((ask) => (
                <fieldset key={ask.connector} className="mt-3">
                  <legend className="text-sm font-medium">{ask.connector}</legend>
                  {ask.reports_no_actor ? (
                    <p className={`mt-1 text-xs ${muted}`}>{ask.note}</p>
                  ) : (
                    <>
                      <div className="mt-2 space-y-1 text-sm">
                        {ask.candidates.slice(0, IDENTITY_SHOWN).map((candidate) =>
                          identityChoice(ask, candidate)
                        )}
                      </div>
                      {/* THE REST OF THE ESTATE, ONE TAP AWAY AND STILL A TAP.
                          The busiest few lead because the operator usually is
                          one of them, but "usually" is not a gate a person can
                          be locked out by: on the measured estate the operator's
                          own account was 25th of 30 on the connector carrying
                          most of it. <details> rather than React state — the
                          rest must be reachable with scripting off. */}
                      {ask.candidates.length > IDENTITY_SHOWN && (
                        <details className="mt-1">
                          <summary className={`min-h-11 cursor-pointer py-2 text-xs ${muted}`}>
                            Show the other {ask.candidates.length - IDENTITY_SHOWN} account
                            {ask.candidates.length - IDENTITY_SHOWN === 1 ? '' : 's'} in{' '}
                            {ask.connector}
                          </summary>
                          <div className="space-y-1 text-sm">
                            {ask.candidates.slice(IDENTITY_SHOWN).map((candidate) =>
                              identityChoice(ask, candidate)
                            )}
                          </div>
                        </details>
                      )}
                      {/* Only where the core says the offer CANNOT be completed.
                          Where it is complete, "none of these is you" is a true
                          terminal state and a typed field could only add a
                          spelling the estate does not use — which resolves the
                          operator and then matches nothing. */}
                      {!ask.complete && (
                        <label className="mt-2 block text-xs">
                          <span className={muted}>
                            {ask.withheld} more account{ask.withheld === 1 ? '' : 's'} in{' '}
                            {ask.connector} than I can list. If yours is one of them, type it
                            exactly as {ask.connector} spells it.
                          </span>
                          <input
                            type="text"
                            name={`${surface}-identity-typed-${ask.connector}`}
                            value={handles[ask.connector] ?? ''}
                            onChange={(event) =>
                              setHandles((current) => ({ ...current, [ask.connector]: event.target.value }))
                            }
                            className={`mt-1 min-h-11 w-full rounded-md border px-3 py-2 text-sm ${variant === 'world' ? 'border-stone-500 bg-amber-50' : 'border-zinc-700 bg-zinc-900'}`}
                          />
                        </label>
                      )}
                    </>
                  )}
                </fieldset>
              ))}
              <p className={`mt-2 text-xs ${muted}`}>
                Leave a system blank if none of these is you. I will keep saying I cannot
                tell, rather than guessing at a name that looks close.
              </p>
              <button
                type="submit"
                disabled={working || Object.values(handles).every((value) => !value.trim())}
                className={`mt-2 min-h-11 rounded-md border px-3 py-2 text-sm font-medium disabled:opacity-50 ${variant === 'world' ? 'border-stone-600 bg-amber-100' : 'border-zinc-600 bg-zinc-800'}`}
              >
                That one is me
              </button>
            </form>
          )}

          {journey.card.entry?.discovery?.executed && (
            <div className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70 bg-amber-50/40' : 'border-zinc-700 bg-zinc-950'}`}>
              <h3 className="text-sm font-semibold">What I went and looked for</h3>
              <ul className="mt-2 space-y-1 text-sm">
                {journey.card.entry.discovery.executed.executed.map((probe) => (
                  <li key={`ran-${probe.kind}-${probe.pattern ?? ''}`}>
                    <code>{probe.pattern ?? probe.kind}</code>
                    <span className={`block ${muted}`}>
                      {probe.matches.length > 0 ? probe.matches.join(', ') : 'nothing matched by name'}
                      {/* A search that stopped at its limit read PART of the
                          folder, so the line above is about what it reached —
                          never about the folder. Silent here, "nothing matched"
                          is a negative this surface never earned. */}
                      {probe.truncated && ' — stopped at my limit before the end of the folder'}
                    </span>
                  </li>
                ))}
                {journey.card.entry.discovery.executed.deferred.map((probe, index) => (
                  <li key={`skipped-${probe.kind}-${index}`}>
                    <code>{probe.kind}</code>
                    <span className={`block ${muted}`}>
                      did not run — {probe.reason.replaceAll('_', ' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {journey.card.entry && journey.card.entry.questions.length > 0 && (
            <div className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70 bg-amber-50/40' : 'border-zinc-700 bg-zinc-950'}`}>
              <h3 className="text-sm font-semibold">
                What I cannot work out for myself
              </h3>
              <ul className="mt-2 space-y-2 text-sm">
                {journey.card.entry.questions.map((question) => (
                  <li key={question.id}>
                    {question.prompt}
                    <span className={`block ${muted}`}>{question.why}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

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

          {journey.card.stage === 'dividend_ready' && (
            <fieldset className={`mt-4 rounded-lg border p-3 ${variant === 'world' ? 'border-stone-500/70' : 'border-zinc-700'}`}>
              <legend className="px-1 text-sm font-semibold">Did this earn its keep?</legend>
              {feedbackRecorded ? (
                <p role="status" className={`text-sm ${muted}`}>Feedback recorded: {feedbackRecorded.replace('_', ' ')}.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="min-h-11 rounded-md border border-current/30 px-3 py-2 text-sm" onClick={() => void recordFeedback('useful', 'useful_as_shown')}>Yes, useful</button>
                  <button type="button" className="min-h-11 rounded-md border border-current/30 px-3 py-2 text-sm" onClick={() => void recordFeedback('not_useful', 'insufficient_value')}>Not useful yet</button>
                  <button type="button" className="min-h-11 rounded-md border border-current/30 px-3 py-2 text-sm" onClick={() => void recordFeedback('corrected', 'wrong_or_missing_context')}>Something is wrong</button>
                </div>
              )}
            </fieldset>
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
                <legend className="text-sm font-medium">Whose data is in this folder?</legend>
                <div className="mt-2 space-y-2 text-sm">
                  {([
                    ['self', 'Mine — my own machine, my own files'],
                    ['employer', "My employer's — I have a seat in it, I do not own it"],
                    ['third_party', "Someone else's — a client, a customer, a counterparty"],
                  ] as const).map(([value, label]) => (
                    <label key={value} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-current/20 px-3 py-2">
                      <input
                        type="radio"
                        name={`${surface}-ownership`}
                        value={value}
                        checked={ownership === value}
                        onChange={() => setOwnership(value)}
                        required
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                <p className={`mt-1 text-xs ${muted}`}>
                  Anything that is not yours is read-only and never written to. I cannot
                  check this answer — I can only refuse to start without one.
                </p>
              </fieldset>

              <div>
                <label htmlFor={`${surface}-authority-basis`} className="block text-sm font-medium">
                  Under what right?
                </label>
                <input
                  id={`${surface}-authority-basis`}
                  value={authorityBasis}
                  onChange={(event) => setAuthorityBasis(event.target.value)}
                  maxLength={300}
                  placeholder="my own laptop / read access granted to my seat / our engagement"
                  className={`mt-1 w-full rounded-md border px-3 py-2 text-sm outline-none ${input}`}
                  autoComplete="off"
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
                This removes the Charter, onboarding history, evidence trial, manifest, and derived excerpts. Explicitly exported review bundles are kept until you delete them.
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
