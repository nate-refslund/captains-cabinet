/**
 * IS THIS OFFICER ALIVE — four answers, where there used to be two.
 *
 * WHY THIS FILE EXISTS. Five surfaces each open-coded the same three lines:
 *
 *   health/page.tsx:19          const hbAge = now - new Date(hb).getTime()
 *   page.tsx:75                 now - hbTime > 10*60*1000 ? 'no-heartbeat' : 'running'
 *   tasks/page.tsx:42           result[slug] = now - hbTime < OFFLINE_THRESHOLD_MS
 *   consumer/card-cabinet.tsx   isOffline = offlineDurationMs > OFFLINE_THRESHOLD_MS
 *   lib/display-data.ts:110     online: ageMs < TH, stale: ageMs >= TH
 *
 * and every one of them had the same two degenerate ends open:
 *
 *   MALFORMED — `new Date('not a date').getTime()` is `NaN`, and `NaN > x` is
 *     `false`, so an unparseable heartbeat fell THROUGH the staleness guard and
 *     out the healthy end. health/page.tsx returned 'green' and the officer
 *     rendered "Active".
 *   FUTURE-DATED — a stamp ahead of this clock makes the age NEGATIVE, which is
 *     less than every threshold there is, so it is maximally fresh forever. A
 *     clock-skewed writer (or a stopped clock on the reader) paints a dead
 *     officer "Active" permanently, and nothing ages it out.
 *
 * Both render the org healthier than any measurement supports, which is the
 * one direction a liveness reading must never fail in.
 *
 * THE DIALECT IS NOT NEW. Same one as `lib/attention/glance.ts` (`badgeState`:
 * absent ≠ unknown ≠ a measured count) and `lib/world/killswitch.ts`
 * (`readingFromPresence`, which already carries this exact skew arm for the
 * presence snapshot). This is that reader for heartbeats, in one place, so the
 * next surface inherits the arms instead of re-opening them.
 *
 * `absent` and `unknown` are deliberately DIFFERENT answers. The store
 * answering "there is no heartbeat for this officer" is a measurement — the
 * officer is not reporting, and red is the honest colour. A heartbeat nobody
 * can parse is not a measurement of anything, and painting it red would be as
 * invented as painting it green; it gets the amber unknown treatment and says
 * why.
 *
 * CLIENT-SAFE BY CONSTRUCTION — zero imports, and no clock of its own: `nowMs`
 * is always passed in, so every arm is reproducible from a fixed instant.
 */

export type Freshness =
  | { state: 'fresh'; ageMs: number }
  | { state: 'stale'; ageMs: number }
  | { state: 'absent' }
  | { state: 'unknown'; reason: string }

/**
 * Tolerated forward clock skew, matching `PRESENCE_MAX_SKEW_MS` in
 * `lib/world/killswitch.ts`. Beyond this the writer's clock and this one
 * disagree by more than any freshness window, so the age is not knowable —
 * which is a different statement from "it is old" or "it is new".
 */
export const MAX_SKEW_MS = 90_000

/**
 * The one decision. `maxAgeMs` is the caller's own freshness bar; everything
 * else is the same for every surface.
 */
export function freshnessOf(
  iso: string | null | undefined,
  nowMs: number,
  maxAgeMs: number,
  maxSkewMs: number = MAX_SKEW_MS
): Freshness {
  if (iso === null || iso === undefined || iso === '') return { state: 'absent' }
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) {
    return {
      state: 'unknown',
      reason:
        'the timestamp could not be read, so how long ago this happened cannot be established',
    }
  }
  const ageMs = nowMs - t
  if (-ageMs > maxSkewMs) {
    return {
      state: 'unknown',
      reason:
        'the timestamp is in the future — the clock that wrote it and this one disagree, so its age cannot be established',
    }
  }
  if (ageMs > maxAgeMs) return { state: 'stale', ageMs }
  // A stamp inside the tolerated forward skew is treated as now, not as
  // negative-age: `Math.max(0, …)` here is a CLAMP ON A KNOWN-GOOD reading,
  // not the one that used to swallow arbitrary skew.
  return { state: 'fresh', ageMs: Math.max(0, ageMs) }
}

/** TRUE only for a reading that measured something. Never for `unknown`. */
export function isMeasured(f: Freshness): boolean {
  return f.state === 'fresh' || f.state === 'stale'
}

/**
 * The word a surface prints. Defence in depth, and the reason it lives here
 * rather than inline: a surface that loses its unknown branch to a refactor or
 * a new skin still cannot print "Active" for a reading nobody could take — the
 * worst it can do is print "Unknown". A static ratchet cannot stop that
 * mutation; a value that never carries the word can.
 */
export function livenessWord(f: Freshness): 'Active' | 'Stale' | 'Down' | 'Unknown' {
  if (f.state === 'fresh') return 'Active'
  if (f.state === 'stale') return 'Stale'
  if (f.state === 'absent') return 'Down'
  return 'Unknown'
}

/** Dual-coded dot (colour never carries alone). `?` is the honest-absence mark. */
export function livenessGlyph(f: Freshness): string {
  if (f.state === 'fresh') return '🟢'
  if (f.state === 'stale') return '🟠'
  if (f.state === 'absent') return '🔴'
  return '❓'
}

/** One plain sentence for a title / aria-label. Never says an unread officer is up. */
export function livenessTitle(f: Freshness): string {
  if (f.state === 'fresh') return 'heartbeat is current'
  if (f.state === 'stale') return 'heartbeat has gone stale'
  if (f.state === 'absent') return 'no heartbeat has been recorded'
  return `heartbeat UNKNOWN: ${f.reason}. This is not "up" and not "down" — unread.`
}
