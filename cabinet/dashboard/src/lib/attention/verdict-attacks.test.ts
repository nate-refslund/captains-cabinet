/**
 * Verdict-door HOSTILE attack proofs (auth/second-door review, 2026-07-10).
 *
 * The existing verdict.test.ts proves the fail-closed chain SEQUENTIALLY
 * (arm → fire → replay-403, and a cross-VERB token is refused). These two
 * add the concurrency + cross-SESSION cases a hostile caller would actually
 * try against the equal-authority door:
 *
 *   1. Race double-approve — the SAME single-use confirm token fired TWICE
 *      CONCURRENTLY must resolve to exactly one success + one replay-403, and
 *      the org wire (door.fire) must be invoked EXACTLY ONCE. Proves the
 *      verifyConfirmToken→spendNonce critical section is atomic in-process
 *      (no await splits the memSpent check-and-set), so two taps cannot both
 *      reach the wire before the nonce is burned.
 *
 *   2. Cross-session token theft — a confirm token armed under session A must
 *      NOT fire under a DIFFERENT valid session B (a leaked/stolen armed
 *      token cannot be replayed by a second dashboard login). Proves the
 *      token is bound to sessionHash(cookie), not just to pid/verb/revision.
 *      Control: the same token still fires under its own session A.
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
  what: 'Reply to Sofie about the DPA redline',
  deadline_iso: '2026-07-12T10:00:00Z',
  age_h: 5,
  blast: { class: 'external', reach: 'external' },
  blast_worst_case: 'a message reaches a human outside the machine',
  refs: ['cmt-4821'],
  one_tap: { approve: 'direct', veto: 'direct', defer: 'direct' },
}

function writeCensus(generatedAt = new Date().toISOString()): void {
  fs.writeFileSync(
    path.join(tmpDir, 'queue.json'),
    JSON.stringify({
      v: 1,
      generated_at: generatedAt,
      pending_captain_items: 1,
      pending_total: 1,
      by_class: {},
      overflow: 0,
      cap: 7,
      admission_enforced: false,
      decisions: [ROW],
      directions: [],
    })
  )
}

function sessionCookie(secret = SECRET): string {
  const token = crypto.randomBytes(16).toString('hex')
  const sig = crypto.createHmac('sha256', secret).update(token).digest('hex')
  return `${token}.${sig}`
}

function freshRevision(): string {
  const parts = [ROW.pid, ROW.state, ROW.what, ROW.deadline_iso].map((v) => v ?? '')
  return crypto.createHash('sha256').update(parts.join('\n'), 'utf8').digest('hex').slice(0, 16)
}

interface CallOpts {
  cookie?: string | null
  csrf?: string | null
  body?: Record<string, unknown>
}

async function call(opts: CallOpts = {}) {
  const cookie = opts.cookie === undefined ? sessionCookie() : opts.cookie
  const headers = new Headers({ 'content-type': 'application/json' })
  if (cookie) headers.set('cookie', `cabinet_session=${cookie}`)
  const csrf = opts.csrf === undefined && cookie ? lib.csrfTokenFor(cookie) : opts.csrf
  if (csrf) headers.set('X-Cabinet-CSRF', csrf)
  const req = new NextRequestCtor('http://localhost:3100/api/attention/verdict', {
    method: 'POST',
    headers,
    body: JSON.stringify(opts.body ?? { pid: PID, verb: 'approve', revision: freshRevision() }),
  })
  const res = await route.POST(req)
  return { status: res.status, json: (await res.json()) as Record<string, unknown> }
}

beforeAll(async () => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'verdict-attacks-'))
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

describe('race double-approve: one token, two concurrent fires', () => {
  it('resolves to exactly one 200 + one 403 replay, and hits the wire ONCE', async () => {
    const cookie = sessionCookie()
    const revision = freshRevision()

    const arm = await call({ cookie, body: { pid: PID, verb: 'approve', revision } })
    expect(arm.status).toBe(200)
    const token = arm.json.confirm_token as string
    expect(typeof token).toBe('string')
    expect(lib.door.fire).not.toHaveBeenCalled()

    const fireBody = { pid: PID, verb: 'approve', revision, confirm_token: token }
    // Fire the SAME token twice at once — the classic double-submit race.
    const [a, b] = await Promise.all([
      call({ cookie, body: fireBody }),
      call({ cookie, body: fireBody }),
    ])
    const statuses = [a.status, b.status]

    // Exactly one wins; the other loses the nonce race with a replay-403.
    expect(statuses.filter((s) => s === 200)).toHaveLength(1)
    expect(statuses.filter((s) => s === 403)).toHaveLength(1)
    const loser = a.status === 403 ? a : b
    expect(loser.json.code).toBe('replay')

    // The load-bearing assertion: the org's wire ran for ONE decision only.
    expect(lib.door.fire).toHaveBeenCalledTimes(1)
    expect(lib.door.fire).toHaveBeenCalledWith({ pid: PID, verb: 'approve', revision })
  })
})

describe('cross-session token theft: armed under A, fired under B', () => {
  it("session B cannot fire session A's confirm token (bound to the session), 403 + wire untouched", async () => {
    const cookieA = sessionCookie()
    const cookieB = sessionCookie() // a DIFFERENT, equally-valid signed session
    expect(cookieA).not.toBe(cookieB)
    const revision = freshRevision()

    const arm = await call({ cookie: cookieA, body: { pid: PID, verb: 'approve', revision } })
    expect(arm.status).toBe(200)
    const token = arm.json.confirm_token as string

    // B is fully authenticated (valid cookie, its own CSRF) but presents A's token.
    const stolen = await call({
      cookie: cookieB,
      body: { pid: PID, verb: 'approve', revision, confirm_token: token },
    })
    expect(stolen.status).toBe(403)
    expect(lib.door.fire).not.toHaveBeenCalled()

    // Control: the very same token DOES fire under its own session A — proving
    // it was rejected for B solely because of session binding, not staleness.
    const own = await call({
      cookie: cookieA,
      body: { pid: PID, verb: 'approve', revision, confirm_token: token },
    })
    expect(own.status).toBe(200)
    expect(own.json.ok).toBe(true)
    expect(lib.door.fire).toHaveBeenCalledTimes(1)
  })
})
