/**
 * The settings READ reflects an adjustment WRITE — `getCaptainAvailability()`
 * against the store the dashboard's write action appends to.
 *
 * Without this arm the write path could land, append a perfectly valid row, and
 * the Settings page would keep showing the old value: two halves that each work
 * and do not meet. The store format under test is the one the recorder
 * produces; the python arm
 * (cabinet/scripts/lib/tests/test_captain_availability_dashboard.py) runs the
 * real writer and asserts it emits exactly this shape, so the fixture here
 * cannot quietly diverge from what actually gets written.
 *
 * Precedence is part of the contract, not decoration: an adjustment must BEAT
 * what onboarding stamped, or a Captain who re-dials from the dashboard would
 * be shown the number he just replaced.
 *
 * Kept in its own file because lib/config.ts resolves both paths at module
 * load, so the env has to be set before the import — the same reason
 * config.test.ts pins MOCK_DATA before its dynamic import.
 */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'cabinet-availability-'))
const STORE = path.join(DIR, 'captain-availability.yml')
const PLATFORM = path.join(DIR, 'platform.yml')

process.env.CAPTAIN_AVAILABILITY_FILE = STORE
process.env.PLATFORM_CONFIG_PATH = PLATFORM
process.env.MOCK_DATA = 'true'

/** The header the recorder writes on a fresh store, verbatim in shape. */
const HEADER =
  '# captain-availability.yml — the Captain\'s declared time budget.\n' +
  '# MACHINE-WRITTEN (cabinet/scripts/lib/captain_availability.py);\n' +
  'schema: cabinet.captain-availability/v1\n' +
  'entries:\n'

/** One appended block, in the recorder's own field order. */
function block(at: string, minutes: number, mode: string, source: string): string {
  return (
    `  - at: ${at}\n` +
    `    minutes_per_day: ${minutes}\n` +
    `    mode: ${mode}\n` +
    `    source: ${source}\n`
  )
}

type Mod = typeof import('./config')
let mod: Mod

beforeAll(async () => {
  mod = await import('./config')
})

beforeEach(() => {
  // Onboarding stamped full_time; every arm below asks what wins over it.
  fs.writeFileSync(
    PLATFORM,
    'captain_availability_minutes_per_day: 480\ncaptain_availability_mode: full_time\n'
  )
  if (fs.existsSync(STORE)) fs.unlinkSync(STORE)
})

describe('an adjustment the dashboard wrote is what Settings shows', () => {
  it('serves the appended row, with its stamp, over the onboarding value', () => {
    fs.writeFileSync(
      STORE,
      HEADER +
        '  # captain text: availability part_time\n' +
        block('2026-07-26T21:30:00Z', 30, 'part_time', 'telegram')
    )
    fs.appendFileSync(STORE, block('2026-07-27T08:00:00Z', 90, 'substantial', 'dashboard'))

    expect(mod.getCaptainAvailability()).toEqual({
      minutesPerDay: 90,
      mode: 'substantial',
      source: 'adjusted',
      setAt: '2026-07-27T08:00:00Z',
    })
  })

  it('keeps the stamp js-yaml turns into a Date', () => {
    // The recorder writes `at:` UNQUOTED, and js-yaml types that as a Date, not
    // a string. A `typeof === 'string'` check therefore silently dropped the
    // timestamp of every row ever written — the row could show a value but
    // never when it was set. Same YAML-retyping class the resolver's
    // _availability_stamp() already handles on the python side.
    fs.writeFileSync(STORE, HEADER + block('2026-07-27T08:00:00Z', 30, 'part_time', 'dashboard'))
    expect(mod.getCaptainAvailability().setAt).toBe('2026-07-27T08:00:00Z')
  })

  it('keeps an explicitly quoted stamp too', () => {
    fs.writeFileSync(
      STORE,
      HEADER +
        "  - at: '2026-07-27T08:00:00Z'\n" +
        '    minutes_per_day: 30\n    mode: part_time\n    source: dashboard\n'
    )
    expect(mod.getCaptainAvailability().setAt).toBe('2026-07-27T08:00:00Z')
  })

  it('reports no stamp rather than a stringified object when at: is junk', () => {
    fs.writeFileSync(
      STORE,
      HEADER +
        '  - at: {nope: 1}\n    minutes_per_day: 30\n    mode: part_time\n    source: dashboard\n'
    )
    const got = mod.getCaptainAvailability()
    expect(got.minutesPerDay).toBe(30)
    expect(got.setAt).toBeNull()
  })

  it('serves the LAST valid row — an append never has to win a rewrite', () => {
    fs.writeFileSync(STORE, HEADER + block('2026-07-27T08:00:00Z', 90, 'substantial', 'dashboard'))
    expect(mod.getCaptainAvailability().minutesPerDay).toBe(90)
    fs.appendFileSync(STORE, block('2026-07-27T09:00:00Z', 10, 'minimal', 'dashboard'))
    expect(mod.getCaptainAvailability().minutesPerDay).toBe(10)
  })

  it('shows a declared zero as a ruling, not as an absence', () => {
    // The degenerate end: `away` has to survive the whole path, or the Captain
    // cannot use the dashboard to say "leave me alone".
    fs.writeFileSync(STORE, HEADER + block('2026-07-27T08:00:00Z', 0, 'away', 'dashboard'))
    expect(mod.getCaptainAvailability()).toEqual({
      minutesPerDay: 0,
      mode: 'away',
      source: 'adjusted',
      setAt: '2026-07-27T08:00:00Z',
    })
  })
})

describe('a store that says nothing usable never invents a number', () => {
  it('falls back to the onboarding stamp when no store exists', () => {
    expect(mod.getCaptainAvailability()).toEqual({
      minutesPerDay: 480,
      mode: 'full_time',
      source: 'onboarding',
      setAt: null,
    })
  })

  it('falls back when the store is corrupt rather than guessing', () => {
    fs.writeFileSync(STORE, 'entries: [ this is not: valid: yaml\n')
    expect(mod.getCaptainAvailability().source).toBe('onboarding')
  })

  it('skips an out-of-range row and serves the last VALID one', () => {
    fs.writeFileSync(
      STORE,
      HEADER +
        block('2026-07-27T08:00:00Z', 30, 'part_time', 'dashboard') +
        block('2026-07-27T09:00:00Z', 4000, 'part_time', 'dashboard')
    )
    expect(mod.getCaptainAvailability().minutesPerDay).toBe(30)
  })

  it('reports UNKNOWN when nobody has declared anything', () => {
    fs.unlinkSync(PLATFORM)
    expect(mod.getCaptainAvailability()).toEqual({
      minutesPerDay: null,
      mode: null,
      source: null,
      setAt: null,
    })
  })
})
