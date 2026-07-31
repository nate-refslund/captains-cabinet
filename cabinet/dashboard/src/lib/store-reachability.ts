/**
 * A STORE THAT CANNOT BE REACHED MUST SAY SO — never hang, never invent.
 *
 * WHY THIS FILE EXISTS. `lib/store-posture.ts` closed the case where nothing is
 * configured. It said, in its own docstring, that the OTHER case was still open:
 *
 *     "The separate case — REDIS_URL SET but unreachable — is untouched by this
 *      module and still carries that hazard."
 *
 * That case is the ordinary shape of a production outage (an env var pointing at
 * a host that has died), where an ABSENT env var is a deploy mistake. And it was
 * the worse failure of the two, because an ioredis client with nothing behind it
 * QUEUES commands rather than failing them. A hanging dashboard is arguably
 * worse than a lying one: the Captain gets no page, no banner and no signal —
 * just a spinner he cannot tell from a slow network.
 *
 * MEASURED, 2026-07-31, ioredis 5.10.1 on node 26, one `GET` issued on a fresh
 * client with the options `lib/redis.ts` used at the time (i.e. none):
 *
 *   | unreachable shape                              | default options     |
 *   |------------------------------------------------|---------------------|
 *   | blackhole — SYN dropped (firewall DROP, dead    | NEVER SETTLED       |
 *   |   host, wrong subnet); 192.0.2.1 per RFC 5737   | (>65s, still pending)|
 *   | refused — host up, redis down (ECONNREFUSED)    | rejected @ 10 546ms |
 *   | mute accept — TCP accepted, no reply ever (a    | NEVER SETTLED       |
 *   |   proxy/LB in front of a dead backend, or a     | (>65s, still pending)|
 *   |   redis stuck loading an RDB)                   |                     |
 *   | HEALTHY control (real local store)              | resolved @ 11ms     |
 *
 * Two of the three shapes do not settle at all, and the one that does takes ten
 * and a half seconds. That is the defect, reproduced.
 *
 * WHAT A LEGITIMATELY SLOW STORE LOOKS LIKE, versus a dead one — the question
 * the numbers below had to answer, because a bound that cannot tell them apart
 * would trade a hang for a lie in the other direction (every reading "unknown"
 * would pass every honesty test in this repo and be just as useless).
 *
 * The two are distinguished by CONNECTION, not by latency:
 *
 *   - Connect is a function of network round trips and nothing else. One RTT
 *     plain, three with TLS. The worst legitimate intercontinental case is
 *     ~300ms RTT × 3 ≈ 900ms. Measured against the cabinet's own store: 1ms,
 *     five cold connects in a row. So a handshake that has not completed in
 *     `CONNECT_TIMEOUT_MS` is not slow — nothing on the public internet is that
 *     slow — it is unreachable.
 *   - A command's reply is one RTT plus server work, and the only command this
 *     app issues that can be genuinely slow is `KEYS`, which is O(N) over the
 *     whole keyspace. Measured on the cabinet's store: `KEYS *` over 61 keys,
 *     0ms; `PING` ×200, p50 0.057ms / p99 0.122ms. A pathological million-key
 *     store would spend a few hundred ms of server CPU on `KEYS`. Budgeting
 *     300ms RTT + that leaves `COMMAND_TIMEOUT_MS` with roughly 5× headroom
 *     over any store that is actually answering.
 *
 * WHY A BREAKER IS NOT OPTIONAL. Per-command bounds alone do not bound a PAGE.
 * `getCostHistory(30)` issues 1 `KEYS` + 30 sequential `HGETALL`. Measured with
 * the per-command bounds below and NO breaker:
 *
 *   | shape      | 31 sequential calls |
 *   |------------|---------------------|
 *   | blackhole  | 74 364ms            |
 *   | refused    | 51 102ms            |
 *   | mute       | 71 875ms            |
 *
 * Still a hang from the Captain's chair. So the first failure trips a breaker
 * and every later call in the cooldown fails INSTANTLY with the same reason:
 * one page pays one timeout, not thirty-one.
 *
 * WHY IT IS A THROW AND NOT AN EMPTY ANSWER. "The store did not answer" is not
 * "the store answered nothing", and this codebase already has the vocabulary for
 * the difference — `readingFromKey(value, contacted)` in `lib/world/killswitch.ts`
 * takes `contacted` as the caller's proof that a live client replied, and a
 * resolved `null` under `contacted: true` is a MEASURED "the emergency stop is
 * clear". Returning `null` from an unreachable store would earn that claim about
 * a fleet nobody reached — the exact defect PR #330 closed one level up. A throw
 * is how the caller learns `contacted: false`, and `killswitch-state.ts` already
 * catches it and says so in plain words.
 *
 * CLIENT-SAFE BY CONSTRUCTION — zero imports, same rule as `lib/store-posture.ts`
 * and `lib/world/killswitch.ts`. A `'use client'` surface that pulls a module
 * with `node:fs` in its import graph breaks the Turbopack client bundle outright
 * (every page 500) while `tsc` and the whole vitest suite stay green. Nothing
 * node-only may ever be imported here, and the clock is INJECTED rather than
 * read off `Date.now()` inside the state machine, so every end is testable.
 */

/**
 * TCP + handshake bound. See the table above: measured 1ms against a real store,
 * ~900ms worst-case intercontinental TLS. 2s is >2× the worst legitimate case.
 */
export const CONNECT_TIMEOUT_MS = 2_000

/**
 * Per-command reply bound. Must survive a legitimately slow O(N) `KEYS` on a
 * loaded store plus intercontinental RTT; measured 0ms on the cabinet's own
 * store. This is the bound that fires first for the blackhole and mute shapes
 * (both settled at ~3 004ms once it was set).
 */
export const COMMAND_TIMEOUT_MS = 3_000

/**
 * The outer hard deadline, raced against every call.
 *
 * Deliberately ABOVE `COMMAND_TIMEOUT_MS` so ioredis's own timer normally wins
 * and this never fires in the shapes that were measured. It exists because a
 * bound that lives inside the library is a bound that depends on the library
 * applying it to the state the client is actually in — and the mute-accept shape
 * is exactly a state where a socket is alive, the client is not `ready`, and
 * nothing outside a race can promise the caller an answer. A control you have
 * never tried to defeat is an assumption.
 */
export const HARD_DEADLINE_MS = 4_000

/**
 * How long the breaker stays open before it lets one call through again.
 *
 * Short on purpose. The cost of being wrong in the closed direction is one more
 * timeout; the cost of being wrong in the open direction is a dashboard that
 * keeps saying "unreachable" about a store that came back. Recovery must be
 * automatic and fast, because nobody is going to restart the dashboard.
 */
export const UNREACHABLE_COOLDOWN_MS = 5_000

/**
 * Retries a QUEUED command tolerates before it is rejected.
 *
 * ioredis defaults to 20, which is where the 10 546ms in the refused row came
 * from: twenty reconnect attempts with a growing backoff, all of them spent
 * before the command was allowed to fail. One is enough to ride out a socket
 * that is being replaced; it is not a substitute for a timeout.
 */
export const MAX_RETRIES_PER_REQUEST = 1

/**
 * The options handed to the live client — exported so the fence asserts the
 * VALUES the constructor received rather than searching the file for text. A
 * grep-shaped fence proves a string is present; this proves the client is bound.
 */
export const LIVE_CLIENT_OPTIONS = {
  connectTimeout: CONNECT_TIMEOUT_MS,
  commandTimeout: COMMAND_TIMEOUT_MS,
  maxRetriesPerRequest: MAX_RETRIES_PER_REQUEST,
  // Kept TRUE deliberately. With the offline queue off, the very first command
  // of a cold process — issued while the socket is still connecting — fails
  // immediately, so a perfectly healthy store would render "unreachable" on
  // every cold start. That is the inverse defect, and it would pass every arm
  // that only checks the dead-store direction.
  enableOfflineQueue: true,
} as const

/**
 * The bounds for a REQUEST-SCOPED client — one built inside a route handler and
 * thrown away, rather than the module-level singleton.
 *
 * There are nine ioredis constructions in this app, not one. Bounding only the
 * shared client left `/queue` hanging for 45 SECONDS in the built app against a
 * mute store (measured; `lib/attention/queue.ts` builds its own), and left the
 * rail, the tasks publisher and three subscribers unbounded. A wall on one
 * channel is not a wall — enumerate every channel that reaches the thing you
 * fenced.
 *
 * TWO PARTIAL DIALECTS ALREADY EXISTED (`api/world/stream`, `api/world/engine`:
 * `{lazyConnect, maxRetriesPerRequest: 1, connectTimeout: 900}`) and BOTH still
 * hang on the mute-accept shape, because neither carries a `commandTimeout` and
 * that shape completes its TCP connect. They are folded in here rather than left
 * as a third spelling of the same idea.
 *
 * `connectTimeout` moves 900ms → 2 000ms for those two routes, deliberately: 900
 * is marginal for a legitimately remote managed store (~900ms worst-case
 * intercontinental TLS), and they gain a command bound they did not have, which
 * is the bound that actually closes their hang. Net strictly stronger.
 *
 * `enableOfflineQueue` is left at the ioredis default here rather than forced,
 * because `lazyConnect` changes when the first command is issued and the
 * healthy-path interaction between the two is not something this change can
 * prove for a client it does not own.
 */
export const REQUEST_CLIENT_OPTIONS = {
  lazyConnect: true,
  connectTimeout: CONNECT_TIMEOUT_MS,
  commandTimeout: COMMAND_TIMEOUT_MS,
  maxRetriesPerRequest: MAX_RETRIES_PER_REQUEST,
} as const

/**
 * The bounds for a SUBSCRIBER connection.
 *
 * Deliberately WITHOUT `commandTimeout`. A subscriber holds a long-lived socket
 * and receives pushed messages rather than replies; applying a per-command bound
 * to it is very likely harmless and possibly right, but this change cannot prove
 * the healthy subscriber path (its fake store answers commands, not pub/sub), and
 * an unproven change to a long-lived connection is how a silent break ships. So
 * the connect bound and the retry bound go on now — strictly better than the
 * nothing they carried — and the command bound is filed rather than guessed.
 */
export const SUBSCRIBER_CLIENT_OPTIONS = {
  connectTimeout: CONNECT_TIMEOUT_MS,
  maxRetriesPerRequest: MAX_RETRIES_PER_REQUEST,
} as const

/** What the Captain can run to settle it out of band. */
export const STORE_CHECK_COMMAND = 'redis-cli -u "$REDIS_URL" ping'

/**
 * The error every guarded call rejects with.
 *
 * A named type rather than a bare `Error` so a consumer can tell "the store did
 * not answer" from "the store answered something I could not parse" — the two
 * deserve different sentences, and a caught `unknown` cannot distinguish them.
 */
export class StoreUnreachableError extends Error {
  /** Plain words, safe to render. Never blank. */
  readonly reason: string
  constructor(reason: string) {
    super(reason)
    this.name = 'StoreUnreachableError'
    this.reason = reason
  }
}

/** Plain-words provenance, in the dialect `lib/store-posture.ts` established. */
export function unreachableSource(detail: string): string {
  return `the configured store (REDIS_URL) did not answer — ${detail}. Nothing below is a measurement of your cabinet; it is what this dashboard has, which is nothing.`
}

/** The sentence for a call that ran out of time rather than being refused. */
export function timedOutReason(op: string, ms: number): string {
  return `the store did not answer \`${op}\` within ${ms}ms`
}

/** The sentence for a call the breaker refused without trying. */
export function shortCircuitReason(reason: string): string {
  return `${reason} (not retried — the store failed moments ago and is being left alone for a few seconds)`
}

/** What the breaker currently believes, and why. */
export interface ReachabilityReading {
  /** true = a call succeeded · false = a call failed · null = nothing tried yet. */
  reachable: boolean | null
  /** Why it is not reachable, in plain words. Null unless `reachable === false`. */
  reason: string | null
}

/**
 * The state machine, pure and clock-injected.
 *
 * Three states and no more: never tried · reachable · failed-at-T. It is
 * deliberately NOT a counting breaker (N failures before opening) — the first
 * failure here is already a 3-second timeout the Captain waited through, and
 * making him wait through three of them to earn an honest banner would be the
 * wrong trade. One failure is enough evidence to stop asking for five seconds.
 */
export class StoreBreaker {
  private failedAtMs: number | null = null
  private failReason: string | null = null
  private everSucceeded = false

  constructor(private readonly cooldownMs: number = UNREACHABLE_COOLDOWN_MS) {}

  /** TRUE while the breaker is refusing calls. Closes on its own after cooldown. */
  isOpen(nowMs: number): boolean {
    if (this.failedAtMs === null) return false
    return nowMs - this.failedAtMs < this.cooldownMs
  }

  /**
   * The reason to reject with while open. Never blank.
   *
   * `??` was wrong here: an empty-string reason is falsy but not nullish, so it
   * survived the fallback and produced an unknown with no words in it — the
   * defect `unknownKillswitch` exists to prevent, reintroduced in the module
   * that was meant to carry the reason.
   */
  get reason(): string {
    return this.failReason || 'the store could not be reached'
  }

  /** Record a failure. The next `cooldownMs` of calls are refused without trying. */
  trip(nowMs: number, reason: string): void {
    this.failedAtMs = nowMs
    this.failReason = reason
  }

  /**
   * Record a success — closes the breaker immediately.
   *
   * The half-open probe is implicit: once `isOpen` goes false the next call is
   * attempted for real, and if it works the breaker closes here. No separate
   * half-open state to get wrong.
   */
  succeed(): void {
    this.failedAtMs = null
    this.failReason = null
    this.everSucceeded = true
  }

  /**
   * What to tell a surface.
   *
   * `reachable: null` is "nothing has asked yet" and is NOT the same as
   * reachable — a page that renders before any call must not claim a healthy
   * store any more than it may claim a dead one.
   */
  reading(nowMs: number): ReachabilityReading {
    if (this.isOpen(nowMs)) return { reachable: false, reason: this.reason }
    if (this.everSucceeded) return { reachable: true, reason: null }
    return { reachable: null, reason: null }
  }
}

/**
 * Race a call against the hard deadline.
 *
 * The losing promise is left pending on purpose — an ioredis command that never
 * settles cannot be cancelled, and attaching a rejection handler to it is the
 * only thing needed to keep node quiet. What matters is that the CALLER is
 * released.
 */
export function withDeadline<T>(
  work: Promise<T>,
  ms: number,
  op: string,
  setTimer: typeof setTimeout = setTimeout,
  clearTimer: typeof clearTimeout = clearTimeout
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimer(() => {
      reject(new StoreUnreachableError(timedOutReason(op, ms)))
    }, ms)
    work.then(
      (v) => {
        clearTimer(timer)
        resolve(v)
      },
      (e) => {
        clearTimer(timer)
        reject(e)
      }
    )
  })
}

/** Anything with the command surface this dashboard uses. */
export type StoreCommands = Record<string, (...args: never[]) => Promise<unknown>>

/**
 * Wrap a live client so every command is bounded, breaker-gated, and rejects
 * with `StoreUnreachableError` instead of hanging.
 *
 * Takes the client as an ARGUMENT rather than reaching for the module's own, so
 * the whole failure surface — a client that never settles, one that rejects, one
 * that is perfectly healthy — is drivable from a test without a redis server.
 * The end-to-end proof against a real ioredis is a separate arm; this one exists
 * so the degenerate ends can be reached at all.
 */
export function guardCommands<T extends object>(
  client: T,
  methods: readonly (keyof T & string)[],
  breaker: StoreBreaker,
  opts: {
    deadlineMs?: number
    now?: () => number
    setTimer?: typeof setTimeout
    clearTimer?: typeof clearTimeout
  } = {}
): T {
  const deadlineMs = opts.deadlineMs ?? HARD_DEADLINE_MS
  const now = opts.now ?? Date.now
  const out = Object.create(null) as Record<string, unknown>
  for (const name of methods) {
    const fn = client[name]
    if (typeof fn !== 'function') continue
    out[name] = async (...args: unknown[]) => {
      if (breaker.isOpen(now())) {
        throw new StoreUnreachableError(shortCircuitReason(breaker.reason))
      }
      try {
        const value = await withDeadline(
          (fn as (...a: unknown[]) => Promise<unknown>).apply(client, args),
          deadlineMs,
          name,
          opts.setTimer,
          opts.clearTimer
        )
        breaker.succeed()
        return value
      } catch (err) {
        const reason =
          err instanceof StoreUnreachableError
            ? err.reason
            : `the store rejected \`${name}\` (${
                err instanceof Error ? err.message : 'unknown error'
              })`
        breaker.trip(now(), reason)
        throw new StoreUnreachableError(reason)
      }
    }
  }
  return out as T
}
