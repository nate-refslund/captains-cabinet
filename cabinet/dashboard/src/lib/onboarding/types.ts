export type OnboardingSurface =
  | 'dashboard'
  | 'telegram'
  | 'world'
  | 'companion'
  | 'api'

export type OnboardingAction =
  | 'propose_window'
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
