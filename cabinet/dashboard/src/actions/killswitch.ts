'use server'

import { execFile } from 'node:child_process'
import path from 'node:path'
import { promisify } from 'node:util'

import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

const run = promisify(execFile)

/**
 * WHO PULLED IT, added 2026-08-26.
 *
 * `cabinet/scripts/kill-switch.sh` exists partly to leave a ledger row naming
 * the actor -- its own header records an incident where the switch read
 * INACTIVE and no record could say who cleared it. The dashboard never called
 * it. It wrote the key directly, so a Captain hitting Stop All halted the
 * fleet and left no row saying it was him.
 *
 * The arm now goes through the script. Deliberately argv-only: `execFile`
 * with an array, never a shell string, so nothing in the environment can be
 * read as a command on the one surface where being wrong costs the most.
 *
 * The direct write survives as the FALLBACK, not the path. Some deployments
 * have no script to run (a container built from the app alone), and refusing
 * to halt a fleet because the audit trail is unavailable would be the wrong
 * trade on an emergency stop: stopping matters more than knowing who stopped
 * it. When that happens the caller is told, in the return value, that the halt
 * landed unattributed -- an unrecorded stop is not the same event as a
 * recorded one and the surface must not present them as one.
 *
 * A script that RUNS AND FAILS is the opposite case and is fatal. It reached
 * the machinery and the machinery said no; writing the key behind its back
 * would be overriding the very check that just refused.
 */
const KILL_SWITCH_ACTOR = 'captain-dashboard'

type ArmOutcome =
  | { armed: true; attributed: true }
  | { armed: true; attributed: false; why: string }
  | { armed: false; error: string }

async function armThroughLedger(): Promise<ArmOutcome> {
  const root =
    process.env.CABINET_ROOT ?? path.resolve(process.cwd(), '..', '..')
  const script = path.join(root, 'cabinet', 'scripts', 'kill-switch.sh')
  try {
    await run('bash', [script, 'activate'], {
      env: { ...process.env, CABINET_OFFICER: KILL_SWITCH_ACTOR },
      timeout: 30_000,
    })
    return { armed: true, attributed: true }
  } catch (err) {
    const code = (err as NodeJS.ErrnoException)?.code
    if (code === 'ENOENT') {
      // No script to run here. The halt still happens; it just goes
      // unrecorded, and the caller is told so rather than shown a plain
      // success.
      return {
        armed: true,
        attributed: false,
        why: 'no ledger script on this deployment',
      }
    }
    return {
      armed: false,
      error:
        err instanceof Error
          ? `the emergency stop script refused: ${err.message}`
          : 'the emergency stop script refused',
    }
  }
}

/**
 * Toggle (or intent-pin) the fleet killswitch.
 *
 * `intent` (optional, additive — T3 world lever, Captain ruling 2026-07-09:
 * the lever is the ONE in-world actuator and reuses THIS existing write):
 * when given, the action becomes idempotent toward that end-state, so a
 * caller rendering stale state can never invert the Captain's intent.
 * Legacy no-arg callers keep exact toggle semantics.
 *
 * READ-BACK, added 2026-07-31. This returned `{ success: true }` from HAVING
 * ISSUED the command — the exact defect `cabinet/scripts/kill-switch.sh` was
 * written against ("an emergency surface must never report success it cannot
 * prove"; that script rc-checks the SET *and* reads it back through the
 * nonce-sandwiched shared reader, and prints ACTIVATION FAILED otherwise). The
 * dashboard's own write had neither, so a Captain who tapped Stop All saw a
 * confirmed-looking pill whether or not the fleet was ever halted.
 *
 * The read-back below is weaker than the shell's — ioredis is one client
 * against one endpoint, with no second filesystem channel — but it closes the
 * gap that matters here: the write is verified to have LANDED in the store this
 * process talks to before the surface is allowed to claim it did.
 *
 * WHAT THE READ-BACK COULD NOT REACH, closed 2026-07-31. A read-back cannot see
 * a write that never left the process. With no `REDIS_URL` the client is an
 * in-process object (`lib/redis.ts:emptyStore`), so `set` then `get` returns
 * exactly what was just written and the proof above PASSES over a fleet this
 * dashboard has never contacted — the emergency stop reporting a halt it did
 * not achieve, on a posture that (unlike `demo`) is reachable on a production
 * deploy that simply forgot the store. `actions/crons.ts` closed this for its
 * timers and named this file as still carrying it; `actions/officers.ts` closed
 * it for the fleet. This is the same gate, in the same words, on the surface
 * where being wrong costs the most.
 *
 * The gate is BEFORE the pre-read, not after: `redis.get` against the empty
 * store answers `null`, which the code below would read as "not currently
 * engaged" and then act on.
 */
const notLiveRefusal = (): { success: false; error: string } | null =>
  isMockRedis
    ? {
        success: false,
        error: `this dashboard is not connected to a cabinet, so the emergency stop was NOT changed and the fleet was not halted — ${storeReading.source}`,
      }
    : null

export async function toggleKillSwitch(intent?: 'activate' | 'deactivate') {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
  const notLive = notLiveRefusal()
  if (notLive) return notLive
  try {
    const current = await redis.get('cabinet:killswitch')
    const isActive = current === 'active'
    if (intent === 'activate' && isActive) {
      revalidatePath('/')
      return { success: true } // already the intended state — no-op
    }
    if (intent === 'deactivate' && !isActive) {
      revalidatePath('/')
      return { success: true } // already the intended state — no-op
    }
    const wanted = isActive ? 'clear' : 'active'
    let unattributed = ''
    if (isActive) {
      // The clear direction stays a direct write. Converging it onto the
      // script would put a second authority over the same state, and the
      // ratified rule is that there is one law -- see the receipt behind this
      // change. Only the ARM gained a ledger row here.
      await redis.del('cabinet:killswitch')
    } else {
      const outcome = await armThroughLedger()
      if (!outcome.armed) {
        // Reached the machinery and it refused. Writing the key behind its
        // back would override the check that just said no.
        return { success: false, error: outcome.error }
      }
      if (!outcome.attributed) {
        unattributed = outcome.why
      }
      // Either the script already set it, or there is no script here. The
      // write is idempotent and the read-back below is what proves the halt
      // either way.
      await redis.set('cabinet:killswitch', 'active')
    }
    // Prove it. A store that accepted the command and did not keep it, a
    // read-only replica, an eviction, a competing writer — all of them used to
    // come back as success.
    const after = await redis.get('cabinet:killswitch')
    const landed = wanted === 'active' ? after === 'active' : after === null
    if (!landed) {
      return {
        success: false,
        error: `the kill switch did not take: after writing "${wanted}" the store still reads ${
          after === null ? '(absent)' : JSON.stringify(after)
        }`,
      }
    }
    revalidatePath('/')
    if (unattributed) {
      // Halted, and the record does not name who did it. Said out loud rather
      // than folded into a plain success: an unrecorded stop is a different
      // event from a recorded one.
      return {
        success: true,
        unattributed: `the fleet is halted, but nothing recorded who did it — ${unattributed}`,
      }
    }
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error:
        err instanceof Error ? err.message : 'Failed to toggle kill switch',
    }
  }
}
