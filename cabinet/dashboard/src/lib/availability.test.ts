/**
 * The dashboard's mirror of the availability mode table, and the strict value
 * grammar built on it (lib/availability.ts).
 *
 * THE POINT OF THIS FILE IS THE PARITY ARM. `framework/env.py` owns the
 * canonical table and `cabinet/scripts/lib/captain_availability.py` refuses to
 * keep a second copy of it on the stated grounds that "a second copy of the
 * bands would drift, and a drifted budget is worse than a verb that fails
 * open". The dashboard cannot import python, so it keeps a mirror — which is
 * only defensible with a check that reads the canonical table and reds the
 * build the moment the two disagree. Without this arm the mirror IS the drift
 * the lib warns about.
 *
 * The parity arm also has to be able to FAIL: a regex that quietly matched
 * nothing would make an empty extraction look like agreement, so the extracted
 * row count is asserted non-empty and compared both ways.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  AVAILABILITY_MAX_MINUTES,
  AVAILABILITY_MODES,
  AVAILABILITY_REFUSAL,
  parseAvailabilityValue,
  renderAvailability,
} from './availability'

// vitest runs with cwd = cabinet/dashboard.
const ENV_PY = path.resolve(process.cwd(), '..', '..', 'framework', 'env.py')

describe('parity with the canonical table in framework/env.py', () => {
  const source = fs.readFileSync(ENV_PY, 'utf8')

  it('reads a non-empty table out of framework/env.py', () => {
    // Guard the sensor itself: if the extraction ever silently matched
    // nothing, every comparison below would pass vacuously.
    expect(source).toContain('AVAILABILITY_MODES')
    expect(extractModes(source).length).toBeGreaterThan(0)
  })

  it('mirrors every mode and every band, in order, with nothing extra', () => {
    const canonical = extractModes(source)
    const mirrored = AVAILABILITY_MODES.map((m) => [m.mode, m.minutes] as [string, number])
    expect(mirrored).toEqual(canonical)
  })

  it('mirrors the upper bound', () => {
    const m = source.match(/AVAILABILITY_MAX_MINUTES\s*=\s*(\d+)\s*\*\s*(\d+)/)
    expect(m).not.toBeNull()
    expect(AVAILABILITY_MAX_MINUTES).toBe(Number(m![1]) * Number(m![2]))
  })

  it('gives every mirrored mode a label for the picker', () => {
    for (const m of AVAILABILITY_MODES) {
      expect(m.label.length).toBeGreaterThan(0)
    }
  })
})

/** `("part_time", 30, "part-time — …"),` rows from the canonical tuple. */
function extractModes(source: string): [string, number][] {
  const block = source.match(/AVAILABILITY_MODES[^=]*=\s*\(([\s\S]*?)\n\)/)
  if (!block) return []
  const rows: [string, number][] = []
  const rowRe = /\(\s*"([a-z_]+)"\s*,\s*(\d+)\s*,/g
  let hit: RegExpExecArray | null
  while ((hit = rowRe.exec(block[1])) !== null) {
    rows.push([hit[1], Number(hit[2])])
  }
  return rows
}

describe('the grammar accepts exactly what the dial can hold', () => {
  it.each([
    ['away', 0, 'away'],
    ['minimal', 10, 'minimal'],
    ['part_time', 30, 'part_time'],
    ['part-time', 30, 'part_time'],
    ['PART_TIME', 30, 'part_time'],
    ['  substantial  ', 120, 'substantial'],
    ['full_time', 480, 'full_time'],
  ])('accepts the mode %s', (raw, minutes, cli) => {
    const got = parseAvailabilityValue(raw)
    expect(got).not.toBeNull()
    expect(got!.kind).toBe('mode')
    expect(got!.minutes).toBe(minutes)
    expect(got!.cli).toBe(cli)
  })

  it.each([
    ['0', 0],
    ['1', 1],
    ['90', 90],
    ['090', 90],
    [' 45 ', 45],
    ['1440', 1440],
  ])('accepts %s whole minutes', (raw, minutes) => {
    const got = parseAvailabilityValue(raw)
    expect(got).not.toBeNull()
    expect(got!.kind).toBe('minutes')
    expect(got!.minutes).toBe(minutes)
    expect(got!.cli).toBe(String(minutes))
  })

  it('reads 0 as a real ruling, not as an absence', () => {
    // The degenerate end. `away` is a declaration; UNKNOWN is the absence, and
    // they must never collapse into each other.
    expect(parseAvailabilityValue('0')!.minutes).toBe(0)
    expect(parseAvailabilityValue('away')!.minutes).toBe(0)
    expect(parseAvailabilityValue('')).toBeNull()
  })
})

describe('everything else is refused, never repaired', () => {
  it.each([
    '90.5', '1.5', '0.0', '-1', '-0', '1441', '99999',
    '', '   ', '\n',
    'vacation', 'part', 'time', 'awayy', 'away away',
    '0x10', '3e2', '1_440', '+30', '30.', '.5',
    '20m', '2h', '20 min', '1,5h',
    'away; touch /tmp/pwned', "away'", 'away"', 'away`', '$(whoami)', 'away|minimal',
    'away\nminimal', 'away minimal',
  ])('refuses %j', (raw) => {
    expect(parseAvailabilityValue(raw)).toBeNull()
  })

  it.each([null, undefined, 42, {}, [], true])('refuses the non-string %j', (raw) => {
    expect(parseAvailabilityValue(raw)).toBeNull()
  })

  it('names the accepted forms when it refuses', () => {
    expect(AVAILABILITY_REFUSAL).toContain('1440')
    for (const m of AVAILABILITY_MODES) {
      expect(AVAILABILITY_REFUSAL).toContain(m.mode)
    }
  })
})

describe('rendering keeps an absence honest', () => {
  it('says Not set when nothing was declared', () => {
    expect(renderAvailability({ minutesPerDay: null, mode: null })).toBe('Not set')
  })

  it('never renders a declared zero as an absence', () => {
    expect(renderAvailability({ minutesPerDay: 0, mode: 'away' })).toBe('0 min/day (away)')
  })

  it('renders a declared value with its band', () => {
    expect(renderAvailability({ minutesPerDay: 90, mode: 'substantial' })).toBe(
      '90 min/day (substantial)'
    )
  })
})
