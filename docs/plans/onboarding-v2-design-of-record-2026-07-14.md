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

**Addendum, 2026-07-30 — the first run is three questions, stepped.** The one
seed question that opened the front ("What do you do, and how can I best serve
you?") was three questions in one breath, and the dashboard rendered it as a
single dense card. It is now a guided, stepped flow — one idea per step, a
visible progress rail, plain Back/Next — asking, in order:

1. **your role** — *"Tell me about you and your work. What do you do?"* Free
   text, any language. Stored as the journey **seed**, the seam genesis reads.
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
