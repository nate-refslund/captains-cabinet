'use server'

import { readFile } from 'node:fs/promises'
import { cabinetPath } from '@/lib/cabinet-root'
import { assertRuntimeWritesAllowed } from '@/lib/docker'
import {
  editDocument,
  ensureEnvFile,
  mustParseAsYaml,
  readEnvDocument,
  setYamlScalar,
  writeEnvValue,
} from '@/lib/config-write'
import { requireDashboardAuth } from '@/lib/provisioning/guard'
import {
  CHAT_ENV_NAME,
  CHAT_ID_RE,
  CONNECTED_MESSAGE,
  looksLikeBotToken,
  plainFailure,
  TOKEN_ENV_NAME,
  type ChatCandidate,
} from '@/lib/telegram/contract'
import {
  getMe,
  getPendingUpdates,
  readCapture,
  sendMessage,
} from '@/lib/telegram/connect'
import { revalidatePath } from 'next/cache'

/**
 * The guided Telegram connect — the four server-side moves behind it.
 *
 * WHAT AN OPERATOR DOES: create a bot in Telegram, paste the token, message
 * their own bot, confirm the name they are shown. WHAT THIS FILE DOES: prove
 * the token against Telegram before storing it, read the pending window without
 * consuming it, send one message so the round trip is visible, and only then
 * write the captured address to the three places that consume it.
 *
 * EVERY ACTION IS AUTH-GATED. Server Actions are global action-ID POST
 * endpoints and middleware never covers action dispatch (see actions/env.ts),
 * so an unauthenticated caller must never reach a live Telegram call, a stored
 * credential, or a config write.
 *
 * THE TOKEN IS WRITE-ONLY FROM THE BROWSER'S SIDE. It arrives once, in
 * `verifyBotToken`, and is stored through the same safe `.env` writer every
 * other credential uses. No action here returns it, and `getTelegramStatus`
 * reports only whether a token is PRESENT — never a masked copy, never a last
 * four, because a value the page renders is a value in the page source.
 */

const envPath = () => process.env.CABINET_ENV_PATH || cabinetPath('cabinet/.env')
const platformPath = () =>
  process.env.PLATFORM_PATH || cabinetPath('instance/config/platform.yml')
const answersPath = () =>
  process.env.CABINET_ANSWERS_PATH ||
  cabinetPath('instance/config/cabinet-init.answers.yml')

export interface TelegramStatus {
  /** A bot token is stored. Never the token, never part of it. */
  tokenStored: boolean
  /** The captured chat id, or null. An address, not a secret — see below. */
  chatId: string | null
  /** True once both halves are present: the Cabinet can reach the phone. */
  connected: boolean
}

/**
 * What is already set up. Reads cabinet/.env and returns booleans plus the chat
 * id, which is an ADDRESS and not a secret (the same call
 * telegram-capture-chat-id.sh makes when it prints captured ids to a terminal):
 * showing it is what lets an operator check the cabinet is pointed at them.
 */
export async function getTelegramStatus(): Promise<TelegramStatus> {
  if (!(await requireDashboardAuth())) throw new Error('Unauthorized')
  let vars: Record<string, string> = {}
  try {
    vars = await readEnvDocument(envPath())
  } catch {
    vars = {}
  }
  const tokenStored = Boolean(vars[TOKEN_ENV_NAME]?.trim())
  const chatId = vars[CHAT_ENV_NAME]?.trim() || null
  return {
    tokenStored,
    chatId: chatId && CHAT_ID_RE.test(chatId) ? chatId : null,
    connected: tokenStored && Boolean(chatId && CHAT_ID_RE.test(chatId)),
  }
}

export interface VerifyTokenResult {
  ok: boolean
  /** The bot's @username, once Telegram has confirmed it. */
  botUsername?: string
  /** The bot's display name. */
  botName?: string
  /** A sentence for the operator. Never contains the token. */
  error?: string
}

/**
 * STEP 2 — prove the token, then store it.
 *
 * Order matters and is the opposite of the obvious one: `getMe` runs FIRST, so
 * a mistyped token is refused with a sentence instead of being written into
 * cabinet/.env where it would sit looking configured while the cabinet stays
 * dark. Only a token Telegram itself accepted is stored.
 */
export async function verifyBotToken(rawToken: string): Promise<VerifyTokenResult> {
  if (!(await requireDashboardAuth())) return { ok: false, error: 'Unauthorized' }

  const token = String(rawToken ?? '').trim()
  if (!token) return { ok: false, error: 'Paste the token BotFather gave you.' }
  if (!looksLikeBotToken(token)) {
    return {
      ok: false,
      error:
        'That does not look like a bot token. BotFather sends one long line: digits, a colon, then letters and numbers.',
    }
  }

  const identity = await getMe(token)
  if (!identity.ok) return { ok: false, error: plainFailure(identity.reason, 'token') }

  try {
    assertRuntimeWritesAllowed(`store ${TOKEN_ENV_NAME} in cabinet/.env`)
    // A fresh hatch has no cabinet/.env at all, and this is often the first
    // credential of the cabinet's life — the safe writer edits an existing file.
    await ensureEnvFile(envPath())
    await writeEnvValue(envPath(), TOKEN_ENV_NAME, token, { createIfMissing: true })
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : 'Could not store the token.',
    }
  }
  revalidatePath('/integrations')
  return {
    ok: true,
    botUsername: identity.result.username,
    botName: identity.result.name,
  }
}

export interface ListenResult {
  ok: boolean
  /** The first private sender in the pending window, if any. */
  candidate?: ChatCandidate
  /** Other distinct senders — "more than one person messaged this bot". */
  others?: ChatCandidate[]
  /** True when the only traffic seen was a group chat. */
  groupOnly?: boolean
  /** The pending window came back full; newer messages may lie beyond it. */
  windowFull?: boolean
  error?: string
}

/**
 * STEP 3 — read the pending window once.
 *
 * The browser calls this on a bounded loop with a visible count; each call is
 * ONE read with no offset, so nothing is consumed and the cabinet's own poller
 * still sees every message later. That is why "listening" here needs no daemon:
 * it is polling on the operator's behalf for as long as they are watching.
 */
export async function listenForFirstMessage(): Promise<ListenResult> {
  if (!(await requireDashboardAuth())) return { ok: false, error: 'Unauthorized' }

  let token = ''
  try {
    token = (await readEnvDocument(envPath()))[TOKEN_ENV_NAME]?.trim() || ''
  } catch {
    token = ''
  }
  if (!token) {
    return { ok: false, error: 'No bot token is stored yet — go back a step and paste it.' }
  }

  const updates = await getPendingUpdates(token)
  if (!updates.ok) return { ok: false, error: plainFailure(updates.reason, 'listen') }

  const reading = readCapture(updates.result)
  return {
    ok: true,
    candidate: reading.candidate ?? undefined,
    others: reading.others,
    groupOnly: reading.groupOnly,
    windowFull: reading.windowFull,
  }
}

export interface ConfirmResult {
  ok: boolean
  /** The message reached Telegram and is on the operator's phone. */
  delivered: boolean
  /** The words that were sent, so the screen and the phone can be compared. */
  message?: string
  /** Every place the address landed, in plain words. */
  wrote?: string[]
  /** Things that are true and worth saying — never failures dressed as notes. */
  notes?: string[]
  error?: string
}

/**
 * Write one key into a YAML config, appending it at the top level when the file
 * does not carry it yet.
 *
 * `writeYamlScalar` THROWS on a missing field, deliberately — a settings form
 * must never report success for a key it did not find. Here the key is one the
 * generator stamps, so on a generated file it is always present; on a
 * hand-trimmed one, appending it is the right answer rather than refusing to
 * connect. The append is a top-level scalar only, which is the shape
 * `captain_telegram_chat_id` has.
 */
async function writeTopLevelYaml(filePath: string, key: string, value: string) {
  return editDocument(
    filePath,
    (text) => {
      const set = setYamlScalar(text, [key], value, { quoted: true })
      if (set.matched > 0) return set
      const body = text.length && !text.endsWith('\n') ? `${text}\n` : text
      return { text: `${body}${key}: ${JSON.stringify(value)}\n`, matched: 1 }
    },
    { validate: mustParseAsYaml }
  )
}

/**
 * STEP 4 — send the proof, then record the address.
 *
 * SEND FIRST, WRITE SECOND. The send needs nothing on disk, and a cabinet that
 * has recorded an address it has never successfully reached is exactly the
 * "looks configured, is dark" state this whole flow exists to end. So the
 * round trip is proven first; only a delivered message earns the writes.
 *
 * THE ADDRESS LANDS IN THREE PLACES, and the third is the one that stops a
 * regenerate from undoing the other two:
 *
 *   cabinet/.env  CAPTAIN_TELEGRAM_ID
 *       what the runtime actually reads — the recipient of every outbound
 *       message and the identity gate on inbound DMs.
 *   instance/config/platform.yml  captain_telegram_chat_id
 *       what the inbound poller's capture seam and the governance label channel
 *       read. It is a GENERATED key: cabinet/scripts/generate-instance.py
 *       re-stamps it from the interview answers on every run.
 *   instance/config/cabinet-init.answers.yml  captain.telegram_chat_id
 *       the SOURCE that generated key is derived from. Writing platform.yml
 *       alone would be a hand-edit of a generator output: the next
 *       generate-instance.py run would stamp the placeholder back over it and
 *       the cabinet would go quiet with nothing to show why. Writing the answer
 *       too means a regenerate re-derives the SAME value. Pinned end to end by
 *       cabinet/scripts/tests/test_telegram_chat_id_survives_regenerate.py.
 *
 * An absent answers file is not a failure — a deployment that never ran the
 * interview has nothing to keep in step — but it IS said out loud, because
 * silence there would hide the one thing that could later revert the write.
 */
export async function confirmChatAndSend(rawChatId: string): Promise<ConfirmResult> {
  if (!(await requireDashboardAuth())) {
    return { ok: false, delivered: false, error: 'Unauthorized' }
  }

  const chatId = String(rawChatId ?? '').trim()
  if (!CHAT_ID_RE.test(chatId)) {
    return { ok: false, delivered: false, error: 'That is not a chat address I can use.' }
  }

  let token = ''
  try {
    token = (await readEnvDocument(envPath()))[TOKEN_ENV_NAME]?.trim() || ''
  } catch {
    token = ''
  }
  if (!token) {
    return {
      ok: false,
      delivered: false,
      error: 'No bot token is stored yet — go back a step and paste it.',
    }
  }

  const sent = await sendMessage(token, chatId, CONNECTED_MESSAGE)
  if (!sent.ok) {
    return { ok: false, delivered: false, error: plainFailure(sent.reason, 'send') }
  }

  const wrote: string[] = []
  const notes: string[] = []
  try {
    assertRuntimeWritesAllowed(`store ${CHAT_ENV_NAME} in cabinet/.env`)
    await ensureEnvFile(envPath())
    await writeEnvValue(envPath(), CHAT_ENV_NAME, chatId, { createIfMissing: true })
    wrote.push('where your Cabinet looks for who to message')
  } catch (err) {
    return {
      ok: true,
      delivered: true,
      message: CONNECTED_MESSAGE,
      error: `The message went through, but the address could not be saved — ${
        err instanceof Error ? err.message : 'the write failed'
      }`,
    }
  }

  try {
    await writeTopLevelYaml(platformPath(), 'captain_telegram_chat_id', chatId)
    wrote.push('your Cabinet settings')
  } catch (err) {
    notes.push(
      `Your Cabinet settings file was not updated — ${
        err instanceof Error ? err.message : 'the write failed'
      }`
    )
  }

  try {
    await readFile(answersPath(), 'utf8')
  } catch {
    notes.push(
      'There is no setup-interview file on this machine, so there is nothing else to keep in step.'
    )
    revalidatePath('/integrations')
    return { ok: true, delivered: true, message: CONNECTED_MESSAGE, wrote, notes }
  }

  try {
    await editDocument(
      answersPath(),
      (text) => setYamlScalar(text, ['captain', 'telegram_chat_id'], chatId, { quoted: true }),
      {
        validate: mustParseAsYaml,
        missingHint:
          'the setup-interview file has no place to record your Telegram address, so it was left alone',
      }
    )
    wrote.push('your setup answers, so re-running setup keeps this address')
  } catch (err) {
    notes.push(
      `Your setup answers were not updated, so re-running setup would undo this — ${
        err instanceof Error ? err.message : 'the write failed'
      }`
    )
  }

  revalidatePath('/integrations')
  return { ok: true, delivered: true, message: CONNECTED_MESSAGE, wrote, notes }
}
