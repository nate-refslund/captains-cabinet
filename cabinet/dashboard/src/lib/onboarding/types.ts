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

export interface OnboardingCitation {
  path: string
  line: number
  excerpt: string
  sha256: string
}

export interface OnboardingOption {
  action: OnboardingAction
  label: string
  danger?: boolean
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
  }
  cannot_know: Array<{ subject: string; verdict: string; statement: string }>
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
