/**
 * The guided Telegram connect, END TO END against a fixture Telegram.
 *
 * WHAT IS REAL HERE: the actions, the safe `.env` writer, the YAML line editor,
 * the capture reader, and a socket standing in for api.telegram.org that records
 * every request. WHAT IS MOCKED: the session check (so the unauthenticated arm
 * can be exercised) and `revalidatePath`.
 *
 * WHY NO REAL BOT. Creating one is an account action against a third party in
 * the Captain's name. The mechanical flow is proven here; the live halves
 * (Telegram accepting a real token, a message landing on a real phone) are
 * proven once by the Captain's own connect.
 *
 * THE FOUR QUESTIONS, held against every arm below:
 *   - would this arm FAIL against code that did the wrong thing? Each one names
 *     the wrong thing it is watching for.
 *   - what happens at the DEGENERATE end — no messages, no token, no answers
 *     file, a send that fails? All four are arms, and none of them may report
 *     success.
 *   - what does the test environment guarantee that production does not? Only
 *     the host: everything else (file layout, writers, parsing) is the real code
 *     against real files in a temp tree.
 *   - is the sensor wired to the live artifact? The writes are asserted by
 *     READING THE FILES BACK, not by trusting a returned flag.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import nodePath from 'node:path'
import yaml from 'js-yaml'

const { mockVerify, mockWriteGuard } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockWriteGuard: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/docker', () => ({
  assertRuntimeWritesAllowed: mockWriteGuard,
  dockerExec: vi.fn(),
  getEnvVars: vi.fn(),
}))

import {
  confirmChatAndSend,
  getTelegramStatus,
  listenForFirstMessage,
  verifyBotToken,
} from './telegram-connect'
import { CONNECTED_MESSAGE } from '@/lib/telegram/contract'
import {
  FAKE_TOKEN,
  groupMessage,
  privateMessage,
  startMockTelegram,
  type MockTelegram,
} from '@/lib/telegram/mock-telegram'

const PLATFORM_BEFORE = `# generated-by: cabinet-init
captain_name: Captain
captain_timezone: UTC
captain_telegram_chat_id: "0000"

communication:
  briefing_frequency: daily
`

const ANSWERS_BEFORE = `# generated-by: cabinet-init — DEFAULTS fast lane.
version: 1

captain:
  name: Captain
  timezone: UTC                  # placeholder
  telegram_chat_id: "0000"       # placeholder address (not a secret)

cabinet:
  id: main
`

let root = ''
let telegram: MockTelegram

const envPath = () => nodePath.join(root, 'cabinet', '.env')
const platformPath = () => nodePath.join(root, 'instance', 'config', 'platform.yml')
const answersPath = () =>
  nodePath.join(root, 'instance', 'config', 'cabinet-init.answers.yml')
const read = (p: string) => readFileSync(p, 'utf8')

function makeRoot({ withAnswers = true, withEnv = true } = {}): void {
  root = mkdtempSync(nodePath.join(tmpdir(), 'telegram-connect-'))
  mkdirSync(nodePath.join(root, 'cabinet'), { recursive: true })
  mkdirSync(nodePath.join(root, 'instance', 'config'), { recursive: true })
  if (withEnv) writeFileSync(envPath(), 'EXISTING_KEY=already-here\n', { mode: 0o600 })
  writeFileSync(platformPath(), PLATFORM_BEFORE)
  if (withAnswers) writeFileSync(answersPath(), ANSWERS_BEFORE)
  vi.stubEnv('CABINET_ROOT', root)
  vi.stubEnv('CABINET_ENV_PATH', envPath())
  vi.stubEnv('PLATFORM_PATH', platformPath())
  vi.stubEnv('CABINET_ANSWERS_PATH', answersPath())
  if (!envPath().startsWith(root + nodePath.sep)) {
    throw new Error('refusing to run: the env-file path is outside the temp tree')
  }
}

/** The happy Telegram: a named bot, one message from one person, sends land. */
function friendlyTelegram(chatId = 4242424242): void {
  telegram.reply('getMe', () => ({
    body: { ok: true, result: { id: 7, username: 'ada_hq_bot', first_name: 'Ada HQ' } },
  }))
  telegram.reply('getUpdates', () => ({
    body: { ok: true, result: [privateMessage(chatId, { username: 'ada' })] },
  }))
  telegram.reply('sendMessage', () => ({ body: { ok: true, result: { message_id: 9 } } }))
}

beforeEach(async () => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockVerify.mockResolvedValue(true)
  telegram = await startMockTelegram()
  makeRoot()
  vi.stubEnv('TELEGRAM_API_BASE', telegram.base)
})

afterEach(async () => {
  vi.unstubAllEnvs()
  if (root) rmSync(root, { recursive: true, force: true })
  root = ''
  await telegram.close()
})

// ---------------------------------------------------------------------------
// The gate. Server Actions are global POST endpoints; middleware never covers
// action dispatch, so an unauthenticated caller must reach NO network call and
// NO write.
// ---------------------------------------------------------------------------

describe('unauthenticated — refused before anything happens', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('getTelegramStatus throws rather than reporting a cabinet it did not read', async () => {
    await expect(getTelegramStatus()).rejects.toThrow('Unauthorized')
  })

  it('verifyBotToken makes no call to Telegram and stores nothing', async () => {
    friendlyTelegram()
    const result = await verifyBotToken(FAKE_TOKEN)
    expect(result).toEqual({ ok: false, error: 'Unauthorized' })
    expect(telegram.calls).toEqual([])
    expect(read(envPath())).not.toContain('TELEGRAM_COS_TOKEN')
  })

  it('listenForFirstMessage reads nothing', async () => {
    friendlyTelegram()
    expect(await listenForFirstMessage()).toEqual({ ok: false, error: 'Unauthorized' })
    expect(telegram.calls).toEqual([])
  })

  it('confirmChatAndSend sends nothing and writes nothing', async () => {
    friendlyTelegram()
    const result = await confirmChatAndSend('4242424242')
    expect(result).toEqual({ ok: false, delivered: false, error: 'Unauthorized' })
    expect(telegram.calls).toEqual([])
    expect(read(platformPath())).toContain('captain_telegram_chat_id: "0000"')
  })
})

// ---------------------------------------------------------------------------
// Step 2 — the token.
// ---------------------------------------------------------------------------

describe('verifyBotToken — proven with Telegram BEFORE it is stored', () => {
  it('stores the token only after getMe accepts it, and names the bot', async () => {
    friendlyTelegram()
    const result = await verifyBotToken(FAKE_TOKEN)
    expect(result).toMatchObject({ ok: true, botUsername: 'ada_hq_bot', botName: 'Ada HQ' })
    expect(read(envPath())).toContain(`TELEGRAM_COS_TOKEN=${FAKE_TOKEN}`)
    // The existing file is edited, never replaced.
    expect(read(envPath())).toContain('EXISTING_KEY=already-here')
  })

  it('a REFUSED token is never written — the file stays as it was', async () => {
    telegram.reply('getMe', () => ({
      status: 401,
      body: { ok: false, description: 'Unauthorized' },
    }))
    const result = await verifyBotToken(FAKE_TOKEN)
    expect(result.ok).toBe(false)
    expect(result.error).toContain('did not work')
    expect(read(envPath())).not.toContain('TELEGRAM_COS_TOKEN')
  })

  it('a token-shaped nothing is refused without spending a call', async () => {
    friendlyTelegram()
    expect((await verifyBotToken('   ')).error).toContain('Paste the token')
    expect((await verifyBotToken('4242424242')).error).toContain('does not look like a bot token')
    expect(telegram.calls).toEqual([])
  })

  it('an unreachable Telegram stores nothing and says what to do', async () => {
    vi.stubEnv('TELEGRAM_API_BASE', 'http://127.0.0.1:1')
    const result = await verifyBotToken(FAKE_TOKEN)
    expect(result.error).toContain('could not reach Telegram')
    expect(read(envPath())).not.toContain('TELEGRAM_COS_TOKEN')
  })

  it('creates cabinet/.env when a fresh hatch has none yet', async () => {
    rmSync(envPath())
    friendlyTelegram()
    expect((await verifyBotToken(FAKE_TOKEN)).ok).toBe(true)
    expect(read(envPath())).toContain(`TELEGRAM_COS_TOKEN=${FAKE_TOKEN}`)
  })
})

// ---------------------------------------------------------------------------
// Step 3 — the capture.
// ---------------------------------------------------------------------------

describe('listenForFirstMessage — the capture, and its empty ends', () => {
  beforeEach(async () => {
    friendlyTelegram()
    await verifyBotToken(FAKE_TOKEN)
  })

  it('captures the first private sender with a name to confirm', async () => {
    const result = await listenForFirstMessage()
    expect(result.ok).toBe(true)
    expect(result.candidate).toEqual({ chatId: '4242424242', label: '@ada' })
    expect(result.others).toEqual([])
  })

  it('an empty window is an honest nothing, never a fabricated address', async () => {
    telegram.reply('getUpdates', () => ({ body: { ok: true, result: [] } }))
    const result = await listenForFirstMessage()
    expect(result).toMatchObject({ ok: true, groupOnly: false })
    expect(result.candidate).toBeUndefined()
  })

  it('two senders: the first is offered, the rest are surfaced', async () => {
    telegram.reply('getUpdates', () => ({
      body: {
        ok: true,
        result: [
          privateMessage(111111, { username: 'ada' }),
          privateMessage(222222, { username: 'stranger' }),
        ],
      },
    }))
    const result = await listenForFirstMessage()
    expect(result.candidate?.chatId).toBe('111111')
    expect(result.others).toEqual([{ chatId: '222222', label: '@stranger' }])
  })

  it('a group-only window offers nothing and says it is a group', async () => {
    telegram.reply('getUpdates', () => ({
      body: { ok: true, result: [groupMessage(-1001234567890)] },
    }))
    const result = await listenForFirstMessage()
    expect(result.candidate).toBeUndefined()
    expect(result.groupOnly).toBe(true)
  })

  it('another reader holding the token is named as a conflict', async () => {
    telegram.reply('getUpdates', () => ({ status: 409, body: { ok: false } }))
    const result = await listenForFirstMessage()
    expect(result.ok).toBe(false)
    expect(result.error).toContain('already reading this bot')
  })

  it('with no token stored, it says so instead of calling Telegram', async () => {
    writeFileSync(envPath(), 'EXISTING_KEY=already-here\n')
    const before = telegram.calls.length
    const result = await listenForFirstMessage()
    expect(result.error).toContain('No bot token is stored')
    expect(telegram.calls.length).toBe(before)
  })
})

// ---------------------------------------------------------------------------
// Step 4 — the round trip, and where the address lands.
// ---------------------------------------------------------------------------

describe('confirmChatAndSend — send first, then record', () => {
  beforeEach(async () => {
    friendlyTelegram()
    await verifyBotToken(FAKE_TOKEN)
  })

  it('sends exactly one message, with the exact words the screen shows', async () => {
    const before = telegram.calls.length
    const result = await confirmChatAndSend('4242424242')
    expect(result).toMatchObject({ ok: true, delivered: true, message: CONNECTED_MESSAGE })
    const sends = telegram.calls.slice(before).filter((c) => c.apiMethod === 'sendMessage')
    expect(sends).toHaveLength(1)
    expect(sends[0].body).toEqual({ chat_id: '4242424242', text: CONNECTED_MESSAGE })
  })

  it('the address lands in all three places the cabinet reads', async () => {
    await confirmChatAndSend('4242424242')
    expect(read(envPath())).toContain('CAPTAIN_TELEGRAM_ID=4242424242')
    const platform = yaml.load(read(platformPath())) as Record<string, unknown>
    expect(String(platform.captain_telegram_chat_id)).toBe('4242424242')
    const answers = yaml.load(read(answersPath())) as { captain: Record<string, unknown> }
    expect(String(answers.captain.telegram_chat_id)).toBe('4242424242')
  })

  it('the generated key and the answer it is derived from AGREE — a regenerate cannot undo this', async () => {
    // THE CLOBBER GUARD. `cabinet/scripts/generate-instance.py` re-stamps
    // platform.yml's captain_telegram_chat_id FROM answers.captain.telegram_chat_id
    // on every run. Writing platform.yml alone would be a hand-edit of a
    // generator output that the next regenerate silently reverts to "0000" —
    // the cabinet would go quiet with nothing on screen to say why. The other
    // half of this proof runs the real generator:
    // cabinet/scripts/tests/test_telegram_chat_id_survives_regenerate.py
    await confirmChatAndSend('4242424242')
    const platform = yaml.load(read(platformPath())) as Record<string, unknown>
    const answers = yaml.load(read(answersPath())) as { captain: Record<string, unknown> }
    expect(String(platform.captain_telegram_chat_id)).toBe(
      String(answers.captain.telegram_chat_id)
    )
  })

  it('writes the generator\'s own bytes — a QUOTED scalar, so a regenerate is a no-op', async () => {
    // `render_platform` in generate-instance.py emits
    // `captain_telegram_chat_id: "12345678"`. An id is plain-safe YAML, so the
    // line editor would otherwise write it bare and it would load back as an
    // INT — legal, readable, and a different type depending on which of the two
    // writers went last.
    await confirmChatAndSend('4242424242')
    expect(read(platformPath())).toContain('captain_telegram_chat_id: "4242424242"')
    expect(read(answersPath())).toContain('telegram_chat_id: "4242424242"')
    const platform = yaml.load(read(platformPath())) as Record<string, unknown>
    expect(typeof platform.captain_telegram_chat_id).toBe('string')
  })

  it('the edit is surgical — comments and every other key survive', async () => {
    await confirmChatAndSend('4242424242')
    expect(read(answersPath())).toContain('# generated-by: cabinet-init')
    expect(read(answersPath())).toContain('name: Captain')
    expect(read(platformPath())).toContain('briefing_frequency: daily')
  })

  it('a send that FAILS records nothing at all', async () => {
    telegram.reply('sendMessage', () => ({
      status: 400,
      body: { ok: false, description: 'chat not found' },
    }))
    const result = await confirmChatAndSend('4242424242')
    expect(result).toMatchObject({ ok: false, delivered: false })
    expect(read(envPath())).not.toContain('CAPTAIN_TELEGRAM_ID')
    expect(read(platformPath())).toContain('captain_telegram_chat_id: "0000"')
    expect(read(answersPath())).toContain('telegram_chat_id: "0000"')
  })

  it('an address that is not an address is refused before the send', async () => {
    const before = telegram.calls.length
    for (const bad of ['', 'abc', '12', '  ', '4242424242; rm -rf /']) {
      const result = await confirmChatAndSend(bad)
      expect(result).toMatchObject({ ok: false, delivered: false })
    }
    expect(telegram.calls.length).toBe(before)
  })

  it('no answers file is a NOTE, not a silent success', async () => {
    rmSync(answersPath())
    const result = await confirmChatAndSend('4242424242')
    expect(result.delivered).toBe(true)
    expect(result.notes?.join(' ')).toContain('no setup-interview file')
    // The runtime half still landed, which is what makes the note honest
    // rather than a failure in disguise.
    expect(read(envPath())).toContain('CAPTAIN_TELEGRAM_ID=4242424242')
  })

  it('a platform file with no such key gets it appended rather than refusing', async () => {
    writeFileSync(platformPath(), 'captain_name: Captain\n')
    await confirmChatAndSend('4242424242')
    const platform = yaml.load(read(platformPath())) as Record<string, unknown>
    expect(String(platform.captain_telegram_chat_id)).toBe('4242424242')
  })

  it('a negative (group) address is accepted — some operators want the room', async () => {
    const result = await confirmChatAndSend('-1001234567890')
    expect(result.delivered).toBe(true)
    expect(read(envPath())).toContain('CAPTAIN_TELEGRAM_ID=-1001234567890')
  })
})

// ---------------------------------------------------------------------------
// Status, and the secret.
// ---------------------------------------------------------------------------

describe('getTelegramStatus — presence, never the value', () => {
  it('reports nothing configured on a fresh hatch', async () => {
    expect(await getTelegramStatus()).toEqual({
      tokenStored: false,
      chatId: null,
      connected: false,
    })
  })

  it('reports connected once both halves are stored, and shows the address', async () => {
    friendlyTelegram()
    await verifyBotToken(FAKE_TOKEN)
    await confirmChatAndSend('4242424242')
    expect(await getTelegramStatus()).toEqual({
      tokenStored: true,
      chatId: '4242424242',
      connected: true,
    })
  })

  it('a placeholder address is not an address', async () => {
    writeFileSync(envPath(), 'CAPTAIN_TELEGRAM_ID=\nTELEGRAM_COS_TOKEN=x\n')
    const status = await getTelegramStatus()
    expect(status.chatId).toBeNull()
    expect(status.connected).toBe(false)
  })

  it('an absent .env is an honest empty, not a crash', async () => {
    rmSync(envPath())
    expect(await getTelegramStatus()).toEqual({
      tokenStored: false,
      chatId: null,
      connected: false,
    })
  })

  it('NEVER returns the token, in any shape', async () => {
    friendlyTelegram()
    await verifyBotToken(FAKE_TOKEN)
    expect(JSON.stringify(await getTelegramStatus())).not.toContain(FAKE_TOKEN)
    expect(JSON.stringify(await getTelegramStatus())).not.toContain(FAKE_TOKEN.slice(-8))
  })
})

describe('the token cannot leak through a result or a log', () => {
  it('no action returns it, on any path, and nothing prints it', async () => {
    const spies = (['log', 'error', 'warn', 'info', 'debug'] as const).map((name) =>
      vi.spyOn(console, name).mockImplementation(() => {})
    )
    try {
      // A path that succeeds…
      friendlyTelegram()
      const ok = await verifyBotToken(FAKE_TOKEN)
      const listened = await listenForFirstMessage()
      const confirmed = await confirmChatAndSend('4242424242')

      // …and a path where Telegram quotes the token-bearing URL straight back.
      telegram.reply('getMe', () => ({
        status: 401,
        body: {
          ok: false,
          description: `Unauthorized for https://api.telegram.org/bot${FAKE_TOKEN}/getMe`,
        },
      }))
      const refused = await verifyBotToken(FAKE_TOKEN)
      telegram.reply('sendMessage', () => ({
        status: 400,
        body: { ok: false, description: `no chat for /bot${FAKE_TOKEN}/sendMessage` },
      }))
      const sendFailed = await confirmChatAndSend('4242424242')

      for (const result of [ok, listened, confirmed, refused, sendFailed]) {
        expect(JSON.stringify(result)).not.toContain(FAKE_TOKEN)
        expect(JSON.stringify(result)).not.toContain(FAKE_TOKEN.split(':')[1])
      }
      for (const spy of spies) {
        const printed = spy.mock.calls.flat().map(String).join(' ')
        expect(printed).not.toContain(FAKE_TOKEN)
      }
    } finally {
      spies.forEach((spy) => spy.mockRestore())
    }
  })

  it('the stored token is safe-quoted, so cabinet/.env can never execute it', async () => {
    friendlyTelegram()
    await verifyBotToken(FAKE_TOKEN)
    const line = read(envPath())
      .split('\n')
      .find((l) => l.startsWith('TELEGRAM_COS_TOKEN='))
    expect(line).toBeDefined()
    expect(line).not.toMatch(/[$`(){}]/)
  })
})
