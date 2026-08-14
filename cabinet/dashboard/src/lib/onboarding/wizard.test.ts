/**
 * The stepped first-run's LOGIC, tested without a DOM.
 *
 * The three questions and the arc they open into live in wizard.ts precisely so
 * their sequence and their no-value-lost rule can be pinned here as pure
 * functions — the render is a separate guarantee in journey-card.test.ts. What
 * this file proves: role is required and the dream is not; the third question
 * branches; Back and Next never touch the answers; and the answer_seed payload
 * carries exactly the three seams (role -> seed, dream -> purpose, the
 * preference) and omits a dream nobody gave.
 */
import { describe, expect, it } from 'vitest'
import {
  canAdvance,
  EMPTY_WIZARD,
  nextStep,
  prevStep,
  resumeStep,
  seedRequest,
  type WizardValues,
} from './wizard'

const filled = (over: Partial<WizardValues> = {}): WizardValues => ({
  role: 'I run a small ryokan',
  dream: 'A calmer front desk',
  startPreference: 'point',
  ...over,
})

describe('the front is exactly three questions, then the window', () => {
  it('orders role -> dream -> start, then hands off to a core action', () => {
    const v = filled()
    expect(nextStep('role', v)).toBe('dream')
    expect(nextStep('dream', v)).toBe('start')
    expect(nextStep('start', filled({ startPreference: 'point' }))).toBe('window')
    expect(nextStep('start', filled({ startPreference: 'decide' }))).toBe('discover')
    // window and discover are terminal client steps — the next move is a core
    // action (propose_window / a real source), so there is no next step.
    expect(nextStep('window', v)).toBeNull()
    expect(nextStep('discover', v)).toBeNull()
  })

  it('walks Back the way it came, and never past the first question', () => {
    expect(prevStep('role')).toBeNull()
    expect(prevStep('dream')).toBe('role')
    expect(prevStep('start')).toBe('dream')
    expect(prevStep('window')).toBe('start')
    expect(prevStep('discover')).toBe('start')
  })
})

describe('which answers a step requires', () => {
  it('requires the role — it is the seed the core will not do without', () => {
    expect(canAdvance('role', filled({ role: '' }))).toBe(false)
    expect(canAdvance('role', filled({ role: '   ' }))).toBe(false)
    expect(canAdvance('role', filled({ role: 'a shopkeeper' }))).toBe(true)
  })

  it('lets the dream be skipped — a role-only answer is honest, not incomplete', () => {
    expect(canAdvance('dream', filled({ dream: '' }))).toBe(true)
  })

  it('needs one of the two start answers chosen before it will advance', () => {
    expect(canAdvance('start', filled({ startPreference: '' }))).toBe(false)
    expect(canAdvance('start', filled({ startPreference: 'point' }))).toBe(true)
    expect(canAdvance('start', filled({ startPreference: 'decide' }))).toBe(true)
  })
})

describe('the answer_seed payload carries the three seams and no invented one', () => {
  it('maps role -> seed, dream -> purpose, and the chosen preference', () => {
    expect(seedRequest(filled({
      role: '  I keep the books  ',
      dream: '  fewer late nights  ',
      startPreference: 'decide',
    }))).toEqual({
      seed: 'I keep the books',
      purpose: 'fewer late nights',
      start_preference: 'decide',
    })
  })

  it('OMITS purpose when no dream was given — never sends a blank mission', () => {
    const payload = seedRequest(filled({ dream: '   ', startPreference: 'point' }))
    expect(payload).not.toBeNull()
    expect(payload).not.toHaveProperty('purpose')
    expect(payload).toEqual({ seed: 'I run a small ryokan', start_preference: 'point' })
  })

  it('is null until the answers are complete enough to send', () => {
    expect(seedRequest(EMPTY_WIZARD)).toBeNull()
    expect(seedRequest(filled({ role: '' }))).toBeNull()
    expect(seedRequest(filled({ startPreference: '' }))).toBeNull()
  })
})

describe('resume', () => {
  // The rail's own arms moved to flow-rail.test.ts with the rail itself — see
  // the note at the top of wizard.ts. They are not deleted: they are stated
  // there over four stops instead of six, plus the monotonic law the six-stop
  // mapping failed.
  it('resumes a journey that already carries answers at its branch step', () => {
    expect(resumeStep(false, undefined)).toBe('role')
    expect(resumeStep(true, 'point')).toBe('window')
    expect(resumeStep(true, 'decide')).toBe('discover')
    // A journey seeded before the preference existed resumes at the folder.
    expect(resumeStep(true, undefined)).toBe('window')
  })
})
