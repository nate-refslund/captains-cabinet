/**
 * THE HANG, DRIVEN END TO END — a real ioredis client against a real socket
 * that never answers, through the app's own module.
 *
 * WHY THIS FILE EXISTS AND WHY THE UNIT ARMS ARE NOT ENOUGH. Every other arm in
 * this change drives `guardCommands` with a fake client. That proves the
 * wrapper. It does not prove the OPTIONS, and the options are half the fix: the
 * measured failure was ioredis's own behaviour, not the dashboard's. A wrapper
 * proven against a fake and options proven against nothing is a sensor pointed
 * at a twin of the thing it is supposed to watch — the dominant defect class in
 * this program.
 *
 * MEASURED against pre-change `lib/redis.ts` (ioredis 5.10.1, node 26), one GET
 * on a fresh client with no options:
 *
 *   mute accept — TCP accepted, no reply ever   NEVER SETTLED (>65s pending)
 *   refused     — ECONNREFUSED                  rejected @ 10 546ms
 *   blackhole   — SYN dropped (192.0.2.1)       NEVER SETTLED (>65s pending)
 *   HEALTHY control                             resolved @ 11ms
 *
 * So the first arm below HANGS against pre-change code and fails by vitest
 * timeout, which is what makes it a sensor. (Re-proven by mutation: reverting
 * `LIVE_CLIENT_OPTIONS` off the constructor makes it red again; the log is in
 * the PR.)
 *
 * WHY MUTE-ACCEPT AND REFUSED, AND NOT BLACKHOLE. Both shapes here are created
 * inside this process on the loopback interface, so they behave identically on
 * a laptop and on a CI runner with no outbound network. A blackhole needs a
 * routable address that silently drops SYNs; a sandboxed runner may answer
 * ENETUNREACH instantly instead, which would pass this test for the wrong
 * reason — a green that proves nothing is worse than no arm.
 *
 * NO WALL-CLOCK ASSERTION. The verdict is the ERROR TYPE, not a duration:
 * timing bounds flake on shared runners, and a flaky gate gets bypassed. Against
 * pre-change code the promise never settles at all, so the type assertion never
 * runs and vitest's own timeout is the red. That is the strongest available
 * signal that does not depend on how fast the runner is.
 */
import net from 'node:net'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const saved = {
  REDIS_URL: process.env.REDIS_URL,
  MOCK_DATA: process.env.MOCK_DATA,
  CABINET_DEMO_DATA: process.env.CABINET_DEMO_DATA,
}

/**
 * A server that accepts the TCP connection and then never speaks.
 *
 * Sockets are tracked and destroyed at teardown: `server.close()` waits for
 * every open connection, and ioredis holds its socket open across retries, so
 * closing without destroying hangs the hook rather than the test.
 */
const muteSockets = new Set<net.Socket>()
const muteServer = net.createServer((s) => {
  muteSockets.add(s)
  s.on('close', () => muteSockets.delete(s))
})
let mutePort = 0

/** A port nobody is listening on, obtained by opening one and closing it. */
let refusedPort = 0

beforeEach(async () => {
  vi.resetModules()
  delete process.env.MOCK_DATA
  delete process.env.CABINET_DEMO_DATA
  if (!mutePort) {
    await new Promise<void>((res) => muteServer.listen(0, '127.0.0.1', res))
    mutePort = (muteServer.address() as net.AddressInfo).port
  }
  if (!refusedPort) {
    const probe = net.createServer()
    await new Promise<void>((res) => probe.listen(0, '127.0.0.1', res))
    refusedPort = (probe.address() as net.AddressInfo).port
    await new Promise<void>((res) => probe.close(() => res()))
  }
})

afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k]
    else process.env[k] = v
  }
  vi.resetModules()
})

afterAll(async () => {
  for (const s of muteSockets) s.destroy()
  muteSockets.clear()
  await new Promise<void>((res) => muteServer.close(() => res()))
})

describe('REDIS_URL set but the store never answers', () => {
  it('rejects the command instead of queueing it forever', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { default: redis } = await import('./redis')
    const { StoreUnreachableError } = await import('./store-reachability')
    const err = await redis.get('cabinet:killswitch').catch((e) => e)
    expect(err).toBeInstanceOf(StoreUnreachableError)
    expect(String(err.reason)).toMatch(/did not answer|rejected/)
  }, 30_000)

  it('the emergency stop reads UNKNOWN, and says the store could not be reached', async () => {
    // The highest-stakes consumer, driven through its real reader. A hang here
    // is a header pill that never renders; a `null` would be a MEASURED "the
    // stop is clear" about a fleet nobody contacted.
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { readKillswitch } = await import('./killswitch-state')
    const reading = await readKillswitch()
    expect(reading.engaged).toBeNull()
    expect(reading.unknownReason).toBeTruthy()
    expect(String(reading.unknownReason)).toContain('could not be reached')
  }, 30_000)

  it('the store posture becomes `unreachable` and the banner says so', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { currentStoreReading } = await import('./redis')
    const { storeBannerTitle, storeBannerAttr, isNotLiveStore } = await import(
      './store-posture'
    )
    const reading = await currentStoreReading()
    expect(reading.posture).toBe('unreachable')
    // Not fabricated — nothing was invented; nothing was obtained either.
    expect(reading.fabricated).toBe(false)
    expect(isNotLiveStore(reading)).toBe(true)
    expect(storeBannerAttr(reading)).toBe('unreachable')
    expect(storeBannerTitle(reading)).toContain('UNREACHABLE')
    // The banner must NEVER say the fleet is fine, and must not claim demo data
    // (a wrong sentence in the disclosure slot is the same defect one level
    // down — exactly why NO_STORE_CONFIGURED_REASON was split from DEMO).
    expect(storeBannerTitle(reading)).not.toMatch(/demo/i)
    expect(String(reading.source)).toContain('did not answer')
  }, 30_000)

  it('money reads as unmeasured, with a reason that does NOT claim "no record"', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { getCostHistory } = await import('./redis')
    const history = await getCostHistory(30)
    expect(history).toHaveLength(30)
    for (const day of history) {
      expect(day.total).toBeNull()
      expect(day.officers).toEqual({})
      // "no cost record was written for this date" is a claim about the
      // cabinet. Nobody asked it anything.
      expect(day.unmeasuredReason).toBeTruthy()
      expect(day.unmeasuredReason).not.toContain('no cost record was written')
      expect(day.unmeasuredReason).toContain('never read')
    }
  }, 40_000)

  it('the schedule page degrades to an empty map rather than throwing the page away', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { getScheduleLastRuns } = await import('./redis')
    await expect(getScheduleLastRuns()).resolves.toEqual({})
  }, 30_000)
})

describe('REDIS_URL set but the connection is refused', () => {
  it('rejects fast rather than retrying twenty times', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${refusedPort}`
    const { default: redis } = await import('./redis')
    const { StoreUnreachableError } = await import('./store-reachability')
    const err = await redis.get('cabinet:killswitch').catch((e) => e)
    expect(err).toBeInstanceOf(StoreUnreachableError)
  }, 30_000)

})

describe('the client the app actually constructs', () => {
  /**
   * THE OPTIONS, ASSERTED OFF THE OBJECT — not off the constant, and not through
   * the wrapper.
   *
   * Mutation caught this arm missing. Reverting `new Redis(url,
   * LIVE_CLIENT_OPTIONS)` to `new Redis(url)` — the original defect, verbatim —
   * left every other arm in this file GREEN, because `guardCommands` bounds the
   * call whether or not ioredis is bounded. Two independent controls, one of
   * them invisible: exactly the shape this program keeps finding in its own
   * tests. This reads the constructed client's own option bag.
   */
  it('carries every bound on the live ioredis instance itself', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { liveClientBounds } = await import('./redis')
    const { LIVE_CLIENT_OPTIONS } = await import('./store-reachability')
    expect(liveClientBounds()).toEqual({
      connectTimeout: LIVE_CLIENT_OPTIONS.connectTimeout,
      commandTimeout: LIVE_CLIENT_OPTIONS.commandTimeout,
      maxRetriesPerRequest: LIVE_CLIENT_OPTIONS.maxRetriesPerRequest,
      enableOfflineQueue: LIVE_CLIENT_OPTIONS.enableOfflineQueue,
    })
    // And explicitly NOT the ioredis defaults the defect shipped with.
    expect(liveClientBounds()!.connectTimeout).not.toBe(10_000)
    expect(liveClientBounds()!.maxRetriesPerRequest).not.toBe(20)
    expect(liveClientBounds()!.commandTimeout).toBeTypeOf('number')
  }, 20_000)

  it('a BARE ioredis carrying only these options still bounds a mute socket', async () => {
    // No wrapper anywhere in this arm. If the option set is weakened — drop
    // `commandTimeout`, restore `maxRetriesPerRequest: 20` — this hangs and
    // fails on its own, independently of anything `guardCommands` does.
    const Redis = (await import('ioredis')).default
    const { LIVE_CLIENT_OPTIONS } = await import('./store-reachability')
    const client = new Redis(`redis://127.0.0.1:${mutePort}`, LIVE_CLIENT_OPTIONS)
    client.on('error', () => {})
    try {
      await expect(client.get('cabinet:killswitch')).rejects.toThrow()
    } finally {
      client.disconnect()
    }
  }, 20_000)

  it('THE PAGE BOUND, end to end — a whole render costs ONE timeout, not one per fetcher', async () => {
    /**
     * The five independent store fetchers a costs-page render actually issues.
     * Not a synthetic 31-call loop: an earlier version of this arm asserted one,
     * and mutation showed `getCostHistory` bails at its FIRST call when the
     * roster read fails, so the loop never ran and the arm passed with the
     * breaker neutered. It was measuring nothing.
     *
     * MEASURED against a mute socket, this file's own shape:
     *   with the breaker      3 004ms
     *   breaker neutered     12 009ms
     * The test timeout is the assertion. The DETERMINISTIC proof of the breaker
     * is the call-count arm in `store-reachability.test.ts` ("after the first
     * failure the underlying client is not called again"); this one exists to
     * ground it in the real render, and its margin is stated so a future reader
     * can judge whether a red here is a regression or a slow runner.
     */
    process.env.REDIS_URL = `redis://127.0.0.1:${mutePort}`
    const { getCostHistory, getTokenCostHistory, getScheduleLastRuns, currentStoreReading } =
      await import('./redis')
    const { readKillswitch } = await import('./killswitch-state')
    await currentStoreReading()
    await readKillswitch()
    const history = await getCostHistory(30)
    await getTokenCostHistory(7)
    await getScheduleLastRuns()
    expect(history).toHaveLength(30)
    expect(history.every((d) => d.total === null)).toBe(true)
  }, 9_000)
})

describe('INVERSE — a store that ANSWERS is still measured', () => {
  /**
   * Driven against a tiny hand-rolled RESP server rather than a real redis, so
   * the arm runs everywhere CI does. It answers the handshake and returns a
   * real value — which is all that is needed to prove the bounds do not turn a
   * working store into an unknown one.
   *
   * Without this arm, deleting every reading and returning "unreachable" for
   * everything would pass the whole file above.
   */
  let server: net.Server
  let port = 0
  const sockets = new Set<net.Socket>()

  beforeEach(async () => {
    server = net.createServer((sock) => {
      sockets.add(sock)
      sock.on('close', () => sockets.delete(sock))
      sock.on('error', () => {})
      sock.on('data', (buf) => {
        const text = buf.toString()
        // ioredis opens with INFO (enableReadyCheck) and may send CLIENT/COMMAND
        // probes. Answering every request with a bulk string is enough: the
        // ready check only needs a reply it can parse.
        const requests = text.split('*').length - 1
        for (let i = 0; i < Math.max(1, requests); i++) {
          if (/\bGET\b/i.test(text)) sock.write('$6\r\nactive\r\n')
          else if (/\bPING\b/i.test(text)) sock.write('+PONG\r\n')
          else sock.write('$14\r\nredis_version:\r\n')
        }
      })
    })
    await new Promise<void>((res) => server.listen(0, '127.0.0.1', res))
    port = (server.address() as net.AddressInfo).port
  })

  afterEach(async () => {
    for (const s of sockets) s.destroy()
    sockets.clear()
    await new Promise<void>((res) => server.close(() => res()))
  })

  it('returns the value the store gave, and the posture stays `live`', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${port}`
    const { default: redis, currentStoreReading } = await import('./redis')
    expect(await redis.get('cabinet:killswitch')).toBe('active')
    const reading = await currentStoreReading()
    expect(reading.posture).toBe('live')
    const { storeBannerTitle } = await import('./store-posture')
    expect(storeBannerTitle(reading)).toBeNull() // zero pixels for a live store
  }, 30_000)

  it('the emergency stop reads ENGAGED — a real reading, not an unknown', async () => {
    process.env.REDIS_URL = `redis://127.0.0.1:${port}`
    const { readKillswitch } = await import('./killswitch-state')
    const reading = await readKillswitch()
    expect(reading.engaged).toBe(true)
    expect(reading.unknownReason).toBeNull()
  }, 30_000)
})
