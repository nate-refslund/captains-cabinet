'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { WINDOW_RELATIONS } from '@/lib/onboarding/types'
import type {
  OnboardingAction,
  OnboardingIdentityAsk,
  OnboardingResponse,
  OnboardingSalienceOption,
  OnboardingSurface,
  OwnershipClass,
  WindowRelation,
} from '@/lib/onboarding/types'
import {
  activePhaseIndex,
  canAdvance,
  EMPTY_WIZARD,
  nextStep,
  prevStep,
  resumeStep,
  seedRequest,
  WIZARD_PHASES,
  type WizardStepId,
} from '@/lib/onboarding/wizard'

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

/** The merge picker's empty starting value — stable for the same reason. */
export const NO_MERGE: readonly string[] = Object.freeze([])

/**
 * What the operator has to state when the folder they proposed shares no word
 * with the target they answered. The core refuses that window rather than
 * retargeting it silently, and takes ONE of two statements; this is the shape
 * the card renders them from.
 */
interface RelationAsk {
  target: string
  window: string
  relations: WindowRelation[]
}

/**
 * Never through the prototype chain: the relations arrive from a refusal, and
 * `'constructor' in WINDOW_RELATIONS` is true.
 */
function isWindowRelation(value: string): value is WindowRelation {
  return Object.prototype.hasOwnProperty.call(WINDOW_RELATIONS, value)
}

/** The folder's own name — what the core's name test compares, and what it names back. */
function folderName(path: string): string {
  return path.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || path
}

// How many of a connector's accounts lead the picker before the rest go behind
// a disclosure. A LAYOUT number and nothing else — the core decides who is
// offered, and every account it offers is rendered on this card: the ones past
// this number sit behind a disclosure, never behind a second request.
export const IDENTITY_SHOWN = 8

/** The visual system, one object per surface so both skins read the same JSX. */
function themeOf(variant: 'dashboard' | 'world') {
  if (variant === 'world') {
    return {
      shell: 'w-[min(92vw,30rem)] rounded-lg border-4 border-amber-900 bg-[#f4dfaa] text-stone-900 shadow-[6px_6px_0_#3f2b1d]',
      eyebrow: 'text-amber-900',
      title: 'text-stone-900',
      muted: 'text-stone-700',
      faint: 'text-stone-600',
      panel: 'rounded-md border border-stone-500/70 bg-amber-50/50',
      input: 'border-stone-500 bg-[#fff4d2] text-stone-950 placeholder:text-stone-500 focus:border-stone-900',
      primary: 'bg-stone-900 text-amber-50 hover:bg-stone-800',
      secondary: 'border border-stone-600 bg-amber-100 text-stone-900 hover:bg-amber-200',
      ghost: 'text-stone-700 hover:bg-amber-100 hover:text-stone-900',
      danger: 'border border-red-800/70 text-red-800 hover:bg-red-100',
      choice: 'border-stone-500/60 bg-amber-50/60 hover:border-stone-500',
      choiceOn: 'border-stone-900 bg-amber-200/70 ring-1 ring-stone-900',
      badge: 'border-emerald-800/40 bg-emerald-100 text-emerald-900',
      railOn: 'border-stone-900 bg-stone-900 text-amber-50',
      railDone: 'border-emerald-800 bg-emerald-700 text-amber-50',
      railOff: 'border-stone-400 bg-transparent text-stone-500',
      railLine: 'bg-stone-400',
      railLineDone: 'bg-emerald-700',
    }
  }
  return {
    shell: 'w-full rounded-2xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900 to-zinc-950 text-zinc-100 shadow-2xl shadow-black/40',
    eyebrow: 'text-violet-300/90',
    title: 'text-zinc-50',
    muted: 'text-zinc-400',
    faint: 'text-zinc-500',
    panel: 'rounded-xl border border-zinc-800 bg-zinc-950/50',
    input: 'border-zinc-700 bg-zinc-950 text-zinc-50 placeholder:text-zinc-600 focus:border-violet-400 focus:ring-2 focus:ring-violet-500/25',
    primary: 'bg-violet-600 text-white hover:bg-violet-500 shadow-lg shadow-violet-950/40',
    secondary: 'border border-zinc-700 bg-zinc-800/70 text-zinc-100 hover:bg-zinc-800 hover:border-zinc-600',
    ghost: 'text-zinc-300 hover:bg-zinc-800/60 hover:text-white',
    danger: 'border border-red-500/50 text-red-300 hover:bg-red-950/40',
    choice: 'border-zinc-700 bg-zinc-900/40 hover:border-zinc-600',
    choiceOn: 'border-violet-500 bg-violet-500/10 ring-1 ring-violet-500/40',
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    railOn: 'border-violet-500 bg-violet-500/15 text-violet-200',
    railDone: 'border-emerald-500/60 bg-emerald-500/15 text-emerald-300',
    railOff: 'border-zinc-700 bg-transparent text-zinc-600',
    railLine: 'bg-zinc-800',
    railLineDone: 'bg-emerald-500/50',
  }
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
  // Non-welcome "Change it" / "Choose another folder" re-opens the window form.
  const [editScope, setEditScope] = useState(false)
  // The client-driven step of the welcome front — the three questions, then the
  // window or discover branch. The core owns the stages AFTER the front; this is
  // only where the operator is inside it.
  const [wizardStep, setWizardStep] = useState<WizardStepId>('role')
  // Question one: what the operator does. Becomes the journey seed.
  const [role, setRole] = useState('')
  // Question two: the dream. Becomes mission.purpose. Optional by design.
  const [dream, setDream] = useState('')
  // Question three: point me, or go find where I am useful.
  const [startPreference, setStartPreference] = useState<'' | 'point' | 'decide'>('')
  const [purgeArmed, setPurgeArmed] = useState(false)
  const [purgeConfirmation, setPurgeConfirmation] = useState('')
  const [source, setSource] = useState('~/Documents')
  // WHETHER THE OPERATOR HAS TOUCHED THE FOLDER FIELD. `source` alone cannot
  // answer that — its default is a real path someone might also type — and
  // without the answer the only sync into this field (re-opening the window form
  // over an existing proposal) overwrote whatever they had entered with the
  // last-proposed value.
  const [sourceEdited, setSourceEdited] = useState(false)
  // The per-window purpose the Charter names — distinct from the DREAM (question
  // two). Defaulted so the window step asks one fewer thing; the dream, when the
  // operator gave one, seeds it.
  const [purpose, setPurpose] = useState('Find one useful thing I may be missing.')
  const [destination, setDestination] = useState<'earn' | 'reversible' | 'sovereign'>('reversible')
  // No initial value, deliberately: an unclassified source is REFUSED by the
  // core, so pre-selecting "mine" here would answer the operator's question for
  // them and defeat the whole gate.
  const [ownership, setOwnership] = useState<OwnershipClass | ''>('')
  const [authorityBasis, setAuthorityBasis] = useState('')
  const [feedbackRecorded, setFeedbackRecorded] = useState<string | null>(null)
  // Which account is the operator, per connector. Empty until they pick.
  const [handles, setHandles] = useState<Readonly<Record<string, string>>>(NO_IDENTITY_PICKS)
  // Which of the ranked candidates to open first. Empty until they pick.
  const [salienceChoice, setSalienceChoice] = useState('')
  // The escape hatch's typed name.
  const [salienceName, setSalienceName] = useState('')
  // The merge the operator can see and no matcher can derive.
  const [salienceMerge, setSalienceMerge] = useState<readonly string[]>(NO_MERGE)
  // Set only by an off-target refusal.
  const [relationAsk, setRelationAsk] = useState<RelationAsk | null>(null)
  const effectiveSurface = useRef<Extract<OnboardingSurface, 'dashboard' | 'world' | 'companion'>>(surface)
  const handoffIds = useRef<{ trace_id?: string; correlation_id?: string }>({})
  const salienceFormRef = useRef<HTMLFormElement | null>(null)
  const identityFormRef = useRef<HTMLFormElement | null>(null)

  const t = themeOf(variant)

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
      // RESUME WHERE THE ANSWERS LEFT OFF. A reload mid-flow should land on the
      // branch step with the questions behind it, not back at question one — and
      // the fields re-fill from what the core already holds, so Back shows the
      // operator their own words rather than a blank.
      if (body.card.stage === 'welcome' && body.state.seed) {
        setRole(body.state.seed.text)
        setDream(body.state.mission?.purpose ?? '')
        setStartPreference(body.state.start_preference ?? '')
        setWizardStep(resumeStep(true, body.state.start_preference))
      }
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
    async (action: OnboardingAction, extra: Record<string, unknown> = {}): Promise<boolean> => {
      if (!journey) return false
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
          // THE ONE REFUSAL THAT CARRIES ITS OWN WAY OUT. The operator pointed
          // depth at one thing and proposed a window somewhere else; the core
          // will not retarget their answer silently, so it asks which of two
          // statements is true.
          if (body.code === 'salience_window_off_target') {
            const detail = body.detail || {}
            const proposed = typeof extra.source === 'string' ? extra.source : ''
            const offered = detail.relations?.length
              ? detail.relations
              : Object.keys(WINDOW_RELATIONS)
            setRelationAsk({
              target: detail.target || journey.state.salience?.target || '',
              window: detail.window || folderName(proposed),
              relations: offered.filter(isWindowRelation),
            })
          }
          throw new Error(body.error || 'That choice could not be completed.')
        }
        setJourney(body)
        setRelationAsk(null)
        setEditScope(false)
        setPurgeArmed(false)
        setPurgeConfirmation('')
        setFeedbackRecorded(null)
        // The field is only "theirs" until it has been committed or discarded.
        if (action === 'propose_window') setSourceEdited(false)
        if (action === 'purge' || action === 'start_again') {
          setSourceEdited(false)
          setSource('~/Documents')
          setWizardStep('role')
          setRole('')
          setDream('')
          setStartPreference('')
        }
        if (action !== 'purge') {
          void reportEvidence('ui', 'succeeded', { action, rendered_stage: body.card.stage }, body.evidence || ids)
        }
        return true
      } catch (err) {
        setError(err instanceof Error ? err.message : 'That choice could not be completed.')
        if (action !== 'purge') {
          void reportEvidence('transport', 'failed', { action, error_code: 'action_request_failed' }, ids)
        }
        return false
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

  const wizardValues = { role, dream, startPreference }

  // Question three, both answers, sent as ONE action so role, dream and the
  // preference all land before the window opens. On success the front hands off
  // to the branch the operator chose.
  async function commitAnswers() {
    const payload = seedRequest(wizardValues)
    if (!payload) return
    const ok = await send('answer_seed', payload)
    if (ok) setWizardStep(startPreference === 'decide' ? 'discover' : 'window')
  }

  function advance() {
    if (wizardStep === 'start') {
      void commitAnswers()
      return
    }
    const next = nextStep(wizardStep, wizardValues)
    if (next) setWizardStep(next)
  }

  function retreat() {
    const prev = prevStep(wizardStep)
    if (prev) {
      setEditScope(false)
      setWizardStep(prev)
    }
  }

  const salienceOption = journey?.card.options.find(
    (option) => option.action === 'answer_salience'
  )
  const salienceOptions: OnboardingSalienceOption[] = salienceOption?.options ?? []
  const salienceAsksName =
    salienceOptions.find((option) => option.id === salienceChoice)?.input === 'seed'

  function windowPayload(): Record<string, unknown> {
    return {
      source,
      purpose,
      relationship_destination: destination,
      ownership: ownership || undefined,
      authority_basis: authorityBasis,
    }
  }

  function submitScope(event: FormEvent) {
    event.preventDefault()
    void send('propose_window', windowPayload())
  }

  function submitRelation(relation: WindowRelation) {
    void send('propose_window', { ...windowPayload(), salience_relation: relation })
  }

  function submitSalience(event: FormEvent) {
    event.preventDefault()
    if (!salienceChoice) return
    const picked = salienceOptions.find((option) => option.id === salienceChoice)
    const extra: Record<string, unknown> = { choice: salienceChoice }
    if (picked?.input === 'seed') extra.name = salienceName.trim()
    if (salienceMerge.length > 0) extra.same_as = [...salienceMerge]
    void send('answer_salience', extra)
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
  // entry a typed answer writes to, so tapping and typing are one field.
  function identityChoice(
    ask: OnboardingIdentityAsk,
    candidate: { identifier: string; rows: number }
  ) {
    const on = handles[ask.connector] === candidate.identifier
    return (
      <label
        key={candidate.identifier}
        className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors motion-reduce:transition-none ${on ? t.choiceOn : t.choice}`}
      >
        <input
          type="radio"
          name={`${surface}-identity-${ask.connector}`}
          value={candidate.identifier}
          checked={on}
          onChange={() =>
            setHandles((current) => ({ ...current, [ask.connector]: candidate.identifier }))
          }
        />
        <span>
          {candidate.identifier}
          <span className={`block text-xs ${t.faint}`}>{candidate.rows} of {ask.rows} here</span>
        </span>
      </label>
    )
  }

  function choose(action: OnboardingAction) {
    if (action === 'answer_salience' && salienceOptions.length > 0) {
      salienceFormRef.current?.scrollIntoView?.({ block: 'nearest' })
      salienceFormRef.current?.querySelector?.('input')?.focus()
      return
    }
    if (action === 'record_operator_identity' && journey?.card.entry?.identity_question) {
      identityFormRef.current?.scrollIntoView?.({ block: 'nearest' })
      identityFormRef.current?.querySelector?.('input')?.focus()
      return
    }
    if (action === 'propose_window') {
      // PRE-FILL, NEVER OVERWRITE. Re-opening the window form syncs it from the
      // last proposal so "Change it" starts from what is already approved — but
      // only while the field is PRISTINE.
      if (!sourceEdited && journey?.state.source?.root) setSource(journey.state.source.root)
      if (journey?.state.purpose) setPurpose(journey.state.purpose)
      if (journey?.state.relationship_destination) {
        setDestination(journey.state.relationship_destination)
      }
      if (journey?.state.source?.ownership) setOwnership(journey.state.source.ownership)
      if (journey?.state.source?.authority_basis) {
        setAuthorityBasis(journey.state.source.authority_basis)
      }
      setEditScope(true)
      setWizardStep('window')
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

  const stage = journey?.card.stage ?? ''
  const inFrontQuestions =
    stage === 'welcome' && !editScope &&
    (wizardStep === 'role' || wizardStep === 'dream' || wizardStep === 'start')
  const showWindowForm =
    editScope || (stage === 'welcome' && !editScope && wizardStep === 'window')
  const inDiscover = stage === 'welcome' && !editScope && wizardStep === 'discover'
  // The sweep results (rank, identity, discovery, evidence) surface once the
  // front is behind us: in the discover branch, and in every server stage.
  const showSweep = !inFrontQuestions && !showWindowForm && !purgeArmed
  const gatherOption = journey?.card.options.find((o) => o.action === 'gather_connectors')
  // The honest discover panel shows when the decide branch has NOTHING to
  // explore yet — no ranking, no identity to settle. The moment a connected
  // source produces either, the sweep sections below speak instead, and this
  // steps aside rather than talking over a real result.
  const hasSweepContent =
    salienceOptions.length > 0 || Boolean(journey?.card.entry?.identity_question)
  const showDiscoverPanel = inDiscover && !hasSweepContent

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

  const activePhase = activePhaseIndex(stage, wizardStep)

  return (
    <section
      className={`p-6 sm:p-7 ${t.shell}`}
      aria-labelledby={journey ? 'onboarding-card-title' : undefined}
      aria-label={journey ? undefined : 'Cabinet orientation'}
    >
      {loading ? (
        <p role="status" className={t.muted}>Opening your Cabinet orientation…</p>
      ) : journey ? (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className={`text-[0.7rem] font-semibold uppercase tracking-[0.2em] ${t.eyebrow}`}>
                First Window
              </p>
              <h2 id="onboarding-card-title" className={`mt-1.5 text-2xl font-semibold tracking-tight ${t.title}`}>
                {journey.card.title}
              </h2>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.7rem] font-medium ${t.badge}`}>
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
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

          {activePhase >= 0 && (
            <ol
              className="mt-5 flex items-center gap-1.5"
              aria-label={`Onboarding progress: step ${activePhase + 1} of ${WIZARD_PHASES.length}`}
              role="list"
            >
              {WIZARD_PHASES.map((phase, index) => {
                const done = index < activePhase
                const current = index === activePhase
                return (
                  <li key={phase.id} className="flex flex-1 flex-col items-center gap-1.5" aria-current={current ? 'step' : undefined}>
                    <div className="flex w-full items-center gap-1.5">
                      <span
                        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-xs font-semibold transition-colors motion-reduce:transition-none ${current ? t.railOn : done ? t.railDone : t.railOff}`}
                      >
                        {done ? '✓' : index + 1}
                      </span>
                      {index < WIZARD_PHASES.length - 1 && (
                        <span className={`h-px flex-1 ${index < activePhase ? t.railLineDone : t.railLine}`} />
                      )}
                    </div>
                    <span className={`hidden text-center text-[0.65rem] font-medium sm:block ${current ? t.eyebrow : t.faint}`}>
                      {phase.label}
                    </span>
                  </li>
                )
              })}
            </ol>
          )}

          {/* ------------------------------------------------------------------
              THE WELCOME FRONT — the three questions, one idea per step.
              The one seed question was three; here they are, plainly, before any
              folder is named or any byte is read.
          ------------------------------------------------------------------- */}
          {inFrontQuestions && wizardStep === 'role' && (
            <div className="mt-6">
              <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${t.title}`}>
                Tell me about you and your work.
              </h3>
              <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
                What do you do? A sentence in your own words — a shopkeeper, a team lead,
                a researcher. I take it as where to start looking, never as the answer.
              </p>
              <label htmlFor={`${surface}-role`} className="sr-only">What do you do?</label>
              <textarea
                id={`${surface}-role`}
                value={role}
                onChange={(event) => setRole(event.target.value)}
                rows={3}
                maxLength={500}
                autoFocus
                placeholder="I run a small ryokan on the coast…"
                className={`mt-4 w-full rounded-xl border px-4 py-3 text-base leading-6 outline-none transition-colors motion-reduce:transition-none ${t.input}`}
              />
            </div>
          )}

          {inFrontQuestions && wizardStep === 'dream' && (
            <div className="mt-6">
              <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${t.title}`}>
                What would you love this Cabinet to become?
              </h3>
              <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
                Think bigger than today. This is the one thing no amount of reading can
                tell me — it is a choice, and it is yours. You can skip it and add it later.
              </p>
              <label htmlFor={`${surface}-dream`} className="sr-only">Your dream for the Cabinet</label>
              <textarea
                id={`${surface}-dream`}
                value={dream}
                onChange={(event) => setDream(event.target.value)}
                rows={3}
                maxLength={300}
                autoFocus
                placeholder="A calmer front desk, and guests who leave feeling looked after…"
                className={`mt-4 w-full rounded-xl border px-4 py-3 text-base leading-6 outline-none transition-colors motion-reduce:transition-none ${t.input}`}
              />
            </div>
          )}

          {inFrontQuestions && wizardStep === 'start' && (
            <div className="mt-6">
              <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${t.title}`}>
                Where should I begin?
              </h3>
              <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
                You can point me at one folder to read, or ask me to go and find where I
                am most useful. Either way, nothing is read until you approve a Charter.
              </p>
              <div className="mt-4 grid gap-3">
                {([
                  ['point', 'Point me somewhere', 'I name one folder, and you read it under a Charter I approve.'],
                  ['decide', 'Go find where you are most useful', 'You look across what I have connected and propose where to start.'],
                ] as const).map(([value, label, detail]) => {
                  const on = startPreference === value
                  return (
                    <label
                      key={value}
                      className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors motion-reduce:transition-none ${on ? t.choiceOn : t.choice}`}
                    >
                      <input
                        type="radio"
                        name={`${surface}-start-preference`}
                        value={value}
                        checked={on}
                        onChange={() => setStartPreference(value)}
                        className="mt-1"
                      />
                      <span>
                        <span className={`block font-medium ${t.title}`}>{label}</span>
                        <span className={`mt-0.5 block text-sm ${t.muted}`}>{detail}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          {inFrontQuestions && (
            <div className="mt-6 flex items-center justify-between gap-3">
              {prevStep(wizardStep) ? (
                <button
                  type="button"
                  onClick={retreat}
                  disabled={working}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${t.ghost}`}
                >
                  Back
                </button>
              ) : <span />}
              <button
                type="button"
                onClick={advance}
                disabled={working || !canAdvance(wizardStep, wizardValues)}
                className={`min-h-11 rounded-xl px-5 py-2 text-sm font-semibold disabled:opacity-50 disabled:shadow-none ${t.primary}`}
              >
                {wizardStep === 'start' ? (working ? 'Setting up…' : 'Continue') : 'Next'}
              </button>
            </div>
          )}

          {/* ------------------------------------------------------------------
              THE DISCOVER BRANCH — honest self-exploration. It needs a source it
              can read. Where one is connected, that read is the real move; where
              none is, this says so plainly and routes to the folder that always
              works, rather than pretending to go looking at nothing.
          ------------------------------------------------------------------- */}
          {showDiscoverPanel && (
            <div className={`mt-6 p-4 ${t.panel}`}>
              <h3 className={`text-lg font-semibold ${t.title}`}>Let me go and find where I fit</h3>
              <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
                To find where I am most useful, I need something to read. Connect a tool and
                I will look across it read-only and propose where to start — or point me at a
                single folder now, which works today with nothing connected.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {gatherOption && (
                  <button
                    type="button"
                    onClick={() => choose('gather_connectors')}
                    disabled={working}
                    className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${t.primary}`}
                  >
                    {gatherOption.label}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setWizardStep('window')}
                  disabled={working}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${gatherOption ? t.secondary : t.primary}`}
                >
                  Point me at a folder instead
                </button>
              </div>
              <p className={`mt-3 text-xs ${t.faint}`}>
                You connect tools in Integrations. I never write to anything I read.
              </p>
              <button
                type="button"
                onClick={retreat}
                disabled={working}
                className={`mt-4 min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-50 ${t.ghost}`}
              >
                Back
              </button>
            </div>
          )}

          {/* The server's own sentence, on every stage past the front. The front
              speaks for itself above; a charter, a dividend or a paused card
              speaks here. */}
          {!inFrontQuestions && !inDiscover && !showWindowForm && (
            <p className={`mt-5 break-words text-sm leading-6 ${t.muted}`}>{journey.card.body}</p>
          )}

          {journey.card.entry?.identity_question && showSweep && (
            <form
              ref={identityFormRef}
              className={`mt-5 p-4 ${t.panel}`}
              onSubmit={submitIdentity}
            >
              <h3 className={`text-sm font-semibold ${t.title}`}>{journey.card.entry.identity_question.question}</h3>
              {journey.card.entry.identity_question.connectors.map((ask) => (
                <fieldset key={ask.connector} className="mt-3">
                  <legend className="text-sm font-medium">{ask.connector}</legend>
                  {ask.reports_no_actor ? (
                    <p className={`mt-1 text-xs ${t.faint}`}>{ask.note}</p>
                  ) : (
                    <>
                      <div className="mt-2 space-y-1.5 text-sm">
                        {ask.candidates.slice(0, IDENTITY_SHOWN).map((candidate) =>
                          identityChoice(ask, candidate)
                        )}
                      </div>
                      {ask.candidates.length > IDENTITY_SHOWN && (
                        <details className="mt-1">
                          <summary className={`min-h-11 cursor-pointer py-2 text-xs ${t.faint}`}>
                            Show the other {ask.candidates.length - IDENTITY_SHOWN} account
                            {ask.candidates.length - IDENTITY_SHOWN === 1 ? '' : 's'} in{' '}
                            {ask.connector}
                          </summary>
                          <div className="space-y-1.5 text-sm">
                            {ask.candidates.slice(IDENTITY_SHOWN).map((candidate) =>
                              identityChoice(ask, candidate)
                            )}
                          </div>
                        </details>
                      )}
                      {!ask.complete && (
                        <label className="mt-2 block text-xs">
                          <span className={t.faint}>
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
                            className={`mt-1 min-h-11 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                          />
                        </label>
                      )}
                    </>
                  )}
                </fieldset>
              ))}
              <p className={`mt-2 text-xs ${t.faint}`}>
                Leave a system blank if none of these is you. I will keep saying I cannot
                tell, rather than guessing at a name that looks close.
              </p>
              <button
                type="submit"
                disabled={working || Object.values(handles).every((value) => !value.trim())}
                className={`mt-3 min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${t.secondary}`}
              >
                That one is me
              </button>
            </form>
          )}

          {salienceOptions.length > 0 && showSweep && (
            <form
              ref={salienceFormRef}
              className={`mt-5 p-4 ${t.panel}`}
              onSubmit={submitSalience}
            >
              <h3 className={`text-sm font-semibold ${t.title}`}>{salienceOption?.label}</h3>
              <div className="mt-2 space-y-1.5 text-sm">
                {salienceOptions.map((option) => {
                  const on = salienceChoice === option.id
                  return (
                    <label
                      key={option.id}
                      className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border px-3 py-2 transition-colors motion-reduce:transition-none ${on ? t.choiceOn : t.choice}`}
                    >
                      <input
                        type="radio"
                        name={`${surface}-salience`}
                        value={option.id}
                        checked={on}
                        onChange={() => setSalienceChoice(option.id)}
                        className="mt-1"
                      />
                      <span>
                        {option.label}
                        <span className={`block text-xs ${t.faint}`}>{option.why}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
              {salienceAsksName && (
                <label className="mt-2 block text-xs">
                  <span className={t.faint}>What should I open instead? A word or two.</span>
                  <input
                    type="text"
                    name={`${surface}-salience-name`}
                    value={salienceName}
                    onChange={(event) => setSalienceName(event.target.value)}
                    autoComplete="off"
                    className={`mt-1 min-h-11 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                  />
                </label>
              )}
              {salienceOption?.merge?.candidates && salienceOption.merge.candidates.length > 1 && (
                <details className="mt-3">
                  <summary className={`min-h-11 cursor-pointer py-2 text-xs ${t.faint}`}>
                    Are two of these the same thing under different names?
                  </summary>
                  <p className={`text-xs ${t.faint}`}>{salienceOption.merge.question}</p>
                  <div className="mt-1 space-y-1.5 text-sm">
                    {salienceOption.merge.candidates.map((candidate) => (
                      <label
                        key={candidate.id}
                        className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${salienceMerge.includes(candidate.id) ? t.choiceOn : t.choice}`}
                      >
                        <input
                          type="checkbox"
                          name={`${surface}-salience-merge`}
                          value={candidate.id}
                          checked={salienceMerge.includes(candidate.id)}
                          onChange={() =>
                            setSalienceMerge((current) =>
                              current.includes(candidate.id)
                                ? current.filter((id) => id !== candidate.id)
                                : [...current, candidate.id]
                            )
                          }
                        />
                        <span>{candidate.label}</span>
                      </label>
                    ))}
                  </div>
                  {salienceOption.merge.learned?.length > 0 && (
                    <p className={`mt-2 text-xs ${t.faint}`}>
                      Already one thing: {salienceOption.merge.learned
                        .map((group) => group.labels.join(' = '))
                        .join('; ')}
                    </p>
                  )}
                </details>
              )}
              {salienceOption?.not_reached && (
                <p className={`mt-2 text-xs ${t.faint}`}>{salienceOption.not_reached}</p>
              )}
              <button
                type="submit"
                disabled={working || !salienceChoice || (salienceAsksName && !salienceName.trim())}
                className={`mt-3 min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${t.secondary}`}
              >
                Go deep on that one
              </button>
            </form>
          )}

          {journey.card.entry?.discovery?.executed && showSweep && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>What I went and looked for</h3>
              <ul className="mt-2 space-y-1.5 text-sm">
                {journey.card.entry.discovery.executed.executed.map((probe) => (
                  <li key={`ran-${probe.kind}-${probe.pattern ?? ''}`}>
                    <code className="font-mono text-[0.8rem]">{probe.pattern ?? probe.kind}</code>
                    <span className={`block ${t.faint}`}>
                      {probe.matches.length > 0 ? probe.matches.join(', ') : 'nothing matched by name'}
                      {probe.truncated && ' — stopped at my limit before the end of the folder'}
                    </span>
                  </li>
                ))}
                {journey.card.entry.discovery.executed.deferred.map((probe, index) => (
                  <li key={`skipped-${probe.kind}-${index}`}>
                    <code className="font-mono text-[0.8rem]">{probe.kind}</code>
                    <span className={`block ${t.faint}`}>
                      did not run — {probe.reason.replaceAll('_', ' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {journey.card.entry && journey.card.entry.questions.length > 0 && showSweep && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>What I cannot work out for myself</h3>
              <ul className="mt-2 space-y-2 text-sm">
                {journey.card.entry.questions.map((question) => (
                  <li key={question.id}>
                    {question.prompt}
                    <span className={`block ${t.faint}`}>{question.why}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {journey.card.evidence.length > 0 && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>Receipt — where this came from</h3>
              <ul className="mt-2 space-y-2 text-sm">
                {journey.card.evidence.map((citation) => (
                  <li key={`${citation.path}:${citation.line}`}>
                    <code className="font-mono text-[0.8rem]">{citation.path}:{citation.line}</code>
                    <span className={`block ${t.faint}`}>{citation.excerpt}</span>
                  </li>
                ))}
              </ul>
              {journey.card.egress && journey.card.egress.withheld > 0 && (
                <p className={`mt-2 text-xs ${t.faint}`}>
                  I am holding back the words of {journey.card.egress.withheld} of{' '}
                  {journey.card.egress.items} citation
                  {journey.card.egress.items === 1 ? '' : 's'}: this source is not yours to
                  send. The file and line are above so you can open them yourself, or
                  reclassify the source if I have it wrong.
                </p>
              )}
            </div>
          )}

          {journey.card.stage === 'dividend_ready' && (
            <fieldset className={`mt-5 p-4 ${t.panel}`}>
              <legend className={`px-1 text-sm font-semibold ${t.title}`}>Did this earn its keep?</legend>
              {feedbackRecorded ? (
                <p role="status" className={`text-sm ${t.muted}`}>Feedback recorded: {feedbackRecorded.replace('_', ' ')}.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${t.secondary}`} onClick={() => void recordFeedback('useful', 'useful_as_shown')}>Yes, useful</button>
                  <button type="button" className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${t.secondary}`} onClick={() => void recordFeedback('not_useful', 'insufficient_value')}>Not useful yet</button>
                  <button type="button" className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium ${t.secondary}`} onClick={() => void recordFeedback('corrected', 'wrong_or_missing_context')}>Something is wrong</button>
                </div>
              )}
            </fieldset>
          )}

          {/* ------------------------------------------------------------------
              THE WINDOW FORM — the one folder, and the consent facts a sweep can
              never derive. The Charter honesty lives here: whose data, under what
              right, and the read-only promise. Reached as the point branch's step
              four, or from "Change it" on a later card.
          ------------------------------------------------------------------- */}
          {showWindowForm && (
            <form className="mt-6 space-y-5" onSubmit={submitScope}>
              {stage === 'welcome' && !editScope && (
                <div>
                  <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${t.title}`}>
                    Which folder may I read?
                  </h3>
                  <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
                    One specific folder. I will show you the Charter — exactly what I would
                    open — before I read a single file.
                  </p>
                </div>
              )}
              <div>
                <label htmlFor={`${surface}-source`} className={`block text-sm font-medium ${t.title}`}>
                  Folder to look through
                </label>
                <div className="mt-1.5 flex flex-col gap-2 sm:flex-row">
                  <input
                    id={`${surface}-source`}
                    value={source}
                    onChange={(event) => {
                      setSourceEdited(true)
                      setSource(event.target.value)
                    }}
                    className={`min-h-11 flex-1 rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                    autoComplete="off"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setSourceEdited(false)
                      setSource('~/Documents')
                    }}
                    className={`min-h-11 rounded-lg px-3 text-sm font-medium ${t.secondary}`}
                  >
                    Use my Documents
                  </button>
                </div>
                <p className={`mt-1.5 text-xs ${t.faint}`}>Choose one specific folder. The whole home folder is refused.</p>
              </div>

              <div>
                <label htmlFor={`${surface}-purpose`} className={`block text-sm font-medium ${t.title}`}>
                  What should I make easier first?
                </label>
                <textarea
                  id={`${surface}-purpose`}
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value)}
                  maxLength={300}
                  rows={2}
                  className={`mt-1.5 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                  required
                />
              </div>

              <fieldset>
                <legend className={`text-sm font-medium ${t.title}`}>Whose data is in this folder?</legend>
                <div className="mt-2 space-y-2 text-sm">
                  {([
                    ['self', 'Mine — my own machine, my own files'],
                    ['employer', "My employer's — I have a seat in it, I do not own it"],
                    ['third_party', "Someone else's — a client, a customer, a counterparty"],
                  ] as const).map(([value, label]) => (
                    <label key={value} className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${ownership === value ? t.choiceOn : t.choice}`}>
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
                <p className={`mt-1.5 text-xs ${t.faint}`}>
                  Anything that is not yours is read-only and never written to. I cannot
                  check this answer — I can only refuse to start without one.
                </p>
              </fieldset>

              <div>
                <label htmlFor={`${surface}-authority-basis`} className={`block text-sm font-medium ${t.title}`}>
                  Under what right?
                </label>
                <input
                  id={`${surface}-authority-basis`}
                  value={authorityBasis}
                  onChange={(event) => setAuthorityBasis(event.target.value)}
                  maxLength={300}
                  placeholder="my own laptop / read access granted to my seat / our engagement"
                  className={`mt-1.5 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                  autoComplete="off"
                  required
                />
              </div>

              <fieldset>
                <legend className={`text-sm font-medium ${t.title}`}>How should the Cabinet earn your trust?</legend>
                <div className="mt-2 space-y-2 text-sm">
                  {([
                    ['earn', 'Earn every responsibility'],
                    ['reversible', 'Be proactive where actions are reversible — recommended'],
                    ['sovereign', 'Aim for broad autonomy after it is earned'],
                  ] as const).map(([value, label]) => (
                    <label key={value} className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${destination === value ? t.choiceOn : t.choice}`}>
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
                <p className={`mt-1.5 text-xs ${t.faint}`}>This sets a destination only. It grants no authority.</p>
              </fieldset>

              <div className="flex items-center justify-between gap-3">
                {stage === 'welcome' && !editScope ? (
                  <button
                    type="button"
                    onClick={() => setWizardStep('start')}
                    disabled={working}
                    className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${t.ghost}`}
                  >
                    Back
                  </button>
                ) : <span />}
                <button
                  type="submit"
                  disabled={working}
                  className={`min-h-11 rounded-xl px-5 py-2 text-sm font-semibold disabled:opacity-50 disabled:shadow-none ${t.primary}`}
                >
                  {working ? 'Preparing the Charter…' : 'Show me the Charter first'}
                </button>
              </div>
            </form>
          )}

          {/* THE REFUSAL THAT CARRIES ITS OWN WAY OUT. */}
          {relationAsk && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>
                You pointed me at {relationAsk.target}, and “{relationAsk.window}” shares no
                word with it.
              </h3>
              <p className={`mt-1 text-xs ${t.faint}`}>
                I cannot know what is in a folder before I am allowed to open it, so this is
                yours to say. Whichever you choose is recorded and shown on the Charter.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {relationAsk.relations.map((relation) => (
                  <button
                    key={relation}
                    type="button"
                    name={`${surface}-relation-${relation}`}
                    disabled={working}
                    onClick={() => submitRelation(relation)}
                    className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-50 ${t.secondary}`}
                  >
                    {relation === 'same_thing'
                      ? `“${relationAsk.window}” IS ${relationAsk.target}, under another name`
                      : `That is somewhere else I want opened`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* The server card's own options — ratify, change, continue, pause,
              revoke, purge, start again — on the stages that carry them. The
              front and the window form own their own buttons above. */}
          {!inFrontQuestions && !inDiscover && !showWindowForm && !purgeArmed && journey.card.options.length > 0 && (
            <div className="mt-6 flex flex-wrap gap-2">
              {journey.card.options.map((option) => (
                <button
                  key={option.action}
                  type="button"
                  disabled={working}
                  onClick={() => choose(option.action)}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${
                    option.danger
                      ? t.danger
                      : option.action === 'ratify_charter'
                        ? t.primary
                        : t.secondary
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}

          {purgeArmed && (
            <form
              className={`mt-6 rounded-xl border p-4 ${variant === 'world' ? 'border-red-800/70 bg-red-50/40' : 'border-red-700/70 bg-red-950/30'}`}
              onSubmit={(event) => {
                event.preventDefault()
                void send('purge', { confirmation: purgeConfirmation })
              }}
            >
              <label htmlFor={`${surface}-purge-confirmation`} className={`block text-sm font-semibold ${t.title}`}>
                Type PURGE to permanently delete this onboarding record
              </label>
              <p className={`mt-1 text-xs ${t.faint}`}>
                Destroyed, permanently: the Charter, onboarding history, evidence trial,
                manifest, and derived excerpts. None of it comes back.
              </p>
              <p className={`mt-1 text-xs ${t.faint}`}>
                Kept on purpose: the content-free record that a read happened — whose data,
                under what claimed right — with the folder path removed and no content in it.
                Explicitly exported review bundles are kept until you delete them.
              </p>
              <p className={`mt-1 text-xs ${t.faint}`}>
                Afterwards: you can start a new orientation whenever you like. It begins from
                nothing, with a new evidence trail, and cannot see anything deleted here.
              </p>
              <input
                id={`${surface}-purge-confirmation`}
                value={purgeConfirmation}
                onChange={(event) => setPurgeConfirmation(event.target.value)}
                autoComplete="off"
                className={`mt-3 min-h-11 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={working || purgeConfirmation !== 'PURGE'}
                  className="min-h-11 rounded-xl border border-red-600 bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
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
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium ${t.secondary}`}
                >
                  Keep it
                </button>
              </div>
            </form>
          )}
        </>
      ) : (
        <div className="space-y-3">
          <p className={t.muted}>The Cabinet orientation could not be loaded.</p>
          <button
            type="button"
            onClick={() => { setError(null); setLoading(true); void load() }}
            className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium ${t.secondary}`}
          >
            Try again
          </button>
        </div>
      )}

      <div aria-live="polite" className="mt-4 min-h-5 text-sm">
        {working && <span className={t.muted}>The Cabinet is working on that…</span>}
        {error && <span className="font-medium text-red-500 dark:text-red-300">{error}</span>}
      </div>
    </section>
  )
}
