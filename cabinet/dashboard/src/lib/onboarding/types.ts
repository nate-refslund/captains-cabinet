export type OnboardingSurface =
  | 'dashboard'
  | 'telegram'
  | 'world'
  | 'companion'
  | 'api'

export type OnboardingAction =
  | 'propose_window'
  /** Answers the seed question. Carries free text, so surfaces render a FIELD. */
  | 'answer_seed'
  /**
   * Reads every connector the operator declared — read-only, contents-free.
   * Payload-free: the estate is declared in instance/config/connectors.yml, so
   * a surface can trigger the read but can never widen it.
   */
  | 'gather_connectors'
  /**
   * Records which account is the operator in each connector. Surfaces render a
   * PICKER over the candidates the sweep reported, never a free-text field: the
   * estate's own account identifiers are what the core matches, exactly.
   */
  | 'record_operator_identity'
  | 'ratify_charter'
  | 'continue'
  | 'pause'
  | 'revoke'
  | 'undo'
  | 'purge'

export type OwnershipClass = 'self' | 'employer' | 'third_party'

/** How content from a source of a given ownership class may leave the machine. */
export type EgressDisposition = 'allow' | 'record_and_allow' | 'per_item_approval'

export interface OnboardingCitation {
  path: string
  line: number
  excerpt: string
  sha256: string
  /** Set when the excerpt was withheld because the source is not the operator's. */
  withheld_reason?: string
}

/**
 * The egress verdict the core attaches to a dividend card. Surfaces RENDER it;
 * they never decide it. `withheld` counts citations whose words the core
 * replaced, so a surface can say how much is being held back without ever
 * holding the withheld text itself.
 */
export interface OnboardingEgress {
  ownership: string
  disposition: EgressDisposition
  items: number
  withheld: number
  approved: string[]
}

export interface OnboardingOption {
  action: OnboardingAction
  label: string
  danger?: boolean
  /**
   * Set when the action needs typed input rather than a tap. A question the
   * core prints with no way to answer it is a dead end wearing an
   * invitation's clothes, so the core says which option needs a field and
   * every surface obeys — a tap-only surface must not offer it as a button.
   */
  input?: 'seed' | 'handles'
  /**
   * Set on `record_operator_identity`: the connectors that still cannot
   * recognise the operator, each with the account identifiers its own rows
   * carried. A surface renders a PICKER over these, never a blank field —
   * the core matches whole and exact, so a spelling the estate does not use
   * resolves the operator and attributes nothing.
   */
  connectors?: OnboardingIdentityAsk[]
}

/** One connector that cannot yet tell which of its actors is the operator. */
export interface OnboardingIdentityAsk {
  connector: string
  rows: number
  candidates: Array<{ identifier: string; rows: number }>
  /** True when the connector reported no actor at all, so no pick can help. */
  reports_no_actor: boolean
  note: string
}

/**
 * The three entry modes (Captain ruling 2026-07-26). Present on the cards that
 * were dead ends — `welcome` (one option: choose a folder) and
 * `orientation_offered` (pause/revoke/purge and nothing forward). Optional
 * because every other stage renders without it, never because it may be
 * skipped where it belongs: `next_actions` is non-empty by construction on the
 * producing side, so a card carrying an entry plan always carries a way on.
 */
export interface OnboardingEntryQuestion {
  id: string
  prompt: string
  why: string
  required: boolean
}

export interface OnboardingEntryPlan {
  schema: 'cabinet.onboarding-entry-plan/v1'
  mode: 'connected' | 'seeded' | 'ungranted'
  opening_move: 'sweep_and_assert' | 'seed_then_discover' | 'residual_questions'
  grants: { connectors: string[]; local_files: boolean; web: boolean }
  seed_question: string | null
  questions: OnboardingEntryQuestion[]
  discovery: {
    terms: string[]
    probes: Array<Record<string, string>>
    executable: boolean
    /**
     * What the probes actually FOUND once they were run. `deferred` carries
     * every probe class that did NOT run with its reason, so no surface can
     * summarise a partial run as though it had searched everywhere.
     */
    executed?: {
      schema: 'cabinet.onboarding-probe-result/v1'
      executed: Array<{ kind: string; pattern?: string; matches: string[]; truncated: boolean }>
      deferred: Array<{ kind: string; reason: string }>
      complete: boolean
    }
  }
  cannot_know: Array<{ subject: string; verdict: string; statement: string }>
  /** Null once every connector resolves — a settled question is never printed. */
  identity_question: {
    question: string
    connectors: OnboardingIdentityAsk[]
    is_a_question: true
  } | null
  next_actions: OnboardingOption[]
}

export interface OnboardingCard {
  schema: 'cabinet.onboarding-card/v1'
  id: string
  journey_id: string
  revision: number
  stage: string
  kind: string
  title: string
  body: string
  status: string
  evidence: OnboardingCitation[]
  options: OnboardingOption[]
  entry?: OnboardingEntryPlan
  egress?: OnboardingEgress
}

export interface OnboardingState {
  schema: 'cabinet.onboarding-journey/v2'
  journey_id: string
  evidence_trial_id: string
  revision: number
  stage: string
  purpose: string | null
  relationship_destination: 'earn' | 'reversible' | 'sovereign' | null
  orientation_mode: 'observe_only'
  access: string
  source: null | {
    kind: 'folder'
    root: string
    label: string
    status: string
    manifest_hash?: string
    ownership?: OwnershipClass
    authority_basis?: string
  }
  charter: null | {
    hash: string
    status: string
    payload: Record<string, unknown>
    ratified_at?: string
  }
  first_dividend: null | Record<string, unknown>
  /** The seed answer, when one was given. A starting point, never the data. */
  seed?: { text: string; answered_at: string }
  /** Written by the core's connector registry on every commit and snapshot. */
  entry_grants?: { connectors: string[]; local_files: boolean; web: boolean }
  connector_probes?: {
    schema: 'cabinet.connector-registry/v1'
    connected: Array<{ kind: string; name: string; evidence?: string }>
    refused: Array<{ kind: string; name: string; reason: string }>
  }
  created_at: string
  updated_at: string
}

export interface OnboardingResponse {
  ok: boolean
  state: OnboardingState
  card: OnboardingCard
  duplicate?: boolean
  purged?: boolean
  error?: string
  code?: string
  evidence?: {
    trial_id: string
    trace_id: string
    action_id: string
    correlation_id: string
  }
}

export interface OnboardingActionRequest {
  action: OnboardingAction
  action_id?: string
  trace_id?: string
  correlation_id?: string
  expected_revision?: number
  source?: string
  purpose?: string
  relationship_destination?: 'earn' | 'reversible' | 'sovereign'
  /** REQUIRED by propose_window. An unclassified source is refused, not defaulted. */
  ownership?: OwnershipClass
  /** REQUIRED by propose_window, for every class including `self`. */
  authority_basis?: string
  charter_hash?: string
  confirmation?: string
  /** REQUIRED by answer_seed. A sentence about the operator's work. */
  seed?: string
  /**
   * REQUIRED by record_operator_identity: connector name -> the operator's own
   * account identifier(s) there. A connector the sweep never read is refused.
   */
  handles?: Record<string, string[]>
}

export interface OnboardingObservationRequest {
  phase: 'transport' | 'ui' | 'feedback'
  status:
    | 'started'
    | 'succeeded'
    | 'failed'
    | 'retried'
    | 'interrupted'
    | 'recovered'
    | 'useful'
    | 'not_useful'
    | 'corrected'
  action_id?: string
  trace_id?: string
  correlation_id?: string
  detail?: Record<string, unknown>
}

export interface OnboardingObservationResponse {
  ok: boolean
  evidence?: {
    trial_id: string
    event_id: string
    trace_id: string
    action_id: string
    correlation_id: string
  }
  error?: string
  code?: string
}
