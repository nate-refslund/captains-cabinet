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

import { OnboardingBridgeError } from './bridge'
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

  // A tap carries no words, so the core marks this option `input: 'seed'` and
  // Telegram must answer the seed question with a TYPED command instead. Without
  // one the question prints here and the operator has no way to answer it —
  // the dead end the whole seed path exists to close.
  it('answers the seed question through a typed command, never a button', async () => {
    applyMock.mockResolvedValue(WELCOME)
    await handleTelegramOnboarding('/onboard seed I look after payments releases', 'tg-seed')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'answer_seed',
        seed: 'I look after payments releases',
      }),
      'telegram'
    )
    const rendered = formatTelegramOnboarding({
      ...WELCOME,
      card: {
        ...WELCOME.card,
        stage: 'orientation_offered',
        options: [
          { action: 'answer_seed', label: 'Tell me in a sentence', input: 'seed' },
          { action: 'pause', label: 'Pause here' },
        ],
      },
    } as never)
    const actions = (rendered.buttons || []).flat().map((button) => button.callback_data)
    expect(actions).toEqual(['onboard:pause'])
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

// ---------------------------------------------------------------------------
// THE TWO ACTIONS THE COMMAND TABLE DID NOT CARRY.
//
// journey.py said so in its own source: "no shipped surface can send
// answer_salience yet — it is absent from the Dashboard bridge's action set and
// from the Telegram command table". A card printing candidates on a channel
// with no command able to send one is a dead end wearing an invitation's
// clothes, and parity.test.ts now fails whenever a new one appears.
// ---------------------------------------------------------------------------

const RANKED = {
  ...WELCOME,
  card: {
    ...WELCOME.card,
    options: [
      { action: 'propose_window', label: 'Choose a folder' },
      { action: 'gather_connectors', label: "Read what I'm connected to" },
      {
        action: 'answer_salience',
        label: 'Point me at the one to open first',
        input: 'choice',
        options: [
          { id: 'blueharbour', label: 'blueharbour', why: 'repo: blue-harbour; tracker: Blue Harbour plan' },
          { id: 'other', label: 'None of these — I will name it', why: 'a name you type beats a name I guessed', input: 'seed' },
        ],
        not_reached: 'two workspaces refused the read',
      },
    ],
  },
}

describe('Telegram — the ranked question', () => {
  it('prints the candidates AS COMMANDS, since the channel has no picker', () => {
    const message = formatTelegramOnboarding(RANKED as never)
    expect(message.text).toContain('/onboard salience blueharbour')
    expect(message.text).toContain('repo: blue-harbour')
    expect(message.text).toContain('/onboard salience other <what to open instead>')
  })

  it('never offers it as a TAP — a tap carries no choice', () => {
    // Read past the welcome stage, which returns no buttons at all by design
    // (an ownership class cannot ride a tap), so the assertion is about the
    // callback table rather than about that early return.
    const offered = {
      ...RANKED,
      state: { ...RANKED.state, stage: 'orientation_offered' },
      card: { ...RANKED.card, stage: 'orientation_offered' },
    }
    const taps = (formatTelegramOnboarding(offered as never).buttons || [])
      .flat()
      .map((button) => button.callback_data)
    expect(taps).not.toContain('onboard:salience')
    // The sweep is the one discovery action a tap MAY carry: it is payload-free
    // by construction, so a tap can start it and can never widen it.
    expect(taps).toContain('onboard:gather')
  })

  it('sends a ranked pick to the core', async () => {
    await handleTelegramOnboarding('/onboard salience blueharbour', 'tg-sal')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'answer_salience', choice: 'blueharbour' }),
      'telegram'
    )
  })

  it('sends the escape hatch with the rest of the line as the name', async () => {
    await handleTelegramOnboarding('/onboard salience other Harbour Yard', 'tg-esc')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'answer_salience', choice: 'other', name: 'Harbour Yard' }),
      'telegram'
    )
  })

  it('does not invent a choice for a bare command — the core names what is missing', async () => {
    await handleTelegramOnboarding('/onboard salience', 'tg-bare')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'answer_salience', choice: '' }),
      'telegram'
    )
  })
})

describe('Telegram — the connector sweep', () => {
  it('runs it from a command and from its tap, both payload-free', async () => {
    await handleTelegramOnboarding('/onboard gather', 'tg-gather')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'gather_connectors' }),
      'telegram'
    )
    const sent = applyMock.mock.calls[0][0] as Record<string, unknown>
    expect('handles' in sent || 'source' in sent).toBe(false)

    applyMock.mockClear()
    await handleTelegramOnboardingCallback('onboard:gather', 'tg-gather-tap')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'gather_connectors' }),
      'telegram'
    )
  })

  it('names both new commands in the unrecognised-choice reply', async () => {
    const reply = await handleTelegramOnboarding('/onboard wat', 'tg-unknown')
    expect(reply[0].text).toContain('/onboard gather')
    expect(reply[0].text).toContain('/onboard salience')
    expect(reply[0].text).toContain('/onboard look')
    expect(reply[0].text).toContain('/onboard org')
  })
})

describe('Telegram — going and looking it up', () => {
  it('runs the look-up from a command and from its tap, both payload-free', async () => {
    await handleTelegramOnboarding('/onboard look', 'tg-look')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'run_discovery' }),
      'telegram'
    )
    const sent = applyMock.mock.calls[0][0] as Record<string, unknown>
    expect('seed' in sent || 'source' in sent).toBe(false)

    applyMock.mockClear()
    await handleTelegramOnboardingCallback('onboard:look', 'tg-look-tap')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'run_discovery' }),
      'telegram'
    )
  })

  it('sends the organisation as typed, including "just me"', async () => {
    await handleTelegramOnboarding('/onboard org just me', 'tg-org')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'answer_organization', organization: 'just me' }),
      'telegram'
    )
  })

  it('renders the results with their addresses, since the body carries only the query', () => {
    const looked = {
      ...RANKED,
      card: {
        ...RANKED.card,
        entry: {
          ...(RANKED.card as { entry?: Record<string, unknown> }).entry,
          discovery: {
            terms: [],
            probes: [],
            executable: true,
            executed: {
              schema: 'cabinet.onboarding-probe-result/v1',
              executed: [{
                kind: 'web_search',
                query: 'tech lead STEP Network',
                provider: 'brave search',
                truncated: false,
                results: [{
                  title: 'STEP Network',
                  url: 'https://stepnetwork.example/',
                  snippet: 'A media network in Copenhagen.',
                }],
              }],
              deferred: [],
              complete: true,
            },
          },
        },
      },
    }
    const message = formatTelegramOnboarding(looked as never)
    expect(message.text).toContain('Searched: tech lead STEP Network')
    expect(message.text).toContain('STEP Network — https://stepnetwork.example/')
    expect(message.text).toContain('A media network in Copenhagen.')
    // PLAIN, with no parse mode — so a hostile result cannot forge formatting
    // or an entity on its way to the operator's phone.
    expect(message.plain).toBe(true)
  })

  // ── IS ANY OF IT ABOUT YOU? (Captain, 2026-08-15) ────────────────────────
  function judged(relevant: number, extra: Record<string, unknown> = {}) {
    return {
      ...RANKED,
      card: {
        ...RANKED.card,
        options: [...((RANKED.card as { options?: unknown[] }).options ?? []),
                  ...((extra.options as unknown[]) ?? [])],
        entry: {
          ...(RANKED.card as { entry?: Record<string, unknown> }).entry,
          discovery: {
            terms: [],
            probes: [],
            executable: true,
            executed: {
              schema: 'cabinet.onboarding-probe-result/v1',
              looked_for: ['STEP Network'],
              executed: [{
                kind: 'web_search',
                query: '"STEP Network"',
                provider: 'brave search',
                truncated: false,
                relevant,
                results: relevant
                  ? [{
                      title: 'STEP Network A/S',
                      url: 'https://stepnetwork.example/',
                      matched: [{ term: 'STEP Network', kind: 'organization', where: 'title' }],
                    }]
                  : [{ title: 'What a tech lead does', url: 'https://blog.example/lead' }],
              }],
              deferred: [],
              complete: true,
            },
          },
        },
      },
    }
  }

  it('says the miss out loud rather than counting what came back', () => {
    const message = formatTelegramOnboarding(judged(0) as never)
    expect(message.text).toContain('None of this looks like your STEP Network')
    // FOLDED, NEVER DELETED — a chat surface has no fold, so it still lists them.
    expect(message.text).toContain('What a tech lead does')
  })

  it('says WHY a result counts, and stays silent when nothing was judged', () => {
    expect(formatTelegramOnboarding(judged(1) as never).text)
      .toContain('names STEP Network')
    const unjudged = judged(0)
    const block = (unjudged.card.entry as { discovery: { executed: Record<string, unknown> } })
      .discovery.executed
    delete block.looked_for
    delete (block.executed as Array<Record<string, unknown>>)[0].relevant
    expect(formatTelegramOnboarding(unjudged as never).text)
      .not.toContain('None of this looks like')
  })

  it('prints the exact command for each earned follow-up', () => {
    const asked = judged(0, {
      options: [{ action: 'answer_org_link', label: 'Give me a link about STEP Network' }],
    })
    expect(formatTelegramOnboarding(asked as never).text)
      .toContain('Give me a link about STEP Network: /onboard link https://…')
    const chip = judged(1, {
      options: [{
        action: 'confirm_organization_domain',
        label: 'Yes, stepnetwork.example is STEP Network',
        domain: 'stepnetwork.example',
      }],
    })
    expect(formatTelegramOnboarding(chip as never).text)
      .toContain('Yes, stepnetwork.example is STEP Network: /onboard confirm')
  })

  it('sends a pasted page as typed, and confirms a domain payload-free', async () => {
    await handleTelegramOnboarding('/onboard link https://stepnetwork.example/about', 'tg-link')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'answer_org_link',
        url: 'https://stepnetwork.example/about',
      }),
      'telegram'
    )
    applyMock.mockClear()
    // PAYLOAD-FREE: the core re-derives the candidate from its own committed
    // look-up, so neither this command nor its tap can record an address that
    // no search returned.
    await handleTelegramOnboarding('/onboard confirm', 'tg-confirm')
    const sent = applyMock.mock.calls[0][0] as Record<string, unknown>
    expect(sent.action).toBe('confirm_organization_domain')
    expect('domain' in sent).toBe(false)
    applyMock.mockClear()
    await handleTelegramOnboardingCallback('onboard:confirm_site', 'tg-confirm-tap')
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'confirm_organization_domain' }),
      'telegram'
    )
  })
})

describe('Telegram — the off-target window is answerable here too', () => {
  it('carries a stated relation on the folder command', async () => {
    await handleTelegramOnboarding(
      '/onboard folder /srv/tax | close the quarter | mine: my own laptop | elsewhere',
      'tg-rel'
    )
    expect(applyMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'propose_window',
        source: '/srv/tax',
        ownership: 'self',
        salience_relation: 'elsewhere',
      }),
      'telegram'
    )
  })

  it('leaves the other segments intact when a relation rides along', async () => {
    await handleTelegramOnboarding(
      '/onboard folder /srv/tax | close the quarter | mine: my own laptop | sovereign | same_thing',
      'tg-rel-2'
    )
    const sent = applyMock.mock.calls[0][0] as Record<string, unknown>
    expect(sent).toMatchObject({
      source: '/srv/tax',
      purpose: 'close the quarter',
      ownership: 'self',
      authority_basis: 'my own laptop',
      relationship_destination: 'sovereign',
      salience_relation: 'same_thing',
    })
  })

  it('sends NOTHING for a relation the vocabulary does not carry', async () => {
    await handleTelegramOnboarding(
      '/onboard folder /srv/tax | close the quarter | mine: my own laptop | probably',
      'tg-rel-3'
    )
    const sent = applyMock.mock.calls[0][0] as Record<string, unknown>
    // Absent means absent — this surface never guesses which statement was
    // meant. The unrecognised segment is not quietly swallowed either: it stays
    // in the string, so the ownership tail no longer parses and the core
    // refuses with `ownership_unclassified`, whose reply carries the syntax.
    // A parser that dropped what it could not read would send a proposal the
    // operator did not write.
    expect(sent.salience_relation).toBeUndefined()
    expect(sent.ownership).toBeUndefined()
    expect(String(sent.purpose)).toContain('probably')
  })

  it('answers an off-target refusal with the syntax that resolves it', async () => {
    applyMock.mockRejectedValueOnce(
      new OnboardingBridgeError(
        'salience_window_off_target',
        'You pointed me at blueharbour, and “tax” shares no word with it.'
      )
    )
    const [reply] = await handleTelegramOnboarding(
      '/onboard folder /srv/tax | close the quarter | mine: my own laptop',
      'tg-rel-refused'
    )
    expect(reply.text).toContain('shares no word with it')
    expect(reply.text).toContain('| same_thing')
    expect(reply.text).toContain('elsewhere')
    expect(reply.text).toContain('/onboard salience')
  })

  it('still answers an ownership refusal with the OWNERSHIP syntax, not this one', async () => {
    applyMock.mockRejectedValueOnce(
      new OnboardingBridgeError('ownership_unclassified', 'Say whose data this is.')
    )
    const [reply] = await handleTelegramOnboarding('/onboard folder /srv/tax', 'tg-own')
    expect(reply.text).toContain('mine, employer, or client')
    expect(reply.text).not.toContain('| same_thing')
  })
})
