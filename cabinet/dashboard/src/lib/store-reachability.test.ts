/**
 * THE BOUNDS AND THE BREAKER, DRIVEN — including both inverse directions.
 *
 * The dead-store direction is easy to test and easy to over-fix: a change that
 * turned EVERY reading into "unreachable" would pass every arm that only checks
 * the failure path. So each behaviour below is paired with its inverse — a
 * healthy client stays measured, a success closes the breaker, a measured zero
 * is still a zero. Both directions or it is not a sensor.
 *
 * The end-to-end proof against a real ioredis client and a real unreachable
 * socket is `store-unreachable.e2e.test.ts`; this file drives the machinery
 * directly so the degenerate ends can be reached at all.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  COMMAND_TIMEOUT_MS,
  CONNECT_TIMEOUT_MS,
  HARD_DEADLINE_MS,
  LIVE_CLIENT_OPTIONS,
  MAX_RETRIES_PER_REQUEST,
  StoreBreaker,
  StoreUnreachableError,
  UNREACHABLE_COOLDOWN_MS,
  guardCommands,
  withDeadline,
} from './store-reachability'

describe('the bounds themselves', () => {
  it('are all finite and positive — an unset bound is an unbounded wait', () => {
    for (const [name, v] of Object.entries({
      CONNECT_TIMEOUT_MS,
      COMMAND_TIMEOUT_MS,
      HARD_DEADLINE_MS,
      UNREACHABLE_COOLDOWN_MS,
    })) {
      expect(Number.isFinite(v), name).toBe(true)
      expect(v, name).toBeGreaterThan(0)
    }
  })

  it('put the hard deadline ABOVE the command timeout', () => {
    // The race is a backstop for the shape where ioredis's own timer does not
    // apply (socket alive, client never `ready`). If it fired first it would be
    // the only bound in play and ioredis's would be dead code — a control that
    // never runs is a control nobody has tested.
    expect(HARD_DEADLINE_MS).toBeGreaterThan(COMMAND_TIMEOUT_MS)
  })

  it('keeps the offline queue ON', () => {
    // With it off, the first command of a cold process fails while the socket is
    // still connecting, so a perfectly healthy store renders "unreachable" on
    // every cold start. This is the inverse defect, and it is a one-word change
    // away at all times.
    expect(LIVE_CLIENT_OPTIONS.enableOfflineQueue).toBe(true)
  })

  it('hands the live client every bound — not just the ones that are easy', () => {
    expect(LIVE_CLIENT_OPTIONS).toEqual({
      connectTimeout: CONNECT_TIMEOUT_MS,
      commandTimeout: COMMAND_TIMEOUT_MS,
      maxRetriesPerRequest: MAX_RETRIES_PER_REQUEST,
      enableOfflineQueue: true,
    })
  })

  it('does not leave maxRetriesPerRequest at the ioredis default of 20', () => {
    // Measured: 20 retries is where the 10 546ms ECONNREFUSED wait came from.
    expect(MAX_RETRIES_PER_REQUEST).toBeLessThan(20)
  })
})

describe('withDeadline', () => {
  it('rejects a promise that never settles', async () => {
    vi.useFakeTimers()
    try {
      const never = new Promise<string>(() => {})
      const raced = withDeadline(never, 1000, 'get')
      const settled = raced.catch((e) => e)
      await vi.advanceTimersByTimeAsync(1001)
      const err = await settled
      expect(err).toBeInstanceOf(StoreUnreachableError)
      expect((err as StoreUnreachableError).reason).toContain('within 1000ms')
      expect((err as StoreUnreachableError).reason).toContain('get')
    } finally {
      vi.useRealTimers()
    }
  })

  it('INVERSE — a promise that resolves in time passes its value straight through', async () => {
    await expect(withDeadline(Promise.resolve('PONG'), 1000, 'ping')).resolves.toBe('PONG')
  })

  it('INVERSE — a resolved FALSY value is not mistaken for a failure', async () => {
    // `null` is the answer for an absent key and 0 is a measured zero. A
    // deadline wrapper that treated either as "no answer" would turn every
    // absent key into an unreachable store.
    await expect(withDeadline(Promise.resolve(null), 1000, 'get')).resolves.toBeNull()
    await expect(withDeadline(Promise.resolve(0), 1000, 'del')).resolves.toBe(0)
  })

  it('propagates the underlying rejection rather than masking it as a timeout', async () => {
    const boom = new Error('WRONGTYPE')
    await expect(withDeadline(Promise.reject(boom), 1000, 'get')).rejects.toThrow('WRONGTYPE')
  })
})

describe('the breaker', () => {
  it('starts closed and reports "nothing tried yet" — not "reachable"', () => {
    const b = new StoreBreaker(5000)
    expect(b.isOpen(0)).toBe(false)
    expect(b.reading(0)).toEqual({ reachable: null, reason: null })
  })

  it('opens on ONE failure and refuses for exactly the cooldown', () => {
    const b = new StoreBreaker(5000)
    b.trip(1_000, 'the store did not answer `get` within 3000ms')
    expect(b.isOpen(1_000)).toBe(true)
    expect(b.isOpen(5_999)).toBe(true)
    expect(b.isOpen(6_000)).toBe(false) // cooldown elapsed → try again
    expect(b.reading(2_000)).toEqual({
      reachable: false,
      reason: 'the store did not answer `get` within 3000ms',
    })
  })

  it('INVERSE — a success closes it immediately and it reports reachable', () => {
    const b = new StoreBreaker(5000)
    b.trip(1_000, 'down')
    expect(b.isOpen(1_500)).toBe(true)
    b.succeed()
    expect(b.isOpen(1_500)).toBe(false)
    expect(b.reading(1_500)).toEqual({ reachable: true, reason: null })
  })

  it('INVERSE — never opens on its own; only a recorded failure opens it', () => {
    const b = new StoreBreaker(5000)
    for (const t of [0, 1, 10_000, 1e9]) expect(b.isOpen(t)).toBe(false)
  })

  it('always has a reason to give while open', () => {
    const b = new StoreBreaker(5000)
    b.trip(0, '')
    expect(b.reason.length).toBeGreaterThan(0)
  })
})

/** A client whose commands never settle — the mute-accept shape, in miniature. */
function hangingClient() {
  let calls = 0
  return {
    calls: () => calls,
    client: {
      get: async () => {
        calls++
        return new Promise<string | null>(() => {})
      },
      keys: async () => {
        calls++
        return new Promise<string[]>(() => {})
      },
    },
  }
}

describe('guardCommands', () => {
  it('turns a call that never settles into a rejection, not a hang', async () => {
    vi.useFakeTimers()
    try {
      const { client } = hangingClient()
      const g = guardCommands(client, ['get'], new StoreBreaker(5000), {
        deadlineMs: 500,
      })
      const settled = g.get().catch((e) => e)
      await vi.advanceTimersByTimeAsync(501)
      const err = await settled
      expect(err).toBeInstanceOf(StoreUnreachableError)
    } finally {
      vi.useRealTimers()
    }
  })

  it('THE PAGE BOUND — after the first failure the underlying client is not called again', async () => {
    // This is the arm that justifies the breaker's existence. Measured without
    // one, per-command bounds alone left `getCostHistory(30)`'s 31 sequential
    // calls at 51-74 SECONDS against the three unreachable shapes. One page must
    // pay one timeout, not thirty-one.
    vi.useFakeTimers()
    try {
      const h = hangingClient()
      let clock = 0
      const g = guardCommands(h.client, ['get'], new StoreBreaker(5000), {
        deadlineMs: 500,
        now: () => clock,
      })
      const first = g.get().catch((e) => e)
      await vi.advanceTimersByTimeAsync(501)
      expect(await first).toBeInstanceOf(StoreUnreachableError)
      expect(h.calls()).toBe(1)

      // The next thirty resolve instantly, without touching the client at all.
      for (let i = 0; i < 30; i++) {
        const err = await g.get().catch((e) => e)
        expect(err).toBeInstanceOf(StoreUnreachableError)
        expect((err as StoreUnreachableError).reason).toContain('not retried')
      }
      expect(h.calls()).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('lets one call through again once the cooldown has elapsed', async () => {
    vi.useFakeTimers()
    try {
      const h = hangingClient()
      let clock = 0
      const g = guardCommands(h.client, ['get'], new StoreBreaker(5000), {
        deadlineMs: 500,
        now: () => clock,
      })
      const first = g.get().catch((e) => e)
      await vi.advanceTimersByTimeAsync(501)
      await first
      expect(h.calls()).toBe(1)

      clock = 5_000 // cooldown elapsed
      const second = g.get().catch((e) => e)
      await vi.advanceTimersByTimeAsync(501)
      await second
      expect(h.calls()).toBe(2) // it tried again — recovery is automatic
    } finally {
      vi.useRealTimers()
    }
  })

  it('INVERSE — a healthy client is untouched: values pass through and nothing trips', async () => {
    const breaker = new StoreBreaker(5000)
    const client = {
      get: async (k: string) => (k === 'present' ? 'value' : null),
      keys: async () => ['a', 'b'],
      hgetall: async () => ({ cos_cost_micro: '0' }),
    }
    const g = guardCommands(client, ['get', 'keys', 'hgetall'], breaker)
    expect(await g.get('present')).toBe('value')
    // An ABSENT key still answers null — a measured absence, not a failure.
    expect(await g.get('missing')).toBeNull()
    expect(await g.keys()).toEqual(['a', 'b'])
    // A MEASURED ZERO survives the wrapper intact.
    expect(await g.hgetall()).toEqual({ cos_cost_micro: '0' })
    expect(breaker.isOpen(Date.now())).toBe(false)
    expect(breaker.reading(Date.now()).reachable).toBe(true)
  })

  it('a rejecting command trips the breaker and keeps the underlying message', async () => {
    const breaker = new StoreBreaker(5000)
    const g = guardCommands(
      {
        get: async () => {
          throw new Error('NOAUTH Authentication required')
        },
      },
      ['get'],
      breaker
    )
    const err = await g.get().catch((e) => e)
    expect(err).toBeInstanceOf(StoreUnreachableError)
    expect((err as StoreUnreachableError).reason).toContain('NOAUTH')
    expect(breaker.isOpen(Date.now())).toBe(true)
  })

  it('guards every method it is given, and only those', () => {
    const client = { get: async () => null, keys: async () => [], nope: 1 }
    const g = guardCommands(client as never, ['get', 'keys'] as never, new StoreBreaker())
    expect(typeof (g as { get: unknown }).get).toBe('function')
    expect(typeof (g as { keys: unknown }).keys).toBe('function')
    // Anything not listed is absent rather than silently unguarded — a call to
    // it is a TypeError at the callsite, which is loud. An unguarded passthrough
    // would be the hang again on whichever command nobody listed.
    expect((g as Record<string, unknown>).nope).toBeUndefined()
  })
})
