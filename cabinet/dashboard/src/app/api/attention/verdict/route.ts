/**
 * POST /api/attention/verdict — the dashboard's ONE write door (Ruling A,
 * captain-decisions 2026-07-10: WRITE-CLASS-2 = YES, equal-authority-door).
 *
 * Two-phase two-tap on ONE endpoint:
 *   Tap-1 ARM : {pid, verb, revision}                → {armed, confirm_token,
 *               consequence, undo, expires_in}       (nothing executes)
 *   Tap-2 FIRE: {pid, verb, revision, confirm_token} → the FULL chain re-runs,
 *               the single-use token is spent, and the Python bridge submits
 *               the org's own reply grammar through the SAME binder wire the
 *               Captain's typed Telegram replies use.
 *
 * Ordered fail-closed chain (spec §1.2): session 401 → CSRF/origin 403 →
 * rate 429 → freshness 409 (+ refreshed card) → verb 400 → token 403.
 * Every arm/fire/deny becomes one attention-feed journal row (batched via
 * the bridge). Plain-language bodies only; org vocabulary lives in `code`
 * fields, never in `message`.
 */
import { NextRequest, NextResponse } from 'next/server'
import { readQueue, type QueueRow } from '@/lib/attention/queue'
import {
  MESSAGES,
  consequenceFor,
  plainCard,
  revisionOf,
  undoFor,
  VERBS,
  type Verb,
} from '@/lib/attention/plain'
import {
  BODY_CAP_BYTES,
  CONFIRM_TTL_S,
  COOKIE_NAME,
  CSRF_HEADER,
  checkCsrf,
  checkSameOrigin,
  door,
  doorSecret,
  journalEvent,
  mintConfirmToken,
  rateLimiter,
  sessionHash,
  spendNonce,
  verifyConfirmToken,
  verifySessionValue,
} from '@/lib/attention/verdict'

export const dynamic = 'force-dynamic'

interface VerdictBody {
  pid: string
  verb: Verb
  revision: string
  confirm_token?: string
}

function deny(
  status: number,
  code: string,
  extra: Record<string, unknown> = {},
  journal: { pid?: string; verb?: string } = {}
): NextResponse {
  journalEvent({
    phase: 'deny',
    code,
    http_status: status,
    pid: journal.pid,
    verb: journal.verb,
  })
  const message = MESSAGES[code] ?? MESSAGES.bridge_fail
  const res = NextResponse.json({ ok: false, code, message, ...extra }, { status })
  if (status === 429 && typeof extra.retry_after === 'number') {
    res.headers.set('Retry-After', String(extra.retry_after))
  }
  return res
}

function parseBody(raw: string): VerdictBody | null {
  let doc: unknown
  try {
    doc = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof doc !== 'object' || doc === null) return null
  const d = doc as Record<string, unknown>
  const pid = d.pid
  const verb = d.verb
  const revision = d.revision
  const token = d.confirm_token
  if (typeof pid !== 'string' || pid.length === 0 || pid.length > 300) return null
  if (typeof verb !== 'string' || !(VERBS as readonly string[]).includes(verb)) return null
  if (typeof revision !== 'string' || !/^[0-9a-f]{16}$/.test(revision)) return null
  if (token !== undefined && (typeof token !== 'string' || token.length > 512)) return null
  return { pid, verb: verb as Verb, revision, confirm_token: token as string | undefined }
}

function findRow(rows: QueueRow[], pid: string): QueueRow | null {
  return rows.find((r) => r.pid === pid) ?? null
}

export async function POST(req: NextRequest) {
  // a. Session — full signature verification; the door refuses to operate
  //    without a real DASHBOARD_PASSWORD (fail closed, never 'changeme').
  const cookie = req.cookies.get(COOKIE_NAME)?.value
  if (!doorSecret() || !cookie || !verifySessionValue(cookie)) {
    return deny(401, 'no_session')
  }
  const session = sessionHash(cookie)

  // b. CSRF — strict same-origin (when headers present) + double-submit
  //    custom header (forces preflight; this app serves no CORS).
  //    The expected origin derives from the HOST the browser addressed, not
  //    req.nextUrl.origin: under `next start --hostname 0.0.0.0` nextUrl
  //    resolves to http://0.0.0.0:<port>, an origin no browser ever sends,
  //    which made the door deny every legitimate page tap (found live,
  //    deploy 2026-07-10). Host is what the browser targeted — a cross-site
  //    attacker cannot make Origin match it (DNS rebinding shifts BOTH).
  const host = req.headers.get('host')
  const requestOrigin = host ? `${req.nextUrl.protocol}//${host}` : req.nextUrl.origin
  const sameOrigin = checkSameOrigin(
    requestOrigin,
    req.headers.get('origin'),
    req.headers.get('referer')
  )
  if (!sameOrigin || !checkCsrf(cookie, req.headers.get(CSRF_HEADER))) {
    return deny(403, 'csrf')
  }

  // c. Rate limit — per session, burst 3/10s + 10/5min.
  const rate = rateLimiter.take(session)
  if (!rate.ok) {
    return deny(429, 'rate_limited', { retry_after: rate.retryAfterS })
  }

  // Body — capped and strictly shaped.
  const raw = await req.text()
  if (raw.length > BODY_CAP_BYTES) return deny(400, 'bad_request')
  const body = parseBody(raw)
  if (!body) return deny(400, 'bad_request')
  const { pid, verb, revision } = body

  // d. Freshness — live census re-read; never act on what the page cached.
  //
  // ANY source other than the census artifact is a freshness failure, not a
  // decidable list. The old check only caught `empty`: on the degraded live
  // path the rows carry pid=null, so findRow missed and the Captain was told
  // "no longer waiting — it may already be decided" (`gone`) when the truth
  // was that the door could not see the list at all. Wrong reason on a write
  // door is worse than no reason.
  const queue = await readQueue()
  if (queue.source !== 'census') {
    return deny(409, 'stale_census', {}, { pid, verb })
  }
  const row = findRow([...queue.decisions, ...queue.directions], pid)
  if (!row) return deny(409, 'gone', {}, { pid, verb })
  const fresh = revisionOf(row)
  const card = plainCard(row)
  if (card.decided) {
    return deny(409, 'decided', { refreshed: refreshedPayload(row, fresh) }, { pid, verb })
  }
  if (fresh !== revision) {
    return deny(409, 'stale', { refreshed: refreshedPayload(row, fresh) }, { pid, verb })
  }

  // e. Verb legality — census one_tap semantics; rituals never tap-approve.
  if (!card.decidable) return deny(400, 'not_here', {}, { pid, verb })
  if (verb === 'approve') {
    const sem = row.one_tap?.approve
    if (card.ritual || sem === 'ritual-print') return deny(400, 'ritual', {}, { pid, verb })
    if (sem !== 'direct' && sem !== 'per-item-approval') {
      return deny(400, 'bad_verb', {}, { pid, verb })
    }
  } else if (verb === 'no') {
    if (row.one_tap?.veto !== 'direct') return deny(400, 'bad_verb', {}, { pid, verb })
  } else if (row.one_tap?.defer !== 'direct') {
    return deny(400, 'bad_verb', {}, { pid, verb })
  }

  const secret = doorSecret() as string // non-null: checked at (a)

  // Tap-1 ARM — mint the single-use token; show consequence + undo first
  // (deck steal #3: every mutating verb explains itself before firing).
  if (!body.confirm_token) {
    const confirmToken = mintConfirmToken(secret, { pid, verb, revision, session })
    journalEvent({ phase: 'arm', pid, verb })
    return NextResponse.json({
      armed: true,
      confirm_token: confirmToken,
      consequence: consequenceFor(row, verb),
      undo: undoFor(row, verb),
      expires_in: CONFIRM_TTL_S,
    })
  }

  // f. Tap-2 FIRE — verify + spend the token, then the bridge re-validates
  //    freshness and speaks the org's grammar through the org's gate.
  const check = verifyConfirmToken(secret, body.confirm_token, {
    pid,
    verb,
    revision,
    session,
  })
  if (!check.ok) {
    return deny(403, check.code, {}, { pid, verb })
  }
  if (!spendNonce(check.nonce)) return deny(403, 'replay', {}, { pid, verb })

  const result = await door.fire({ pid, verb, revision })
  if (!result.ok) {
    const code = result.code ?? 'bridge_fail'
    const status =
      code === 'stale' || code === 'gone' || code === 'decided' || code === 'stale_census'
        ? 409
        : code === 'bad_verb' || code === 'ritual' || code === 'bad_request'
          ? 400
          : code === 'not_here'
            ? 409
            : 502
    // The bridge journals its own denials; do not double-journal here.
    return NextResponse.json(
      {
        ok: false,
        code,
        message: result.message ?? MESSAGES.bridge_fail,
        ...(result.refreshed ? { refreshed: result.refreshed } : {}),
      },
      { status }
    )
  }

  return NextResponse.json({
    ok: true,
    receipt_seq: result.receipt_seq ?? null,
    deferred: result.deferred === true,
    plain_result: result.plain_result ?? '',
    ...(result.journal_warn ? { journal_warn: result.journal_warn } : {}),
  })
}

function refreshedPayload(row: QueueRow, revision: string) {
  const card = plainCard(row)
  return {
    pid: row.pid,
    state: row.state,
    revision,
    headline: card.headline,
    sentence: card.sentence,
    decided: card.decided,
  }
}
