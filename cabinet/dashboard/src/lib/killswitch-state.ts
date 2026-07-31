/**
 * THE dashboard-side emergency-stop reader — one truth function, server only.
 *
 * There used to be four readers on `cabinet:killswitch` in this app, and two of
 * them disagreed:
 *
 *   layout.tsx / page.tsx   value === 'active'                 → false on anything else
 *   api/world/engine        Boolean(await redis.get(...))      → TRUE on anything non-empty
 *   api/world/stream        presence?.killswitch ?? false      → false on absence
 *
 * So the same unrecognised reply (a NOAUTH error string, say) rendered the
 * header pill "fleet running" and the sky "storm" at the same moment, and every
 * failure path in three of the four produced a confident "not engaged". The
 * decision now lives once, in `lib/world/killswitch.ts` (pure, client-safe);
 * this module is only the door to the shared client.
 *
 * MOCK MODE IS NOT A READING. With `REDIS_URL` unset the shared client is an
 * in-process object seeded with `'cabinet:killswitch': ''`, so `=== 'active'`
 * answered "not engaged" about a fleet this process has never contacted. That
 * is the census defect with the safety switch substituted for the count.
 */
// NOTE: no `import 'server-only'` — that package is not a dependency here, and
// adding one to mark a boundary the import graph already enforces is not worth
// a new install. This module pulls `@/lib/redis`, which `require`s ioredis;
// importing it from a `'use client'` component breaks the client bundle at
// build time, loudly. The pure half every client component needs lives in
// `lib/world/killswitch.ts`, which imports nothing at all.
import redis, { isMockRedis, storeReading } from '@/lib/redis'
import {
  DEMO_STORE_REASON,
  NO_STORE_CONFIGURED_REASON,
  readingFromKey,
  unknownKillswitch,
  type KillswitchReading,
} from '@/lib/world/killswitch'

export async function readKillswitch(): Promise<KillswitchReading> {
  // Both not-live postures are unknown, and each says which one it is. They
  // used to share one sentence that claimed the page was showing demo data —
  // true of one posture and false of the other.
  if (isMockRedis) {
    return unknownKillswitch(
      storeReading.fabricated ? DEMO_STORE_REASON : NO_STORE_CONFIGURED_REASON
    )
  }
  try {
    // `contacted: true` is earned: ioredis REJECTS on NOAUTH / NOPERM /
    // WRONGTYPE / LOADING rather than resolving them as data (which is what
    // defeated the shell readers), so reaching this line means a live client
    // answered. Anything other than the literal `active` is still unknown, not
    // clear — the closed enum is in readingFromKey.
    return readingFromKey(await redis.get('cabinet:killswitch'), true)
  } catch (err) {
    return unknownKillswitch(
      `the store that holds the emergency stop could not be reached (${
        err instanceof Error ? err.message : 'unknown error'
      })`
    )
  }
}
