/**
 * Verdict-door negative proofs (spec §1.6): no-cookie 401 · forged-cookie
 * 401 · cross-origin 403 · missing/wrong CSRF 403 · stale-pid 409 (+
 * refreshed card) · unknown-pid 409 · replayed token 403 · burst 429 ·
 * 11-in-5min window (lib) · ritual refuse 400 · stale census 409. Plus the
 * arm→fire happy path against a stubbed bridge (the real bridge is pytest's
 * jurisdiction — here we prove the ROUTE only ever speaks through it).
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const SECRET = 'test-door-secret-9'
let tmpDir: string
let route: typeof import('@/app/api/attention/verdict/route')
let lib: typeof import('./verdict')
let NextRequestCtor: typeof import('next/server').NextRequest

const PID = 'prop-abc'
const ROW = {
  id: 'sit-1',
  kind: 'action-proposal',
  state: 'pending',
  pid: PID,
  what: 'Reply to Alice about the DPA redline',
  deadline_iso: '2026-07-12T10:00:00Z',
  age_h: 5,
  blast: { class: 'external', reach: 'external' },
  blast_worst_case: 'a message reaches a human outside the machine',
  refs: ['cmt-4821'],
  one_tap: { approve: 'direct', veto: 'direct', defer: 'direct' },
}
const RITUAL_ROW = {
  ...ROW,
  id: 'sit-2',
  pid: 'gl-hand-1',
  kind: 'germline-handback',
  one_tap: { approve: 'ritual-print', veto: 'direct', defer: 'direct' },
}

function writeCensus(generatedAt = new Date().toISOString()): void {
  fs.writeFileSync(
    path.join(tmpDir, 'queue.json'),
    JSON.stringify({
      v: 1,
      generated_at: generatedAt,
      pending_captain_items: 2,
      pending_total: 2,
      by_class: {},
      overflow: 0,
      cap: 7,
      admission_enforced: false,
      decisions: [ROW, RITUAL_ROW],
      directions: [],
    })
  )
}

function sessionCookie(secret = SECRET): string {
  const token = crypto.randomBytes(16).toString('hex')
  const sig = crypto.createHmac('sha256', secret).update(token).digest('hex')
  return `${token}.${sig}`
}

interface CallOpts {
  cookie?: string | null
  csrf?: string | null
  origin?: string | null
  referer?: string | null
  body?: Record<string, unknown>
}

async function call(opts: CallOpts = {}) {
  const cookie = opts.cookie === undefined ? sessionCookie() : opts.cookie
  const headers = new Headers({ 'content-type': 'application/json' })
  if (cookie) headers.set('cookie', `cabinet_session=${cookie}`)
  const csrf =
    opts.csrf === undefined && cookie ? lib.csrfTokenFor(cookie) : opts.csrf
  if (csrf) headers.set('X-Cabinet-CSRF', csrf)
  if (opts.origin !== undefined && opts.origin !== null) headers.set('origin', opts.origin)
  if (opts.referer) headers.set('referer', opts.referer)
  const req = new NextRequestCtor('http://localhost:3100/api/attention/verdict', {
    method: 'POST',
    headers,
    body: JSON.stringify(
      opts.body ?? { pid: PID, verb: 'approve', revision: freshRevision() }
    ),
  })
  const res = await route.POST(req)
  return { status: res.status, json: (await res.json()) as Record<string, unknown>, cookie }
}

function freshRevision(row: Record<string, unknown> = ROW): string {
  const parts = [row.pid, row.state, row.what, row.deadline_iso].map((v) => v ?? '')
  return crypto.createHash('sha256').update(parts.join('\n'), 'utf8').digest('hex').slice(0, 16)
}

beforeAll(async () => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'verdict-door-'))
  process.env.DASHBOARD_PASSWORD = SECRET
  process.env.CABINET_ATTENTION_DIR = tmpDir
  delete process.env.REDIS_URL
  lib = await import('./verdict')
  route = await import('@/app/api/attention/verdict/route')
  NextRequestCtor = (await import('next/server')).NextRequest
})

afterAll(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true })
})

beforeEach(() => {
  lib._resetForTests()
  writeCensus()
  vi.restoreAllMocks()
  vi.spyOn(lib.door, 'fire').mockResolvedValue({
    ok: true,
    receipt_seq: 7,
    plain_result: 'Approved — done.',
  })
  vi.spyOn(lib.door, 'journal').mockResolvedValue({ ok: true })
})

describe('the chain denies, in order, fail-closed', () => {
  it('401 without a session cookie', async () => {
    const { status } = await call({ cookie: null, csrf: null })
    expect(status).toBe(401)
  })

  it('401 on a forged cookie signature', async () => {
    const forged = sessionCookie('wrong-secret')
    const { status } = await call({ cookie: forged, csrf: lib.csrfTokenFor(forged) })
    expect(status).toBe(401)
  })

  it('401 when no real DASHBOARD_PASSWORD is configured (door stays closed)', async () => {
    const prev = process.env.DASHBOARD_PASSWORD
    process.env.DASHBOARD_PASSWORD = 'changeme'
    try {
      const { status } = await call()
      expect(status).toBe(401)
    } finally {
      process.env.DASHBOARD_PASSWORD = prev
    }
  })

  it('403 on a cross-origin POST', async () => {
    const { status, json } = await call({ origin: 'https://evil.example' })
    expect(status).toBe(403)
    expect(json.code).toBe('csrf')
  })

  it('403 on a cross-origin referer', async () => {
    const { status } = await call({ referer: 'https://evil.example/queue' })
    expect(status).toBe(403)
  })

  it('0.0.0.0-bound server: browser Origin matching the Host header passes the origin leg (live-deploy regression 2026-07-10)', async () => {
    // Under `next start --hostname 0.0.0.0`, req.nextUrl.origin is
    // http://0.0.0.0:<port> — an origin no browser ever sends. The route must
    // compare against the HOST the browser addressed instead.
    const cookie = sessionCookie()
    const headers = new Headers({
      'content-type': 'application/json',
      cookie: `cabinet_session=${cookie}`,
      host: 'localhost:3100',
      origin: 'http://localhost:3100',
      referer: 'http://localhost:3100/queue',
    })
    const csrf = lib.csrfTokenFor(cookie)
    if (csrf) headers.set('X-Cabinet-CSRF', csrf)
    const req = new NextRequestCtor('http://0.0.0.0:3100/api/attention/verdict', {
      method: 'POST',
      headers,
      body: JSON.stringify({ pid: PID, verb: 'approve', revision: freshRevision() }),
    })
    const res = await route.POST(req)
    expect(res.status).toBe(200) // armed — NOT a 403 csrf deny
    const json = (await res.json()) as Record<string, unknown>
    expect(json.armed).toBe(true)
  })

  it('0.0.0.0-bound server: cross-site Origin still 403s (Host-derived origin does not weaken the gate)', async () => {
    const cookie = sessionCookie()
    const headers = new Headers({
      'content-type': 'application/json',
      cookie: `cabinet_session=${cookie}`,
      host: 'localhost:3100',
      origin: 'https://evil.example',
    })
    const csrf = lib.csrfTokenFor(cookie)
    if (csrf) headers.set('X-Cabinet-CSRF', csrf)
    const req = new NextRequestCtor('http://0.0.0.0:3100/api/attention/verdict', {
      method: 'POST',
      headers,
      body: JSON.stringify({ pid: PID, verb: 'approve', revision: freshRevision() }),
    })
    const res = await route.POST(req)
    expect(res.status).toBe(403)
    const json = (await res.json()) as Record<string, unknown>
    expect(json.code).toBe('csrf')
  })

  it('403 without the X-Cabinet-CSRF header, 403 with a wrong one', async () => {
    expect((await call({ csrf: null })).status).toBe(403)
    expect((await call({ csrf: 'a'.repeat(64) })).status).toBe(403)
  })

  it('429 on the 4th verdict inside the 10s burst window (same session)', async () => {
    const cookie = sessionCookie()
    for (let i = 0; i < 3; i++) {
      const r = await call({ cookie })
      expect(r.status).toBe(200)
    }
    const fourth = await call({ cookie })
    expect(fourth.status).toBe(429)
    expect(fourth.json.code).toBe('rate_limited')
  })

  it('409 gone on an unknown pid', async () => {
    const { status, json } = await call({
      body: { pid: 'prop-nope', verb: 'approve', revision: '0'.repeat(16) },
    })
    expect(status).toBe(409)
    expect(json.code).toBe('gone')
  })

  it('409 stale on a revision mismatch, carrying the refreshed card', async () => {
    const { status, json } = await call({
      body: { pid: PID, verb: 'approve', revision: 'f'.repeat(16) },
    })
    expect(status).toBe(409)
    expect(json.code).toBe('stale')
    const refreshed = json.refreshed as Record<string, unknown>
    expect(refreshed.revision).toBe(freshRevision())
    expect(typeof refreshed.headline).toBe('string')
  })

  it('409 when the census artifact is stale (door cannot prove freshness)', async () => {
    writeCensus(new Date(Date.now() - 31 * 60_000).toISOString())
    const { status, json } = await call()
    expect(status).toBe(409)
    expect(json.code).toBe('stale_census')
  })

  it('400 ritual: sign-off kinds never tap-approve through the door', async () => {
    const { status, json } = await call({
      body: { pid: RITUAL_ROW.pid, verb: 'approve', revision: freshRevision(RITUAL_ROW) },
    })
    expect(status).toBe(400)
    expect(json.code).toBe('ritual')
  })

  it('400 on a malformed verb', async () => {
    const { status } = await call({
      body: { pid: PID, verb: 'maybe', revision: freshRevision() },
    })
    expect(status).toBe(400)
  })
})

describe('arm → fire → replay', () => {
  it('two-tap: arm returns consequence+undo+token; fire lands via the bridge; replay 403', async () => {
    const cookie = sessionCookie()
    const revision = freshRevision()

    const arm = await call({ cookie, body: { pid: PID, verb: 'approve', revision } })
    expect(arm.status).toBe(200)
    expect(arm.json.armed).toBe(true)
    expect(typeof arm.json.confirm_token).toBe('string')
    expect(String(arm.json.consequence)).toContain('real person outside')
    expect(String(arm.json.undo).length).toBeGreaterThan(0)
    expect(lib.door.fire).not.toHaveBeenCalled()

    const fire = await call({
      cookie,
      body: { pid: PID, verb: 'approve', revision, confirm_token: arm.json.confirm_token },
    })
    expect(fire.status).toBe(200)
    expect(fire.json.ok).toBe(true)
    expect(fire.json.plain_result).toBe('Approved — done.')
    expect(lib.door.fire).toHaveBeenCalledWith({ pid: PID, verb: 'approve', revision })

    const replay = await call({
      cookie,
      body: { pid: PID, verb: 'approve', revision, confirm_token: arm.json.confirm_token },
    })
    expect(replay.status).toBe(403)
    expect(replay.json.code).toBe('replay')
  })

  it("a token minted for one verb can't fire another", async () => {
    const cookie = sessionCookie()
    const revision = freshRevision()
    const arm = await call({ cookie, body: { pid: PID, verb: 'later', revision } })
    expect(arm.status).toBe(200)
    const cross = await call({
      cookie,
      body: { pid: PID, verb: 'approve', revision, confirm_token: arm.json.confirm_token },
    })
    expect(cross.status).toBe(403)
    expect(lib.door.fire).not.toHaveBeenCalled()
  })

  it('bridge refusal is surfaced honestly (409, never fake success)', async () => {
    vi.spyOn(lib.door, 'fire').mockResolvedValue({
      ok: false,
      code: 'not_here',
      message: 'no',
    })
    const cookie = sessionCookie()
    const revision = freshRevision()
    const arm = await call({ cookie, body: { pid: PID, verb: 'approve', revision } })
    const fire = await call({
      cookie,
      body: { pid: PID, verb: 'approve', revision, confirm_token: arm.json.confirm_token },
    })
    expect(fire.status).toBe(409)
    expect(fire.json.ok).toBe(false)
  })
})

describe('lib windows (injected clocks)', () => {
  it('rate window: the 11th verdict in 5 minutes is denied even unpaced', () => {
    const rl = new lib.RateLimiter()
    const t0 = 1_000_000
    for (let i = 0; i < 10; i++) {
      expect(rl.take('k', t0 + i * 20_000).ok).toBe(true) // paced past burst
    }
    expect(rl.take('k', t0 + 10 * 20_000).ok).toBe(false)
  })

  it('confirm tokens expire after ~90s', () => {
    const fields = { pid: PID, verb: 'approve', revision: '0'.repeat(16), session: 's1' }
    const token = lib.mintConfirmToken(SECRET, fields, 1_000_000)
    const ok = lib.verifyConfirmToken(SECRET, token, fields, 1_000_000 + 89_000)
    expect(ok.ok).toBe(true)
    const late = lib.verifyConfirmToken(SECRET, token, fields, 1_000_000 + 91_000)
    expect(late).toEqual({ ok: false, code: 'expired_token' })
  })

  it('same-origin check: absent headers pass (custom header still required); mismatches fail', () => {
    expect(lib.checkSameOrigin('http://localhost:3100', null, null)).toBe(true)
    expect(lib.checkSameOrigin('http://localhost:3100', 'http://localhost:3100', null)).toBe(true)
    expect(lib.checkSameOrigin('http://localhost:3100', 'https://evil.example', null)).toBe(false)
    expect(lib.checkSameOrigin('http://localhost:3100', null, 'not a url')).toBe(false)
  })
})
