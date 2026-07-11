/**
 * env.ts auth-guard coverage — the P1 broken-access-control fix.
 *
 * Server Actions are global action-ID POST endpoints; middleware never covers
 * action dispatch, so before this guard an unauthenticated attacker could POST
 * getEnvVarsAction to /display and exfiltrate real cabinet/.env secrets, or
 * addEnvVar/updateEnvVar/deleteEnvVar to rewrite the file. These pin: an
 * unauthenticated call NEVER reaches the underlying docker op (asserted via a
 * mock), and an authenticated call proceeds.
 *
 * The real requireDashboardAuth is exercised (only verifySession is mocked),
 * with NODE_ENV/ MOCK_DATA pinned so the guard is in enforcing posture.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockDockerExec, mockGetEnvVars } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockDockerExec: vi.fn(),
  mockGetEnvVars: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/docker', () => ({
  dockerExec: mockDockerExec,
  getEnvVars: mockGetEnvVars,
}))

import { getEnvVarsAction, addEnvVar, updateEnvVar, deleteEnvVar } from './env'

beforeEach(() => {
  vi.clearAllMocks()
  // Enforcing posture: not the demo/dev bypass, so requireDashboardAuth
  // delegates to the (mocked) verifySession.
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
  mockGetEnvVars.mockResolvedValue({ SECRET_KEY: 'super-secret' })
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('env actions — unauthenticated is refused, no side effect', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('getEnvVarsAction throws and never reads the real env (no secret leak)', async () => {
    await expect(getEnvVarsAction()).rejects.toThrow('Unauthorized')
    expect(mockGetEnvVars).not.toHaveBeenCalled()
  })

  it('addEnvVar returns Unauthorized and never shells out', async () => {
    expect(await addEnvVar('FOO', 'bar')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('updateEnvVar returns Unauthorized and never shells out', async () => {
    expect(await updateEnvVar('FOO', 'bar')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('deleteEnvVar returns Unauthorized and never shells out', async () => {
    expect(await deleteEnvVar('FOO')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('env actions — authenticated proceeds', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('getEnvVarsAction returns the env map for an authed caller', async () => {
    expect(await getEnvVarsAction()).toEqual({ SECRET_KEY: 'super-secret' })
    expect(mockGetEnvVars).toHaveBeenCalledOnce()
  })

  it('addEnvVar reaches the write path for an authed caller', async () => {
    mockDockerExec.mockResolvedValueOnce({ stdout: '0', stderr: '' }) // not-exists check
    const res = await addEnvVar('FOO', 'bar')
    expect(res).toEqual({ success: true })
    expect(mockDockerExec).toHaveBeenCalled()
  })
})
