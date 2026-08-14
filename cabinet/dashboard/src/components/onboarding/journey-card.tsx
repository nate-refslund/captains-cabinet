'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { WINDOW_RELATIONS } from '@/lib/onboarding/types'
import type {
  ConnectorCatalog,
  ConnectorTemplateChoice,
  OnboardingAction,
  OnboardingIdentityAsk,
  OnboardingResponse,
  OnboardingSalienceOption,
  OnboardingSurface,
  OnboardingSweptConnector,
  OwnershipClass,
  WindowRelation,
} from '@/lib/onboarding/types'
import { getConnectorCatalog } from '@/actions/connectors'
import { saveConnectorCredential } from '@/actions/env'
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

/** The connect step's empty template-field answers — stable for the same reason. */
export const NO_FIELDS: Readonly<Record<string, string>> = Object.freeze({})

/**
 * How many tools the catalog shows before the operator has narrowed it. A
 * LAYOUT number: every tool in the pack is reachable by search or by shelf, and
 * the count above the grid says how many are being held back, so nothing is
 * hidden without saying so. A pack of three is unaffected; a pack of three
 * hundred does not become a scroll.
 */
export const CATALOG_SHOWN = 12

/**
 * Why a connector came back with nothing, in the operator's words.
 *
 * The sweep's own reason strings are diagnostic and stable (`credential_absent`,
 * `http_401`, `read_only_refused:<verdict>`) — good in a log, useless on a card.
 * This translates the ones an operator can ACT on and passes anything else
 * through readably rather than swallowing it: an unrecognised reason printed
 * plainly is still a fact, while a generic "something went wrong" is not.
 */
export function plainReason(reason: string): string {
  const code = String(reason || '').trim()
  if (!code) return 'it did not answer'
  if (code === 'credential_absent') return 'no key is stored for it yet'
  if (code === 'inventory_returned_no_items') return 'it answered, and there is nothing in it yet'
  if (code === 'http_401' || code === 'http_403') {
    return 'the key was refused — check you pasted the whole key, and that it has read access'
  }
  if (code === 'http_404') return 'that address answered “not found”'
  if (code === 'http_429') return 'it asked me to slow down — try again in a minute'
  if (code.startsWith('http_5')) return 'the other side had an error of its own'
  if (code.startsWith('http_')) return `it answered ${code.slice(5)}`
  if (code.startsWith('unreachable')) return 'I could not reach it'
  if (code.startsWith('egress_')) return 'outbound calls are switched off for this cabinet'
  if (code.startsWith('read_only_refused')) return 'that shape is not a read, so I did not run it'
  if (code.startsWith('name_path_missed')) return 'I read it, but found no names where I was told to look'
  if (code === 'response_not_json') return 'what came back was not a list I can read'
  if (code === 'response_too_large') return 'what came back was too big to read'
  return code.replaceAll('_', ' ')
}

/** The date half of a sweep stamp. ISO in, `2026-08-13` out, locale-free. */
function dayOf(stamp: string | null | undefined): string {
  const match = /^\d{4}-\d{2}-\d{2}/.exec(String(stamp ?? ''))
  return match ? match[0] : ''
}

/** What one connector's last sweep amounts to, in one sentence. */
export function sweepLine(row: OnboardingSweptConnector): string {
  if (!row.connected) return plainReason(String(row.reason ?? ''))
  const parts = [`read ${row.items} thing${row.items === 1 ? '' : 's'}`]
  const day = dayOf(row.latest)
  if (day) parts.push(`newest ${day}`)
  if (row.actors) parts.push(`${row.actors} account${row.actors === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

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
  // The connect step, on the discover branch. `null` means the catalog has
  // not loaded yet (it is fetched once, client-side); an empty one means no pack
  // ships, and the step falls back to the folder. These stay the LAST hooks so
  // adding them leaves every index above unchanged.
  const [connectorCatalog, setConnectorCatalog] = useState<ConnectorCatalog | null>(null)
  // Which tool the operator picked, the credential they pasted (kept only until
  // the connect completes, then cleared), and their answers to the template's
  // own fields. The credential's setter is what wipes it from memory after use.
  const [connectPick, setConnectPick] = useState('')
  const [connectCredential, setConnectCredential] = useState('')
  const [connectFields, setConnectFields] =
    useState<Readonly<Record<string, string>>>(NO_FIELDS)
  const [connectError, setConnectError] = useState<string | null>(null)
  // How the operator is narrowing a catalog that is meant to grow: free text
  // over the names, and one shelf at a time. Both are pure view state — nothing
  // here reaches the core, and clearing them restores the whole pack.
  const [connectSearch, setConnectSearch] = useState('')
  const [connectCategory, setConnectCategory] = useState('')
  // WHETHER THE OPERATOR HAS SAID "that is enough, go and look". Connecting is
  // deliberately not a one-shot: a cabinet reads across MANY tools, so the step
  // stays open — connect, see what each one reads, connect another — until they
  // ask for the look. Without this the first successful sweep replaced the step
  // with its own results and the second tool could never be added.
  const [exploring, setExploring] = useState(false)
  // WHICH act the visible refusal belongs to. There is one `error` line, and it
  // sits at the FOOT of a card that is several screens long — so a refusal of an
  // answer given near the top is a message the operator never sees, which reads
  // as the act doing nothing at all. This lets the reason render AT the control
  // that fired it, in addition to the shared line. Cleared at the start of every
  // send, so a stale refusal can never sit under a control that just succeeded.
  const [refusedAction, setRefusedAction] = useState<OnboardingAction | null>(null)
  // Whose work this is. Empty until they say — never pre-filled from a folder
  // name, a credential or a search result, because the core stores this as the
  // operator's own statement and a default would put words in their mouth.
  const [organization, setOrganization] = useState('')
  const effectiveSurface = useRef<Extract<OnboardingSurface, 'dashboard' | 'world' | 'companion'>>(surface)
  const handoffIds = useRef<{ trace_id?: string; correlation_id?: string }>({})
  const salienceFormRef = useRef<HTMLFormElement | null>(null)
  const identityFormRef = useRef<HTMLFormElement | null>(null)
  // Guards the connect flow's three server round-trips against a re-entrant
  // submit — the credential write must never fire twice for one click, whatever
  // the `working` flag does between the calls.
  const connectingRef = useRef(false)

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

  // The connect step's catalog, fetched once. It reads a shipped DATA file
  // (never a secret), so a failure is an empty catalog and the folder path, not
  // an error — the discover branch stays usable with no tools to offer.
  useEffect(() => {
    let cancelled = false
    void getConnectorCatalog()
      .then((catalog) => { if (!cancelled) setConnectorCatalog(catalog) })
      .catch(() => { if (!cancelled) setConnectorCatalog({ templates: [], categories: [] }) })
    return () => { cancelled = true }
  }, [])

  const send = useCallback(
    async (
      action: OnboardingAction,
      extra: Record<string, unknown> = {},
      // The revision to send AS. Defaults to the card in this render's closure —
      // but a handler that fires two actions back to back (declare then gather)
      // holds a STALE closure between them: the first bumps the revision and the
      // second would collide (revision_conflict) unless it is told the fresh one
      // the first returned. Measured live 2026-08-13: the connect flow declared,
      // then its gather was refused as a conflict, so the sweep never ran.
      expectedRevisionOverride?: number
    ): Promise<OnboardingResponse | null> => {
      if (!journey) return null
      setWorking(true)
      setError(null)
      setRefusedAction(null)
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
            expected_revision: expectedRevisionOverride ?? journey.card.revision,
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
        return body
      } catch (err) {
        setError(err instanceof Error ? err.message : 'That choice could not be completed.')
        setRefusedAction(action)
        if (action !== 'purge') {
          void reportEvidence('transport', 'failed', { action, error_code: 'action_request_failed' }, ids)
        }
        return null
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
  // WHAT THE CORE ALREADY HOLDS, read back at the control that sent it. The
  // ranked question keeps its candidates on the card after it is answered (the
  // operator may re-point at any time), so without this the form is
  // byte-identical before and after a successful answer — the radios, the typed
  // name and the button all unchanged. Read from committed state, never from the
  // local field, so it says what the CORE recorded rather than what was typed.
  const answeredTarget = journey?.state.salience?.target ?? ''

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

  function submitOrganization(event: FormEvent) {
    event.preventDefault()
    const said = organization.trim()
    if (!said) return
    void send('answer_organization', { organization: said })
  }

  function submitIdentity(event: FormEvent) {
    event.preventDefault()
    const picked = Object.entries(handles)
      .filter(([, identifier]) => identifier.trim())
      .map(([connector, identifier]) => [connector, [identifier.trim()]] as const)
    if (picked.length === 0) return
    void send('record_operator_identity', { handles: Object.fromEntries(picked) })
  }

  // ------------------------------------------------------------------ CONNECT
  // What the catalog holds, what is already connected, and what the operator can
  // see right now. Derived above the handlers because both read them.
  const templates = connectorCatalog?.templates ?? []
  const shelves = connectorCatalog?.categories ?? []
  // EVERY declared connector as the last sweep found it — the authority on what
  // exists, because it is read from the config rather than from what this
  // session happens to have done. `connector_declarations` adds the ones
  // declared since the last sweep, so a tool connected a second ago is not
  // offered again as if it were new.
  const swept: OnboardingSweptConnector[] = journey?.state.connector_sweep?.connectors ?? []
  const declaredNames = new Set<string>([
    ...swept.map((row) => row.name),
    ...(journey?.state.connector_declarations ?? []).map((row) => row.name),
  ])
  // The connected list, in the order they were connected, each with the state
  // the sweep gave it. A tool declared but not yet swept shows as pending rather
  // than as a failure — those are opposite facts.
  const connected = [...declaredNames].map((name) => {
    const row = swept.find((entry) => entry.name === name)
    return {
      name,
      row,
      label: templates.find((tpl) => tpl.id === name)?.label ?? name,
    }
  })
  const pickedTemplate = templates.find((tpl) => tpl.id === connectPick) ?? null
  const canConnect =
    pickedTemplate != null &&
    connectCredential.trim() !== '' &&
    pickedTemplate.fields.every((field) => !field.required || (connectFields[field.key] ?? '').trim() !== '')
  // Free text over everything an operator might type: the tool's name, what it
  // is for, the shelf it sits on, and the host — so "invoice", "billing" and
  // "stripe.com" all find the same card.
  const needle = connectSearch.trim().toLowerCase()
  const matches = templates.filter((tpl) => {
    if (connectCategory && tpl.category !== connectCategory) return false
    if (!needle) return true
    return [tpl.label, tpl.summary, tpl.category_label, tpl.host, tpl.id]
      .join(' ')
      .toLowerCase()
      .includes(needle)
  })
  // Narrowed lists are shown WHOLE — a search that hides its own tail is worse
  // than no search. Only the unnarrowed catalog is capped, and the count says so.
  const narrowed = needle !== '' || connectCategory !== ''
  const shown = narrowed ? matches : matches.slice(0, CATALOG_SHOWN)

  // CONNECT A TOOL, right here in onboarding — the write half of the read lane.
  // Three server steps, in order: the credential VALUE goes to cabinet/.env by
  // the safe writer (and ONLY there); the connector is declared with the env var
  // NAME (never the value); and the sweep runs, so the operator sees what that
  // tool actually reads before deciding whether to add another. The credential is
  // wiped from memory the instant the declaration lands.
  //
  // A TOOL ALREADY DECLARED IS A RETRY, NOT A SECOND TOOL. The commonest failure
  // on this step is a key pasted short or made with the wrong scope: the
  // connector exists, the sweep says the key was refused, and the fix is a new
  // key under the SAME name. Declaring again would be refused as a duplicate
  // name and read to the operator as "you cannot fix this", so the declare is
  // skipped and the credential is simply replaced.
  async function submitConnect(event: FormEvent) {
    event.preventDefault()
    const template = templates.find((tpl) => tpl.id === connectPick)
    if (!template || !connectCredential.trim() || connectingRef.current) return
    const missingRequired = template.fields.some(
      (field) => field.required && !(connectFields[field.key] ?? '').trim()
    )
    if (missingRequired) return
    connectingRef.current = true
    setConnectError(null)
    setWorking(true)
    try {
      const stored = await saveConnectorCredential(template.credential_env, connectCredential)
      if (!stored.success) {
        setConnectError(stored.error || 'That credential could not be stored, so nothing was connected.')
        return
      }
      let revision = journey?.card.revision
      if (!declaredNames.has(template.id)) {
        const answers: Record<string, string> = {}
        for (const field of template.fields) {
          const value = (connectFields[field.key] ?? '').trim()
          if (value) answers[field.key] = value
        }
        const declared = await send('declare_connector', {
          template: template.id,
          name: template.id,
          credential_env: template.credential_env,
          fields: answers,
        })
        if (!declared) return // send() put the refusal on the card
        revision = declared.card.revision
      }
      setConnectCredential('')
      setConnectPick('')
      setConnectFields(NO_FIELDS)
      setConnectSearch('')
      // Read with the revision the declaration just produced, not the stale one
      // in this closure — otherwise the sweep collides with the write above.
      // ONE sweep covers EVERY declared connector, so this both proves the tool
      // just connected and refreshes the state of the ones connected before it.
      await send('gather_connectors', {}, revision)
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : 'That tool could not be connected.')
    } finally {
      connectingRef.current = false
      setWorking(false)
    }
  }

  /** Re-open the setup sheet for one tool, with its old credential not reused. */
  function reconnect(templateId: string) {
    setConnectPick(templateId)
    setConnectCredential('')
    setConnectFields(NO_FIELDS)
    setConnectError(null)
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
  const gatherOption = journey?.card.options.find((o) => o.action === 'gather_connectors')
  // THE CONNECT STEP STAYS OPEN UNTIL THE OPERATOR CLOSES IT. It used to close
  // itself the moment a sweep produced anything to rank — which made connecting
  // a one-shot: the first tool's results replaced the step, and a second tool
  // could never be added. Now the step holds the catalog and the connected list
  // together, and only "go look" hands over to the results below.
  const showDiscoverPanel = inDiscover && !exploring
  // The sweep results (rank, identity, discovery, evidence) surface once the
  // front is behind us and the connect step has been left: in the discover
  // branch after the look, and in every server stage.
  const showSweep = !inFrontQuestions && !showWindowForm && !purgeArmed && !showDiscoverPanel

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
              {/* ONE VOICE. Every word on this card is the CABINET speaking to
                  the operator: "I" is the Cabinet, "you" is the person reading.
                  These two rows had flipped into the operator's voice — "I name
                  one folder, and you read it" — so three lines of the same
                  paragraph disagreed about who "I" was (Captain, 2026-08-13,
                  from a live run; the two descriptions are his wording). The
                  labels are held to the same rule: the branch above says "Point
                  me somewhere", so this one cannot say "where YOU are useful"
                  and mean the Cabinet. */}
              <div className="mt-4 grid gap-3">
                {([
                  ['point', 'Point me somewhere', 'You name one folder, and I read it under a Charter you approve.'],
                  ['decide', 'Go and find where I am most useful', 'I look across what you have connected and propose where to start.'],
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
                To find where I am most useful, I need something to read. Connect as many tools
                as you like below and I will read across all of them — only ever read — then
                tell you where to start. Or point me at a single folder now, which works with
                nothing connected.
              </p>

              {/* CONNECTED SO FAR — every tool the cabinet has been given, each
                  with what the last sweep actually got from it. One sweep covers
                  them all, so a key refused on one tool sits beside the counts
                  from the others instead of reading as a failed sweep. */}
              {connected.length > 0 && (
                <div className="mt-4">
                  <h4 className={`text-sm font-semibold ${t.title}`}>
                    Connected so far ({connected.length})
                  </h4>
                  <ul className="mt-2 space-y-1.5">
                    {connected.map(({ name, row, label }) => {
                      const ok = row?.connected === true
                      const pending = row === undefined
                      return (
                        <li
                          key={name}
                          className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 ${t.choice}`}
                        >
                          <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-emerald-500' : pending ? 'bg-amber-500' : 'bg-red-500'}`} />
                          <span className={`font-medium ${t.title}`}>{label}</span>
                          <span className={`text-sm ${ok || pending ? t.faint : variant === 'world' ? 'text-red-800' : 'text-red-300'}`}>
                            {pending ? 'not read yet' : sweepLine(row)}
                          </span>
                          {!ok && !pending && (
                            <button
                              type="button"
                              onClick={() => reconnect(name)}
                              disabled={working}
                              className={`ml-auto min-h-11 rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${t.secondary}`}
                            >
                              Try a different key
                            </button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}

              {/* THE CATALOG. Pick a tool, follow its own steps to make a key,
                  paste it, and the cabinet gains a source it reads read-only.
                  The credential goes only to cabinet/.env; the declaration
                  carries its NAME. The pack is DATA, so this list grows without
                  a line of code changing. */}
              {connectorCatalog === null ? (
                <p className={`mt-4 text-sm ${t.faint}`}>Finding the tools you can connect…</p>
              ) : templates.length > 0 && !pickedTemplate ? (
                <div className="mt-5">
                  <label
                    htmlFor={`${surface}-connect-search`}
                    className={`block text-sm font-medium ${t.title}`}
                  >
                    {connected.length > 0 ? 'Connect another tool' : 'Connect a tool'}
                  </label>
                  <input
                    id={`${surface}-connect-search`}
                    type="search"
                    value={connectSearch}
                    onChange={(e) => setConnectSearch(e.target.value)}
                    placeholder="Search by name, or by what it holds"
                    autoComplete="off"
                    className={`mt-1.5 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                  />

                  {shelves.length > 1 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label="Filter by kind of tool">
                      <button
                        type="button"
                        aria-pressed={connectCategory === ''}
                        onClick={() => setConnectCategory('')}
                        className={`min-h-11 rounded-full border px-3 py-1 text-xs font-medium ${connectCategory === '' ? t.railOn : t.choice}`}
                      >
                        Everything
                      </button>
                      {shelves.map((shelf) => (
                        <button
                          key={shelf.id}
                          type="button"
                          aria-pressed={connectCategory === shelf.id}
                          onClick={() => setConnectCategory(connectCategory === shelf.id ? '' : shelf.id)}
                          className={`min-h-11 rounded-full border px-3 py-1 text-xs font-medium ${connectCategory === shelf.id ? t.railOn : t.choice}`}
                        >
                          {shelf.label} <span className="opacity-60">{shelf.count}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                    {shown.map((tpl) => {
                      const already = declaredNames.has(tpl.id)
                      return (
                        <li key={tpl.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setConnectPick(tpl.id)
                              setConnectFields(NO_FIELDS)
                              setConnectCredential('')
                              setConnectError(null)
                            }}
                            className={`flex h-full w-full flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors motion-reduce:transition-none ${t.choice}`}
                          >
                            <span className={`flex w-full items-baseline justify-between gap-2 font-medium ${t.title}`}>
                              {tpl.label}
                              {already && (
                                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[0.65rem] font-medium ${t.badge}`}>
                                  connected
                                </span>
                              )}
                            </span>
                            <span className={`text-sm leading-5 ${t.muted}`}>{tpl.summary}</span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>

                  {matches.length === 0 ? (
                    <p className={`mt-3 text-sm ${t.muted}`}>
                      Nothing here matches that. Every tool with a web address and a key can still
                      be connected — choose{' '}
                      <button
                        type="button"
                        onClick={() => { setConnectSearch(''); setConnectCategory(''); setConnectPick('rest') }}
                        className={`underline underline-offset-2 ${t.title}`}
                      >
                        Another REST list
                      </button>{' '}
                      and describe it yourself.
                    </p>
                  ) : (
                    <p className={`mt-2.5 text-xs ${t.faint}`}>
                      {narrowed
                        ? `${matches.length} of ${templates.length} tools`
                        : matches.length > shown.length
                          ? `Showing ${shown.length} of ${templates.length} tools — search or pick a kind to see the rest.`
                          : `${templates.length} tools`}
                    </p>
                  )}
                </div>
              ) : null}

              {templates.length > 0 && pickedTemplate ? (
                <form onSubmit={submitConnect} aria-label="Connect a tool" className="mt-5">
                  <div className={`space-y-3 rounded-xl border p-4 ${t.panel}`}>
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h4 className={`text-base font-semibold ${t.title}`}>
                        Connect {pickedTemplate.label}
                      </h4>
                      <button
                        type="button"
                        onClick={() => { setConnectPick(''); setConnectCredential(''); setConnectError(null) }}
                        className={`min-h-11 rounded-lg px-2 py-1 text-xs font-medium ${t.ghost}`}
                      >
                        Choose a different tool
                      </button>
                    </div>

                    {/* WHERE THE KEY COMES FROM, in that product's own words. An
                        ordered list because the steps ARE one — the key cannot be
                        copied before it is made — and because the scope named in
                        step two is the difference between handing over a reader
                        and handing over a writer. */}
                    {pickedTemplate.how_to_connect.length > 0 && (
                      <div>
                        <p className={`text-sm font-medium ${t.title}`}>How to get the key</p>
                        <ol className={`mt-1.5 list-decimal space-y-1 pl-5 text-sm leading-6 ${t.muted}`}>
                          {pickedTemplate.how_to_connect.map((step, index) => (
                            <li key={`${pickedTemplate.id}-step-${index}`}>{step}</li>
                          ))}
                        </ol>
                      </div>
                    )}

                    {pickedTemplate.fields.map((field) => (
                        <div key={field.key}>
                          <label
                            htmlFor={`${surface}-connect-${field.key}`}
                            className={`block text-sm font-medium ${t.title}`}
                          >
                            {field.label}
                            {!field.required && (
                              <span className={`ml-1 text-xs font-normal ${t.faint}`}>optional</span>
                            )}
                          </label>
                          <input
                            id={`${surface}-connect-${field.key}`}
                            type="text"
                            value={connectFields[field.key] ?? ''}
                            onChange={(e) =>
                              setConnectFields({ ...connectFields, [field.key]: e.target.value })
                            }
                            placeholder={field.placeholder}
                            autoComplete="off"
                            spellCheck={false}
                            className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                          />
                          {field.help && <p className={`mt-1 text-xs ${t.faint}`}>{field.help}</p>}
                        </div>
                      ))}

                      <div>
                        <label
                          htmlFor={`${surface}-connect-credential`}
                          className={`block text-sm font-medium ${t.title}`}
                        >
                          Credential
                        </label>
                        <input
                          id={`${surface}-connect-credential`}
                          type="password"
                          value={connectCredential}
                          onChange={(e) => setConnectCredential(e.target.value)}
                          placeholder="Paste your token or key"
                          autoComplete="off"
                          spellCheck={false}
                          className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                        />
                        {pickedTemplate.credential_help && (
                          <p className={`mt-1 text-xs ${t.faint}`}>{pickedTemplate.credential_help}</p>
                        )}
                        {pickedTemplate.key_looks_like && (
                          <p className={`mt-1 text-xs ${t.faint}`}>
                            A right-looking key: {pickedTemplate.key_looks_like}.
                          </p>
                        )}
                      </div>

                      <p className={`text-xs leading-5 ${t.muted}`}>
                        {pickedTemplate.host ? (
                          <>
                            This sends your credential to{' '}
                            <span className={`font-medium ${t.title}`}>{pickedTemplate.host}</span>, and
                            reads only — I list what is there, and never write.
                          </>
                        ) : (
                          <>This sends your credential only to the address you enter above, and reads only — I list what is there, and never write.</>
                        )}
                      </p>

                      {connectError && (
                        <p
                          role="alert"
                          className={`text-xs font-medium ${variant === 'world' ? 'text-red-800' : 'text-red-300'}`}
                        >
                          {connectError}
                        </p>
                      )}

                      <button
                        type="submit"
                        disabled={working || !canConnect}
                        className={`min-h-11 w-full rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 disabled:shadow-none ${t.primary}`}
                      >
                        {working ? 'Connecting…' : `Connect ${pickedTemplate.label}`}
                      </button>
                  </div>
                </form>
              ) : null}

              {/* THE LOOK, over everything connected — and the two ways out that
                  never depended on connecting anything. `gather_connectors`
                  sweeps EVERY declared connector in one act, so this one button
                  covers however many tools are on the list above. */}
              <div className="mt-5 flex flex-wrap gap-2">
                {gatherOption && (
                  <button
                    type="button"
                    onClick={() => { setExploring(true); choose('gather_connectors') }}
                    disabled={working}
                    className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${connected.length > 0 ? t.primary : t.secondary}`}
                  >
                    {connected.length > 1
                      ? `Go look across all ${connected.length}`
                      : connected.length === 1
                        ? 'Go look at what I can read'
                        : gatherOption.label}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setWizardStep('window')}
                  disabled={working}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${t.ghost}`}
                >
                  Point me at a folder instead
                </button>
              </div>

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
              speaks here.

              GATED ON THE CONNECT PANEL, NOT ON THE BRANCH — the same predicate
              the sweep results use. Gated on `inDiscover` it stayed hidden for
              the WHOLE discover branch, including after the look, and this
              sentence is the only place the card reports an answered salience
              target ("You pointed me at X, so that is where I spend depth").
              Measured live 2026-08-13: the operator named their own focus, the
              core accepted it (HTTP 200, revision bumped, target recorded), and
              the page did not change by one character. */}
          {!inFrontQuestions && !showDiscoverPanel && !showWindowForm && (
            <p className={`mt-5 break-words text-sm leading-6 ${t.muted}`}>{journey.card.body}</p>
          )}

          {/* WHAT ONE SWEEP FOUND, PER TOOL. The aggregate of the look: every
              declared connector on its own row, counts and freshest stamp where
              it read, its own reason where it did not. Contents-free by
              construction — the core never puts a row's body on this state. */}
          {swept.length > 0 && showSweep && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>
                What I found across {swept.length === 1 ? 'it' : `all ${swept.length}`}
              </h3>
              <ul className="mt-2 space-y-1.5 text-sm">
                {swept.map((row) => (
                  <li key={row.name} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                    <span aria-hidden className={`h-2 w-2 shrink-0 self-center rounded-full ${row.connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <span className={`font-medium ${t.title}`}>{row.name}</span>
                    <span className={row.connected ? t.faint : variant === 'world' ? 'text-red-800' : 'text-red-300'}>
                      {sweepLine(row)}
                    </span>
                  </li>
                ))}
              </ul>
              {journey.state.connector_sweep?.swept_at && (
                <p className={`mt-2 text-xs ${t.faint}`}>
                  Read {dayOf(journey.state.connector_sweep.swept_at)}. I list what is there and
                  never write, and none of what is in them is stored here.
                </p>
              )}
            </div>
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
                {answeredTarget ? 'Point me somewhere else' : 'Go deep on that one'}
              </button>
              {/* EVERY ANSWER LANDS SOMEWHERE THE OPERATOR CAN SEE — one of these
                  two always renders once an answer has been sent: what the core
                  recorded, or why it refused. Silence here is the defect. */}
              {refusedAction === 'answer_salience' && error ? (
                <p
                  role="alert"
                  className={`mt-2 text-xs font-medium ${variant === 'world' ? 'text-red-800' : 'text-red-300'}`}
                >
                  {error}
                </p>
              ) : answeredTarget ? (
                <p role="status" className={`mt-2 text-xs ${t.faint}`}>
                  I am pointed at {answeredTarget}. Choose the folder that holds it below —
                  if it is called something else there, I will ask you what it is.
                </p>
              ) : null}
            </form>
          )}

          {journey.card.entry?.discovery?.executed && showSweep && (
            <div className={`mt-5 p-4 ${t.panel}`}>
              <h3 className={`text-sm font-semibold ${t.title}`}>What I went and looked for</h3>
              <ul className="mt-2 space-y-3 text-sm">
                {/*
                  TWO KINDS OF PROBE, ONE LIST. A local one shows the name
                  pattern it matched inside the ratified folder; an outward one
                  shows the QUERY that left this machine and the results that
                  came back.

                  EVERY STRING FROM A RESULT IS RENDERED AS TEXT, never as
                  markup and never as a template. The core scrubs and caps each
                  field before it gets here (control characters, angle brackets,
                  lone surrogates, a length cap, and an address that is not
                  http/https reduced to an empty string) precisely because
                  whoever ranks well for the operator's own words could be an
                  adversary. Keep it this way: `dangerouslySetInnerHTML`, a
                  markdown renderer, or trusting `found.url` without the
                  emptiness check below would each undo that at a stroke.
                */}
                {journey.card.entry.discovery.executed.executed.map((probe, index) => (
                  <li key={`ran-${probe.kind}-${probe.pattern ?? probe.query ?? index}`}>
                    <code className="font-mono text-[0.8rem]">
                      {probe.pattern ?? (probe.query ? `“${probe.query}”` : probe.kind)}
                    </code>
                    {probe.results ? (
                      <>
                        <span className={`block text-xs ${t.faint}`}>
                          searched the web{probe.provider ? ` with ${probe.provider}` : ''}
                          {probe.truncated && ' — more results than I show'}
                        </span>
                        <ul className="mt-1.5 space-y-1.5">
                          {probe.results.map((found, position) => (
                            <li key={`${found.url || found.title}-${position}`}>
                              {found.url ? (
                                <a
                                  href={found.url}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  className="underline underline-offset-2"
                                >
                                  {found.title || found.url}
                                </a>
                              ) : (
                                <span>{found.title}</span>
                              )}
                              {found.url && (
                                <span className={`block text-xs ${t.faint}`}>{found.url}</span>
                              )}
                              {found.snippet && (
                                <span className={`block text-xs ${t.faint}`}>{found.snippet}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <span className={`block ${t.faint}`}>
                        {(probe.matches?.length ?? 0) > 0
                          ? probe.matches?.join(', ')
                          : 'nothing matched by name'}
                        {probe.truncated && ' — stopped at my limit before the end of the folder'}
                      </span>
                    )}
                  </li>
                ))}
                {journey.card.entry.discovery.executed.deferred.map((probe, index) => (
                  <li key={`skipped-${probe.kind}-${index}`}>
                    <code className="font-mono text-[0.8rem]">
                      {probe.query ? `“${probe.query}”` : probe.kind}
                    </code>
                    <span className={`block ${t.faint}`}>
                      did not run — {probe.reason.replaceAll('_', ' ')}
                    </span>
                  </li>
                ))}
              </ul>
              {/*
                THE RE-RUN, where the results are. The core offers this action
                only once a search tool is declared, so this button never
                appears unable to work — and when it is absent the deferral
                line above says what to connect.
              */}
              {journey.card.entry.next_actions.some((a) => a.action === 'run_discovery') && (
                <button
                  type="button"
                  disabled={working}
                  onClick={() => void send('run_discovery', {})}
                  className={`mt-3 min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${t.secondary}`}
                >
                  {journey.card.entry.next_actions.find((a) => a.action === 'run_discovery')?.label}
                </button>
              )}
              {/* The refusal lands AT the control that fired it. This panel can
                  sit several screens above the shared error line, and a look-up
                  that silently did nothing reads as a broken button. */}
              {refusedAction === 'run_discovery' && error && (
                <p
                  role="alert"
                  className={`mt-2 text-xs font-medium ${variant === 'world' ? 'text-red-800' : 'text-red-300'}`}
                >
                  {error}
                </p>
              )}
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
                    {/*
                      A QUESTION WITH A FIELD, where the core says there is one.
                      Only the earned organisation ask carries an action today —
                      the other residuals are printed with no way to answer them,
                      which is a real gap and is NOT hidden here by rendering a
                      field that would send nothing.
                    */}
                    {question.action === 'answer_organization' && (
                      <form className="mt-2 flex flex-col gap-2 sm:flex-row" onSubmit={submitOrganization}>
                        <input
                          type="text"
                          name={`${surface}-organization`}
                          value={organization}
                          onChange={(event) => setOrganization(event.target.value)}
                          placeholder="A company name, or “just me”"
                          autoComplete="organization"
                          className={`min-h-11 flex-1 rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                        />
                        <button
                          type="submit"
                          disabled={working || !organization.trim()}
                          className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50 ${t.secondary}`}
                        >
                          Remember that
                        </button>
                      </form>
                    )}
                    {question.id === 'organization' &&
                      refusedAction === 'answer_organization' &&
                      error && (
                        <p
                          role="alert"
                          className={`mt-2 text-xs font-medium ${variant === 'world' ? 'text-red-800' : 'text-red-300'}`}
                        >
                          {error}
                        </p>
                      )}
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
              front and the window form own their own buttons above.

              THE SAME GATE AS THE SENTENCE ABOVE, and for a harder reason: on
              the discover branch after the look, this row holds the ONLY way
              onward ("Choose a folder I may read"). Gated on `inDiscover` it
              never rendered — the connect panel had already handed over, so its
              own two buttons were gone too, and an operator who had just told
              the Cabinet what to open had no control left on the page. That is
              the "I cannot continue" half of the live report. */}
          {!inFrontQuestions && !showDiscoverPanel && !showWindowForm && !purgeArmed && journey.card.options.length > 0 && (
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
