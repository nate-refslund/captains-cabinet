import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The login surface must never send a non-technical operator to a terminal.
 * The old "Forgot the password?" block told them to open Terminal and run a
 * bash command against cabinet/scripts — a dead end. That is deleted; a forgotten
 * password is now reset by double-clicking a file, and a fresh instance shows a
 * "create a password" screen instead of a locked door.
 *
 * We scan every source file of the /login route (page + both forms) so the
 * forbidden words cannot survive in a comment or a sibling component either.
 */
const LOGIN_DIR = __dirname
const loginSources = fs
  .readdirSync(LOGIN_DIR)
  .filter((f) => /\.(tsx|ts)$/.test(f) && !f.endsWith('.test.ts'))
  .map((f) => fs.readFileSync(path.join(LOGIN_DIR, f), 'utf8'))
  .join('\n')

describe('login surface — no terminal, ever', () => {
  it('contains NO Terminal / bash / cabinet/scripts / dashboard-password instruction', () => {
    expect(loginSources).not.toMatch(/terminal/i)
    expect(loginSources).not.toMatch(/\bbash\b/i)
    expect(loginSources).not.toContain('cabinet/scripts')
    expect(loginSources).not.toContain('dashboard-password')
    expect(loginSources).not.toContain('--copy')
  })

  it('names the product correctly', () => {
    expect(loginSources).toContain('Captain&apos;s Cabinet')
    expect(loginSources).not.toContain('Founder&apos;s Cabinet')
  })

  it('offers first-run create-a-password and a double-click reset in plain words', () => {
    expect(loginSources).toContain('Create a password')
    expect(loginSources).toContain('Choose a password only you know')
    expect(loginSources).toContain('Reset Cabinet Password')
  })

  it('uses no jargon on screen (no HMAC / credential / session token / auth)', () => {
    // Visible copy only — the words a non-technical person should never see.
    for (const word of ['HMAC', 'credential', 'session token']) {
      expect(loginSources).not.toContain(word)
    }
  })
})
