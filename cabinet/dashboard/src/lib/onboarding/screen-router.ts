/**
 * The screen router — one state in, exactly one screen out.
 *
 * WHAT IT REPLACED, AND WHY. Onboarding was a single ~2,000-line card whose
 * panels appeared by ADDITIVE predicates: a panel opened when its data existed
 * and then never left, so by the end of a connected run the operator was
 * reading a sweep table, an identity picker, a ranked question, a discovery log,
 * a residual-questions list, a receipt and a row of eight buttons on one page.
 * Measured live (Captain, 2026-08-14): "this is way too much text", and then —
 * on a journey that was objectively finished — "i believe i've answered
 * everything and am now stuck and can't continue again?". A state inspector,
 * not a journey.
 *
 * SCREENS REPLACE EACH OTHER. One screen is one idea with one primary action;
 * nothing from the previous screen survives except the four-stop rail and the
 * standing read-only line. That is only safe if "which screen?" is a decidable
 * question with exactly one answer for every state the core can produce — so it
 * is THIS module, pure, with no React, no fetch and no styling, and every law
 * below is testable without a DOM.
 *
 * THE ORDER OF THE RULES IS THE DESIGN. Reading `screenFor` top to bottom is
 * reading the precedence: a destructive confirmation outranks everything, a
 * scan in flight outranks the stage it is about to change, an explicit
 * management act outranks the flow, and only then does the journey's own state
 * decide. Precedence stated as code beats precedence emerging from a pile of
 * `&&`-ed booleans, which is exactly what this replaces.
 */
import type { WizardStepId } from './wizard'

/**
 * Every screen the operator can be on. Nine of them are the ruling's flow
 * (welcome → you → dream → begin → folder | connect → approve → look → find →
 * arrival); the three asks are EARNED screens that exist only while unanswered;
 * the rest are the ways out and the two states that are not a journey at all.
 */
export type ScreenId =
  | 'loading'
  | 'unavailable'
  | 'welcome'
  | 'you'
  | 'dream'
  | 'begin'
  | 'connect'
  | 'sweep'
  | 'identity'
  | 'salience'
  | 'organization'
  | 'folder'
  | 'approve'
  | 'look'
  | 'find'
  | 'arrival'
  | 'paused'
  | 'revoked'
  | 'purged'
  | 'status'
  | 'purge'

/** The three questions that are asked only when they have not been answered. */
export const ASK_SCREENS = ['identity', 'salience', 'organization'] as const
export type AskId = (typeof ASK_SCREENS)[number]

/**
 * Which asks are still open. Derived from what the CORE offers plus what the
 * committed state records — never from what this session happens to have sent,
 * so a reload cannot re-ask a question the operator has already answered.
 */
export interface OpenAsks {
  identity: boolean
  salience: boolean
  organization: boolean
}

export const NO_ASKS: Readonly<OpenAsks> = Object.freeze({
  identity: false,
  salience: false,
  organization: false,
})

export interface RouteInput {
  /** The card is still being fetched. */
  loading: boolean
  /** The core's stage, or '' when there is no journey to route. */
  stage: string
  /** The card kind — `arrival` is the core saying the journey ended. */
  kind: string
  /**
   * Has the journey actually DELIVERED what onboarding promises? Separate from
   * the stage on purpose, and both are required: the stage says where the
   * operator navigated to, this says what they were given. See
   * `completion.ts` — a state that claims the stage without carrying the facts
   * must not be able to render a success screen with nothing behind it.
   */
  arrived: boolean
  /** Where the operator is inside the welcome stage. */
  step: WizardStepId
  /** The operator has left the connect step and asked for the look. */
  explored: boolean
  /** Which questions are still open. */
  asks: OpenAsks
  /** Asks the operator chose to leave for later, this session. */
  skipped: readonly string[]
  /**
   * An ask whose answer the core just REFUSED. It re-opens that question, so
   * the reason lands on the control that produced it rather than on whichever
   * screen the flow would otherwise have moved to.
   */
  refusedAsk: AskId | null
  /** A management act with a form of its own is holding the screen. */
  editScope: boolean
  /** The typed destructive confirmation is armed. */
  purgeArmed: boolean
  /** The first read is running right now. */
  scanning: boolean
  /** The operator asked a finished journey for its remaining questions. */
  fullSurface: boolean
}

/**
 * The first ask still open and not skipped, in the order they unblock the rest:
 * who the operator is bounds every claim about whose work this is, the target
 * bounds where depth goes, and whose work it is bounds the reading of both.
 */
export function firstOpenAsk(
  asks: OpenAsks,
  skipped: readonly string[] = []
): AskId | null {
  for (const ask of ASK_SCREENS) {
    if (asks[ask] && !skipped.includes(ask)) return ask
  }
  return null
}

/**
 * Which client step of the welcome stage maps to which screen. `discover` is
 * the branch that connects tools, and it holds three positions — the catalog,
 * the earned asks the look produced, and the look's own result — because they
 * are one arc and the operator walks it forward.
 */
function welcomeScreen(input: RouteInput): ScreenId {
  if (input.step === 'window') return 'folder'
  if (input.step === 'discover') {
    if (!input.explored) return 'connect'
    const ask = firstOpenAsk(input.asks, input.skipped)
    if (ask) return ask
    return 'sweep'
  }
  if (input.step === 'dream') return 'dream'
  if (input.step === 'start') return 'begin'
  if (input.step === 'role') return 'you'
  return 'welcome'
}

/**
 * THE ONE MAPPING. Every state the core can produce lands on exactly one
 * screen; a stage this module has never heard of lands on `status`, which is
 * the honest "I do not have a screen for this" rather than a blank page.
 */
export function screenFor(input: RouteInput): ScreenId {
  // A destructive confirmation is not a step of anything — while it is armed it
  // IS the screen, whatever the journey underneath is doing.
  if (input.purgeArmed) return 'purge'
  // The scan outranks the stage it is about to change: the operator pressed
  // approve, the read is running, and the card they would otherwise see is the
  // one they just left. Flowing straight into the result is the point.
  if (input.scanning) return 'look'
  if (!input.stage) return input.loading ? 'loading' : 'unavailable'
  // Changing what may be read is a management act with its own form, reachable
  // from a finished journey as well as from the flow.
  if (input.editScope) return 'folder'

  switch (input.stage) {
    case 'purged':
      return 'purged'
    case 'paused':
      return 'paused'
    case 'revoked':
      return 'revoked'
    case 'charter_pending':
      return 'approve'
    case 'dividend_ready':
      return 'find'
    case 'welcome':
      return input.refusedAsk ?? welcomeScreen(input)
    case 'complete':
    case 'orientation_offered': {
      // THE ENDING, and the two conditions are deliberately separate — see
      // `arrived`. A finished operator coming back gets the management view,
      // never the wizard; asking for the remaining questions opens them one at
      // a time and hands the screen back when they run out.
      if (!input.arrived || input.kind !== 'arrival') return 'status'
      if (!input.fullSurface) return 'arrival'
      // SKIPS DO NOT APPLY HERE. Asking a finished journey for its remaining
      // questions IS the operator un-skipping them: the arrival's own link says
      // "I still have N questions for you", and honouring an earlier skip would
      // make that link route straight back to the screen it was clicked from —
      // a dead end reachable in two taps.
      return input.refusedAsk ?? firstOpenAsk(input.asks) ?? 'arrival'
    }
    default:
      return 'status'
  }
}

/**
 * Where a returning operator resumes — the answer to "I closed the tab
 * mid-flow". It is `screenFor` with the client-side step DERIVED from what the
 * core already holds rather than from a step this session never had, so the
 * resume is a function of the record and not of a memory nothing persists.
 */
export function resumeInput(
  base: Omit<RouteInput, 'step' | 'explored'>,
  record: { seedAnswered: boolean; preference: string | undefined; swept: boolean }
): RouteInput {
  const step: WizardStepId = !record.seedAnswered
    ? 'welcome'
    : record.preference === 'decide'
      ? 'discover'
      : 'window'
  // A sweep on the record means the look already happened, so the connect
  // catalog is behind them: resuming into it would ask them to connect a tool
  // they have already connected and read.
  return { ...base, step, explored: record.swept }
}

/**
 * The screens that are a step of the flow rather than a state of it. Used by
 * the rail (a progress indicator on a revoked journey is a lie) and by the
 * transition, which animates movement and not arrival at a notice.
 */
export const FLOW_SCREENS: readonly ScreenId[] = Object.freeze([
  'welcome', 'you', 'dream', 'begin', 'connect', 'sweep',
  'identity', 'salience', 'organization', 'folder', 'approve', 'look', 'find',
])
