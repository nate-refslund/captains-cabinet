/**
 * The stepped first-run's logic, framework-free so it is PURE-testable.
 *
 * The Captain's ruling (2026-07-30): the one question "What do you do, and how
 * can I best serve you?" was three questions in a trench coat. This module owns
 * the three and the arc they open into — role, then the dream, then where to
 * begin — with no React in sight, so `wizard.test.ts` can drive every
 * transition and the no-value-lost rule without a DOM.
 *
 * It owns SEQUENCE and COMPOSITION only. It never fetches, never renders, and
 * never decides what the core will accept — the core still refuses a bare seed,
 * bounds every field, and drops an unknown preference. This is the surface's
 * map of the questions, not a second copy of the core's rules.
 */

/** The client-driven steps of the welcome front. `window`/`discover` are the
 *  two branches of the third question; both then hand off to a core action. */
export type WizardStepId = 'role' | 'dream' | 'start' | 'window' | 'discover'

/** What the three questions collect, before any of it crosses to the core. */
export interface WizardValues {
  /** Question one — what the operator does. Becomes the journey seed. */
  role: string
  /** Question two — the dream for the Cabinet. Becomes `mission.purpose`. */
  dream: string
  /** Question three — point me at a folder, or go find where I am useful. */
  startPreference: '' | 'point' | 'decide'
}

/**
 * The empty start, module-level and frozen so it has a STABLE identity — the
 * same reason the card's other empty starts are frozen: a fresh object per
 * render would defeat the hook-order assertions the tests script.
 */
export const EMPTY_WIZARD: Readonly<WizardValues> = Object.freeze({
  role: '',
  dream: '',
  startPreference: '',
})

/**
 * The arc, in order: three questions, then the first window, the Charter the
 * operator approves, and the one useful result. This IS a sequence — each phase
 * genuinely precedes the next — so a numbered rail encodes something true
 * rather than decorating the card. The rail reads these; nothing here styles.
 */
export interface WizardPhase {
  id: string
  label: string
  hint: string
}

export const WIZARD_PHASES: readonly WizardPhase[] = Object.freeze([
  { id: 'role', label: 'You', hint: 'What you do' },
  { id: 'dream', label: 'Purpose', hint: 'What this becomes' },
  { id: 'start', label: 'Start', hint: 'Where I begin' },
  { id: 'window', label: 'Window', hint: 'What I may read' },
  { id: 'charter', label: 'Charter', hint: 'You approve' },
  { id: 'result', label: 'Result', hint: 'One useful thing' },
])

/**
 * Which phase is lit, given the server stage and the client step. The welcome
 * stage maps to the three questions plus the window/discover branch; the server
 * stages own the rest. A stage off the linear arc (paused, revoked, purged)
 * returns -1, and the rail hides rather than lying about progress.
 */
export function activePhaseIndex(stage: string, step: WizardStepId): number {
  if (stage === 'welcome') {
    if (step === 'role') return 0
    if (step === 'dream') return 1
    if (step === 'start') return 2
    return 3 // window | discover — the first-window phase
  }
  if (stage === 'charter_pending') return 4
  if (stage === 'dividend_ready') return 5
  // Deeper orientation is another first-window ask, so it sits at the window
  // phase rather than off the rail.
  if (stage === 'orientation_offered') return 3
  return -1
}

/**
 * May the operator move on from this step? Role is required — it is the seed
 * the core refuses to do without. The dream is genuinely optional (a role-only
 * answer conditions the cabinet honestly, and pressing for a dream would teach
 * the operator this is an interview). The third question needs one of its two
 * answers chosen. Window and discover are terminal client steps.
 */
export function canAdvance(step: WizardStepId, values: WizardValues): boolean {
  if (step === 'role') return values.role.trim().length > 0
  if (step === 'dream') return true
  if (step === 'start') {
    return values.startPreference === 'point' || values.startPreference === 'decide'
  }
  return true
}

/**
 * The next step, or null when this step hands off to a core action (the window
 * form submits `propose_window`; the discover panel routes to a real source).
 * The third question branches: `decide` goes to self-exploration, everything
 * else to the folder.
 */
export function nextStep(step: WizardStepId, values: WizardValues): WizardStepId | null {
  if (step === 'role') return 'dream'
  if (step === 'dream') return 'start'
  if (step === 'start') return values.startPreference === 'decide' ? 'discover' : 'window'
  return null
}

/** The previous step, or null at the first one. Back never crosses a branch it
 *  cannot see — window and discover both return to the third question. */
export function prevStep(step: WizardStepId): WizardStepId | null {
  if (step === 'dream') return 'role'
  if (step === 'start') return 'dream'
  if (step === 'window' || step === 'discover') return 'start'
  return null
}

/**
 * The `answer_seed` payload for the three answers, or null when they are not yet
 * complete enough to send (no role, or no branch chosen). Role becomes the seed;
 * a stated dream becomes `purpose` (the core stores it under `mission.purpose`);
 * an unstated dream is omitted rather than sent blank, so the core writes no
 * mission the operator never gave.
 */
export function seedRequest(values: WizardValues): {
  seed: string
  purpose?: string
  start_preference: 'point' | 'decide'
} | null {
  const seed = values.role.trim()
  if (!seed) return null
  if (values.startPreference !== 'point' && values.startPreference !== 'decide') return null
  const dream = values.dream.trim()
  return {
    seed,
    ...(dream ? { purpose: dream } : {}),
    start_preference: values.startPreference,
  }
}

/**
 * Where to resume the front when a journey already carries answers — a reload
 * mid-flow should land on the branch step with the questions behind it, not back
 * at question one. A journey with no seed yet resumes at the first question.
 */
export function resumeStep(seedAnswered: boolean, preference: string | undefined): WizardStepId {
  if (!seedAnswered) return 'role'
  return preference === 'decide' ? 'discover' : 'window'
}
