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

  it('renders the canonical card id and all three destination choices', () => {
    const message = formatTelegramOnboarding(WELCOME as never)
    expect(message.plain).toBe(true)
    expect(message.text).toContain(WELCOME.card.id)
    expect(message.text).toContain('destination, not an authority grant')
    expect(message.buttons?.flat().map((button) => button.callback_data)).toEqual([
      'onboard:documents:reversible',
      'onboard:documents:earn',
      'onboard:documents:sovereign',
    ])
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

  it('turns the Documents button into the same canonical propose action', async () => {
    await handleTelegramOnboardingCallback('onboard:documents:reversible', 'tg-2')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'propose_window',
        action_id: 'tg-2',
        source: '~/Documents',
        relationship_destination: 'reversible',
      }),
      'telegram'
    )
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
    await handleTelegramOnboardingCallback('onboard:documents:earn', 'tg-earn')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        source: '~/Documents',
        relationship_destination: 'earn',
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
