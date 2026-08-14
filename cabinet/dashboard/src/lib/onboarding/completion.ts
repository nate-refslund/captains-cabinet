/** The only two fields the predicate reads. */
export interface CompletableJourney {
  charter?: { status?: string } | null
  first_dividend?: unknown
}

/**
 * Has this journey DELIVERED what onboarding promises — a first cited result
 * under a Charter the operator approved?
 *
 * THE ONE COMPLETION PREDICATE, and the reason it is exported as a pure
 * function rather than living inside the file read below: two surfaces gate on
 * it and they must never disagree. The home page redirects an unfinished
 * operator into /onboarding; the arrival screen announces "Your Cabinet is
 * ready". Two copies of "is it done?" would eventually answer differently, and
 * the operator would be told both.
 *
 * It reads the onboarding core's OWN durable record, not a flag invented here.
 * `framework/onboarding/journey.py` persists the journey to
 * instance/onboarding/v2/state.json, and the `ratify_charter` action is the
 * moment onboarding delivers its promise: it stamps
 *   charter.status   = "ratified"
 *   first_dividend    = <the one cited useful result>
 * (journey.py `_act_core`). Both present is the honest "done" signal.
 *
 * Everything else is NOT complete, and the honest default is to send the
 * operator to /onboarding:
 *   - no state.json at all           → onboarding never started;
 *   - stage charter_pending          → charter proposed, not yet ratified;
 *   - purged / paused before the read → no ratified charter, no dividend;
 *   - an unreadable/blank state       → we cannot prove completion, so we don't.
 *
 * A REVOKED journey that had already arrived stays complete, and that is
 * deliberate: taking access back stops future reads, it does not erase the
 * Charter that was approved or the result that was given. Bouncing an operator
 * into the wizard for exercising a control would punish them for using it.
 * What stops the ARRIVAL SCREEN rendering there is the card's kind, not this.
 *
 * The core mirrors this predicate as `journey_has_arrived`. Both are asserted
 * against the shared table in
 * framework/onboarding/tests/data/completion-parity.json, so neither can drift
 * alone.
 */
export function journeyIsComplete(state: CompletableJourney | null | undefined): boolean {
  return state?.charter?.status === 'ratified' && state.first_dividend != null
}
