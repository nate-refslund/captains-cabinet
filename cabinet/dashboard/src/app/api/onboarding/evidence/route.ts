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
  // Require a declared, bounded Content-Length BEFORE buffering. A missing
  // header (chunked / streaming body) previously coerced to 0 and skipped this
  // gate, so an unbounded body was fully buffered by req.text() before the
  // byte check below ever ran. Mirrors the sibling /api/onboarding gate: a
  // legitimate JSON POST from a browser or the bridge always sends
  // Content-Length, so no real observation is lost by refusing here.
  const header = req.headers.get('content-length')
  const declared = header === null ? NaN : Number(header)
  if (!Number.isFinite(declared) || declared < 0 || declared > MAX_BODY_BYTES) {
    return response({ ok: false, code: 'body_too_large', error: 'That evidence signal is too large.' }, { status: 413 })
  }
  let text: string
  try {
    text = await req.text()
  } catch {
    return response({ ok: false, code: 'invalid_json', error: 'That evidence signal was not valid.' }, { status: 400 })
  }
  // Re-check the real bytes — a lying small Content-Length must not smuggle an
  // oversized body past the declared gate.
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) {
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
