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

// Body-bounding gate. The declared Content-Length must be validated BEFORE the
// body is buffered: a chunked/streaming request carries no Content-Length at
// all, and `Number(null || 0)` used to coerce that to 0 and skip the gate, so
// req.text() fully buffered an unbounded body before the real byte check ran.
// The crafted request exposes a text() spy so these tests prove the body was
// never read, not merely that the status code is right.
describe('POST /api/onboarding/evidence — body bounding', () => {
  function rawRequest(options: { contentLength?: string; body?: string } = {}) {
    const headers = new Headers({ origin: 'http://localhost:3100', host: 'localhost:3100' })
    if (options.contentLength !== undefined) headers.set('content-length', options.contentLength)
    const text = vi.fn().mockResolvedValue(options.body ?? '{"phase":"ui","status":"failed"}')
    const req = {
      headers,
      nextUrl: { protocol: 'http:', origin: 'http://localhost:3100' },
      text,
    } as unknown as NextRequest
    return { req, text }
  }

  it('refuses a missing Content-Length (chunked body) with 413 before buffering', async () => {
    const { req, text } = rawRequest()
    const result = await POST(req)
    expect(result.status).toBe(413)
    expect(text).not.toHaveBeenCalled()
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('refuses a non-numeric Content-Length with 413 before buffering', async () => {
    const { req, text } = rawRequest({ contentLength: 'banana' })
    const result = await POST(req)
    expect(result.status).toBe(413)
    expect(text).not.toHaveBeenCalled()
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('refuses a negative Content-Length with 413 before buffering', async () => {
    const { req, text } = rawRequest({ contentLength: '-5' })
    const result = await POST(req)
    expect(result.status).toBe(413)
    expect(text).not.toHaveBeenCalled()
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('refuses an oversized declared Content-Length with 413 before buffering', async () => {
    const { req, text } = rawRequest({ contentLength: String(9 * 1024 * 1024) })
    const result = await POST(req)
    expect(result.status).toBe(413)
    expect(text).not.toHaveBeenCalled()
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('still refuses an oversized real body hiding behind a lying small Content-Length', async () => {
    const { req } = rawRequest({ contentLength: '10', body: 'x'.repeat(9 * 1024) })
    const result = await POST(req)
    expect(result.status).toBe(413)
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('a real NextRequest without an explicit Content-Length header is refused', async () => {
    // undici does not surface an auto-computed Content-Length on the Request
    // object, so this is exactly what the route sees for a chunked sender.
    const result = await POST(new NextRequest('http://localhost:3100/api/onboarding/evidence', {
      method: 'POST',
      headers: { origin: 'http://localhost:3100', host: 'localhost:3100' },
      body: JSON.stringify({ phase: 'ui', status: 'failed' }),
    }))
    expect(result.status).toBe(413)
    expect(recordMock).not.toHaveBeenCalled()
  })

  it('records a bounded event normally when Content-Length is declared and honest', async () => {
    const body = JSON.stringify({ phase: 'ui', status: 'succeeded', detail: { rendered_stage: 'welcome' } })
    const { req, text } = rawRequest({ contentLength: String(body.length), body })
    const result = await POST(req)
    expect(result.status).toBe(200)
    expect(text).toHaveBeenCalled()
    expect(recordMock).toHaveBeenCalledWith(
      { phase: 'ui', status: 'succeeded', detail: { rendered_stage: 'welcome' } },
      'dashboard'
    )
  })
})
