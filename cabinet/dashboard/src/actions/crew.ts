'use server'

/**
 * WAKE YOUR CABINET — and put it back to sleep from the same screen.
 *
 * WHAT THIS IS. The hatch stops short of launchd on purpose, so a freshly
 * hatched cabinet has officers that have never run. Until now the only way to
 * start them was a terminal command in a runbook, and the home page said
 * "offline" in red about the gap. This is that command, as one consent-first
 * action the operator takes from the page they are already looking at.
 *
 * WHAT IT WILL NOT DO, and why each refusal is here rather than in the UI —
 * the UI can be bypassed, a Server Action is a POST endpoint:
 *   - UNAUTHENTICATED callers get nothing. Action dispatch is not covered by
 *     middleware (see `actions/env.ts`), so the guard is per-action.
 *   - ONBOARDING INCOMPLETE gets nothing. Starting background agents for an
 *     operator who has not ratified a charter is starting work nobody
 *     authorised; the same signal that guards the home page guards this.
 *   - A DASHBOARD WITH NO STORE gets nothing. The whole promise is that the
 *     officer's state flips in front of you; a wake this process cannot then
 *     observe is a dead end, and writing the expectation marker into an
 *     in-process object would be the "it says stopped over a running agent"
 *     defect in reverse.
 *   - AN EMPTY ROSTER gets nothing, loudly. Guessing a fleet is the
 *     wrong-fleet-deploy failure `deploy-mac.sh` refuses for the same reason.
 *
 * WHAT IT CAN RUN is two argv shapes, and only two — see `lib/crew-ops.ts`.
 * Nothing from the request reaches a command line: the officer ids come from
 * this deployment's own `roster.yml` and are re-validated at the door.
 *
 * IDEMPOTENT BY REUSE. `deploy-mac.sh --officer` boots the label out before it
 * bootstraps, so pressing wake twice is a redeploy, never a double-start;
 * `--stop` on an already-stopped agent is a success, because the post-state is
 * the same either way. Neither needs a lock here, and a lock here would be a
 * second, weaker copy of a guarantee the script already gives.
 */

import { revalidatePath } from 'next/cache'
import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
// The disk read moved out of `completion.ts` while this branch was in flight:
// that module is now the PURE predicate, because the arrival screen is a client
// component and gating it on a module that imports node:fs/promises 500'd
// /onboarding for every operator. Server callers take the state-file half.
import { isOnboardingComplete } from '@/lib/onboarding/completion-state-file'
import { readRoster } from '@/lib/crew-roster'
import { officerNameSources } from '@/lib/crew-roster'
import { officerTitle } from '@/lib/officer-title'
import { CrewOpRefused, runCrewOp, type CrewOp } from '@/lib/crew-ops'
import { STOP_REQUESTED_KEY } from '@/lib/crew-state'
import type { CrewOpOutcome, CrewStep } from '@/lib/crew'

function refusal(message: string): CrewOpOutcome {
  return { ok: false, message, steps: [] }
}

/**
 * Everything that must be true before a single command runs. Returns the
 * officer ids to act on, or the sentence explaining why nothing will happen.
 */
async function preflight(): Promise<{ slugs: string[] } | { refused: CrewOpOutcome }> {
  if (!(await requireDashboardAuth())) {
    return { refused: refusal('Unauthorized') }
  }
  if (!(await isOnboardingComplete())) {
    return {
      refused: refusal(
        'Your Cabinet is still being set up — finish setting it up first, then you can wake it.'
      ),
    }
  }
  if (isMockRedis) {
    return {
      refused: refusal(
        `This dashboard is not connected to a cabinet, so nothing was started — ${storeReading.source}.`
      ),
    }
  }
  const slugs = readRoster()
    .filter((m) => !m.onDemand)
    .map((m) => m.slug)
  if (slugs.length === 0) {
    return {
      refused: refusal(
        'This cabinet has no crew on its roster yet, so there is nobody to wake.'
      ),
    }
  }
  return { slugs }
}

async function runAcross(op: CrewOp, slugs: string[]): Promise<CrewStep[]> {
  const names = officerNameSources()
  const steps: CrewStep[] = []
  for (const slug of slugs) {
    const name = officerTitle(slug, names)
    const label =
      op === 'wake'
        ? `Starting ${name} in the background`
        : `Putting ${name} to sleep`
    try {
      const result = await runCrewOp(op, slug)
      steps.push({ id: `${op}:${slug}`, label, ok: result.ok, detail: result.detail })
    } catch (err) {
      steps.push({
        id: `${op}:${slug}`,
        label,
        ok: false,
        detail: err instanceof CrewOpRefused ? err.message : 'it did not run',
      })
    }
  }
  return steps
}

/**
 * Start every always-on officer on this Mac.
 *
 * The expectation marker is written ONLY for officers whose command actually
 * succeeded. Marking a failed one `active` would tell the supervisor — and the
 * card — that an officer nobody started is expected to be running, which is
 * the alarm this whole change exists to stop inventing.
 */
export async function wakeCrew(): Promise<CrewOpOutcome> {
  const pre = await preflight()
  if ('refused' in pre) return pre.refused

  const steps = await runAcross('wake', pre.slugs)
  const started = steps.filter((s) => s.ok)

  for (const step of started) {
    const slug = step.id.slice('wake:'.length)
    try {
      await redis.set(`cabinet:officer:expected:${slug}`, 'active')
      // The stop time is about the LAST sleep and must not outlive it: left
      // behind, it would make the next sleep's leftover-vs-still-running
      // comparison read against an hour-old instant.
      await redis.del(STOP_REQUESTED_KEY(slug))
    } catch {
      // The command ran; the marker is a hint for the supervisor, not the act.
      // A store that refused the write does not un-start an officer.
    }
  }

  revalidatePath('/')
  revalidatePath('/officers')

  if (started.length === steps.length) {
    return {
      ok: true,
      message:
        started.length === 1
          ? 'Your Cabinet is waking up. It takes a minute or two before the first sign of life.'
          : `All ${started.length} of your crew are waking up. It takes a minute or two before the first sign of life.`,
      steps,
    }
  }
  if (started.length === 0) {
    return {
      ok: false,
      message: 'Nothing started. Nothing on your Mac was changed — you can try again.',
      steps,
    }
  }
  return {
    ok: false,
    message: `${started.length} of ${steps.length} started. The rest can be tried again.`,
    steps,
  }
}

/**
 * Stop every always-on officer. The reverse of `wakeCrew`, from the same
 * screen, using the same script — because an action you cannot undo where you
 * took it is not one an operator should be asked to take.
 *
 * `--stop` leaves the plist file on disk deliberately, so the expectation
 * marker is what tells the card this quiet is DELIBERATE. Without the marker a
 * slept officer would render as the alarm state, and the sleep button would
 * look like it broke something.
 */
export async function sleepCrew(): Promise<CrewOpOutcome> {
  const pre = await preflight()
  if ('refused' in pre) return pre.refused

  // The marker goes down FIRST. If a bootout succeeds and the marker write
  // never happens, the card alarms about an officer the operator deliberately
  // stopped; the opposite order is only ever wrong for the seconds between.
  const stopRequestedAt = new Date().toISOString()
  for (const slug of pre.slugs) {
    try {
      await redis.set(`cabinet:officer:expected:${slug}`, 'stopped')
      // WHEN, not just THAT. The heartbeat outlives a successful stop by up to
      // its 900s TTL, and without this instant the card cannot tell that
      // leftover beat from an officer that ignored the stop — it showed
      // "First Mate is planning your first week" directly above "Your crew is
      // asleep" until this landed.
      await redis.set(STOP_REQUESTED_KEY(slug), stopRequestedAt)
    } catch {
      // Same reasoning as the wake side: the marker is a hint, not the act.
    }
  }

  const steps = await runAcross('sleep', pre.slugs)
  const stopped = steps.filter((s) => s.ok)

  revalidatePath('/')
  revalidatePath('/officers')

  if (stopped.length === steps.length) {
    return {
      ok: true,
      message: 'Your crew is asleep. Nothing runs in the background until you wake them again.',
      steps,
    }
  }
  return {
    ok: false,
    message: `${stopped.length} of ${steps.length} stopped. The rest are still running.`,
    steps,
  }
}
