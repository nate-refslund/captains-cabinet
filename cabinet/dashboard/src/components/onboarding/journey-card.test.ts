/**
 * Three layers of guarantee, explicitly scoped:
 *
 * 1. RENDER TESTS (`rendered component` below) — execute the REAL component
 *    through react-dom/server and assert on its rendered output: the typed
 *    purge confirmation gate (destructive submit stays disabled until the
 *    Captain types exactly PURGE) and the feedback claim gate ("Feedback
 *    recorded" renders only from confirmed state). A dead or rewired gate
 *    fails these; a source grep alone would not.
 *
 * 2. DRIVEN TESTS (`driven component` below) — invoke the component's real
 *    onSubmit/onClick closures against a stubbed fetch and setter spies:
 *    the confirmed purge is POSTed to the one shared API without a
 *    post-purge ui observation, and feedback is claimed only after the
 *    evidence endpoint confirms preservation.
 *
 *    Full click-through DOM tests (@testing-library/react + jsdom/happy-dom)
 *    are NOT possible in this package today — neither library is a
 *    dependency and vitest runs in the 'node' environment — so state is
 *    injected via a hook-scripted useState (loudly order-guarded below).
 *
 * 3. SOURCE CONTRACTS (the grep sections) — pin source-level promises that a
 *    render cannot see (no window.confirm anywhere, no storage APIs, the
 *    awaited-endpoint pattern for feedback claims).
 *
 * SECURITY BOUNDARY: the UI gate is a convenience layer only. The journey
 * core refuses any purge whose confirmation !== 'PURGE' server-side —
 * enforced by framework/onboarding/journey.py ("purge_confirmation" refusal)
 * and pinned by framework/onboarding/tests/test_journey.py::
 * test_purge_requires_typed_confirmation_and_removes_sensitive_history.
 * Nothing in this file is load-bearing for that refusal.
 */
import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createElement, type ComponentProps } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type {
  OnboardingEntryPlan,
  OnboardingIdentityAsk,
  OnboardingOption,
  OnboardingResponse,
} from '@/lib/onboarding/types'

// Hook-scripted state injection: react-dom/server renders initial state only,
// so stateful scenarios (purge armed, feedback recorded) are reached by
// overriding useState returns in call order, and handlers are driven by
// calling the component function directly (useCallback/useRef/useEffect are
// given handler-faithful stand-ins while a script is active). Every scripted
// useState call asserts the initial value the component actually passed, so a
// hook reorder/add/remove in journey-card.tsx fails LOUDLY here instead of
// silently testing the wrong state.
const hookScript = vi.hoisted(() => ({
  steps: null as Array<{ initial: unknown; value?: unknown }> | null,
  cursor: 0,
  setterCalls: [] as Array<{ index: number; value: unknown }>,
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    useState: (initial: unknown) => {
      if (!hookScript.steps) return actual.useState(initial)
      const index = hookScript.cursor
      const step = hookScript.steps[index]
      if (!step) {
        throw new Error(
          `journey-card useState call #${index} is beyond the scripted hook order — update hookScript in journey-card.test.ts`
        )
      }
      if (!Object.is(step.initial, initial)) {
        throw new Error(
          `journey-card useState call #${index} initial value changed (expected ${JSON.stringify(step.initial)}, got ${JSON.stringify(initial)}) — hook order in journey-card.tsx moved; update hookScript in journey-card.test.ts`
        )
      }
      hookScript.cursor += 1
      return [
        'value' in step ? step.value : initial,
        (value: unknown) => hookScript.setterCalls.push({ index, value }),
      ]
    },
    useCallback: (fn: unknown, deps: unknown[]) =>
      hookScript.steps ? fn : actual.useCallback(fn as () => void, deps),
    useRef: (initial: unknown) =>
      hookScript.steps ? { current: initial } : actual.useRef(initial),
    useEffect: (fn: () => void, deps?: unknown[]) =>
      hookScript.steps ? undefined : actual.useEffect(fn, deps),
  }
})

import OnboardingJourneyCard, { IDENTITY_SHOWN, NO_IDENTITY_PICKS, NO_MERGE } from './journey-card'

afterEach(() => {
  hookScript.steps = null
  hookScript.cursor = 0
  hookScript.setterCalls = []
  vi.unstubAllGlobals()
})

function journeyFixture(stage: string): OnboardingResponse {
  return {
    ok: true,
    state: {
      schema: 'cabinet.onboarding-journey/v2',
      journey_id: 'journey-test',
      evidence_trial_id: 'trial-test',
      revision: 3,
      stage,
      purpose: 'Find one useful thing I may be missing.',
      relationship_destination: 'reversible',
      orientation_mode: 'observe_only',
      access: 'read_only',
      source: null,
      charter: null,
      first_dividend: null,
      created_at: '2026-07-14T10:00:00Z',
      updated_at: '2026-07-14T10:05:00Z',
    },
    card: {
      schema: 'cabinet.onboarding-card/v1',
      id: 'card-test',
      journey_id: 'journey-test',
      revision: 3,
      stage,
      kind: 'journey',
      title: 'Test card title',
      body: 'Test card body.',
      status: 'active',
      evidence: [],
      options: [],
    },
  }
}

/** An entry plan whose only content is the identity ask, for picker arms. */
function identityEntry(connectors: OnboardingIdentityAsk[]): OnboardingEntryPlan {
  return {
    schema: 'cabinet.onboarding-entry-plan/v1',
    mode: 'connected',
    opening_move: 'sweep_and_assert',
    grants: { connectors: connectors.map((ask) => ask.connector), local_files: true, web: false },
    seed_question: null,
    questions: [],
    discovery: { terms: [], probes: [], executable: false },
    cannot_know: [],
    identity_question: {
      question: 'I cannot tell which of the actors I read is you.',
      is_a_question: true,
      connectors,
    },
    next_actions: [
      { action: 'record_operator_identity', label: 'Tell me which account is you', input: 'handles' },
    ],
  }
}

/**
 * Script the component's useState calls, in source order, with overrides.
 * Initial values are asserted against the component's real ones so drift is
 * loud (see hookScript mock above).
 */
function scriptState(overrides: {
  journey?: OnboardingResponse
  loading?: boolean
  working?: boolean
  purgeArmed?: boolean
  purgeConfirmation?: string
  source?: string
  sourceEdited?: boolean
  ownership?: string
  authorityBasis?: string
  seed?: string
  feedbackRecorded?: string | null
  handles?: Readonly<Record<string, string>>
  salienceChoice?: string
  salienceName?: string
  salienceMerge?: readonly string[]
  relationAsk?: unknown
}) {
  hookScript.cursor = 0
  hookScript.steps = [
    { initial: null, value: overrides.journey ?? null }, // journey
    { initial: true, value: overrides.loading ?? false }, // loading
    { initial: false, value: overrides.working ?? false }, // working
    { initial: null }, // error
    { initial: false }, // collapsed
    { initial: false }, // editScope
    { initial: false, value: overrides.purgeArmed ?? false }, // purgeArmed
    { initial: '', value: overrides.purgeConfirmation ?? '' }, // purgeConfirmation
    { initial: '~/Documents', value: overrides.source ?? '~/Documents' }, // source
    // sourceEdited — has the operator touched the folder field? `source` alone
    // cannot say (its default is a real path someone might type), and the answer
    // is what stops a pre-fill overwriting their text.
    { initial: false, value: overrides.sourceEdited ?? false }, // sourceEdited
    { initial: 'Find one useful thing I may be missing.' }, // purpose
    { initial: 'reversible' }, // destination
    { initial: '', value: overrides.ownership ?? '' }, // ownership — no default BY DESIGN
    { initial: '', value: overrides.authorityBasis ?? '' }, // authorityBasis
    { initial: '', value: overrides.seed ?? '' }, // seed — the seed question's field
    { initial: null, value: overrides.feedbackRecorded ?? null }, // feedbackRecorded
    { initial: NO_IDENTITY_PICKS, value: overrides.handles ?? NO_IDENTITY_PICKS }, // handles — which account is the operator, per connector
    { initial: '', value: overrides.salienceChoice ?? '' }, // salienceChoice — no default BY DESIGN: the ranking is a guess
    { initial: '', value: overrides.salienceName ?? '' }, // salienceName — the escape hatch's typed target
    { initial: NO_MERGE, value: overrides.salienceMerge ?? NO_MERGE }, // salienceMerge — ranked names the operator says are one thing
    { initial: null, value: overrides.relationAsk ?? null }, // relationAsk — set only by an off-target refusal
  ]
}

function render(props: ComponentProps<typeof OnboardingJourneyCard> = {}): string {
  return renderToStaticMarkup(createElement(OnboardingJourneyCard, props))
}

/** The opening tag of the destructive purge submit button in rendered HTML. */
function purgeSubmitTag(html: string): string {
  const label = html.indexOf('Permanently delete onboarding data')
  expect(label, 'purge submit button not rendered').toBeGreaterThan(-1)
  return html.slice(html.lastIndexOf('<button', label), label)
}

// The disabled ATTRIBUTE, not the substring — the button's className contains
// `disabled:opacity-50`, which a plain toContain('disabled') would match.
const DISABLED_ATTR = /\sdisabled(?:="[^"]*")?(?=[\s>])/

describe('rendered component — typed purge confirmation gate', () => {
  it('renders the armed purge form with the destructive submit DISABLED before PURGE is typed', () => {
    scriptState({ journey: journeyFixture('charter_ratified'), purgeArmed: true, purgeConfirmation: '' })
    const tag = purgeSubmitTag(render())
    expect(tag).toMatch(DISABLED_ATTR)
  })

  it('keeps the destructive submit DISABLED for a wrong or lowercase confirmation', () => {
    for (const wrong of ['purge', 'PURG', 'PURGE ', 'DELETE']) {
      scriptState({ journey: journeyFixture('charter_ratified'), purgeArmed: true, purgeConfirmation: wrong })
      expect(purgeSubmitTag(render()), `confirmation ${JSON.stringify(wrong)} must keep the button disabled`).toMatch(DISABLED_ATTR)
    }
  })

  it('enables the destructive submit only when the confirmation is exactly PURGE', () => {
    scriptState({ journey: journeyFixture('charter_ratified'), purgeArmed: true, purgeConfirmation: 'PURGE' })
    const tag = purgeSubmitTag(render())
    expect(tag).not.toMatch(DISABLED_ATTR)
  })

  it('keeps the destructive submit disabled while an action is in flight even with PURGE typed', () => {
    scriptState({ journey: journeyFixture('charter_ratified'), purgeArmed: true, purgeConfirmation: 'PURGE', working: true })
    expect(purgeSubmitTag(render())).toMatch(DISABLED_ATTR)
  })
})

describe('rendered component — feedback claim gate', () => {
  it('never claims feedback was recorded before the confirmed state exists', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), feedbackRecorded: null })
    const html = render()
    expect(html).toContain('Did this earn its keep?')
    expect(html).toContain('Yes, useful')
    expect(html).not.toContain('Feedback recorded:')
  })

  it('claims recording only from the endpoint-confirmed state', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), feedbackRecorded: 'useful' })
    const html = render()
    expect(html).toContain('Feedback recorded: useful.')
    expect(html).not.toContain('Yes, useful')
  })
})

// ---------------------------------------------------------------------------
// DRIVEN handlers — call the component function with scripted hooks, walk the
// returned element tree, and invoke the real onSubmit/onClick closures against
// a stubbed fetch. This executes the actual gating logic (send()'s post-purge
// observation suppression, recordFeedback()'s confirm-before-claim), which no
// markup or grep assertion can reach.
// ---------------------------------------------------------------------------

interface TreeElement {
  type: unknown
  props: { children?: unknown; [key: string]: unknown }
}

function* walk(node: unknown): Generator<TreeElement> {
  if (node === null || node === undefined) return
  if (typeof node !== 'object') return
  if (Array.isArray(node)) {
    for (const child of node) yield* walk(child)
    return
  }
  const el = node as TreeElement
  if (!('props' in el) || typeof el.props !== 'object' || el.props === null) return
  yield el
  yield* walk(el.props.children)
}

function driveTree(props: ComponentProps<typeof OnboardingJourneyCard> = {}): TreeElement[] {
  // Direct invocation is only valid while hooks are scripted.
  expect(hookScript.steps, 'driveTree requires scriptState() first').not.toBeNull()
  const root = (OnboardingJourneyCard as unknown as (p: object) => unknown)(props)
  return [...walk(root)]
}

function findByText(tree: TreeElement[], type: string, text: string): TreeElement {
  const match = tree.find((el) => el.type === type && el.props.children === text)
  expect(match, `<${type}> with text ${JSON.stringify(text)} not found in tree`).toBeDefined()
  return match!
}

/** Indices into the component's useState order (guarded by scriptState). */
// Indices track the useState order in journey-card.tsx; the ownership pair
// landed between destination and feedbackRecorded. The four salience/relation
// hooks were APPENDED after handles so every index above stayed put. The
// `sourceEdited` flag landed at 9, immediately after the field it describes, so
// everything from `purpose` down shifted by one.
const STATE = {
  error: 3,
  editScope: 5,
  source: 8,
  sourceEdited: 9,
  ownership: 12,
  authorityBasis: 13,
  seed: 14,
  feedbackRecorded: 15,
  salienceChoice: 17,
  relationAsk: 20,
} as const

function settersFor(index: number): unknown[] {
  return hookScript.setterCalls.filter((call) => call.index === index).map((call) => call.value)
}

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('driven component — typed purge submit', () => {
  it('posts the confirmed purge action and never reports a post-purge ui observation', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'purged' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({ journey: journeyFixture('charter_ratified'), purgeArmed: true, purgeConfirmation: 'PURGE' })
    const tree = driveTree()
    const form = tree.find((el) => el.type === 'form')
    expect(form, 'armed purge form not in tree').toBeDefined()
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
    await flush(); await flush()

    const calls = fetchSpy.mock.calls.map(([url, init]) => ({
      url: String(url),
      body: String((init as RequestInit | undefined)?.body ?? ''),
    }))
    const action = calls.find((call) => call.url.endsWith('/api/onboarding'))
    expect(action, 'purge action was never POSTed to the shared API').toBeDefined()
    expect(action!.body).toContain('"action":"purge"')
    expect(action!.body).toContain('"confirmation":"PURGE"')
    // The pre-action ui/started observation is legitimate; a post-purge
    // succeeded/failed observation into the just-purged trial is not.
    const observations = calls.filter((call) => call.url.endsWith('/api/onboarding/evidence'))
    expect(observations.some((call) => call.body.includes('"status":"started"'))).toBe(true)
    expect(observations.some((call) => call.body.includes('"status":"succeeded"'))).toBe(false)
    expect(observations.some((call) => call.body.includes('"status":"failed"'))).toBe(false)
  })
})

describe('driven component — feedback claim gate', () => {
  function clickUseful(): void {
    scriptState({ journey: journeyFixture('dividend_ready'), feedbackRecorded: null })
    const useful = findByText(driveTree(), 'button', 'Yes, useful')
    ;(useful.props.onClick as () => void)()
  }

  it('claims feedback only after the evidence endpoint confirms preservation', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) })))
    clickUseful()
    await flush(); await flush()
    expect(settersFor(STATE.feedbackRecorded)).toEqual(['useful'])
    expect(settersFor(STATE.error)).toEqual([])
  })

  it('does not claim feedback when the endpoint returns ok:false, and surfaces the failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ok: false }) })))
    clickUseful()
    await flush(); await flush()
    expect(settersFor(STATE.feedbackRecorded)).toEqual([])
    expect(settersFor(STATE.error)).toEqual(['Your feedback could not be preserved yet. Please try again.'])
  })

  it('does not claim feedback when the evidence endpoint is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    clickUseful()
    await flush(); await flush()
    expect(settersFor(STATE.feedbackRecorded)).toEqual([])
    expect(settersFor(STATE.error)).toEqual(['Your feedback could not be preserved yet. Please try again.'])
    errorSpy.mockRestore()
  })
})

describe('rendered component — accessible shell', () => {
  it('executes the real component and renders an accessible loading state', () => {
    const html = render({ surface: 'dashboard' })
    expect(html).toContain('role="status"')
    expect(html).toContain('Opening your Cabinet orientation')
    expect(html).toContain('aria-live="polite"')
  })

  it('renders the loaded card with a labelled section and live region', () => {
    scriptState({ journey: journeyFixture('charter_pending') })
    const html = render()
    expect(html).toContain('aria-labelledby="onboarding-card-title"')
    expect(html).toContain('id="onboarding-card-title"')
    expect(html).toContain('Test card title')
    expect(html).toContain('aria-live="polite"')
  })

  // Three entry modes (Captain ruling 2026-07-26). The welcome card used to
  // offer one move and name no alternative; when the core hands down an entry
  // plan the surface has to SHOW the questions it cannot answer for itself,
  // or the plan is data nobody reads.
  it('renders the residual questions when the card carries an entry plan', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'ungranted',
      opening_move: 'residual_questions',
      grants: { connectors: [], local_files: false, web: false },
      seed_question: 'What do you do, and how can I best serve you?',
      questions: [
        {
          id: 'rights',
          prompt: 'Which of these sources are yours to give me read access to?',
          why: 'No amount of access answers this.',
          required: true,
        },
      ],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [
        { subject: 'grant_rights', verdict: 'never', statement: 'Not in the data.' },
      ],
      identity_question: null,
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('What I cannot work out for myself')
    expect(html).toContain('yours to give me read access to')
    expect(html).toContain('No amount of access answers this.')
  })

  // THE FIELD THE QUESTION NEVER HAD. The core printed "what do you do, and
  // how can I best serve you?" inside the card body, and this surface rendered
  // it as prose with no input — so the operator was asked a question they had
  // no way to answer, which is a dead end wearing an invitation's clothes.
  it('renders an input for the seed question whenever the core asks it', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'seeded',
      opening_move: 'seed_then_discover',
      grants: { connectors: [], local_files: true, web: false },
      seed_question: 'What do you do, and how can I best serve you?',
      questions: [],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [],
      identity_question: null,
      next_actions: [
        { action: 'propose_window', label: 'Choose a folder I may read' },
        { action: 'answer_seed', label: 'Tell me in a sentence', input: 'seed' },
      ],
    }
    scriptState({ journey: fixture, seed: 'I look after payments releases' })
    const html = render()
    expect(html).toContain('What do you do, and how can I best serve you?')
    expect(html).toContain('id="dashboard-seed"')
    expect(html).toContain('Go and look')
  })

  // WHO THE OPERATOR IS IS ASKED, AND THE ASK NEEDS A FIELD. The core resolves
  // attribution only from what the operator says, so a surface that prints the
  // question and offers no way to answer it makes the resolved branch
  // unreachable — the exact defect the seed field was added to close.
  it('renders the identity picker over the connectors own account identifiers', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'connected',
      opening_move: 'sweep_and_assert',
      grants: { connectors: ['code'], local_files: true, web: false },
      seed_question: null,
      questions: [],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [],
      identity_question: {
        question: 'I cannot tell which of the actors I read is you in code, tracker.',
        is_a_question: true,
        connectors: [
          {
            connector: 'code',
            rows: 56,
            candidates: [
              { identifier: 'an-org', rows: 52 },
              { identifier: 'aperson', rows: 3 },
            ],
            reports_no_actor: false,
            accounts: 2,
            withheld: 0,
            complete: true,
            note: 'code: 2 account(s) appear across 56 rows, and all of them are offered here',
          },
          {
            connector: 'tracker',
            rows: 531,
            candidates: [],
            reports_no_actor: true,
            accounts: 0,
            withheld: 0,
            complete: true,
            note: 'tracker reported no actor on any of its 531 rows, so until its actor path is declared, even your own account attributes nothing there',
          },
        ],
      },
      next_actions: [
        { action: 'record_operator_identity', label: 'Tell me which account is you', input: 'handles' },
      ],
    }
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('I cannot tell which of the actors I read is you')
    // The candidates are the ESTATE's own strings, with how much of the
    // connector each accounts for, so the pick is a tap and not a spelling test.
    expect(html).toContain('an-org')
    expect(html).toContain('52 of 56 here')
    expect(html).toContain('name="dashboard-identity-code"')
    // A connector that reported nobody offers no radio to press and says why.
    expect(html).not.toContain('name="dashboard-identity-tracker"')
    expect(html).toContain('even your own account attributes nothing there')
  })

  // THE OPERATOR IS NOT ALWAYS THE BUSIEST ACCOUNT, and on the estate this was
  // measured against they were 25th of 30 on the connector carrying 531 of 665
  // rows. The core now offers every account a connector reported; this surface
  // must make all of them reachable, so the quiet ones go behind a disclosure
  // rather than off the card. Lopsided on purpose — a fixture where the
  // operator sits in the visible head cannot tell a complete offer from a head.
  it('keeps the quietest account reachable instead of showing only the busiest', () => {
    const busiest = Array.from({ length: IDENTITY_SHOWN }, (_, index) => ({
      identifier: `colleague-${index}`,
      rows: 50 - index,
    }))
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      {
        connector: 'tracker',
        rows: 531,
        candidates: [...busiest, { identifier: 'the-operator', rows: 1 }],
        reports_no_actor: false,
        accounts: IDENTITY_SHOWN + 1,
        withheld: 0,
        complete: true,
        note: 'tracker: 9 account(s) appear across 531 rows, and all of them are offered here',
      },
    ])
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('colleague-0')
    // Present in the markup — a disclosure, never a truncation.
    expect(html).toContain('the-operator')
    expect(html).toContain('Show the other 1 account in tracker')
    expect(html).toContain('<details')
    // No typed field: the offer is COMPLETE, so "none of these" is a true
    // terminal state and a free-text box could only add a wrong spelling.
    expect(html).not.toContain('name="dashboard-identity-typed-tracker"')
  })

  it('opens a typed field only where the core says the offer cannot be completed', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      {
        connector: 'tracker',
        rows: 4000,
        candidates: [{ identifier: 'colleague-0', rows: 900 }],
        reports_no_actor: false,
        accounts: 203,
        withheld: 202,
        complete: false,
        note: 'tracker: 203 account(s) appear across 4000 rows, and I can only offer 1 of them here — if none of those 1 is you, type the account name instead',
      },
    ])
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('name="dashboard-identity-typed-tracker"')
    expect(html).toContain('202 more accounts in tracker than I can list')
  })

  it('asks nothing about identity once every connector resolves', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'connected',
      opening_move: 'sweep_and_assert',
      grants: { connectors: ['code'], local_files: true, web: false },
      seed_question: null,
      questions: [],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [],
      identity_question: null,
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    expect(render()).not.toContain('That one is me')
  })

  it('renders no seed input when the core asks no seed question', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'connected',
      opening_move: 'sweep_and_assert',
      grants: { connectors: ['tracker_export:t.csv'], local_files: true, web: false },
      seed_question: null,
      questions: [],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [],
      identity_question: null,
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    // Narrow to the seed field's own id: the welcome scope form carries its
    // own textarea, so a bare '<textarea' assertion would pass for the wrong
    // reason and stop being a sensor for this behaviour at all.
    expect(render()).not.toContain('id="dashboard-seed"')
  })

  // A probe class that did not run is never summarised away: the surface shows
  // the deferred rows beside the hits, or "I went looking" is a claim about
  // somewhere it never reached.
  it('renders what the probes found AND what did not run', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'seeded',
      opening_move: 'seed_then_discover',
      grants: { connectors: [], local_files: true, web: false },
      seed_question: 'What do you do, and how can I best serve you?',
      questions: [],
      discovery: {
        terms: ['payments'],
        probes: [{ kind: 'local_name_match', pattern: '*payments*' }],
        executable: true,
        executed: {
          schema: 'cabinet.onboarding-probe-result/v1',
          executed: [
            { kind: 'local_name_match', pattern: '*payments*', matches: ['docs/payments.md'], truncated: false },
          ],
          deferred: [{ kind: 'web_search', reason: 'no_egress_in_the_onboarding_core' }],
          complete: false,
        },
      },
      cannot_know: [],
      identity_question: null,
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('What I went and looked for')
    expect(html).toContain('docs/payments.md')
    expect(html).toContain('did not run')
    expect(html).toContain('no egress in the onboarding core')
  })

  // A probe that STOPPED read part of the folder, so "nothing matched by name"
  // beside it is a claim about somewhere it never reached. The core marks the
  // row `truncated`; rendering the row without it is the unearned negative on
  // the one surface the operator actually reads.
  it('says when a search stopped at its limit instead of implying it finished', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'seeded',
      opening_move: 'seed_then_discover',
      grants: { connectors: [], local_files: true, web: false },
      seed_question: 'What do you do, and how can I best serve you?',
      questions: [],
      discovery: {
        terms: ['payments'],
        probes: [{ kind: 'local_name_match', pattern: '*payments*' }],
        executable: true,
        executed: {
          schema: 'cabinet.onboarding-probe-result/v1',
          executed: [
            { kind: 'local_name_match', pattern: '*payments*', matches: [], truncated: true },
          ],
          deferred: [],
          complete: false,
        },
      },
      cannot_know: [],
      identity_question: null,
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('nothing matched by name')
    expect(html).toContain('stopped at my limit before the end of the folder')
  })

  it('renders no residual-question block when the card carries no entry plan', () => {
    scriptState({ journey: journeyFixture('charter_pending') })
    expect(render()).not.toContain('What I cannot work out for myself')
  })
})

const component = fs.readFileSync(
  path.join(process.cwd(), 'src/components/onboarding/journey-card.tsx'),
  'utf8'
)
const worldPage = fs.readFileSync(
  path.join(process.cwd(), 'src/app/(authenticated)/world/page.tsx'),
  'utf8'
)

describe('onboarding journey accessibility floor', () => {
  it('uses labeled controls, a fieldset, live status, and minimum 44px targets', () => {
    expect(component).toMatch(/<label htmlFor=/)
    expect(component).toMatch(/<fieldset>/)
    expect(component).toMatch(/<legend/)
    expect(component).toMatch(/aria-live="polite"/)
    expect(component).toMatch(/min-h-11/)
    expect(component).toMatch(/role="status"/)
  })

  it('requires a typed destructive confirmation instead of a one-tap prompt', () => {
    expect(component).toContain("purgeConfirmation !== 'PURGE'")
    expect(component).toContain('Type PURGE to permanently delete')
    expect(component).not.toContain('window.confirm')
    expect(component).toContain("action !== 'purge'")
    expect(component).toContain("body.card.stage !== 'purged'")
  })

  it('keeps evidence as DOM text with path and line, never canvas-only', () => {
    expect(component).toMatch(/citation\.path/)
    expect(component).toMatch(/citation\.line/)
    expect(component).toMatch(/citation\.excerpt/)
    expect(component).not.toMatch(/<canvas/)
  })

  it('uses ordinary product language at the low floor', () => {
    expect(component).toContain('Folder to look through')
    expect(component).toContain('Use my Documents')
    expect(component).not.toMatch(/\bMCP\b/)
    expect(component).not.toMatch(/\bRedis\b/)
    expect(component).not.toMatch(/\bYAML\b/)
  })

  it('only claims Captain feedback was recorded after the evidence endpoint confirms it', () => {
    expect(component).toContain('const recorded = await reportEvidence')
    expect(component).toContain('if (recorded)')
    expect(component).toContain('Your feedback could not be preserved yet')
  })

  it('uses the insecure-LAN-safe id helper for action and evidence correlation ids', () => {
    expect(component).not.toContain('crypto.randomUUID()')
    expect(component.match(/newActionId\(/g)?.length).toBeGreaterThanOrEqual(8)
  })
})

describe('surface parity without a World mutation fork', () => {
  it('submits every surface action to the one shared API', () => {
    expect(component.match(/fetch\('\/api\/onboarding'/g)?.length).toBe(2)
    expect(component).not.toContain('/api/world/')
    expect(component).not.toMatch(/localStorage|sessionStorage|indexedDB/)
  })

  it('World renders the same component and labels its shared-service seam', () => {
    expect(worldPage).toContain('<OnboardingJourneyCard surface="world" variant="world" />')
    expect(worldPage).toContain('posts to /api/onboarding')
    expect(worldPage).not.toMatch(/fetch\(|axios\.|export\s+async\s+function\s+(POST|PUT|PATCH|DELETE)/)
  })
})

// A COMMENT IS A CLAIM SURFACE TOO, and this one shipped in a public repo. The
// native <details> was justified on the ground that "the rest must be reachable
// with scripting off", and the same sentence sat on IDENTITY_SHOWN. Neither was
// ever true: this is a client component whose entire content arrives from a
// fetch, so with scripting off there is no picker, no account list and no
// question to disclose. The <details> is the right choice for a different
// reason — the browser owns the open/closed bit, so it costs no hook — and
// these arms hold the stated reason to what the component actually does.
describe('claim surfaces — the reasons the source gives for itself', () => {
  it('renders nothing of the identity ask before the client fetch resolves', () => {
    scriptState({ loading: true })   // journey stays null, as it is on first paint
    const html = render()
    expect(html).toContain('Opening your Cabinet orientation')
    expect(html).not.toContain('<details')
    expect(html).not.toContain('identity')
    expect(html).not.toContain('<form')
  })

  it('does not justify the disclosure as a no-script fallback', () => {
    // The property that makes the old reason false, read off the source: the
    // component is client-only and gets its content from fetch.
    expect(component).toContain("'use client'")
    expect(component).toContain("await fetch('/api/onboarding'")
    expect(component).not.toMatch(/reachable with scripting off/)
    expect(component).not.toMatch(/reachable here without scripting/)
    expect(component).not.toMatch(/<noscript/)
  })

  it('still promises what it can keep — every offered account is on the card', () => {
    const candidates = Array.from({ length: IDENTITY_SHOWN + 4 }, (_, index) => ({
      identifier: `account-${index}`,
      rows: 40 - index,
    }))
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      {
        connector: 'tracker',
        rows: 400,
        candidates,
        reports_no_actor: false,
        accounts: candidates.length,
        withheld: 0,
        complete: true,
        note: 'tracker: 12 account(s) appear across 400 rows, and all of them are offered here',
      },
    ])
    scriptState({ journey: fixture })
    const html = render()
    for (const candidate of candidates) {
      expect(html).toContain(candidate.identifier)
    }
    expect(html).toContain('<details')
  })
})

// ---------------------------------------------------------------------------
// THE RANKED QUESTION, AND THE TWO BUTTONS THAT USED TO GO NOWHERE.
//
// `answer_salience` was printed on the card as an option, the surface rendered
// it as a button, and `choose()` fell through to a bare send that the bridge
// refused as `action_invalid` before the core ever saw it — a live dead end at
// the one question that decides where the depth budget is spent.
// `record_operator_identity` fell through the same path onto a core refusal.
// Both arms below FAIL against the pre-change component.
// ---------------------------------------------------------------------------

/** The offer as the core builds it: three ranked names, escape hatch last. */
function salienceOfferOption(): OnboardingOption {
  return {
    action: 'answer_salience',
    label: 'Point me at the one to open first',
    input: 'choice',
    options: [
      {
        id: 'blueharbour',
        label: 'blueharbour',
        why: 'repo: blue-harbour, blue-harbour-api; tracker: Blue Harbour plan',
        connectors: ['repo', 'tracker'],
        rows: 4,
        aliases: ['blue', 'harbour'],
      },
      {
        id: 'redanchor',
        label: 'redanchor',
        why: 'repo: red-anchor; tracker: Red Anchor',
        connectors: ['repo', 'tracker'],
        rows: 2,
        aliases: ['red', 'anchor'],
      },
      {
        id: 'other',
        label: 'None of these — I will name it',
        why: 'The ranking can be wrong; a name you type beats a name I guessed.',
        input: 'seed',
      },
    ],
    merge: {
      field: 'same_as',
      question: 'Are any two of these the same thing under different names?',
      candidates: [
        { id: 'blueharbour', label: 'blueharbour', connectors: ['repo'] },
        { id: 'redanchor', label: 'redanchor', connectors: ['repo'] },
        { id: 'harbouryard', label: 'harbouryard', connectors: ['tracker'] },
      ],
      learned: [{ labels: ['greenlantern', 'lantern'] }],
    },
    not_reached: 'Ranked names only, never contents: 9 from repo, 9 from tracker.',
  }
}

function rankedFixture(): OnboardingResponse {
  const fixture = journeyFixture('orientation_offered')
  fixture.card.options = [
    salienceOfferOption(),
    { action: 'propose_window', label: 'Choose a folder I may read' },
  ]
  return fixture
}

describe('rendered component — the ranked question is answerable', () => {
  it('renders every candidate with the names behind its rank, escape hatch last', () => {
    scriptState({ journey: rankedFixture() })
    const html = render()
    expect(html).toContain('Point me at the one to open first')
    expect(html).toContain('value="blueharbour"')
    expect(html).toContain('value="redanchor"')
    expect(html).toContain('value="other"')
    // The evidence line, not a score: a number the operator cannot audit is not
    // evidence, and it is the only thing they have to judge the ranking by.
    expect(html).toContain('blue-harbour-api')
    expect(html).toContain('None of these')
    expect(html).toContain('Go deep on that one')
  })

  it('states what the sweep did not reach — an unearned clean negative is the defect', () => {
    scriptState({ journey: rankedFixture() })
    expect(render()).toContain('Ranked names only, never contents')
  })

  it('opens the typed field ONLY where the core marked the picked option as needing one', () => {
    scriptState({ journey: rankedFixture(), salienceChoice: 'blueharbour' })
    expect(render()).not.toContain('dashboard-salience-name')
    scriptState({ journey: rankedFixture(), salienceChoice: 'other' })
    expect(render()).toContain('dashboard-salience-name')
  })

  it('keeps the submit disabled until there is an answer to send', () => {
    const submitTag = (html: string): string => {
      const label = html.indexOf('Go deep on that one')
      return html.slice(html.lastIndexOf('<button', label), label)
    }
    scriptState({ journey: rankedFixture() })
    expect(submitTag(render()), 'no pick').toMatch(DISABLED_ATTR)
    scriptState({ journey: rankedFixture(), salienceChoice: 'other' })
    expect(submitTag(render()), 'escape hatch with no name').toMatch(DISABLED_ATTR)
    scriptState({ journey: rankedFixture(), salienceChoice: 'other', salienceName: 'Harbour Yard' })
    expect(submitTag(render()), 'escape hatch with a name').not.toMatch(DISABLED_ATTR)
    scriptState({ journey: rankedFixture(), salienceChoice: 'blueharbour' })
    expect(submitTag(render()), 'a ranked pick').not.toMatch(DISABLED_ATTR)
  })

  it('offers the merge over the WHOLE ranking, not the shown three, and echoes what is learned', () => {
    scriptState({ journey: rankedFixture() })
    const html = render()
    // harbouryard is a merge candidate the picker never showed — the twin of a
    // top candidate routinely sits below the cut, so a merge reachable only
    // from what is on screen cannot fix the split it exists for.
    expect(html).toContain('harbouryard')
    expect(html).toContain('Already one thing: greenlantern = lantern')
  })
})

describe('driven component — the ranked answer reaches the core', () => {
  function postBodies(spy: ReturnType<typeof vi.fn>): string[] {
    return spy.mock.calls
      .filter(([url]) => String(url).endsWith('/api/onboarding'))
      .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''))
  }

  function stubFetch(): ReturnType<typeof vi.fn> {
    const spy = vi.fn(async (url: RequestInfo | URL) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome', revision: 4 } }) }
    ))
    vi.stubGlobal('fetch', spy)
    return spy
  }

  it('sends the pick, and never a bare action the core would only refuse', async () => {
    const spy = stubFetch()
    scriptState({ journey: rankedFixture(), salienceChoice: 'blueharbour' })
    // ONE driveTree per scriptState: each render walks the scripted hook order
    // from the cursor it left, so a second invocation runs off the end.
    const tree = driveTree()
    expect(findByText(tree, 'button', 'Go deep on that one')).toBeDefined()
    const form = tree.find((el) => el.type === 'form')
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
    await flush(); await flush()
    const [body] = postBodies(spy)
    expect(body).toContain('"action":"answer_salience"')
    expect(body).toContain('"choice":"blueharbour"')
    expect(body).not.toContain('"name"')
  })

  it('sends the typed name with the escape hatch, plus the merge when one is given', async () => {
    const spy = stubFetch()
    scriptState({
      journey: rankedFixture(),
      salienceChoice: 'other',
      salienceName: 'Harbour Yard',
      salienceMerge: ['blueharbour', 'harbouryard'],
    })
    const form = driveTree().find((el) => el.type === 'form')
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
    await flush(); await flush()
    const [body] = postBodies(spy)
    expect(body).toContain('"choice":"other"')
    expect(body).toContain('"name":"Harbour Yard"')
    expect(body).toContain('"same_as":["blueharbour","harbouryard"]')
  })

  it('the option button POINTS AT the picker instead of firing a bare answer', async () => {
    const spy = stubFetch()
    scriptState({ journey: rankedFixture() })
    const option = findByText(driveTree(), 'button', 'Point me at the one to open first')
    ;(option.props.onClick as () => void)()
    await flush(); await flush()
    expect(
      postBodies(spy),
      'a bare answer_salience was POSTed — that is the dead end, not the fix'
    ).toEqual([])
  })

  it('the identity option POINTS AT its picker instead of firing a bare handles-less action', async () => {
    const spy = stubFetch()
    const fixture = journeyFixture('orientation_offered')
    fixture.card.entry = identityEntry([
      {
        connector: 'tracker',
        rows: 400,
        candidates: [{ identifier: 'a.operator@example.com', rows: 300 }],
        reports_no_actor: false,
        accounts: 1,
        withheld: 0,
        complete: true,
        note: 'tracker: 1 account across 400 rows',
      },
    ])
    fixture.card.options = [
      { action: 'record_operator_identity', label: 'Tell me which account is you', input: 'handles' },
    ]
    scriptState({ journey: fixture })
    const option = findByText(driveTree(), 'button', 'Tell me which account is you')
    ;(option.props.onClick as () => void)()
    await flush(); await flush()
    expect(
      postBodies(spy),
      'a bare record_operator_identity was POSTed — the core can only refuse it'
    ).toEqual([])
  })

  it('still sends bare when the control does not exist, so the core says what is missing', async () => {
    // A quiet no-op is the same dead end by a politer route: with no picker on
    // the card the operator must get the core's own sentence about why not.
    const spy = stubFetch()
    const fixture = journeyFixture('orientation_offered')
    fixture.card.options = [
      { action: 'answer_salience', label: 'Point me at the one to open first', input: 'choice' },
    ]
    scriptState({ journey: fixture })
    const option = findByText(driveTree(), 'button', 'Point me at the one to open first')
    ;(option.props.onClick as () => void)()
    await flush(); await flush()
    expect(postBodies(spy)[0]).toContain('"action":"answer_salience"')
  })
})

// ---------------------------------------------------------------------------
// THE OFF-TARGET REFUSAL, AND THE TWO STATEMENTS THAT ANSWER IT.
// ---------------------------------------------------------------------------

describe('driven component — an off-target window is answerable', () => {
  function refusingFetch(payload: Record<string, unknown>): ReturnType<typeof vi.fn> {
    const spy = vi.fn(async (url: RequestInfo | URL) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: false, status: 400, json: async () => payload }
    ))
    vi.stubGlobal('fetch', spy)
    return spy
  }

  function proposeOffTarget(payload: Record<string, unknown>): void {
    const fixture = journeyFixture('welcome')
    fixture.state.salience = { target: 'blueharbour' }
    scriptState({ journey: fixture, source: '/Users/x/quarterly-tax-returns' })
    const form = driveTree().find((el) => el.type === 'form')
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
  }

  it('builds the ask from the state it already holds when the refusal carries no detail', async () => {
    // What production returns today: journey._cli prints {ok, code, error} and
    // drops JourneyError.detail, so a surface that could only render from a
    // detail block would render nothing at the one refusal that needs it.
    refusingFetch({ ok: false, code: 'salience_window_off_target', error: 'You pointed me at blueharbour…' })
    proposeOffTarget({})
    await flush(); await flush()
    expect(settersFor(STATE.relationAsk)).toEqual([
      { target: 'blueharbour', window: 'quarterly-tax-returns', relations: ['same_thing', 'elsewhere'] },
    ])
  })

  it("prefers the core's own words when the refusal does carry them", async () => {
    refusingFetch({
      ok: false,
      code: 'salience_window_off_target',
      error: 'You pointed me at blueharbour…',
      detail: { target: 'harbour yard', window: 'tax-2026', relations: ['elsewhere'] },
    })
    proposeOffTarget({})
    await flush(); await flush()
    expect(settersFor(STATE.relationAsk)).toEqual([
      { target: 'harbour yard', window: 'tax-2026', relations: ['elsewhere'] },
    ])
  })

  it('drops a relation this surface cannot state rather than offering a button that must fail', async () => {
    refusingFetch({
      ok: false,
      code: 'salience_window_off_target',
      error: '…',
      detail: { relations: ['elsewhere', 'probably', 'constructor', '__proto__'] },
    })
    proposeOffTarget({})
    await flush(); await flush()
    expect(settersFor(STATE.relationAsk)).toEqual([
      { target: 'blueharbour', window: 'quarterly-tax-returns', relations: ['elsewhere'] },
    ])
  })

  it('asks nothing on any OTHER refusal', async () => {
    refusingFetch({ ok: false, code: 'purpose_too_long', error: 'Keep it under 300 characters.' })
    proposeOffTarget({})
    await flush(); await flush()
    expect(settersFor(STATE.relationAsk)).toEqual([])
    // send() clears the previous error before every action, so the trailing
    // value is the refusal and the leading null is that clear.
    expect(settersFor(STATE.error)).toEqual([null, 'Keep it under 300 characters.'])
  })

  it('re-proposes the same window carrying the statement the operator made', async () => {
    const spy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'charter_pending', revision: 4 } }) }
    ))
    vi.stubGlobal('fetch', spy)
    const fixture = journeyFixture('welcome')
    fixture.state.salience = { target: 'blueharbour' }
    scriptState({
      journey: fixture,
      source: '/Users/x/quarterly-tax-returns',
      relationAsk: {
        target: 'blueharbour',
        window: 'quarterly-tax-returns',
        relations: ['same_thing', 'elsewhere'],
      },
    })
    const button = driveTree().find(
      (el) => el.type === 'button' && el.props.name === 'dashboard-relation-elsewhere'
    )
    expect(button, 'the elsewhere statement had no control').toBeDefined()
    ;(button!.props.onClick as () => void)()
    await flush(); await flush()
    const body = spy.mock.calls
      .filter(([url]) => String(url).endsWith('/api/onboarding'))
      .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''))[0]
    expect(body).toContain('"action":"propose_window"')
    expect(body).toContain('"salience_relation":"elsewhere"')
    expect(body).toContain('/Users/x/quarterly-tax-returns')
  })

  it('renders both statements, naming the target and the folder', () => {
    const fixture = journeyFixture('welcome')
    fixture.state.salience = { target: 'blueharbour' }
    scriptState({
      journey: fixture,
      relationAsk: {
        target: 'blueharbour',
        window: 'quarterly-tax-returns',
        relations: ['same_thing', 'elsewhere'],
      },
    })
    const html = render()
    expect(html).toContain('name="dashboard-relation-same_thing"')
    expect(html).toContain('name="dashboard-relation-elsewhere"')
    expect(html).toContain('blueharbour')
    expect(html).toContain('quarterly-tax-returns')
  })
})

// ---------------------------------------------------------------------------
// THE PART OF THE RECEIPT THAT IS NOT THERE.
//
// The core replaces the words of any citation whose source is not the
// operator's and says so on the card (`card.egress.withheld`). Telegram has
// rendered that since the verdict existed; this surface showed the survivors
// and said nothing, which is a quieter lie than a refusal.
// ---------------------------------------------------------------------------

describe('rendered component — withheld citations are disclosed', () => {
  function withEgress(withheld: number, items: number): OnboardingResponse {
    const fixture = journeyFixture('dividend_ready')
    fixture.card.evidence = [
      { path: 'notes/release.md', line: 12, excerpt: 'a line the operator owns', sha256: 'a'.repeat(64) },
      { path: 'client/contract.md', line: 3, excerpt: '', sha256: 'b'.repeat(64), withheld_reason: 'THE-WITHHELD-EXCERPT' },
    ]
    fixture.card.egress = {
      ownership: 'third_party',
      disposition: 'per_item_approval',
      items,
      withheld,
      approved: [],
    }
    return fixture
  }

  it('says how much is held back, and never reconstructs it', () => {
    scriptState({ journey: withEgress(1, 2) })
    const html = render()
    expect(html).toContain('holding back the words of 1 of 2 citation')
    expect(html).toContain('reclassify the source if I have it wrong')
    // The verdict is RENDERED, never decided or undone here: the count crosses,
    // the withheld words never do.
    expect(html).not.toContain('THE-WITHHELD-EXCERPT')
  })

  it('says nothing when nothing was withheld — a false alarm is its own defect', () => {
    scriptState({ journey: withEgress(0, 2) })
    expect(render()).not.toContain('holding back the words')
  })

  it('says nothing when the core attached no verdict at all', () => {
    const fixture = journeyFixture('dividend_ready')
    fixture.card.evidence = [
      { path: 'notes/release.md', line: 12, excerpt: 'mine', sha256: 'a'.repeat(64) },
    ]
    scriptState({ journey: fixture })
    expect(render()).not.toContain('holding back the words')
  })
})

// ---------------------------------------------------------------------------
// THE FOLDER FIELD — root-caused by execution, not by reading.
//
// Measured on a fresh hatch (2026-07-30, CDP-driven): the folder field lost a
// programmatically-set value while every sibling field kept it, and the
// submitted proposal carried the '~/Documents' DEFAULT — the operator approved
// a Charter over a folder they never chose. The report attributed it to an
// effect re-syncing the field on a polling refresh.
//
// THE COMPONENT HAS NO POLL AND NO SUCH EFFECT. `load()` runs once on mount and
// again only on a 409, and neither writes this field; the arms below execute
// that rather than assert it. What the arms DO establish is the mechanism: the
// field is controlled, the submitted payload is read from STATE, and state has
// exactly four writers. A programmatic write that does not reach React's
// onChange therefore leaves state at its default, any later re-render repaints
// the stale value over the DOM (the "reverted within seconds"), and the submit
// carries the default (the "sticky" ~/Documents). That is an automation
// artifact of a controlled input, not a poll — and a human typing cannot hit
// it, because a keystroke IS the onChange.
//
// The pre-fill clobber is real regardless and is fixed: re-opening the scope
// form used to overwrite whatever the operator had entered with the stored
// proposal, unconditionally.
// ---------------------------------------------------------------------------

/** charter_pending, holding a proposal over a folder that is NOT what is typed. */
function journeyWithProposal(root: string): OnboardingResponse {
  const fixture = journeyFixture('charter_pending')
  fixture.state.source = {
    kind: 'folder',
    root,
    label: root.split('/').pop() || root,
    status: 'proposed',
    ownership: 'self',
    authority_basis: 'my own machine',
  }
  fixture.state.purpose = 'Find one useful thing I may be missing.'
  fixture.card.options = [
    { action: 'ratify_charter', label: 'Approve and find one useful thing' },
    { action: 'propose_window', label: 'Change it' },
    { action: 'purge', label: 'Delete onboarding data', danger: true },
  ] as OnboardingOption[]
  return fixture
}

function clickOption(label: string, overrides: Parameters<typeof scriptState>[0]): void {
  scriptState(overrides)
  const button = findByText(driveTree(), 'button', label)
  ;(button.props.onClick as () => void)()
}

describe('driven component — a typed folder survives the scope form re-opening', () => {
  it('NEVER overwrites a folder the operator has entered', () => {
    clickOption('Change it', {
      journey: journeyWithProposal('/var/data/somewhere-else'),
      source: '/home/me/quarterly-review',
      sourceEdited: true,
    })
    expect(
      settersFor(STATE.source),
      'the operator had typed a folder; re-opening the form replaced it with the ' +
        'stored proposal, and the next submit would carry a path they never chose'
    ).toEqual([])
    // …and the form still opens. A no-clobber rule that closed the door instead
    // would be the same dead end by a quieter route.
    expect(settersFor(STATE.editScope)).toEqual([true])
  })

  it('still pre-fills from the last proposal while the field is PRISTINE', () => {
    clickOption('Change it', {
      journey: journeyWithProposal('/var/data/somewhere-else'),
      sourceEdited: false,
    })
    expect(
      settersFor(STATE.source),
      '"Change it" must start from what is already approved, or the operator ' +
        'retypes a path the cabinet already knows'
    ).toEqual(['/var/data/somewhere-else'])
  })
})

describe('driven component — the folder that is submitted is the folder in state', () => {
  it('sends the state value verbatim, which is why a write that misses onChange is lost', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'charter_pending' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({ journey: journeyFixture('welcome'), source: '/home/me/quarterly-review' })
    const form = driveTree().find(
      (el) => el.type === 'form' && typeof el.props.onSubmit === 'function' && !el.props.ref
    )
    expect(form, 'the scope form is not in the tree').toBeDefined()
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
    await flush(); await flush()
    const action = fetchSpy.mock.calls.find(([url]) => String(url).endsWith('/api/onboarding'))
    expect(action, 'the proposal was never POSTed').toBeDefined()
    const body = String((action![1] as RequestInit | undefined)?.body ?? '')
    expect(body).toContain('"action":"propose_window"')
    expect(body).toContain('"source":"/home/me/quarterly-review"')
  })

  it('has no recurring refresh at all, so no timer can repaint the field', () => {
    // The measured symptom was blamed on a poll. There is none: assert it on
    // the source, both as the absence of a scheduler and as the enumeration of
    // every writer of the field.
    expect(component).not.toMatch(/setInterval|requestAnimationFrame/)
    const writers = [...component.matchAll(/setSource\(/g)]
    expect(
      writers.length,
      'setSource has exactly four sanctioned writers: the field\'s own onChange, ' +
        'the explicit "Use my Documents" reset, the pristine-only pre-fill, and ' +
        'the reset after the journey it belonged to is deleted or restarted'
    ).toBe(4)
    expect(component).toContain('if (!sourceEdited && journey?.state.source?.root) setSource(')
  })
})

describe('rendered + driven component — a purge is survivable', () => {
  /** The purged card, exactly as the core composes it. */
  function purgedJourney(): OnboardingResponse {
    const fixture = journeyFixture('purged')
    fixture.card.title = 'Onboarding data was deleted'
    fixture.card.body =
      'The Charter, onboarding history, bounded manifest, derived excerpts, and live ' +
      'evidence trial were removed. Stale actions cannot reopen them. You can start a ' +
      'new orientation whenever you like.'
    fixture.card.status = 'complete'
    fixture.card.options = [
      { action: 'start_again', label: 'Start a new orientation' },
    ] as OnboardingOption[]
    return fixture
  }

  it('renders the way back in on the purged card', () => {
    scriptState({ journey: purgedJourney() })
    const html = render()
    expect(
      html,
      'the purged card offered nothing at all, so deleting your data ended ' +
        'onboarding on the instance'
    ).toContain('Start a new orientation')
  })

  it('POSTs start_again when that control is used', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    clickOption('Start a new orientation', { journey: purgedJourney() })
    await flush(); await flush()
    const body = String(fetchSpy.mock.calls
      .map(([, init]) => (init as RequestInit | undefined)?.body ?? '')
      .find((value) => String(value).includes('/api/onboarding') || String(value).includes('start_again')) ?? '')
    expect(body).toContain('"action":"start_again"')
  })

  it('the confirm dialog says what is destroyed, what is kept, and what comes after', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true })
    const html = render()
    expect(html).toContain('Destroyed, permanently')
    expect(html).toContain('Kept on purpose')
    expect(html).toContain('the content-free record that a read happened')
    expect(
      html,
      'the operator armed an irreversible deletion without being told they ' +
        'could ever onboard again — and for a while they could not'
    ).toContain('you can start a new orientation')
  })
})

describe('rendered component — the Charter names the folder it will read', () => {
  it('wraps the card body so a long path is never clipped out of view', () => {
    const fixture = journeyFixture('charter_pending')
    fixture.card.body =
      'Read-only access to “deep” (/Users/someone/a/very/long/nested/path/to/deep) ' +
      'for this purpose: find one useful thing.'
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('/Users/someone/a/very/long/nested/path/to/deep')
    // The sentence the read is consented to must reflow, not overflow.
    expect(html).toMatch(/class="[^"]*break-words[^"]*"[^>]*>Read-only access to/)
  })
})
