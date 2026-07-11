'use server'

import redis from '@/lib/redis'
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
 */
export async function toggleKillSwitch(intent?: 'activate' | 'deactivate') {
  if (!(await requireDashboardAuth())) {
    return { success: false, error: 'Unauthorized' }
  }
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
    if (isActive) {
      await redis.del('cabinet:killswitch')
    } else {
      await redis.set('cabinet:killswitch', 'active')
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
