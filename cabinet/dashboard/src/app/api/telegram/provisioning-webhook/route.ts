/**
 * Spec 034 PR 4 — POST /api/telegram/provisioning-webhook
 *
 * Telegram webhook endpoint for the manager bot's conversational provisioning
 * flow. Telegram calls this URL with each incoming message.
 *
 * Auth: Verifies `chat_id` against `CAPTAIN_TELEGRAM_CHAT_ID` env var.
 *       Non-Captain chat_ids receive a 403 and no bot reply.
 *
 * Dispatches to `provisioning-flow.ts` for state machine logic.
 * Replies to Captain via Telegram Bot API (sendMessage).
 *
 * Feature flag: Multi-Cabinet provisioning returns 503 when disabled. The
 * canonical post-hatch `/onboard` journey remains available independently.
 *
 * Polling: After all bots adopted, starts a background polling loop that
 * sends live status updates. PR 5 will replace this with SSE push.
 *
 * Spec refs: §2 "Conversational Telegram flow", AC 4, 11, 12
 */

import { NextRequest, NextResponse } from 'next/server'
import { createHash, timingSafeEqual } from 'node:crypto'
import { featureFlagCheck } from '@/lib/provisioning/guard'
import {
  handleMessage,
  startPollingLoop,
  loadState,
} from '@/lib/provisioning/flow'
import type { BotMessage } from '@/lib/provisioning/flow'
import {
  handleTelegramOnboarding,
  handleTelegramOnboardingCallback,
  isOnboardingIntent,
} from '@/lib/onboarding/telegram'
import { recordOnboardingEvidence } from '@/lib/onboarding/bridge'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Types — Telegram Update subset
// ---------------------------------------------------------------------------

interface TelegramUser {
  id: number
  first_name: string
  username?: string
}

interface TelegramChat {
  id: number
  type: string
}

interface TelegramMessage {
  message_id: number
  from?: TelegramUser
  chat: TelegramChat
  text?: string
  /** Set when message is a forward — present for BotFather forward flow */
  forward_from?: TelegramUser
  /** Caption for forwarded messages */
  caption?: string
  /** Date (Unix timestamp) */
  date: number
}

interface TelegramUpdate {
  update_id: number
  message?: TelegramMessage
  callback_query?: {
    id: string
    from: TelegramUser
    message?: TelegramMessage
    data?: string
  }
}

// ---------------------------------------------------------------------------
// Captain authentication
// ---------------------------------------------------------------------------

/**
 * Verify that the incoming message is from the configured Captain chat.
 *
 * CAPTAIN_TELEGRAM_CHAT_ID is the Captain's personal chat_id (integer as string).
 * This single-Captain guard is intentional per spec §out-of-scope:
 * "Multi-Captain support is Phase 4".
 */
function isCaptainChat(chatId: number): boolean {
  const configured = process.env.CAPTAIN_TELEGRAM_CHAT_ID
  if (!configured) {
    // If not configured, fail-closed: reject all (safe default)
    console.warn('[provisioning-webhook] CAPTAIN_TELEGRAM_CHAT_ID not set — rejecting all messages')
    return false
  }
  return String(chatId) === configured.trim()
}

/**
 * Verify Telegram's per-webhook secret token — set once at setWebhook time and
 * sent by Telegram on EVERY update as the X-Telegram-Bot-Api-Secret-Token
 * header. This is the transport authentication: the request BODY (chat_id and
 * all) is attacker-controllable, a header secret is not. Fail-closed — an unset
 * TELEGRAM_WEBHOOK_SECRET rejects every update rather than running the
 * onboarding/provisioning state machine (including the destructive purge) for
 * an unauthenticated caller. isCaptainChat stays as a second, in-band check.
 */
function webhookSecretOk(req: NextRequest): boolean {
  const configured = process.env.TELEGRAM_WEBHOOK_SECRET
  if (!configured) {
    console.warn('[provisioning-webhook] TELEGRAM_WEBHOOK_SECRET not set — rejecting all updates')
    return false
  }
  const presented = req.headers.get('x-telegram-bot-api-secret-token') || ''
  // SHA-256 both sides so timingSafeEqual always compares equal-length buffers
  // (no length-mismatch throw) in constant time.
  const a = createHash('sha256').update(presented).digest()
  const b = createHash('sha256').update(configured.trim()).digest()
  return timingSafeEqual(a, b)
}

// ---------------------------------------------------------------------------
// Telegram API sender
// ---------------------------------------------------------------------------

const TELEGRAM_API_BASE = 'https://api.telegram.org/bot'

/**
 * Send a text message to a Telegram chat via the Bot API.
 * Uses MANAGER_BOT_TOKEN env var.
 *
 * Markdown parse_mode: 'Markdown' (v1) — safe for our backtick/bold patterns.
 * Messages longer than 4096 chars are truncated (Telegram limit).
 */
async function sendTelegramMessage(
  chatId: number,
  text: string,
  replyToMessageId?: number,
  options?: {
    plain?: boolean
    buttons?: Array<Array<{ text: string; callback_data: string }>>
  },
  evidenceActionId?: string
): Promise<void> {
  const recordTransport = async (
    status: 'succeeded' | 'failed',
    detail: Record<string, unknown>
  ) => {
    if (!evidenceActionId) return
    try {
      await recordOnboardingEvidence({
        phase: 'transport', status,
        action_id: `telegram-transport-${evidenceActionId}`,
        trace_id: `trace-${evidenceActionId}`,
        correlation_id: `corr-${evidenceActionId}`,
        detail: { transport: 'telegram_bot_api', ...detail },
      }, 'telegram')
    } catch {
      console.error('[provisioning-webhook] Telegram evidence unavailable')
    }
  }
  const token = process.env.MANAGER_BOT_TOKEN
  if (!token) {
    console.error('[provisioning-webhook] MANAGER_BOT_TOKEN not set — cannot send message')
    await recordTransport('failed', { error_code: 'bot_token_unavailable' })
    return
  }

  const truncated = text.length > 4096 ? text.slice(0, 4093) + '…' : text

  const body: Record<string, unknown> = {
    chat_id: chatId,
    text: truncated,
  }
  if (!options?.plain) body.parse_mode = 'Markdown'
  if (replyToMessageId) {
    body.reply_to_message_id = replyToMessageId
  }
  if (options?.buttons && options.buttons.length > 0) {
    body.reply_markup = { inline_keyboard: options.buttons }
  }

  try {
    const res = await fetch(`${TELEGRAM_API_BASE}${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      console.error('[provisioning-webhook] sendMessage failed', { status: res.status })
      await recordTransport('failed', { error_code: 'telegram_http_error', http_status: res.status })
    } else {
      await recordTransport('succeeded', { http_status: res.status })
    }
  } catch {
    console.error('[provisioning-webhook] sendMessage transport error')
    await recordTransport('failed', { error_code: 'telegram_transport_error' })
  }
}

/**
 * Send all BotMessages from the flow handler to Telegram.
 * First message threads to the Captain's original message_id.
 */
async function sendReplies(
  chatId: number,
  messages: BotMessage[],
  replyToId?: number,
  evidenceActionId?: string
): Promise<void> {
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i]
    await sendTelegramMessage(chatId, msg.text, i === 0 ? replyToId : undefined, {
      plain: msg.plain,
      buttons: msg.buttons,
    }, evidenceActionId)
    // If message has additional chained messages, send them too
    if (msg.additional) {
      for (const extra of msg.additional) {
        await sendTelegramMessage(chatId, extra.text, undefined, {
          plain: extra.plain,
          buttons: extra.buttons,
        }, evidenceActionId)
      }
    }
  }
}

async function answerCallbackQuery(callbackId: string): Promise<void> {
  const token = process.env.MANAGER_BOT_TOKEN
  if (!token) return
  try {
    await fetch(`${TELEGRAM_API_BASE}${token}/answerCallbackQuery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ callback_query_id: callbackId }),
    })
  } catch {
    // The reply card still lands; clearing Telegram's spinner is best-effort.
  }
}

// ---------------------------------------------------------------------------
// Webhook handler
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest): Promise<NextResponse> {
  // Transport auth FIRST — before any body parse or dispatch. A forged request,
  // or any request lacking Telegram's secret-token header, never reaches the
  // onboarding/provisioning state machine.
  if (!webhookSecretOk(req)) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }

  // The multi-Cabinet provisioning flag does not gate the canonical
  // post-hatch orientation. Evaluate it now, but apply it only after parsing
  // enough of the authenticated update to distinguish /onboard.
  const flagResponse = featureFlagCheck()

  // Parse update
  let update: TelegramUpdate
  try {
    update = (await req.json()) as TelegramUpdate
  } catch {
    // Telegram retries on non-200; return 200 to ack and drop
    return NextResponse.json({ ok: true })
  }

  const callback = update.callback_query
  if (callback?.data?.startsWith('onboard:') && callback.message) {
    const chatId = callback.message.chat.id
    if (!isCaptainChat(chatId)) {
      console.warn(`[provisioning-webhook] Rejected callback from unauthorized chat_id: ${chatId}`)
      return NextResponse.json({ ok: true })
    }
    const replies = await handleTelegramOnboardingCallback(
      callback.data,
      `telegram-update-${update.update_id}`
    )
    await sendReplies(
      chatId, replies, callback.message.message_id,
      `telegram-update-${update.update_id}`
    )
    await answerCallbackQuery(callback.id)
    return NextResponse.json({ ok: true })
  }

  const message = update.message
  const isOnboardingMessage = Boolean(
    message && (message.text || message.caption) &&
    isOnboardingIntent(message.text || message.caption || '')
  )
  if (flagResponse && !isOnboardingMessage) return flagResponse
  if (!message) {
    // Unknown callback queries and other non-message updates are acknowledged.
    return NextResponse.json({ ok: true })
  }

  const chatId = message.chat.id
  const messageId = message.message_id

  // --- Captain-auth guard ---
  if (!isCaptainChat(chatId)) {
    console.warn(`[provisioning-webhook] Rejected message from unauthorized chat_id: ${chatId}`)
    // 200 to stop Telegram retries; no reply to non-Captain chats
    return NextResponse.json({ ok: true })
  }

  // Extract text — prefer text field, fall back to caption (forwarded media)
  const rawText = message.text || message.caption || ''

  if (!rawText.trim()) {
    // Non-text message (photo, sticker, etc.) — ignore in PR 4
    return NextResponse.json({ ok: true })
  }
  const isTypedOnboardingPurge = Boolean(
    isOnboardingMessage && /^\/(?:onboard|onboarding)\s+purge\s+PURGE\s*$/.test(rawText)
  )

  // A First Window command may contain a private absolute path and purpose.
  // Keep both out of process logs; the canonical core records only bounded,
  // structured receipts. Retain token redaction for the older provisioning
  // flow, whose inputs do not contain onboarding source details.
  const logSafeText = isOnboardingMessage
    ? '[ONBOARDING_COMMAND_REDACTED]'
    : rawText.replace(/[0-9]{8,12}:[a-zA-Z0-9_-]{35,}/g, '[TOKEN_REDACTED]')
  console.log(`[provisioning-webhook] chat=${chatId} text="${logSafeText}"`)

  // ------------------------------------------------------------------
  // Dispatch to state machine
  // ------------------------------------------------------------------
  let replies: BotMessage[]
  try {
    replies = isOnboardingMessage
      ? await handleTelegramOnboarding(rawText, `telegram-update-${update.update_id}`)
      : await handleMessage(String(chatId), rawText)
  } catch {
    console.error('[provisioning-webhook] handler failed', { onboarding: isOnboardingMessage })
    await sendTelegramMessage(
      chatId,
      'Something went wrong. Please try again or say "cancel".',
      undefined,
      undefined,
      isOnboardingMessage && !isTypedOnboardingPurge ? `telegram-update-${update.update_id}` : undefined
    )
    return NextResponse.json({ ok: true })
  }

  // Send replies back to Captain
  if (replies.length > 0) {
    await sendReplies(
      chatId,
      replies,
      messageId,
      isOnboardingMessage && !isTypedOnboardingPurge ? `telegram-update-${update.update_id}` : undefined
    )
  }

  // ------------------------------------------------------------------
  // Start polling loop if we just entered polling_status
  // ------------------------------------------------------------------
  const stateAfter = await loadState(String(chatId))
  if (stateAfter?.step === 'polling_status' && stateAfter.cabinetId) {
    // Fire-and-forget: polling loop runs in background
    // Note: In Vercel serverless, this runs until function timeout.
    // PR 5 will replace with a proper queue/SSE mechanism.
    startPollingLoop(
      String(chatId),
      stateAfter,
      async (msg) => {
        await sendTelegramMessage(chatId, msg.text)
      }
    ).catch((err) => {
      console.error('[provisioning-webhook] polling loop error:', err)
    })
  }

  // Always return 200 — Telegram retries on any non-2xx
  return NextResponse.json({ ok: true })
}

// ---------------------------------------------------------------------------
// GET — health check for webhook registration verification
// ---------------------------------------------------------------------------

export async function GET(): Promise<NextResponse> {
  return NextResponse.json({
    ok: true,
    endpoint: 'provisioning-webhook',
    note: 'POST only — this endpoint receives Telegram updates',
  })
}
