import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, applyMock, recordMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  applyMock: vi.fn(),
  recordMock: vi.fn(),
}))

vi.mock('./bridge', () => {
  class OnboardingBridgeError extends Error {
    constructor(public readonly code: string, message: string) {
      super(message)
    }
  }
  return {
    getOnboarding: getMock,
    applyOnboardingAction: applyMock,
    recordOnboardingEvidence: recordMock,
    OnboardingBridgeError,
  }
})

import {
  formatTelegramOnboarding,
  handleTelegramOnboarding,
  handleTelegramOnboardingCallback,
  isOnboardingIntent,
} from './telegram'

const WELCOME = {
  ok: true,
  state: {
    schema: 'cabinet.onboarding-journey/v2',
    journey_id: 'journey-1',
    revision: 0,
    stage: 'welcome',
    purpose: null,
    relationship_destination: null,
    orientation_mode: 'observe_only',
    access: 'not_granted',
    source: null,
    charter: null,
    first_dividend: null,
    created_at: 'x',
    updated_at: 'x',
  },
  card: {
    schema: 'cabinet.onboarding-card/v1',
    id: 'onboarding:journey-1:welcome',
    journey_id: 'journey-1',
    revision: 0,
    stage: 'welcome',
    kind: 'first_window',
    title: 'Let me earn my first responsibility',
    body: 'Choose one folder. Nothing is opened until you approve.',
    status: 'open',
    evidence: [],
    options: [{ action: 'propose_window', label: 'Choose a folder' }],
  },
} as const

beforeEach(() => {
  getMock.mockReset().mockResolvedValue(WELCOME)
  applyMock.mockReset().mockResolvedValue(WELCOME)
  recordMock.mockReset().mockResolvedValue({ ok: true })
})

describe('Telegram onboarding intent', () => {
  it('is explicit and does not steal normal Cabinet messages', () => {
    expect(isOnboardingIntent('/onboard')).toBe(true)
    expect(isOnboardingIntent('orientation status')).toBe(true)
    expect(isOnboardingIntent('please deploy the release')).toBe(false)
  })

  it('renders the canonical card id and offers NO one-tap folder button', () => {
    // INVERTED 2026-07-27 by the ownership ceiling. The three Documents
    // buttons used to act. A tap cannot carry whose data the folder is, and
    // the core refuses an unclassified source, so a button here would be a
    // dead end that reads like an offer. The typed form is the only path.
    const message = formatTelegramOnboarding(WELCOME as never)
    expect(message.plain).toBe(true)
    expect(message.text).toContain(WELCOME.card.id)
    expect(message.text).toContain('destination, not an authority grant')
    expect(message.text).toContain('mine, employer, or client')
    expect(message.buttons?.flat() ?? []).toEqual([])
  })

  it('renders a purged journey as terminal and offers no stale action', () => {
    const purged = {
      ...WELCOME,
      state: { ...WELCOME.state, stage: 'purged' },
      card: {
        ...WELCOME.card,
        stage: 'purged',
        status: 'complete',
        title: 'Onboarding data was deleted',
        body: 'The Charter, history, and live evidence trial were removed.',
        options: [],
      },
    }
    const message = formatTelegramOnboarding(purged as never)
    expect(message.buttons).toEqual([])
    expect(message.text).toContain('No action from an older Dashboard')
    expect(message.text).not.toContain('Choose a Documents option')
  })
})

describe('Telegram standalone journey', () => {
  it('shows current state without creating Telegram shadow state', async () => {
    const messages = await handleTelegramOnboarding('/onboard', 'tg-1')
    expect(getMock).toHaveBeenCalledTimes(1)
    expect(applyMock).not.toHaveBeenCalled()
    expect(messages[0].text).toContain(WELCOME.card.id)
  })

  it('answers a legacy Documents callback with the question instead of acting', async () => {
    // INVERTED 2026-07-27: acting on this callback would read a folder whose
    // ownership class nobody declared. A stale button from an older message
    // must not become an unclassified read.
    const reply = await handleTelegramOnboardingCallback('onboard:documents:reversible', 'tg-2')
    expect(applyMock).not.toHaveBeenCalled()
    expect(reply[0].text).toContain('mine, employer, or client')
  })

  it('carries the declared ownership and basis into the canonical action', async () => {
    await handleTelegramOnboarding(
      '/onboard folder /Users/ada/work | find the next risk | employer: read access granted to my seat',
      'tg-own'
    )
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'propose_window',
        source: '/Users/ada/work',
        purpose: 'find the next risk',
        ownership: 'employer',
        authority_basis: 'read access granted to my seat',
      }),
      'telegram'
    )
  })

  it('sends no ownership at all when the operator declared none', async () => {
    // The surface must not invent a class to make the core accept the action;
    // the core's refusal is the correct outcome.
    await handleTelegramOnboarding('/onboard folder /Users/ada/work | find the next risk', 'tg-bare')
    const [payload] = applyMock.mock.calls[0]
    expect(payload.ownership).toBeUndefined()
    expect(payload.authority_basis).toBeUndefined()
  })

  it('withholds nothing itself but renders the core egress verdict', () => {
    const withheld = {
      ...WELCOME,
      card: {
        ...WELCOME.card,
        stage: 'dividend_ready',
        evidence: [{ path: 'a/b.md', line: 4, excerpt: '[withheld]', sha256: 'x' }],
        egress: {
          ownership: 'third_party',
          disposition: 'per_item_approval',
          items: 1,
          withheld: 1,
          approved: [],
        },
      },
    }
    const message = formatTelegramOnboarding(withheld as never)
    expect(message.text).toContain('holding back the words of 1 of 1')
    expect(message.text).toContain('a/b.md:4')
  })

  it('accepts a custom folder and purpose without technical connector terms', async () => {
    await handleTelegramOnboarding(
      '/onboard folder /Users/ada/Client Work | find the next delivery risk | sovereign',
      'tg-3'
    )
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source: '/Users/ada/Client Work',
        purpose: 'find the next delivery risk',
        relationship_destination: 'sovereign',
      }),
      'telegram'
    )
  })

  it('can select earn-every-step from Telegram without granting authority', async () => {
    await handleTelegramOnboarding(
      '/onboard documents | keep me ahead | mine: my own laptop | earn',
      'tg-earn'
    )
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source: '~/Documents',
        relationship_destination: 'earn',
        ownership: 'self',
        authority_basis: 'my own laptop',
      }),
      'telegram'
    )
  })

  it('requires typed PURGE and never offers a one-tap destructive callback', async () => {
    const prompt = await handleTelegramOnboardingCallback('onboard:purge_prompt', 'tg-4')
    expect(prompt[0].text).toContain('/onboard purge PURGE')
    expect(applyMock).not.toHaveBeenCalled()
    await handleTelegramOnboarding('/onboard purge PURGE', 'tg-5')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'purge', confirmation: 'PURGE' }),
      'telegram'
    )
  })

  it('records usefulness feedback through the bounded observation seam', async () => {
    const reply = await handleTelegramOnboardingCallback('onboard:feedback:useful', 'tg-feedback')
    expect(recordMock).toHaveBeenCalledWith(
      expect.objectContaining({ phase: 'feedback', status: 'useful' }),
      'telegram'
    )
    expect(reply[0].text).toContain('Feedback recorded')
  })
})
