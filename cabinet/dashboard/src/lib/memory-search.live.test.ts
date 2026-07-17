// memory-search LIVE smoke — opt-in end-to-end parity check against the
// REAL cabinet_memory store + embedding provider (review fix 2026-07-17).
//
// The unit suite mocks pg and fetch, so it can never catch a wire-text /
// floor-calibration divergence from shell memory_search (that is exactly how
// the 2026-07-17 P2 shipped: hybrid arm blanked on-corpus queries the shell
// answered). This smoke runs the real thing ONCE, on demand:
//
//   LIBRARY_SEARCH_LIVE_SMOKE=1 \
//   NEON_CONNECTION_STRING=… VOYAGE_API_KEY=… \
//   npx vitest run src/lib/memory-search.live.test.ts
//
// Compare against the shell engine on the same box for hit overlap:
//   source cabinet/scripts/lib/memory.sh && memory_search "killswitch doctrine"
//
// SKIPPED everywhere by default: it requires the explicit opt-in flag AND
// both secrets in env — a configured CI box still won't dial out unless
// asked. Read-only (searchMemory issues single SELECTs); no disk writes; no
// secrets read beyond process env; nothing logged beyond vitest output.

import { describe, it, expect } from 'vitest'
import { searchMemory } from './memory-search'

const optedIn =
  process.env.LIBRARY_SEARCH_LIVE_SMOKE === '1' &&
  !!process.env.NEON_CONNECTION_STRING &&
  !!process.env.VOYAGE_API_KEY

// Query + expected hit ride env so the smoke survives corpus evolution;
// defaults pin the canonical on-corpus case from the 2026-07-17 review.
const LIVE_QUERY = process.env.LIVE_SMOKE_QUERY || 'killswitch doctrine'
const LIVE_EXPECT =
  process.env.LIVE_SMOKE_EXPECT || 'constitution/KILLSWITCH.md'

describe.runIf(optedIn)('LIVE smoke — hybrid arm against the real store', () => {
  it(
    `hybrid search returns hits incl. ${LIVE_EXPECT} (no degrade, no 0-hit blank)`,
    async () => {
      const res = await searchMemory(LIVE_QUERY, 5)
      // Embed key is live → the semantic arm must actually run.
      expect(res.degraded).toBe(false)
      // The on-corpus row the shell engine returns for the same query must
      // surface here too (wire-text parity + floor calibration).
      expect(res.hits.length).toBeGreaterThan(0)
      expect(res.hits.map((h) => h.source_id)).toContain(LIVE_EXPECT)
    },
    60_000
  )
})
