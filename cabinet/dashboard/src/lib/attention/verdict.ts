/**
 * Verdict-door server library (Ruling A: WRITE-CLASS-2 = YES with the
 * EQUAL-AUTHORITY-DOOR LAW, captain-decisions 2026-07-10).
 *
 * The dashboard's ONE write path. Server-side only. The chain the route
 * runs is ordered and fail-closed (spec §1.2 a–f):
 *   a. session   — HMAC-signed cabinet_session cookie, verified HERE (not
 *                  just presence). The door REFUSES to operate without a
 *                  real DASHBOARD_PASSWORD (no 'changeme' fallback ever).
 *   b. CSRF      — strict same-origin Origin/Referer check + X-Cabinet-CSRF
 *                  double-submit header derived from the session cookie
 *                  (custom header ⇒ preflight; no CORS is ever served).
 *   c. rate      — per-session token bucket: burst 3/10s, 10/5min.
 *   d. freshness — live census re-read; content revision must match.
 *   e. verb      — allowlist per card one_tap semantics.
 *   f. token     — tap-2 only: single-use HMAC confirm token, ~90s TTL,
 *                  spent-nonce journal blocks replay.
 *
 * Execution is NEVER local: fire spawns `python3.12 -m
 * framework.attention.verdicts` (fixed argv, shell:false, curated env, 30s
 * wall clock, JSON over stdio) which re-validates freshness and submits the
 * org's own reply grammar through the SAME binder wire the Captain's typed
 * Telegram replies use. The door forges nothing.
 *
 * Every denial is journaled to the attention feed via the same bridge
 * (batched, fire-and-forget — a denial burst must not block responses).
 */
import { execFile } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { cabinetRoot } from '@/lib/cabinet-root'
import { MESSAGES } from './plain'

export const COOKIE_NAME = 'cabinet_session'
export const CSRF_HEADER = 'x-cabinet-csrf'
export const CONFIRM_TTL_S = 90
export const BODY_CAP_BYTES = 4096

// --- secret ---------------------------------------------------------------

/** The door's HMAC secret. null ⇒ the door stays CLOSED (fail-closed: a
 * write door never runs on the dev 'changeme' fallback). */
export function doorSecret(): string | null {
  const s = process.env.DASHBOARD_PASSWORD
  return s && s !== 'changeme' ? s : null
}

function hmacHex(secret: string, value: string): string {
  return crypto.createHmac('sha256', secret).update(value).digest('hex')
}

function safeEqualHex(a: string, b: string): boolean {
  const ba = Buffer.from(a, 'utf8')
  const bb = Buffer.from(b, 'utf8')
  if (ba.length !== bb.length) return false
  return crypto.timingSafeEqual(ba, bb)
}

// --- a. session -----------------------------------------------------------

/** Verify the signed session cookie VALUE (same scheme as lib/auth.ts). */
export function verifySessionValue(cookieValue: string | undefined): boolean {
  const secret = doorSecret()
  if (!secret || !cookieValue) return false
  const [token, sig] = cookieValue.split('.')
  if (!token || !sig) return false
  return safeEqualHex(hmacHex(secret, token), sig)
}

/** Stable per-session key for rate limiting + token binding. */
export function sessionHash(cookieValue: string): string {
  return crypto.createHash('sha256').update(cookieValue, 'utf8').digest('hex').slice(0, 24)
}

// --- b. CSRF ----------------------------------------------------------------

/** The double-submit CSRF token for a session — derived server-side, handed
 * to the page as a prop, echoed back in the X-Cabinet-CSRF header. */
export function csrfTokenFor(cookieValue: string): string | null {
  const secret = doorSecret()
  if (!secret) return null
  return hmacHex(secret, `csrf|${cookieValue}`)
}

export function checkCsrf(
  cookieValue: string,
  headerValue: string | null | undefined
): boolean {
  const expected = csrfTokenFor(cookieValue)
  if (!expected || !headerValue) return false
  return safeEqualHex(expected, headerValue)
}

/** Origin/Referer, WHEN PRESENT, must match the request origin exactly
 * ('null' — sandboxed/opaque contexts — is never our own page). */
export function checkSameOrigin(
  requestOrigin: string,
  origin: string | null,
  referer: string | null
): boolean {
  if (origin && origin !== requestOrigin) return false
  if (referer) {
    try {
      if (new URL(referer).origin !== requestOrigin) return false
    } catch {
      return false
    }
  }
  return true
}

// --- c. rate limit ----------------------------------------------------------

export interface RateVerdict {
  ok: boolean
  retryAfterS: number
}

/** Sliding-window pair: burst 3/10s + 10/5min per key. Pure; clock injected. */
export class RateLimiter {
  private hits = new Map<string, number[]>()
  constructor(
    private burstN = 3,
    private burstWindowMs = 10_000,
    private windowN = 10,
    private windowMs = 300_000
  ) {}

  take(key: string, nowMs = Date.now()): RateVerdict {
    const floor = nowMs - this.windowMs
    const kept = (this.hits.get(key) ?? []).filter((t) => t > floor)
    const burstFloor = nowMs - this.burstWindowMs
    const inBurst = kept.filter((t) => t > burstFloor)
    if (inBurst.length >= this.burstN) {
      const retry = Math.ceil((inBurst[0] + this.burstWindowMs - nowMs) / 1000)
      this.hits.set(key, kept)
      return { ok: false, retryAfterS: Math.max(1, retry) }
    }
    if (kept.length >= this.windowN) {
      const retry = Math.ceil((kept[0] + this.windowMs - nowMs) / 1000)
      this.hits.set(key, kept)
      return { ok: false, retryAfterS: Math.max(1, retry) }
    }
    kept.push(nowMs)
    this.hits.set(key, kept)
    return { ok: true, retryAfterS: 0 }
  }

  reset(): void {
    this.hits.clear()
  }
}

// Survives Next dev hot-reload; per-process (single-captain surface).
const g = globalThis as unknown as { __cabinetVerdictRate?: RateLimiter }
export const rateLimiter: RateLimiter = (g.__cabinetVerdictRate ??=
  new RateLimiter())

// --- d. census / attention dir ----------------------------------------------

export function attentionDir(): string {
  return (
    process.env.CABINET_ATTENTION_DIR ||
    path.join(os.homedir(), 'Library', 'Application Support', 'cabinet', 'attention')
  )
}

// --- f. confirm token (single-use, HMAC, TTL) --------------------------------

interface TokenPayload {
  pid: string
  verb: string
  revision: string
  session: string
  exp: number
  nonce: string
}

function b64url(buf: Buffer): string {
  return buf.toString('base64url')
}

export function mintConfirmToken(
  secret: string,
  fields: { pid: string; verb: string; revision: string; session: string },
  nowMs = Date.now()
): string {
  const payload: TokenPayload = {
    ...fields,
    exp: Math.floor(nowMs / 1000) + CONFIRM_TTL_S,
    nonce: crypto.randomBytes(16).toString('hex'),
  }
  const body = b64url(Buffer.from(JSON.stringify(payload), 'utf8'))
  return `${body}.${hmacHex(secret, `confirm|${body}`)}`
}

export type TokenCheck =
  | { ok: true; nonce: string }
  | { ok: false; code: 'replay' | 'expired_token' | 'csrf' }

/** Verify WITHOUT spending (spend happens only after the whole chain holds). */
export function verifyConfirmToken(
  secret: string,
  token: string,
  expect: { pid: string; verb: string; revision: string; session: string },
  nowMs = Date.now()
): TokenCheck {
  const [body, sig] = token.split('.')
  if (!body || !sig || !safeEqualHex(hmacHex(secret, `confirm|${body}`), sig)) {
    return { ok: false, code: 'csrf' }
  }
  let payload: TokenPayload
  try {
    payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'))
  } catch {
    return { ok: false, code: 'csrf' }
  }
  if (
    payload.pid !== expect.pid ||
    payload.verb !== expect.verb ||
    payload.revision !== expect.revision ||
    payload.session !== expect.session
  ) {
    return { ok: false, code: 'csrf' }
  }
  if (typeof payload.exp !== 'number' || payload.exp * 1000 < nowMs) {
    return { ok: false, code: 'expired_token' }
  }
  if (typeof payload.nonce !== 'string' || payload.nonce.length < 16) {
    return { ok: false, code: 'csrf' }
  }
  if (isNonceSpent(payload.nonce)) return { ok: false, code: 'replay' }
  return { ok: true, nonce: payload.nonce }
}

// Spent-nonce journal — file-backed so replay stays blocked across dev
// reloads; synchronous read-modify-write (single-process door). A missing
// dir falls back to an in-memory set (still single-use per process).
const memSpent = new Map<string, number>()

function noncePath(): string {
  return path.join(attentionDir(), 'verdict-nonces.json')
}

function readSpent(): Record<string, number> {
  try {
    const doc = JSON.parse(fs.readFileSync(noncePath(), 'utf8'))
    return typeof doc === 'object' && doc !== null ? doc : {}
  } catch {
    return {}
  }
}

export function isNonceSpent(nonce: string): boolean {
  if (memSpent.has(nonce)) return true
  return Object.prototype.hasOwnProperty.call(readSpent(), nonce)
}

/** Mark spent. Returns false when the nonce was ALREADY spent (race lost). */
export function spendNonce(nonce: string, nowMs = Date.now()): boolean {
  if (memSpent.has(nonce)) return false
  memSpent.set(nonce, nowMs)
  const floor = Math.floor(nowMs / 1000) - CONFIRM_TTL_S * 2
  const doc = readSpent()
  if (Object.prototype.hasOwnProperty.call(doc, nonce)) return false
  const pruned: Record<string, number> = { [nonce]: Math.floor(nowMs / 1000) }
  for (const [k, v] of Object.entries(doc)) {
    if (typeof v === 'number' && v > floor) pruned[k] = v
  }
  try {
    fs.mkdirSync(attentionDir(), { recursive: true })
    fs.writeFileSync(noncePath(), JSON.stringify(pruned))
  } catch {
    /* fs journal unavailable — memSpent still blocks in-process replay */
  }
  return true
}

// --- the bridge (equal authority: the org's own gate does the deciding) -----

/** Curated child env: PATH/HOME/locale + CABINET_* only. No secrets
 * (NODE_ENV rides along solely to satisfy the ProcessEnv type — the
 * bridge is Python and never reads it). */
export function curatedEnv(): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {
    NODE_ENV: process.env.NODE_ENV ?? 'production',
  }
  for (const k of ['PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR']) {
    const v = process.env[k]
    if (v) out[k] = v
  }
  for (const [k, v] of Object.entries(process.env)) {
    if (k.startsWith('CABINET_') && k !== 'CABINET_DASHBOARD_SECRET' && v) {
      out[k] = v
    }
  }
  return out
}

export interface BridgeResult {
  ok: boolean
  code?: string
  message?: string
  plain_result?: string
  receipt_seq?: number | null
  deferred?: boolean
  wire_status?: string
  journal_warn?: string
  refreshed?: { pid: string; state: string; revision: string; summary: string }
}

export function spawnBridge(request: object): Promise<BridgeResult> {
  return new Promise((resolve) => {
    const child = execFile(
      'python3.12',
      ['-m', 'framework.attention.verdicts'],
      {
        cwd: cabinetRoot(),
        env: curatedEnv(),
        timeout: 30_000,
        maxBuffer: 1024 * 1024,
        windowsHide: true,
      },
      (err, stdout) => {
        // THE EXIT CODE IS PART OF THE ANSWER. `if (err && !stdout)` was the
        // whole failure branch, so a bridge that printed a well-formed
        // `{"ok": true, "plain_result": "Approved — done."}` and THEN died —
        // having submitted nothing through the binder wire — resolved as a
        // success, and the route handed the Captain a completed act.
        // Reproduced with a shim that does exactly that; the two sibling
        // transports already read it (`lib/onboarding/bridge.ts` rejects
        // `core_exit` on any non-zero, `lib/evidence/read.ts` refuses any exit
        // outside {0,3,4}), so this is the house standard rather than a new one.
        if (err) {
          resolve({ ok: false, code: 'bridge_fail', message: MESSAGES.bridge_fail })
          return
        }
        try {
          const parsed: unknown = JSON.parse(String(stdout).trim().split('\n').pop() ?? '')
          if (typeof parsed === 'object' && parsed !== null) {
            resolve(parsed as BridgeResult)
            return
          }
        } catch {
          /* fall through */
        }
        resolve({ ok: false, code: 'bridge_fail', message: MESSAGES.bridge_fail })
      }
    )
    // A BRIDGE THAT DIED BEFORE WE FINISHED ASKING MUST NOT TAKE THE PROCESS
    // WITH IT. Writing to the stdin of an exited child raises EPIPE on the
    // stream, and an unhandled stream error is fatal to the Node process — so
    // the same crash this function now REPORTS could, one line later, kill the
    // dashboard instead. Found by the arm above on the CI runner, where the
    // child exits fast enough to lose the race; on the slower path it never
    // fired, which is what a platform-dependent unhandled rejection looks like.
    // The `err` callback resolves this promise either way, so swallowing here
    // loses nothing: the failure is already on its way to the caller.
    child.stdin?.on('error', () => {})
    try {
      child.stdin?.end(JSON.stringify(request))
    } catch {
      /* the child is already gone; the execFile callback reports it */
    }
  })
}

/** Test seam: the route calls door.fire/door.journal so vitest can stub the
 * python spawn without a live framework checkout. */
export const door = {
  fire(payload: { pid: string; verb: string; revision: string }): Promise<BridgeResult> {
    return spawnBridge({ op: 'fire', ...payload })
  },
  journal(rows: object[]): Promise<BridgeResult> {
    return spawnBridge({ op: 'journal', rows })
  },
}

// --- denial journaling (batched, fire-and-forget) ----------------------------

interface DenialRow {
  phase: 'arm' | 'deny'
  code?: string
  pid?: string
  verb?: string
  http_status?: number
  detail?: string
}

const pendingJournal: DenialRow[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null

export function journalEvent(row: DenialRow): void {
  pendingJournal.push(row)
  if (pendingJournal.length > 200) pendingJournal.splice(0, pendingJournal.length - 200)
  if (!flushTimer) {
    flushTimer = setTimeout(() => {
      flushTimer = null
      void flushJournal()
    }, 1500)
    // Never hold the process open for a journal batch.
    if (typeof flushTimer.unref === 'function') flushTimer.unref()
  }
}

export async function flushJournal(): Promise<void> {
  if (pendingJournal.length === 0) return
  const rows = pendingJournal.splice(0, 50)
  try {
    await door.journal(rows)
  } catch {
    /* journal failures are surfaced on receipts, not thrown here */
  }
}

/** Tests: drain synchronously and reset shared state. */
export function _resetForTests(): void {
  pendingJournal.length = 0
  if (flushTimer) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  memSpent.clear()
  rateLimiter.reset()
}
