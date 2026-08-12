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
   * PICKER over the candidates the sweep reported — the estate's own account
   * identifiers are what the core matches, exactly, so a tap beats a spelling.
   *
   * A typed field opens ONLY where `complete` is false. The rule used to be
   * "never a free-text field", and it was wrong in the one direction that
   * matters: the offer was the 12 busiest accounts, and on a real estate the
   * operator's own was 25th of 30 on the connector holding 531 of 665 rows, so
   * the only writer of an identity could not be handed the identifier and 80%
   * of the estate was unresolvable by any sequence of operator actions. The
   * offer now carries every account a connector reported, up to a guardrail;
   * where that guardrail binds, a picker cannot be the only door.
   */
  | 'record_operator_identity'
  /**
   * Points the depth budget at ONE of the things the sweep ranked. Surfaces
   * render a PICKER over `offer.options` plus the escape hatch that always
   * ends it — measured, the right answer can sit outside the top three, and an
   * offer with no way to say "none of these" turns that into a wrong answer the
   * operator had to accept. The escape option carries `input: 'seed'`, so it
   * needs a FIELD (`name`) beside the choice, and `same_as` optionally carries
   * the merge the operator can see and the ranking could not derive.
   */
  | 'answer_salience'
  | 'ratify_charter'
  | 'continue'
  | 'pause'
  | 'revoke'
  | 'undo'
  | 'purge'
  /**
   * Begins a NEW journey after a purge — the affordance the purged card had
   * none of. Payload-free and never destructive: on a live journey the core
   * refuses it (`start_again_unavailable`) rather than resetting anything.
   */
  | 'start_again'

/**
 * The same vocabulary as DATA, because a type is erased at runtime and the
 * drift this list exists to catch is with a Python file no TypeScript compiler
 * reads. `parity.test.ts` asserts this array is exactly the action-dispatch
 * chain in `framework/onboarding/journey.py`; the compile-time assertion below
 * fails `tsc --noEmit` the moment the array and the documented union above
 * part, so neither can be updated alone.
 */
export const ONBOARDING_ACTIONS = [
  'propose_window',
  'answer_seed',
  'answer_salience',
  'gather_connectors',
  'record_operator_identity',
  'ratify_charter',
  'continue',
  'pause',
  'revoke',
  'undo',
  'purge',
  'start_again',
] as const

/**
 * Both directions, deliberately: a one-way `extends` passes whenever one side
 * is a strict subset, which is exactly the drift ("the union gained a member the
 * array never did", or the reverse) this pins.
 */
type ActionsAgree = [OnboardingAction] extends [(typeof ONBOARDING_ACTIONS)[number]]
  ? [(typeof ONBOARDING_ACTIONS)[number]] extends [OnboardingAction]
    ? true
    : never
  : never

export const ONBOARDING_ACTIONS_MATCH_UNION: ActionsAgree = true

/**
 * How a proposed window relates to the salience answer, when the two names
 * share no word. The core refuses an off-target window rather than retargeting
 * it silently, and takes ONE of these two statements — they are two different
 * facts making two different sentences true, so they are never collapsed.
 *
 * Mirrored from `WINDOW_RELATIONS` in `framework/onboarding/journey.py` and
 * pinned key-for-key by `parity.test.ts`: the operator has to be offered the
 * relations to state one, and a surface that offers a value the core does not
 * accept is a refusal wearing a button's clothes.
 */
export const WINDOW_RELATIONS = {
  same_thing: 'the operator says this folder is that target under another name',
  elsewhere: 'the operator says this is somewhere else they want opened',
} as const

export type WindowRelation = keyof typeof WINDOW_RELATIONS

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

/** One thing the sweep ranked, with the names that produced it. */
export interface OnboardingSalienceOption {
  id: string
  label: string
  /** The evidence line — the NAMES behind the rank, never an unauditable score. */
  why: string
  connectors?: string[]
  rows?: number
  aliases?: string[]
  /** Only on the escape hatch: this option needs a typed name beside the pick. */
  input?: 'seed'
}

/**
 * The second question, and the only one a matcher provably cannot answer: are
 * two of these candidates one thing under different names? `candidates` is
 * EVERY ranked name, not the shown three — the twin of the top candidate
 * routinely sits below the cut, so a merge reachable only from what is on
 * screen cannot fix the split it exists for.
 */
export interface OnboardingSalienceMerge {
  field: 'same_as'
  question: string
  candidates: Array<{ id: string; label: string; connectors?: string[] }>
  /** Merges already taught, echoed back — the only place one is VISIBLE. */
  learned: Array<{ labels: string[] }>
}

export interface OnboardingSalienceOffer {
  schema: 'cabinet.onboarding-salience-offer/v1'
  prompt: string
  options: OnboardingSalienceOption[]
  merge?: OnboardingSalienceMerge
  /** What the sweep did NOT reach. An unearned clean negative is the defect. */
  not_reached?: string
  ranked?: number
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
   *
   * `choice` means a pick from `options` below, and — where the picked option
   * is itself marked `input` — a field beside it.
   */
  input?: 'seed' | 'handles' | 'choice'
  /** Set on `answer_salience`: the candidates, escape hatch last. */
  options?: OnboardingSalienceOption[]
  /** Set on `answer_salience`: the merge question, carried WITH the pick. */
  merge?: OnboardingSalienceMerge
  not_reached?: string
  /**
   * Set on `record_operator_identity`: the connectors that still cannot
   * recognise the operator, each with the account identifiers its own rows
   * carried. A surface renders a PICKER over these — the core matches whole and
   * exact, so a spelling the estate does not use resolves the operator and
   * attributes nothing, and a tap on the estate's own string cannot misspell.
   */
  connectors?: OnboardingIdentityAsk[]
}

/** One connector that cannot yet tell which of its actors is the operator. */
export interface OnboardingIdentityAsk {
  connector: string
  rows: number
  /** Every account this connector reported, busiest first, up to the guardrail. */
  candidates: Array<{ identifier: string; rows: number }>
  /** True when the connector reported no actor at all, so no pick can help. */
  reports_no_actor: boolean
  /** How many distinct accounts the connector reported — the estate, uncapped. */
  accounts: number
  /** How many of those the guardrail kept off the list. Zero is the normal case. */
  withheld: number
  /**
   * True when every account the connector reported is on the list. A surface
   * MUST obey this: complete means "none of these is you" is a true terminal
   * state and a typed field could only introduce a spelling the estate does not
   * use; incomplete means the picker cannot be the only door, and the surface
   * owes the operator a way to name an account it did not offer.
   */
  complete: boolean
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
  /**
   * Present on the `salience` question once a ranking exists. Salience stops
   * being a blank field the moment there are candidates — and a question
   * printed with options and no way to send one is the dead end this whole
   * surface exists to abolish.
   */
  offer?: OnboardingSalienceOffer
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
  /**
   * The seed answer, when one was given — the operator's ROLE ("what you do").
   * A starting point for discovery, never the data itself.
   */
  seed?: { text: string; answered_at: string }
  /**
   * The DREAM for the Cabinet, when one was given — "what would you love this
   * to become?". Stored in the `mission.purpose` shape the genesis proposal
   * tree already conditions its cards on, so it composes that seam rather than
   * forking a parallel one. Absent means the operator stated no dream, and the
   * cards derive byte-identically to a missionless answer.
   */
  mission?: { purpose: string }
  /**
   * Where the operator asked me to begin: `point` (they name a folder and I read
   * it under a Charter) or `decide` (I go find where I am most useful, which
   * needs a connected source to read). Absent until they answer the third
   * question.
   */
  start_preference?: 'point' | 'decide'
  /**
   * Where the depth budget is pointed, once the operator has answered. `window`
   * appears when a First Window has been proposed against it, carrying the
   * relation the operator stated (or the name test the core ran itself).
   */
  salience?: {
    target: string
    aliases?: string[]
    from_escape_hatch?: boolean
    offered?: string[]
    not_reached?: string
    evidence?: string
    answered_at?: string
    merged_with?: string[]
    window?: {
      relation: string
      target?: string
      root?: string
      evidence?: string
      bound_at?: string
    }
  }
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
  /** Only on a refusal, and only the allowlisted fields. */
  detail?: OnboardingRefusalDetail
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
  /**
   * On propose_window: the per-window purpose ("what should I make easier
   * first?"). On answer_seed: the DREAM for the Cabinet, which the core stores
   * under `mission.purpose` — the seam genesis conditions its cards on. Two
   * different seams read by two different actions; both stay under 300 chars.
   */
  purpose?: string
  relationship_destination?: 'earn' | 'reversible' | 'sovereign'
  /** REQUIRED by propose_window. An unclassified source is refused, not defaulted. */
  ownership?: OwnershipClass
  /** REQUIRED by propose_window, for every class including `self`. */
  authority_basis?: string
  charter_hash?: string
  confirmation?: string
  /**
   * REQUIRED by answer_seed. A sentence about what the operator DOES — their
   * role. The core stores it as the journey seed; genesis reads it there.
   */
  seed?: string
  /**
   * Optional on answer_seed: where to begin. `point` runs the folder + Charter
   * flow; `decide` asks me to go find where I am most useful (which needs a
   * connected source). An unrecognised value is dropped by the core, never
   * stored.
   */
  start_preference?: 'point' | 'decide'
  /**
   * REQUIRED by record_operator_identity: connector name -> the operator's own
   * account identifier(s) there. A connector the sweep never read is refused.
   */
  handles?: Record<string, string[]>
  /**
   * REQUIRED by answer_salience: the id of one offered candidate, or `other`
   * for the escape hatch. A bare answer_salience is refused BY THE CORE
   * (`salience_choice_required`) — the bridge admits it so the operator gets
   * the core's own sentence, not a surface-invented one.
   */
  choice?: string
  /** REQUIRED when `choice` is the escape hatch: what to open instead. */
  name?: string
  /**
   * Optional on answer_salience: ranked names the operator says are one thing.
   * Bounded by what the ranking PRODUCED — a name it never ranked is refused,
   * because an unvalidated string entering the ranking's own vocabulary is how
   * a merge becomes a guess.
   */
  same_as?: string[]
  /**
   * Optional on propose_window, and the only way past an off-target refusal:
   * the operator stating how this folder relates to the target they answered.
   * The cabinet never retargets their choice silently.
   */
  salience_relation?: WindowRelation
}

/**
 * The allowlisted fields a refusal may carry back to a surface.
 *
 * A refusal that only says no leaves the operator with nothing to do about it;
 * `salience_window_off_target` names the target, the window and the relations
 * that resolve it. The route is a trust boundary, so this is an explicit
 * allowlist and never a spread of whatever the core printed.
 */
export interface OnboardingRefusalDetail {
  target?: string
  window?: string
  relations?: string[]
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
