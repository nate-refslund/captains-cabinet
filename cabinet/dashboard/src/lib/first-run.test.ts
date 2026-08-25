// first-run.ts — the pure security decisions behind the first-run password flow.
// These gate the one pre-auth window (no password set yet), so each arm below
// is one way that window could be abused, proven closed.

import { describe, it, expect } from 'vitest'
import {
  PASSWORD_MAX_LENGTH,
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

describe('validateChosenPassword — a floor people accept, and a keyboard they can use whole', () => {
  const good = 'sunshine cabinet'

  /** One character by code. Used instead of escapes so every hostile character
   *  below is unambiguous in the source and none of them is invisible. */
  const ch = (code: number) => String.fromCharCode(code)

  it('accepts a reasonable password typed identically twice', () => {
    expect(validateChosenPassword(good, good)).toEqual({ ok: true })
  })

  it('rejects a mismatched confirmation', () => {
    const r = validateChosenPassword(good, good + 'x')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/do not match/i)
  })

  // -------------------------------------------------------------------------
  // THE FLOOR AND THE CEILING, AT THEIR EXACT EDGES. An off-by-one on an
  // inclusive bound is invisible to a test that only probes the middle, and
  // "8 characters" on screen has to mean 8 accepted and 7 refused.
  // -------------------------------------------------------------------------
  const a = (n: number) => 'a'.repeat(n)

  it.each([
    ['an empty box', ''],
    ['a single character', a(1)],
    [`${PASSWORD_MIN_LENGTH - 1} characters — one under the floor`, a(PASSWORD_MIN_LENGTH - 1)],
  ])('rejects %s as too short', (_label, pw) => {
    const r = validateChosenPassword(pw, pw)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/at least/i)
  })

  it(`accepts EXACTLY ${PASSWORD_MIN_LENGTH} characters — the floor is inclusive`, () => {
    const pw = a(PASSWORD_MIN_LENGTH)
    expect(validateChosenPassword(pw, pw)).toEqual({ ok: true })
  })

  it(`accepts EXACTLY ${PASSWORD_MAX_LENGTH} characters — the ceiling is inclusive`, () => {
    const pw = a(PASSWORD_MAX_LENGTH)
    expect(validateChosenPassword(pw, pw)).toEqual({ ok: true })
  })

  it(`rejects ${PASSWORD_MAX_LENGTH + 1} characters, in plain words`, () => {
    const pw = a(PASSWORD_MAX_LENGTH + 1)
    const r = validateChosenPassword(pw, pw)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/longer than/i)
  })

  // JavaScript's `.length` counts UTF-16 units, so an emoji counts as TWO. A
  // floor written that way would accept SEVEN emoji as "14 characters" — a
  // password shorter than the screen promises — and a ceiling written that way
  // would refuse 65 emoji the operator can see are 65 characters. Both ends are
  // counted in CODE POINTS instead, and both ends are pinned here.
  describe('length is counted the way the person typing counts it', () => {
    const LOCK = '🔐' // one code point, two UTF-16 units

    it(`rejects ${PASSWORD_MIN_LENGTH - 1} emoji even though .length reads ${(PASSWORD_MIN_LENGTH - 1) * 2}`, () => {
      const pw = LOCK.repeat(PASSWORD_MIN_LENGTH - 1)
      expect(pw.length).toBe((PASSWORD_MIN_LENGTH - 1) * 2) // the trap itself
      const r = validateChosenPassword(pw, pw)
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.error).toMatch(/at least/i)
    })

    it(`accepts ${PASSWORD_MIN_LENGTH} emoji`, () => {
      const pw = LOCK.repeat(PASSWORD_MIN_LENGTH)
      expect(validateChosenPassword(pw, pw)).toEqual({ ok: true })
    })

    it(`accepts ${PASSWORD_MAX_LENGTH} emoji and refuses one more`, () => {
      const atCeiling = LOCK.repeat(PASSWORD_MAX_LENGTH)
      expect(atCeiling.length).toBe(PASSWORD_MAX_LENGTH * 2) // the trap at the other end
      expect(validateChosenPassword(atCeiling, atCeiling)).toEqual({ ok: true })
      const over = LOCK.repeat(PASSWORD_MAX_LENGTH + 1)
      const r = validateChosenPassword(over, over)
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.error).toMatch(/longer than/i)
    })
  })

  // -------------------------------------------------------------------------
  // EVERY CHARACTER A KEYBOARD PRODUCES IS ALLOWED (Captain, 2026-08-25:
  // "allow all symbols"). Every row below was REFUSED before this change, by a
  // charset gate that existed because cabinet/.env is bash-`source`d and the
  // writer used to emit values raw. The writer now emits them through
  // `config-write.envValueLiteral`, which single-quotes anything not provably
  // literal — proven inert against a real bash in `env-source-safety.test.ts`,
  // and proven end-to-end from this screen (set → source → sign in) in
  // `actions/create-password.test.ts`. These rows are the sensor that the gate
  // stays gone.
  // -------------------------------------------------------------------------

  /** Every printable ASCII character, space (32) through tilde (126), at once —
   *  so no symbol can be quietly re-banned without this row going red. */
  const ALL_PRINTABLE_ASCII = Array.from({ length: 126 - 32 + 1 }, (_, i) => ch(32 + i)).join('')

  it.each([
    ['a single quote', "O'Brien's cabinet"],
    ['a double quote', 'say "hello" cabinet'],
    ['a backslash', 'back' + ch(92) + 'slash' + ch(92) + 'pass'],
    ['a dollar sign', '$HOME-is-where-it-is'],
    ['a backtick', '`whoami`-cabinet'],
    ['command substitution', 'pw$(id)-cabinet'],
    ['a semicolon chain', 'pw;touch nope;x'],
    ['interior spaces', 'correct horse battery staple'],
    ['leading and trailing spaces', '  padded password  '],
    ['a percent sign', '100%-secure-please'],
    ['Danish letters', 'blåbærgrød-2026'],
    ['a euro sign', '€uro-cabinet-2026'],
    ['emoji', '🔐🔐-cabinet-2026'],
    ['every printable ASCII character at once', ALL_PRINTABLE_ASCII],
  ])('accepts a password containing %s', (_label, pw) => {
    expect(validateChosenPassword(pw, pw)).toEqual({ ok: true })
  })

  it('a space at either end is PART of the password, never trimmed away', () => {
    const padded = '  padded password  '
    expect(validateChosenPassword(padded, padded)).toEqual({ ok: true })
    // The trimmed form is therefore a DIFFERENT password: confirming with it
    // must fail, which is what proves nothing silently ate the spaces.
    const r = validateChosenPassword(padded, padded.trim())
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/do not match/i)
  })

  // -------------------------------------------------------------------------
  // THE TWO THINGS STILL REFUSED. Both are about the PASSWORD — one that could
  // never be re-typed, or one indistinguishable from an empty box — and not
  // about the file it lands in.
  // -------------------------------------------------------------------------
  it.each([
    ['a newline (the paste accident)', 'pasted-line' + ch(10) + 'cabinet'],
    ['a carriage return', 'pasted-line' + ch(13) + 'cabinet'],
    ['a tab', 'tabbed' + ch(9) + 'cabinet-2026'],
    ['a NUL', 'nul' + ch(0) + 'cabinet-2026'],
    ['an escape', 'esc' + ch(27) + 'cabinet-2026'],
    ['DEL', 'del' + ch(127) + 'cabinet-2026'],
    ['a C1 control', 'c1' + ch(133) + 'cabinet-2026'],
  ])('rejects %s — it cannot be typed on purpose', (_label, pw) => {
    const r = validateChosenPassword(pw, pw)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/invisible character/i)
  })

  it('rejects a password that is only spaces, however long', () => {
    const pw = ' '.repeat(PASSWORD_MIN_LENGTH + 4)
    const r = validateChosenPassword(pw, pw)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toMatch(/only spaces/i)
  })

  it('but spaces are fine as long as something else is there too', () => {
    const pw = '        x'
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
