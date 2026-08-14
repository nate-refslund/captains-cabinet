import { describe, it, expect } from 'vitest'
import {
  OFFICER_TITLES,
  officerTitle,
  splitLaneRole,
  titleCaseSlug,
} from './officer-title'

describe('officerTitle — the one officer display-name resolver', () => {
  it('the coordinator is "First Mate" — the Captain\'s clean name', () => {
    // The reported defect: the dashboard printed "COS". The ruling: it is
    // "First Mate", not "COS", not "Chief of Staff", not "Chair", and with no
    // parenthetical.
    expect(officerTitle('cos')).toBe('First Mate')
    expect(officerTitle('cos')).not.toBe('COS')
    expect(officerTitle('cos')).not.toContain('CoS')
    expect(officerTitle('cos')).not.toContain('Chief of Staff')
    expect(officerTitle('cos')).not.toContain('Chair')
  })

  it('a KNOWN officer never renders as its uppercased slug', () => {
    for (const role of ['cos', 'cto', 'cpo', 'cro', 'coo']) {
      const title = officerTitle(role)
      expect(title).toBeTruthy()
      // The core defect this abolishes: the raw id shouted where a name belongs.
      expect(title).not.toBe(role.toUpperCase())
    }
  })

  it('every known officer resolves to its configured title verbatim', () => {
    for (const [role, expected] of Object.entries(OFFICER_TITLES)) {
      expect(officerTitle(role)).toBe(expected)
    }
  })

  it('an UNTITLED custom lane degrades readably — Title Case, not a raw slug shout', () => {
    // The degenerate end: a lane with no configured title. It must still read
    // as words, never as an all-caps machine id.
    expect(officerTitle('xyz')).toBe('Xyz')
    expect(officerTitle('xyz')).not.toBe('XYZ')
    // Was `Bakery Ceo` before 2026-08-14. A job title title-cased into a word
    // ("Ceo") is the same defect as the slug shout, one notch quieter — the
    // trailing role word is now written the way it is written.
    expect(officerTitle('bakery-ceo')).toBe('Bakery CEO')
    expect(officerTitle('bakery-ceo')).not.toBe('BAKERY-CEO')
  })

  it('titleCaseSlug splits on -, _ and whitespace and never throws', () => {
    expect(titleCaseSlug('news_letter ceo')).toBe('News Letter Ceo')
    // Fully degenerate input returns itself rather than crashing the render.
    expect(titleCaseSlug('')).toBe('')
    expect(officerTitle('')).toBe('')
  })
})

describe('a lane officer is named after its LANE, never after its id', () => {
  it('the roster title wins when this deployment has one', () => {
    const sources = { titles: { 'first-lane-ceo': 'First Lane CEO' } }
    expect(officerTitle('first-lane-ceo', sources)).toBe('First Lane CEO')
  })

  it('with no roster title, the lane declaration supplies the noun', () => {
    const sources = { laneNames: { 'first-lane': 'Askes Multiservice' } }
    expect(officerTitle('first-lane-ceo', sources)).toBe('Askes Multiservice CEO')
  })

  it('the exact string the Captain was shown is no longer reachable', () => {
    // `Hired Lane Ceo` — a title-cased slug for a placeholder nobody chose.
    for (const sources of [
      {},
      { titles: {} },
      { laneNames: {} },
      { titles: {}, laneNames: {} },
    ]) {
      expect(officerTitle('hired-lane-ceo', sources)).not.toBe('Hired Lane Ceo')
    }
  })

  it('an EMPTY configured title is not a title — it falls through, never renders blank', () => {
    expect(officerTitle('first-lane-ceo', { titles: { 'first-lane-ceo': '   ' } })).toBe(
      'First Lane CEO'
    )
    expect(officerTitle('first-lane-ceo', { laneNames: { 'first-lane': '' } })).toBe(
      'First Lane CEO'
    )
  })

  it('a known officer ignores both maps — the ruling is not a per-deployment setting', () => {
    expect(officerTitle('cos', { titles: { cos: 'Chair' } })).toBe('First Mate')
  })

  it('sources are optional — every existing single-argument caller is unchanged', () => {
    expect(officerTitle('cos')).toBe('First Mate')
    expect(officerTitle('xyz')).toBe('Xyz')
  })
})

describe('splitLaneRole — only an unambiguous job word splits', () => {
  it('splits a lane officer', () => {
    expect(splitLaneRole('first-lane-ceo')).toEqual({ lane: 'first-lane', roleWord: 'CEO' })
    expect(splitLaneRole('comms-officer')).toEqual({ lane: 'comms', roleWord: 'Officer' })
  })

  it('does NOT split a lane, a bare slug, or an unknown trailing word', () => {
    expect(splitLaneRole('first-lane')).toBeNull()
    expect(splitLaneRole('cos')).toBeNull()
    expect(splitLaneRole('bakery-site')).toBeNull()
    expect(splitLaneRole('-ceo')).toBeNull()
    expect(splitLaneRole('')).toBeNull()
  })
})
