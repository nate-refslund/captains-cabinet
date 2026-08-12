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

  it('cookie-gates /vault (now the redirect alias — auth still runs FIRST)', async () => {
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

  // Captain naming ruling 2026-07-17: the reader lives at /library now (the
  // vault browser moved; /vault redirects). Same gate, new address.
  it('cookie-gates /library (the Library reader is NOT in the static allowlist)', async () => {
    const res = await middleware(req('/library'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('cookie-gates a deep /library/... note path and the graph tab', async () => {
    for (const p of ['/library/decisions/some-note.md', '/library/graph']) {
      const res = await middleware(req(p))
      expect(res.status).toBe(307)
      expect(res.headers.get('location')).toContain('/login')
    }
  })

  it('cookie-gates GET /api/library/search (memory search endpoint) with no session', async () => {
    const res = await middleware(req('/api/library/search?q=anything'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })
})

/**
 * THE FIRST-RUN LOCK. Between the hatch finishing and the operator choosing a
 * password, DASHBOARD_PASSWORD is unset. In that window the cabinet must not be
 * driveable: every gated route and mutating API is redirected to /login (which
 * renders the "create a password" screen), and ONLY /login is reachable. This is
 * the property the "choose your own password on first run" flow rests on — the
 * create action is the sole allowed pre-auth path and is itself localhost-only.
 */
describe('first-run lock — no password configured yet', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('DASHBOARD_PASSWORD', '') // unset — the fresh-instance state
    vi.stubEnv('MOCK_DATA', '')
    vi.stubEnv('DASHBOARD_NO_AUTH', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('refuses a protected API with no password set — redirected to /login, never served', async () => {
    for (const p of ['/api/library/search?q=x', '/api/tasks', '/api/world/stream']) {
      const res = await middleware(req(p))
      expect(res.status).toBe(307)
      expect(res.headers.get('location')).toContain('/login')
    }
  })

  it('refuses a normal gated page with no password set', async () => {
    const res = await middleware(req('/'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toContain('/login')
  })

  it('lets ONLY /login through, so the create-password screen is reachable', async () => {
    const res = await middleware(req('/login'))
    expect(res.status).toBe(200)
    expect(res.headers.get('location')).toBeNull()
  })
})
