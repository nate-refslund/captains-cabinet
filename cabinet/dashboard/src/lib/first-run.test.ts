// first-run.ts — the pure security decisions behind the first-run password flow.
// These gate the one pre-auth window (no password set yet), so each arm below
// is one way that window could be abused, proven closed.

import { describe, it, expect } from 'vitest'
import {
  PASSWORD_MIN_LENGTH,
  hasRealPassword,
  validateChosenPassword,
  isLocalRequest,
} from './first-run'

describe('hasRealPassword — one definition of "a password is configured"', () => {
  it('false when unset (the first-run state)', () => {
    expect(hasRealPassword({})).toBe(false)
    expect(hasRealPassword({ DASHBOARD_PASSWORD: '' })).toBe(false)
  })

  it("false on the well-known dev placeholder 'changeme'", () => {
    expect(hasRealPassword({ DASHBOARD_PASSWORD: 'changeme' })).toBe(false)
  })

  it('true for any real value', () => {
    expect(hasRealPassword({ DASHBOARD_PASSWORD: 'a-real-secret-1' })).toBe(true)
  })
})

describe('validateChosenPassword — plain-language floor + shell safety', () => {
  const good = 'sunshine-cabinet-2026'

  it('accepts a reasonable password typed identically twice', () => {
    expect(validateChosenPassword(good, good)).toEqual({ ok: true })
  })

  it(`rejects anything under ${PASSWORD_MIN_LENGTH} characters`, () => {
    const short = 'a'.repeat(PASSWORD_MIN_LENGTH - 1)
    const r = validateChosenPassword(short, short)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/at least/i)
  })

  it('rejects a mismatched confirmation', () => {
    const r = validateChosenPassword(good, good + 'x')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/do not match/i)
  })

  // cabinet/.env is SOURCED by bash at officer/dashboard start, so a value with
  // a space or a shell metacharacter would break — or, with $()/backticks,
  // EXECUTE — on restart. The charset gate is the wall against that.
  it.each([
    ['a space', 'my pass word 12'],
    ['a dollar sign', 'passwordwith$FOO'],
    ['a backtick', 'password`whoami`x'],
    ['command substitution', 'pw$(touch /tmp/x)yz'],
    ['a semicolon', 'password;rm-rf-x'],
    ['a single quote', "password'orx'yz"],
    ['a double quote', 'password"orx"yz'],
  ])('rejects a password containing %s', (_label, pw) => {
    const r = validateChosenPassword(pw, pw)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/letters, numbers/i)
  })

  it('accepts the safe symbol subset', () => {
    const pw = 'Cabinet.2026_ok-@%^+=:,'
    expect(validateChosenPassword(pw, pw)).toEqual({ ok: true })
  })
})

describe('isLocalRequest — the first password may be set from the box only', () => {
  const h = (headers: Record<string, string>) => new Headers(headers)

  it('true for a direct loopback request (no proxy headers)', () => {
    expect(isLocalRequest(h({ host: '127.0.0.1:3100' }))).toBe(true)
    expect(isLocalRequest(h({ host: 'localhost:3100' }))).toBe(true)
    expect(isLocalRequest(h({ host: '[::1]:3100' }))).toBe(true)
    expect(isLocalRequest(h({ host: 'localhost' }))).toBe(true)
  })

  it('false when any proxy hop is present, even to a loopback host', () => {
    expect(isLocalRequest(h({ host: '127.0.0.1:3100', 'x-forwarded-for': '100.64.0.9' }))).toBe(false)
    expect(isLocalRequest(h({ host: '127.0.0.1:3100', 'x-forwarded-host': 'cab.tail.ts.net' }))).toBe(false)
    expect(isLocalRequest(h({ host: '127.0.0.1:3100', 'x-real-ip': '100.64.0.9' }))).toBe(false)
  })

  it('false for a non-loopback Host (reached over the tailnet/LAN)', () => {
    expect(isLocalRequest(h({ host: 'cabinet.tail1234.ts.net' }))).toBe(false)
    expect(isLocalRequest(h({ host: '192.168.1.50:3100' }))).toBe(false)
  })

  it('false when the Host header is absent', () => {
    expect(isLocalRequest(h({}))).toBe(false)
  })
})

// The mock bags above never carried the headers Next SYNTHESISES, so the gate
// tested green while the live control refused the on-box operator. These two
// fixtures are the ACTUAL `await headers()` bags captured from a real Next 16
// `next start` server action (2026-08-12): a genuine loopback curl POST to
// /login, and a remote hop simulated tailscale-serve style (X-Forwarded-* set to
// a tailnet peer, Origin matched so Next's action check passed and the action
// ran). They are transcribed verbatim from the server's own header dump, not
// hand-authored — this is the regression the unit mock could not see.
describe('isLocalRequest — REAL Next 16 runtime header bags (captured, not mocked)', () => {
  const bag = (pairs: [string, string][]) => new Headers(pairs)

  // Captured verbatim from the running server on a direct 127.0.0.1 POST. Next
  // injected x-forwarded-host/-port/-proto/-for itself, all with LOOPBACK values.
  const REAL_LOCAL: [string, string][] = [
    ['host', '127.0.0.1:3197'],
    ['origin', 'http://127.0.0.1:3197'],
    ['x-forwarded-host', '127.0.0.1:3197'],
    ['x-forwarded-port', '3197'],
    ['x-forwarded-proto', 'http'],
    ['x-forwarded-for', '127.0.0.1'],
  ]

  // Captured verbatim when the same POST arrived carrying a proxy's forwarded
  // headers; Next PRESERVED them, so the non-loopback client is visible.
  const REAL_REMOTE: [string, string][] = [
    ['host', '127.0.0.1:3197'],
    ['origin', 'http://cabinet.tail1234.ts.net'],
    ['x-forwarded-host', 'cabinet.tail1234.ts.net'],
    ['x-forwarded-for', '100.64.0.9'],
    ['x-real-ip', '100.64.0.9'],
    ['x-forwarded-port', '3197'],
    ['x-forwarded-proto', 'http'],
  ]

  it('true for the real on-box loopback bag (the bug: was refused)', () => {
    expect(isLocalRequest(bag(REAL_LOCAL))).toBe(true)
  })

  it('false for the real remote-proxied bag (security still holds)', () => {
    expect(isLocalRequest(bag(REAL_REMOTE))).toBe(false)
  })

  it('IPv6 loopback with Next-injected forwarded headers is still local', () => {
    expect(
      isLocalRequest(
        bag([
          ['host', '[::1]:3197'],
          ['x-forwarded-host', '[::1]:3197'],
          ['x-forwarded-for', '::1'],
        ])
      )
    ).toBe(true)
  })

  it('a remote hop anywhere in a multi-hop X-Forwarded-For fails', () => {
    // client (remote) → proxy (loopback): the chain must be all-loopback.
    expect(
      isLocalRequest(
        bag([
          ['host', '127.0.0.1:3197'],
          ['x-forwarded-for', '100.64.0.9, 127.0.0.1'],
        ])
      )
    ).toBe(false)
  })
})
