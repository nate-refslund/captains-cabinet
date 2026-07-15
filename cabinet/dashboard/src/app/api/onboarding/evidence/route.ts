/** Same-origin, bounded observation door for onboarding UI/transport/feedback. */
import { NextRequest, NextResponse } from 'next/server'
import {
  OnboardingBridgeError,
  recordOnboardingEvidence,
} from '@/lib/onboarding/bridge'
import type {
  OnboardingObservationRequest,
  OnboardingSurface,
} from '@/lib/onboarding/types'

const MAX_BODY_BYTES = 8 * 1024

function response(body: object, init?: ResponseInit): NextResponse {
  const out = NextResponse.json(body, init)
  out.headers.set('Cache-Control', 'private, no-store, max-age=0')
  return out
}

function sameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get('origin')
  if (!origin) return false
  try {
    const host = req.headers.get('host')
    const expected = host ? `${req.nextUrl.protocol}//${host}` : req.nextUrl.origin
    return new URL(origin).origin === expected
  } catch {
    return false
  }
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  if (!sameOrigin(req)) {
    return response({ ok: false, code: 'origin_refused', error: 'That evidence signal did not come from the Cabinet app.' }, { status: 403 })
  }
  const declared = Number(req.headers.get('content-length') || 0)
  if (declared > MAX_BODY_BYTES) {
    return response({ ok: false, code: 'body_too_large', error: 'That evidence signal is too large.' }, { status: 413 })
  }
  const text = await req.text()
  if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) {
    return response({ ok: false, code: 'body_too_large', error: 'That evidence signal is too large.' }, { status: 413 })
  }
  let raw: (OnboardingObservationRequest & { surface?: string }) | null = null
  try {
    raw = JSON.parse(text) as OnboardingObservationRequest & { surface?: string }
  } catch {
    return response({ ok: false, code: 'invalid_json', error: 'That evidence signal was not valid.' }, { status: 400 })
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return response({ ok: false, code: 'invalid_body', error: 'That evidence signal was not valid.' }, { status: 400 })
  }
  const surface: OnboardingSurface = (
    raw.surface === 'world' || raw.surface === 'companion' ? raw.surface : 'dashboard'
  )
  const { surface: _ignored, ...observation } = raw
  try {
    return response(await recordOnboardingEvidence(observation, surface))
  } catch (error) {
    const known = error instanceof OnboardingBridgeError ? error : null
    return response(
      { ok: false, code: known?.code || 'evidence_failed', error: known?.message || 'The evidence signal could not be preserved.' },
      { status: known?.status || 503 }
    )
  }
}
