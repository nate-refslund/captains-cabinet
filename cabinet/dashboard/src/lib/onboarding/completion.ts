import { readFile } from 'node:fs/promises'
import { cabinetPath } from '@/lib/cabinet-root'
import { journeyIsComplete } from './wizard'

/**
 * Has the operator FINISHED onboarding — received their first cited result
 * under a ratified Charter?
 *
 * This reads the onboarding core's OWN durable record, not a flag invented
 * here. `framework/onboarding/journey.py` persists the journey to
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
 *   - a purged / paused / revoked     → fresh or halted state carries no
 *     ratified charter and no dividend;
 *   - an unreadable/blank state       → we cannot prove completion, so we don't.
 *
 * A false read here costs one redirect an operator can navigate out of; the
 * opposite default — dropping a not-yet-oriented operator on a confusing home —
 * is the exact bug this fixes, so uncertainty resolves to "not complete".
 *
 * `ONBOARDING_STATE_PATH` overrides the location (tests; alternate layouts).
 */
export async function isOnboardingComplete(): Promise<boolean> {
  const statePath =
    process.env.ONBOARDING_STATE_PATH || cabinetPath('instance/onboarding/v2/state.json')

  let raw: string
  try {
    raw = await readFile(statePath, 'utf8')
  } catch {
    return false // no journey state on disk → onboarding has not run
  }

  try {
    // The predicate itself lives in `./wizard` — framework-free, so the
    // onboarding CARD can import it too. A router that has stopped redirecting
    // and a page that still says "not started" is the stuck state this shares
    // one rule to prevent.
    return journeyIsComplete(JSON.parse(raw))
  } catch {
    return false // unreadable state → cannot prove completion
  }
}
