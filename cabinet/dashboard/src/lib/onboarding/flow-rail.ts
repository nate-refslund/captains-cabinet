/**
 * The progress rail — four stops, and it never goes backwards.
 *
 * WHAT IT REPLACED, AND WHY. The rail used to have six stops (You · Purpose ·
 * Start · Window · Charter · Result) and mapped `orientation_offered` back to
 * stop four while `dividend_ready` sat at stop six. So the operator's LAST act
 * — pressing continue on the result — visibly moved the rail two stops
 * BACKWARD. Measured live (Captain, 2026-08-14): "it is like it goes a step
 * back". A progress indicator that reverses is worse than none: it tells a
 * finished operator they have regressed, on the one screen whose whole job is
 * to say where they are. The pre-change mapping is kept in `flow-rail.test.ts`
 * as `LEGACY_PHASE_INDEX`, purely so the monotonic arm can be proven to fire
 * against the build that failed it.
 *
 * FOUR STOPS, because four is what actually happens: the operator answers
 * questions about themselves, grants a read, gets one result, and is done.
 * Purpose and Start were steps of the FIRST stop, not stops of their own, and
 * Window and Charter are two halves of granting the read.
 *
 * THIS MODULE IS PURE. It maps state to a position and nothing else — no
 * React, no fetch, no styling — so every law below is testable without a DOM.
 */
import type { WizardStepId } from './wizard'

export interface FlowStop {
  id: string
  /** What the operator sees. */
  label: string
  /** One line, for the title attribute and screen readers. */
  hint: string
}

/**
 * The four stops, in order. The index into this array IS the position, so the
 * order here is load-bearing and the monotonic law below is stated over it.
 */
export const FLOW_STOPS: readonly FlowStop[] = Object.freeze([
  Object.freeze({ id: 'you', label: 'You', hint: 'What you do' }),
  Object.freeze({ id: 'access', label: 'Access', hint: 'What I may read' }),
  Object.freeze({ id: 'first-look', label: 'First look', hint: 'One useful thing' }),
  Object.freeze({ id: 'done', label: 'Done', hint: 'Your Cabinet is ready' }),
])

/**
 * Every stage the core can put on a card, mapped to EXACTLY ONE stop.
 *
 * The registry is pinned against `journey.STAGES` in the core
 * (`flow-rail.test.ts`), which is itself pinned against the card builder's own
 * branches (`test_every_declared_stage_renders_its_own_card`). A stage the core
 * can render and this map has never heard of would land here as `-1` — the rail
 * would silently vanish rather than lie — but silence about a real stage is
 * still a screen nobody designed, so the test refuses it.
 */
export const STAGE_STOPS: Readonly<Record<string, number>> = Object.freeze({
  welcome: 0,
  charter_pending: 1,
  dividend_ready: 2,
  complete: 3,
  // The legacy terminal stage. `journey.COMPLETE_STAGES` reads it as complete
  // and renders the same arrival card, so it sits on the same stop — this is
  // the rail half of that one interpretation rule.
  orientation_offered: 3,
})

/**
 * The stages that are deliberately OFF the rail, each with the reason.
 *
 * A rail is a claim about forward progress. These three are not points on the
 * way anywhere: they are the operator stepping out of the flow, taking access
 * back, or deleting the record. Drawing them as a position would either invent
 * a stop that does not exist or freeze the rail on a stop the operator has
 * left. An exemption here is a claim about the stage, not a to-do — the test
 * refuses an empty or placeholder reason.
 */
export const OFF_RAIL: Readonly<Record<string, string>> = Object.freeze({
  paused: 'the operator stepped out of the flow; the rail would freeze on a stop they are no longer at',
  revoked: 'access was taken back, which is a control being used and not a step on the way to anything',
  purged: 'the record is gone, so there is no journey left to draw a position on',
})

/**
 * Which of the welcome stage's client steps belongs to which stop. The three
 * questions ARE the first stop; naming the folder and approving the Charter are
 * two halves of the second.
 */
const WELCOME_STEP_STOPS: Readonly<Record<WizardStepId, number>> = Object.freeze({
  role: 0,
  dream: 0,
  start: 0,
  window: 1,
  discover: 1,
})

/**
 * Where the operator is: an index into `FLOW_STOPS`, or -1 when the journey is
 * off the rail and the rail should hide rather than lie about progress.
 *
 * The client step only refines a position WITHIN the welcome stage — the server
 * stages own everything after it — so a stale step can never drag a later stage
 * backwards.
 */
export function stopIndex(stage: string, step: WizardStepId): number {
  if (stage === 'welcome') return WELCOME_STEP_STOPS[step] ?? 0
  const stop = STAGE_STOPS[stage]
  return stop === undefined ? -1 : stop
}

/**
 * The forward path a journey actually walks, as (stage, step) pairs in order.
 *
 * This is the sequence the monotonic law is stated over, and it is a claim
 * about the core's transitions: welcome's three questions, the branch step, the
 * Charter, the result, the arrival — plus the legacy tail a pre-2026-08-14
 * build wrote, which is where the reversal used to happen.
 */
export const FORWARD_PATH: readonly (readonly [string, WizardStepId])[] = Object.freeze([
  ['welcome', 'role'],
  ['welcome', 'dream'],
  ['welcome', 'start'],
  ['welcome', 'window'],
  ['charter_pending', 'window'],
  ['dividend_ready', 'window'],
  ['complete', 'window'],
  ['orientation_offered', 'window'],
] as const)

/**
 * The monotonic law, as a function so a test can run it against ANY mapping —
 * including the one this replaced, which is how the arm is proven able to fire.
 *
 * Returns the first reversal it finds, or null. A reversal is reported rather
 * than thrown so the test can assert on WHICH transition broke, not merely that
 * something did.
 */
export function firstReversal(
  index: (stage: string, step: WizardStepId) => number,
  path: readonly (readonly [string, WizardStepId])[] = FORWARD_PATH
): { from: string; to: string; fromStop: number; toStop: number } | null {
  let highest = -Infinity
  let previous = ''
  for (const [stage, step] of path) {
    const stop = index(stage, step)
    if (stop < 0) continue // off-rail stages carry no position to compare
    if (stop < highest) {
      return { from: previous, to: stage, fromStop: highest, toStop: stop }
    }
    highest = stop
    previous = stage
  }
  return null
}
