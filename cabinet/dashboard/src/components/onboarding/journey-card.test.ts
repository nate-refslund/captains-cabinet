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
import type { OnboardingResponse } from '@/lib/onboarding/types'

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

import OnboardingJourneyCard from './journey-card'

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

/**
 * Script the component's 12 useState calls, in source order, with overrides.
 * Initial values are asserted against the component's real ones so drift is
 * loud (see hookScript mock above).
 */
function scriptState(overrides: {
  journey?: OnboardingResponse
  loading?: boolean
  working?: boolean
  purgeArmed?: boolean
  purgeConfirmation?: string
  ownership?: string
  authorityBasis?: string
  seed?: string
  feedbackRecorded?: string | null
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
    { initial: '~/Documents' }, // source
    { initial: 'Find one useful thing I may be missing.' }, // purpose
    { initial: 'reversible' }, // destination
    { initial: '', value: overrides.ownership ?? '' }, // ownership — no default BY DESIGN
    { initial: '', value: overrides.authorityBasis ?? '' }, // authorityBasis
    { initial: '', value: overrides.seed ?? '' }, // seed — the seed question's field
    { initial: null, value: overrides.feedbackRecorded ?? null }, // feedbackRecorded
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
// landed between destination (10) and feedbackRecorded, which moved to 13.
const STATE = { error: 3, ownership: 11, authorityBasis: 12, seed: 13, feedbackRecorded: 14 } as const

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
      next_actions: [{ action: 'propose_window', label: 'Choose a folder I may read' }],
    }
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('What I went and looked for')
    expect(html).toContain('docs/payments.md')
    expect(html).toContain('did not run')
    expect(html).toContain('no egress in the onboarding core')
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
