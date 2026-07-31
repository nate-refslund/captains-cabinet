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
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import nodePath from 'node:path'

const {
  mockVerify,
  mockReadEvidence,
  mockCheckPassword,
  mockCreateSession,
  mockDestroySession,
  mockDockerExec,
  mockWriteGuard,
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
  mockWriteGuard: vi.fn(),
  mockRedisGet: vi.fn(),
  mockRedisSet: vi.fn(),
  mockRedisDel: vi.fn(),
  mockRedirect: vi.fn(),
  mockReadJournal: vi.fn(),
  mockReadEvidence: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('next/navigation', () => ({ redirect: mockRedirect }))
vi.mock('@/lib/auth', () => ({
  verifySession: mockVerify,
  checkPassword: mockCheckPassword,
  createSession: mockCreateSession,
  destroySession: mockDestroySession,
}))
// `assertRuntimeWritesAllowed` is the in-process half of the same gate: the
// config/env editors no longer shell out (they edit the documents with node:fs
// — lib/config-write.ts, because `sed -i` never ran on this platform), so
// "never reached the write path" is now asserted on BOTH transports. A mock
// that only knew about `dockerExec` would go green for an unauthenticated call
// that reached the filesystem.
vi.mock('@/lib/docker', () => ({
  dockerExec: mockDockerExec,
  assertRuntimeWritesAllowed: mockWriteGuard,
  getEnvVars: vi.fn(),
}))
vi.mock('@/lib/redis', () => ({
  default: { get: mockRedisGet, set: mockRedisSet, del: mockRedisDel },
}))
vi.mock('@/components/receipts/journal', () => ({
  readJournal: mockReadJournal,
  shapeReceipt: vi.fn(),
}))
vi.mock('@/lib/evidence/read', () => ({
  readEvidence: mockReadEvidence,
  EVIDENCE_SHOW_CAP: 100,
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
import { listEvidence } from './evidence'
import { login, logout } from './auth'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
  makeRoot()
})

afterEach(() => {
  vi.unstubAllEnvs()
  dropRoot()
})


/**
 * A temp checkout for the actions that now write with node:fs.
 *
 * CABINET_ROOT is owned here and the destination is ASSERTED to be inside it
 * before any test runs — a previous pass proved that a sweep which overrode the
 * root but not every path-steering variable appends to the live cabinet/.env.
 */
const PRODUCT_YML_BEFORE = 'product:\n  name: Before\n  repo: owner/repo\nlinear:\n  enabled: false\n'
let testRoot = ''
const productYml = () =>
  readFileSync(nodePath.join(testRoot, 'instance', 'config', 'product.yml'), 'utf8')

function makeRoot(): void {
  testRoot = mkdtempSync(nodePath.join(tmpdir(), 'actions-auth-'))
  mkdirSync(nodePath.join(testRoot, 'instance', 'config'), { recursive: true })
  writeFileSync(nodePath.join(testRoot, 'instance', 'config', 'product.yml'), PRODUCT_YML_BEFORE)
  vi.stubEnv('CABINET_ROOT', testRoot)
  const dest = nodePath.join(testRoot, 'instance', 'config', 'product.yml')
  if (!dest.startsWith(testRoot + nodePath.sep)) {
    throw new Error('refusing to run: the config path is outside the temp tree')
  }
}

function dropRoot(): void {
  if (testRoot) rmSync(testRoot, { recursive: true, force: true })
  testRoot = ''
}

describe('mutating actions refuse the unauthenticated caller', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('config.updateProductConfig → Unauthorized, and the write path is never reached', async () => {
    expect(await updateProductConfig('name', 'evil')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
    expect(mockWriteGuard).not.toHaveBeenCalled()
    expect(productYml()).toBe(PRODUCT_YML_BEFORE)
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

  it('evidence store is not read, returns an empty payload with an honest error', async () => {
    const res = await listEvidence()
    expect(res.rows).toEqual([])
    expect(res.unverified).toEqual([])
    expect(res.error).toBe('Unauthorized')
    expect(mockReadEvidence).not.toHaveBeenCalled()
  })
})

describe('authenticated caller proceeds', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('config.updateProductConfig reaches the write path AND lands the bytes', async () => {
    const res = await updateProductConfig('name', 'Acme')
    expect(res).toEqual({ success: true })
    expect(mockWriteGuard).toHaveBeenCalled()
    // The FILE, not the mock. `expect(mockDockerExec).toHaveBeenCalled()` was
    // true of a `sed -i` that exited 1 and changed nothing.
    expect(productYml()).toContain('  name: Acme')
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

  it('evidence.listEvidence reads the real store for an authed caller', async () => {
    const empty = {
      rows: [], unverified: [], totalTrials: 0, verifiedCount: 0, unverifiedCount: 0,
      matchedCount: 0, skippedLines: 0, skippedFiles: 0, storeOk: true, storeErrors: [],
      missingDir: true, error: null, filterError: null, filters: {},
      storeDir: '/tmp/testburg-store', cap: 100,
    }
    mockReadEvidence.mockResolvedValue(empty)
    const res = await listEvidence({ status: 'failed' })
    expect(res.error).toBeNull()
    expect(mockReadEvidence).toHaveBeenCalledOnce()
    expect(mockReadEvidence).toHaveBeenCalledWith({ status: 'failed' })
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
