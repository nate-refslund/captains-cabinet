/**
 * A cabinet/.env VALUE CAN NEVER EXECUTE ON `source` — the sensor, run against a
 * real bash.
 *
 * WHAT THIS IS THE SENSOR FOR. cabinet/.env is written by `writeEnvValue`
 * (lib/config-write.ts) and by `setup-env.sh`, and then bash-`source`d by 30+
 * scripts, several under `set -a` (cabinet-spawn.sh, create-project.sh,
 * memory-reconcile.sh, resume-officer.sh, the cron wrappers…). The value's only
 * validation was a newline refusal, so a value of `FOO=$(touch /tmp/x)` — which
 * an operator can set through the dashboard's add-a-secret form — EXECUTED at
 * assignment the next time any of those scripts sourced the file. Command
 * substitution runs before the variable is ever read.
 *
 * WHY THE ASSERTION IS A REAL bash. The property is about what bash does on
 * `source`, so the test SHELLS OUT to bash: it writes the value through the real
 * writer, sources the resulting file with `set -a`, and checks BOTH that no
 * side-effect file was created AND that the variable holds the exact literal
 * string. A pure-JS assertion on the bytes could not tell an inert value from an
 * executing one — only bash can.
 *
 * RUN AGAINST THE PRE-FIX WRITER, the payload arm fails: the marker file exists.
 * That is the red this file was written to catch.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import {
  writeEnvValue,
  envValueLiteral,
  envValueUnliteral,
} from './config-write'

let dir: string
let envFile: string
let marker: string

beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), 'env-source-'))
  envFile = path.join(dir, '.env')
  marker = path.join(dir, 'PWNED')
  writeFileSync(envFile, 'EXISTING_KEY=already-here\n')
})

afterEach(() => {
  try {
    rmSync(dir, { recursive: true, force: true })
  } catch {
    /* disposable */
  }
})

/** `set -a; source .env; set +a; printf %s "$KEY"` in a real bash — returns the
 *  value bash actually assigned to KEY after sourcing the written file. */
function sourceAndRead(key: string): string {
  return execFileSync(
    'bash',
    ['-c', `set -a; source "${envFile}"; set +a; printf '%s' "$${key}"`],
    { encoding: 'utf8' }
  )
}

// Every one of these, written raw into an unquoted assignment, either executes
// or breaks the line. `${marker}` is substituted into the payload so a
// successful execution would create THIS test's marker file.
const payloads = (m: string): Array<[string, string]> => [
  ['command-substitution', `$(touch ${m})`],
  ['backtick', `\`touch ${m}\``],
  ['nested-in-text', `pre$(touch ${m})post`],
  ['parameter-expansion', '${HOME}'],
  ['semicolon-chain', `x; touch ${m}`],
  ['and-chain', `x && touch ${m}`],
  ['pipe', `x | touch ${m}`],
  ['redirect', `x > ${m}`],
  ['subshell', `(touch ${m})`],
  ['tilde', '~root/x'],
  ['space-splits-word', `a touch ${m}`],
  ['single-quote-in-value', `O'Brien-$(touch ${m})`],
  ['double-quote-with-subst', `"$(touch ${m})"`],
  ['backslash', 'a\\b\\c'],
  ['unicode', 'café-☕-Ünïcode'],
]

describe('a written .env value is inert when bash sources it — for any input', () => {
  for (const [name, payload] of payloads('MARK')) {
    it(`${name}: does not execute, and round-trips to the exact literal`, async () => {
      const mark = marker // absolute path, unique per test
      const realPayload = payload.replace('MARK', mark)
      await writeEnvValue(envFile, 'PWN', realPayload, { createIfMissing: true })

      // 1) Sourcing it must not run anything.
      const got = sourceAndRead('PWN')
      expect(existsSync(mark), `sourcing .env executed the payload (${name})`).toBe(false)

      // 2) The variable bash assigned must be the exact string we asked to store.
      expect(got).toBe(realPayload)

      // 3) And the in-process parser reads back the same logical value.
      const parsed = envValueUnliteral(
        readFileSync(envFile, 'utf8')
          .split('\n')
          .find((l) => l.startsWith('PWN='))!
          .slice('PWN='.length)
      )
      expect(parsed).toBe(realPayload)
    })
  }

  it('a plain value stays BARE (unquoted) — no consumer churn for the common case', async () => {
    await writeEnvValue(envFile, 'TOKEN', '70012345:AAE-token_x.y/z', { createIfMissing: true })
    expect(readFileSync(envFile, 'utf8')).toMatch(/^TOKEN=70012345:AAE-token_x\.y\/z$/m)
    expect(sourceAndRead('TOKEN')).toBe('70012345:AAE-token_x.y/z')
  })

  it('a connection string with & and ? is quoted, inert, and round-trips', async () => {
    const conn = 'postgresql://u:p%40ss@h:5432/db?sslmode=require&x=1'
    await writeEnvValue(envFile, 'NEON_CONNECTION_STRING', conn, { createIfMissing: true })
    // quoted on disk...
    expect(readFileSync(envFile, 'utf8')).toContain(`NEON_CONNECTION_STRING='${conn}'`)
    // ...literal after source (the bare form would background at `&`).
    expect(sourceAndRead('NEON_CONNECTION_STRING')).toBe(conn)
  })

  it('an empty value stays bare (KEY=), the first-run DASHBOARD_PASSWORD shape', async () => {
    await writeEnvValue(envFile, 'DASHBOARD_PASSWORD', '', { createIfMissing: true })
    expect(readFileSync(envFile, 'utf8')).toMatch(/^DASHBOARD_PASSWORD=$/m)
    expect(sourceAndRead('DASHBOARD_PASSWORD')).toBe('')
  })

  it('a newline is REFUSED — it cannot inject a second .env line', async () => {
    await expect(
      writeEnvValue(envFile, 'INJECTED', 'a\nSUPERUSER=yes', { createIfMissing: true })
    ).rejects.toThrow()
    expect(readFileSync(envFile, 'utf8')).not.toMatch(/^SUPERUSER=/m)
  })
})

describe('envValueLiteral / envValueUnliteral are exact inverses', () => {
  const cases = [
    '',
    'plain',
    '70012345:AAE-token',
    '-10012345',
    'postgresql://u:p@h/db',
    'postgresql://u:p@h/db?a=b&c=d',
    '$(touch x)',
    '`x`',
    '${x}',
    "O'Brien",
    "a'b'c",
    'has spaces',
    'quote"and`tick$and~tilde',
    'café-☕',
    'semi;colon|pipe&redirect>',
  ]
  for (const v of cases) {
    it(`round-trips: ${JSON.stringify(v)}`, () => {
      expect(envValueUnliteral(envValueLiteral(v))).toBe(v)
    })
  }

  it('bare only for the provably-safe set; everything else is single-quoted', () => {
    expect(envValueLiteral('plain-KEY_1.2:3/4=5+6@7%8,9')).toBe('plain-KEY_1.2:3/4=5+6@7%8,9')
    expect(envValueLiteral('')).toBe('')
    expect(envValueLiteral('has space')).toBe("'has space'")
    expect(envValueLiteral('$(x)')).toBe("'$(x)'")
    expect(envValueLiteral("a'b")).toBe("'a'\\''b'")
  })
})
