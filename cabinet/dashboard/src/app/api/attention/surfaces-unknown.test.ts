/**
 * THE ATTENTION SURFACES, DRIVEN — not grepped.
 *
 * WHY THIS FILE EXISTS. The 2026-07-30 fix made `readQueue()` return a null
 * count for a reading nobody took, and pinned that in `lib/attention/
 * queue.test.ts`. An adversarial review then reverted, one at a time, every
 * SURFACE the Captain actually saw the lie on — the mailbox route's unknown
 * branch back to `pendingTotal: 0`, the world SSE helper back to `return 0`,
 * the verdict door's refusal back to `=== 'unknown'` — and the whole suite
 * stayed green. The only guards were substring greps, and a grep tests a
 * spelling, not a behaviour. That is the exact defect class the fix is written
 * against, reproduced inside the fix.
 *
 * So these arms CALL THE HANDLERS with a stale, absent or malformed census on
 * disk and assert what comes back. `next/headers` is mocked to hand every
 * request a session cookie; `@/lib/attention/verdict` is mocked so the verdict
 * door's HMAC chain does not need a real password, while its FRESHNESS decision
 * — the thing under test — runs for real.
 *
 * HONEST LIMIT, stated rather than hidden: this package runs vitest with
 * `environment: 'node'` and no DOM renderer, so the two React surfaces
 * (`queue/page.tsx`, `needs-you-badge.tsx`) cannot be rendered here. Their
 * decisions were therefore MOVED into `lib/attention/queue.ts`
 * (`mastheadCount`, `badgeState`) where they are driven directly, and the
 * masthead numeral is a STRING so that a broken branch prints "—" rather than
 * a zero nobody counted. What remains untestable in this suite is JSX layout,
 * not the unknown/clear/count decision.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const COOKIE = 'test-session-value'

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: () => ({ value: COOKIE }) }),
}))

// The write door's auth/CSRF/rate chain is not under test here; its FRESHNESS
// gate is. Everything else is stubbed permissive so a refusal can only come
// from the freshness decision.
vi.mock('@/lib/attention/verdict', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/attention/verdict')>(
      '@/lib/attention/verdict'
    )
  return {
    ...actual,
    doorSecret: () => 'a-real-password',
    verifySessionValue: () => true,
    checkCsrf: () => true,
    rateLimiter: { take: () => ({ ok: true }) },
  }
})

// A live standby view we can switch on, so the DEGRADED source
// (`redis-fallback`) is reachable — the reviewer's finding was that the verdict
// door's refusal was only ever tested on `unknown`, and the degraded path is
// exactly where it used to answer "already decided" for a freshness failure.
const redisState: { cards: Record<string, string> } = { cards: {} }
vi.mock('ioredis', () => ({
  default: class {
    async scan(): Promise<[string, string[]]> {
      return ['0', Object.keys(redisState.cards)]
    }
    async get(k: string): Promise<string | null> {
      return redisState.cards[k] ?? null
    }
    async quit() {}
    disconnect() {}
  },
}))

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'attn-surfaces-'))
const savedDir = process.env.CABINET_ATTENTION_DIR
const savedRedis = process.env.REDIS_URL

function writeCensus(text: string): void {
  fs.writeFileSync(path.join(tmp, 'queue.json'), text)
}
function clearCensus(): void {
  try {
    fs.unlinkSync(path.join(tmp, 'queue.json'))
  } catch {
    /* already absent */
  }
}

/** A census that really counted two things, `ageMs` ago. */
function census(ageMs: number, overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    v: 1,
    generated_at: new Date(Date.now() - ageMs).toISOString(),
    pending_captain_items: 2,
    pending_total: 3,
    decisions: [
      {
        id: 'sit-aaaa',
        kind: 'action-proposal',
        state: 'pending',
        what: 'reply to counsel',
        pid: 'cos|action-card|subj|2026-07-09T12:00:00Z',
        one_tap: { approve: 'direct' },
        refs: [],
      },
    ],
    directions: [],
    ...overrides,
  })
}

const FRESH = 60_000
const NINE_DAYS = 9 * 24 * 3600 * 1000

beforeEach(() => {
  process.env.CABINET_ATTENTION_DIR = tmp
  delete process.env.REDIS_URL // no live standby view → unknown is reachable
  redisState.cards = {}
  clearCensus()
})

/** Turn the degraded live view on, holding one real pending card. */
function liveCard(): void {
  process.env.REDIS_URL = 'redis://127.0.0.1:6399'
  redisState.cards = {
    'cabinet:action:c1': JSON.stringify({
      cid: 'c1',
      subject: 'a live pending card',
      lane: 'bakery',
      urgency: 'batch',
      ts: '2026-07-10T08:00:00Z',
    }),
  }
}
afterEach(() => {
  if (savedDir === undefined) delete process.env.CABINET_ATTENTION_DIR
  else process.env.CABINET_ATTENTION_DIR = savedDir
  if (savedRedis === undefined) delete process.env.REDIS_URL
  else process.env.REDIS_URL = savedRedis
})

const req = () => ({}) as never

describe('GET /api/attention/queue — the machine-readable count', () => {
  it('a fresh census answers with the real number', async () => {
    writeCensus(census(FRESH))
    const { GET } = await import('./queue/route')
    const body = await (await GET(req())).json()
    expect(body.pendingCaptainItems).toBe(2)
    expect(body.source).toBe('census')
    expect(body.unknownReason).toBeNull()
  })

  it('a 9-day-old census answers NULL and says why', async () => {
    writeCensus(census(NINE_DAYS))
    const { GET } = await import('./queue/route')
    const body = await (await GET(req())).json()
    expect(body.pendingCaptainItems).toBeNull()
    expect(body.pendingTotal).toBeNull()
    expect(body.source).toBe('unknown')
    expect(body.unknownReason).toMatch(/stopped updating/)
  })

  it('an absent census answers NULL', async () => {
    const { GET } = await import('./queue/route')
    const body = await (await GET(req())).json()
    expect(body.pendingCaptainItems).toBeNull()
    expect(body.source).toBe('unknown')
  })

  it('a fresh census with NO count answers NULL, not zero', async () => {
    writeCensus(census(FRESH, { pending_captain_items: undefined }))
    const { GET } = await import('./queue/route')
    const body = await (await GET(req())).json()
    expect(body.pendingCaptainItems).toBeNull()
    expect(body.unknownReason).toMatch(/carries no count/)
  })

  it('a non-numeric count answers NULL, not NaN and not zero', async () => {
    writeCensus(census(FRESH, { pending_captain_items: '2' }))
    const { GET } = await import('./queue/route')
    const body = await (await GET(req())).json()
    expect(body.pendingCaptainItems).toBeNull()
  })
})

describe('GET /api/world/mailbox — the flag', () => {
  it('a fresh census gives the mailbox a real total', async () => {
    writeCensus(census(FRESH))
    const { GET } = await import('../world/mailbox/route')
    const body = await (await GET(req())).json()
    expect(body.pendingTotal).toBe(3)
    expect(body.unknownReason).toBeNull()
  })

  it('a stale census leaves the flag UNKNOWN, never down', async () => {
    writeCensus(census(NINE_DAYS))
    const { GET } = await import('../world/mailbox/route')
    const body = await (await GET(req())).json()
    // 0 here is what put "the queue is honestly empty (flag down)" on the card.
    expect(body.pendingTotal).toBeNull()
    expect(body.unknownReason).toBeTruthy()
    expect(body.items).toEqual([])
    expect(body.proof.keyPattern).toMatch(/no current reading/)
  })

  it('an absent census leaves the flag UNKNOWN', async () => {
    const { GET } = await import('../world/mailbox/route')
    const body = await (await GET(req())).json()
    expect(body.pendingTotal).toBeNull()
  })

  it('a malformed census leaves the flag UNKNOWN', async () => {
    writeCensus('{ not json')
    const { GET } = await import('../world/mailbox/route')
    const body = await (await GET(req())).json()
    expect(body.pendingTotal).toBeNull()
  })

  it('the degraded live path counts what it actually read, once', async () => {
    // It used to re-read Redis here — a second chance to fail, whose failure
    // maps to [] and would have emitted a confident 0 (adversarial review).
    liveCard()
    writeCensus(census(NINE_DAYS))
    const { GET } = await import('../world/mailbox/route')
    const body = await (await GET(req())).json()
    expect(body.pendingTotal).toBe(1)
    expect(body.items).toHaveLength(1)
    expect(body.items[0].subject).toBe('a live pending card')
  })
})

describe('POST /api/attention/verdict — the door refuses what it cannot see', () => {
  async function post(body: unknown) {
    const { POST } = await import('./verdict/route')
    const request = {
      text: async () => JSON.stringify(body),
      cookies: { get: () => ({ value: COOKIE }) },
      headers: {
        get: (k: string) =>
          k.toLowerCase() === 'origin'
            ? 'http://localhost:3100'
            : k.toLowerCase() === 'x-cabinet-csrf'
              ? 'csrf'
              : null,
      },
      nextUrl: { origin: 'http://localhost:3100' },
    } as never
    const res = await POST(request)
    return { status: res.status, body: await res.json() }
  }

  const TAP = {
    pid: 'cos|action-card|subj|2026-07-09T12:00:00Z',
    verb: 'approve',
    revision: '0123456789abcdef', // parseBody wants 16 hex chars
  }

  it('refuses on a stale census with the FRESHNESS reason', async () => {
    writeCensus(census(NINE_DAYS))
    const { status, body } = await post(TAP)
    expect(status).toBe(409)
    // Not `gone` ("it may already be decided") — the door could not see the
    // list at all, and a write door must not invent a reason.
    expect(JSON.stringify(body)).toMatch(/out of date/)
  })

  it('refuses on an absent census', async () => {
    const { status } = await post(TAP)
    expect(status).toBe(409)
  })

  it('refuses on the DEGRADED live path with the freshness reason', async () => {
    // The reviewer's finding: `source === 'redis-fallback'` rows carry
    // pid=null, so the old door fell through to findRow and answered `gone` —
    // "This one is no longer waiting — it may already be decided" — for what
    // was actually "I cannot see the list". A write door must not invent a
    // reason, and this is the only arm that reaches that branch.
    liveCard()
    writeCensus(census(NINE_DAYS))
    const { status, body } = await post(TAP)
    expect(status).toBe(409)
    expect(JSON.stringify(body)).toMatch(/out of date/)
    expect(JSON.stringify(body)).not.toMatch(/already been decided|no longer waiting/)
  })

  it('gets PAST freshness on a live census (the arm can pass)', async () => {
    writeCensus(census(FRESH))
    const { status, body } = await post(TAP)
    // Whatever it decides next (token, revision, verb), it is no longer
    // refusing for staleness — otherwise every arm above would be vacuous.
    expect(JSON.stringify(body)).not.toMatch(/out of date/)
    expect(status).toBeGreaterThanOrEqual(400)
  })
})
