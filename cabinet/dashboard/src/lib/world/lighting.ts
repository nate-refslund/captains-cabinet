/**
 * Day/night lighting read-model — PURE mapping from the server-stamped
 * snapshot clock to Wardroom ambience (grammar v2 `night` block; world-alive
 * direction 2026-07-08 §2 "Lighting & day/night").
 *
 * DOCTRINE:
 *  - Wall-clock time enters the render path ONLY as data on the SSE snapshot
 *    (`WorldSnapshot.clock`, server-computed in stream/route.ts from the
 *    Captain timezone). Nothing in this module reads a clock — the CI
 *    ratchet greps this tree for Date.now / Math.random.
 *  - Lighting drives AMBIENCE only — never state, never morphology (the
 *    grammar night codex says exactly this).
 *  - §12 law: night = warm lamp pools + moon-tint, never murky. The lamp
 *    amber is LAMPLIGHT, not signal-amber — the reserved salience palette
 *    (green/amber/red/grey/purple) stays untouched on status surfaces
 *    (dual-coding rule; morphology.yml law block).
 *  - No clock on the snapshot → bucket 'day' → zero tint (honest neutral:
 *    absence of data renders as no claim, not as invented night).
 */
import { fnv1a } from './hash'

export type DayBucket = 'dawn' | 'day' | 'dusk' | 'night'

/** [startHour, endHour) ranges; a range may wrap midnight (e.g. [21, 6)). */
export type BucketRanges = Partial<Record<DayBucket, [number, number]>>

/** Grammar-law defaults (show-grammar.yml v2 `night.buckets`). */
export const DEFAULT_BUCKETS: Record<DayBucket, [number, number]> = {
  dawn: [6, 8],
  day: [8, 18],
  dusk: [18, 21],
  night: [21, 6],
}

/** True when hour h falls inside [a, z) treating z<=a as a midnight wrap. */
function inRange(h: number, a: number, z: number): boolean {
  return a < z ? h >= a && h < z : h >= a || h < z
}

/**
 * Snapshot hour → day bucket. Pure; identical inputs yield identical
 * buckets forever. `ranges` (from the parsed grammar `night.buckets`)
 * overrides the defaults per bucket; dawn/day/dusk are checked in order and
 * night is the wrap-around remainder, so a malformed/partial law still
 * resolves to exactly one bucket (fail-closed to the calmest reading).
 */
export function bucketForHour(
  hour: number | null | undefined,
  ranges?: BucketRanges
): DayBucket {
  if (hour === null || hour === undefined || !Number.isFinite(hour)) {
    return 'day' // no clock on the snapshot → no tint claim
  }
  const h = ((Math.floor(hour) % 24) + 24) % 24
  const r = { ...DEFAULT_BUCKETS, ...ranges }
  for (const b of ['dawn', 'day', 'dusk'] as const) {
    const [a, z] = r[b]
    if (inRange(h, a, z)) return b
  }
  return 'night'
}

/**
 * THE AMBIENCE PASS DOES NOT LIVE HERE ANY MORE, and the two deletions that got
 * it here are the reason this note replaces it rather than nothing.
 *
 * `ambientTint` was a per-bucket alpha wash. It was deleted 2026-07-29 once it had
 * been dead long enough to become a trap: it still returned the apricot the veil
 * laws had just banned, and a green test asserted it.
 *
 * `ambientVeil` was the opaque seeded dither that replaced it — a per-bucket hue
 * table plus a coverage. Deleted 2026-07-30: a dither pays for every unit of
 * darkness with a unit of the art's own grain, so it could not express night at
 * all (THE AMBIENCE STRUCTURE LAW, lib/world/ambience.ts, with the arithmetic and
 * the live-frame measurements). Ambience is now `ambienceLut(bucket)` there — a
 * colour map, not an overlay — and this module keeps only the parts that ARE
 * per-bucket ambience data: the window sky, the lamps, the stars. `WINDOW_SKY` is
 * additionally the SOURCE of the remap's hue direction, so the two halves of the
 * lighting model can no longer disagree about what hour it is.
 */
/** Warm additive pool under desk lamps + the kettle nook at dusk/night. */
export interface LampGlow {
  color: number
  alpha: number
  radiusPx: number
}

/** Lamplight (0xffb050@0.15, r=28px) — warm decor light, NOT signal-amber. */
export function lampGlow(bucket: DayBucket): LampGlow | null {
  return bucket === 'dusk' || bucket === 'night'
    ? { color: 0xffb050, alpha: 0.15, radiusPx: 28 }
    : null
}

/**
 * Window sky fill per bucket — drawn BEHIND the window sprite's transparent
 * glass (the Room_Builder window cut has a see-through pane; the sky is a
 * lighting overlay, not invented art). light blue / bright / amber dusk /
 * dark blue with stars, per the direction doc.
 */
export const WINDOW_SKY: Record<DayBucket, number> = {
  dawn: 0xa9c6e8,
  day: 0xbfe3f2,
  dusk: 0xe8a860,
  night: 0x1c2a52,
}

export function windowSky(bucket: DayBucket): number {
  return WINDOW_SKY[bucket]
}

/** Night-sky star pixel color (drawn only in the night bucket). */
export const STAR_COLOR = 0xd8e0f0

/**
 * Seeded star offsets inside a window's glass rect (night only).
 * Deterministic per window id — the same window shows the same sky forever.
 */
export function starOffsets(
  windowId: string,
  count = 3,
  glassW = 16,
  glassH = 26
): Array<{ x: number; y: number }> {
  const out: Array<{ x: number; y: number }> = []
  const w = Math.max(1, glassW - 1)
  const h = Math.max(1, glassH - 1)
  for (let k = 0; k < count; k++) {
    out.push({
      x: fnv1a(`${windowId}:star:${k}:x`) % w,
      y: fnv1a(`${windowId}:star:${k}:y`) % h,
    })
  }
  return out
}

/** HH:MM chip text from the snapshot clock (DOM text — text is never canvas). */
export function formatClock(
  clock: { hour: number; minute: number } | null | undefined
): string | null {
  if (!clock || !Number.isFinite(clock.hour) || !Number.isFinite(clock.minute)) {
    return null
  }
  const h = ((Math.floor(clock.hour) % 24) + 24) % 24
  const m = ((Math.floor(clock.minute) % 60) + 60) % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
