'use client'

/**
 * THE ONBOARDING ROUTER — one screen at a time, and the state every screen is
 * drawn from.
 *
 * WHAT THIS FILE STOPPED BEING. It was a ~2,000-line CARD: every panel appeared
 * by an additive predicate and none of them ever left, so a connected run ended
 * with a sweep table, an identity picker, a ranked question, a discovery log, a
 * residuals list, a receipt and eight buttons on one page. The Captain drove it
 * and reported both halves of the same defect — "this is way too much text" and,
 * on an objectively FINISHED journey, "i believe i've answered everything and am
 * now stuck and can't continue again?". A state inspector, not a journey.
 *
 * WHAT IT IS NOW. A router: it holds the state, talks to the core, and renders
 * EXACTLY ONE screen. Screens replace each other. Nothing from the previous
 * screen survives except the four-stop rail and the standing read-only line.
 * Which screen is a pure decision in `lib/onboarding/screen-router.ts`, so it
 * is testable without a DOM and cannot become a pile of `&&`-ed booleans again.
 *
 * WHY EVERY HOOK STILL LIVES HERE. Screens are PURE: they render and they call
 * back. That is not tidiness — it keeps ONE hook order, which
 * `journey-card.test.ts` scripts by index with `Object.is` assertions so a hook
 * added, removed or reordered fails loudly there instead of silently testing
 * the wrong state. NEW HOOKS GO AT THE END, for the same reason.
 *
 * WHAT THIS FILE MUST NEVER DO: render two screens at once, or let a control
 * fire an act that the core will refuse for a reason the screen could have
 * stated first. Wrong input is meant to be impossible here, not corrected
 * afterwards.
 */
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { WINDOW_RELATIONS } from '@/lib/onboarding/types'
import type {
  ConnectorCatalog,
  OnboardingAction,
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
  blockedReason,
  canAdvance,
  nextStep,
  prevStep,
  resumeStep,
  seedRequest,
  type WizardStepId,
} from '@/lib/onboarding/wizard'
import { FLOW_STOPS, stopIndex } from '@/lib/onboarding/flow-rail'
import { journeyIsComplete } from '@/lib/onboarding/completion'
import {
  NO_ASKS,
  screenFor,
  type AskId,
  type OpenAsks,
  type ScreenId,
} from '@/lib/onboarding/screen-router'
import Arrival, { wantsFullSurface } from './arrival'
import { StandingLine } from './screen-chrome'
import { BeginScreen, DreamScreen, WelcomeScreen, YouScreen } from './screens/questions'
import { ConnectScreen, FolderScreen, SweepScreen } from './screens/access'
import { IdentityScreen, OrganizationScreen, SalienceScreen } from './screens/asks'
import { OpenQuestions, ProbeLog } from './screens/residuals'
import {
  ApproveScreen,
  FindScreen,
  LookScreen,
  NoticeScreen,
  PurgeScreen,
  SCAN_LINES,
} from './screens/result'

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

// The empty starting values, module-level and frozen so they have a STABLE
// identity. journey-card.test.ts scripts the hook order and asserts each
// initial value with Object.is — deliberately, so a hook added, removed or
// reordered fails loudly there instead of silently testing the wrong state —
// and a fresh `{}` per render would make that assertion unsatisfiable.
export const NO_IDENTITY_PICKS: Readonly<Record<string, string>> = Object.freeze({})

/** The merge picker's empty starting value — stable for the same reason. */
export const NO_MERGE: readonly string[] = Object.freeze([])

/** The connect step's empty template-field answers — stable for the same reason. */
export const NO_FIELDS: Readonly<Record<string, string>> = Object.freeze({})

/** The skipped-asks set's empty starting value — stable for the same reason. */
export const NO_SKIPPED: readonly string[] = Object.freeze([])

/**
 * The purpose a window carries when the operator has told the Cabinet nothing
 * else. THE FIELD THAT ASKED FOR THIS IS GONE (ruling, 2026-08-14): it re-asked
 * the dream one screen after it was given, and being asked twice reads as not
 * being heard. Priority is recorded-window > dream > mission > this.
 */
export const DEFAULT_PURPOSE = 'Find one useful thing I may be missing.'

// The sweep's card language. Re-exported so this module stays the one import
// site the card's own tests already point at; the implementation lives in
// lib/onboarding/sweep-line.ts, which the arrival also consumes.
import { plainReason, sweepLine } from '@/lib/onboarding/sweep-line'
export { plainReason, sweepLine }
export { CATALOG_SHOWN } from './screens/access'
export { IDENTITY_SHOWN } from './screens/asks'

/**
 * What the operator has to state when the folder they proposed shares no word
 * with the target they answered. The core refuses that window rather than
 * retargeting it silently, and takes ONE of two statements; this is the shape
 * the router renders them from.
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

/** The folder's own name — what the core's name test compares, and names back. */
function folderName(path: string): string {
  return path.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || path
}

/** How long one plain-words line of the first read stays up. */
const SCAN_LINE_MS = 1400

/**
 * Which earned ask an offered action re-opens. The core still lists these as
 * options on a card the operator may be past; choosing one is a request for
 * that question back, not a scroll to a panel that is no longer on the page.
 */
const ASK_FOR_ACTION: Partial<Record<OnboardingAction, AskId>> = {
  record_operator_identity: 'identity',
  answer_salience: 'salience',
  answer_organization: 'organization',
}

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
  // Non-flow "Change it" / "Choose another folder" re-opens the folder screen.
  const [editScope, setEditScope] = useState(false)
  // Where the operator is inside the welcome stage. The core owns every stage
  // AFTER the front; this is only where they are inside it.
  const [wizardStep, setWizardStep] = useState<WizardStepId>('welcome')
  // Question one: what the operator does. Becomes the journey seed.
  const [role, setRole] = useState('')
  // Question two: the dream. Becomes mission.purpose, and seeds the window's
  // purpose so the folder screen never asks for it again.
  const [dream, setDream] = useState('')
  // Question three: point me, or go find where I am useful.
  const [startPreference, setStartPreference] = useState<'' | 'point' | 'decide'>('')
  const [purgeArmed, setPurgeArmed] = useState(false)
  const [purgeConfirmation, setPurgeConfirmation] = useState('')
  const [source, setSource] = useState('~/Documents')
  // WHETHER THE OPERATOR HAS TOUCHED THE FOLDER FIELD. `source` alone cannot
  // answer that — its default is a real path someone might also type — and
  // without the answer the only sync into this field (re-opening the folder
  // screen over an existing proposal) overwrote whatever they had entered.
  const [sourceEdited, setSourceEdited] = useState(false)
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
  // The connect screen's catalog. `null` means it has not loaded yet (fetched
  // once, client-side); an empty one means no pack ships, and the screen falls
  // back to the folder.
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
  // over the names, and one shelf at a time. Pure view state.
  const [connectSearch, setConnectSearch] = useState('')
  const [connectCategory, setConnectCategory] = useState('')
  // WHETHER THE OPERATOR HAS SAID "that is enough, go and look". Connecting is
  // deliberately not a one-shot: a cabinet reads across MANY tools, so the
  // screen stays open — connect, see what each one reads, connect another —
  // until they ask for the look.
  const [exploring, setExploring] = useState(false)
  // WHICH act the visible refusal belongs to, so the reason renders AT the
  // control that fired it. Cleared at the start of every send.
  const [refusedAction, setRefusedAction] = useState<OnboardingAction | null>(null)
  // Whose work this is. Empty until they say — never pre-filled from a folder
  // name, a credential or a search result.
  const [organization, setOrganization] = useState('')
  // What the operator is CALLED — question one's opening line. Optional, and
  // never invented.
  const [name, setName] = useState('')
  // Whether the operator has touched the escape hatch's name field.
  const [salienceNameEdited, setSalienceNameEdited] = useState(false)
  // WHICH EARNED ASKS THE OPERATOR CHOSE TO LEAVE. A question they cannot
  // answer must not be a wall; skipping is a real control, and it is session
  // state on purpose — nothing is recorded by declining to answer.
  const [skipped, setSkipped] = useState<readonly string[]>(NO_SKIPPED)
  // THE FIRST READ IS RUNNING. Set the moment the Charter is approved and
  // cleared when the core answers, so the look screen holds the surface and
  // then flows into the find WITHOUT a click.
  const [scanning, setScanning] = useState(false)
  // Which plain-words line of the read is up. Advanced by a timer because the
  // read is one round-trip and the client cannot see inside it.
  const [scanLine, setScanLine] = useState(0)
  // What the operator says is wrong with a finding — travels with their rating.
  // NEW HOOKS GO HERE, at the end: an insert renumbers every index the test
  // script pins, which is the sensor working rather than an inconvenience.
  const [correction, setCorrection] = useState('')
  const effectiveSurface = useRef<Extract<OnboardingSurface, 'dashboard' | 'world' | 'companion'>>(surface)
  const handoffIds = useRef<{ trace_id?: string; correlation_id?: string }>({})
  // Guards the connect flow's three server round-trips against a re-entrant
  // submit — the credential write must never fire twice for one click.
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
      // RESUME ON THE RIGHT SCREEN. A reload mid-flow lands on the screen the
      // RECORD implies, not back at question one — and the fields re-fill from
      // what the core already holds, so Back shows the operator their own words
      // rather than a blank. The mapping is `resumeStep`, and the screen it
      // produces is pinned in screen-router.test.ts per stage.
      if (body.card.stage === 'welcome' && body.state.seed) {
        setRole(body.state.seed.text)
        setName(body.state.operator_name?.name ?? '')
        setDream(body.state.mission?.purpose ?? '')
        setStartPreference(body.state.start_preference ?? '')
        setWizardStep(resumeStep(true, body.state.start_preference))
        // A sweep on the record means the look already happened, so the connect
        // catalog is behind them: resuming into it would ask them to connect a
        // tool they have already connected and read.
        if (body.state.connector_sweep) setExploring(true)
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

  // The connect screen's catalog, fetched once. It reads a shipped DATA file
  // (never a secret), so a failure is an empty catalog and the folder path, not
  // an error — the discover branch stays usable with no tools to offer.
  useEffect(() => {
    let cancelled = false
    void getConnectorCatalog()
      .then((catalog) => { if (!cancelled) setConnectorCatalog(catalog) })
      .catch(() => { if (!cancelled) setConnectorCatalog({ templates: [], categories: [] }) })
    return () => { cancelled = true }
  }, [])

  // THE READ'S OWN CLOCK. It advances the plain-words line and STOPS at the
  // last one — it never loops and never claims a step finished, because the
  // client cannot see inside the round-trip. The read landing is what ends this
  // screen, not the timer.
  useEffect(() => {
    if (!scanning) return
    const timer = setInterval(() => {
      setScanLine((current) => Math.min(current + 1, SCAN_LINES.length - 1))
    }, SCAN_LINE_MS)
    return () => clearInterval(timer)
  }, [scanning])

  const send = useCallback(
    async (
      action: OnboardingAction,
      extra: Record<string, unknown> = {},
      // The revision to send AS. Defaults to the card in this render's closure —
      // but a handler that fires two actions back to back (declare then gather)
      // holds a STALE closure between them: the first bumps the revision and the
      // second would collide (revision_conflict) unless it is told the fresh one
      // the first returned.
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
          setWizardStep('welcome')
          setRole('')
          setName('')
          setDream('')
          setStartPreference('')
          setExploring(false)
          setSkipped(NO_SKIPPED)
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

  /**
   * The rating, and the operator's own line about what is wrong with it. The
   * correction travels WITH the grade in one observation — a grade with no
   * correction path is a dead end, and two separate submissions would let the
   * grade land without the reason.
   */
  async function recordFeedback(
    status: 'useful' | 'not_useful' | 'corrected',
    note: string
  ) {
    const ids = {
      action_id: newActionId('feedback'),
      trace_id: newActionId('trace'),
      correlation_id: journey?.evidence?.correlation_id || newActionId('corr'),
    }
    const said = note.trim()
    const recorded = await reportEvidence('feedback', status, {
      feedback_rating: status,
      feedback_category: status === 'useful' ? 'useful_as_shown' : 'wrong_or_missing_context',
      ...(said ? { feedback_correction: said } : {}),
      rendered_stage: journey?.card.stage,
    }, ids)
    if (recorded) {
      setFeedbackRecorded(status)
    } else {
      setError('Your feedback could not be preserved yet. Please try again.')
    }
  }

  const wizardValues = { name, role, dream, startPreference }

  // The three answers, sent as ONE action so role, dream and the preference all
  // land before any folder is named. On success the front hands off to the
  // branch the operator chose.
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

  function skipAsk(ask: string) {
    setSkipped((current) => (current.includes(ask) ? current : [...current, ask]))
  }

  const salienceOption = journey?.card.options.find(
    (option) => option.action === 'answer_salience'
  )
  const salienceOptions: OnboardingSalienceOption[] = salienceOption?.options ?? []
  const salienceAsksName =
    salienceOptions.find((option) => option.id === salienceChoice)?.input === 'seed'
  // WHAT THE CORE ALREADY HOLDS, read from committed state rather than from the
  // local field, so it says what the CORE recorded rather than what was typed.
  const answeredTarget = journey?.state.salience?.target ?? ''
  const saliencePrefill = salienceOption?.prefill ?? ''
  const salienceNameValue = salienceNameEdited ? salienceName : salienceName || saliencePrefill

  /**
   * THE WINDOW'S PURPOSE, without a field that asks for it.
   * Recorded-window > the dream they gave > the mission the core stored > the
   * default. Every one of these is either the operator's own words or a stated
   * default; none of them is invented from a folder name.
   */
  function windowPurpose(): string {
    const recorded = String(journey?.state.purpose ?? '').trim()
    const dreamed = dream.trim()
    const mission = String(journey?.state.mission?.purpose ?? '').trim()
    return recorded || dreamed || mission || DEFAULT_PURPOSE
  }

  function windowPayload(): Record<string, unknown> {
    return {
      source,
      purpose: windowPurpose(),
      // `relationship_destination` is NOT sent. The radio that set it granted
      // nothing — its own helper said so — and the core defaults it to the same
      // value that radio recommended. Where authority grows is the trust ladder.
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

  function answerSalience(choice: string) {
    const picked = salienceOptions.find((option) => option.id === choice)
    const extra: Record<string, unknown> = { choice }
    if (picked?.input === 'seed') extra.name = salienceNameValue.trim()
    if (salienceMerge.length > 0) extra.same_as = [...salienceMerge]
    void send('answer_salience', extra)
  }

  function submitSalience(event: FormEvent) {
    event.preventDefault()
    if (!salienceChoice) return
    answerSalience(salienceChoice)
  }

  function submitOrganization(event: FormEvent) {
    event.preventDefault()
    const said = organization.trim()
    if (!said) return
    void send('answer_organization', { organization: said })
  }

  /**
   * One tap on a confirm chip = one recorded identity, through the SAME act a
   * pick from the list goes through. The chip is a shortcut to an answer, never
   * a second way of storing one.
   */
  function confirmIdentity(connector: string, identifier: string) {
    if (!identifier.trim()) return
    setHandles((current) => ({ ...current, [connector]: identifier }))
    void send('record_operator_identity', { handles: { [connector]: [identifier] } })
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
  const templates = connectorCatalog?.templates ?? []
  // EVERY declared connector as the last sweep found it — read from the config
  // rather than from what this session happens to have done.
  const swept: OnboardingSweptConnector[] = journey?.state.connector_sweep?.connectors ?? []
  const declaredNames = new Set<string>([
    ...swept.map((row) => row.name),
    ...(journey?.state.connector_declarations ?? []).map((row) => row.name),
  ])
  const connected = [...declaredNames].map((declaredName) => ({
    name: declaredName,
    row: swept.find((entry) => entry.name === declaredName),
    label: templates.find((tpl) => tpl.id === declaredName)?.label ?? declaredName,
  }))
  const pickedTemplate = templates.find((tpl) => tpl.id === connectPick) ?? null
  const gatherOption = journey?.card.options.find((o) => o.action === 'gather_connectors')

  // CONNECT A TOOL, right here in onboarding — the write half of the read lane.
  // Three server steps, in order: the credential VALUE goes to cabinet/.env by
  // the safe writer (and ONLY there); the connector is declared with the env var
  // NAME (never the value); and the sweep runs, so the operator sees what that
  // tool actually reads before deciding whether to add another. The credential
  // is wiped from memory the instant the declaration lands.
  //
  // A TOOL ALREADY DECLARED IS A RETRY, NOT A SECOND TOOL. The commonest
  // failure is a key pasted short or made with the wrong scope: the connector
  // exists, the sweep says the key was refused, and the fix is a new key under
  // the SAME name. Declaring again would be refused as a duplicate name and read
  // as "you cannot fix this", so the declare is skipped and the credential is
  // simply replaced.
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
        if (!declared) return // send() put the refusal on the screen
        revision = declared.card.revision
      }
      setConnectCredential('')
      setConnectPick('')
      setConnectFields(NO_FIELDS)
      setConnectSearch('')
      // Read with the revision the declaration just produced, not the stale one
      // in this closure. ONE sweep covers EVERY declared connector.
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

  /**
   * THE APPROVAL, AND THE READ IT STARTS. `scanning` holds the look screen for
   * the whole round-trip, so approving flows into the result with no click —
   * and it is cleared in every exit, including the refusal, because a stuck
   * progress screen is the worst possible way to report a failure.
   */
  async function ratify() {
    setScanLine(0)
    setScanning(true)
    try {
      await send('ratify_charter', { charter_hash: journey?.state.charter?.hash })
    } finally {
      setScanning(false)
    }
  }

  function choose(action: OnboardingAction) {
    if (action === 'propose_window') {
      // PRE-FILL, NEVER OVERWRITE. Re-opening the folder screen syncs it from
      // the last proposal so "Change it" starts from what is already approved —
      // but only while the field is PRISTINE.
      if (!sourceEdited && journey?.state.source?.root) setSource(journey.state.source.root)
      if (journey?.state.source?.ownership) setOwnership(journey.state.source.ownership)
      if (journey?.state.source?.authority_basis) {
        setAuthorityBasis(journey.state.source.authority_basis)
      }
      setEditScope(true)
      setWizardStep('window')
      return
    }
    if (action === 'ratify_charter') {
      void ratify()
      return
    }
    if (action === 'purge') {
      setPurgeArmed(true)
      setPurgeConfirmation('')
      return
    }
    const reopens = ASK_FOR_ACTION[action]
    if (reopens) {
      // AN ASK IS A SCREEN NOW, not a scroll target. Choosing it un-skips that
      // one question and routes to it — the operator asked for it back.
      setSkipped((current) => current.filter((id) => id !== reopens))
      setExploring(true)
      setWizardStep('discover')
      return
    }
    void send(action)
  }

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

  // ------------------------------------------------------------------- ROUTE
  const card = journey?.card
  const identityQuestion = card?.entry?.identity_question ?? null
  const organizationQuestion =
    card?.entry?.questions?.find((question) => question.action === 'answer_organization') ?? null
  // WHICH QUESTIONS ARE STILL OPEN — from what the CORE offers plus what the
  // committed state records, never from what this session happens to have sent.
  const asks: OpenAsks = card
    ? {
        identity:
          !!identityQuestion?.connectors?.length &&
          Object.keys(journey?.state.operator_identity?.handles ?? {}).length === 0,
        salience: salienceOptions.length > 0 && !answeredTarget,
        organization: !!organizationQuestion,
      }
    : NO_ASKS
  const arrived = !!journey && journey.card.kind === 'arrival' && journeyIsComplete(journey.state)
  const screen: ScreenId = screenFor({
    loading,
    stage: card?.stage ?? '',
    kind: card?.kind ?? '',
    arrived,
    step: wizardStep,
    explored: exploring,
    asks,
    skipped,
    // A REFUSED ANSWER RE-OPENS ITS QUESTION. The reason has to land on the
    // control that produced it, and a refusal that leaves the operator on the
    // next screen is a refusal they never see.
    refusedAsk: (refusedAction && error && ASK_FOR_ACTION[refusedAction]) || null,
    editScope,
    purgeArmed,
    scanning,
    fullSurface: wantsFullSurface(),
  })

  const activePhase = stopIndex(card?.stage ?? '', wizardStep)
  const shared = { t, variant, working, surface }
  const refusalFor = (action: OnboardingAction) =>
    refusedAction === action && error ? error : ''

  // THE ARRIVAL KEEPS ITS OWN SURFACE. On /onboarding it IS the page, so the
  // boxed shell would be a frame around a frame; on the World it is a fixed
  // overlay panel and cannot lose the shell without becoming loose text on a
  // pixel map.
  if (journey && screen === 'arrival') {
    const inWorld = variant === 'world'
    return (
      <section className={inWorld ? `p-6 sm:p-7 ${t.shell}` : 'w-full'}>
        {inWorld && (
          <div className="mb-2 flex justify-end">
            <button
              type="button"
              aria-label="Hide orientation card"
              aria-expanded="true"
              onClick={() => setCollapsed(true)}
              className="min-h-11 min-w-11 rounded-md border border-stone-600 text-lg"
            >
              −
            </button>
          </div>
        )}
        <Arrival journey={journey} t={t} variant={variant} working={working} choose={choose} />
        <div aria-live="polite" className="mt-4 min-h-5 text-sm">
          {working && <span className={t.muted}>The Cabinet is working on that…</span>}
          {error && <span className="font-medium text-red-500 dark:text-red-300">{error}</span>}
        </div>
      </section>
    )
  }

  return (
    <section
      className={`p-6 sm:p-7 ${t.shell}`}
      aria-labelledby={journey ? 'onboarding-card-title' : undefined}
      aria-label={journey ? undefined : 'Cabinet orientation'}
    >
      {/* ONE MOTION IDEA, and it belongs to the router: a screen replacing
          another rises a few pixels as it arrives, keyed on the screen id so it
          fires exactly once per change. Reduced motion removes it entirely. */}
      <style>{`
        @keyframes cabinet-screen-in {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: none; }
        }
        .cabinet-screen { animation: cabinet-screen-in 260ms cubic-bezier(0.2, 0.8, 0.2, 1) both; }
        @media (prefers-reduced-motion: reduce) { .cabinet-screen { animation: none; } }
      `}</style>

      <div className="flex items-start justify-between gap-4">
        <p className={`text-[0.7rem] font-semibold uppercase tracking-[0.2em] ${t.eyebrow}`}>
          Setting up your Cabinet
        </p>
        {variant === 'world' && (
          <button
            type="button"
            aria-label="Hide orientation card"
            aria-expanded="true"
            onClick={() => setCollapsed(true)}
            className="min-h-11 min-w-11 shrink-0 rounded-md border border-stone-600 text-lg"
          >
            −
          </button>
        )}
      </div>

      {/* FOUR STOPS, AND IT NEVER GOES BACKWARDS. The mapping and the monotonic
          law it obeys live in lib/onboarding/flow-rail.ts, where both are
          testable without a DOM. */}
      {activePhase >= 0 && (
        <ol
          className="mt-4 flex items-center gap-1.5"
          aria-label={`Onboarding progress: step ${activePhase + 1} of ${FLOW_STOPS.length}`}
          role="list"
        >
          {FLOW_STOPS.map((stop, index) => {
            const done = index < activePhase
            const current = index === activePhase
            return (
              <li
                key={stop.id}
                className="flex flex-1 flex-col items-center gap-1.5"
                aria-current={current ? 'step' : undefined}
              >
                <div className="flex w-full items-center gap-1.5">
                  <span
                    title={stop.hint}
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-xs font-semibold transition-colors motion-reduce:transition-none ${current ? t.railOn : done ? t.railDone : t.railOff}`}
                  >
                    {done ? '✓' : index + 1}
                  </span>
                  {index < FLOW_STOPS.length - 1 && (
                    <span className={`h-px flex-1 ${index < activePhase ? t.railLineDone : t.railLine}`} />
                  )}
                </div>
                <span className={`hidden text-center text-[0.65rem] font-medium sm:block ${current ? t.eyebrow : t.faint}`}>
                  {stop.label}
                </span>
              </li>
            )
          })}
        </ol>
      )}

      <div key={screen} className="cabinet-screen mt-7">
        {screen === 'loading' && (
          <p role="status" className={t.muted}>Opening your Cabinet orientation…</p>
        )}

        {screen === 'unavailable' && (
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

        {screen === 'welcome' && <WelcomeScreen {...shared} onBegin={advance} />}

        {screen === 'you' && (
          <YouScreen
            {...shared}
            name={name}
            role={role}
            onName={setName}
            onRole={setRole}
            onNext={advance}
            onBack={retreat}
            blocked={blockedReason('role', wizardValues)}
          />
        )}

        {screen === 'dream' && (
          <DreamScreen
            {...shared}
            name={name}
            dream={dream}
            onDream={setDream}
            onNext={advance}
            onBack={retreat}
          />
        )}

        {screen === 'begin' && (
          <BeginScreen
            {...shared}
            startPreference={startPreference}
            onPreference={setStartPreference}
            onNext={advance}
            onBack={retreat}
            blocked={
              canAdvance('start', wizardValues) ? '' : blockedReason('start', wizardValues)
            }
          />
        )}

        {screen === 'connect' && (
          <ConnectScreen
            {...shared}
            catalog={connectorCatalog}
            connected={connected}
            picked={pickedTemplate}
            credential={connectCredential}
            fields={connectFields}
            search={connectSearch}
            category={connectCategory}
            connectError={connectError ?? ''}
            /* The core's own option decides whether the look is offered at
               all; the count only decides how it reads. */
            gatherLabel={
              !gatherOption
                ? null
                : connected.length > 1
                  ? `Go look across all ${connected.length}`
                  : connected.length === 1
                    ? 'Go look at what I can read'
                    : gatherOption.label
            }
            onPick={(id) => {
              setConnectPick(id)
              setConnectFields(NO_FIELDS)
              setConnectCredential('')
              setConnectError(null)
              setConnectSearch('')
              setConnectCategory('')
            }}
            onClearPick={() => { setConnectPick(''); setConnectCredential(''); setConnectError(null) }}
            onCredential={setConnectCredential}
            onField={(key, value) => setConnectFields({ ...connectFields, [key]: value })}
            onSearch={setConnectSearch}
            onCategory={setConnectCategory}
            onSubmit={submitConnect}
            onReconnect={reconnect}
            onLook={() => { setExploring(true); void send('gather_connectors') }}
            onFolderInstead={() => setWizardStep('window')}
            onBack={retreat}
          />
        )}

        {screen === 'sweep' && (
          <>
          <SweepScreen
            {...shared}
            swept={swept}
            sweptAt={journey?.state.connector_sweep?.swept_at}
            answeredTarget={answeredTarget}
            onChooseFolder={() => setWizardStep('window')}
            onConnectMore={() => setExploring(false)}
            onRepoint={() => setSkipped(NO_SKIPPED)}
            repointable={salienceOptions.length > 0}
            error={refusedAction && error ? error : ''}
            card={card}
          />
          {/* THE LOG AND THE OPEN QUESTIONS, on every screen the old card
              showed them on. They are furniture, not messages, so they render
              plainly — and they render HERE rather than nowhere, because a
              redesign that drops a disclosure is the one failure this branch
              is guarded against. */}
          <ProbeLog
            t={t}
            variant={variant}
            working={working}
            entry={card?.entry}
            onRerun={() => void send('run_discovery')}
            error={refusalFor('run_discovery')}
          />
          <OpenQuestions t={t} questions={card?.entry?.questions} />
          </>
        )}

        {screen === 'identity' && identityQuestion && (
          <IdentityScreen
            {...shared}
            question={identityQuestion}
            handles={handles}
            onPick={(connector, identifier) =>
              setHandles((current) => ({ ...current, [connector]: identifier }))
            }
            onConfirm={confirmIdentity}
            onSubmit={submitIdentity}
            onSkip={() => skipAsk('identity')}
            error={refusalFor('record_operator_identity')}
          />
        )}

        {screen === 'salience' && (
          <SalienceScreen
            {...shared}
            offer={salienceOption ?? null}
            options={salienceOptions}
            choice={salienceChoice}
            nameValue={salienceNameValue}
            merge={salienceMerge}
            onChoice={setSalienceChoice}
            onName={(value) => { setSalienceNameEdited(true); setSalienceName(value) }}
            onMerge={(id) =>
              setSalienceMerge((current) =>
                current.includes(id) ? current.filter((one) => one !== id) : [...current, id]
              )
            }
            onConfirm={answerSalience}
            onSubmit={submitSalience}
            onSkip={() => skipAsk('salience')}
            error={refusalFor('answer_salience')}
          />
        )}

        {screen === 'organization' && organizationQuestion && (
          <OrganizationScreen
            {...shared}
            prompt={organizationQuestion.prompt}
            why={organizationQuestion.why}
            organization={organization}
            onOrganization={setOrganization}
            onSubmit={submitOrganization}
            onSkip={() => skipAsk('organization')}
            error={refusalFor('answer_organization')}
          />
        )}

        {screen === 'folder' && (
          <>
            <FolderScreen
              {...shared}
              source={source}
              ownership={ownership}
              authorityBasis={authorityBasis}
              onSource={(value) => { setSourceEdited(true); setSource(value) }}
              onUseDocuments={() => { setSourceEdited(false); setSource('~/Documents') }}
              onOwnership={setOwnership}
              onAuthorityBasis={setAuthorityBasis}
              onSubmit={submitScope}
              onBack={() => { setEditScope(false); if (!editScope) retreat() }}
              backLabel={editScope ? 'Leave it as it is' : 'Back'}
              error={refusalFor('propose_window')}
              managing={editScope}
            />
            {/* THE REFUSAL THAT CARRIES ITS OWN WAY OUT — rendered on the screen
                that caused it, never at the foot of a page below it. */}
            {relationAsk && (
              <div className={`mt-6 p-4 ${t.panel}`}>
                <h3 className={`text-sm font-semibold ${t.title}`}>
                  You pointed me at {relationAsk.target}, and “{relationAsk.window}” shares no word
                  with it.
                </h3>
                <p className={`mt-1 text-xs ${t.faint}`}>
                  I cannot know what is in a folder before I am allowed to open it, so this is yours
                  to say. Whichever you choose is recorded and shown on the Charter.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {relationAsk.relations.map((relation) => (
                    <button
                      key={relation}
                      type="button"
                      name={`${surface}-relation-${relation}`}
                      disabled={working}
                      onClick={() => submitRelation(relation)}
                      className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-45 ${t.secondary}`}
                    >
                      {relation === 'same_thing'
                        ? `“${relationAsk.window}” IS ${relationAsk.target}, under another name`
                        : 'That is somewhere else I want opened'}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {screen === 'approve' && card && (
          <ApproveScreen
            {...shared}
            card={card}
            onApprove={() => void ratify()}
            onChange={() => choose('propose_window')}
            error={refusalFor('ratify_charter')}
          />
        )}
        {screen === 'approve' && card && (
          <>
            <ProbeLog
              t={t}
              variant={variant}
              working={working}
              entry={card.entry}
              onRerun={() => void send('run_discovery')}
              error={refusalFor('run_discovery')}
            />
            <OpenQuestions t={t} questions={card.entry?.questions} />
          </>
        )}

        {screen === 'look' && (
          <LookScreen {...shared} line={scanLine} source={journey?.state.source?.root ?? null} />
        )}

        {screen === 'find' && card && (
          <FindScreen
            {...shared}
            card={card}
            stamp={journey?.state.first_dividend?.delivered_at ?? null}
            recorded={feedbackRecorded}
            correction={correction}
            onCorrection={setCorrection}
            onRate={(status, note) => void recordFeedback(status, note)}
            onContinue={() => void send('continue')}
            onRevoke={() => void send('revoke')}
            error={refusedAction && error ? error : ''}
          />
        )}
        {screen === 'find' && card && (
          <>
            <ProbeLog
              t={t}
              variant={variant}
              working={working}
              entry={card.entry}
              onRerun={() => void send('run_discovery')}
              error={refusalFor('run_discovery')}
            />
            <OpenQuestions t={t} questions={card.entry?.questions} />
          </>
        )}

        {(screen === 'paused' || screen === 'revoked' || screen === 'purged' || screen === 'status') &&
          card && (
            <NoticeScreen
              {...shared}
              card={card}
              onChoose={choose}
              error={refusedAction && error ? error : ''}
            />
          )}

        {screen === 'purge' && (
          <PurgeScreen
            {...shared}
            confirmation={purgeConfirmation}
            onConfirmation={setPurgeConfirmation}
            onSubmit={(event) => {
              event.preventDefault()
              void send('purge', { confirmation: purgeConfirmation })
            }}
            onCancel={() => { setPurgeArmed(false); setPurgeConfirmation('') }}
            error={refusalFor('purge')}
          />
        )}
      </div>

      {/* THE ONE LINE THAT SURVIVES EVERY SCREEN CHANGE, besides the rail. */}
      {screen !== 'loading' && screen !== 'unavailable' && <StandingLine t={t} />}

      <div aria-live="polite" className="mt-4 min-h-5 text-sm">
        {working && !scanning && <span className={t.muted}>The Cabinet is working on that…</span>}
        {/* THE SHARED LINE ALWAYS CARRIES THE REASON, even when a screen has
            already rendered it at the control. A refusal is never swallowed;
            the per-control copy is an addition, not a replacement. */}
        {error && <span className="font-medium text-red-500 dark:text-red-300">{error}</span>}
      </div>
    </section>
  )
}
