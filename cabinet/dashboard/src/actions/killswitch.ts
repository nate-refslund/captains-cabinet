'use server'

import redis, { isMockRedis, storeReading } from '@/lib/redis'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import { revalidatePath } from 'next/cache'

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
    if (isActive) {
      await redis.del('cabinet:killswitch')
    } else {
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
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error:
        err instanceof Error ? err.message : 'Failed to toggle kill switch',
    }
  }
}
