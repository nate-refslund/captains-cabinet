/**
 * officers.ts auth-guard coverage — before this guard an unauthenticated POST
 * could start/stop/restart/delete officers or create a new one (spawning
 * tmux windows, rewriting product.yml, deleting .env bot tokens). Pins: every
 * mutating officer action refuses the unauthenticated caller and never shells
 * out; an authenticated caller proceeds.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockDockerExec, mockRedisSet, mockRedisDel } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockDockerExec: vi.fn(),
  mockRedisSet: vi.fn(),
  mockRedisDel: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/docker', () => ({ dockerExec: mockDockerExec }))
vi.mock('@/lib/redis', () => ({
  default: { set: mockRedisSet, del: mockRedisDel },
  // A LIVE store. These arms are about the auth gate; the posture gate has its
  // own describe at the bottom, where the value is varied per test.
  isMockRedis: false,
  storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
}))

import {
  startOfficer,
  stopOfficer,
  restartOfficer,
  deleteOfficer,
  createOfficer,
} from './officers'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
})

afterEach(() => vi.unstubAllEnvs())

describe('officer actions — unauthenticated is refused, no shell exec', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('startOfficer', async () => {
    expect(await startOfficer('cto')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('stopOfficer', async () => {
    expect(await stopOfficer('cto')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('restartOfficer', async () => {
    expect(await restartOfficer('cto')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('deleteOfficer', async () => {
    expect(await deleteOfficer('cto')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('createOfficer (form action) → { error: Unauthorized }, no shell exec', async () => {
    const fd = new FormData()
    fd.set('abbreviation', 'xyz')
    fd.set('title', 'X')
    fd.set('domain', 'd')
    fd.set('botUsername', 'u')
    fd.set('botToken', 't')
    expect(await createOfficer(null, fd)).toEqual({ error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('officer actions — authenticated proceeds', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('startOfficer reaches the start script', async () => {
    const res = await startOfficer('cto')
    expect(res).toEqual({ success: true })
    expect(mockDockerExec).toHaveBeenCalled()
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:officer:expected:cto', 'active')
  })
})

/**
 * THE POSTURE GATE — a fleet command that was never executed may not report
 * success.
 *
 * With the store not live, `dockerExec` returns `mock: command executed`
 * without running anything, and every action below used to follow it with
 * `{ success: true }`. `stopOfficer` is the sharp end: the Captain is told an
 * autonomous officer was halted while it is still running. A read-back cannot
 * catch this — the not-live store is an in-process object that echoes the write
 * straight back — so the posture is the gate.
 *
 * Each arm FAILS against pre-guard `officers.ts`, which returned success here.
 */
describe('officer actions — a dashboard with no cabinet refuses instead of claiming', () => {
  const withPosture = async (isMock: boolean) => {
    vi.resetModules()
    vi.doMock('next/cache', () => ({ revalidatePath: vi.fn() }))
    vi.doMock('@/lib/auth', () => ({ verifySession: async () => true }))
    vi.doMock('@/lib/docker', () => ({ dockerExec: mockDockerExec }))
    vi.doMock('@/lib/redis', () => ({
      default: { set: mockRedisSet, del: mockRedisDel },
      isMockRedis: isMock,
      storeReading: {
        posture: isMock ? 'unconfigured' : 'live',
        source: isMock
          ? 'no store is configured (REDIS_URL unset)'
          : 'the configured store',
        fabricated: false,
      },
    }))
    return import('./officers')
  }

  it('stopOfficer refuses — the Captain is never told a running officer was halted', async () => {
    const { stopOfficer } = await withPosture(true)
    const res = await stopOfficer('cto')
    expect(res.success).toBe(false)
    expect(res.error).toMatch(/not connected to a cabinet/)
    expect(mockDockerExec).not.toHaveBeenCalled()
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it('startOfficer, restartOfficer and deleteOfficer refuse too', async () => {
    const { startOfficer, restartOfficer, deleteOfficer } = await withPosture(true)
    for (const call of [startOfficer('cto'), restartOfficer('cto'), deleteOfficer('cto')]) {
      const res = await call
      expect(res.success).toBe(false)
      expect(res.error).toMatch(/not connected to a cabinet/)
    }
    expect(mockDockerExec).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('the inverse: a live store still runs the command and reports success', async () => {
    const { stopOfficer } = await withPosture(false)
    expect(await stopOfficer('cto')).toEqual({ success: true })
    expect(mockDockerExec).toHaveBeenCalledWith('tmux kill-window -t cabinet:officer-cto')
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:officer:expected:cto', 'stopped')
  })
})
