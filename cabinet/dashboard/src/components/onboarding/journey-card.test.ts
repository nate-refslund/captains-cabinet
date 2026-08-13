/**
 * Three layers of guarantee, explicitly scoped:
 *
 * 1. RENDER TESTS (`rendered component` below) — execute the REAL component
 *    through react-dom/server and assert on its rendered output: the stepped
 *    front (one question per step, the progress rail, Back/Next), the typed
 *    purge confirmation gate (destructive submit stays disabled until the
 *    Captain types exactly PURGE) and the feedback claim gate ("Feedback
 *    recorded" renders only from confirmed state). A dead or rewired gate
 *    fails these; a source grep alone would not.
 *
 * 2. DRIVEN TESTS (`driven component` below) — invoke the component's real
 *    onSubmit/onClick closures against a stubbed fetch and setter spies:
 *    the three answers reach the ONE answer_seed action; Next/Back move the
 *    step without touching the answers; the confirmed purge is POSTed without
 *    a post-purge ui observation; feedback is claimed only after the evidence
 *    endpoint confirms preservation.
 *
 *    Full click-through DOM tests (@testing-library/react + jsdom/happy-dom)
 *    are NOT a dependency here and vitest runs in the 'node' environment, so
 *    step state is injected via a hook-scripted useState (loudly order-guarded
 *    below) and the stepping LOGIC is pinned separately, framework-free, in
 *    wizard.test.ts.
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
  OnboardingResponse,
} from '@/lib/onboarding/types'

// Hook-scripted state injection: react-dom/server renders initial state only,
// so stateful scenarios are reached by overriding useState returns in call
// order, and handlers are driven by calling the component function directly.
// Every scripted useState call asserts the initial value the component actually
// passed, so a hook reorder/add/remove in journey-card.tsx fails LOUDLY here
// instead of silently testing the wrong state.
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

// The two server actions the connect step calls. Mocked so a driven test can
// assert the ORCHESTRATION (credential stored, then declared, then swept)
// without a real filesystem or auth — the credential value must reach
// saveConnectorCredential and NOT the declare_connector fetch body, and that is
// exactly what these let us check.
const serverActions = vi.hoisted(() => ({
  saveConnectorCredential: vi.fn(
    async (_key: string, _value: string): Promise<{ success: boolean; error?: string }> => ({
      success: true,
    })
  ),
  getConnectorCatalog: vi.fn(
    async (): Promise<ConnectorCatalog> => ({ templates: [], categories: [] })
  ),
}))
vi.mock('@/actions/env', () => ({
  saveConnectorCredential: serverActions.saveConnectorCredential,
}))
vi.mock('@/actions/connectors', () => ({
  getConnectorCatalog: serverActions.getConnectorCatalog,
}))

import OnboardingJourneyCard, {
  IDENTITY_SHOWN,
  NO_FIELDS,
  NO_IDENTITY_PICKS,
  NO_MERGE,
  plainReason,
  sweepLine,
} from './journey-card'
import type { ConnectorCatalog, OnboardingSweptConnector } from '@/lib/onboarding/types'

afterEach(() => {
  hookScript.steps = null
  hookScript.cursor = 0
  hookScript.setterCalls = []
  serverActions.saveConnectorCredential.mockClear()
  serverActions.getConnectorCatalog.mockClear()
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

/** The catalog a loaded fetch would return: two named tools on two shelves —
 *  one single-credential, one with its own how-to steps — and the open template
 *  that asks for its own fields. */
function connectCatalog(): ConnectorCatalog {
  return {
    templates: [
      {
        id: 'github',
        label: 'GitHub',
        summary: 'The repositories your account can see, most-recently-updated first.',
        host: 'api.github.com',
        credential_env: 'GITHUB_TOKEN',
        credential_help: 'A GitHub personal access token.',
        fields: [],
        category: 'code',
        category_label: 'Where your code lives',
        how_to_connect: [
          'Open Settings, then Developer settings, then Personal access tokens.',
          'Generate a fine-grained token with Read-only access and nothing else.',
        ],
        key_looks_like: 'starts with github_pat_',
      },
      {
        id: 'stripe',
        label: 'Stripe',
        summary: 'The products in your Stripe account.',
        host: 'api.stripe.com',
        credential_env: 'STRIPE_API_KEY',
        credential_help: 'A Stripe restricted API key.',
        fields: [],
        category: 'finance',
        category_label: 'Money in and out',
        how_to_connect: ['Create a restricted key and set Products to Read.'],
        key_looks_like: 'starts with rk_live_',
      },
      {
        id: 'rest',
        label: 'Another REST list',
        summary: 'Any HTTPS GET that returns a JSON list.',
        host: '',
        credential_env: 'REST_API_TOKEN',
        credential_help: 'The bearer token the endpoint expects.',
        fields: [
          { key: 'url', label: 'List URL', help: 'The full https:// URL.', placeholder: 'https://…', required: true },
          { key: 'name_field', label: 'Name field', help: 'Dotted path.', placeholder: 'name', required: true },
          { key: 'updated_field', label: 'Updated field', help: 'Dotted path.', placeholder: 'updated_at', required: true },
        ],
        category: 'other',
        category_label: 'Anything else',
        how_to_connect: [],
        key_looks_like: '',
      },
    ],
    categories: [
      { id: 'code', label: 'Where your code lives', count: 1 },
      { id: 'finance', label: 'Money in and out', count: 1 },
      { id: 'other', label: 'Anything else', count: 1 },
    ],
  }
}

/** One connector as a sweep found it — connected, or refused with its reason. */
function sweptRow(over: Partial<OnboardingSweptConnector> & { name: string }): OnboardingSweptConnector {
  return { connected: true, items: 12, calls: 2, latest: '2026-08-11T09:00:00Z', actors: 3, ...over }
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
  editScope?: boolean
  wizardStep?: string
  role?: string
  dream?: string
  startPreference?: string
  purgeArmed?: boolean
  purgeConfirmation?: string
  source?: string
  sourceEdited?: boolean
  ownership?: string
  authorityBasis?: string
  feedbackRecorded?: string | null
  handles?: Readonly<Record<string, string>>
  salienceChoice?: string
  salienceName?: string
  salienceMerge?: readonly string[]
  relationAsk?: unknown
  connectorCatalog?: ConnectorCatalog | null
  connectPick?: string
  connectCredential?: string
  connectFields?: Readonly<Record<string, string>>
  connectSearch?: string
  connectCategory?: string
  exploring?: boolean
}) {
  hookScript.cursor = 0
  hookScript.steps = [
    { initial: null, value: overrides.journey ?? null }, // 0 journey
    { initial: true, value: overrides.loading ?? false }, // 1 loading
    { initial: false, value: overrides.working ?? false }, // 2 working
    { initial: null }, // 3 error
    { initial: false }, // 4 collapsed
    { initial: false, value: overrides.editScope ?? false }, // 5 editScope
    { initial: 'role', value: overrides.wizardStep ?? 'role' }, // 6 wizardStep
    { initial: '', value: overrides.role ?? '' }, // 7 role — question one
    { initial: '', value: overrides.dream ?? '' }, // 8 dream — question two
    { initial: '', value: overrides.startPreference ?? '' }, // 9 startPreference — question three
    { initial: false, value: overrides.purgeArmed ?? false }, // 10 purgeArmed
    { initial: '', value: overrides.purgeConfirmation ?? '' }, // 11 purgeConfirmation
    { initial: '~/Documents', value: overrides.source ?? '~/Documents' }, // 12 source
    { initial: false, value: overrides.sourceEdited ?? false }, // 13 sourceEdited
    { initial: 'Find one useful thing I may be missing.' }, // 14 purpose (per-window)
    { initial: 'reversible' }, // 15 destination
    { initial: '', value: overrides.ownership ?? '' }, // 16 ownership — no default BY DESIGN
    { initial: '', value: overrides.authorityBasis ?? '' }, // 17 authorityBasis
    { initial: null, value: overrides.feedbackRecorded ?? null }, // 18 feedbackRecorded
    { initial: NO_IDENTITY_PICKS, value: overrides.handles ?? NO_IDENTITY_PICKS }, // 19 handles
    { initial: '', value: overrides.salienceChoice ?? '' }, // 20 salienceChoice — no default BY DESIGN
    { initial: '', value: overrides.salienceName ?? '' }, // 21 salienceName
    { initial: NO_MERGE, value: overrides.salienceMerge ?? NO_MERGE }, // 22 salienceMerge
    { initial: null, value: overrides.relationAsk ?? null }, // 23 relationAsk
    // The connect step (discover branch). connectorTemplates is null until the
    // client fetch lands — and that fetch is a useEffect, which this scripted
    // renderer does NOT run, so a test that wants tiles must pass them here.
    { initial: null, value: overrides.connectorCatalog ?? null }, // 24 connectorCatalog
    { initial: '', value: overrides.connectPick ?? '' }, // 25 connectPick
    { initial: '', value: overrides.connectCredential ?? '' }, // 26 connectCredential
    { initial: NO_FIELDS, value: overrides.connectFields ?? NO_FIELDS }, // 27 connectFields
    { initial: null }, // 28 connectError
    { initial: '', value: overrides.connectSearch ?? '' }, // 29 connectSearch
    { initial: '', value: overrides.connectCategory ?? '' }, // 30 connectCategory
    { initial: false, value: overrides.exploring ?? false }, // 31 exploring
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

// ---------------------------------------------------------------------------
// THE STEPPED FRONT — one question per step, a rail, Back/Next.
// ---------------------------------------------------------------------------
describe('rendered component — the stepped front', () => {
  it('opens on question one — what you do — with a textarea and a disabled Next', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'role', role: '' })
    const html = render()
    expect(html).toContain('Tell me about you and your work.')
    expect(html).toContain(`id="dashboard-role"`)
    // Next cannot advance an empty role — it is the seed the core will not skip.
    const nextTag = html.slice(html.lastIndexOf('<button', html.indexOf('Next')), html.indexOf('Next'))
    expect(nextTag).toMatch(DISABLED_ATTR)
  })

  it('enables Next once a role is entered', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'role', role: 'a shopkeeper' })
    const html = render()
    const nextTag = html.slice(html.lastIndexOf('<button', html.indexOf('Next')), html.indexOf('Next'))
    expect(nextTag).not.toMatch(DISABLED_ATTR)
  })

  it('asks the dream as its own step, and lets it be skipped', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'dream', role: 'a shopkeeper', dream: '' })
    const html = render()
    expect(html).toContain('What would you love this Cabinet to become?')
    // Next is enabled with an empty dream — a role-only answer is honest.
    const nextTag = html.slice(html.lastIndexOf('<button', html.indexOf('Next')), html.indexOf('Next'))
    expect(nextTag).not.toMatch(DISABLED_ATTR)
    // And it can go Back — the questions are a sequence, not a wall.
    expect(html).toContain('>Back<')
  })

  it('asks where to begin with two branches, and disables Continue until one is chosen', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'start', role: 'a shopkeeper', startPreference: '' })
    const html = render()
    expect(html).toContain('Where should I begin?')
    expect(html).toContain('Point me somewhere')
    expect(html).toContain('Go find where you are most useful')
    const continueTag = html.slice(html.lastIndexOf('<button', html.indexOf('Continue')), html.indexOf('Continue'))
    expect(continueTag).toMatch(DISABLED_ATTR)
  })

  it('renders the progress rail with the phase for the current step lit', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'start' })
    const html = render()
    expect(html).toContain('Onboarding progress: step 3 of 6')
    expect(html).toContain('aria-current="step"')
  })

  it('shows the folder form as the point branch, with the consent facts intact', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'window' })
    const html = render()
    expect(html).toContain('Which folder may I read?')
    expect(html).toContain('Whose data is in this folder?')       // ownership, un-derivable
    expect(html).toContain('Under what right?')                    // authority basis
    expect(html).toContain('Show me the Charter first')
  })

  it('is honest on the decide branch when nothing is connected, and routes to the folder', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'discover' })
    const html = render()
    expect(html).toContain('Let me go and find where I fit')
    expect(html).toContain('I need something to read')
    expect(html).toContain('Point me at a folder instead')
    // No connector is offered, so no gather button is fabricated.
    expect(html).not.toContain('Read what I')
  })

  it('offers the real connector read on the decide branch when the core carries one', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.options = [{ action: 'gather_connectors', label: 'Read what I am connected to' }]
    scriptState({ journey: fixture, wizardStep: 'discover' })
    const html = render()
    expect(html).toContain('Read what I am connected to')
  })

  it('draws the connect catalog on the decide branch when tools are available', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
    })
    const html = render()
    expect(html).toContain('GitHub')
    expect(html).toContain('The repositories your account can see')
    expect(html).toContain('Another REST list')
    // Nothing picked yet ⇒ no credential field is revealed.
    expect(html).not.toContain('id="dashboard-connect-credential"')
  })

  it('reveals a password credential field and a host consent line once a tool is picked', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectPick: 'github',
    })
    const html = render()
    expect(html).toContain('id="dashboard-connect-credential"')
    expect(html).toContain('type="password"')
    // The consent line NAMES the host the credential will reach — the honest
    // confirmation the custody model owes the operator.
    expect(html).toContain('api.github.com')
    // Connect stays disabled until a credential is entered.
    const idx = html.lastIndexOf('Connect GitHub')
    const connectTag = html.slice(html.lastIndexOf('<button', idx), idx)
    expect(connectTag).toMatch(DISABLED_ATTR)
  })

  it('enables Connect once a credential is present', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectPick: 'github',
      connectCredential: 'ghp_secret_token',
    })
    const html = render()
    const idx = html.lastIndexOf('Connect GitHub')
    const connectTag = html.slice(html.lastIndexOf('<button', idx), idx)
    expect(connectTag).not.toMatch(DISABLED_ATTR)
  })

  it('asks the open template for its own fields', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectPick: 'rest',
    })
    const html = render()
    expect(html).toContain('List URL')
    expect(html).toContain('id="dashboard-connect-url"')
  })
})

// ---------------------------------------------------------------------------
// THE CATALOG — browsable, searchable, and honest about what it is holding back
// ---------------------------------------------------------------------------
describe('rendered component — the connector catalog', () => {
  it('draws a search field and one shelf per populated category', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
    })
    const html = render()
    expect(html).toContain('id="dashboard-connect-search"')
    expect(html).toContain('Where your code lives')
    expect(html).toContain('Money in and out')
    expect(html).toContain('Everything')
    // Every tool in a small pack is on the page; nothing is picked yet, so no
    // credential field is revealed.
    expect(html).toContain('GitHub')
    expect(html).toContain('Stripe')
    expect(html).not.toContain('id="dashboard-connect-credential"')
  })

  it('narrows to one shelf without hiding that it has narrowed', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectCategory: 'finance',
    })
    const html = render()
    expect(html).toContain('Stripe')
    expect(html).not.toContain('The repositories your account can see')
    expect(html).toContain('1 of 3 tools')
  })

  it('searches over what a tool holds, not only its name', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectSearch: 'repositories',
    })
    const html = render()
    expect(html).toContain('GitHub')
    expect(html).not.toContain('The products in your Stripe account')
  })

  it('routes a search that matches nothing to the open template, never a dead end', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectSearch: 'no-such-tool-anywhere',
    })
    const html = render()
    expect(html).toContain('Nothing here matches that')
    expect(html).toContain('Another REST list')
  })

  it('shows the steps for getting the key, and what a right key looks like', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectPick: 'github',
    })
    const html = render()
    expect(html).toContain('How to get the key')
    // An ordered list, because the steps are a sequence — the key cannot be
    // copied before it is made.
    expect(html).toContain('<ol')
    expect(html).toContain('Generate a fine-grained token with Read-only access')
    expect(html).toContain('starts with github_pat_')
  })
})

// ---------------------------------------------------------------------------
// MANY TOOLS — the step stays open, and each tool carries its own state
// ---------------------------------------------------------------------------
describe('rendered component — connecting many tools', () => {
  it('lists what is connected with each tool own sweep state, and offers the look across all of them', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.options = [{ action: 'gather_connectors', label: 'Read what I am connected to' }]
    fixture.state.connector_sweep = {
      schema: 'cabinet.connector-sweep/v1',
      swept_at: '2026-08-13T09:30:00Z',
      declared: 3,
      calls: 6,
      connectors: [
        sweptRow({ name: 'github', items: 12 }),
        sweptRow({ name: 'stripe', items: 4, latest: '2026-08-12T10:00:00Z' }),
        sweptRow({ name: 'rest', connected: false, items: 0, reason: 'http_401' }),
      ],
    }
    scriptState({
      journey: fixture,
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
    })
    const html = render()
    expect(html).toContain('Connected so far (3)')
    expect(html).toContain('read 12 things')
    expect(html).toContain('newest 2026-08-12')
    // The refused key is reported against ITS tool, with a plain retry, while
    // the other two report their counts beside it.
    expect(html).toContain('the key was refused')
    expect(html).toContain('Try a different key')
    // One act covers all three, and the button says so.
    expect(html).toContain('Go look across all 3')
  })

  it('keeps the catalog open after a connect instead of replacing it with the results', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.options = [{ action: 'gather_connectors', label: 'Read what I am connected to' }]
    fixture.state.connector_sweep = {
      schema: 'cabinet.connector-sweep/v1',
      swept_at: '2026-08-13T09:30:00Z',
      declared: 1,
      calls: 2,
      connectors: [sweptRow({ name: 'github' })],
    }
    fixture.card.entry = identityEntry([
      { connector: 'github', rows: 4, candidates: [{ identifier: 'ada', rows: 4 }], reports_no_actor: false, accounts: 1, withheld: 0, complete: true, note: '' },
    ])
    scriptState({
      journey: fixture,
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
    })
    const html = render()
    // The step is still the step: another tool can still be added.
    expect(html).toContain('Connect another tool')
    expect(html).toContain('id="dashboard-connect-search"')
    // …and the post-look sections have NOT taken over yet.
    expect(html).not.toContain('What I found across')
  })

  it('shows the aggregate, per connector, once the operator asks for the look', () => {
    const fixture = journeyFixture('welcome')
    fixture.state.connector_sweep = {
      schema: 'cabinet.connector-sweep/v1',
      swept_at: '2026-08-13T09:30:00Z',
      declared: 2,
      calls: 4,
      connectors: [
        sweptRow({ name: 'github', items: 12, actors: 3 }),
        sweptRow({ name: 'stripe', connected: false, items: 0, reason: 'credential_absent' }),
      ],
    }
    scriptState({
      journey: fixture,
      wizardStep: 'discover',
      exploring: true,
      connectorCatalog: connectCatalog(),
    })
    const html = render()
    expect(html).toContain('What I found across all 2')
    expect(html).toContain('read 12 things')
    expect(html).toContain('3 accounts')
    expect(html).toContain('no key is stored for it yet')
    expect(html).toContain('Read 2026-08-13')
  })
})

// ---------------------------------------------------------------------------
// The sweep sentence, unit-tested — a diagnostic code is not an explanation.
// ---------------------------------------------------------------------------
describe('sweep state, in the operator words', () => {
  it('translates the reasons an operator can act on', () => {
    expect(plainReason('credential_absent')).toContain('no key')
    expect(plainReason('http_401')).toContain('refused')
    expect(plainReason('http_403')).toContain('refused')
    expect(plainReason('http_404')).toContain('not found')
    expect(plainReason('http_503')).toContain('error of its own')
    expect(plainReason('egress_closed')).toContain('switched off')
    expect(plainReason('read_only_refused:url_not_https')).toContain('not a read')
  })

  it('passes an unrecognised reason through readably rather than swallowing it', () => {
    // An unknown code printed plainly is still a fact; a generic "something
    // went wrong" is not, and is how a diagnosable failure becomes a mystery.
    expect(plainReason('some_new_reason')).toBe('some new reason')
    expect(plainReason('')).toBe('it did not answer')
  })

  it('counts what was read, and says nothing it did not measure', () => {
    expect(sweepLine({ name: 'x', connected: true, items: 1, calls: 1, latest: null }))
      .toBe('read 1 thing')
    expect(sweepLine({ name: 'x', connected: true, items: 9, calls: 1, latest: '2026-08-01T00:00:00Z', actors: 2 }))
      .toBe('read 9 things · newest 2026-08-01 · 2 accounts')
  })
})

// ---------------------------------------------------------------------------
// DRIVEN — the three answers reach ONE action, and stepping keeps them.
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
const STATE = {
  error: 3,
  editScope: 5,
  wizardStep: 6,
  role: 7,
  dream: 8,
  startPreference: 9,
  source: 12,
  sourceEdited: 13,
  ownership: 16,
  feedbackRecorded: 18,
  salienceChoice: 20,
  relationAsk: 23,
  connectPick: 25,
  connectCredential: 26,
  connectFields: 27,
} as const

function settersFor(index: number): unknown[] {
  return hookScript.setterCalls.filter((call) => call.index === index).map((call) => call.value)
}

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('driven component — the three questions round-trip into the core', () => {
  it('sends role, dream and preference as ONE answer_seed, on the seams the core reads', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome', revision: 4 }, state: { stage: 'welcome' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'start',
      role: 'I run a small ryokan',
      dream: 'A calmer front desk',
      startPreference: 'point',
    })
    const tree = driveTree()
    const cont = findByText(tree, 'button', 'Continue')
    ;(cont.props.onClick as () => void)()
    await flush(); await flush()

    const action = fetchSpy.mock.calls
      .map(([url, init]) => ({ url: String(url), body: String((init as RequestInit | undefined)?.body ?? '') }))
      .find((call) => call.url.endsWith('/api/onboarding'))
    expect(action, 'answer_seed was never POSTed').toBeDefined()
    expect(action!.body).toContain('"action":"answer_seed"')
    expect(action!.body).toContain('"seed":"I run a small ryokan"')     // role -> seed seam
    expect(action!.body).toContain('"purpose":"A calmer front desk"')   // dream -> mission.purpose seam
    expect(action!.body).toContain('"start_preference":"point"')        // the one new field
  })

  it('omits the dream from the payload when it was left blank', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome', revision: 4 }, state: { stage: 'welcome' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'start', role: 'a shopkeeper', dream: '', startPreference: 'decide' })
    ;(findByText(driveTree(), 'button', 'Continue').props.onClick as () => void)()
    await flush(); await flush()
    const action = fetchSpy.mock.calls
      .map(([url, init]) => ({ url: String(url), body: String((init as RequestInit | undefined)?.body ?? '') }))
      .find((call) => call.url.endsWith('/api/onboarding'))
    expect(action!.body).toContain('"start_preference":"decide"')
    expect(action!.body).not.toContain('"purpose"')
  })

  it('connect stores the credential via the safe writer, declares the NAME, then sweeps', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome', revision: 4 }, state: { stage: 'welcome' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'discover',
      connectorCatalog: connectCatalog(),
      connectPick: 'github',
      connectCredential: 'ghp_the_secret_value',
    })
    const form = driveTree().find(
      (el) => el.type === 'form' && el.props['aria-label'] === 'Connect a tool'
    )
    expect(form, 'the connect form was not rendered').toBeDefined()
    await (form!.props.onSubmit as (e: { preventDefault(): void }) => Promise<void>)({
      preventDefault() {},
    })
    await flush(); await flush(); await flush()

    // 1. The credential VALUE went to the safe .env writer, under the template's
    //    env var NAME — and ONLY there.
    expect(serverActions.saveConnectorCredential).toHaveBeenCalledWith(
      'GITHUB_TOKEN',
      'ghp_the_secret_value'
    )
    const posts = fetchSpy.mock.calls
      .map(([url, init]) => ({ url: String(url), body: String((init as RequestInit | undefined)?.body ?? '') }))
      .filter((call) => call.url.endsWith('/api/onboarding'))
    // 2. declare_connector was POSTed carrying the env var NAME, NEVER the value.
    const declare = posts.find((p) => p.body.includes('"action":"declare_connector"'))
    expect(declare, 'declare_connector was never POSTed').toBeDefined()
    expect(declare!.body).toContain('"credential_env":"GITHUB_TOKEN"')
    expect(declare!.body).toContain('"template":"github"')
    expect(declare!.body).not.toContain('ghp_the_secret_value')
    // 3. The sweep ran straight after — and with the FRESH revision the declare
    //    returned (4), not the stale one this closure opened with (3). Measured
    //    live 2026-08-13: without this, the gather collided with the declare as a
    //    revision_conflict and the sweep never ran.
    const gather = posts.find((p) => p.body.includes('"action":"gather_connectors"'))
    expect(gather, 'gather_connectors was never POSTed').toBeDefined()
    expect(declare!.body).toContain('"expected_revision":3') // the opening revision
    expect(gather!.body).toContain('"expected_revision":4') // the one declare produced
    // 4. The credential was wiped from state once the declaration landed.
    expect(settersFor(STATE.connectCredential)).toContain('')
  })

  it('Next moves the step WITHOUT clearing the role already entered', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'role', role: 'I run a small ryokan' })
    ;(findByText(driveTree(), 'button', 'Next').props.onClick as () => void)()
    expect(settersFor(STATE.wizardStep)).toEqual(['dream'])
    expect(settersFor(STATE.role)).toEqual([])       // the answer is untouched
  })

  it('Back returns to the previous step and preserves every entered answer', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'start', role: 'a shopkeeper', dream: 'a calmer desk' })
    ;(findByText(driveTree(), 'button', 'Back').props.onClick as () => void)()
    expect(settersFor(STATE.wizardStep)).toEqual(['dream'])
    expect(settersFor(STATE.role)).toEqual([])
    expect(settersFor(STATE.dream)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// The purge gate — unchanged security surface, restyled chrome.
// ---------------------------------------------------------------------------
describe('rendered component — typed purge confirmation gate', () => {
  it('renders the armed purge form with the destructive submit DISABLED before PURGE is typed', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true, purgeConfirmation: '' })
    expect(purgeSubmitTag(render())).toMatch(DISABLED_ATTR)
  })

  it('keeps the destructive submit DISABLED for a wrong or lowercase confirmation', () => {
    for (const wrong of ['purge', 'PURG', 'PURGE ', 'DELETE']) {
      scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true, purgeConfirmation: wrong })
      expect(purgeSubmitTag(render()), `confirmation ${JSON.stringify(wrong)} must keep the button disabled`).toMatch(DISABLED_ATTR)
    }
  })

  it('enables the destructive submit only when the confirmation is exactly PURGE', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true, purgeConfirmation: 'PURGE' })
    expect(purgeSubmitTag(render())).not.toMatch(DISABLED_ATTR)
  })

  it('keeps the destructive submit disabled while an action is in flight even with PURGE typed', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true, purgeConfirmation: 'PURGE', working: true })
    expect(purgeSubmitTag(render())).toMatch(DISABLED_ATTR)
  })

  it('states what is destroyed, what is kept, and what happens next', () => {
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true })
    const html = render()
    expect(html).toContain('Destroyed, permanently:')
    expect(html).toContain('Kept on purpose:')
    expect(html).toContain('Afterwards:')
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

describe('driven component — typed purge submit', () => {
  it('posts the confirmed purge action and never reports a post-purge ui observation', async () => {
    const fetchSpy = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'purged' } }) }
    ))
    vi.stubGlobal('fetch', fetchSpy)
    scriptState({ journey: journeyFixture('dividend_ready'), purgeArmed: true, purgeConfirmation: 'PURGE' })
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

  it('surfaces the residual questions the sweep cannot answer, on the discover branch', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'ungranted',
      opening_move: 'residual_questions',
      grants: { connectors: [], local_files: false, web: false },
      seed_question: null,
      questions: [
        { id: 'rights', prompt: 'Which of these sources are yours to give me read access to?', why: 'No amount of access answers this.', required: true },
      ],
      discovery: { terms: [], probes: [], executable: false },
      cannot_know: [],
      identity_question: null,
      next_actions: [],
    }
    scriptState({ journey: fixture, wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain('What I cannot work out for myself')
    expect(html).toContain('yours to give me read access to')
    expect(html).toContain('No amount of access answers this.')
  })
})

// ---------------------------------------------------------------------------
// The ranked question is answerable — on the discover branch it belongs to.
// ---------------------------------------------------------------------------
function salienceJourney(): OnboardingResponse {
  const fixture = journeyFixture('welcome')
  fixture.card.options = [
    {
      action: 'answer_salience',
      label: 'Point me at the one to open first',
      input: 'choice',
      options: [
        { id: 'acme', label: 'Acme migration', why: 'named in acme/*, 41 rows' },
        { id: 'zephyr', label: 'Zephyr rollout', why: 'named in zephyr/*, 12 rows' },
        { id: 'other', label: 'None of these — I will name it', why: 'the shortlist is only as good as the sweep', input: 'seed' },
      ],
      merge: {
        field: 'same_as',
        question: 'Are two of these the same under different names?',
        candidates: [
          { id: 'acme', label: 'Acme migration' },
          { id: 'zephyr', label: 'Zephyr rollout' },
          { id: 'acme-2', label: 'Project Acme' },
        ],
        learned: [{ labels: ['Acme', 'Project A'] }],
      },
      not_reached: 'I could not reach the archive; a clean "nothing there" would be unearned.',
    },
  ]
  return fixture
}

describe('rendered component — the ranked question is answerable', () => {
  it('renders every candidate with the names behind its rank, escape hatch last', () => {
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain('Point me at the one to open first')
    expect(html).toContain('Acme migration')
    expect(html).toContain('named in acme/*, 41 rows')            // the WHY, never a bare score
    expect(html).toContain('None of these — I will name it')
    expect(html).toContain('Go deep on that one')
  })

  it('opens the typed field ONLY where the picked option needs one', () => {
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true, salienceChoice: 'acme' })
    expect(render()).not.toContain('What should I open instead?')
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true, salienceChoice: 'other' })
    expect(render()).toContain('What should I open instead?')
  })

  it('offers the merge over the WHOLE ranking and echoes what is learned', () => {
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain('Are two of these the same thing under different names?')
    expect(html).toContain('Project Acme')                        // a candidate below the shown three
    expect(html).toContain('Already one thing: Acme = Project A')
    expect(html).toContain('would be unearned')   // the not-reached line, quotes HTML-escaped
  })

  it('keeps the submit disabled until there is an answer to send', () => {
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true, salienceChoice: '' })
    const html = render()
    const tag = html.slice(html.lastIndexOf('<button', html.indexOf('Go deep on that one')), html.indexOf('Go deep on that one'))
    expect(tag).toMatch(DISABLED_ATTR)
  })
})

describe('driven component — the ranked answer reaches the core', () => {
  function stubOk() {
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: true, status: 200, json: async () => ({ ok: true, card: { stage: 'welcome' }, state: {} }) }
    )))
  }
  it('sends the pick, and never a bare action the core would only refuse', async () => {
    stubOk()
    const fetchSpy = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    scriptState({ journey: salienceJourney(), wizardStep: 'discover', exploring: true, salienceChoice: 'acme' })
    const forms = driveTree().filter((el) => el.type === 'form')
    const salienceForm = forms.find((f) => {
      let found = false
      for (const el of walk(f)) if (el.props?.name === 'dashboard-salience') found = true
      return found
    })
    expect(salienceForm, 'salience form not found').toBeDefined()
    ;(salienceForm!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
    await flush(); await flush()
    const action = (fetchSpy.mock.calls as unknown[][])
      .map((call) => ({ url: String(call[0]), body: String((call[1] as RequestInit | undefined)?.body ?? '') }))
      .find((c) => c.url.endsWith('/api/onboarding'))
    expect(action!.body).toContain('"action":"answer_salience"')
    expect(action!.body).toContain('"choice":"acme"')
  })
})

// ---------------------------------------------------------------------------
// The identity picker — over the connectors' own account identifiers.
// ---------------------------------------------------------------------------
describe('rendered component — the identity picker', () => {
  it('renders the picker over the connectors own account identifiers', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      {
        connector: 'plugin:dev-tasks',
        rows: 40,
        candidates: [
          { identifier: 'ada@acme.test', rows: 25 },
          { identifier: 'bob@acme.test', rows: 15 },
        ],
        reports_no_actor: false,
        accounts: 2,
        withheld: 0,
        complete: true,
        note: '',
      },
    ])
    scriptState({ journey: fixture, wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain('I cannot tell which of the actors I read is you.')
    expect(html).toContain('ada@acme.test')
    expect(html).toContain('25 of 40 here')
    expect(html).toContain('That one is me')
  })

  it('keeps the quietest account reachable instead of showing only the busiest', () => {
    const many = Array.from({ length: IDENTITY_SHOWN + 3 }, (_, i) => ({ identifier: `user${i}@acme.test`, rows: 30 - i }))
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      { connector: 'linear', rows: 200, candidates: many, reports_no_actor: false, accounts: many.length, withheld: 0, complete: true, note: '' },
    ])
    scriptState({ journey: fixture, wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain(`user${IDENTITY_SHOWN + 2}@acme.test`)          // behind the disclosure, still present
    expect(html).toContain(`Show the other 3 accounts in linear`)
  })

  it('opens a typed field only where the core says the offer cannot be completed', () => {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = identityEntry([
      { connector: 'linear', rows: 665, candidates: [{ identifier: 'a@x.test', rows: 5 }], reports_no_actor: false, accounts: 30, withheld: 22, complete: false, note: '' },
    ])
    scriptState({ journey: fixture, wizardStep: 'discover', exploring: true })
    expect(render()).toContain('type it exactly as linear spells it')
  })
})

// ---------------------------------------------------------------------------
// The discovery receipt — what ran, and what did not.
// ---------------------------------------------------------------------------
describe('rendered component — discovery is disclosed honestly', () => {
  function discoveryFixture(): OnboardingResponse {
    const fixture = journeyFixture('welcome')
    fixture.card.entry = {
      schema: 'cabinet.onboarding-entry-plan/v1',
      mode: 'seeded',
      opening_move: 'seed_then_discover',
      grants: { connectors: [], local_files: true, web: false },
      seed_question: null,
      questions: [],
      discovery: {
        terms: ['payments'],
        probes: [],
        executable: true,
        executed: {
          schema: 'cabinet.onboarding-probe-result/v1',
          executed: [
            { kind: 'local_name_match', pattern: '*payments*', matches: ['payments.md'], truncated: false },
            { kind: 'local_name_match', pattern: '*ledger*', matches: [], truncated: true },
          ],
          deferred: [{ kind: 'web_search', reason: 'no_web_grant' }],
          complete: false,
        },
      },
      cannot_know: [],
      identity_question: null,
      next_actions: [],
    }
    return fixture
  }

  it('renders what the probes found AND what did not run', () => {
    scriptState({ journey: discoveryFixture(), wizardStep: 'discover', exploring: true })
    const html = render()
    expect(html).toContain('What I went and looked for')
    expect(html).toContain('*payments*')
    expect(html).toContain('payments.md')
    expect(html).toContain('did not run — no web grant')
  })

  it('says when a search stopped at its limit instead of implying it finished', () => {
    scriptState({ journey: discoveryFixture(), wizardStep: 'discover', exploring: true })
    expect(render()).toContain('stopped at my limit before the end of the folder')
  })
})

// ---------------------------------------------------------------------------
// Withheld citations — disclosed, never reconstructed.
// ---------------------------------------------------------------------------
describe('rendered component — withheld citations are disclosed', () => {
  function dividendWithEgress(withheld: number, items: number, egress: boolean): OnboardingResponse {
    const fixture = journeyFixture('dividend_ready')
    fixture.card.evidence = [
      { path: 'notes/plan.md', line: 12, excerpt: 'the excerpt', sha256: 'abc' },
    ]
    if (egress) {
      fixture.card.egress = { ownership: 'third_party', disposition: 'per_item_approval', items, withheld, approved: [] }
    }
    return fixture
  }

  it('says how much is held back, and never reconstructs it', () => {
    scriptState({ journey: dividendWithEgress(2, 3, true) })
    const html = render()
    expect(html).toContain('I am holding back the words of 2 of 3 citations')
  })

  it('says nothing when nothing was withheld — a false alarm is its own defect', () => {
    scriptState({ journey: dividendWithEgress(0, 3, true) })
    expect(render()).not.toContain('I am holding back the words')
  })

  it('says nothing when the core attached no verdict at all', () => {
    scriptState({ journey: dividendWithEgress(0, 0, false) })
    expect(render()).not.toContain('I am holding back the words')
  })
})

// ---------------------------------------------------------------------------
// An off-target window is answerable, not a dead end.
// ---------------------------------------------------------------------------
describe('driven component — an off-target window is answerable', () => {
  function refuse(code: string, detail?: Record<string, unknown>) {
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => (
      String(url).endsWith('/api/onboarding/evidence')
        ? { ok: true, json: async () => ({ ok: true }) }
        : { ok: false, status: 400, json: async () => ({ ok: false, code, error: 'refused', ...(detail ? { detail } : {}) }) }
    )))
  }
  function submitWindow(over: Parameters<typeof scriptState>[0]) {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'window', source: '/home/me/garden', ownership: 'self', ...over })
    const form = driveTree().find((el) => el.type === 'form' && typeof el.props.onSubmit === 'function')
    ;(form!.props.onSubmit as (e: object) => void)({ preventDefault: () => undefined })
  }

  it('builds the ask from the state it already holds when the refusal carries no detail', async () => {
    refuse('salience_window_off_target')
    const withSalience = journeyFixture('welcome')
    withSalience.state.salience = { target: 'Acme migration' }
    submitWindow({ journey: withSalience })
    await flush(); await flush()
    const asks = settersFor(STATE.relationAsk)
    expect(asks).toHaveLength(1)
    expect((asks[0] as { target: string }).target).toBe('Acme migration')
    expect((asks[0] as { window: string }).window).toBe('garden')
  })

  it("prefers the core's own words when the refusal does carry them", async () => {
    refuse('salience_window_off_target', { target: 'Ledger cutover', window: 'ledger-2026', relations: ['same_thing', 'elsewhere'] })
    submitWindow({})
    await flush(); await flush()
    const ask = settersFor(STATE.relationAsk)[0] as { target: string; window: string }
    expect(ask.target).toBe('Ledger cutover')
    expect(ask.window).toBe('ledger-2026')
  })

  it('asks nothing on any OTHER refusal', async () => {
    refuse('some_other_refusal')
    submitWindow({})
    await flush(); await flush()
    expect(settersFor(STATE.relationAsk)).toEqual([])
  })

  it('renders both statements, naming the target and the folder', () => {
    scriptState({
      journey: journeyFixture('welcome'),
      wizardStep: 'window',
      relationAsk: { target: 'Acme migration', window: 'garden', relations: ['same_thing', 'elsewhere'] },
    })
    const html = render()
    expect(html).toContain('shares no word with it')
    expect(html).toContain('“garden” IS Acme migration, under another name')
    expect(html).toContain('That is somewhere else I want opened')
  })
})

// ---------------------------------------------------------------------------
// A typed folder survives the window form re-opening (the pre-fill no-clobber).
// ---------------------------------------------------------------------------
describe('driven component — a typed folder survives re-opening the window form', () => {
  it('NEVER overwrites a folder the operator has entered', () => {
    const fixture = journeyFixture('charter_pending')
    fixture.state.source = { kind: 'folder', root: '/proposed/from/server', label: 'server', status: 'proposed' }
    fixture.card.options = [{ action: 'propose_window', label: 'Change it' }]
    scriptState({ journey: fixture, source: '/typed/by/operator', sourceEdited: true })
    const change = findByText(driveTree(), 'button', 'Change it')
    ;(change.props.onClick as () => void)()
    // The pre-fill is suppressed while the field is the operator's.
    expect(settersFor(STATE.source)).not.toContain('/proposed/from/server')
    expect(settersFor(STATE.editScope)).toEqual([true])
    expect(settersFor(STATE.wizardStep)).toEqual(['window'])
  })

  it('still pre-fills from the last proposal while the field is PRISTINE', () => {
    const fixture = journeyFixture('charter_pending')
    fixture.state.source = { kind: 'folder', root: '/proposed/from/server', label: 'server', status: 'proposed' }
    fixture.card.options = [{ action: 'propose_window', label: 'Change it' }]
    scriptState({ journey: fixture, sourceEdited: false })
    ;(findByText(driveTree(), 'button', 'Change it').props.onClick as () => void)()
    expect(settersFor(STATE.source)).toContain('/proposed/from/server')
  })
})

// ---------------------------------------------------------------------------
// Surface parity — the World skin is the same component, no mutation fork.
// ---------------------------------------------------------------------------
describe('surface parity without a World mutation fork', () => {
  it('submits every surface action to the one shared API', () => {
    const src = fs.readFileSync(path.join(__dirname, 'journey-card.tsx'), 'utf8')
    // One fetch target for actions; no World-only mutation route.
    expect(src).toContain("fetch('/api/onboarding'")
    expect(src).not.toMatch(/\/api\/world\/onboarding/)
  })

  it('World renders the same component with its own skin', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'role' })
    const html = render({ surface: 'world', variant: 'world' })
    expect(html).toContain('Tell me about you and your work.')   // same question
    expect(html).toContain('read-only')                          // same promise
  })
})

// ---------------------------------------------------------------------------
// The accessibility floor and the claims the source makes for itself.
// ---------------------------------------------------------------------------
describe('onboarding journey accessibility floor', () => {
  it('uses labeled controls, a fieldset, live status, and minimum 44px targets', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'window' })
    const html = render()
    expect(html).toContain('<label')
    expect(html).toContain('<fieldset')
    expect(html).toContain('<legend')
    expect(html).toContain('aria-live="polite"')
    expect(html).toContain('min-h-11')   // 44px tap targets
  })

  it('marks the progress rail with the current step for assistive tech', () => {
    scriptState({ journey: journeyFixture('welcome'), wizardStep: 'dream' })
    const html = render()
    expect(html).toContain('aria-current="step"')
    expect(html).toContain('Onboarding progress: step 2 of 6')
  })

  it('requires a typed destructive confirmation instead of a one-tap prompt', () => {
    const src = fs.readFileSync(path.join(__dirname, 'journey-card.tsx'), 'utf8')
    expect(src).not.toMatch(/window\.confirm/)
    expect(src).toContain('Type PURGE')
  })

  it('keeps evidence as DOM text with path and line, never canvas-only', () => {
    const fixture = journeyFixture('dividend_ready')
    fixture.card.evidence = [{ path: 'notes/plan.md', line: 12, excerpt: 'the line', sha256: 'x' }]
    scriptState({ journey: fixture })
    const html = render()
    expect(html).toContain('notes/plan.md:12')
    expect(html).not.toContain('<canvas')
  })

  it('only claims Captain feedback was recorded after the evidence endpoint confirms it', () => {
    const src = fs.readFileSync(path.join(__dirname, 'journey-card.tsx'), 'utf8')
    // The claim is gated on the awaited boolean from reportEvidence.
    expect(src).toMatch(/const recorded = await reportEvidence/)
    expect(src).toMatch(/if \(recorded\) \{\s*setFeedbackRecorded/)
  })

  it('uses the insecure-LAN-safe id helper for action and evidence correlation ids', () => {
    const src = fs.readFileSync(path.join(__dirname, 'journey-card.tsx'), 'utf8')
    expect(src).toContain('function newActionId')
    expect(src).toContain('getRandomValues')       // the insecure-context fallback
  })

  it('stores nothing in the browser — onboarding state lives in the core', () => {
    const src = fs.readFileSync(path.join(__dirname, 'journey-card.tsx'), 'utf8')
    expect(src).not.toMatch(/localStorage|sessionStorage|document\.cookie/)
  })
})
