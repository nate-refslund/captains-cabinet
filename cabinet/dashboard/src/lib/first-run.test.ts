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
