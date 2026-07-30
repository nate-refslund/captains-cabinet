/**
 * The CLIENT-SAFE half of the attention glance — pure, zero imports.
 *
 * WHY IT IS ITS OWN FILE. `lib/attention/queue.ts` reads the census off disk,
 * so it imports `node:fs`/`node:os`/`node:path`. The glance strip
 * (`components/needs-you-badge.tsx`) is a `'use client'` component, and
 * importing the reader from it broke the Turbopack client bundle outright —
 * "Code generation for chunk item errored", every page 500. Neither `tsc` nor
 * the vitest suite saw it (both run in node); only starting the app did. So the
 * decision the client needs lives here, where nothing node-only can follow it.
 *
 * `attentionGlance` and `mastheadCount` stay in queue.ts: they take a
 * QueuePayload and are used from the SERVER component only.
 */

/** What the world draws where a number would go, when nobody took one. */
export const UNMEASURED_GLYPH = '—'

/** What the glance strip does: nothing yet asked / unknown / a real count. */
export type BadgeState =
  | { show: 'nothing' }
  | { show: 'unknown' }
  | { show: 'count'; n: number }

/**
 * `undefined` = not asked yet, `null` = asked and nobody could tell.
 *
 * Both used to be `0`, and 0 hides the badge — so "I have not looked" and "the
 * org is dead" both rendered as the same zero pixels as "nothing is waiting".
 * Only a MEASURED zero may hide, because hiding is itself a claim.
 */
export function badgeState(n: number | null | undefined): BadgeState {
  if (n === undefined) return { show: 'nothing' }
  if (n === null || !Number.isFinite(n)) return { show: 'unknown' }
  return n > 0 ? { show: 'count', n } : { show: 'nothing' }
}
