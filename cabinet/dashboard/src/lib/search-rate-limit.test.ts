// search-rate-limit — sliding-window behavior + key derivation.

import { describe, it, expect, beforeEach } from 'vitest'
import {
  allowSearch,
  searchRateKey,
  resetSearchRateLimit,
} from './search-rate-limit'

const T0 = 1_700_000_000_000

beforeEach(() => {
  resetSearchRateLimit()
})

describe('allowSearch — sliding window', () => {
  it('allows 30 requests then blocks the 31st within the window', () => {
    for (let i = 0; i < 30; i++) {
      expect(allowSearch('k1', T0 + i)).toBe(true)
    }
    expect(allowSearch('k1', T0 + 30)).toBe(false)
  })

  it('recovers once the window slides past old stamps', () => {
    for (let i = 0; i < 30; i++) allowSearch('k1', T0 + i)
    expect(allowSearch('k1', T0 + 100)).toBe(false)
    // 60s after the first stamp, budget frees up again.
    expect(allowSearch('k1', T0 + 60_001)).toBe(true)
  })

  it('keys are independent buckets', () => {
    for (let i = 0; i < 30; i++) allowSearch('a', T0 + i)
    expect(allowSearch('a', T0 + 31)).toBe(false)
    expect(allowSearch('b', T0 + 31)).toBe(true)
  })

  it('bounds the key map (oldest key evicted beyond 1000)', () => {
    for (let i = 0; i < 30; i++) allowSearch('victim', T0 + i)
    expect(allowSearch('victim', T0 + 31)).toBe(false)
    // Flood 1000 fresh keys — 'victim' (oldest) gets evicted.
    for (let i = 0; i < 1000; i++) allowSearch(`flood-${i}`, T0 + 32)
    // Evicted bucket restarts clean: the flood cannot be used to KEEP state,
    // and memory stays bounded.
    expect(allowSearch('victim', T0 + 33)).toBe(true)
  })
})

describe('searchRateKey — no raw secrets in keys', () => {
  it('hashes the session cookie (raw value never appears)', () => {
    const cookie = 'super-secret-session-token.abcdef'
    const key = searchRateKey(cookie, null)
    expect(key.startsWith('sess:')).toBe(true)
    expect(key).not.toContain('super-secret')
    expect(key).not.toContain(cookie)
    expect(key.length).toBeLessThan(64)
    // Deterministic per cookie.
    expect(searchRateKey(cookie, null)).toBe(key)
    expect(searchRateKey('other', null)).not.toBe(key)
  })

  it('falls back to the first X-Forwarded-For hop', () => {
    expect(searchRateKey(undefined, '1.2.3.4, 10.0.0.1')).toBe('anon:1.2.3.4')
  })

  it('falls back to a shared local bucket with neither', () => {
    expect(searchRateKey(undefined, null)).toBe('anon:local')
    expect(searchRateKey(undefined, '')).toBe('anon:local')
  })
})
