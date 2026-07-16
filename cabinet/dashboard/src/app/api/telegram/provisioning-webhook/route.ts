/**
 * Spec 034 PR 4 — POST /api/telegram/provisioning-webhook
 *
 * Telegram webhook endpoint for the manager bot's conversational provisioning
 * flow. Telegram calls this URL with each incoming message.
 *
 * Auth: Verifies `chat_id` against the Cabinet's canonical
 *       `CAPTAIN_TELEGRAM_ID` env var (`CAPTAIN_TELEGRAM_CHAT_ID` remains a
 *       compatibility alias).
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
 * CAPTAIN_TELEGRAM_ID is the Captain's personal chat_id (integer as string).
 * CAPTAIN_TELEGRAM_CHAT_ID is accepted only as a compatibility alias; if both
 * are set and disagree, the route rejects every update.
 * This single-Captain guard is intentional per spec §out-of-scope:
 * "Multi-Captain support is Phase 4".
 */
function configuredCaptainChatId(): string | null {
  const canonical = process.env.CAPTAIN_TELEGRAM_ID?.trim()
  const legacy = process.env.CAPTAIN_TELEGRAM_CHAT_ID?.trim()
  if (canonical && legacy && canonical !== legacy) {
    console.error('[provisioning-webhook] Captain Telegram id aliases disagree — rejecting all messages')
    return null
  }
  return canonical || legacy || null
}

function isCaptainChat(chatId: number): boolean {
  const configured = configuredCaptainChatId()
  if (!configured) {
    // If not configured (or aliases conflict), fail-closed.
    console.warn('[provisioning-webhook] CAPTAIN_TELEGRAM_ID not set — rejecting all messages')
    return false
  }
  return String(chatId) === configured
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
 * Uses the Cabinet's canonical TELEGRAM_COS_TOKEN; MANAGER_BOT_TOKEN remains
 * a compatibility fallback for older provisioning-only deployments.
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
): Promise<boolean> {
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
  const token = process.env.TELEGRAM_COS_TOKEN || process.env.MANAGER_BOT_TOKEN
  if (!token) {
    console.error('[provisioning-webhook] TELEGRAM_COS_TOKEN not set — cannot send message')
    await recordTransport('failed', { error_code: 'bot_token_unavailable' })
    return false
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
      return false
    } else {
      await recordTransport('succeeded', { http_status: res.status })
      return true
    }
  } catch {
    console.error('[provisioning-webhook] sendMessage transport error')
    await recordTransport('failed', { error_code: 'telegram_transport_error' })
    return false
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
): Promise<boolean> {
  let delivered = true
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i]
    const sent = await sendTelegramMessage(chatId, msg.text, i === 0 ? replyToId : undefined, {
      plain: msg.plain,
      buttons: msg.buttons,
    }, evidenceActionId)
    delivered = sent && delivered
    // If message has additional chained messages, send them too
    if (msg.additional) {
      for (const extra of msg.additional) {
        const extraSent = await sendTelegramMessage(chatId, extra.text, undefined, {
          plain: extra.plain,
          buttons: extra.buttons,
        }, evidenceActionId)
        delivered = extraSent && delivered
      }
    }
  }
  return delivered
}

/**
 * Canonical onboarding updates are retry-safe: their action id is derived from
 * Telegram's stable update_id and the journey core is idempotent.  A successful
 * state transition is therefore not enough to ACK the transport — the Captain's
 * canonical reply must also have landed.  Non-2xx makes public Telegram webhook
 * deployments retry; the local sole poller reads the explicit body and retains
 * its offset for the same retry instead of falling through to the Chair LLM.
 */
function onboardingDeliveryResponse(
  delivered: boolean,
  deliveryRequired = true
): NextResponse {
  return NextResponse.json(
    {
      ok: delivered,
      handled: true,
      delivered,
      delivery_required: deliveryRequired,
      retryable: !delivered,
    },
    { status: delivered ? 200 : 503 }
  )
}

async function answerCallbackQuery(callbackId: string): Promise<void> {
  const token = process.env.TELEGRAM_COS_TOKEN || process.env.MANAGER_BOT_TOKEN
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
// Typed-purge detection
// ---------------------------------------------------------------------------

/**
 * Mirror of the INTENT grammar in `@/lib/onboarding/telegram.ts` — keep the
 * two in lockstep (telegram.ts does not export it). The journey strips this
 * prefix and then treats `purge PURGE` as a confirmed purge, so `/onboard`,
 * `/onboarding`, `/orientation`, slashless, leading-whitespace, and
 * case-variant intent forms ALL really purge.
 */
const ONBOARDING_INTENT = /^\s*\/?(?:onboard|onboarding|orientation)\b/i

/**
 * True for exactly the messages the onboarding journey treats as a confirmed
 * typed purge. Derived from the same grammar as `handleTelegramOnboarding`
 * (strip INTENT, then `/^purge\s+PURGE$/` on the trimmed remainder) instead of
 * a separate slash-only regex, so the post-purge evidence suppression can
 * never diverge from what actually purges: a divergent form would purge the
 * trial and then attempt to observe into the store it just removed.
 */
function isTypedOnboardingPurgeText(text: string): boolean {
  if (!ONBOARDING_INTENT.test(text)) return false
  return /^purge\s+PURGE$/.test(text.replace(ONBOARDING_INTENT, '').trim())
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
      return onboardingDeliveryResponse(true, false)
    }
    // Telegram callback ids have a short answer window. Clear the spinner as
    // soon as transport + Captain auth pass, before any First Window scan or
    // reply delivery. The state action remains independently idempotent.
    await answerCallbackQuery(callback.id)
    const replies = await handleTelegramOnboardingCallback(
      callback.data,
      `telegram-update-${update.update_id}`
    )
    const delivered = replies.length > 0 && await sendReplies(
      chatId, replies, callback.message.message_id,
      `telegram-update-${update.update_id}`
    )
    return onboardingDeliveryResponse(delivered, replies.length > 0)
  }

  const message = update.message
  const isOnboardingMessage = Boolean(
    message && (message.text || message.caption) &&
    isOnboardingIntent(message.text || message.caption || '')
  )
  if (flagResponse && !isOnboardingMessage) return flagResponse
  if (!message) {
    // Unknown callback queries and other non-message updates are acknowledged.
    if (callback?.data?.startsWith('onboard:')) {
      return onboardingDeliveryResponse(true, false)
    }
    return NextResponse.json({ ok: true })
  }

  const chatId = message.chat.id
  const messageId = message.message_id

  // --- Captain-auth guard ---
  if (!isCaptainChat(chatId)) {
    console.warn(`[provisioning-webhook] Rejected message from unauthorized chat_id: ${chatId}`)
    // 200 to stop Telegram retries; no reply to non-Captain chats
    if (isOnboardingMessage) return onboardingDeliveryResponse(true, false)
    return NextResponse.json({ ok: true })
  }

  // Extract text — prefer text field, fall back to caption (forwarded media)
  const rawText = message.text || message.caption || ''

  if (!rawText.trim()) {
    // Non-text message (photo, sticker, etc.) — ignore in PR 4
    return NextResponse.json({ ok: true })
  }
  const isTypedOnboardingPurge = isOnboardingMessage && isTypedOnboardingPurgeText(rawText)

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
    const errorDelivered = await sendTelegramMessage(
      chatId,
      'Something went wrong. Please try again or say "cancel".',
      undefined,
      undefined,
      isOnboardingMessage && !isTypedOnboardingPurge ? `telegram-update-${update.update_id}` : undefined
    )
    if (isOnboardingMessage) return onboardingDeliveryResponse(errorDelivered)
    return NextResponse.json({ ok: true })
  }

  // Send replies back to Captain
  let repliesDelivered = true
  if (replies.length > 0) {
    repliesDelivered = await sendReplies(
      chatId,
      replies,
      messageId,
      isOnboardingMessage && !isTypedOnboardingPurge ? `telegram-update-${update.update_id}` : undefined
    )
  }

  if (isOnboardingMessage && (!replies.length || !repliesDelivered)) {
    return onboardingDeliveryResponse(false, replies.length > 0)
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

  if (isOnboardingMessage) return onboardingDeliveryResponse(true)

  // The legacy provisioning flow remains always-200. Canonical onboarding
  // returns 503 above only when its visible reply did not land, so Telegram (or
  // the local poller) can retry the same idempotent update.
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
