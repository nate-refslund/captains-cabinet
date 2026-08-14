/**
 * The completion question, asked of the journey state ON DISK — server only.
 *
 * SPLIT FROM `completion.ts` (2026-08-14), and the split is load-bearing rather
 * than tidy. The arrival screen is a CLIENT component and gates on the same
 * predicate the home-page redirect uses; when that predicate lived in the same
 * module as this file's `node:fs/promises` import, the browser bundle pulled a
 * Node-only module in and the whole /onboarding route 500'd. Neither `tsc` nor
 * the unit suite could see it — both run in Node, where the import is fine — so
 * the pure half now lives in a module with no Node imports at all, and
 * `completion.test.ts` greps for their absence.
 */
import { readFile } from 'node:fs/promises'
import { cabinetPath } from '@/lib/cabinet-root'
import { journeyIsComplete, type CompletableJourney } from './completion'

/**
 * The same question, asked of the journey state on disk.
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
    return journeyIsComplete(JSON.parse(raw) as CompletableJourney)
  } catch {
    return false // unreadable state → cannot prove completion
  }
}
