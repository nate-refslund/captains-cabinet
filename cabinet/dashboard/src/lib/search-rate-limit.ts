/**
 * search-rate-limit.ts — light per-session in-memory rate limit for the
 * Library search endpoint.
 *
 * Sliding window per key (default 30 requests / 60s). In-memory by design:
 * the dashboard is a single-process Next server; this is a courtesy brake on
 * runaway clients (debounce bugs, world-librarian loops), not a security
 * boundary — auth is the middleware cookie gate.
 *
 * Keys never contain secrets: the session cookie value is sha256-hashed
 * (truncated) before use, and nothing here is ever logged.
 */

import { createHash } from 'node:crypto'

const WINDOW_MS = 60_000
const MAX_REQUESTS = 30
/** Bound the key map so an unauthenticated scanner can't grow memory. */
const MAX_KEYS = 1_000

const buckets = new Map<string, number[]>()

/**
 * Derive the rate key for a request: hashed session cookie when present,
 * else the first X-Forwarded-For hop, else a shared local bucket.
 */
export function searchRateKey(
  sessionCookie: string | undefined,
  forwardedFor: string | null | undefined
): string {
  if (sessionCookie) {
    return (
      'sess:' +
      createHash('sha256').update(sessionCookie).digest('hex').slice(0, 32)
    )
  }
  const hop = (forwardedFor || '').split(',')[0].trim()
  return 'anon:' + (hop || 'local')
}

/**
 * Record one request for `key`; returns false when the key is over budget
 * (caller responds 429). O(window) per call; oldest keys evicted beyond
 * MAX_KEYS (Map re-insert keeps eviction LRU-ish).
 */
export function allowSearch(key: string, now: number = Date.now()): boolean {
  let stamps = buckets.get(key)
  if (!stamps) {
    if (buckets.size >= MAX_KEYS) {
      const oldest = buckets.keys().next().value
      if (oldest !== undefined) buckets.delete(oldest)
    }
    stamps = []
  } else {
    buckets.delete(key) // re-insert below → most-recently-used tail
  }
  buckets.set(key, stamps)

  const cutoff = now - WINDOW_MS
  while (stamps.length > 0 && stamps[0] <= cutoff) stamps.shift()

  if (stamps.length >= MAX_REQUESTS) return false
  stamps.push(now)
  return true
}

/** Test seam: drop all buckets. */
export function resetSearchRateLimit(): void {
  buckets.clear()
}
