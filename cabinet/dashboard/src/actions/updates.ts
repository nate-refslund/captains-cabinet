'use server'

/**
 * Server actions for the update path — the Captain's Apply / Roll back, from
 * the home card, with no terminal in the loop.
 *
 * TWO PROPERTIES THIS FILE EXISTS TO HOLD.
 *
 * 1. `verifySession()` UNCONDITIONALLY. Every other mutating action in this
 *    dashboard guards with `requireDashboardAuth()`, which returns TRUE under
 *    the no-auth posture (`DASHBOARD_NO_AUTH=true`, or a dev build with no
 *    password set). That posture exists so a half-provisioned box can still be
 *    driven — a reasonable trade for reading a page. It is not a reasonable
 *    trade for replacing the bytes of the running Cabinet from an unauthenticated
 *    POST, and a server action is a global action-ID endpoint that middleware
 *    never covers. So this file calls the session check itself and takes no
 *    waiver.
 *
 * 2. A DETACHED LAUNCH, never a blocking exec. The updater restarts the
 *    dashboard, which is the process serving this action. Awaiting it would
 *    mean awaiting one's own death; the CLI is the thing that reports, through
 *    `.updates/state.json`, which the card reads back.
 *
 * The id is validated before it goes anywhere, and the seam takes an argv
 * array — no shell string is ever composed here.
 */

import { verifySession } from '@/lib/auth'
import { BUNDLE_SHA_RE, SNAPSHOT_STAMP_RE, spawnUpdater } from '@/lib/updates'
import { revalidatePath } from 'next/cache'

export interface UpdateActionResult {
  ok: boolean
  error?: string
}

/** Take the bundle with this source commit. Returns as soon as it is launched. */
export async function applyUpdate(sha: string): Promise<UpdateActionResult> {
  if (!(await verifySession())) return { ok: false, error: 'unauthorized' }
  if (typeof sha !== 'string' || !BUNDLE_SHA_RE.test(sha)) {
    return { ok: false, error: 'invalid bundle id' }
  }
  try {
    spawnUpdater(['apply', '--bundle', sha, '--from', 'web'])
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'apply failed to start' }
  }
  revalidatePath('/')
  return { ok: true }
}

/** Put the previous bytes back — the newest snapshot, or a named one. */
export async function rollbackUpdate(stamp?: string): Promise<UpdateActionResult> {
  if (!(await verifySession())) return { ok: false, error: 'unauthorized' }
  const args = ['rollback', '--from', 'web']
  if (stamp !== undefined && stamp !== '') {
    if (typeof stamp !== 'string' || !SNAPSHOT_STAMP_RE.test(stamp)) {
      return { ok: false, error: 'invalid snapshot stamp' }
    }
    args.push('--to', stamp)
  }
  try {
    spawnUpdater(args)
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'rollback failed to start' }
  }
  revalidatePath('/')
  return { ok: true }
}
