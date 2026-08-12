/**
 * createPassword — the first-run "choose your own password" action.
 *
 * Each arm is one way the single pre-auth window (no password yet) could be
 * abused, proven closed, PLUS the happy path proving the chosen password lands
 * in the same store the verifier reads — so login works right after, no restart.
 *
 * The real checkPassword / config-write / first-run logic run; only the session
 * mint (cookies), redirect, and request headers are mocked.
 */
import { afterEach, afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import nodePath from 'node:path'

const { mockCreateSession, mockRedirect, mockHeaders } = vi.hoisted(() => ({
  mockCreateSession: vi.fn(),
  mockRedirect: vi.fn(),
  mockHeaders: vi.fn(),
}))

vi.mock('next/navigation', () => ({ redirect: mockRedirect }))
vi.mock('next/headers', () => ({
  headers: mockHeaders,
  cookies: vi.fn(async () => ({ get: () => undefined, set: () => {}, delete: () => {} })),
}))
// Keep the REAL checkPassword (so "login works after create" is a real check);
// only the session mint is stubbed away from the cookie store.
vi.mock('@/lib/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth')>()
  return { ...actual, createSession: mockCreateSession }
})

import { createPassword } from './auth'
import { checkPassword } from '@/lib/auth'

const LOCAL = () => new Headers({ host: '127.0.0.1:3100' })
const REMOTE = () => new Headers({ host: 'cab.tail1234.ts.net', 'x-forwarded-for': '100.64.0.9' })

let testRoot = ''
let savedPassword: string | undefined
const envDest = () => nodePath.join(testRoot, 'cabinet', '.env')
const envText = () => readFileSync(envDest(), 'utf8')

function makeRoot(initial = 'DASHBOARD_PASSWORD=\nOTHER_KEY=keep-me\n'): void {
  testRoot = mkdtempSync(nodePath.join(tmpdir(), 'create-pw-'))
  mkdirSync(nodePath.join(testRoot, 'cabinet'), { recursive: true })
  writeFileSync(envDest(), initial)
  vi.stubEnv('CABINET_ROOT', testRoot)
  vi.stubEnv('CABINET_ENV_PATH', envDest())
}

beforeEach(() => {
  vi.clearAllMocks()
  savedPassword = process.env.DASHBOARD_PASSWORD
  delete process.env.DASHBOARD_PASSWORD // fresh first-run state
  vi.stubEnv('NODE_ENV', 'production')
  mockHeaders.mockReturnValue(LOCAL())
  makeRoot()
})

afterEach(() => {
  vi.unstubAllEnvs()
  if (testRoot) rmSync(testRoot, { recursive: true, force: true })
  testRoot = ''
  delete process.env.DASHBOARD_PASSWORD
})

afterAll(() => {
  if (savedPassword !== undefined) process.env.DASHBOARD_PASSWORD = savedPassword
})

function form(password: string, confirm = password): FormData {
  const fd = new FormData()
  fd.set('password', password)
  fd.set('confirm', confirm)
  return fd
}

describe('the happy path — the chosen password becomes the real one', () => {
  it('writes the password to cabinet/.env, sets it live, mints a session — and login then works', async () => {
    const chosen = 'sunshine-cabinet-2026'
    await createPassword(null, form(chosen))

    // 1. durable: the SAME store every secret lives in, other keys intact
    expect(envText()).toContain(`DASHBOARD_PASSWORD=${chosen}`)
    expect(envText()).toContain('OTHER_KEY=keep-me')
    // 2. live in-process
    expect(process.env.DASHBOARD_PASSWORD).toBe(chosen)
    // 3. session minted + landed on the dashboard
    expect(mockCreateSession).toHaveBeenCalledOnce()
    expect(mockRedirect).toHaveBeenCalledWith('/')
    // 4. login now works against the real verifier, and only for the real one
    expect(checkPassword(chosen)).toBe(true)
    expect(checkPassword('wrong-password-xx')).toBe(false)
  })

  it('preserves 0600 permissions on the env file it writes', async () => {
    const { statSync, chmodSync } = await import('node:fs')
    chmodSync(envDest(), 0o600)
    await createPassword(null, form('sunshine-cabinet-2026'))
    expect(statSync(envDest()).mode & 0o777).toBe(0o600)
  })
})

describe('first-run ONLY — never overwrite an existing password', () => {
  it('refuses when the live process already has a real password (no write, no session)', async () => {
    process.env.DASHBOARD_PASSWORD = 'already-a-real-secret'
    const before = envText()
    const res = await createPassword(null, form('sunshine-cabinet-2026'))
    expect(res).toEqual({ error: expect.stringMatching(/already set/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('refuses when the durable file already holds one, even if this process has not loaded it', async () => {
    // process env unset, but the file carries a real password
    rmSync(envDest())
    writeFileSync(envDest(), 'DASHBOARD_PASSWORD=already-on-disk-secret\n')
    const res = await createPassword(null, form('sunshine-cabinet-2026'))
    expect(res).toEqual({ error: expect.stringMatching(/already set/i) })
    expect(envText()).toContain('already-on-disk-secret')
    expect(mockCreateSession).not.toHaveBeenCalled()
  })
})

describe('local machine only — the first password cannot be set over the network', () => {
  it('refuses a request that arrived through a proxy / non-loopback host', async () => {
    mockHeaders.mockReturnValue(REMOTE())
    const before = envText()
    const res = await createPassword(null, form('sunshine-cabinet-2026'))
    expect(res).toEqual({ error: expect.stringMatching(/Cabinet computer/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })
})

describe('the strength + safety floor', () => {
  it('refuses a too-short password (nothing written)', async () => {
    const before = envText()
    const res = await createPassword(null, form('short'))
    expect(res).toEqual({ error: expect.stringMatching(/at least/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('refuses a shell-unsafe password (it would inject when cabinet/.env is sourced)', async () => {
    const before = envText()
    const res = await createPassword(null, form('pw$(touch /tmp/x)yz'))
    expect(res).toEqual({ error: expect.stringMatching(/letters, numbers/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('refuses a mismatched confirmation', async () => {
    const res = await createPassword(null, form('sunshine-cabinet-2026', 'different-one-2026'))
    expect(res).toEqual({ error: expect.stringMatching(/do not match/i) })
    expect(mockCreateSession).not.toHaveBeenCalled()
  })
})
