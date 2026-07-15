// POST|GET /api/telegram/provisioning-webhook — Spec 034 PR 4 harness
//
// Scope: GET health-check, POST feature-flag guard, JSON parse failures,
//   non-message update silently ACK'd, Captain-auth guard (configured vs. not,
//   wrong vs. right chatId), rawText extraction (text/caption/both/empty),
//   privacy-safe logging, handleMessage dispatch, sendReplies
//   (first with replyTo, additional chained), sendTelegramMessage internals
//   (missing token, fetch !ok, fetch throws, text > 4096 truncation),
//   loadState post-dispatch → polling loop fire-and-forget, handleMessage throws,
//   legacy provisioning always-200 behavior, and explicit onboarding delivery
//   ACK/retry semantics.
//
// Mock strategy: vi.hoisted for guard/flow modules and global.fetch.
//   featureFlagCheck is a plain function — mocked via @/lib/provisioning/guard.
//   handleMessage / startPollingLoop / loadState from @/lib/provisioning/flow.
//   global.fetch replaced per-test.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { NextRequest } from 'next/server'

// ---------------------------------------------------------------------------
// Hoisted mocks
// ---------------------------------------------------------------------------

const {
  mockFeatureFlagCheck,
  mockHandleMessage,
  mockStartPollingLoop,
  mockLoadState,
  mockOnboardingIntent,
  mockHandleOnboarding,
  mockHandleOnboardingCallback,
  mockRecordEvidence,
} = vi.hoisted(() => ({
  mockFeatureFlagCheck: vi.fn(),
  mockHandleMessage: vi.fn(),
  mockStartPollingLoop: vi.fn(),
  mockLoadState: vi.fn(),
  mockOnboardingIntent: vi.fn(),
  mockHandleOnboarding: vi.fn(),
  mockHandleOnboardingCallback: vi.fn(),
  mockRecordEvidence: vi.fn(),
}))

vi.mock('@/lib/provisioning/guard', () => ({
  featureFlagCheck: mockFeatureFlagCheck,
}))

vi.mock('@/lib/provisioning/flow', () => ({
  handleMessage: mockHandleMessage,
  startPollingLoop: mockStartPollingLoop,
  loadState: mockLoadState,
}))

vi.mock('@/lib/onboarding/telegram', () => ({
  isOnboardingIntent: mockOnboardingIntent,
  handleTelegramOnboarding: mockHandleOnboarding,
  handleTelegramOnboardingCallback: mockHandleOnboardingCallback,
}))

vi.mock('@/lib/onboarding/bridge', () => ({
  recordOnboardingEvidence: mockRecordEvidence,
}))

import { GET, POST } from './route'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fetchMock = vi.fn()
global.fetch = fetchMock as unknown as typeof fetch

const CAPTAIN_CHAT_ID = '12345678'
const CAPTAIN_CHAT_ID_NUM = 12345678
const WEBHOOK_SECRET = 'wh_secret_token_123'

function setEnv(overrides: Record<string, string | undefined>) {
  for (const [k, v] of Object.entries(overrides)) {
    if (v === undefined) {
      delete process.env[k]
    } else {
      process.env[k] = v
    }
  }
}

function makeUpdate(overrides: {
  chatId?: number
  messageId?: number
  text?: string
  caption?: string
  forwardFrom?: object
  noMessage?: boolean
  callbackQuery?: boolean
}): object {
  if (overrides.noMessage) {
    return { update_id: 1 }
  }
  if (overrides.callbackQuery) {
    return { update_id: 1, callback_query: { id: 'cq1', data: 'test' } }
  }
  const msg: Record<string, unknown> = {
    message_id: overrides.messageId ?? 42,
    chat: { id: overrides.chatId ?? CAPTAIN_CHAT_ID_NUM, type: 'private' },
    from: { id: overrides.chatId ?? CAPTAIN_CHAT_ID_NUM, first_name: 'Ada' },
    date: 1_700_000_000,
  }
  if (overrides.text !== undefined) msg.text = overrides.text
  if (overrides.caption !== undefined) msg.caption = overrides.caption
  if (overrides.forwardFrom !== undefined) msg.forward_from = overrides.forwardFrom
  return { update_id: 1, message: msg }
}

// secretToken defaults to the valid webhook secret so the existing dispatch
// tests pass the transport-auth gate; pass null to omit the header, or a
// wrong string to exercise rejection.
function makeReq(body: unknown, throwOnJson = false, secretToken: string | null = WEBHOOK_SECRET): NextRequest {
  const headers = new Headers()
  if (secretToken !== null) headers.set('x-telegram-bot-api-secret-token', secretToken)
  return {
    headers,
    json: throwOnJson
      ? async () => { throw new SyntaxError('Bad JSON') }
      : async () => body,
  } as unknown as NextRequest
}

// ---------------------------------------------------------------------------
// Default setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockFeatureFlagCheck.mockReset()
  mockHandleMessage.mockReset()
  mockStartPollingLoop.mockReset()
  mockLoadState.mockReset()
  mockOnboardingIntent.mockReset().mockReturnValue(false)
  mockHandleOnboarding.mockReset().mockResolvedValue([])
  mockHandleOnboardingCallback.mockReset().mockResolvedValue([])
  mockRecordEvidence.mockReset().mockResolvedValue({ ok: true })
  fetchMock.mockReset()

  // Feature flag enabled by default
  mockFeatureFlagCheck.mockReturnValue(null)
  // handleMessage returns empty replies by default
  mockHandleMessage.mockResolvedValue([])
  // loadState returns null by default (no polling loop)
  mockLoadState.mockResolvedValue(null)
  // startPollingLoop resolves immediately
  mockStartPollingLoop.mockResolvedValue(undefined)
  // fetch succeeds by default
  fetchMock.mockResolvedValue({ ok: true, text: async () => 'ok' })

  setEnv({
    CAPTAIN_TELEGRAM_ID: undefined,
    CAPTAIN_TELEGRAM_CHAT_ID: CAPTAIN_CHAT_ID,
    TELEGRAM_COS_TOKEN: undefined,
    MANAGER_BOT_TOKEN: 'bot_token_abc',
    TELEGRAM_WEBHOOK_SECRET: WEBHOOK_SECRET,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// GET — health check
// ---------------------------------------------------------------------------

describe('GET provisioning-webhook', () => {
  it('returns 200 with endpoint metadata', async () => {
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.endpoint).toBe('provisioning-webhook')
    expect(typeof body.note).toBe('string')
  })
})

// ---------------------------------------------------------------------------
// POST — feature flag
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — feature flag', () => {
  it('returns flagResponse (503) when feature flag disabled', async () => {
    const { NextResponse } = await import('next/server')
    const flagResp = NextResponse.json({ ok: false, disabled: true }, { status: 503 })
    mockFeatureFlagCheck.mockReturnValueOnce(flagResp)
    const res = await POST(makeReq({ update_id: 1 }))
    expect(res.status).toBe(503)
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// POST — JSON parsing
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — JSON parsing', () => {
  it('returns 200 {ok:true} on invalid JSON (silent drop, no sendMessage)', async () => {
    const res = await POST(makeReq(null, true))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual({ ok: true })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// POST — non-message update
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — non-message updates', () => {
  it('returns 200 ACK on update without message field', async () => {
    const res = await POST(makeReq(makeUpdate({ noMessage: true })))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual({ ok: true })
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })

  it('returns 200 ACK on callback_query update (no message key)', async () => {
    const res = await POST(makeReq(makeUpdate({ callbackQuery: true })))
    expect(res.status).toBe(200)
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// POST — Captain auth guard
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — Captain auth guard', () => {
  it('returns 200 + no sendMessage when CAPTAIN_TELEGRAM_CHAT_ID not set', async () => {
    setEnv({ CAPTAIN_TELEGRAM_CHAT_ID: undefined })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ text: 'hello' })))
    expect(res.status).toBe(200)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mockHandleMessage).not.toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('console.warn emitted when CAPTAIN_TELEGRAM_CHAT_ID not set', async () => {
    setEnv({ CAPTAIN_TELEGRAM_CHAT_ID: undefined })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await POST(makeReq(makeUpdate({ text: 'hello' })))
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('returns 200 + console.warn + no sendMessage for wrong chatId', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ chatId: 99999999, text: 'hello' })))
    expect(res.status).toBe(200)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mockHandleMessage).not.toHaveBeenCalled()
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('proceeds past auth for correct chatId', async () => {
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hello' })))
    expect(mockHandleMessage).toHaveBeenCalled()
  })

  it('uses the canonical CAPTAIN_TELEGRAM_ID without the legacy alias', async () => {
    setEnv({
      CAPTAIN_TELEGRAM_ID: CAPTAIN_CHAT_ID,
      CAPTAIN_TELEGRAM_CHAT_ID: undefined,
    })
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hello' })))
    expect(mockHandleMessage).toHaveBeenCalled()
  })

  it('fails closed when Captain id aliases disagree', async () => {
    setEnv({ CAPTAIN_TELEGRAM_ID: CAPTAIN_CHAT_ID, CAPTAIN_TELEGRAM_CHAT_ID: '99999999' })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hello' })))
    expect(mockHandleMessage).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    errorSpy.mockRestore()
    warnSpy.mockRestore()
  })

  it('rejects a callback_query from a non-Captain chat_id (no dispatch)', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const update = {
      update_id: 5,
      callback_query: { id: 'cq9', data: 'onboard:continue', message: { message_id: 3, chat: { id: 99999999, type: 'private' } } },
    }
    const res = await POST(makeReq(update))
    expect(res.status).toBe(200)
    expect(mockHandleOnboardingCallback).not.toHaveBeenCalled()
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// POST — secret-token transport auth (X-Telegram-Bot-Api-Secret-Token)
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — secret-token transport auth', () => {
  it('rejects with 401 when the secret-token header is absent', async () => {
    const res = await POST(makeReq(makeUpdate({ text: 'hi' }), false, null))
    expect(res.status).toBe(401)
    expect(mockHandleMessage).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects with 401 on a wrong secret token', async () => {
    const res = await POST(makeReq(makeUpdate({ text: 'hi' }), false, 'not-the-secret'))
    expect(res.status).toBe(401)
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })

  it('fails closed with 401 when TELEGRAM_WEBHOOK_SECRET is unset (even with a header)', async () => {
    setEnv({ TELEGRAM_WEBHOOK_SECRET: undefined })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ text: 'hi' })))
    expect(res.status).toBe(401)
    expect(mockHandleMessage).not.toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('dispatches when the secret token matches', async () => {
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(res.status).toBe(200)
    expect(mockHandleMessage).toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// POST — rawText extraction
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — rawText extraction', () => {
  it('returns 200, no dispatch when message has no text and no caption', async () => {
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM })))
    expect(res.status).toBe(200)
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })

  it('returns 200, no dispatch when text is whitespace-only', async () => {
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: '   ' })))
    expect(res.status).toBe(200)
    expect(mockHandleMessage).not.toHaveBeenCalled()
  })

  it('uses text field as rawText', async () => {
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'provision me' })))
    expect(mockHandleMessage).toHaveBeenCalledWith(
      String(CAPTAIN_CHAT_ID_NUM),
      'provision me'
    )
  })

  it('uses caption as rawText when text is absent', async () => {
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, caption: 'forwarded caption' })))
    expect(mockHandleMessage).toHaveBeenCalledWith(
      String(CAPTAIN_CHAT_ID_NUM),
      'forwarded caption'
    )
  })

  it('text takes precedence over caption when both present', async () => {
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'real text', caption: 'caption text' })))
    expect(mockHandleMessage).toHaveBeenCalledWith(
      String(CAPTAIN_CHAT_ID_NUM),
      'real text'
    )
  })
})

describe('POST provisioning-webhook — canonical onboarding skin', () => {
  it('sends with the canonical Chair bot token', async () => {
    setEnv({ TELEGRAM_COS_TOKEN: 'canonical-chair-token', MANAGER_BOT_TOKEN: undefined })
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{ text: 'Orientation', plain: true }])
    await POST(makeReq(makeUpdate({ text: '/onboard' })))
    expect(String(fetchMock.mock.calls[0][0])).toContain('/botcanonical-chair-token/sendMessage')
  })

  it('remains available when multi-Cabinet provisioning is disabled', async () => {
    const { NextResponse } = await import('next/server')
    mockFeatureFlagCheck.mockReturnValueOnce(
      NextResponse.json({ ok: false, disabled: true }, { status: 503 })
    )
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{ text: 'Orientation', plain: true }])
    const response = await POST(makeReq(makeUpdate({ text: '/onboard' })))
    expect(response.status).toBe(200)
    expect(mockHandleOnboarding).toHaveBeenCalled()
  })

  it('routes /onboard to the shared onboarding handler, not provisioning state', async () => {
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{
      text: 'Same canonical card',
      plain: true,
      buttons: [[{ text: 'Continue', callback_data: 'onboard:continue' }]],
    }])
    const response = await POST(makeReq(makeUpdate({ text: '/onboard' })))
    expect(mockHandleOnboarding).toHaveBeenCalledWith('/onboard', 'telegram-update-1')
    expect(mockHandleMessage).not.toHaveBeenCalled()
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(payload.parse_mode).toBeUndefined()
    expect(payload.reply_markup.inline_keyboard[0][0].callback_data).toBe('onboard:continue')
    expect(mockRecordEvidence).toHaveBeenCalledWith(
      expect.objectContaining({ phase: 'transport', status: 'succeeded' }),
      'telegram'
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      ok: true,
      handled: true,
      delivered: true,
      retryable: false,
    })
  })

  it('never writes the Captain source path or purpose to process logs', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    const privateCommand = '/onboard folder /Users/ada/SecretProduct | Prepare acquisition'
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{ text: 'Proposed', plain: true }])

    await POST(makeReq(makeUpdate({ text: privateCommand })))

    const logs = logSpy.mock.calls.map((call) => call.join(' ')).join('\n')
    expect(logs).toContain('[ONBOARDING_COMMAND_REDACTED]')
    expect(logs).not.toContain('/Users/ada/SecretProduct')
    expect(logs).not.toContain('Prepare acquisition')
    logSpy.mockRestore()
  })

  it('does not recreate an evidence trial while delivering a successful typed-purge reply', async () => {
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{ text: 'Purged', plain: true }])
    await POST(makeReq(makeUpdate({ text: '/onboard purge PURGE' })))
    expect(mockRecordEvidence).not.toHaveBeenCalled()
  })

  it('ACKs an authenticated onboarding callback before state work and reply delivery', async () => {
    mockHandleOnboardingCallback.mockResolvedValueOnce([{ text: 'Resolved', plain: true }])
    const update = {
      update_id: 9,
      callback_query: {
        id: 'callback-9',
        from: { id: CAPTAIN_CHAT_ID_NUM, first_name: 'Ada' },
        data: 'onboard:continue',
        message: {
          message_id: 77,
          chat: { id: CAPTAIN_CHAT_ID_NUM, type: 'private' },
          date: 1_700_000_000,
        },
      },
    }
    await POST(makeReq(update))
    expect(mockHandleOnboardingCallback).toHaveBeenCalledWith(
      'onboard:continue',
      'telegram-update-9'
    )
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toContain('/answerCallbackQuery')
    expect(fetchMock.mock.calls[1][0]).toContain('/sendMessage')
    expect(fetchMock.mock.invocationCallOrder[0]).toBeLessThan(
      mockHandleOnboardingCallback.mock.invocationCallOrder[0]
    )
  })

  it('returns explicit retryable failure when the canonical onboarding reply does not land', async () => {
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockResolvedValueOnce([{ text: 'Orientation', plain: true }])
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502 })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const response = await POST(makeReq(makeUpdate({ text: '/onboard' })))

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toMatchObject({
      ok: false,
      handled: true,
      delivered: false,
      delivery_required: true,
      retryable: true,
    })
    errorSpy.mockRestore()
  })

  it('returns retryable failure when an onboarding handler error cannot be reported', async () => {
    mockOnboardingIntent.mockReturnValueOnce(true)
    mockHandleOnboarding.mockRejectedValueOnce(new Error('scan failed'))
    fetchMock.mockRejectedValueOnce(new Error('telegram down'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const response = await POST(makeReq(makeUpdate({ text: '/onboard' })))

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toMatchObject({
      handled: true,
      delivered: false,
      retryable: true,
    })
    errorSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// POST — token redaction in console.log
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — token redaction', () => {
  it('logs [TOKEN_REDACTED] for token-shaped substring in message text', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    const tokenLike = '12345678:ABCDEFGHIJabcdefghij_-12345x67890xy'
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: tokenLike })))
    const logCalls = logSpy.mock.calls.map(c => c.join(' '))
    expect(logCalls.some(msg => msg.includes('[TOKEN_REDACTED]'))).toBe(true)
    expect(logCalls.some(msg => msg.includes('ABCDEFGHIJabcdefghij'))).toBe(false)
    logSpy.mockRestore()
  })

  it('token redaction: exactly 8 digits + colon + 35-char secret matches', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    // Minimum bound: 8 digits + 35-char secret
    const edgeToken = '12345678:' + 'A'.repeat(35)
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: edgeToken })))
    const logCalls = logSpy.mock.calls.map(c => c.join(' '))
    expect(logCalls.some(msg => msg.includes('[TOKEN_REDACTED]'))).toBe(true)
    logSpy.mockRestore()
  })

  it('does NOT redact plain text without token-shaped substring', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'just normal text' })))
    const logCalls = logSpy.mock.calls.map(c => c.join(' '))
    expect(logCalls.some(msg => msg.includes('[TOKEN_REDACTED]'))).toBe(false)
    logSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// POST — handleMessage dispatch and replies
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — handleMessage dispatch', () => {
  it('calls handleMessage with String(chatId) and rawText', async () => {
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hello bot', messageId: 77 })))
    expect(mockHandleMessage).toHaveBeenCalledWith(String(CAPTAIN_CHAT_ID_NUM), 'hello bot')
  })

  it('calls fetch with correct Telegram sendMessage URL for first reply', async () => {
    mockHandleMessage.mockResolvedValueOnce([{ text: 'Reply from bot' }])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'go', messageId: 42 })))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('sendMessage')
    expect(url).toContain('bot_token_abc')
    const parsedBody = JSON.parse(init.body as string)
    expect(parsedBody.chat_id).toBe(CAPTAIN_CHAT_ID_NUM)
    expect(parsedBody.text).toBe('Reply from bot')
    expect(parsedBody.reply_to_message_id).toBe(42)
  })

  it('first reply threads with replyToMessageId; subsequent replies have no reply_to', async () => {
    mockHandleMessage.mockResolvedValueOnce([
      { text: 'First reply' },
      { text: 'Second reply' },
    ])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'go', messageId: 55 })))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const firstBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    const secondBody = JSON.parse(fetchMock.mock.calls[1][1].body)
    expect(firstBody.reply_to_message_id).toBe(55)
    expect(secondBody.reply_to_message_id).toBeUndefined()
  })

  it('sends additional chained messages on a reply', async () => {
    mockHandleMessage.mockResolvedValueOnce([
      {
        text: 'Main reply',
        additional: [{ text: 'Chained 1' }, { text: 'Chained 2' }],
      },
    ])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'multi', messageId: 10 })))
    // First reply + 2 additional = 3 fetch calls
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('no fetch call when replies array is empty', async () => {
    mockHandleMessage.mockResolvedValueOnce([])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends generic error reply when handleMessage throws', async () => {
    mockHandleMessage.mockRejectedValueOnce(new Error('state machine exploded'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'crash' })))
    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.text).toMatch(/wrong|cancel/i)
    errorSpy.mockRestore()
  })

  it('still returns 200 when handleMessage throws', async () => {
    mockHandleMessage.mockRejectedValueOnce(new Error('boom'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'crash' })))
    expect(res.status).toBe(200)
    errorSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// POST — sendTelegramMessage internals
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — sendTelegramMessage internals', () => {
  it('logs error and skips fetch when MANAGER_BOT_TOKEN not set', async () => {
    setEnv({ MANAGER_BOT_TOKEN: undefined })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockHandleMessage.mockResolvedValueOnce([{ text: 'some reply' }])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('logs error when fetch response is not ok', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, text: async () => 'Bad Request' })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockHandleMessage.mockResolvedValueOnce([{ text: 'reply' }])
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(res.status).toBe(200)
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('logs error when fetch throws', async () => {
    fetchMock.mockRejectedValueOnce(new Error('ECONNREFUSED'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockHandleMessage.mockResolvedValueOnce([{ text: 'reply' }])
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(res.status).toBe(200)
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('truncates text longer than 4096 chars to 4093 + ellipsis', async () => {
    const longText = 'x'.repeat(5000)
    mockHandleMessage.mockResolvedValueOnce([{ text: longText }])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'trigger' })))
    const sentBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(sentBody.text.length).toBe(4094) // 4093 + 1 for '…' (1 char)
    expect(sentBody.text.endsWith('…')).toBe(true)
  })

  it('does NOT truncate text of exactly 4096 chars', async () => {
    const exactText = 'y'.repeat(4096)
    mockHandleMessage.mockResolvedValueOnce([{ text: exactText }])
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'trigger' })))
    const sentBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(sentBody.text.length).toBe(4096)
    expect(sentBody.text.endsWith('…')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// POST — polling loop fire-and-forget
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — polling loop', () => {
  it('does not call startPollingLoop when loadState returns null', async () => {
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce(null)
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(mockStartPollingLoop).not.toHaveBeenCalled()
  })

  it('does not call startPollingLoop when step != polling_status', async () => {
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce({ step: 'adopting_bot', cabinetId: 'cab_abc' })
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(mockStartPollingLoop).not.toHaveBeenCalled()
  })

  it('does not call startPollingLoop when step=polling_status but cabinetId is null', async () => {
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce({ step: 'polling_status', cabinetId: null })
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    expect(mockStartPollingLoop).not.toHaveBeenCalled()
  })

  it('calls startPollingLoop with chatId/state/callback when step=polling_status + cabinetId set', async () => {
    const state = { step: 'polling_status', cabinetId: 'cab_xyz' }
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce(state)
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'all bots adopted' })))
    expect(mockStartPollingLoop).toHaveBeenCalledWith(
      String(CAPTAIN_CHAT_ID_NUM),
      state,
      expect.any(Function)
    )
  })

  it('still returns 200 when startPollingLoop rejects (fire-and-forget catch)', async () => {
    const state = { step: 'polling_status', cabinetId: 'cab_xyz' }
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce(state)
    mockStartPollingLoop.mockRejectedValueOnce(new Error('polling exploded'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'go' })))
    expect(res.status).toBe(200)
    errorSpy.mockRestore()
  })

  it('polling callback calls sendTelegramMessage (fetch) with message text', async () => {
    const state = { step: 'polling_status', cabinetId: 'cab_xyz' }
    mockHandleMessage.mockResolvedValueOnce([])
    mockLoadState.mockResolvedValueOnce(state)
    await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'go' })))
    // Retrieve the callback passed to startPollingLoop and call it
    const callback = mockStartPollingLoop.mock.calls[0][2] as (msg: { text: string }) => Promise<void>
    await callback({ text: 'Cabinet is live!' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const sentBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(sentBody.text).toBe('Cabinet is live!')
    expect(sentBody.chat_id).toBe(CAPTAIN_CHAT_ID_NUM)
  })
})

// ---------------------------------------------------------------------------
// POST — legacy provisioning always-200 invariant
// ---------------------------------------------------------------------------

describe('POST provisioning-webhook — legacy provisioning always-200', () => {
  it('returns 200 even on complete internal failure cascade', async () => {
    mockHandleMessage.mockRejectedValueOnce(new Error('catastrophic'))
    fetchMock.mockRejectedValueOnce(new Error('network down'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'go' })))
    expect(res.status).toBe(200)
    errorSpy.mockRestore()
  })

  it('response body always contains {ok: true}', async () => {
    const res = await POST(makeReq(makeUpdate({ chatId: CAPTAIN_CHAT_ID_NUM, text: 'hi' })))
    const body = await res.json()
    expect(body.ok).toBe(true)
  })
})
