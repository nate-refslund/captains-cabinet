import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const { getMock, applyMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  applyMock: vi.fn(),
}))

vi.mock('@/lib/onboarding/bridge', () => {
  class OnboardingBridgeError extends Error {
    constructor(
      public readonly code: string,
      message: string,
      public readonly status = 400
    ) {
      super(message)
    }
  }
  return {
    getOnboarding: getMock,
    applyOnboardingAction: applyMock,
    OnboardingBridgeError,
  }
})

import { GET, POST } from './route'
import { OnboardingBridgeError } from '@/lib/onboarding/bridge'

const SNAPSHOT = {
  ok: true,
  state: { revision: 2, stage: 'charter_pending' },
  card: { id: 'onboarding:j1:charter_pending', revision: 2 },
}

function post(body: unknown, options: { origin?: string; contentLength?: number; url?: string; host?: string; raw?: string } = {}) {
  const text = options.raw ?? JSON.stringify(body)
  const url = options.url ?? 'http://localhost/api/onboarding'
  return new NextRequest(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      origin: options.origin ?? new URL(url).origin,
      ...(options.host ? { host: options.host } : {}),
      'content-length': String(options.contentLength ?? text.length),
    },
    body: text,
  })
}

beforeEach(() => {
  getMock.mockReset().mockResolvedValue(SNAPSHOT)
  applyMock.mockReset().mockResolvedValue(SNAPSHOT)
})

describe('GET /api/onboarding', () => {
  it('returns the canonical card with private no-store', async () => {
    const response = await GET()
    expect(response.status).toBe(200)
    expect(await response.json()).toEqual(SNAPSHOT)
    expect(response.headers.get('cache-control')).toContain('no-store')
  })

  it('does not leak bridge detail on an unknown failure', async () => {
    getMock.mockRejectedValueOnce(new Error('/private/secret/path'))
    const response = await GET()
    expect(response.status).toBe(503)
    expect(JSON.stringify(await response.json())).not.toContain('/private/secret/path')
  })
})

describe('POST /api/onboarding', () => {
  it('routes Dashboard actions into the canonical bridge', async () => {
    const response = await POST(post({ action: 'pause', expected_revision: 2 }))
    expect(response.status).toBe(200)
    expect(applyMock).toHaveBeenCalledWith(
      { action: 'pause', expected_revision: 2 },
      'dashboard'
    )
  })

  it('routes the World skin to the same bridge, not a world writer', async () => {
    const response = await POST(post({ action: 'continue', surface: 'world' }))
    expect(response.status).toBe(200)
    expect(applyMock).toHaveBeenCalledWith({ action: 'continue' }, 'world')
  })

  it('refuses cross-origin posts', async () => {
    const response = await POST(post({ action: 'pause' }, { origin: 'https://evil.example' }))
    expect(response.status).toBe(403)
    expect(applyMock).not.toHaveBeenCalled()
  })

  it('accepts the browser-visible Host when Next is bound to 0.0.0.0', async () => {
    const response = await POST(post(
      { action: 'pause' },
      {
        url: 'http://0.0.0.0:3100/api/onboarding',
        host: 'cabinet.local:3100',
        origin: 'http://cabinet.local:3100',
      }
    ))
    expect(response.status).toBe(200)
    expect(applyMock).toHaveBeenCalled()
  })

  it('refuses oversized declared bodies before parsing', async () => {
    const response = await POST(post({ action: 'pause' }, { contentLength: 99_999 }))
    expect(response.status).toBe(413)
    expect(applyMock).not.toHaveBeenCalled()
  })

  it('refuses an oversized body even when Content-Length lies', async () => {
    const response = await POST(post(null, {
      contentLength: 1,
      raw: JSON.stringify({ action: 'pause', padding: 'x'.repeat(20_000) }),
    }))
    expect(response.status).toBe(413)
    expect(applyMock).not.toHaveBeenCalled()
  })

  it('refuses a POST with no Content-Length before buffering the body', async () => {
    const req = {
      headers: new Headers({ 'content-type': 'application/json', origin: 'http://localhost' }),
      nextUrl: new URL('http://localhost/api/onboarding'),
      text: async () => JSON.stringify({ action: 'pause' }),
    } as unknown as NextRequest
    const response = await POST(req)
    expect(response.status).toBe(413)
    expect(applyMock).not.toHaveBeenCalled()
  })

  it('maps a stale cross-surface card to 409', async () => {
    applyMock.mockRejectedValueOnce(
      new OnboardingBridgeError('revision_conflict', 'Refresh this card.', 400)
    )
    const response = await POST(post({ action: 'pause' }))
    expect(response.status).toBe(409)
    expect(await response.json()).toMatchObject({ code: 'revision_conflict' })
  })
})
