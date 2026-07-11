/**
 * requireDashboardAuth() posture coverage — the server-ACTION auth gate added
 * for the P1 broken-access-control fix.
 *
 * Contract:
 *  - In the enforcing posture (a real production-shaped deploy) it delegates to
 *    verifySession() — the signed cabinet_session cookie is required.
 *  - In the explicit no-auth posture that middleware ALSO bypasses (MOCK_DATA
 *    demo toggle, or development with no password), it short-circuits true so
 *    demo/dev pages and their action buttons stay consistent — WITHOUT ever
 *    consulting a session.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
}))

vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/config', () => ({ getDashboardConfig: () => ({ consumerModeEnabled: false }) }))

import { requireDashboardAuth } from './guard'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => vi.unstubAllEnvs())

describe('enforcing posture — delegates to verifySession', () => {
  beforeEach(() => {
    vi.stubEnv('MOCK_DATA', '')
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('DASHBOARD_PASSWORD', 'a-real-password')
  })

  it('a valid session → true', async () => {
    mockVerify.mockResolvedValue(true)
    expect(await requireDashboardAuth()).toBe(true)
    expect(mockVerify).toHaveBeenCalledOnce()
  })

  it('no/invalid session → false (the P1 attacker case)', async () => {
    mockVerify.mockResolvedValue(false)
    expect(await requireDashboardAuth()).toBe(false)
    expect(mockVerify).toHaveBeenCalledOnce()
  })

  it('NODE_ENV=test with no password is still enforcing (not the dev bypass)', async () => {
    vi.stubEnv('NODE_ENV', 'test')
    vi.stubEnv('DASHBOARD_PASSWORD', '')
    mockVerify.mockResolvedValue(false)
    expect(await requireDashboardAuth()).toBe(false)
    expect(mockVerify).toHaveBeenCalledOnce()
  })
})

describe('no-auth posture — bypasses without consulting a session', () => {
  it('MOCK_DATA=true → true, verifySession never called', async () => {
    vi.stubEnv('MOCK_DATA', 'true')
    expect(await requireDashboardAuth()).toBe(true)
    expect(mockVerify).not.toHaveBeenCalled()
  })

  it('development with no password → true, verifySession never called', async () => {
    vi.stubEnv('MOCK_DATA', '')
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('DASHBOARD_PASSWORD', '')
    expect(await requireDashboardAuth()).toBe(true)
    expect(mockVerify).not.toHaveBeenCalled()
  })

  it('development WITH a password → enforcing again (delegates to verifySession)', async () => {
    vi.stubEnv('MOCK_DATA', '')
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('DASHBOARD_PASSWORD', 'set')
    mockVerify.mockResolvedValue(false)
    expect(await requireDashboardAuth()).toBe(false)
    expect(mockVerify).toHaveBeenCalledOnce()
  })
})

describe('MOCK_DATA never opens a production deploy (AUTHZ-ADV-2)', () => {
  // The MOCK_DATA demo/kiosk toggle is a dev-only affordance. A single env var
  // on a production build must NOT re-open every guarded action — the signed
  // session must still be enforced.
  beforeEach(() => {
    vi.stubEnv('MOCK_DATA', 'true')
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('DASHBOARD_PASSWORD', 'a-real-password')
  })

  it('MOCK_DATA=true in production still delegates to verifySession (no bypass)', async () => {
    mockVerify.mockResolvedValue(false)
    expect(await requireDashboardAuth()).toBe(false)
    expect(mockVerify).toHaveBeenCalledOnce()
  })

  it('MOCK_DATA=true in production admits ONLY a valid session', async () => {
    mockVerify.mockResolvedValue(true)
    expect(await requireDashboardAuth()).toBe(true)
    expect(mockVerify).toHaveBeenCalledOnce()
  })
})
