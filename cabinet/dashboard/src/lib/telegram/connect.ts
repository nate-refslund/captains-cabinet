/**
 * The guided Telegram connect — its transport, and the one decision it makes.
 *
 * WHAT THIS REPLACES. Connecting a fresh cabinet to the operator's phone was a
 * terminal errand in three parts: create a bot with @BotFather, hand-edit
 * `TELEGRAM_COS_TOKEN=` into cabinet/.env with the right name, then run
 * `cabinet/scripts/telegram-capture-chat-id.sh --write` and read a numeric id
 * off a terminal. A non-technical operator cannot cross that, so a fresh hatch
 * boots Telegram-dark and stays there. This module is that script's logic,
 * ported so the dashboard can do all of it with no terminal.
 *
 * THE ONE-DOOR RATCHET, STATED HONESTLY. `framework/tests/test_single_telegram_door.py`
 * holds that only the gated front-door channel and a shrink-only allowlist may
 * speak to api.telegram.org — and its own docstring records that its SCAN_GLOBS
 * reach python and shell only, naming `lib/docker.ts` and
 * `app/api/telegram/provisioning-webhook/route.ts` as TypeScript callers it has
 * never seen. This file is the third, and that docstring now names it. It is
 * deliberately the ONLY new one: every Telegram call in the connect flow goes
 * through `callTelegram` here, so widening that scan later has one file to
 * decide about rather than a scatter.
 *
 * WHAT IT IS ALLOWED TO DO. Three methods, and only three:
 *   getMe        — read-only. Proves the token is real and names the bot.
 *   getUpdates   — read-only, `timeout=0&limit=100` and NO offset, exactly as
 *                  telegram-capture-chat-id.sh does it: without an offset
 *                  Telegram consumes nothing, so the cabinet's own poller still
 *                  sees every message afterwards and this can be re-run freely.
 *   sendMessage  — ONE message, to the chat id the operator just confirmed, so
 *                  the round trip is something they SEE rather than something
 *                  they are told about.
 * `api.telegram.org` is on the framework egress floor
 * (framework/defaults/egress.yml) and an instance override is UNIONED with that
 * floor, so the ceiling cannot close this host — pinned, so it stays true, by
 * cabinet/scripts/tests/test_egress_guard.py.
 *
 * THE TOKEN NEVER LEAVES. It arrives as an argument, goes into the request URL,
 * and is scrubbed out of every string that comes back. No function here returns
 * it, embeds it in an error, or logs it — `scrub` is applied to every failure
 * detail before it is put in a result, because the bot URL EMBEDS the token and
 * a transport error routinely quotes the URL it failed on.
 */

import { sanitizeLabel, type ChatCandidate, type TelegramFailureReason } from './contract'

/** How long a single Telegram call may take before it is a failure. */
const CALL_TIMEOUT_MS = 8000

/**
 * The API root. `TELEGRAM_API_BASE` is the SAME override name
 * `framework/frontdoor/channel.py` uses, so the two Telegram surfaces are
 * redirected by one variable — and it is how the tests point this module at a
 * local fixture server instead of the real host.
 */
export function telegramBase(): string {
  return (process.env.TELEGRAM_API_BASE || 'https://api.telegram.org').replace(/\/+$/, '')
}

/**
 * Remove anything token-shaped from a string that is about to be shown or
 * stored. Two passes, because either alone leaks:
 *   - the URL form `…/bot<token>/getMe`, which is what a transport error quotes;
 *   - the bare token, when the caller has it and the string came from elsewhere.
 */
export function scrub(text: string, token?: string): string {
  let out = String(text ?? '').replace(/\/bot[^/\s"'`]+/g, '/bot<redacted>')
  if (token && token.length >= 8) out = out.split(token).join('<redacted>')
  return out
}

export type TelegramCall<T> =
  | { ok: true; result: T }
  | { ok: false; reason: TelegramFailureReason; detail: string }

interface Envelope<T> {
  ok?: unknown
  result?: T
  description?: unknown
}

/**
 * One Bot API call. GET for the two reads, POST for the one send.
 *
 * Every failure comes back as a VALUE with a reason a caller can branch on —
 * never a throw carrying a token-bearing URL up a stack that logs it.
 */
export async function callTelegram<T>(
  token: string,
  method: 'getMe' | 'getUpdates' | 'sendMessage',
  params: Record<string, string> = {}
): Promise<TelegramCall<T>> {
  const url = `${telegramBase()}/bot${token}/${method}`
  let response: Response
  try {
    response =
      method === 'sendMessage'
        ? await fetch(url, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(params),
            signal: AbortSignal.timeout(CALL_TIMEOUT_MS),
            cache: 'no-store',
          })
        : await fetch(`${url}?${new URLSearchParams(params).toString()}`, {
            signal: AbortSignal.timeout(CALL_TIMEOUT_MS),
            cache: 'no-store',
          })
  } catch (err) {
    return {
      ok: false,
      reason: 'unreachable',
      detail: scrub(err instanceof Error ? err.message : String(err), token),
    }
  }

  // 409 before the body: Telegram says Conflict when a second reader holds the
  // token, and that is a DIFFERENT thing for the operator to do about it.
  if (response.status === 409) {
    return { ok: false, reason: 'conflict', detail: 'another reader already holds this bot' }
  }

  // 429 before the body too, for the same reason: it arrives in the SAME
  // `ok: false` envelope as a refused token, and the two need different words.
  if (response.status === 429) {
    return { ok: false, reason: 'rate_limited', detail: 'asked to slow down' }
  }

  let body: Envelope<T>
  try {
    body = (await response.json()) as Envelope<T>
  } catch {
    return { ok: false, reason: 'unreadable', detail: `answered ${response.status}` }
  }

  if (body?.ok !== true) {
    return {
      ok: false,
      reason: 'rejected',
      detail: scrub(String(body?.description ?? `answered ${response.status}`), token),
    }
  }
  return { ok: true, result: body.result as T }
}

export interface BotIdentity {
  id: number
  username: string
  name: string
}

/** Who this token is. The proof that a pasted token is a working bot. */
export async function getMe(token: string): Promise<TelegramCall<BotIdentity>> {
  const call = await callTelegram<{
    id?: unknown
    username?: unknown
    first_name?: unknown
  }>(token, 'getMe')
  if (!call.ok) return call
  const raw = call.result ?? {}
  return {
    ok: true,
    result: {
      id: typeof raw.id === 'number' ? raw.id : 0,
      username: sanitizeLabel(typeof raw.username === 'string' ? raw.username : ''),
      name: sanitizeLabel(typeof raw.first_name === 'string' ? raw.first_name : ''),
    },
  }
}

/** A Bot API update, as much of it as this flow reads. */
export interface RawUpdate {
  message?: RawMessage
  edited_message?: RawMessage
}
interface RawMessage {
  chat?: { id?: unknown; type?: unknown; title?: unknown }
  from?: { id?: unknown; username?: unknown; first_name?: unknown; is_bot?: unknown }
}

/**
 * The pending window, WITHOUT consuming it.
 *
 * `limit=100` is the API maximum and `timeout=0` makes it a single read. No
 * offset is ever sent — that is what leaves every update pending for the
 * cabinet's own poller, and what makes calling this in a loop safe.
 */
export async function getPendingUpdates(token: string): Promise<TelegramCall<RawUpdate[]>> {
  const call = await callTelegram<RawUpdate[]>(token, 'getUpdates', {
    timeout: '0',
    limit: '100',
  })
  if (!call.ok) return call
  return { ok: true, result: Array.isArray(call.result) ? call.result : [] }
}

/** Send the one message that proves the round trip. */
export async function sendMessage(
  token: string,
  chatId: string,
  text: string
): Promise<TelegramCall<{ message_id?: unknown }>> {
  return callTelegram<{ message_id?: unknown }>(token, 'sendMessage', { chat_id: chatId, text })
}

export interface CaptureReading {
  /** The first private sender in the window — the one this flow will bind to. */
  candidate: ChatCandidate | null
  /** Every OTHER distinct private sender seen. Non-empty means "ask harder". */
  others: ChatCandidate[]
  /** True when the only thing in the window was a group chat. */
  groupOnly: boolean
  /** The window came back full, so newer messages may lie beyond it. */
  windowFull: boolean
}

/**
 * WHICH CHAT TO BIND TO — the question a capture gets wrong silently.
 *
 * `CAPTAIN_TELEGRAM_ID` becomes the default-deny identity gate on inbound DMs
 * and the sole recipient of every outbound briefing. If a stranger messaged the
 * fresh bot — a bot username is guessable, and Telegram will deliver anyone's
 * DM — then binding to "the latest sender" hands them the cabinet's phone line.
 * The shell script's answer is a human eye on a printed id; this flow's answer
 * is three things together:
 *
 *   1. bind to the FIRST private sender in the window, never the latest. The
 *      operator is told to message the bot; the first message is theirs unless
 *      somebody beat them to a bot that has existed for under a minute.
 *   2. report every OTHER distinct sender, so "more than one person has
 *      messaged this bot" is on the screen rather than only in the data.
 *   3. return a CANDIDATE, never a decision — nothing is written until the
 *      operator confirms the name they are shown.
 *
 * Bots are skipped (`is_bot`), and group chats are not candidates at all: this
 * flow connects a person's phone, and a negative chat id is a room.
 */
export function readCapture(updates: RawUpdate[]): CaptureReading {
  const seen = new Map<string, ChatCandidate>()
  let groupSeen = false

  for (const update of Array.isArray(updates) ? updates : []) {
    const message = update?.message ?? update?.edited_message
    const chat = message?.chat
    const from = message?.from
    const chatId = chat?.id
    if (typeof chatId !== 'number' || !Number.isFinite(chatId)) continue
    if (chatId < 0 || chat?.type === 'group' || chat?.type === 'supergroup') {
      groupSeen = true
      continue
    }
    if (from?.is_bot === true) continue
    const key = String(chatId)
    if (seen.has(key)) continue
    const username = typeof from?.username === 'string' ? from.username : ''
    const firstName = typeof from?.first_name === 'string' ? from.first_name : ''
    seen.set(key, { chatId: key, label: sanitizeLabel(username ? `@${username}` : firstName) })
  }

  const all = [...seen.values()]
  return {
    candidate: all[0] ?? null,
    others: all.slice(1),
    groupOnly: all.length === 0 && groupSeen,
    windowFull: Array.isArray(updates) && updates.length >= 100,
  }
}
