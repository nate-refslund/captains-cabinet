/**
 * Cross-module auth-guard sweep for the P1 broken-access-control fix.
 *
 * Server Actions are global action-ID POST endpoints and middleware never
 * covers action dispatch, so every mutating or operational-data action must
 * gate on requireDashboardAuth() as its first statement. This sweep pins the
 * unauthenticated posture across the remaining action modules (env / killswitch
 * / officers have their own focused files) AND proves the login action stays
 * reachable unauthenticated (guarding it would lock everyone out).
 *
 * The real requireDashboardAuth runs — only verifySession is mocked — with the
 * enforcing posture pinned (MOCK_DATA unset, NODE_ENV=test).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const {
  mockVerify,
  mockCheckPassword,
  mockCreateSession,
  mockDestroySession,
  mockDockerExec,
  mockRedisGet,
  mockRedisSet,
  mockRedisDel,
  mockRedirect,
  mockReadJournal,
} = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockCheckPassword: vi.fn(),
  mockCreateSession: vi.fn(),
  mockDestroySession: vi.fn(),
  mockDockerExec: vi.fn(),
  mockRedisGet: vi.fn(),
  mockRedisSet: vi.fn(),
  mockRedisDel: vi.fn(),
  mockRedirect: vi.fn(),
  mockReadJournal: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('next/navigation', () => ({ redirect: mockRedirect }))
vi.mock('@/lib/auth', () => ({
  verifySession: mockVerify,
  checkPassword: mockCheckPassword,
  createSession: mockCreateSession,
  destroySession: mockDestroySession,
}))
vi.mock('@/lib/docker', () => ({ dockerExec: mockDockerExec, getEnvVars: vi.fn() }))
vi.mock('@/lib/redis', () => ({
  default: { get: mockRedisGet, set: mockRedisSet, del: mockRedisDel },
}))
vi.mock('@/components/receipts/journal', () => ({
  readJournal: mockReadJournal,
  shapeReceipt: vi.fn(),
}))

import { updateProductConfig, updateLinearConfig } from './config'
import { updateProjectConfig } from './project-config'
import { switchProject, getActiveProject, getProjects } from './projects'
import { approveGap, declineGap } from './gaps'
import { resetTaskTimer, deleteTaskTimer } from './crons'
import { updateRoleDefinition, updateLoopPrompt } from './files'
import { readGovernanceFile, readAllGovernanceFiles, updateGovernanceFile } from './governance'
import { getPresets, getPresetOfficers } from './cabinets'
import { listReceipts } from './receipts'
import { login, logout } from './auth'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
})

afterEach(() => vi.unstubAllEnvs())

describe('mutating actions refuse the unauthenticated caller', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('config.updateProductConfig → Unauthorized, no shell exec', async () => {
    expect(await updateProductConfig('name', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('config.updateLinearConfig → Unauthorized, no shell exec', async () => {
    expect(await updateLinearConfig('team_key', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('project-config.updateProjectConfig → Unauthorized, no shell exec', async () => {
    expect(await updateProjectConfig('product', 'name', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('projects.switchProject → Unauthorized, no shell exec', async () => {
    expect(await switchProject('evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('gaps.approveGap / declineGap → unauthorized, no shell exec', async () => {
    expect(await approveGap('gap-0000abcd')).toEqual({ ok: false, error: 'unauthorized' })
    expect(await declineGap('gap-0000abcd', 'x')).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('crons.resetTaskTimer / deleteTaskTimer → Unauthorized, Redis untouched', async () => {
    expect(await resetTaskTimer('cos', 'sweep')).toEqual({ error: 'Unauthorized' })
    expect(await deleteTaskTimer('cos', 'sweep')).toEqual({ error: 'Unauthorized' })
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('files.updateRoleDefinition / updateLoopPrompt → Unauthorized', async () => {
    expect(await updateRoleDefinition('cos', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(await updateLoopPrompt('cos', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
  })

  it('governance.updateGovernanceFile → Unauthorized (constitution not rewritten)', async () => {
    expect(await updateGovernanceFile('constitution', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
  })
})

describe('operational-data reads refuse the unauthenticated caller (no data leaked)', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('governance reads return empty', async () => {
    expect(await readGovernanceFile('constitution')).toBe('')
    expect(await readAllGovernanceFiles()).toEqual({})
  })

  it('projects reads return empty', async () => {
    expect(await getActiveProject()).toBe('')
    expect(await getProjects()).toEqual([])
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('cabinet preset catalog returns empty', async () => {
    expect(await getPresets()).toEqual([])
    expect(await getPresetOfficers('any')).toEqual([])
  })

  it('receipts undo-journal is not read, returns an empty payload with an honest error', async () => {
    const res = await listReceipts()
    expect(res.receipts).toEqual([])
    expect(res.error).toBe('Unauthorized')
    expect(mockReadJournal).not.toHaveBeenCalled()
  })
})

describe('authenticated caller proceeds', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('config.updateProductConfig reaches the write path', async () => {
    const res = await updateProductConfig('name', 'Sensed')
    expect(res).toEqual({ success: true })
    expect(mockDockerExec).toHaveBeenCalled()
  })

  it('gaps.approveGap reaches the org-runtime CLI for a valid id', async () => {
    const res = await approveGap('gap-0000abcd')
    expect(res).toEqual({ ok: true })
    expect(mockDockerExec).toHaveBeenCalled()
  })

  it('receipts.listReceipts reads the real journal for an authed caller', async () => {
    mockReadJournal.mockResolvedValue({
      rows: [], skipped: 0, skippedFiles: 0, missingDir: true, error: null, journalDir: '/tmp/j',
    })
    const res = await listReceipts()
    expect(res.error).toBeNull()
    expect(mockReadJournal).toHaveBeenCalledOnce()
  })
})

describe('the login gate stays UNAUTHENTICATED (guarding it would lock everyone out)', () => {
  it('login with a correct password creates a session even with no prior session', async () => {
    mockVerify.mockResolvedValue(false) // attacker/first-time visitor: no session yet
    mockCheckPassword.mockReturnValue(true)
    const fd = new FormData()
    fd.set('password', 'correct')
    await login(null, fd)
    // Body ran: it never called requireDashboardAuth, so the missing session
    // did not block it.
    expect(mockCreateSession).toHaveBeenCalledOnce()
    expect(mockRedirect).toHaveBeenCalledWith('/')
  })

  it('login with a wrong password is rejected by the password gate itself', async () => {
    mockCheckPassword.mockReturnValue(false)
    const fd = new FormData()
    fd.set('password', 'nope')
    expect(await login(null, fd)).toEqual({ error: 'Invalid password' })
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('logout works without a prior session (destroys only the caller cookie)', async () => {
    mockVerify.mockResolvedValue(false)
    await logout()
    expect(mockDestroySession).toHaveBeenCalledOnce()
    expect(mockRedirect).toHaveBeenCalledWith('/login')
  })
})
