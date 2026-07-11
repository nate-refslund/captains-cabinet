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
