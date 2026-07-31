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
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import nodePath from 'node:path'

const { mockVerify, mockDockerExec, mockWriteGuard, mockGetEnvVars } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockDockerExec: vi.fn(),
  mockWriteGuard: vi.fn(),
  mockGetEnvVars: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
// The write path is no longer `dockerExec`: env editing happens in this process
// against cabinet/.env (lib/config-write.ts) because `sed -i` never ran on this
// platform. `assertRuntimeWritesAllowed` is the gate both transports share, so
// "never reached the write path" is asserted on it as well as on the shell.
vi.mock('@/lib/docker', () => ({
  dockerExec: mockDockerExec,
  assertRuntimeWritesAllowed: mockWriteGuard,
  getEnvVars: mockGetEnvVars,
}))

import { getEnvVarsAction, addEnvVar, updateEnvVar, deleteEnvVar } from './env'


/**
 * A temp cabinet/.env, with the destination ASSERTED inside it.
 *
 * CABINET_ENV_PATH is owned here and not merely CABINET_ROOT: `actions/env.ts`
 * reads that variable, and a sweep that overrode only the root appended a test
 * secret to the live file during a previous pass.
 */
const ENV_BEFORE = 'EXISTING_KEY=already-here\n'
let testRoot = ''
const envFile = () => readFileSync(nodePath.join(testRoot, 'cabinet', '.env'), 'utf8')

function makeRoot(): void {
  testRoot = mkdtempSync(nodePath.join(tmpdir(), 'env-actions-'))
  mkdirSync(nodePath.join(testRoot, 'cabinet'), { recursive: true })
  const dest = nodePath.join(testRoot, 'cabinet', '.env')
  writeFileSync(dest, ENV_BEFORE)
  vi.stubEnv('CABINET_ROOT', testRoot)
  vi.stubEnv('CABINET_ENV_PATH', dest)
  if (!dest.startsWith(testRoot + nodePath.sep)) {
    throw new Error('refusing to run: the env-file path is outside the temp tree')
  }
}

function dropRoot(): void {
  if (testRoot) rmSync(testRoot, { recursive: true, force: true })
  testRoot = ''
}

beforeEach(() => {
  vi.clearAllMocks()
  // Enforcing posture: not the demo/dev bypass, so requireDashboardAuth
  // delegates to the (mocked) verifySession.
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
  mockGetEnvVars.mockResolvedValue({ SECRET_KEY: 'super-secret' })
  makeRoot()
})

afterEach(() => {
  vi.unstubAllEnvs()
  dropRoot()
})

describe('env actions — unauthenticated is refused, no side effect', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('getEnvVarsAction throws and never reads the real env (no secret leak)', async () => {
    await expect(getEnvVarsAction()).rejects.toThrow('Unauthorized')
    expect(mockGetEnvVars).not.toHaveBeenCalled()
  })

  it('addEnvVar returns Unauthorized and never shells out', async () => {
    expect(await addEnvVar('FOO', 'bar')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockWriteGuard).not.toHaveBeenCalled()
    expect(envFile()).toBe(ENV_BEFORE)
  })

  it('updateEnvVar returns Unauthorized and never shells out', async () => {
    expect(await updateEnvVar('FOO', 'bar')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockWriteGuard).not.toHaveBeenCalled()
    expect(envFile()).toBe(ENV_BEFORE)
  })

  it('deleteEnvVar returns Unauthorized and never shells out', async () => {
    expect(await deleteEnvVar('FOO')).toEqual({ success: false, error: 'Unauthorized' })
    expect(mockWriteGuard).not.toHaveBeenCalled()
    expect(envFile()).toBe(ENV_BEFORE)
  })
})

describe('env actions — authenticated proceeds', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('getEnvVarsAction returns the env map for an authed caller', async () => {
    expect(await getEnvVarsAction()).toEqual({ SECRET_KEY: 'super-secret' })
    expect(mockGetEnvVars).toHaveBeenCalledOnce()
  })

  it('addEnvVar reaches the write path AND lands the bytes for an authed caller', async () => {
    const res = await addEnvVar('FOO', 'bar')
    expect(res).toEqual({ success: true })
    expect(mockWriteGuard).toHaveBeenCalled()
    // The file, not the mock. The old arm was satisfied by a shell call whose
    // command exited 1 and changed nothing.
    expect(envFile()).toMatch(/^FOO=bar$/m)
  })
})
