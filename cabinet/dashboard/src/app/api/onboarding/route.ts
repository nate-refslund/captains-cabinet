/**
 * Shared authenticated onboarding door.
 *
 * Dashboard and the World overlay use this exact route. World has no
 * onboarding mutation route of its own; it is a skin over the same card and
 * action service. Telegram invokes the same bridge from its authenticated
 * webhook.
 */
import { NextRequest, NextResponse } from 'next/server'
import {
  applyOnboardingAction,
  getOnboarding,
  OnboardingBridgeError,
} from '@/lib/onboarding/bridge'
import type {
  OnboardingActionRequest,
  OnboardingSurface,
} from '@/lib/onboarding/types'

export const dynamic = 'force-dynamic'
const MAX_BODY_BYTES = 16 * 1024

function noStore<T>(body: T, init?: ResponseInit): NextResponse<T> {
  const response = NextResponse.json(body, init)
  response.headers.set('Cache-Control', 'private, no-store, max-age=0')
  return response
}

function sameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get('origin')
  if (!origin) return false
  try {
    // `next start --hostname 0.0.0.0` makes nextUrl.origin use the bind
    // address, while the browser correctly sends the host it visited. This
    // must follow that browser-visible Host or every legitimate tap is 403.
    const host = req.headers.get('host')
    const expected = host ? `${req.nextUrl.protocol}//${host}` : req.nextUrl.origin
    return new URL(origin).origin === expected
  } catch {
    return false
  }
}

export async function GET(): Promise<NextResponse> {
  try {
    return noStore(await getOnboarding())
  } catch (error) {
    const known = error instanceof OnboardingBridgeError ? error : null
    return noStore(
      { ok: false, code: known?.code || 'onboarding_unavailable', error: known?.message || 'Onboarding is temporarily unavailable.' },
      { status: known?.status || 503 }
    )
  }
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  if (!sameOrigin(req)) {
    return noStore({ ok: false, code: 'origin_refused', error: 'This onboarding action did not come from the Cabinet app.' }, { status: 403 })
  }
  // Require a declared, bounded Content-Length. A missing header (chunked /
  // streaming body) previously coerced to 0 and skipped this gate, so an
  // unbounded body was fully buffered by req.text() before the byte check
  // below ever ran. A legitimate JSON POST from a browser or the bridge always
  // sends Content-Length.
  const header = req.headers.get('content-length')
  const declared = header === null ? NaN : Number(header)
  if (!Number.isFinite(declared) || declared < 0 || declared > MAX_BODY_BYTES) {
    return noStore({ ok: false, code: 'body_too_large', error: 'That onboarding request is too large.' }, { status: 413 })
  }
  let text: string
  try {
    text = await req.text()
  } catch {
    return noStore({ ok: false, code: 'invalid_json', error: 'That onboarding request was not valid.' }, { status: 400 })
  }
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) {
    return noStore({ ok: false, code: 'body_too_large', error: 'That onboarding request is too large.' }, { status: 413 })
  }
  let raw: (OnboardingActionRequest & { surface?: string }) | null = null
  try {
    raw = JSON.parse(text) as OnboardingActionRequest & { surface?: string }
  } catch {
    return noStore({ ok: false, code: 'invalid_json', error: 'That onboarding request was not valid.' }, { status: 400 })
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return noStore({ ok: false, code: 'invalid_body', error: 'That onboarding request was not valid.' }, { status: 400 })
  }
  const surface: OnboardingSurface = raw.surface === 'world' ? 'world' : 'dashboard'
  const { surface: _ignored, ...request } = raw
  try {
    return noStore(await applyOnboardingAction(request, surface))
  } catch (error) {
    const known = error instanceof OnboardingBridgeError ? error : null
    const status = known?.code === 'revision_conflict' ? 409 : known?.status || 500
    return noStore(
      { ok: false, code: known?.code || 'action_failed', error: known?.message || 'The onboarding action could not be completed.' },
      { status }
    )
  }
}
