/**
 * Lighting/clock mapping purity tests (TRACK T2 gate).
 *
 * The lighting read-model is the only place the wall clock touches pixels,
 * and it touches them as DATA (snapshot.clock) through pure functions. These
 * tests pin:
 *  1. the full 24-hour → bucket mapping under the grammar-law defaults,
 *  2. boundary hours and the midnight wrap,
 *  3. determinism (identical inputs → identical outputs, no hidden state),
 *  4. honest-neutral behavior when the snapshot has no clock,
 *  5. the §2 lighting table values (tint/glow/sky per bucket),
 *  6. reserved-salience discipline: no lighting constant equals the pure
 *     alarm hues (the lamp amber is lamplight, not signal-amber).
 */
import { describe, expect, it } from 'vitest'
import {
  ambientVeil,
  bucketForHour,
  DEFAULT_BUCKETS,
  formatClock,
  lampGlow,
  starOffsets,
  STAR_COLOR,
  WINDOW_SKY,
  windowSky,
  type DayBucket,
} from './lighting'

const EXPECTED_BY_HOUR: DayBucket[] = [
  // 0..5 night
  'night', 'night', 'night', 'night', 'night', 'night',
  // 6..7 dawn
  'dawn', 'dawn',
  // 8..17 day
  'day', 'day', 'day', 'day', 'day', 'day', 'day', 'day', 'day', 'day',
  // 18..20 dusk
  'dusk', 'dusk', 'dusk',
  // 21..23 night
  'night', 'night', 'night',
]

describe('bucketForHour', () => {
  it('defaults pin the grammar-law bucket table (show-grammar v2 night.buckets)', () => {
    expect(DEFAULT_BUCKETS).toEqual({
      dawn: [6, 8],
      day: [8, 18],
      dusk: [18, 21],
      night: [21, 6],
    })
  })

  it('maps the full 24-hour domain per grammar-law defaults', () => {
    for (let h = 0; h < 24; h++) {
      expect(bucketForHour(h), `hour ${h}`).toBe(EXPECTED_BY_HOUR[h])
    }
  })

  it('boundary hours land on the incoming bucket ([start, end) ranges)', () => {
    expect(bucketForHour(6)).toBe('dawn')
    expect(bucketForHour(8)).toBe('day')
    expect(bucketForHour(18)).toBe('dusk')
    expect(bucketForHour(21)).toBe('night')
    expect(bucketForHour(5)).toBe('night') // wrap side of night [21, 6)
    expect(bucketForHour(0)).toBe('night')
  })

  it('no clock → day (honest neutral: no tint claim)', () => {
    expect(bucketForHour(null)).toBe('day')
    expect(bucketForHour(undefined)).toBe('day')
    expect(bucketForHour(Number.NaN)).toBe('day')
  })

  it('out-of-range hours normalize instead of throwing', () => {
    expect(bucketForHour(24)).toBe(bucketForHour(0))
    expect(bucketForHour(25)).toBe(bucketForHour(1))
    expect(bucketForHour(-1)).toBe(bucketForHour(23))
    expect(bucketForHour(9.7)).toBe(bucketForHour(9)) // floor, never round up
  })

  it('grammar-supplied ranges override defaults per bucket', () => {
    // A law that stretches dusk to 22 pushes night back.
    expect(bucketForHour(21, { dusk: [18, 22] })).toBe('dusk')
    expect(bucketForHour(22, { dusk: [18, 22] })).toBe('night')
    // Partial override keeps other defaults intact.
    expect(bucketForHour(7, { dusk: [18, 22] })).toBe('dawn')
  })

  it('is pure — identical inputs yield identical outputs', () => {
    for (let h = 0; h < 24; h++) {
      expect(bucketForHour(h)).toBe(bucketForHour(h))
      expect(bucketForHour(h, { night: [20, 8] })).toBe(
        bucketForHour(h, { night: [20, 8] })
      )
    }
  })
})

describe('lighting table (§2)', () => {
  it('lamp pools exist ONLY at dusk/night (warm additive, r=28px)', () => {
    expect(lampGlow('dawn')).toBeNull()
    expect(lampGlow('day')).toBeNull()
    for (const b of ['dusk', 'night'] as const) {
      expect(lampGlow(b)).toEqual({ color: 0xffb050, alpha: 0.15, radiusPx: 28 })
    }
  })

  it('window sky swaps per bucket and darkens toward night', () => {
    expect(windowSky('dawn')).toBe(WINDOW_SKY.dawn)
    expect(windowSky('day')).toBe(WINDOW_SKY.day)
    expect(windowSky('dusk')).toBe(WINDOW_SKY.dusk)
    expect(windowSky('night')).toBe(WINDOW_SKY.night)
    // Four distinct skies — a swapped bucket must be visible.
    expect(new Set(Object.values(WINDOW_SKY)).size).toBe(4)
  })

  it('reserved salience hues never appear as lighting constants', () => {
    // green=verified, amber=blocked, red=killswitch, grey=unmeasured,
    // purple=captain-gated (morphology law block). Lighting warmth must not
    // collide with the exact alarm colors used on status surfaces.
    const reserved = new Set([0x22c55e, 0xf59e0b, 0xcc2222, 0xef4444, 0x9ca3af, 0xa855f7])
    const lightingColors = [
      ...Object.values(WINDOW_SKY),
      STAR_COLOR,
      // the ambience VEIL replaced the alpha washes that used to be read here;
      // its hues are what actually reach the frame, so they are what must not
      // collide with an alarm colour. veil.test.ts bans the adrift hue too.
      ...(['dawn', 'dusk', 'night'] as const).flatMap((b) => [
        ...(ambientVeil(b)?.colors ?? []),
      ]),
      lampGlow('night')!.color,
    ]
    for (const c of lightingColors) {
      expect(reserved.has(c), `0x${c.toString(16)}`).toBe(false)
    }
  })
})

describe('starOffsets', () => {
  it('is deterministic per window id and stays inside the glass', () => {
    const a = starOffsets('window:1')
    const b = starOffsets('window:1')
    expect(a).toEqual(b)
    for (const s of a) {
      expect(s.x).toBeGreaterThanOrEqual(0)
      expect(s.x).toBeLessThan(16)
      expect(s.y).toBeGreaterThanOrEqual(0)
      expect(s.y).toBeLessThan(26)
    }
    // Different windows get different skies (seeded, not copied).
    expect(starOffsets('window:2')).not.toEqual(a)
  })

  it('degenerate glass sizes never divide by zero', () => {
    expect(() => starOffsets('w', 3, 1, 1)).not.toThrow()
  })
})

describe('formatClock', () => {
  it('renders HH:MM, zero-padded, normalized', () => {
    expect(formatClock({ hour: 9, minute: 5 })).toBe('09:05')
    expect(formatClock({ hour: 23, minute: 59 })).toBe('23:59')
    expect(formatClock({ hour: 24, minute: 60 })).toBe('00:00')
  })

  it('absent/invalid clock renders nothing (never a fake time)', () => {
    expect(formatClock(null)).toBeNull()
    expect(formatClock(undefined)).toBeNull()
    expect(formatClock({ hour: Number.NaN, minute: 0 })).toBeNull()
  })
})
