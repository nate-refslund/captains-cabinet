# Cabinet Onboarding v2 — one earned organization, three truthful faces

**Status:** Captain-approved design of record, 2026-07-14. The First Window
vertical slice and Evidence Recorder v1 integration are implemented. This governs the intelligence journey
after a Cabinet exists. `world-onboarding-hatching-2026-07-09.md` remains the
install/hatch authority.

## 1. Outcome

The Cabinet should feel startlingly intelligent without asking the Captain to
trust theater:

> Give me one narrow window. I will prove useful within minutes, study deeply
> under a Charter, show you what I think your strategy is, propose the
> organization that fits it, and ask you to commission responsibility with
> examples from your actual work.

The low floor is one folder, one purpose sentence, one approval, and one cited
result. The high ceiling is a self-organizing Cabinet with ratified Direction,
source-aware officers, per-lane authority, verification, receipts, and earned
graduation.

**Addendum, 2026-08-16 — the flow is SCREENS THAT REPLACE EACH OTHER.** The
dashboard surface was one ~2,000-line card whose panels appeared by additive
predicates and never left, so a connected run ended with a sweep table, an
identity picker, a ranked question, a discovery log, a residuals list, a receipt
and eight buttons on one page. It is now a ROUTER over one screen at a time
(`cabinet/dashboard/src/lib/onboarding/screen-router.ts`, pure and testable
without a DOM) plus one component per screen:

| # | Screen | The one idea |
|---|---|---|
| S1 | `welcome` | the door: what this is, what it costs, one tap to start |
| S2 | `you` | your name (optional) and what you do |
| S3 | `dream` | what you would love this Cabinet to become |
| S4 | `begin` | point me at a folder, or go and find where I am useful |
| S5A | `folder` | the folder, whose data it is, under what right |
| S5B | `connect` | the tool catalog, what is connected, and the look |
| — | `sweep` | what one sweep found, per tool, and the way onward |
| — | `identity` / `salience` / `organization` | the earned asks — each fires ONLY while unanswered, one at a time |
| S6 | `approve` | the Charter's terms, every one of them unfolded |
| S7 | `look` | the read running, in plain words, flowing into S8 with no click |
| S8 | `find` | the first result, as a message from the First Mate |
| S9 | `arrival` | what is now true, and the management view a revisit gets |

Nothing survives a screen change except the four-stop rail and one standing
read-only line. The page frame around it says nothing at all: a frame that
describes the product differently from the product is what an operator trusts
least. Every screen carries its ONE primary action, and an act-firing control
that cannot fire is disabled WITH ITS REASON on the screen — wrong input is
impossible rather than corrected. Two fields were CUT by the same ruling: the
per-window purpose (it re-asked the dream, which now seeds it) and the
trust-destination radio (it granted nothing, as its own helper text admitted;
where authority grows is the trust ladder).

The three questions themselves are unchanged, and are asked in this order:

1. **who you are, and your role** — *"What is your name? And tell me about you
   and your work."* One step, two fields. The NAME (2026-08-14, below) is
   optional and lands under `captain.name`; the free text is any language and is
   stored as the journey **seed**, the seam genesis reads.
2. **the dream** — *"What would you love this Cabinet to become? Think bigger
   than today."* Free text, optional. Stored under **`mission.purpose`**, the
   seam the genesis proposal tree already conditions its cards on — composed,
   never forked. A role-only answer stays byte-identical to a missionless one.
3. **where to begin** — *"point me somewhere, or go and find where I am most
   useful?"* The new field **`start_preference`** (`point` | `decide`). `point`
   runs the folder + Charter flow below; `decide` is self-exploration, which
   **requires a connected source to read** — where one is connected it sweeps it
   read-only, and where none is it says so plainly and routes to the folder as
   the concrete start rather than pretending to look at nothing.

The core seams are `framework/onboarding/journey.py::answer_seed` (role/dream/
start_preference) and genesis's existing `mission.purpose` + seed conditioning.
The Charter → scan → dividend → briefing back half is unchanged.

**Connect-a-source, LIVE (Captain 2026-08-13).** The `decide` branch now
connects a tool from inside onboarding, closing the gap this doc used to name.
The dashboard's discover panel draws a catalog from a curated, agnostic
template pack shipped as DATA (`instance/config/connector-templates.yml.example`;
the framework names no vendor — it consumes the pack generically). The operator
picks a tool, pastes a credential and supplies at most a field or two; the
credential VALUE goes only to `cabinet/.env` via the dashboard's safe writer
(`actions/env.ts::saveConnectorCredential`), while a new core act
`declare_connector` (`journey.py::_act_core` → `research.build_connector_from_template`
+ `research.write_connector_declaration`) writes the connector entry — the env
var NAME, never the value — into `instance/config/connectors.yml`, refusing at
declaration anything `assert_read_only` would refuse at the sweep. The existing
`gather_connectors` read then runs and the flow reaches the salience/window
question it always could once a connector existed. **Custody:** `connectors.yml`
is captain-custody; v1 is propose-then-activate — in the personal hatch the
operator IS the captain, so one explicit "Connect" click, with a consent line
naming the host, both declares and activates. A delegated (operator ≠ captain)
future needs a ratification step before activation; that is the named follow-up.
**Out of v1:** MCP connectors (adding an MCP server is a sudo/germline-gated
code-exec grant), honest-disabled and filed, never faked.

**A catalog, and many tools at once (Captain 2026-08-13, same evening).** Two
asks on the live product: *"can we expand this to like hundreds of connectors
and also include HOW to connect for each?"* and *"I want to connect MANY
connectors at once, not just one."* Both are answered in DATA and in the step's
shape, not in new machinery.

- **The pack is the catalog.** Every template now also carries `category` (a
  shelf, resolved through a `categories:` map in the same file),
  `how_to_connect` (2-5 steps in that product's own words — where its key screen
  is, which read-only scope to tick, what will go wrong) and `key_looks_like`
  (so a wrong paste is caught by eye rather than by a puzzling 401 later). The
  surface reads them through `actions/connectors.ts::getConnectorCatalog`, which
  also projects the shelves; a tool whose category is undeclared lands on
  "Anything else" rather than disappearing. **Growth is data-only**: adding a
  hundred more entries is edits to one YAML file with no code change, which is
  what "hundreds" means here. What ships is what was VERIFIED against each
  provider's current public API reference; popular tools are absent where their
  list endpoint cannot meet the ceiling (a non-GraphQL POST, HTTP Basic needing
  a hand-encoded pair, an OAuth round trip, or no timestamp on the items), and
  the open `rest` template covers everything not named.
- **`fields[].into_format`** (`research.build_connector_from_template`) lets a
  template ask for "acme" where the shape needs a whole URL: the format is the
  template author's sentence with one `{value}` hole, and it must start with a
  literal `https://` so no operator value can choose the scheme. Without it,
  every per-tenant tool made a non-technical operator assemble an API address.
- **The connect step no longer closes itself.** It used to be replaced by its
  own results the moment a sweep produced anything to rank, which made
  connecting a one-shot. Now it holds a "Connected so far" list — each tool with
  its own count, freshest stamp, or its own refusal reason — beside the catalog,
  and hands over only when the operator presses *go look*. One
  `gather_connectors` act sweeps every declared connector, so that one press
  covers however many are on the list; a refused key is reported against its own
  tool and takes nothing else down with it, and re-picking a connected tool
  replaces its credential rather than being refused as a duplicate name.
- **Sensors:** `framework/onboarding/tests/test_connector_catalog.py` checks the
  SHIPPED pack (shape, custody of operator answers, host-consent truth, the
  read-only ceiling on every built call, and an adversarial pass over the prose:
  no step may walk an operator into a write-scoped key unremarked) and includes
  arms proving that checker can fail. `test_connector_declare.py` drives three
  tools + one bad credential through one sweep;
  `cabinet/dashboard/src/actions/connectors.test.ts` pins the projection against
  degenerate packs.

**The Cabinet can actually go and look (Captain 2026-08-14).** Three asks on the
live product, all from one session: the catalog had no way to connect a search
key at all; the seed question's outward probes still rendered *"web_search — did
not run — no egress in the onboarding core"* while egress is allow-all by
default; and *"maybe even also … ask which company the person is working for if
it is not clear from the text or connected tools."*

- **A search shelf, in DATA.** `categories.search` plus five VERIFIED search
  templates and one open GET-only escape hatch. They are a NEW template kind:
  a search tool holds no estate, so instead of `inventory:` it carries
  `search:` — how to send a query (`url` with one `{query}` hole, or a POST
  `json` skeleton with the hole at one key) and where the answers are
  (`results_path`, `title_field`, `url_field`, optional `snippet_field`). The
  lane is read off the SHAPE (`research._spec_kind`), never off the `kind:`
  label, so a template cannot pick its own ceiling by claiming one.
- **A second ceiling, not a wider one.** `research.assert_search_read_only` is a
  separate function from `assert_read_only` and the inventory rule did not move
  a byte. The reason is exact: the inventory lane admits a POST only when the
  body is a GraphQL read document, because a GraphQL document declares its own
  verb; a REST search body declares nothing, so admitting it under that rule
  would have admitted every REST write with it. The search rule admits a bounded
  query envelope (scalars, short scalar lists, one nesting, a size cap) and is
  STRICTER than the inventory rule everywhere else — a broader write-verb refusal
  over the address and the body, the injected credential header checked for
  method overrides, and exactly one `{query}` hole counted across url + body. It
  does not, and does not claim to, prove that a hand-declared endpoint will not
  mutate; what it proves is that the call is a query envelope, names no write,
  cannot be redirected, and reached the wire through a slot only the probe
  executor reads. That paragraph is in the code, at the function.
- **The probes RUN, in the plane that holds egress.** The core still holds no
  socket: `_execute_probes` matches names inside the ratified window and defers
  everything else, and `journey._discovery_block` hands those deferrals to
  `research.run_search_probes`, which either runs them or replaces the
  placeholder with what actually stopped them (`no_search_tool_connected`,
  `search_credential_absent`, `egress_…`, `http_401`, …). It runs inside
  `answer_seed` — so the answer to the question the operator just answered
  arrives with the card — and again from a new payload-free act `run_discovery`,
  offered only once a search tool is declared. Caps: three probes, one call
  each, a 12s timeout, five results per probe, per-field length caps and a total
  byte budget over the run. The QUERY is shown on the card, because that is the
  operator's own words leaving their machine.
- **A result is untrusted text.** It is written by whoever ranked well for the
  operator's own sentence, which an adversary can arrange to be. Every field
  passes `_untrusted_text` / `_untrusted_url` at the one place results enter:
  control characters, line separators and angle brackets become spaces, lone
  surrogates are replaced (they are legal in decoded JSON, illegal in UTF-8, and
  would crash the CLI printing the state), lengths are capped, and an address
  that is not http/https is dropped to empty. The card BODY carries only the
  operator's own query — third-party text never enters the string that travels to
  a messenger — and the results ride the structured block, rendered as text with
  their source beside them. Nothing downstream interprets them: the pipeline is
  deterministic, so there is nothing for an instruction to instruct.
- **Whose work is this.** `RESIDUAL_QUESTIONS` still never asks what the company
  is; the amendment is narrower. `_organization_unclear` asks only when nothing
  has answered it — no operator answer, no estate identity from a sweep, and no
  capitalised non-initial term in the seed — and the question is optional, has
  its own field and act (`answer_organization`), and "just me" is a complete
  answer. The stated cost of the seed half: it over-detects English title case
  and cannot fire in a script without letter case, so it errs toward asking,
  which is the cheap direction. The answer joins the discovery seed, so the next
  look-up searches the name the operator gave.
- **Sensors:** `framework/onboarding/tests/test_search_probes.py` — the ceiling
  in both directions (including an arm that goes red if the two ceilings are
  ever merged), every degenerate end, the untrusted-text scrubs, the wire
  request including query encoding, a REAL socket proving the fetch layer and
  that a 30x is not followed, and end-to-end arms driving `journey.act` with only
  the socket stubbed — plus an adversarial arm feeding a hostile result through
  the whole path. `test_connector_catalog.py` gained the search-lane arms
  (shape, custody under `search.`, the label-vs-shape check, the disclosure that
  the operator's own words are sent, and the GET-only property of the open one).

**The First Mate speaks (Captain 2026-08-14, same day, second session).** He
drove the whole connected flow — four real connectors plus a search tool — and
returned seven findings. Not one is about truthfulness; every one is about
PRESENTATION or INITIATIVE, and each fix therefore LAYERS the honesty ledger and
never deletes a word of it.

- **Short first, details fold.** *"this is way too much text. make it short and
  simple."* The connected-mode card opened with ~350 words of cannot-know,
  coverage and ranking caveats as one paragraph. The card now carries three
  fields instead of one blob: `headline` (at most three short sentences — what I
  read, what recurs, the ONE thing needed now), `details` (the same ledger cut
  into named sections), and `body`, which is **exactly the join of `details`**.
  That equality is the whole safety property and it is asserted in both
  directions (`test_first_mate_speaks.py::test_the_body_is_exactly_the_join_of_the_sections`
  plus an arm proving the join can fail), so a surface that cannot fold —
  Telegram, a log, a plain reader — is handed the identical text it always was.
  The dashboard renders headline + a `How I worked this out — every caveat`
  disclosure. Same treatment on the dividend.
- **Never re-ask what was already answered.** *"'What should I open instead? A
  word or two.' this question i actually already answered in the second question
  about purpose."* `_answers_already_given` reads the role, the dream and the
  organisation back onto the ranked offer: each candidate gains `you_said` (the
  operator's own words its name carries), and where EXACTLY ONE candidate
  matches, the offer gains `confirm` — the open ask becomes *"you said X — start
  with Y?"*, one tap. Two matches is a choice, not a confirmation, and stays one.
  The escape hatch's field pre-fills from `prefill`: a word they gave that the
  ranking never produced, taken from the DREAM before the role (question two is
  where a target is named; question one is where "small" is). Nothing is
  recorded by reading their answers back — they still answer.
- **Name first, then guess.** *"if the very first question is 'What is your
  name?' then it may more intelligently guess the user account across the
  tools."* Question one gains the name as its opening line (optional — a cabinet
  that will not start without your name is an interview). It lands under
  `captain.name` through `availability.record_captain_name`, so the answers file's
  `captain:` block keeps exactly ONE writer and the generator stamps it on its
  next run; a failed write does not cost the operator their answer. With a name
  on record, `research.identity_guess` proposes one account per connector under
  three STATED rules over the one tokenizer — the whole name, every word of it,
  or a joined form (`nathanielrefslund`, `nrefslund`). No prefix, no edit
  distance, no similarity: those produce a wrong-person match that reads exactly
  like a right one. Two matches on one connector produces NO guess and says so.
  The surface renders a confirm chip per connector; **nothing is recorded
  without the operator's tap**, through the same `record_operator_identity` act a
  pick from the list uses.
- **Probes run without asking.** *"'What I went and looked for' it should just
  autonomously look for it without asking."* The gap was ordering: the probes
  were derived and deferred (`no_search_tool_connected`) when the seed was
  typed, a search tool was connected afterwards, and nothing re-ran them. The
  look-up now re-fires inside `declare_connector` (search lane only, seed
  present, and only when the last run actually stopped for want of a search
  tool) and inside `gather_connectors`. `_run_seed_probes` is the one
  composition all four callers share.
- **Findings speak as the First Mate.** *"if it is from the first mate, make it
  look like a message from first mate."* The card carries `speaker:
  "coordinator"` — a ROLE, never a name: the framework does not know what a
  deployment calls its coordinating officer, and the surface resolves the title
  through `lib/officer-title.ts` (`COORDINATOR_ROLE` + `officerTitle`). The
  dividend leads with the finding's plain meaning and puts the receipt,
  coverage, binding, clocks and look-ups in the fold. Presentation only: the
  finding's content and citations are byte-identical to the core's.
- **A broad window, with informed consent.** *"i really want the cabinet to
  fully control the entire mac!! so this option should be possible (not just
  home folder)."* The flat home-folder refusal is gone. The whole home folder is
  ALLOWED; the Charter states the trade-off before it is approved — still
  read-only, still skipping secrets/personnel/pay/customer-personal/legal/
  corporate-finance by name, and the honest part: the First Window still opens
  at most `MAX_FILES` files ranked most-informative, so a wider root makes the
  FIRST look SHALLOWER, not deeper. What stays refused is refused for OWNERSHIP,
  not size: the whole disk, a directory that holds other people's home folders,
  and a named set of OS-owned roots — for each, the operator's ownership answer
  cannot honestly be "mine". A specific folder inside any of them is an ordinary
  window. The deeper desire — the cabinet CONTROLLING the Mac — is the trust
  ladder's, and the copy says where control actually comes from rather than
  faking it here.
- **A finished operator is told so** — answered by `feat/onboarding-arrival`,
  which landed the same day and first. The two branches diagnosed one live
  report (*"i believe i've answered everything and am now stuck and can't
  continue again?"*) and both wrote an ending; the arrival screen is the one
  that ships, with its own stage, summary-from-recorded-answers, management view
  and a shared completion-parity fixture. What this branch contributes to it is
  the LAYERING every other card here gained: the arrival card carries a
  `speaker`, a headline built from `_arrival_clauses` — the operator's own
  recorded sentences, never re-authored — and `details` whose join is the body
  the core already published. The duplicate predicate this branch had added
  (`journeyIsComplete` in `wizard.ts`) was deleted in the merge: `completion.ts`
  and `journey_has_arrived` are the one rule, and two spellings of "finished" is
  how a router stops redirecting while a page still offers only more questions.
- **Sensors:** `framework/onboarding/tests/test_first_mate_speaks.py` (46 arms
  across all seven, each layering arm paired with a losslessness arm, plus the
  degenerate ends: no sweep, no name, two lookalikes, no seed, an incomplete
  journey, and a whole-home window that still refuses a sensitive file), and the
  dashboard arms in `journey-card.test.ts` — the fold carries every section, a
  guess sends nothing until it is tapped, and the completion block agrees with
  the redirect's predicate.

## 2. Product doctrine

### One core, three surfaces

There is one Captain identity, journey, Charter, event history, current card,
and organization.

- **Dashboard** is the dense face: scopes, evidence, Strategy Mirror,
  organization, commissioning matrix, receipts, and audit.
- **Telegram** is a complete conversational face. A Captain can start, approve,
  pause, continue, revoke, undo, purge, commission, and operate without a visual
  platform. OS/provider ceremonies may deep-link out and must return to the same
  checkpoint.
- **World** is the spatial and emotional face. Its authenticated overlays render
  and resolve the same cards through the shared service. The map/state engine and
  `/api/world/*` readers gain no independent onboarding write path.
- **Cabinet Companion/app shell** installs, starts, updates, notifies, and routes.
  It is not a fourth database. `Continue Orientation` opens `/onboarding` with
  fresh trace/correlation IDs so the handoff is reviewable without app-shell state.

Surfaces have capability parity, not pixel parity. A Dashboard evidence list can
be a Telegram receipt and a World parchment, but card id, revision, allowed
actions, evidence, and resolution are identical.

### One Chair, one voice

The same Chair speaks everywhere. Stable card ids, optimistic revisions, a
process lock, and action idempotency make a decision resolve once. A stale
surface refreshes instead of overwriting the newer choice.

### Human words at the floor

Say Folder, Documents, Calendar, Mail, accounting export, and project board.
Do not require a Captain without technical vocabulary to understand MCP, API, repository, env
var, JSON, YAML, Redis, launchd, or posture.

## 3. Earned-intelligence sequence

### 0. Relationship destination

Ask where the Captain wants the relationship to head:

1. **Earn every responsibility.**
2. **Be proactive where actions are reversible.** Recommended.
3. **Aim for broad autonomy after it is earned.**

This is a destination, not a grant. It cannot activate a posture, grant,
officer, outcome, connector, send, deploy, or purchase.

### 1. First Window Charter

Ask for one purpose and one narrow source. Before reading, show a plain-language,
hash-bound Charter containing the exact root, purpose, read/write/network effect,
limits, exclusions, retention, lifecycle controls, and destination-with-no-grant
statement.

Entering a folder path is not consent to inspect it. Reads begin only after the
Captain accepts the current Charter hash. Resume revalidates hash and scope.

### 2. First Dividend

Within five minutes of usable access, return one useful result with file, line,
excerpt, and content hash: a broken documented command, conflicting delivery
date, uncovered commitment, urgent item, duplicate process, or inconsistency.

If no strong result exists, say so and return an honest orientation map. Never
manufacture a warning for “wow.” Raw contents are not persisted in this slice;
the manifest retains relative paths, sizes, and hashes, while the dividend keeps
only cited, secret-redacted lines.

### 3. Deep Orientation

Offer bounded, resumable study with a ghost deck and progress stream:

- Source Map with truth authority, volatility, sensitivity, and provenance;
- business, role, rhythm, commitment, decision, and entity maps;
- observed facts separated from inferences and Captain rulings;
- workflows, conflicts, risks, reversibility, and verification inventory;
- missing access requested just in time by the outcome it unlocks.

Orientation begins with one or two read-only sources. Operational read/write
tools come later only when the Cabinet can name task, scope, consequence, and
fallback.

### 4. Strategy Mirror

The Cabinet proposes purpose, 90-day success, constraints, bets, trade-offs,
not-goals, uncertainties, and contradictions with citations. Only the Captain
can edit or ratify the Mirror into Direction. The compiler cannot activate an
unratified mirror.

### 5. Formation

The Cabinet proposes lanes, officers, hats, skills, workflows, memory spaces,
sources, verification, action classes, benchmarks, first outcomes, and a
30–60–90 contract. It explains why each exists and the attention it saves.

The landed `framework.onboarding.formation` machine remains the resumable,
compiler-unreadable scaffold. Until real increments land, its IOUs stay honest
and are not shown as completed orientation.

### 6. Commissioning

Return to the destination with actual examples. Commission per lane and action
class, never through one global switch:

- **earn_up:** all classes propose; rungs require Captain grant.
- **guardian:** approved reversible internal classes may act with real undo and
  receipts; external, irreversible, and ceiling classes remain gated.
- **sovereign:** widest operation toward ratified Direction inside hard
  boundaries, `never_grant`, budgets, verification, and attested grants.

Each cell shows consequence, verification, receipt, undo, and hard ceiling.
Selecting broad autonomy at arrival never bypasses attestation.

### 7. First Campaign and apprenticeship

Run one ratified outcome. Report movement, evidence, actions taken/proposed/
blocked/undone, cost, corrections, and Captain attention. Then onboarding becomes
governance: graduation/demotion digests, expiring grants, permission shrinkage,
trust repair, re-orientation, and organization review.

## 4. Canonical implementation contract

The first slice lives under compiler-unreadable `instance/onboarding/v2/`:

- `state.json`: current projection;
- `events.jsonl`: append-only before/after events and undo references;
- `orientation-charter.json`: payload, hash, and status;
- `first-window-manifest.json`: scope and file hashes, no raw contents;
- `first-dividend.json`: finding and cited redacted lines;
- `window-clocks.json`: the dates the window's own files STATE, one row per
  date, bound to the same `manifest_hash` as the dividend beside it. A row is
  the text as written, the resolved ISO date or `null`, the line, a citation,
  whether it is behind or ahead of the run, where its year came from, and
  whether the file it sits in is calendar-shaped. There is no field for what a
  date relates to, and that is structural rather than pending: relating two
  dated statements is a judgment, and this artifact is the deterministic half.
  A bare month-day takes its year ONLY from a full date in the same file; with
  no such anchor the row keeps its text and states no year, because both
  available guesses (the run's year, the nearest future year) are wrong in
  cases a business folder produces routinely. Surfaces JOIN this artifact at
  render time and never copy rows into their own persisted state: the
  briefing's proposal rows are derived before a window exists and do not
  re-derive after it, so a copy is a copy of nothing;
- `../purge-receipts/`: content-free purge proof.

`framework/onboarding/journey.py` is the sole writer and card builder. It uses a
process lock, atomic owner-only files, idempotent action ids, optimistic
revisions, fixed limits, no network/subprocess, and no source writes.

Every action is also joined into the universal Evidence Recorder v1 plane at
`instance/evidence/v1/`. The onboarding event log remains the canonical journey
state history; the recorder is the tamper-evident correlation/audit plane. It
records intent → policy → execution → verification → receipt → outcome plus
refusal/error/undo and bounded UI/transport/feedback observations. Raw source,
credentials, absolute paths, and hidden reasoning are excluded. Officers see
only the redacted read-only projection; Captain controls retention,
diagnostics, export, and purge. See
`docs/runbooks/evidence-recorder-v1.md`.

| Face | Reader/action path | Shadow state allowed? |
|---|---|---|
| Dashboard | `GET/POST /api/onboarding` | No |
| World | same `/api/onboarding` overlay | No |
| Telegram | authenticated webhook → same core | No |
| Companion | opens `/onboarding` | No |

Purge requires literal `PURGE`, removes all journey content, and cannot be
undone. Revoke stops future reads while retaining derived artifacts until undo
or purge. Undo is event-backed.

### The flow has an ending (added 2026-08-14)

The first slice had no terminal success state. `continue` from `dividend_ready`
landed on `orientation_offered`, a stage whose card was headed "Deeper
Orientation has not started" over a menu of more onboarding — so an operator who
had finished was, on screen, indistinguishable from one who was stuck. Measured
live: the Captain's own journey sat there with the Charter ratified and the
dividend delivered, and he reported "i believe i've answered everything and am
now stuck and can't continue again?".

- `complete` is the terminal stage. `continue` lands there, and only when
  `journey_has_arrived(state)` holds — a ratified Charter AND a delivered first
  dividend. A stage value alone can never announce a success the product cannot
  show.
- `orientation_offered` **is** `complete` (`COMPLETE_STAGES`): journeys
  persisted at the older stage render the same arrival and route the same way.
  Stored state files are NOT rewritten — the event log records what happened,
  and editing history to fix a rendering bug destroys the one thing it is for.
- Both stages emit `kind: "arrival"`, titled "Your Cabinet is ready.", carrying
  the dividend's citations and egress disposition (a summary without its
  citations would be an unsourced claim on the screen whose job is to be
  trustworthy). The deeper-orientation content becomes an OFFER from the
  finished state, with both of its disclosures intact — "That work is disabled
  and has not started", "No new access or authority was granted". `pause` is no
  longer offered there (nothing is running) but is still accepted, so a card
  printed by an older build keeps working.
- `journey.STAGES` declares every stage the card builder renders. It is pinned
  in both directions: `test_every_declared_stage_renders_its_own_card` proves
  each has a live branch, and the dashboard's rail registry
  (`cabinet/dashboard/src/lib/onboarding/flow-rail.ts`) proves each maps to
  exactly one of four monotonic stops — You · Access · First look · Done. The
  six-stop rail it replaced mapped `orientation_offered` two stops BACKWARD from
  `dividend_ready`; that mapping is kept in `flow-rail.test.ts` so the monotonic
  arm is proven able to fail.
- The dashboard mirrors `journey_has_arrived` as `journeyIsComplete`
  (`lib/onboarding/completion.ts`), which gates BOTH the home-page redirect and
  the arrival screen. Both implementations assert against one shared table,
  `framework/onboarding/tests/data/completion-parity.json`, so the two runtimes
  cannot drift into telling the operator different things. Re-entering
  `/onboarding` after completion renders the arrival and its management view
  (what may be read, what was found, connected tools, stop/delete); the wizard
  is structurally unreachable, because its questions are gated on the `welcome`
  stage.

A purge ends that JOURNEY; it does not end onboarding on the instance (fixed
2026-08-02, after a fresh-hatch run measured every later action on every surface
— including the CLI — refused `onboarding_purged` with no way to begin again).
The purged card offers `start_again`, and the next action that can legitimately
begin a journey mints a new `journey_id` with a new evidence trial. Nothing from
the purged journey returns. Two refusals survive and keep "stale actions cannot
reopen them" literally true: an action carrying the deleted card's
`expected_revision`, and the lifecycle actions in `PURGE_TERMINAL_ACTIONS`
(`continue`, `pause`, `revoke`, `undo`, `ratify_charter`, `purge`), which have no
meaning without a live journey. `_act_core` keeps its own unconditional purged
guard for an action already in flight when a concurrent purge landed.

## 5. Validation personas

1. **Software product development — primary dogfood.** Repository, release docs,
   backlog/runbooks, deployments, and strategy. Fixture: documented production
   command missing from `package.json` plus conflicting launch dates. Expected
   dividend: the broken command, cited.
2. **Client-services business.** Proposals, meetings, deliverables, and strict
   external-comms boundaries. Fixture: conflicting delivery dates. Expected:
   both sources cited.
3. **Community/nonprofit coordinator.** Ordinary documents and volunteer rotas;
   low technical confidence; meaning cannot depend on pixel art, color, or
   jargon. Fixture: uncovered welcome-desk shift. Expected: plain-language gap.

Every estate also tests sensitive content, symlinks, binary data, stale cards,
duplicate actions, and lifecycle controls. Secret leakage is a hard failure.

## 6. Acceptance bars

- No content read before exact Charter ratification.
- One cited real-source result targeted within five minutes.
- Honest orientation-only result when no strong finding exists.
- Cross-surface continuation with zero repeated answer or conflicting mutation.
- Telegram performs every slice action, including typed purge.
- World uses the shared service; no onboarding POST below `/api/world`.
- Text labels, 44px targets, DOM evidence, keyboard/screen-reader paths, and no
  critical color-only state.
- Relationship destination has zero authority effect.
- Journey cannot activate outcomes, officers, posture, workflows, grants,
  external communications, spend, or deploy.
- Revoke, undo, purge, stale revision, and idempotency are tested.
- Evidence continuity, hash/signature/anchor verification, crash recovery,
  transport/UI errors, source non-mutation, secret exclusion, redacted export,
  and signed typed-purge receipts are tested.

## 7. Sequence from here

1. First Window vertical slice — implemented.
2. Evidence Recorder v1 universal plane + DOGFOOD-001 — implemented and verified.
3. Replace Formation IOUs with bounded discovery and real progress while
   retaining Charter validation and spend/call caps.
4. Source Map and provisional memory classes.
5. Strategy Mirror → Captain Direction ratification.
6. Formation dossier and organization ratification.
7. Per-lane commissioning and deliberate sovereign ceremony.
8. First Campaign and apprenticeship governance.
9. Commercial hardening: notarization, sandbox/Keychain evidence signing,
   secure credentials, update/restore,
   managed hosts, and real usability trials.

Do not build three onboarding applications. Build one commissioning engine and
give it three truthful faces.
