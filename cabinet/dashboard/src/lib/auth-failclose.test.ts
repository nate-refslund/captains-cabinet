/**
 * lib/auth.ts fail-close coverage (mirrors verdict.ts:47 doorSecret).
 *
 * The session HMAC secret is resolved PER CALL. In production an unset or
 * 'changeme' DASHBOARD_PASSWORD yields NO secret, so the auth surface refuses
 * to sign or verify against the publicly-known dev fallback — otherwise an
 * attacker who knows 'changeme' could forge a passing cabinet_session cookie.
 * Outside production the 'changeme' fallback stays for local dev/test.
 *
 * next/headers cookies() is mocked so verifySession/createSession run in a
 * plain node test; the module reads process.env per call, so vi.stubEnv is
 * enough (no dynamic-import dance).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockCookies, mockCookieStore } = vi.hoisted(() => {
  const store = { get: vi.fn(), set: vi.fn(), delete: vi.fn() }
  return { mockCookies: vi.fn(async () => store), mockCookieStore: store }
})

vi.mock('next/headers', () => ({ cookies: mockCookies }))

import { verifySession, createSession, checkPassword } from './auth'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => vi.unstubAllEnvs())

describe('production + unset/changeme password → fail-closed', () => {
  for (const pw of ['', 'changeme']) {
    describe(`DASHBOARD_PASSWORD=${JSON.stringify(pw)}`, () => {
      beforeEach(() => {
        vi.stubEnv('NODE_ENV', 'production')
        vi.stubEnv('DASHBOARD_PASSWORD', pw)
      })

      it('verifySession returns false even when a cookie is present', async () => {
        // A forged, well-formed cookie must not validate against 'changeme'.
        mockCookieStore.get.mockReturnValue({ value: 'sometoken.somesig' })
        expect(await verifySession()).toBe(false)
      })

      it('createSession refuses to mint a session (throws), never sets a cookie', async () => {
        await expect(createSession()).rejects.toThrow(/DASHBOARD_PASSWORD/)
        expect(mockCookieStore.set).not.toHaveBeenCalled()
      })

      it("checkPassword('changeme') is false — no login with the public dev secret", async () => {
        expect(checkPassword('changeme')).toBe(false)
        expect(checkPassword('')).toBe(false)
      })
    })
  }
})

describe('production + a real password → normal operation, round-trips', () => {
  const REAL = 'a-real-strong-password'
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('DASHBOARD_PASSWORD', REAL)
  })

  it('createSession sets a cookie and verifySession accepts that exact value', async () => {
    let signed = ''
    mockCookieStore.set.mockImplementation((_name: string, value: string) => {
      signed = value
    })
    await createSession()
    expect(signed).toMatch(/^[a-f0-9]+\.[a-f0-9]+$/)

    mockCookieStore.get.mockReturnValue({ value: signed })
    expect(await verifySession()).toBe(true)
  })

  it('a cookie signed with the wrong secret does not verify', async () => {
    mockCookieStore.get.mockReturnValue({ value: 'token.deadbeef' })
    expect(await verifySession()).toBe(false)
  })

  it('checkPassword matches the real password only', async () => {
    expect(checkPassword(REAL)).toBe(true)
    expect(checkPassword('changeme')).toBe(false)
  })
})

describe('non-production keeps the changeme dev fallback', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('DASHBOARD_PASSWORD', '')
  })

  it("checkPassword('changeme') is true for local dev convenience", async () => {
    expect(checkPassword('changeme')).toBe(true)
  })

  it('createSession works in dev and verifySession round-trips', async () => {
    let signed = ''
    mockCookieStore.set.mockImplementation((_n: string, v: string) => {
      signed = v
    })
    await createSession()
    mockCookieStore.get.mockReturnValue({ value: signed })
    expect(await verifySession()).toBe(true)
  })
})
