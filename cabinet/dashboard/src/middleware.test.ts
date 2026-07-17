import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { middleware } from './middleware'

/**
 * Pins the middleware's auth exemptions. The Telegram webhook is let through
 * WITHOUT a session cookie (its route enforces a secret-token check), but the
 * exemption is an EXACT path — any sibling under /api/telegram/* must stay
 * cookie-gated. A regression to a prefix match here would silently un-auth new
 * telegram routes.
 */
function req(pathname: string): NextRequest {
  return new NextRequest(`http://localhost${pathname}`)
}

describe('middleware auth exemptions (production posture)', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('DASHBOARD_PASSWORD', 'a-real-secret')
    vi.stubEnv('MOCK_DATA', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('lets the exact Telegram webhook path through without a session cookie', async () => {
    const res = await middleware(req('/api/telegram/provisioning-webhook'))
    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })

  it('still cookie-gates a SIBLING /api/telegram/* path (exact-match exemption)', async () => {
    const res = await middleware(req('/api/telegram/other'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('cookie-gates a normal app route with no session', async () => {
    const res = await middleware(req('/'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('cookie-gates /vault (read-only vault browser is NOT in the static allowlist)', async () => {
    const res = await middleware(req('/vault'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('cookie-gates a deep /vault/... note path with no session', async () => {
    const res = await middleware(req('/vault/decisions/some-note.md'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('cookie-gates any would-be /api/vault/* endpoint (defense for a future API)', async () => {
    const res = await middleware(req('/api/vault/list'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })
})
