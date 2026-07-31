/**
 * Spec 034 — Route guards for the Provisioning API
 *
 * Provides:
 *  - featureFlagCheck() — returns 503 if provisioning is disabled
 *  - authCheck() — returns 401 if no valid session
 *
 * Every mutating provisioning route calls both before doing any work.
 */

import { NextResponse } from 'next/server'
import { verifySession } from '@/lib/auth'
import { getDashboardConfig } from '@/lib/config'
import { isNoAuthPosture } from '@/lib/auth-posture'

/** Session user context extracted from cookie */
export interface SessionUser {
  /** Opaque token value used as actor ID in audit events */
  token: string
}

/**
 * Check if the CABINETS_PROVISIONING_ENABLED feature flag is active.
 * Returns a 503 Response if disabled, or null if enabled.
 *
 * Flag logic (per PR 1 plan):
 *   If consumer_mode_enabled === false AND env var not set → disabled.
 *   If either is true → enabled.
 */
export function featureFlagCheck(): NextResponse | null {
  const dashConfig = getDashboardConfig()
  const envEnabled = process.env.CABINETS_PROVISIONING_ENABLED === 'true'

  if (!dashConfig.consumerModeEnabled && !envEnabled) {
    return NextResponse.json(
      { ok: false, disabled: true, message: 'Cabinet provisioning not configured' },
      { status: 503 }
    )
  }
  return null
}

/**
 * Check that the request has a valid session cookie.
 * Returns a 401 Response if not authenticated, or null + session user if OK.
 */
export async function authCheck(): Promise<{ response: NextResponse; user: null } | { response: null; user: SessionUser }> {
  const valid = await verifySession()
  if (!valid) {
    return {
      response: NextResponse.json({ ok: false, message: 'Unauthorized' }, { status: 401 }),
      user: null,
    }
  }
  // The session is a signed token — use a stable identifier for audit actor.
  // For now we use a constant sentinel; PR 5 wires real user identity.
  return {
    response: null,
    user: { token: 'captain' },
  }
}

/**
 * Combined guard — feature flag + auth. Returns the first failure response,
 * or null + session user if both pass.
 */
export async function requireProvisioningAccess(): Promise<
  { response: NextResponse; user: null } | { response: null; user: SessionUser }
> {
  const flagResponse = featureFlagCheck()
  if (flagResponse) return { response: flagResponse, user: null }
  return authCheck()
}

/**
 * The no-auth posture, SHARED with middleware.ts rather than copied.
 *
 * Page navigation and action dispatch must agree, or a no-auth build renders
 * pages and returns "Unauthorized" from every button. They used to agree by
 * hand — two copies of one predicate, each commented "keep identical to the
 * other" — which is a rule with a drift date. The decision now lives in
 * lib/auth-posture.ts, and `MOCK_DATA` is no longer one of its triggers.
 */
function noAuthPosture(): boolean {
  return isNoAuthPosture(process.env)
}

/**
 * Server-ACTION auth gate.
 *
 * authCheck()/requireProvisioningAccess() return a NextResponse — the right
 * shape for API ROUTE handlers, the wrong shape for Server Actions (which are
 * global action-ID POST endpoints that return plain result objects, NOT
 * Responses). Middleware gates page navigation but never covers action
 * dispatch, so every mutating or secret-reading action must call THIS as its
 * first statement and fold a `false` into its own error result shape.
 *
 * Reuses the exact same session scheme (verifySession → signed cabinet_session
 * cookie, fail-closed in production per lib/auth.resolveSecret). No new auth
 * primitive is introduced.
 */
export async function requireDashboardAuth(): Promise<boolean> {
  if (noAuthPosture()) return true
  return verifySession()
}
