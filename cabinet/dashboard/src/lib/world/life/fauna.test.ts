/**
 * T2 LIFE — fauna tests (spec v2 §15.5 population law): all seeded, all
 * honest ("carries no data — exists for joy"), day-gated where the species
 * honestly sleeps, capped, and byte-deterministic.
 */
import { describe, expect, it } from 'vitest'
import {
  BIRD_SLOTS,
  BUTTERFLY_CAP,
  FISH_CAP,
  PET_REACTION_TICKS,
  catPosture,
  faunaAt,
  faunaCard,
  petReaction,
  type FaunaInput,
} from './fauna'

function input(over: Partial<FaunaInput> = {}): FaunaInput {
  return {
    tick: 500,
    clockHour: 12,
    bounds: { w: 60, h: 48 },
    flowerAnchors: [
      { x: 20, y: 20 },
      { x: 24, y: 22 },
    ],
    quayWater: [{ x: 30, y: 46 }],
    catPerch: { x: 15, y: 12 },
    ...over,
  }
}

describe('faunaAt — seeded, pure, deterministic', () => {
  it('same input twice → byte-identical sprites', () => {
    expect(JSON.stringify(faunaAt(input()))).toBe(
      JSON.stringify(faunaAt(input()))
    )
  })
  it('different seed salt → a different (still deterministic) schedule', () => {
    const seen = new Set<string>()
    for (const salt of ['a', 'b']) {
      for (let t = 0; t < 4000; t += 7) {
        for (const f of faunaAt(input({ tick: t, seedSalt: salt }))) {
          if (f.kind === 'bird') seen.add(`${salt}:${t}`)
        }
      }
    }
    expect(seen.size).toBeGreaterThan(0)
  })
  it('butterflies: one per flower anchor, capped, day-only', () => {
    const day = faunaAt(input())
    expect(day.filter((f) => f.kind === 'butterfly')).toHaveLength(2)
    const many = faunaAt(
      input({
        flowerAnchors: Array.from({ length: 10 }, (_, i) => ({ x: i, y: i })),
      })
    )
    expect(many.filter((f) => f.kind === 'butterfly')).toHaveLength(
      BUTTERFLY_CAP
    )
    const night = faunaAt(input({ clockHour: 23 }))
    expect(night.filter((f) => f.kind === 'butterfly')).toHaveLength(0)
  })
  it('no clock data → day-only fauna stays home (fail-closed honesty)', () => {
    const unknown = faunaAt(input({ clockHour: null }))
    expect(
      unknown.filter((f) => f.kind === 'bird' || f.kind === 'butterfly')
    ).toHaveLength(0)
  })
  it('birds appear during seeded fly-by windows, inside the sky band', () => {
    let seen = 0
    for (let t = 0; t < 3200; t++) {
      const birds = faunaAt(input({ tick: t })).filter((f) => f.kind === 'bird')
      expect(birds.length).toBeLessThanOrEqual(BIRD_SLOTS)
      for (const b of birds) {
        seen++
        expect(b.layer).toBe('air')
        expect(b.x).toBeGreaterThanOrEqual(-4)
        expect(b.x).toBeLessThanOrEqual(64)
        expect(b.y).toBeLessThan(48 / 2) // sky band, never ground level
      }
    }
    expect(seen).toBeGreaterThan(0)
  })
  it('fish jump in short seeded arcs at the quay, capped', () => {
    let jumps = 0
    for (let t = 0; t < 2000; t++) {
      const fish = faunaAt(input({ tick: t })).filter((f) => f.kind === 'fish')
      expect(fish.length).toBeLessThanOrEqual(FISH_CAP)
      for (const f of fish) {
        jumps++
        expect(f.layer).toBe('water')
        expect(f.y).toBeLessThanOrEqual(46) // arc rises above the anchor
      }
    }
    expect(jumps).toBeGreaterThan(0)
    expect(jumps).toBeLessThan(2000 / 4) // a fish is an event, not a resident
  })
  it('exactly one cat, at its perch, at all hours', () => {
    for (const hour of [3, 12, 23, null]) {
      const cats = faunaAt(input({ clockHour: hour })).filter(
        (f) => f.kind === 'cat'
      )
      expect(cats).toHaveLength(1)
      expect(cats[0].x).toBe(15)
    }
    expect(
      faunaAt(input({ catPerch: null })).filter((f) => f.kind === 'cat')
    ).toHaveLength(0)
  })
})

describe('the pettable cat — client-only, zero writes', () => {
  it('postures cycle deterministically per seeded window', () => {
    expect(catPosture(100)).toBe(catPosture(100))
    const postures = new Set<string>()
    for (let t = 0; t < 64 * 32; t += 64) postures.add(catPosture(t))
    expect(postures.size).toBeGreaterThan(1)
  })
  it('pet reaction is a pure function of (clickTick, tick) and expires', () => {
    expect(petReaction(null, 100).active).toBe(false)
    expect(petReaction(100, 99).active).toBe(false)
    expect(petReaction(100, 100).active).toBe(true)
    expect(petReaction(100, 100 + PET_REACTION_TICKS - 1).active).toBe(true)
    expect(petReaction(100, 100 + PET_REACTION_TICKS).active).toBe(false)
  })
})

describe('honest cards — every creature answers inspect truthfully', () => {
  it('joy fauna: "carries no data — exists for joy"', () => {
    for (const kind of ['bird', 'butterfly', 'fish', 'dog'] as const) {
      expect(faunaCard(kind).now).toContain('Carries no data')
      expect(faunaCard(kind).decorative).toBe(true)
    }
  })
  it('the cat: pets gratefully accepted, zero state, zero writes', () => {
    const card = faunaCard('cat')
    expect(card.now).toBe('Carries no data — pets gratefully accepted.')
    expect(card.proof).toContain('zero state, zero writes')
    expect(card.proof).toContain('Exactly one cat')
  })
})
