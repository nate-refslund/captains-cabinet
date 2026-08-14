import { afterEach, describe, it, expect } from 'vitest'
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { journeyIsComplete, type CompletableJourney } from './completion'
import { isOnboardingComplete } from './completion-state-file'

const dirs: string[] = []

function stateFileWith(contents: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'onboarding-state-'))
  dirs.push(dir)
  const path = join(dir, 'state.json')
  writeFileSync(path, contents)
  process.env.ONBOARDING_STATE_PATH = path
  return path
}

afterEach(() => {
  delete process.env.ONBOARDING_STATE_PATH
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true })
})

describe('isOnboardingComplete — the /onboarding redirect signal', () => {
  it('NO state file → not complete (onboarding never started)', async () => {
    process.env.ONBOARDING_STATE_PATH = join(tmpdir(), 'does-not-exist', 'state.json')
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('ratified charter + a first dividend → complete (renders home)', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'dividend_ready',
        charter: { status: 'ratified', ratified_at: '2026-08-01T00:00:00Z', hash: 'h', payload: {} },
        first_dividend: { finding: 'one cited useful thing' },
      })
    )
    expect(await isOnboardingComplete()).toBe(true)
  })

  it('charter still pending → not complete', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'charter_pending',
        charter: { status: 'proposed', hash: 'h', payload: {} },
        first_dividend: null,
      })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('purged (fresh state, no charter, no dividend) → not complete', async () => {
    // What framework.onboarding.journey._fresh_state(stage="purged") writes.
    stateFileWith(
      JSON.stringify({ stage: 'purged', charter: null, first_dividend: null })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('ratified charter but NO dividend yet → not complete (both are required)', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'dividend_ready',
        charter: { status: 'ratified', hash: 'h', payload: {} },
        first_dividend: null,
      })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('unreadable/blank state → not complete (never assume done)', async () => {
    stateFileWith('{ this is not valid json')
    expect(await isOnboardingComplete()).toBe(false)
  })
})

/**
 * ONE PREDICATE, TWO RUNTIMES. The core answers "has this journey arrived?" in
 * Python (`journey_has_arrived`) and this module answers it in TypeScript. They
 * decide different things — the core decides whether to render an arrival, this
 * decides whether to redirect — so a drift would tell the operator both "your
 * Cabinet is ready" and "you have not finished". Nothing but a shared table can
 * hold two languages together, and both suites assert against this one.
 */
describe('journeyIsComplete — the shared table the core asserts against too', () => {
  const TABLE = resolve(
    __dirname,
    '..', '..', '..', '..', '..',
    'framework', 'onboarding', 'tests', 'data', 'completion-parity.json'
  )

  const table = JSON.parse(readFileSync(TABLE, 'utf8')) as {
    cases: { name: string; why: string; state: CompletableJourney; complete: boolean }[]
  }

  it('has a table worth calling a sensor', () => {
    // A thin table proves little, and an absent one would let this describe
    // block pass with zero assertions.
    expect(table.cases.length).toBeGreaterThanOrEqual(10)
    expect(table.cases.some((c) => c.complete)).toBe(true)
    expect(table.cases.some((c) => !c.complete)).toBe(true)
  })

  for (const testCase of table.cases) {
    it(`${testCase.name}: ${testCase.why}`, () => {
      expect(journeyIsComplete(testCase.state)).toBe(testCase.complete)
    })
  }

  it('is the SAME predicate the file reader uses, not a second copy', async () => {
    // Proven by behaviour rather than by inspection: a state the pure predicate
    // calls complete must make the file reader say so too.
    for (const testCase of table.cases) {
      stateFileWith(JSON.stringify(testCase.state))
      expect(await isOnboardingComplete(), testCase.name).toBe(testCase.complete)
    }
  })
})

/**
 * THE BUNDLE BOUNDARY, as a test.
 *
 * Neither `tsc --noEmit` nor this suite can see it: both run in Node, where
 * importing `node:fs/promises` is perfectly legal. The browser bundler cannot,
 * and when the arrival screen — a CLIENT component — began gating on the
 * completion predicate, the shared module dragged `node:fs/promises` into the
 * client graph and /onboarding returned 500 for every operator. It was caught
 * by opening the page, which is the only sensor that had a chance.
 *
 * So it becomes a cheap permanent one: every module the client component
 * imports must be free of Node built-ins. Proven able to fire by
 * `completion-state-file.ts`, which deliberately fails the same check.
 */
describe('client-safe modules import no Node built-ins', () => {
  const NODE_IMPORT = /from ['"](node:[a-z/]+|fs|path|child_process|os|crypto)['"]/

  const CLIENT_SAFE = [
    'completion.ts',   // gates the arrival screen
    'arrival.ts',      // assembles the summary it renders
    'flow-rail.ts',    // maps the rail it draws
    'wizard.ts',       // the stepped front's logic
    'types.ts',
  ]

  for (const file of CLIENT_SAFE) {
    it(`${file} is safe to pull into the browser bundle`, () => {
      const source = readFileSync(resolve(__dirname, file), 'utf8')
      expect(NODE_IMPORT.test(source), `${file} imports a Node built-in`).toBe(false)
    })
  }

  it('THE SENSOR FIRES: the server-only half fails this same check', () => {
    const source = readFileSync(resolve(__dirname, 'completion-state-file.ts'), 'utf8')
    expect(NODE_IMPORT.test(source)).toBe(true)
  })
})
