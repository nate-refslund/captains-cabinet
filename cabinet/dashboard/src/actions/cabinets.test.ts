/**
 * src/actions/cabinets.ts mutating actions (suspend/resume/archive) —
 * AUTHZ-ADV-1 coverage.
 *
 * These thin wrappers POST to the internal /api/cabinets/{id}/{op} route.
 * Two properties are pinned:
 *  1. They gate on requireDashboardAuth as their first statement (middleware
 *     never covers server-action dispatch), so an unauthenticated caller is
 *     refused BEFORE any internal API hop.
 *  2. When authenticated they forward the caller's session cookie on the
 *     internal fetch — without it the route-side requireProvisioningAccess()
 *     sees no cookie and denies even a legitimately authenticated captain
 *     (the surfaced correctness bug).
 *
 * requireDashboardAuth runs for real — only verifySession is mocked — with the
 * enforcing posture pinned (MOCK_DATA unset, NODE_ENV=test).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockHeaders } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockHeaders: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/config', () => ({ getDashboardConfig: () => ({ consumerModeEnabled: false }) }))
vi.mock('next/headers', () => ({ headers: mockHeaders }))

import { suspendCabinet, resumeCabinet, archiveCabinet } from './cabinets'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  vi.stubGlobal('fetch', fetchMock)
  mockHeaders.mockResolvedValue({
    get: (k: string) => (k === 'cookie' ? 'cabinet_session=tok.sig' : null),
  })
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('unauthenticated caller is refused before the internal API hop', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('suspendCabinet → Unauthorized, fetch never called', async () => {
    expect(await suspendCabinet('cab-1')).toEqual({ ok: false, message: 'Unauthorized' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('resumeCabinet → Unauthorized, fetch never called', async () => {
    expect(await resumeCabinet('cab-1')).toEqual({ ok: false, message: 'Unauthorized' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('archiveCabinet → Unauthorized, fetch never called', async () => {
    expect(await archiveCabinet('cab-1')).toEqual({ ok: false, message: 'Unauthorized' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('authenticated caller reaches the op with the session cookie forwarded', () => {
  beforeEach(() => {
    mockVerify.mockResolvedValue(true)
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ok: true, state: 'suspended' }) })
  })

  it('suspendCabinet forwards the caller cookie header and returns the route body', async () => {
    const res = await suspendCabinet('cab-1')
    expect(res).toEqual({ ok: true, state: 'suspended' })
    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/cabinets/cab-1/suspend')
    expect(opts.method).toBe('POST')
    expect(opts.headers.cookie).toBe('cabinet_session=tok.sig')
  })

  it('resumeCabinet and archiveCabinet hit their respective op paths (authenticated)', async () => {
    await resumeCabinet('cab-2')
    expect(fetchMock.mock.calls[0][0]).toContain('/api/cabinets/cab-2/resume')
    fetchMock.mockClear()
    await archiveCabinet('cab-3')
    expect(fetchMock.mock.calls[0][0]).toContain('/api/cabinets/cab-3/archive')
  })

  it('a missing cookie still reaches the op (route-side guard adjudicates) with an empty cookie header', async () => {
    mockHeaders.mockResolvedValue({ get: () => null })
    await suspendCabinet('cab-4')
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][1].headers.cookie).toBe('')
  })
})
