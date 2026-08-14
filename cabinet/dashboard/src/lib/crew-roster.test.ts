/**
 * THE NAME COMES FROM THE HIRE RECORD, NEVER FROM THE ID.
 *
 * The reported defect was `Hired Lane Ceo` — a machine id, title-cased, in the
 * place where a person's name goes, about an officer the operator never chose.
 * `roster.yml` already carries the words the operator's own answers produced
 * ("First Lane CEO"), and `contexts/<lane>.yml` carries the lane's display
 * name. Nothing was missing; nothing was being read.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { officerNameSources, readLaneNames, readRoster } from './crew-roster'
import { officerTitle } from './officer-title'

let dir: string

function writeRoster(text: string) {
  fs.writeFileSync(path.join(dir, 'roster.yml'), text)
}

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'crew-roster-'))
  fs.mkdirSync(path.join(dir, 'contexts'))
  process.env.CABINET_ROSTER_PATH = path.join(dir, 'roster.yml')
  process.env.CABINET_CONTEXTS_DIR = path.join(dir, 'contexts')
})

afterEach(() => {
  delete process.env.CABINET_ROSTER_PATH
  delete process.env.CABINET_CONTEXTS_DIR
  fs.rmSync(dir, { recursive: true, force: true })
})

describe('readRoster', () => {
  it('reads the hire record: slug, title and whether it is on-demand', () => {
    writeRoster(`roster:
  cos:
    title: Chair
    type: fulltime
  first-lane-ceo:
    title: First Lane CEO
    type: consultant
`)
    expect(readRoster()).toEqual([
      { slug: 'cos', title: 'Chair', onDemand: false },
      { slug: 'first-lane-ceo', title: 'First Lane CEO', onDemand: true },
    ])
  })

  it('a missing roster is zero hires, not a crash — a fresh checkout is legal', () => {
    expect(readRoster()).toEqual([])
  })

  it('malformed YAML is zero hires, not a half-read roster', () => {
    writeRoster('roster:\n  cos: [this is not a mapping\n')
    expect(readRoster()).toEqual([])
  })

  it('a roster key that is not slug-shaped is skipped rather than trusted', () => {
    writeRoster(`roster:
  "cos; rm -rf /":
    title: Nope
  cos:
    title: Chair
`)
    expect(readRoster().map((m) => m.slug)).toEqual(['cos'])
  })

  it('a row with no type defaults to always-on, matching lib_roster.py', () => {
    writeRoster('roster:\n  cos:\n    title: Chair\n')
    expect(readRoster()[0].onDemand).toBe(false)
  })

  it('a row with no title is null — never an invented one', () => {
    writeRoster('roster:\n  cos:\n    type: fulltime\n')
    expect(readRoster()[0].title).toBeNull()
  })
})

describe('readLaneNames', () => {
  it('reads each declaration\'s own slug and name — not the filename', () => {
    fs.writeFileSync(
      path.join(dir, 'contexts', 'anything.yml'),
      'slug: first-lane\nname: First Lane\n'
    )
    expect(readLaneNames()).toEqual({ 'first-lane': 'First Lane' })
  })

  it('skips the shipped .example twins and anything missing a key', () => {
    fs.writeFileSync(path.join(dir, 'contexts', 'a.yml.example'), 'slug: demo\nname: Demo\n')
    fs.writeFileSync(path.join(dir, 'contexts', 'b.yml'), 'slug: nameless\n')
    fs.writeFileSync(path.join(dir, 'contexts', 'c.yml'), 'name: Slugless\n')
    expect(readLaneNames()).toEqual({})
  })

  it('a missing contexts directory is no lane names, not a crash', () => {
    fs.rmSync(path.join(dir, 'contexts'), { recursive: true, force: true })
    expect(readLaneNames()).toEqual({})
  })
})

describe('the defect, end to end', () => {
  it('a HIRED lane CEO is called what the roster calls it', () => {
    writeRoster('roster:\n  first-lane-ceo:\n    title: First Lane CEO\n    type: consultant\n')
    const title = officerTitle('first-lane-ceo', officerNameSources())
    expect(title).toBe('First Lane CEO')
    expect(title).not.toBe('First Lane Ceo')
  })

  it('an UN-HIRED lane CEO still reads as its LANE plus its job, never a slug shout', () => {
    // The pending-authorization case: generated, inert, absent from roster.yml.
    // It has no hire record to quote, so the lane declaration supplies the noun.
    fs.writeFileSync(
      path.join(dir, 'contexts', 'first-lane.yml'),
      'slug: first-lane\nname: First Lane\n'
    )
    const title = officerTitle('first-lane-ceo', officerNameSources())
    expect(title).toBe('First Lane CEO')
  })

  it('with neither a roster nor a lane declaration it still reads as words', () => {
    // The last resort must not regress to the shout: `Hired Lane Ceo` was
    // wrong because of the "Ceo", and because it named nothing real.
    const title = officerTitle('hired-lane-ceo', officerNameSources())
    expect(title).toBe('Hired Lane CEO')
    expect(title).not.toBe('HIRED-LANE-CEO')
  })

  it('a known framework officer is unaffected by any of this', () => {
    writeRoster('roster:\n  cos:\n    title: Chair\n')
    // The roster calls it "Chair"; the Captain's ruling is "First Mate", and
    // the framework title wins — the ruling is not a per-deployment setting.
    expect(officerTitle('cos', officerNameSources())).toBe('First Mate')
  })
})
