import { describe, it, expect } from 'vitest'
import { OFFICER_TITLES, officerTitle, titleCaseSlug } from './officer-title'

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
    expect(officerTitle('bakery-ceo')).toBe('Bakery Ceo')
    expect(officerTitle('bakery-ceo')).not.toBe('BAKERY-CEO')
  })

  it('titleCaseSlug splits on -, _ and whitespace and never throws', () => {
    expect(titleCaseSlug('news_letter ceo')).toBe('News Letter Ceo')
    // Fully degenerate input returns itself rather than crashing the render.
    expect(titleCaseSlug('')).toBe('')
    expect(officerTitle('')).toBe('')
  })
})
