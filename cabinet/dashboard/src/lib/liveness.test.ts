/**
 * The heartbeat reader, at the ends that used to render "Active".
 *
 * Each arm here names the surface it was found on. `livenessWord` is driven
 * directly because vitest runs `environment: 'node'` with no DOM renderer —
 * the DECISION was moved into this module precisely so the printed word can be
 * tested where the JSX cannot be mounted (the same split `lib/world/
 * killswitch.ts` uses, and for the same reason).
 */
import { describe, expect, it } from 'vitest'
import {
  freshnessOf,
  isMeasured,
  livenessGlyph,
  livenessTitle,
  livenessWord,
  MAX_SKEW_MS,
} from './liveness'

const NOW = Date.parse('2026-07-31T12:00:00.000Z')
const FIFTEEN_MIN = 15 * 60 * 1000

describe('freshnessOf — the degenerate ends', () => {
  it('a fresh stamp is fresh', () => {
    const f = freshnessOf('2026-07-31T11:58:00.000Z', NOW, FIFTEEN_MIN)
    expect(f.state).toBe('fresh')
  })

  it('an old stamp is stale', () => {
    const f = freshnessOf('2026-07-31T11:00:00.000Z', NOW, FIFTEEN_MIN)
    expect(f.state).toBe('stale')
  })

  it('absent is its OWN answer, not unknown', () => {
    // The store answering "no heartbeat for this officer" IS a measurement.
    // A stamp nobody can parse is not.
    expect(freshnessOf(null, NOW, FIFTEEN_MIN).state).toBe('absent')
    expect(freshnessOf(undefined, NOW, FIFTEEN_MIN).state).toBe('absent')
    expect(freshnessOf('', NOW, FIFTEEN_MIN).state).toBe('absent')
  })

  describe('MALFORMED — health/page.tsx rendered these green', () => {
    // `NaN > 900000` is false, so an unparseable stamp fell THROUGH the
    // staleness guard and out the healthy end.
    // NB: '0000' is deliberately NOT here — Date.parse('0000') is the year 0,
    // a real (and very stale) date. An arm that asserted it was unparseable
    // would be testing the test's assumption, not the reader.
    for (const bad of ['not a date', 'yesterday', '{}', '2026-13-45T99:99:99Z', 'NaN']) {
      it(`"${bad}" is unknown, never fresh`, () => {
        const f = freshnessOf(bad, NOW, FIFTEEN_MIN)
        expect(f.state).toBe('unknown')
        expect(livenessWord(f)).toBe('Unknown')
        expect(livenessWord(f)).not.toBe('Active')
      })
    }

    it('names a reason in plain words', () => {
      const f = freshnessOf('not a date', NOW, FIFTEEN_MIN)
      if (f.state !== 'unknown') throw new Error('expected unknown')
      expect(f.reason).toMatch(/could not be read/i)
    })
  })

  describe('FUTURE-DATED — a permanent green ring on five surfaces', () => {
    it('a stamp far in the future is unknown, never fresh', () => {
      const f = freshnessOf('2026-08-01T12:00:00.000Z', NOW, FIFTEEN_MIN)
      expect(f.state).toBe('unknown')
      expect(livenessWord(f)).toBe('Unknown')
    })

    it('names clock disagreement as the reason', () => {
      const f = freshnessOf('2030-01-01T00:00:00.000Z', NOW, FIFTEEN_MIN)
      if (f.state !== 'unknown') throw new Error('expected unknown')
      expect(f.reason).toMatch(/future/i)
    })

    it('tolerates small forward skew as fresh, and does not report a negative age', () => {
      const f = freshnessOf(
        new Date(NOW + MAX_SKEW_MS - 1000).toISOString(),
        NOW,
        FIFTEEN_MIN
      )
      expect(f.state).toBe('fresh')
      if (f.state !== 'fresh') throw new Error('unreachable')
      expect(f.ageMs).toBeGreaterThanOrEqual(0)
    })

    it('the boundary just past tolerance flips to unknown', () => {
      const f = freshnessOf(
        new Date(NOW + MAX_SKEW_MS + 1000).toISOString(),
        NOW,
        FIFTEEN_MIN
      )
      expect(f.state).toBe('unknown')
    })

    it('a future stamp NEVER ages into freshness, however big the window', () => {
      // The old code's failure was permanent: a negative age is under every
      // threshold there is, so no window size rescued it.
      for (const window of [0, 1000, FIFTEEN_MIN, 24 * 3600 * 1000, Number.MAX_SAFE_INTEGER]) {
        expect(freshnessOf('2030-01-01T00:00:00.000Z', NOW, window).state).toBe(
          'unknown'
        )
      }
    })
  })
})

describe('the printed word can never carry a health claim it did not measure', () => {
  it('livenessWord is Unknown for every unknown reading', () => {
    for (const bad of ['x', '2030-01-01T00:00:00.000Z']) {
      expect(livenessWord(freshnessOf(bad, NOW, FIFTEEN_MIN))).toBe('Unknown')
    }
  })

  it('isMeasured is false for absent and unknown', () => {
    expect(isMeasured(freshnessOf(null, NOW, FIFTEEN_MIN))).toBe(false)
    expect(isMeasured(freshnessOf('x', NOW, FIFTEEN_MIN))).toBe(false)
    expect(isMeasured(freshnessOf('2026-07-31T11:59:00Z', NOW, FIFTEEN_MIN))).toBe(true)
  })

  it('the glyph is dual-coded and distinct per state', () => {
    const glyphs = [
      livenessGlyph(freshnessOf('2026-07-31T11:59:00Z', NOW, FIFTEEN_MIN)),
      livenessGlyph(freshnessOf('2026-07-31T11:00:00Z', NOW, FIFTEEN_MIN)),
      livenessGlyph(freshnessOf(null, NOW, FIFTEEN_MIN)),
      livenessGlyph(freshnessOf('x', NOW, FIFTEEN_MIN)),
    ]
    expect(new Set(glyphs).size).toBe(4)
  })

  it('the unknown title refuses both "up" and "down"', () => {
    const t = livenessTitle(freshnessOf('x', NOW, FIFTEEN_MIN))
    expect(t).toMatch(/unread/i)
    expect(t).toMatch(/UNKNOWN/)
  })
})
