/**
 * /evidence static contracts (grep-ratchet style, cloned from
 * components/receipts/receipts-static.test.ts):
 *
 *  A. READ-ONLY BY CONSTRUCTION — the page, the row components, the action
 *     and the read model never grow buttons, forms, client JS, mutation
 *     endpoints, fs/Redis writes, or ANY mutating evidence verb. Phase 3's
 *     one designed write (Captain labels) is a token-gated CLI harness —
 *     it must never appear here, so the spawn surface is pinned to the
 *     read model alone, shell:false, with a fixed argv whose only verb is
 *     `verify`.
 *  B. FAIL-CLOSED + HONESTY STRINGS — the verification-first serve order,
 *     the explicit UNVERIFIED red badge, the honest-empty gate, the counted
 *     corruption notes, the untrusted-observations boundary and the
 *     producer-asserted basis caveat are load-bearing and pinned.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const DASH = path.resolve(__dirname, '..', '..', '..')
const src = (...rel: string[]) =>
  fs.readFileSync(path.join(DASH, 'src', ...rel), 'utf8')

const PAGE = ['app', '(authenticated)', 'evidence', 'page.tsx']
const ROW = ['components', 'evidence', 'evidence-row.tsx']
const ACTION = ['actions', 'evidence.ts']
const LIB = ['lib', 'evidence', 'read.ts']

const FS_WRITE_VERBS =
  /\b(writeFile|writeFileSync|appendFile|appendFileSync|unlink|unlinkSync|rm|rmSync|rmdir|rmdirSync|mkdir|mkdirSync|rename|renameSync|chmod|chmodSync|symlink|symlinkSync|truncate|truncateSync|cp|cpSync|copyFile|copyFileSync|writev|createWriteStream)\s*\(/

describe('A. /evidence is read-only by construction', () => {
  it('page + rows: server-rendered, no buttons, no forms, no client JS', () => {
    for (const [name, rel] of [
      ['evidence page', PAGE],
      ['evidence rows', ROW],
    ] as const) {
      const text = src(...rel)
      expect(text, name).not.toMatch(/['"]use client['"]/)
      expect(text, name).not.toMatch(/<button/i)
      expect(text, name).not.toMatch(/<form/i)
      expect(text, name).not.toMatch(/onClick/)
      expect(text, name).not.toMatch(/dangerouslySetInnerHTML/)
      expect(text, name).not.toMatch(/fetch\(/)
    }
  })

  it('the row components import no actions (render-only props in)', () => {
    expect(src(...ROW)).not.toMatch(/@\/actions\//)
  })

  it('actions/evidence.ts exports exactly one read (listEvidence), gated before it reads', () => {
    const text = src(...ACTION)
    expect(text).toMatch(/['"]use server['"]/)
    const fnExports = text.match(/export\s+(?:async\s+)?function\s+(\w+)/g) ?? []
    expect(fnExports).toEqual(['export async function listEvidence'])
    expect(text).not.toMatch(FS_WRITE_VERBS)
    expect(text).not.toMatch(/@\/lib\/redis|ioredis/)
    expect(text).not.toMatch(/child_process|execFile|spawn/)
    expect(text).not.toMatch(/revalidatePath/)
    // Auth is the FIRST thing that happens — the store read sits behind it.
    const authAt = text.indexOf('requireDashboardAuth()')
    const readAt = text.indexOf('readEvidence(')
    expect(authAt).toBeGreaterThan(-1)
    expect(readAt).toBeGreaterThan(-1)
    expect(authAt).toBeLessThan(readAt)
  })

  it('the read model touches the filesystem read-only, no Redis, no cache mutation', () => {
    const text = src(...LIB)
    expect(text).not.toMatch(FS_WRITE_VERBS)
    expect(text).not.toMatch(/@\/lib\/redis|ioredis/)
    expect(text).not.toMatch(/revalidatePath/)
  })

  it('the ONLY subprocess in the family is the read model verifier spawn — fixed argv, shell:false, verb `verify`', () => {
    // page / rows / action: no subprocess machinery at all
    for (const rel of [PAGE, ROW, ACTION]) {
      expect(src(...rel)).not.toMatch(/child_process|execFile|spawn/)
    }
    const lib = src(...LIB)
    // spawn is allowed here, but pinned: never a shell, never interpolated
    expect(lib).toMatch(/shell: false/)
    expect(lib).toMatch(/argv: \['-m', 'framework\.evidence', '--store', dir, 'verify'\]/)
    expect(lib).not.toMatch(/argv[^\n]*\$\{/)
    // no shell-string subprocess API — spawn(argv) only ((?<!\.) spares
    // the read-only RegExp.prototype.exec calls)
    expect(lib).not.toMatch(/(?<!\.)\bexec(File)?(Sync)?\s*\(/)
    // no mutating or projection-widening CLI verb may ever ride this spawn
    for (const verb of ["'purge'", "'retain'", "'export'", "'grant-token'", "'control'", "'project'"]) {
      expect(lib, `forbidden verb ${verb}`).not.toContain(verb)
    }
    // the Captain capability token never enters this surface (mentioning it
    // in doctrine comments is fine; presenting/reading it is not)
    expect(lib).not.toMatch(/--captain-token|CABINET_CAPTAIN_TOKEN/)
    // the germline onboarding bridge is cloned discipline, never a coupling
    expect(lib).not.toMatch(/@\/lib\/onboarding\/bridge/)
  })

  it('the store root is fixed server-side — no env override, no caller segment', () => {
    const lib = src(...LIB)
    expect(lib).toMatch(/cabinetPath\('instance', 'evidence', 'v1'\)/)
    // naming the Python-side env var in the doctrine comment is fine;
    // READING it (an override) is not
    expect(lib).not.toMatch(/process\.env\.CABINET_EVIDENCE_DIR/)
  })
})

describe('B. fail-closed display + honesty strings are load-bearing', () => {
  it('the page carries the honest-empty, cap, corruption and force-dynamic notes', () => {
    const text = src(...PAGE)
    expect(text).toMatch(/no evidence trials yet — the store is honestly empty/)
    expect(text).toMatch(/showing latest/)
    expect(text).toMatch(/skipped/)
    expect(text).toMatch(/never guessed at/)
    expect(text).toMatch(/force-dynamic/)
    // honest-empty is GATED on zero unreadable ledgers
    expect(text).toMatch(/skippedFiles === 0/)
    expect(text).toMatch(/PROOF:/)
  })

  it('UNVERIFIED trials are explicit, red, reasoned — and filters never hide them', () => {
    const page = src(...PAGE)
    expect(page).toMatch(/UNVERIFIED/)
    expect(page).toMatch(/filters\s+never hide them/)
    const row = src(...ROW)
    expect(row).toMatch(/UNVERIFIED/)
    expect(row).toMatch(/red-500/) // the explicit red badge
    expect(row).toMatch(/reason/)
    expect(row).toMatch(/content withheld/)
  })

  it('the four basis classes render as explicit badges with an unknown fallback', () => {
    const row = src(...ROW)
    for (const basis of [
      "'human-verified'",
      "'independently-recomputed'",
      "'self-asserted'",
      "'persistence-only'",
    ]) {
      expect(row).toContain(basis)
    }
    expect(row).toMatch(/unknown/)
    expect(row).toMatch(/\?\? BASIS_BADGE\.unknown/) // never coerced
  })

  it('the untrusted-observations boundary and the producer-asserted caveat are on the page', () => {
    const text = src(...PAGE)
    expect(text).toMatch(/UNTRUSTED OBSERVATIONS ONLY/)
    expect(text).toMatch(/producer-asserted/)
    expect(text).toMatch(/token-gated/)
    expect(text).toMatch(/changes nothing/)
  })

  it('the read model documents + implements verification-before-serve', () => {
    const lib = src(...LIB)
    expect(lib).toMatch(/verified prefix/)
    expect(lib).toMatch(/rollback-shaped/)
    expect(lib).toMatch(/verifier did not run/)
    // the status vocabulary stays a lockstep mirror of the Python verifier
    expect(lib).toMatch(/LOCKSTEP: framework\/evidence\/verifier\.py/)
  })
})
