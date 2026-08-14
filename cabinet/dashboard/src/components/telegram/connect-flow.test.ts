/**
 * The four screens, rendered.
 *
 * Each step is a props-only component, so these render the REAL thing in the
 * real state and read the words an operator would read — no hook scripting, and
 * no grep standing in for a render. What is pinned:
 *
 *   - every step says what to DO, and the deep link into Telegram is present
 *     and points at BotFather rather than at a page about BotFather;
 *   - the token field is a password field and the token is never rendered back;
 *   - the wrong-chat warning appears the moment a second sender exists, and
 *     names the one that will be used;
 *   - the timeout state offers a retry rather than a dead end;
 *   - the connected screen is HONEST about inbound: it says replies do not work
 *     yet. A flow that ends by implying a two-way channel would be the exact
 *     over-claim this program keeps finding.
 *
 * The power-up card's own contract is here too, because "never nags" is a
 * property of what it renders (nothing) rather than of what it says.
 */
import fs from 'node:fs'
import nodePath from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'

// The container half of connect-flow.tsx imports the server actions, which pull
// in `next/cache` and the runtime-write gate. Neither is exercised here — the
// step components are props-only — so both are stubbed at the module boundary
// to keep this file a pure render test.
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: vi.fn(async () => false) }))
vi.mock('@/lib/docker', () => ({
  assertRuntimeWritesAllowed: vi.fn(),
  dockerExec: vi.fn(),
  getEnvVars: vi.fn(),
}))
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Bubble,
  StepConnected,
  StepCreateBot,
  StepPasteToken,
  StepRail,
  StepSayHi,
  STEPS,
  LISTEN_MAX_TRIES,
} from './connect-flow'
import TelegramPowerUpCard from './power-up-card'
import { CONNECTED_MESSAGE } from '@/lib/telegram/contract'
import { FAKE_TOKEN } from '@/lib/telegram/mock-telegram'

const html = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el)
const noop = () => {}

describe('the rail — four steps, and the one you are on', () => {
  it('numbers every step and ticks the ones behind the current one', () => {
    const out = html(createElement(StepRail, { active: 'hi' }))
    expect(STEPS).toHaveLength(4)
    for (const step of STEPS) expect(out).toContain(step.label)
    // Two done (ticks), the third current, the fourth still numbered.
    expect(out.match(/✓/g) ?? []).toHaveLength(2)
    expect(out).toContain('aria-current="step"')
  })

  it('on the first step nothing is ticked yet', () => {
    expect(html(createElement(StepRail, { active: 'bot' }))).not.toContain('✓')
  })
})

describe('step 1 — make a bot', () => {
  const out = html(createElement(StepCreateBot, { onNext: noop }))

  it('deep-links straight into a chat with BotFather', () => {
    expect(out).toContain('href="https://t.me/BotFather"')
  })

  it('gives the command to send and says what a token looks like', () => {
    expect(out).toContain('/newbot')
    expect(out).toContain('A token looks like this')
    expect(out).toMatch(/\d{8,}:[A-Za-z0-9_-]{20,}/)
  })

  it('says what the token is and where it stays', () => {
    expect(out).toContain('Treat it like a password')
    expect(out).toContain('stays on this machine')
  })
})

describe('step 2 — the token field', () => {
  it('is a password field that never renders the value back as text', () => {
    const out = html(
      createElement(StepPasteToken, {
        token: FAKE_TOKEN,
        onTokenChange: noop,
        onSubmit: noop,
        onBack: noop,
        busy: false,
        error: null,
      })
    )
    expect(out).toContain('type="password"')
    // React renders `value` on the input, which is the field's own state and is
    // not readable as page TEXT — but nothing else may echo it.
    const withoutInput = out.replace(/<input[^>]*>/g, '')
    expect(withoutInput).not.toContain(FAKE_TOKEN)
  })

  it('cannot be submitted empty', () => {
    const out = html(
      createElement(StepPasteToken, {
        token: '',
        onTokenChange: noop,
        onSubmit: noop,
        onBack: noop,
        busy: false,
        error: null,
      })
    )
    expect(out).toContain('disabled=""')
  })

  it('renders a refusal as a sentence with the fix in it', () => {
    const out = html(
      createElement(StepPasteToken, {
        token: 'x',
        onTokenChange: noop,
        onSubmit: noop,
        onBack: noop,
        busy: false,
        error: 'That token did not work — check you copied all of it.',
      })
    )
    expect(out).toContain('check you copied all of it')
  })
})

describe('step 3 — say hi, and who the Cabinet heard', () => {
  const base = {
    botUsername: 'ada_hq_bot',
    listening: false,
    attempts: 0,
    candidate: null,
    others: [],
    groupOnly: false,
    onListen: noop,
    onConfirm: noop,
    onBack: noop,
    busy: false,
    error: null,
  }

  it('names the bot and links straight to it', () => {
    const out = html(createElement(StepSayHi, base))
    expect(out).toContain('@ada_hq_bot')
    expect(out).toContain('href="https://t.me/ada_hq_bot"')
  })

  it('while listening it shows a real count, not a fake progress bar', () => {
    const out = html(createElement(StepSayHi, { ...base, listening: true, attempts: 4 }))
    expect(out).toContain('Checked 4 times')
    expect(out).toContain('Nothing is sent or deleted while I look')
  })

  it('after the wait runs out it offers to keep listening', () => {
    const out = html(createElement(StepSayHi, { ...base, attempts: LISTEN_MAX_TRIES }))
    expect(out).toContain('have not heard from you yet')
    expect(out).toContain('Keep listening')
  })

  it('a captured sender is offered by NAME for confirmation', () => {
    const out = html(
      createElement(StepSayHi, {
        ...base,
        candidate: { chatId: '4242424242', label: '@ada' },
      })
    )
    expect(out).toContain('Yes, that is me')
    expect(out).toContain('@ada')
  })

  it('a SECOND sender raises the wrong-chat warning and names the one that wins', () => {
    const out = html(
      createElement(StepSayHi, {
        ...base,
        candidate: { chatId: '111111', label: '@ada' },
        others: [{ chatId: '222222', label: '@stranger' }],
      })
    )
    expect(out).toContain('More than one person has messaged this bot')
    expect(out).toContain('I will use the first one, @ada')
    expect(out).toContain('@stranger')
    expect(out).toContain('make a fresh bot')
  })

  it('a group-only window says to message the bot directly', () => {
    const out = html(createElement(StepSayHi, { ...base, groupOnly: true }))
    expect(out).toContain('only see a message from a group')
    expect(out).toContain('one-to-one chat')
  })

  it('a hostile display name arrives as inert text, never as markup', () => {
    const out = html(
      createElement(StepSayHi, {
        ...base,
        candidate: { chatId: '111111', label: '<img src=x onerror=alert(1)>' },
      })
    )
    expect(out).not.toContain('<img src=x')
    expect(out).toContain('&lt;img src=x')
  })
})

describe('step 4 — the round trip, and what is honestly not there yet', () => {
  const out = html(
    createElement(StepConnected, {
      botUsername: 'ada_hq_bot',
      chatId: '4242424242',
      wrote: ['where your Cabinet looks for who to message'],
      notes: [],
      onRestart: noop,
    })
  )

  it('shows the exact words that were sent, so screen and phone can be compared', () => {
    expect(out).toContain(CONNECTED_MESSAGE.replace(/'/g, '&#x27;'))
    expect(out).toContain('delivered to your phone')
  })

  it('says what will arrive, and WHEN — not "immediately"', () => {
    expect(out).toContain('What arrives here now')
    expect(out).toContain('when it is scheduled to run')
  })

  it('says plainly that replying does not work yet, and what would make it', () => {
    expect(out).toContain('What does not work yet')
    expect(out).toContain('Replying to the bot')
    expect(out).toContain('running in the background')
    // And WHERE, now that there is a control rather than a runbook command.
    expect(out).toContain('home page')
  })

  it('an AWAKE cabinet is not told to switch on the thing it already switched on', () => {
    // The line used to end "that is the next thing to switch on" for everyone.
    // On a cabinet whose crew is running that is simply false, and it was the
    // same shape of wrong as the red dot: a screen asserting a state it had
    // not measured.
    const awake = html(
      createElement(StepConnected, {
        botUsername: 'ada_hq_bot',
        chatId: '4242424242',
        wrote: [],
        notes: [],
        crewAwake: true,
        onRestart: noop,
      })
    )
    expect(awake).toContain('awake in the background')
    expect(awake).not.toContain('only read once your Cabinet is')
  })

  it('a caller that does not know the crew\'s state must not claim it is awake', () => {
    // The default. `out` above passes no `crewAwake` at all.
    expect(out).not.toContain('awake in the background')
  })

  it('shows the captured address and where it was saved', () => {
    expect(out).toContain('4242424242')
    expect(out).toContain('Saved to where your Cabinet looks for who to message')
  })

  it('a failed write is surfaced as a note rather than swallowed', () => {
    const withNote = html(
      createElement(StepConnected, {
        botUsername: 'ada_hq_bot',
        chatId: '4242424242',
        wrote: [],
        notes: ['Your setup answers were not updated, so re-running setup would undo this'],
        onRestart: noop,
      })
    )
    expect(withNote).toContain('re-running setup would undo this')
  })
})

describe('the bubble — one shape, three states', () => {
  it('waiting is dashed and says it is waiting', () => {
    const out = html(
      createElement(Bubble, { from: '@ada_hq_bot', text: 'listening…', state: 'waiting' })
    )
    expect(out).toContain('border-dashed')
    expect(out).toContain('listening')
  })

  it('delivered carries the tick', () => {
    const out = html(
      createElement(Bubble, { from: 'x', text: 'y', side: 'us', state: 'delivered' })
    )
    expect(out).toContain('delivered to your phone')
  })

  it('respects reduced motion on the only animation in the flow', () => {
    const out = html(createElement(Bubble, { from: 'x', text: 'y', state: 'waiting' }))
    expect(out).toContain('motion-reduce:animate-none')
  })
})

describe('the power-up card — an offer that cannot nag', () => {
  it('renders NOTHING when Telegram is already connected', () => {
    expect(html(createElement(TelegramPowerUpCard, { connected: true }))).toBe('')
  })

  it('renders nothing on the server pass either — the dismissal is read first', () => {
    // Server-rendered markup is empty by construction: the component starts in
    // "have not looked yet" and only decides after the effect. That is what
    // stops a dismissed card flashing back onto the page for a frame.
    expect(html(createElement(TelegramPowerUpCard, { connected: false }))).toBe('')
  })

  it('the source offers a way out and points at the flow', () => {
    // The dismissable body only exists post-hydration, so its promises are
    // pinned at the source: a "not now", a link to the one flow, and the
    // sentence that says the offer survives being declined.
    const source = readSource('src/components/telegram/power-up-card.tsx')
    expect(source).toContain('Not now')
    expect(source).toContain('/integrations/telegram')
    expect(source).toContain('it stays in Integrations')
    expect(source).toContain('cabinet:telegram:power-up-dismissed')
  })
})

describe('source contracts the render cannot see', () => {
  it('the client bundle never imports the token-bearing transport', () => {
    // `lib/telegram/connect.ts` builds `…/bot<token>/…` URLs. A client component
    // importing it would ship that builder to a browser. The shared vocabulary
    // lives in `contract.ts` precisely so this import never has to happen.
    const flow = readSource('src/components/telegram/connect-flow.tsx')
    expect(flow).toContain("from '@/lib/telegram/contract'")
    expect(flow).not.toContain("from '@/lib/telegram/connect'")
  })

  it('the flow never persists the token in the browser', () => {
    const flow = readSource('src/components/telegram/connect-flow.tsx')
    expect(flow).not.toMatch(/localStorage|sessionStorage|document\.cookie/)
    // …and it drops its in-memory copy the moment the server has it.
    expect(flow).toContain("setToken('')")
  })
})

function readSource(rel: string): string {
  return fs.readFileSync(nodePath.join(process.cwd(), rel), 'utf8')
}
