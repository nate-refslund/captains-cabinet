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
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
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
import { envValueLiteral, parseEnvDocument } from '@/lib/config-write'
import { PASSWORD_MAX_LENGTH } from '@/lib/first-run'

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

  // A shell-unsafe password is no longer refused — the writer makes it inert
  // (see the round-trip block below). What IS still refused is a control
  // character: it cannot be typed on purpose, so it is always a paste accident,
  // and a newline would additionally split this line-oriented file.
  it.each([
    ['a newline', 'pasted-line' + String.fromCharCode(10) + 'cabinet'],
    ['a tab', 'tabbed' + String.fromCharCode(9) + 'cabinet-2026'],
    ['a NUL', 'nul' + String.fromCharCode(0) + 'cabinet-2026'],
  ])('refuses a password containing %s (nothing written, no session)', async (_label, pw) => {
    const before = envText()
    const res = await createPassword(null, form(pw))
    expect(res).toEqual({ error: expect.stringMatching(/invisible character/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('refuses a password that is only spaces', async () => {
    const before = envText()
    const res = await createPassword(null, form('          '))
    expect(res).toEqual({ error: expect.stringMatching(/only spaces/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it(`refuses a password longer than ${PASSWORD_MAX_LENGTH} characters`, async () => {
    const before = envText()
    const res = await createPassword(null, form('x'.repeat(PASSWORD_MAX_LENGTH + 1)))
    expect(res).toEqual({ error: expect.stringMatching(/longer than/i) })
    expect(envText()).toBe(before)
    expect(mockCreateSession).not.toHaveBeenCalled()
  })

  it('refuses a mismatched confirmation', async () => {
    const res = await createPassword(null, form('sunshine-cabinet-2026', 'different-one-2026'))
    expect(res).toEqual({ error: expect.stringMatching(/do not match/i) })
    expect(mockCreateSession).not.toHaveBeenCalled()
  })
})

/**
 * THE ROUND TRIP, END TO END, FOR PASSWORDS BUILT TO BREAK IT.
 *
 * WHERE THE PASSWORD ACTUALLY GOES. There is no hash anywhere in this flow, by
 * design and on the record (`actions/auth.createPassword`): the chosen password
 * IS the HMAC key that signs the session cookie (`lib/auth.resolveSecret`), so
 * it is stored as recoverable plaintext in `DASHBOARD_PASSWORD` in cabinet/.env
 * — the same store every other secret lives in, 0600, never printed. A one-way
 * hash would make cookie signing impossible.
 *
 * WHICH MAKES THE SHELL THE HAZARD, not the crypto. cabinet/.env is bash
 * `source`d by 30+ scripts, several under `set -a`. So each arm below runs the
 * WHOLE path — choose on the first-run screen → written by the real writer →
 * SOURCED BY A REAL BASH → read back → sign in with the real verifier — and
 * asserts four things at once:
 *
 *   1. no side effect: a `$(…)`/backtick payload never executes on source;
 *   2. bash assigns the EXACT string the operator typed, byte for byte;
 *   3. the in-process reader (`parseEnvDocument`) agrees with bash;
 *   4. `checkPassword` accepts it — and rejects near-misses, including the
 *      TRIMMED form, which is what proves the spaces were never eaten.
 *
 * A pure-JS assertion on the file's bytes could not tell an inert value from an
 * executing one. Only bash can, so bash is what runs.
 */
describe('hostile passwords survive the real round trip: set → source → sign in', () => {
  /**
   * `set -a; source .env` in a real bash; returns what bash assigned.
   *
   * THE ENV IS DELIBERATELY EMPTY BUT FOR PATH. `createPassword` sets
   * `process.env.DASHBOARD_PASSWORD` in THIS process, and a child bash inherits
   * it — so with the parent's environment this call happily prints the right
   * answer even when the file it was meant to read never assigned anything. It
   * did, while this sensor was being written: a `source` that ERRORED out
   * ("cabinet: command not found") still "passed", because the value being
   * printed came from the parent, not the file. An empty env is what makes this
   * a measurement of the FILE.
   */
  const sourceAndRead = (): string =>
    execFileSync(
      'bash',
      ['-c', `set -a; source "${envDest()}"; set +a; printf '%s' "$DASHBOARD_PASSWORD"`],
      {
        encoding: 'utf8',
        // Cast because the app's ProcessEnv augmentation makes NODE_ENV required;
        // handing bash a genuinely minimal env is the whole point of this call.
        env: { PATH: process.env.PATH ?? '/usr/bin:/bin' } as unknown as NodeJS.ProcessEnv,
      }
    )

  /** The raw text after `DASHBOARD_PASSWORD=` — the bytes actually on disk. */
  const storedLiteral = (): string =>
    envText()
      .split('\n')
      .find((l) => l.startsWith('DASHBOARD_PASSWORD='))!
      .slice('DASHBOARD_PASSWORD='.length)

  const ch = (code: number) => String.fromCharCode(code)

  // MARKER is replaced per test with a path inside this test's own temp root,
  // so a payload that DID execute would leave a file this test can see.
  const hostile: Array<[string, string]> = [
    ['a single quote', "O'Brien's cabinet"],
    ['two single quotes in a row', "double''quote-cabinet"],
    ['a double quote', 'say "hello" cabinet'],
    ['a backslash', 'back' + ch(92) + 'slash' + ch(92) + 'pass'],
    ['a dollar sign', '$HOME-is-where-it-is'],
    ['a backtick', '`whoami`-cabinet'],
    ['command substitution', 'pw$(touch MARKER)yz'],
    ['a backticked command', 'pw`touch MARKER`yz'],
    ['a semicolon chain', 'pw; touch MARKER; x'],
    ['interior spaces', 'correct horse battery staple'],
    ['leading and trailing spaces', '  padded password  '],
    ['a percent sign', '100%-secure-please'],
    ['Danish letters', 'blåbærgrød-2026'],
    ['a euro sign', '€uro-cabinet-2026'],
    ['emoji', '🔐🔐-cabinet-2026'],
    ['a glob and a pipe', 'pw*|touch MARKER'],
  ]

  it.each(hostile)('%s: set, sourced by bash, read back, and signs in', async (_label, template) => {
    const marker = nodePath.join(testRoot, 'PWNED')
    const chosen = template.replace('MARKER', marker)
    // Guard the fixture itself: a payload long enough to trip the ceiling would
    // turn this into a length test wearing a round-trip test's name.
    expect(Array.from(chosen).length).toBeLessThanOrEqual(PASSWORD_MAX_LENGTH)

    const res = await createPassword(null, form(chosen))
    expect(res, `createPassword refused ${JSON.stringify(chosen)}`).toBeUndefined()

    // The raw password DOES land in the file (it is the cookie-signing key), so
    // it must land through the safe-quote layer and nowhere else.
    expect(storedLiteral()).toBe(envValueLiteral(chosen))
    // Nothing dangerous is ever written bare: anything outside the provably
    // literal set comes out single-quoted.
    if (storedLiteral() !== chosen) {
      expect(storedLiteral().startsWith("'")).toBe(true)
      expect(storedLiteral().endsWith("'")).toBe(true)
    }

    // 1 + 2: a real bash sources it — no side effect, exact literal.
    const fromBash = sourceAndRead()
    expect(existsSync(marker), 'sourcing cabinet/.env executed the password').toBe(false)
    expect(fromBash).toBe(chosen)

    // 3: the in-process reader agrees with bash.
    expect(parseEnvDocument(envText()).DASHBOARD_PASSWORD).toBe(chosen)

    // 4: sign in with it, and only with it.
    expect(process.env.DASHBOARD_PASSWORD).toBe(chosen)
    expect(checkPassword(chosen)).toBe(true)
    expect(checkPassword(chosen + 'x')).toBe(false)
    if (chosen !== chosen.trim()) {
      expect(
        checkPassword(chosen.trim()),
        'the trimmed form must NOT sign in — the spaces are part of the password'
      ).toBe(false)
    }

    // Untouched neighbours: one line edited, the rest of the file intact.
    expect(envText()).toContain('OTHER_KEY=keep-me')
    expect(mockCreateSession).toHaveBeenCalledOnce()
  })

  it('the very first write of a cabinet lifetime takes a hostile password too (no .env yet)', async () => {
    // A fresh hatch has no cabinet/.env at all; createIfMissing is the path that
    // creates it, and it must quote just as carefully as the edit path.
    const marker = nodePath.join(testRoot, 'PWNED-FRESH')
    rmSync(envDest())
    writeFileSync(envDest(), '')
    const chosen = `fresh$(touch ${marker}) cabinet`
    expect(Array.from(chosen).length).toBeLessThanOrEqual(PASSWORD_MAX_LENGTH)

    expect(await createPassword(null, form(chosen))).toBeUndefined()
    expect(sourceAndRead()).toBe(chosen)
    expect(existsSync(marker)).toBe(false)
    expect(checkPassword(chosen)).toBe(true)
  })

  it('the password is never written a second time, in the clear, anywhere else in the file', async () => {
    const chosen = "O'Brien's cabinet"
    await createPassword(null, form(chosen))
    const lines = envText().split('\n').filter((l) => l.includes('Brien'))
    expect(lines).toEqual([`DASHBOARD_PASSWORD=${envValueLiteral(chosen)}`])
  })
})
