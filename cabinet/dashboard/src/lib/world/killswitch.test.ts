/**
 * THE EMERGENCY STOP READING — every degenerate end, driven.
 *
 * Every arm here FAILS against the pre-change code, because the pre-change code
 * had exactly one answer for all of them: `false`, which draws the lever UP.
 * The pairs are stated as such in the arm names — "was false" means the old
 * expression (`presence?.killswitch ?? false`, `Boolean(await get(...))`,
 * `value === 'active'`) produced a confident "not engaged" for that input.
 *
 * The five degenerate ends the census pass found the hard way, each with its
 * own arm below: ABSENT, MALFORMED, UNPARSEABLE TIMESTAMP, FUTURE-DATED (clock
 * skew), and PRESENT-BUT-FIELD-MISSING/wrong-type coercing to a falsy default.
 */
import { describe, expect, it } from 'vitest'
import {
  fallbackCommandFor,
  glanceOf,
  intentFor,
  killswitchAttr,
  killswitchGlance,
  killswitchGlyph,
  killswitchTitle,
  killswitchWord,
  measuredKillswitch,
  DEMO_STORE_REASON,
  NO_STORE_CONFIGURED_REASON,
  PRESENCE_MAX_AGE_MS,
  PRESENCE_MAX_SKEW_MS,
  readingFromKey,
  readingFromPresence,
  unknownKillswitch,
} from './killswitch'

const NOW = Date.parse('2026-07-31T10:00:00.000Z')
const fresh = (extra: Record<string, unknown>) => ({
  v: 1,
  ts: new Date(NOW - 2000).toISOString(),
  iid_high: 7,
  officers: {},
  ...extra,
})

describe('killswitchGlance — the one decision', () => {
  it('true → engaged, false → clear', () => {
    expect(killswitchGlance(true)).toEqual({ state: 'engaged' })
    expect(killswitchGlance(false)).toEqual({ state: 'clear' })
  })

  it('null and undefined are UNKNOWN, never clear (was: false → clear)', () => {
    expect(killswitchGlance(null).state).toBe('unknown')
    expect(killswitchGlance(undefined).state).toBe('unknown')
  })

  it('an unknown always carries a reason, even when the caller forgets one', () => {
    const g = killswitchGlance(null)
    expect(g.state === 'unknown' && g.reason.length > 0).toBe(true)
    const g2 = killswitchGlance(null, 'redis refused the connection')
    expect(g2).toEqual({ state: 'unknown', reason: 'redis refused the connection' })
  })

  it('`clear` is reachable ONLY from a measured false', () => {
    // The property that matters: no input other than an explicit `false`
    // produces the picture of a verified-off emergency stop.
    const inputs = [null, undefined, true, false] as const
    const clears = inputs.filter((v) => killswitchGlance(v).state === 'clear')
    expect(clears).toEqual([false])
  })
})

describe('the words and glyphs a surface can print', () => {
  it('never prints UP for an unknown (was: "LEVER UP" on an unread stop)', () => {
    expect(killswitchWord(killswitchGlance(null))).toBe('UNKNOWN')
    expect(killswitchWord(killswitchGlance(false))).toBe('UP')
    expect(killswitchWord(killswitchGlance(true))).toBe('THROWN')
  })

  it('the glyph is dual-coded with the word (never colour alone)', () => {
    expect(killswitchGlyph(killswitchGlance(null))).toBe('?')
    expect(killswitchGlyph(killswitchGlance(false))).toBe('↑')
    expect(killswitchGlyph(killswitchGlance(true))).toBe('↓')
  })

  it('the DOM attribute distinguishes all three (frame harness + probes read it)', () => {
    expect(killswitchAttr(killswitchGlance(null))).toBe('unknown')
    expect(killswitchAttr(killswitchGlance(false))).toBe('up')
    expect(killswitchAttr(killswitchGlance(true))).toBe('thrown')
    // Distinctness is the point: 'unknown' colliding with 'up' would put the
    // defect straight back into every automated reader of the world.
    const attrs = [null, false, true].map((v) => killswitchAttr(killswitchGlance(v)))
    expect(new Set(attrs).size).toBe(3)
  })

  it('the title never says off/inactive for an unknown, and names the check', () => {
    const t = killswitchTitle(killswitchGlance(null, 'redis unreachable'))
    expect(t).toMatch(/UNKNOWN/)
    expect(t).toMatch(/redis unreachable/)
    expect(t).toMatch(/kill-switch\.sh status/)
    expect(t).not.toMatch(/\binactive\b/i)
    expect(t).not.toMatch(/fleet running/)
  })
})

describe('intentFor — the direction is never guessed', () => {
  it('engaged→deactivate, clear→activate, unknown→NULL', () => {
    expect(intentFor(killswitchGlance(true))).toBe('deactivate')
    expect(intentFor(killswitchGlance(false))).toBe('activate')
    expect(intentFor(killswitchGlance(null))).toBeNull()
  })

  it('the CLI fallback names the verb, not the guessed state', () => {
    expect(fallbackCommandFor('activate')).toBe('cabinet/scripts/kill-switch.sh activate')
    expect(fallbackCommandFor('deactivate')).toBe('cabinet/scripts/kill-switch.sh deactivate')
  })
})

describe('readingFromPresence — the world SSE path', () => {
  it('verdict ACTIVE / CLEAR are the two measured readings', () => {
    expect(readingFromPresence(fresh({ killswitch_verdict: 'ACTIVE' }), NOW).engaged).toBe(true)
    expect(readingFromPresence(fresh({ killswitch_verdict: 'CLEAR' }), NOW).engaged).toBe(false)
  })

  it('verdict INDETERMINATE is UNKNOWN — the reader could not prove either', () => {
    const r = readingFromPresence(fresh({ killswitch_verdict: 'INDETERMINATE' }), NOW)
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toMatch(/verifiable answer/)
  })

  it('the verdict OUTRANKS the legacy bool when both are present', () => {
    // The daemon writes killswitch = (verdict != CLEAR), so an INDETERMINATE
    // arrives as `killswitch: true`. Reading the bool would call an unreadable
    // switch "engaged" — safe, but still a guess, and the wrong report.
    const r = readingFromPresence(
      fresh({ killswitch: true, killswitch_verdict: 'INDETERMINATE' }),
      NOW
    )
    expect(r.engaged).toBeNull()
  })

  it('an unrecognised verdict is unknown, not clear (closed enum)', () => {
    expect(readingFromPresence(fresh({ killswitch_verdict: 'OK' }), NOW).engaged).toBeNull()
    expect(readingFromPresence(fresh({ killswitch_verdict: '' }), NOW).engaged).toBeNull()
  })

  // ── DEGENERATE END 1: absent ────────────────────────────────────────────
  it('no presence snapshot at all → unknown (was: false → LEVER UP)', () => {
    for (const absent of [null, undefined]) {
      const r = readingFromPresence(absent, NOW)
      expect(r.engaged).toBeNull()
      expect(r.unknownReason).toMatch(/presence snapshot/)
    }
  })

  // ── DEGENERATE END 2: malformed ─────────────────────────────────────────
  it('a non-object / array presence blob → unknown (was: false)', () => {
    expect(readingFromPresence('active', NOW).engaged).toBeNull()
    expect(readingFromPresence(42, NOW).engaged).toBeNull()
    expect(readingFromPresence([], NOW).engaged).toBeNull()
  })

  // ── DEGENERATE END 3: unparseable timestamp ─────────────────────────────
  it('no readable timestamp → unknown, even with a CLEAR verdict (was: false)', () => {
    for (const ts of [undefined, '', 'yesterday', 123]) {
      const r = readingFromPresence(
        { v: 1, ts, officers: {}, killswitch_verdict: 'CLEAR' },
        NOW
      )
      expect(r.engaged).toBeNull()
      expect(r.unknownReason).toMatch(/timestamp/)
    }
  })

  // ── DEGENERATE END 4: stale, and future-dated (clock skew) ──────────────
  it('a stale snapshot is not a current reading, whatever its verdict', () => {
    const old = {
      v: 1,
      ts: new Date(NOW - PRESENCE_MAX_AGE_MS - 60_000).toISOString(),
      officers: {},
      killswitch_verdict: 'CLEAR',
    }
    const r = readingFromPresence(old, NOW)
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toMatch(/stopped updating/)
    // ...and an ACTIVE verdict is equally not current.
    expect(
      readingFromPresence({ ...old, killswitch_verdict: 'ACTIVE' }, NOW).engaged
    ).toBeNull()
  })

  it('a snapshot stamped in the future → unknown (clocks disagree)', () => {
    const r = readingFromPresence(
      {
        v: 1,
        ts: new Date(NOW + PRESENCE_MAX_SKEW_MS + 60_000).toISOString(),
        officers: {},
        killswitch_verdict: 'CLEAR',
      },
      NOW
    )
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toMatch(/future/)
  })

  it('ordinary small skew still passes (the bar is not a hair trigger)', () => {
    const r = readingFromPresence(
      { v: 1, ts: new Date(NOW + 1500).toISOString(), officers: {}, killswitch_verdict: 'CLEAR' },
      NOW
    )
    expect(r.engaged).toBe(false)
  })

  // ── DEGENERATE END 5: present but the field is missing / wrong type ─────
  it('a fresh snapshot carrying NO emergency-stop field → unknown (was: false)', () => {
    const r = readingFromPresence(fresh({}), NOW)
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toMatch(/no emergency-stop reading/)
  })

  it('a non-boolean, non-verdict emergency-stop field → unknown (was: falsy→false)', () => {
    for (const junk of [0, '', 'false', null, {}, []]) {
      expect(readingFromPresence(fresh({ killswitch: junk }), NOW).engaged).toBeNull()
    }
  })

  it('legacy snapshots (bool only) still read, both ways', () => {
    expect(readingFromPresence(fresh({ killswitch: false }), NOW).engaged).toBe(false)
    expect(readingFromPresence(fresh({ killswitch: true }), NOW).engaged).toBe(true)
  })
})

describe('readingFromKey — the direct GET path', () => {
  it('a proven-absent key is the only clear reading', () => {
    expect(readingFromKey(null, true).engaged).toBe(false)
    expect(readingFromKey('active', true).engaged).toBe(true)
  })

  it('never contacted → unknown (was: `let killswitch = false` survived the catch)', () => {
    const r = readingFromKey(null, false)
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toMatch(/could not ask|could not reach|no store/i)
  })

  it('an unrecognised value → unknown, in BOTH directions of the old bug', () => {
    // `value === 'active'` (layout.tsx) called these false → "fleet running".
    // `Boolean(value)` (engine route) called them true → storm. Two readers,
    // opposite lies, same input. Neither is a reading.
    for (const junk of ['', 'ACTIVE', 'yes', '1', 'NOAUTH Authentication required.']) {
      const r = readingFromKey(junk, true)
      expect(r.engaged).toBeNull()
      expect(r.unknownReason).toMatch(/unrecognised value/)
    }
  })

  it('the mock store’s seeded empty string is not a reading', () => {
    // With REDIS_URL unset the shared client serves `'cabinet:killswitch': ''`,
    // which `=== 'active'` reported as a verified-clear fleet stop.
    expect(readingFromKey('', true).engaged).toBeNull()
  })

  it('a caller can name its own not-contacted reason, per store posture', () => {
    // Two reasons, not one (2026-07-31). The single string said "it is showing
    // demo data" and was used for BOTH not-live postures — but an unconfigured
    // dashboard shows honest absences, not demo data, so half the time the
    // banner made a false claim about the page it was printed on.
    for (const reason of [NO_STORE_CONFIGURED_REASON, DEMO_STORE_REASON]) {
      expect(readingFromKey(null, false, reason).unknownReason).toBe(reason)
      expect(reason.toLowerCase()).not.toMatch(/not engaged|inactive|clear/)
    }
    expect(NO_STORE_CONFIGURED_REASON).toMatch(/REDIS_URL/)
    expect(NO_STORE_CONFIGURED_REASON).not.toMatch(/showing demo data/)
    expect(DEMO_STORE_REASON).toMatch(/demo data/)
  })
})

describe('constructors', () => {
  it('an unknown is always built WITH its reason (no zero-valued constant)', () => {
    expect(unknownKillswitch('because')).toEqual({
      engaged: null,
      unknownReason: 'because',
    })
    expect(measuredKillswitch(true)).toEqual({ engaged: true, unknownReason: null })
    expect(glanceOf(unknownKillswitch('because'))).toEqual({
      state: 'unknown',
      reason: 'because',
    })
  })
})
