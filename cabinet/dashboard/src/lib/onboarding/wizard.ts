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
  /**
   * Question one's OPENING LINE — what the operator is called (Captain,
   * 2026-08-14: "if the very first question is 'What is your name?' then it may
   * more intelligently guess the user account across the tools"). Optional: a
   * cabinet that refuses to start without a name is an interview. Given, it
   * lands under `captain.name` and turns "which of these thirty accounts is
   * you?" into one confirm chip per tool.
   */
  name: string
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
  name: '',
  role: '',
  dream: '',
  startPreference: '',
})

/**
 * THE RAIL MOVED OUT OF THIS MODULE (2026-08-14). `WIZARD_PHASES` and
 * `activePhaseIndex` used to live here: six phases, and a mapping that sent the
 * stage AFTER the first result back to phase four, so an operator's last act
 * visibly moved the rail two stops backward. The rail spans the whole flow
 * including its ending, which is not this module's subject — it owns the
 * stepped FRONT — so it now lives in `./flow-rail.ts` as four stops with a
 * monotonic law that is tested, and the mapping it replaced is kept in
 * `flow-rail.test.ts` purely so that law can be proven to fire against it.
 */

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
  name?: string
  purpose?: string
  start_preference: 'point' | 'decide'
} | null {
  const seed = values.role.trim()
  if (!seed) return null
  if (values.startPreference !== 'point' && values.startPreference !== 'decide') return null
  const dream = values.dream.trim()
  // An unstated name is OMITTED, not sent blank — the same rule the dream
  // follows, and for the same reason: the core would otherwise record a
  // `captain.name` the operator never gave, over whatever the generator's
  // defaults lane already wrote there.
  const name = values.name.trim()
  return {
    seed,
    ...(name ? { name } : {}),
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
