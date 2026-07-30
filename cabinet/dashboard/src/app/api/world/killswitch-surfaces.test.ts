/**
 * THE EMERGENCY-STOP SURFACES, DRIVEN — not grepped.
 *
 * WHY THIS FILE EXISTS. The census fix (PR #328) was defeated on every surface
 * in its first adversarial round: `lib/attention/queue.ts` was correct and
 * pinned, but each CONSUMER — the mailbox route, the world SSE helper, the
 * verdict door — could be reverted to its old zero one at a time with 2900
 * tests still green, because the only guards were substring greps and a grep
 * tests a spelling. `lib/world/killswitch.test.ts` is the queue.ts of this fix;
 * this file is what stops the same defeat.
 *
 * So these arms CALL THE HANDLERS — `GET /api/world/stream` and
 * `GET /api/world/engine` — with no store, a dead store, and a store holding an
 * absent / malformed / stale / future-dated / field-less presence snapshot, and
 * assert what comes out on the wire. Reverting any producer line to `false`
 * turns them red.
 *
 * HONEST LIMIT, stated rather than hidden: vitest runs here with
 * `environment: 'node'` and no DOM renderer, so the React surfaces
 * (`killswitch-lever.tsx`, `kill-switch-header.tsx`, the home-page banner)
 * cannot be mounted. Their decisions were therefore MOVED into
 * `lib/world/killswitch.ts` — `killswitchWord`, `killswitchAttr`, `intentFor` —
 * where they are driven directly and where the printed word can never carry
 * "UP" for a reading nobody took. What remains untested here is JSX layout, not
 * the engaged/clear/unknown decision. The pixels are covered by the
 * before/after browser capture in the PR, taken against a running app.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const COOKIE = 'test-session-value'

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: () => ({ value: COOKIE }) }),
}))

/**
 * A switchable stand-in for the store. `mode` drives what the world's own
 * ioredis client does, so the routes exercise their real failure paths rather
 * than a hand-built fixture of them.
 */
const store: {
  mode: 'ok' | 'throw-on-get' | 'throw-on-construct'
  values: Record<string, string | null>
} = { mode: 'ok', values: {} }

vi.mock('ioredis', () => ({
  default: class {
    constructor() {
      if (store.mode === 'throw-on-construct') {
        throw new Error('connection refused')
      }
    }
    async get(k: string): Promise<string | null> {
      if (store.mode === 'throw-on-get') throw new Error('ECONNREFUSED')
      return store.values[k] ?? null
    }
    async xrevrange(): Promise<Array<[string, string[]]>> {
      if (store.mode === 'throw-on-get') throw new Error('ECONNREFUSED')
      return []
    }
    async xlen(): Promise<number> {
      return 0
    }
    async quit() {}
    disconnect() {}
  },
}))

const savedRedisUrl = process.env.REDIS_URL

beforeEach(() => {
  store.mode = 'ok'
  store.values = {}
  process.env.REDIS_URL = 'redis://127.0.0.1:6379'
})

afterEach(() => {
  if (savedRedisUrl === undefined) delete process.env.REDIS_URL
  else process.env.REDIS_URL = savedRedisUrl
  vi.resetModules()
})

/** Read the FIRST `world:snapshot` frame the SSE route emits. */
async function firstSnapshot(): Promise<Record<string, unknown>> {
  const { GET } = await import('./stream/route')
  const req = { signal: undefined } as unknown as Parameters<typeof GET>[0]
  const res = await GET(req)
  const body = res.body as ReadableStream<Uint8Array> | null
  if (!body) throw new Error('no stream body')
  const reader = body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  // Bounded: the snapshot is emitted synchronously on connect, so a handful of
  // chunks is always enough. No watcher, no timer.
  for (let i = 0; i < 20; i++) {
    const { value, done } = await reader.read()
    if (value) buf += dec.decode(value, { stream: true })
    const line = buf.split('\n').find((l) => l.startsWith('data: '))
    if (line) {
      await reader.cancel()
      return JSON.parse(line.slice(6)) as Record<string, unknown>
    }
    if (done) break
  }
  throw new Error('no snapshot frame')
}

function presence(extra: Record<string, unknown>): string {
  return JSON.stringify({
    v: 1,
    ts: new Date().toISOString(),
    iid_high: 3,
    officers: {},
    ...extra,
  })
}

describe('GET /api/world/stream — the emergency stop on the wire', () => {
  it('a VERIFIED-CLEAR switch still reports false (the fix does not blind the world)', async () => {
    store.values['cabinet:world:presence'] = presence({
      killswitch: false,
      killswitch_verdict: 'CLEAR',
    })
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBe(false)
    expect(snap.killswitchUnknownReason).toBeNull()
  })

  it('an ARMED switch still reports true', async () => {
    store.values['cabinet:world:presence'] = presence({
      killswitch: true,
      killswitch_verdict: 'ACTIVE',
    })
    expect((await firstSnapshot()).killswitch).toBe(true)
  })

  // The defect, on the surface the Captain sees it on.
  it('NO STORE CONFIGURED → null + a reason (was: killswitch:false, lever UP)', async () => {
    delete process.env.REDIS_URL
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(String(snap.killswitchUnknownReason)).toMatch(/could not reach the store/)
  })

  it('the store REFUSES the connection → null, not false', async () => {
    store.mode = 'throw-on-construct'
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(snap.killswitchUnknownReason).toBeTruthy()
  })

  it('the read THROWS mid-flight → null, not false', async () => {
    store.mode = 'throw-on-get'
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(snap.killswitchUnknownReason).toBeTruthy()
  })

  it('the presence key is ABSENT (daemon dead, store fine) → null, not false', async () => {
    // The store answers cleanly; there is simply no snapshot. This used to be
    // indistinguishable from a chronicled, verified-clear fleet.
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(String(snap.killswitchUnknownReason)).toMatch(/presence snapshot/)
  })

  it('a MALFORMED presence blob → null, not false', async () => {
    store.values['cabinet:world:presence'] = '{not json'
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
  })

  it('a STALE presence snapshot → null, even when its verdict says CLEAR', async () => {
    store.values['cabinet:world:presence'] = JSON.stringify({
      v: 1,
      ts: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
      iid_high: 3,
      officers: {},
      killswitch_verdict: 'CLEAR',
    })
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(String(snap.killswitchUnknownReason)).toMatch(/stopped updating/)
  })

  it('a FUTURE-DATED presence snapshot → null (clock skew, age unknowable)', async () => {
    store.values['cabinet:world:presence'] = JSON.stringify({
      v: 1,
      ts: new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString(),
      iid_high: 3,
      officers: {},
      killswitch_verdict: 'CLEAR',
    })
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(String(snap.killswitchUnknownReason)).toMatch(/future/)
  })

  it('a fresh snapshot with NO emergency-stop field → null, not false', async () => {
    store.values['cabinet:world:presence'] = presence({})
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
    expect(String(snap.killswitchUnknownReason)).toMatch(/no emergency-stop reading/)
  })

  it('INDETERMINATE from the one reader → null, not the daemon’s folded true', async () => {
    store.values['cabinet:world:presence'] = presence({
      killswitch: true, // what the daemon writes for verdict != CLEAR
      killswitch_verdict: 'INDETERMINATE',
    })
    const snap = await firstSnapshot()
    expect(snap.killswitch).toBeNull()
  })

  it('the officer roster survives a presence read the stop could not use', async () => {
    // Regression guard on the refactor itself: parsing the blob once for both
    // the roster and the stop must not have dropped the roster.
    store.values['cabinet:world:presence'] = presence({
      killswitch_verdict: 'CLEAR',
      officers: { cos: { present: true, verb: 'reviewing' } },
    })
    const snap = await firstSnapshot()
    expect((snap.officers as unknown[]).length).toBe(1)
    expect(snap.iidHigh).toBe(3)
  })
})

describe('GET /api/world/engine — the weather signal', () => {
  async function weather(): Promise<Record<string, unknown>> {
    const { GET } = await import('./engine/route')
    const req = {} as unknown as Parameters<typeof GET>[0]
    const res = await GET(req)
    const json = (await res.json()) as { weather: Record<string, unknown> }
    return json.weather
  }

  it('a proven-absent key is a measured "not engaged"', async () => {
    expect((await weather()).killswitch).toBe(false)
  })

  it('an armed key reads true', async () => {
    store.values['cabinet:killswitch'] = 'active'
    expect((await weather()).killswitch).toBe(true)
  })

  it('the store is unreachable → null (was: `let killswitch = false` survived the catch)', async () => {
    store.mode = 'throw-on-construct'
    const w = await weather()
    expect(w.killswitch).toBeNull()
    expect(w.killswitchUnknownReason).toBeTruthy()
  })

  it('an unrecognised value → null, not the old `Boolean(value)` storm', async () => {
    // `Boolean('NOAUTH Authentication required.')` was TRUE here while
    // `=== 'active'` in layout.tsx was FALSE for the same reply: the sky
    // stormed while the header pill said the fleet was running.
    store.values['cabinet:killswitch'] = 'NOAUTH Authentication required.'
    expect((await weather()).killswitch).toBeNull()
  })

  it('every other live signal still degrades to null beside it', async () => {
    store.mode = 'throw-on-construct'
    const w = await weather()
    expect(w.doctorAgeSecs).toBeNull()
    expect(w.doctorGreen).toBeNull()
    expect(w.probesOk).toBeNull()
  })
})

describe('the sky over an unread stop', () => {
  it('fog, with the emergency stop named — never SUN on a green doctor', async () => {
    const { weatherTarget } = await import('@/lib/world/weather')
    const t = weatherTarget({
      killswitch: null,
      killswitchUnknownReason: 'redis unreachable',
      doctorAgeSecs: 10,
      doctorGreen: true,
      probesOk: true,
    })
    // Pre-change this returned `sun` — "the measured good day" — because
    // `if (s.killswitch)` treated null as "not engaged" and fell through to a
    // doctor that was perfectly healthy.
    expect(t.kind).toBe('fog')
    expect(t.why).toMatch(/emergency stop could not be read/)
    expect(t.why).toMatch(/redis unreachable/)
  })

  it('storm still requires a MEASURED engaged stop', async () => {
    const { weatherTarget } = await import('@/lib/world/weather')
    const base = { doctorAgeSecs: 10, doctorGreen: true, probesOk: true }
    expect(weatherTarget({ ...base, killswitch: true }).kind).toBe('storm')
    expect(weatherTarget({ ...base, killswitch: false }).kind).toBe('sun')
    expect(weatherTarget({ ...base, killswitch: null }).kind).not.toBe('storm')
  })
})
