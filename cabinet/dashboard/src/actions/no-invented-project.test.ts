/**
 * A STORE THAT IS NOT THERE DOES NOT NAME YOUR PROJECT — and does not report a
 * write that never happened.
 *
 * WHY THIS FILE EXISTS. Three action modules kept their own
 * `IS_MOCK = MOCK_DATA === 'true' || !REDIS_URL`, i.e. the exact predicate the
 * 2026-07-31 ruling deleted from `lib/redis.ts`, and were left because a project
 * identifier is not a measurement of health, money or attention. Two things
 * were behind it that ARE worse than a label:
 *
 *   1. `actions/crons.ts` returned `{ success: true }` from every schedule
 *      mutation without touching the watchdog's crontab whenever `REDIS_URL` was
 *      unset — a false success claim about a write, which is the shape PR #330
 *      closed for the emergency stop.
 *   2. `actions/project-config.ts` resolved the active slug to `'widgets'` on
 *      any failure and interpolated it into `${PROJECTS_DIR}/${slug}.yml`, so a
 *      box with no active project had its config edits written into a file named
 *      after a project it does not have.
 *
 * The rendered symptom was visible in the built app: with `REDIS_URL` pointing at
 * an unreachable store, the nav header read "Captain's Cabinet / Widgets".
 *
 * Every arm fails against the pre-change predicate — mutation log in the PR.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolveStorePosture } from '@/lib/store-posture'

const saved = { ...process.env }

beforeEach(() => {
  vi.resetModules()
})

afterEach(() => {
  for (const k of ['REDIS_URL', 'MOCK_DATA', 'CABINET_DEMO_DATA', 'NODE_ENV']) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
  vi.resetModules()
})

/**
 * The predicate these three modules now share, driven directly.
 *
 * Asserting the DECISION rather than each caller's branch is deliberate: the
 * callers reach docker and the filesystem, and a test that stands those up would
 * be testing the harness. What went wrong was the predicate — every one of them
 * treated a missing store as permission to invent — so the predicate is what is
 * pinned, alongside the source fence below that proves no caller kept its own.
 */
describe('the fabrication trigger these actions share', () => {
  it('an UNCONFIGURED store does not license fabrication', () => {
    expect(resolveStorePosture({}).fabricated).toBe(false)
  })

  it('a CONFIGURED store does not license fabrication', () => {
    expect(resolveStorePosture({ REDIS_URL: 'redis://x:6379' }).fabricated).toBe(false)
  })

  it('only the explicit non-production demo opt-in does', () => {
    expect(resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'test' }).fabricated).toBe(true)
    expect(
      resolveStorePosture({ CABINET_DEMO_DATA: 'true', NODE_ENV: 'test' }).fabricated
    ).toBe(true)
  })

  it('and never in production', () => {
    expect(
      resolveStorePosture({
        MOCK_DATA: 'true',
        CABINET_DEMO_DATA: 'true',
        NODE_ENV: 'production',
      }).fabricated
    ).toBe(false)
  })
})

describe('the placeholder project itself is gone from every real path', () => {
  /**
   * The demo branch was never where "Widgets" actually came from on a real box.
   * `getProjects()`'s OWN fallbacks — `projects.length === 0` and its catch —
   * both returned `[{slug:'widgets', name:'Widgets', active:true}]`, so a
   * cabinet whose project listing failed, or which simply has no projects yet,
   * rendered "Captain's Cabinet / Widgets" in the nav. Measured in the built app.
   *
   * This arm reads the source because the alternative is standing up docker to
   * make the listing fail; what is being pinned is that the literal exists at
   * exactly one place — behind the explicit demo opt-in — and nowhere else.
   */
  it('the fabricated roster literal appears ONLY inside a FABRICATED branch', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(path.join(__dirname, 'projects.ts'), 'utf8')
    const lines = src.split('\n')
    // Every line mentioning the placeholder, minus prose.
    const hits = lines
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => {
        const code = line.trimStart()
        if (code.startsWith('*') || code.startsWith('//')) return false
        return /['\`"]widgets['\`"]|name: 'Widgets'/i.test(line)
      })
    // Walk upward from each hit to the nearest branch keyword; every one must
    // sit under `if (FABRICATED)`.
    const unguarded = hits.filter(({ n }) => {
      for (let i = n - 1; i >= 0 && i > n - 12; i--) {
        if (/if \(FABRICATED\)/.test(lines[i])) return false
        if (/^\s*(} catch|return \[\]|export async function)/.test(lines[i])) return true
      }
      return true
    })
    expect(
      unguarded.map(({ n, line }) => `projects.ts:${n}: ${line.trim()}`),
      'a placeholder project name outside the explicit demo opt-in'
    ).toEqual([])
  })
})

describe('no action module keeps its own copy of the deleted predicate', () => {
  /**
   * The source fence. `!process.env.REDIS_URL` as a fabrication trigger is the
   * exact expression the ruling removed; anywhere it survives is a module that
   * did not get the memo, which is how three of them survived the last pass.
   *
   * Read with `node:fs` and matched with a JavaScript regex — a `git grep -E`
   * fence written with `\s` reported GREEN against a deliberately re-introduced
   * defect one PR ago, because POSIX ERE reads `\s` as a literal backslash-s.
   */
  it('none of them triggers on the ABSENCE of REDIS_URL', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const dir = path.resolve(__dirname)
    const offenders: string[] = []
    for (const f of fs.readdirSync(dir)) {
      if (!/\.tsx?$/.test(f) || /\.test\.tsx?$/.test(f)) continue
      const src = fs.readFileSync(path.join(dir, f), 'utf8')
      src.split('\n').forEach((line, i) => {
        const code = line.trimStart()
        if (code.startsWith('*') || code.startsWith('//')) return
        if (/!\s*process\.env\.REDIS_URL/.test(line)) offenders.push(`${f}:${i + 1}`)
      })
    }
    expect(
      offenders,
      'these modules still treat a missing store as permission to invent'
    ).toEqual([])
  })
})
