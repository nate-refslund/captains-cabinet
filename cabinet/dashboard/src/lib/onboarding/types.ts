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
   * Declares ONE connector from a curated template plus a credential, right in
   * onboarding. Carries a template id, a label, an env var NAME and at most a
   * field or two — NEVER a credential value: the dashboard's own safe .env
   * writer stores that, so the value never crosses to the core. Dashboard-
   * surface only in practice — a credential paste belongs on the local surface,
   * not a chat one — so the core never prints this on a card, and it needs no
   * Telegram branch. The gather that follows is the existing read.
   */
  | 'declare_connector'
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
  /**
   * Sends the seed's outward probes AGAIN, through whatever search tool the
   * operator has connected. Payload-free — what goes out is derived from words
   * they already gave this journey — so a tap can carry it and no surface can
   * widen what is searched. `answer_seed` already runs them once; this exists
   * for everything that changes AFTERWARDS (a tool connected, a key pasted, an
   * organisation named), and the core offers it only when a search tool is
   * declared, so it is never a button that cannot work.
   */
  | 'run_discovery'
  /**
   * Records which company or organization this cabinet is for — or that it is
   * just the operator. Carries an `organization` string, bounded by the core.
   * Asked only when nothing has answered it (no estate identity from a sweep,
   * no name in the seed), never required, and never derived: the one source is
   * the operator's own sentence.
   */
  | 'answer_organization'
  /**
   * Records a page the operator pastes about their organization, and READS it.
   * Carries a `url` (https only — the core refuses anything else by name). It
   * is EARNED: offered only after a look-up ran through a connected search tool
   * and nothing that came back named the organization, which is the one moment
   * "do you have a website I should read?" is a useful question rather than an
   * interview. The address is the consent — the operator typed that exact page
   * for that exact purpose — and it is read on the same read-only rails as a
   * search: no credential, one page, capped, refusals by name.
   */
  | 'answer_org_link'
  /**
   * The operator confirming that an address a search actually returned is their
   * organization's. Carries the `domain` the core offered. NOTHING IS CLAIMED
   * WITHOUT THE TAP: a search result is a stranger's page, and recording its
   * address because it ranked well would be a fact about the operator that they
   * never stated and that reads exactly like a correct one. The core re-derives
   * the candidate from the committed look-up, so a domain no search returned is
   * refused (`organization_domain_not_offered`).
   */
  | 'confirm_organization_domain'
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
  'declare_connector',
  'answer_salience',
  'gather_connectors',
  'record_operator_identity',
  'run_discovery',
  'answer_organization',
  'answer_org_link',
  'confirm_organization_domain',
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
 * One field a connector template still needs the operator to supply — the open
 * `rest` template asks for a URL and a couple of paths; a single-credential tool
 * asks for none. The dashboard renders these; the core validates them.
 */
export interface ConnectorTemplateField {
  key: string
  label: string
  help: string
  placeholder: string
  required: boolean
}

/**
 * One entry in the "Connect a tool" catalog, projected to what the surface
 * draws — never the connector body. The read shape (URLs, paths, the identity
 * call) stays server-side; a surface is handed the id to send back, the label
 * and summary to show, the host the credential reaches (for the consent line),
 * the env var NAME it lands under, and the fields still to fill. The vendor
 * names live in the DATA pack this is read from, never in the framework.
 */
export interface ConnectorTemplateChoice {
  id: string
  label: string
  summary: string
  host: string
  credential_env: string
  credential_help: string
  fields: ConnectorTemplateField[]
  /**
   * Which shelf of the catalog this sits on — the pack's own id, resolved to a
   * label through `categories` below. A tool whose pack entry names no category,
   * or names one the pack never declared, lands in `other`: a browsable list is
   * only browsable if every entry is somewhere.
   */
  category: string
  category_label: string
  /**
   * The steps to take IN THAT PRODUCT to produce the credential — where its key
   * screen is, which read-only scope to tick, and what will go wrong. An ordered
   * sequence, because they are one: the key cannot be copied before it is made.
   */
  how_to_connect: string[]
  /** What a right-looking key looks like, so a wrong paste is caught by eye. */
  key_looks_like: string
}

/**
 * The catalog as one browsable object: the tools, and the shelf labels they sort
 * onto. Both come from the same DATA pack, so a new shelf is a data edit.
 */
export interface ConnectorCatalog {
  templates: ConnectorTemplateChoice[]
  categories: Array<{ id: string; label: string; count: number }>
}

/**
 * One connector as the LAST sweep found it — the contents-free row
 * `research.sweep_connectors` writes, projected to what a surface may draw.
 * `connected` is the fact; `reason` is why not, in the sweep's own words.
 */
export interface OnboardingSweptConnector {
  name: string
  connected: boolean
  items: number
  calls: number
  host?: string
  latest?: string | null
  actors?: number
  reason?: string
}

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
  /**
   * The words of the operator's OWN earlier answers — role, dream, organisation
   * — that this candidate's name carries. Present only where there is a match,
   * so a surface can say why this ranks in the operator's language rather than
   * only in the ranking's recurrence arithmetic.
   */
  you_said?: string[]
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
  /**
   * Set when EXACTLY ONE ranked candidate matches words the operator already
   * gave (their role, their dream, the organisation they named). The open ask
   * becomes a CONFIRM — "you said X, start there?" — because re-asking for
   * something already answered is the complaint this closes. Two matches is a
   * choice, not a confirmation, and stays an open ask.
   */
  confirm?: { option: string; label: string; words: string[]; question: string }
  /**
   * A word the operator gave that the ranking never produced, for the escape
   * hatch's "name your own" field. Their vocabulary, not a guess: it is one of
   * the terms they typed, offered back so the field does not start blank.
   */
  prefill?: string
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
  input?: 'seed' | 'handles' | 'choice' | 'organization' | 'url' | 'domain'
  /** Set on `answer_salience`: the candidates, escape hatch last. */
  options?: OnboardingSalienceOption[]
  /** Set on `answer_salience`: the merge question, carried WITH the pick. */
  merge?: OnboardingSalienceMerge
  not_reached?: string
  /**
   * Set on `answer_salience` when ONE ranked candidate matches words the
   * operator already gave. Carried on the ACTION as well as the question,
   * because a surface builds the control from the action — on the question
   * alone it would be a confirmation nothing renders.
   */
  confirm?: OnboardingSalienceOffer['confirm']
  /** Set on `answer_salience`: their own word, for the escape hatch's field. */
  prefill?: string
  /**
   * Set on `record_operator_identity`: the connectors that still cannot
   * recognise the operator, each with the account identifiers its own rows
   * carried. A surface renders a PICKER over these — the core matches whole and
   * exact, so a spelling the estate does not use resolves the operator and
   * attributes nothing, and a tap on the estate's own string cannot misspell.
   */
  connectors?: OnboardingIdentityAsk[]
  /**
   * Set on `confirm_organization_domain`: the address one of my own searches
   * returned. Carried on the ACTION because a surface builds its control from
   * the action, and a value it has to re-derive from the results list is a
   * value it can derive differently.
   */
  domain?: string
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
  /**
   * The ONE account whose identifier matches the operator's name, when a name
   * is on record and exactly one account matches it. A PROPOSAL: the surface
   * renders it as a confirm chip, and nothing is recorded until the operator
   * taps. A guess written without that tap is an attribution the operator never
   * made, which reads exactly like a correct one and is therefore never caught.
   */
  guess?: {
    identifier: string
    rows: number
    rule: 'whole_name' | 'every_word' | 'joined_words'
    matched_name: string
    evidence: string[]
    why: string
  } | null
  /**
   * Why there is no guess even though the name matched here: two or more
   * accounts are spelled like the operator. Said out loud, because silence
   * reads as "your name matched nothing", which is the opposite of what
   * happened.
   */
  guess_note?: string
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
  /**
   * Present on a question the operator can actually ANSWER. Only the earned
   * organisation question carries it today; the other residuals are printed
   * with no field, which is a real gap and not one this type papers over.
   */
  action?: OnboardingAction
  input?: string
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
      /**
       * TWO PLANES, ONE LIST. A local probe carries `matches` (names inside the
       * ratified window); an outward one carries the `query` that left the
       * machine, the `provider` it went to, and `results`.
       *
       * EVERY FIELD OF A RESULT IS UNTRUSTED TEXT — it was written by whoever
       * ranked well for the operator's own words, which an adversary can
       * arrange to be. The core scrubs and caps each one (control characters,
       * angle brackets, lone surrogates, length, and a non-http address is
       * dropped to an empty string), so what arrives here is a caption. Render
       * it as TEXT. Never as markup, never as a template, never as anything a
       * click or a script can reach beyond an ordinary link.
       */
      executed: Array<{
        kind: string
        pattern?: string
        matches?: string[]
        truncated: boolean
        query?: string
        provider?: string
        /**
         * A page the OPERATOR pasted, read rather than searched (`web_read`).
         * Same shape, because "what did you actually go and look at" is one
         * question and answering it out of two shapes would put the seam in
         * front of the person instead of behind them.
         */
        url?: string
        results?: Array<{
          title: string
          url: string
          snippet?: string
          /**
           * WHY this result counts as being about the operator: which of their
           * own words it says, and in which field. The core matches verbatim
           * over tokens (`research.result_mentions`), so `term` may be quoted
           * back to them as the reason. Absent means it matched nothing they
           * said — which is not a reason to hide it, only to fold it.
           */
          matched?: Array<{ term: string; kind: string; where: string }>
        }>
        /**
         * How many of this probe's results name something the operator said.
         * ABSENT means the run was never judged (nothing to look for), which is
         * a different fact from `0` — "I did not check" versus "I checked and
         * none of it was you". A surface must not render one as the other.
         */
        relevant?: number
      }>
      deferred: Array<{ kind: string; reason: string; query?: string; url?: string }>
      complete: boolean
      /**
       * What the judgment was made AGAINST — the operator's own organization and
       * name, in their spelling. Empty means unjudged; see `relevant` above.
       */
      looked_for?: string[]
    }
  }
  cannot_know: Array<{ subject: string; verdict: string; statement: string }>
  /** Null once every connector resolves — a settled question is never printed. */
  identity_question: {
    question: string
    connectors: OnboardingIdentityAsk[]
    is_a_question: true
  } | null
  /**
   * What is known about whose work this is: the operator's own answer, and what
   * the connected tools call themselves. Either one present means the earned
   * organisation question is not asked.
   */
  organization: { answer?: string | null; estate?: string[] } | null
  next_actions: OnboardingOption[]
}

/** One named part of a card's honesty ledger — a heading and its own text. */
export interface OnboardingCardSection {
  id: string
  title: string
  text: string
}

export interface OnboardingCard {
  schema: 'cabinet.onboarding-card/v1'
  id: string
  journey_id: string
  revision: number
  stage: string
  kind: string
  title: string
  /**
   * THE WHOLE LEDGER, still. `body` is the join of `details` in order, so a
   * surface that cannot fold (Telegram, a log, a plain reader) loses nothing.
   * Layering is a rendering choice; it is never a shorter truth.
   */
  body: string
  /**
   * At most three short sentences: what was read, what recurs, what is needed
   * from the operator now. A SUMMARY of `details`, never a replacement — a
   * surface rendering only this is a surface with a bug.
   */
  headline?: string[]
  /** The same ledger `body` joins, cut into named sections for a disclosure. */
  details?: OnboardingCardSection[]
  /**
   * Who is speaking. A ROLE, never a name: the framework does not know what
   * this deployment calls its coordinating officer, so a surface resolves the
   * title through `officerTitle`.
   */
  speaker?: 'coordinator'
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
    /**
     * How broad this window is. `whole_home` is LAWFUL and disclosed — the
     * operator may open their whole home folder, read-only, with the
     * sensitivity skips intact; what it costs them is the DEPTH of the first
     * look, which the Charter card states before they approve.
     */
    breadth?: 'whole_home' | 'folder'
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
   * What the operator is called, when they said. `stored` is whether it reached
   * the cabinet-init answers file (`captain.name`); a failed write does not
   * cost the operator their answer, so the name is on the journey either way
   * and the identity guess still uses it.
   */
  operator_name?: { name: string; stored: boolean; answered_at: string }
  /**
   * The DREAM for the Cabinet, when one was given — "what would you love this
   * to become?". Stored in the `mission.purpose` shape the genesis proposal
   * tree already conditions its cards on, so it composes that seam rather than
   * forking a parallel one. Absent means the operator stated no dream, and the
   * cards derive byte-identically to a missionless answer.
   */
  mission?: { purpose: string }
  /**
   * Whose work this cabinet is for, when the operator said. Written by
   * `answer_organization` and NEVER derived — not from a folder name, not from
   * a credential, not from a search result. Absent means nobody has answered
   * it, which is why the arrival summary omits the clause rather than guessing.
   */
  organization?: {
    name: string
    answered_at: string
    /** A page the operator pasted about it. Re-read on every look-up. */
    link?: string
    link_answered_at?: string
    /**
     * The address the operator CONFIRMED is theirs, from a result one of my own
     * searches returned. Never written without their tap.
     */
    domain?: string
    domain_confirmed_at?: string
  }
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
  /**
   * What the last `gather_connectors` found, per connector. One sweep covers
   * EVERY declared connector, so this is the aggregate the connect step reads
   * back: each tool with its own count, freshest stamp and — where it failed —
   * its own reason, which is what keeps one bad credential from reading as a
   * failed sweep.
   */
  connector_sweep?: {
    schema: 'cabinet.connector-sweep/v1'
    swept_at: string
    declared: number
    calls: number
    connectors: OnboardingSweptConnector[]
    not_reached?: string[]
  }
  /**
   * Contents-free provenance: what was connected from inside onboarding, in
   * order. Written by `declare_connector`; carries the env var NAME and never a
   * value. A connector declared before onboarding is NOT here — the sweep above
   * is the authority on what exists.
   */
  connector_declarations?: Array<{
    name: string
    host: string
    template: string
    declared_at: string
  }>
  /** Written by the core's connector registry: how many connectors are declared. */
  connectors_declared?: number
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
   * REQUIRED by answer_organization. The company or organization this cabinet
   * is for — or the operator saying it is just them, which is a real answer and
   * stored as typed. Never derived from a folder, a credential or a search
   * result: the one source is what they said.
   */
  organization?: string
  /**
   * REQUIRED by answer_org_link. A page about the organization, https only —
   * the core refuses anything else BY NAME so the operator can fix a typo in a
   * keystroke rather than read a probe reason two screens later.
   */
  url?: string
  /**
   * REQUIRED by confirm_organization_domain: the address the core offered on
   * the action itself. Anything a search did not return is refused by the core,
   * so this cannot be used to record an address the operator never saw.
   */
  domain?: string
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
  /**
   * REQUIRED when `choice` is the escape hatch: what to open instead.
   *
   * ALSO on answer_seed, where it is what the OPERATOR is called. The core
   * records it under `captain.name` in the cabinet-init answers file — the
   * generator's own input — and on the journey, where the identity guess reads
   * it to propose "in github, are you @…?" instead of asking the operator to
   * pick their own account out of thirty strangers. Optional there: a journey
   * with no name asks exactly as it did before.
   */
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
  /**
   * REQUIRED by declare_connector: the id of a template from the catalog
   * (`instance/config/connector-templates.yml.example`). An id the pack does
   * not carry is refused BY THE CORE.
   */
  template?: string
  /**
   * REQUIRED by declare_connector: the env var NAME the credential is stored
   * under in cabinet/.env. UPPER_SNAKE_CASE, validated by the core. The
   * credential VALUE is never in this request — the dashboard's safe .env
   * writer stores it separately, so it never crosses to the core.
   */
  credential_env?: string
  /**
   * Optional on declare_connector: the operator's answers to the template's own
   * fields, keyed by the template's field keys. A key the template never asked
   * for is refused by the core, and each value is bounded there.
   */
  fields?: Record<string, string>
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
