import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const { recordMock } = vi.hoisted(() => ({ recordMock: vi.fn() }))
vi.mock('@/lib/onboarding/bridge', () => ({
  recordOnboardingEvidence: recordMock,
  OnboardingBridgeError: class OnboardingBridgeError extends Error {
    constructor(public code: string, message: string, public status = 400) { super(message) }
  },
}))

import { POST } from './route'

function request(body: unknown, origin = 'http://localhost:3100') {
  const text = JSON.stringify(body)
  return new NextRequest('http://localhost:3100/api/onboarding/evidence', {
    method: 'POST',
    headers: { origin, host: 'localhost:3100', 'content-length': String(text.length) },
    body: text,
  })
}

beforeEach(() => recordMock.mockReset().mockResolvedValue({ ok: true, evidence: { event_id: 'e1' } }))

describe('POST /api/onboarding/evidence', () => {
  it('records a bounded World UI failure through the canonical bridge', async () => {
    const result = await POST(request({
      phase: 'ui', status: 'failed', surface: 'world',
      detail: { error_code: 'window_error' },
    }))
    expect(result.status).toBe(200)
    expect(recordMock).toHaveBeenCalledWith(
      { phase: 'ui', status: 'failed', detail: { error_code: 'window_error' } },
      'world'
    )
  })

  it('refuses cross-origin evidence injection', async () => {
    const result = await POST(request({ phase: 'feedback', status: 'useful' }, 'https://evil.example'))
    expect(result.status).toBe(403)
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('refuses a scheme mismatch even when Host matches', async () => {
    const result = await POST(request(
      { phase: 'feedback', status: 'useful' },
      'https://localhost:3100'
    ))
    expect(result.status).toBe(403)
    expect(recordMock).not.toHaveBeenCalled()
  })
})
