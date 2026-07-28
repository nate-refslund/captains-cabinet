---
name: cabinet-init
description: Onboarding interview for a new Cabinet deployment. Use when a captain sets up this repo for the first time (or adds/changes lanes) — interviews purpose-first (mission + focus letter), then for captain profile, lanes, org shape, autonomy posture, and seed outcomes, writes instance/config/cabinet-init.answers.yml, runs cabinet/scripts/generate-instance.py, and prints the exact activation steps. Idempotent on re-run. A zero-question fast lane exists for defaults-accepting hatches (generate-instance.py --defaults).
---

# Cabinet Init — the onboarding interview

> **Post-hatch continuation:** this skill still owns deterministic instance
> generation. Once the deployment exists, continue through the canonical
> Onboarding v2 First Window at `/onboarding`, Telegram `/onboard`, or the World
> overlay. All three consume `framework.onboarding/journey.py`; do not create a
> skill-local or surface-local journey state. Design:
> `docs/plans/onboarding-v2-design-of-record-2026-07-14.md`.

You are interviewing the captain sitting in this Claude Code session and
turning their answers into this deployment's `instance/` configuration.
The repo stays UNIVERSAL — everything captain- or lane-specific lands
only under `instance/` (and secrets only in the gitignored
`cabinet/.env`). Nothing you generate activates anything: contexts ship
`active: false`, projects ship `activation.status: pending`, outcomes
ship `status: draft`, and officers start only when the captain runs the
printed deploy steps.

**Idempotency:** safe to re-run any time (new lane, changed boards,
renamed captain). The answers file is the single input; the generator
overwrites only files it generated before (marker-checked), never
hand-authored ones. Before appending outcomes, check for existing ids.

## Fast lane — one confirm, zero questions (`--defaults`)

For a stranger/demo hatch — or any captain happy to start from safe
defaults and refine later — skip the interview entirely:

```bash
python3.12 cabinet/scripts/generate-instance.py --defaults [--captain-name NAME]
# clone ships a previous deployment's instance/ (or its answers file)?
# the refusal teaches the one-confirm fix — and names the previous captain
# whenever the inherited platform.yml records one:
python3.12 cabinet/scripts/generate-instance.py --defaults --adopt
```

`--defaults` writes a marker-stamped
`instance/config/cabinet-init.answers.yml` and then runs the exact same
generation path as the interview (same path jail, secret-shape refusal,
marker-checked overwrites, idempotent byte-identical re-runs; nothing
activates). It never overwrites an interview-written answers file (no
marker ⇒ refusal teaching `--defaults --adopt`, which archives it to
`instance/_pre-adopt-<stamp>/` — nothing deleted; `--force` deliberately
does **not** override that one refusal — an interview record is archived,
never clobbered). A custom `--answers` target must be named
`*.answers.yml` — the one filename shape no generated instance file can
occupy — so the defaults write can never land on a generator output like
`posture.yml`. A refused generation still leaves the marker-stamped
defaults answers file behind: harmless, regeneratable, and the `--adopt`
re-run completes from it. The defaults it picks, exactly:

| Field | Default |
|---|---|
| `captain.name` | `--captain-name`, else `$USER`, else `Captain` (an invalid explicit name refuses loud; an unusable `$USER` falls back silently) |
| `captain.timezone` | `UTC` — placeholder, edit later |
| `captain.telegram_chat_id` | `"0000"` — placeholder address (not a secret); set after the bot exists |
| `cabinet` | `id: main` · `mode: single` · `org_shape: portfolio` · default `officer_model` |
| `lanes` | one placeholder lane: `First Lane` / `first-lane`, no repos, no boards, `task_system: none` — rename it, or clear it to `[]` after running discovery (§2) |
| `mission.altitude` | ABSENT unless `--altitude <rung>` is passed (`hatch.sh --altitude` threads it through); unknown stays unknown |
| `autonomy` | `posture: propose_first` · `flavor: org` (OrgSource recall, no personal estate) · `target_posture: guardian` — explicitly consent-safe; nothing can scaffold sovereign |
| `integrations` | `bot_token_env: TELEGRAM_COS_TOKEN` (env-var NAME only), no bot username yet |

To refine afterwards: edit the answers file and re-run **without**
`--defaults` (a `--defaults` re-run rewrites the file with fresh
defaults — it carries the generated-by marker, so the generator owns
it), or run this interview — it loads the existing answers and asks
only about gaps/changes (placeholder values count as answered, so
correct them when refining). The full interview below stays the default
lane for real captains.

## Flow

Work through the seven phases (0–6) in order. Ask conversationally,
batch related questions, and confirm the assembled answers back before
generating. If an answers file already exists, load it first and only
ask about gaps/changes.

### 0. Mission — purpose first

Before any lane, board, or bot: ask what the org is FOR. Three
questions, in the captain's own words:

1. **Purpose** — "What is this org for? What should it make true?"
2. **90-day success** — "What does success look like in ~90 days?"
3. **Never touch** — "Anything the org must never touch or do without
   you?" (a short list; it becomes a standing, visible constraint on
   every proposed card).

**Dual output — write BOTH:**

- **The focus letter** — `instance/config/onboarding-focus.md`: a short
  prose letter assembled from the answers (bearing, not tasks), read
  back and corrected before writing. It is a first-class artifact now,
  not an optional sidecar: genesis reads it
  (`framework/onboarding/genesis.py`) and anchors the org's first
  proposed outcome cards to it. Never overwrite an existing letter
  without the captain's explicit yes.
- **The `mission:` block** — a machine-readable top-level key in the
  answers file (schema in "Write answers + generate" below):
  `purpose`, `success_90d`, `never_touch: []`, `altitude`. The zero-LLM
  generator ignores `purpose`/`success_90d`/`never_touch` (a test pins that
  tolerance) and genesis conditions its proposed outcome cards on them.
  Propose-only as ever — nothing in the mission block activates anything.

4. **Altitude** — "What can you actually DECIDE where you work?" It is not
   a title and it is not seniority; it bounds what a proposed outcome's
   PROOF can be. Map the answer onto exactly one rung — `contributor` |
   `project` | `team` | `function` | `company` — and record it as
   `mission.altitude`. **OMIT it if the captain does not answer**: unknown
   is a legal state and every consumer keeps its pre-altitude behaviour;
   a guessed rung is a value pretending to be an answer.

   Why it is asked at all: the north star is an AIM, not an entry bar
   (Captain ruling 2026-07-26). A developer inside a large company does not
   get to run it, and the cabinet must be valuable to them anyway. Altitude
   is LOAD-BEARING in two places — it selects the preset
   (`generate-instance.py --print-preset`, which is what `hatch.sh` writes
   into `instance/config/active-preset`) and it reshapes every proposed
   card's proof line. At `contributor`/`project`/`team` the six hard
   ceilings (external comms, production deploys, spend, secrets, network
   writes, credential grants) belong to the captain's EMPLOYER, not to
   them, so a "shipped and deployed" proof is unreachable by org chart
   rather than by cabinet quality. There the proof becomes proposal-shaped:
   evidence assembled across what they already read, delivered to whoever
   owns the decision. **Say the promise plainly: expanded reach and
   proposal quality, never permission that is not theirs to grant.**

**Optional MCP-estate glance (consent-gated, names only):** offer —
never assume — "May I read the MCP server NAMES this repo declares
(`.mcp.json` + `instance/config/extensions.yml`), to ground the lane
questions? Names only, never values." Only on an explicit yes, call
`framework.onboarding.research.inventory_mcp_estate(root, consent=True)`
and narrate the names found. A no (or silence) skips it silently — it
reads nothing without consent, and it never touches the captain's
user-level Claude config.

`--defaults` skips this phase entirely (no mission block, no letter) —
the zero-question fast lane above is unchanged.

### 1. Captain profile

Collect:
- **Name** — display name officers use (e.g. `Ada`).
- **Timezone** — IANA identifier (e.g. `Europe/Madrid`). All officer
  communication renders times in it.
- **Telegram chat id** — the captain's numeric chat id (an address, not
  a secret; the bot TOKEN never goes in config). If unknown, it can be
  read from any incoming message's `chat_id` after the bot exists —
  leave it for a re-run rather than guessing.
- **Quiet hours** — a silent default is an invisible feature (Captain
  insight 2026-07-17): PRESENT it, never assume the captain knows a
  quiet time exists. Render the question from the LIVE framework
  default — never hardcode the times; if the default changes, the
  question follows:

  ```bash
  python3.12 -m framework.onboarding.quiet_hours question
  ```

  It reads `framework/attention/charter-default.yml` and asks, e.g.:
  "Quiet hours are 21:00–07:00: outside pings are held for the morning
  briefing except infrastructure pages and security alerts. Keep,
  change, or disable?" Ask it verbatim, then map the captain's answer
  onto EXACTLY one verb — conversational free text never reaches the
  command line (fixed enum + 24h HH:MM only; anything else refuses
  loudly and writes nothing, so just re-ask):

  ```bash
  python3.12 -m framework.onboarding.quiet_hours apply --choice keep
  python3.12 -m framework.onboarding.quiet_hours apply --choice change --start 22:00 --end 06:00
  python3.12 -m framework.onboarding.quiet_hours apply --choice disable
  ```

  `keep` (or an unclear answer) writes NOTHING — the framework default
  already rules; on a re-run it refuses (never silently reverts) when
  the deployment already carries a different ruling. `change`/`disable`
  materialize the deployment override at
  `instance/config/comms-charter.yml` through the charter system's own
  amend path (chair provenance + amendment-ledger row, schema-validated
  fail-closed BEFORE any write; `disable` is the zero-length window the
  attention gate treats as never-active). The quiet-hours floor — the
  classes that may still ping at night — is carried unchanged: this
  question can never widen it.
- **Availability** — how much time a day the captain has for the
  cabinet (Captain ruling 2026-07-26). Same reason quiet hours is
  asked: a silent default is an invisible feature, and until this was
  asked nothing knew the budget it was spending. **The org fits the
  declared budget, never the reverse** — the Captain-Seat Review judges
  every ask relative to it, and the comms surface paces from it. Render
  the question from the LIVE mode table, never a hardcoded copy:

  ```bash
  python3.12 -m framework.onboarding.availability question
  ```

  It reads `framework.env.AVAILABILITY_MODES` and asks, e.g.: "How much
  time a day do you have for the cabinet? … Options: minimal (about 10
  minutes a day); part_time (about 30 minutes a day); substantial
  (about 2 hours a day); full_time (the cabinet is my main seat)." Ask
  it verbatim, then map the answer onto EXACTLY one verb — free text
  never reaches the command line:

  ```bash
  python3.12 -m framework.onboarding.availability apply --choice part_time
  python3.12 -m framework.onboarding.availability apply --choice skip
  ```

  `apply` records `captain.availability` in the answers file; the
  generator stamps `captain_availability_minutes_per_day` +
  `captain_availability_mode` into `instance/config/platform.yml` on
  the next run. **`skip` (or an unclear answer) writes NOTHING** — the
  value stays UNKNOWN, a legal documented state meaning "the org does
  not know how much of the captain it is entitled to", and every
  consumer keeps its own conservative default. NEVER invent a number to
  fill the gap: a placeholder that pretends to be an answer is the named
  failure here. The captain can set or change it any time from his phone
  — `availability 20m` / `availability part_time` / `availability away`
  / `availability ?` — which appends to
  `instance/config/captain-availability.yml` and OUTRANKS the platform
  key, so a later re-run of the interview can never demote his own
  ruling.

### 2. Lanes — ASK LAST, and prefer to READ them

A **lane** is a product/venture/area the Cabinet works (see
`framework/docs/work-model.md` — products are lanes, not outcomes).

**A captain who owns no product is not a broken captain.** Since the
ordering inversion (Captain ruling 2026-07-26,
`docs/plans/onboarding-ordering-inversion-2026-07-26.md`) `lanes: []` is a
legal answer whenever discovery has RUN: grant one read-only First Window
(`/onboarding`, Telegram `/onboard`, or the World overlay) and run
`bash cabinet/scripts/formation.sh`, which derives
`instance/onboarding/formation/derived-estate.yml` from what was actually
read and proposes lanes — with citations — in
`instance/config/lanes-proposed.yml`. Ratifying one is copying its row into
this answers file and re-running the generator; nothing self-activates.
Offer that path BEFORE asking a captain to name products, and never invent
a placeholder lane to get past the generator.

Per declared lane:

- **Name** (human, e.g. `Acme Storefront`) and **slug** (kebab-case,
  e.g. `acme-store` — becomes the context slug and the `<slug>-ceo`
  role id).
- **Repo(s)** — `org/name` or URL; first repo becomes `product.repo`.
- **Task system + board ids** — e.g. `plugin:dev-tasks` with board ids,
  `linear` with a team key, `github-issues`, or `none`. When the route
  is a plugin, the project file deliberately carries NO tasks block —
  just a comment saying so (avoids duplicate adapters).
- **Infra identifiers as NAMES only** — Neon project NAME, hosting
  project NAME. Never connection strings, never keys.

### 3. Org shape

- **portfolio** (recommended for multi-product captains): one
  persistent Chair (officer id `cos`, single bot, the only human
  surface) + one on-demand lane-CEO consultant per lane, generated from
  `presets/portfolio/agents/_lane-ceo.md.template`. Functional depth
  comes from hats + Sonnet crew, not extra officers.
- **functional** (single product): the classic five-officer roster
  (cos/cto/cpo/cro/coo) from the `work` preset; no per-lane roles
  generated.
- **custom**: contexts + projects only; the captain authors roles by
  hand (see `presets/_template/`).

### 3b. Preset (OPTIONAL — ask only for the functional shape)

The functional shape defaults to the `work` preset. One follow-up
question, only when `org_shape: functional`:

> Is the product you're shipping a **software / web / app product**? If
> yes, the OPTIONAL **developer** preset is the software product-kind
> kit — the work roster plus day-1 connector declarations (GitHub MCP,
> Playwright, read-only Neon; Vercel by REST+probes; Sentry armed when
> keys exist) and a Product Journal starter Space
> (`presets/developer/README.md`). Default is work — say "developer" to
> opt in.

Map the answer onto the fixed slug enum — `work` (default) |
`developer` — and record it as `cabinet.preset` in
`cabinet-init.answers.yml` ONLY when the captain opted in (absent =
default; the choice is opt-in, never a default flip; conversational free
text never becomes a slug). The generator validates the slug shape.

**Resolution order is `cabinet.preset` > `mission.altitude` > `org_shape`**
and lives in ONE place — `generate-instance.py resolve_preset()`, printed
by `--print-preset`, which is what `hatch.sh` writes into
`instance/config/active-preset`. A declared `contributor`/`project` rung
resolves to **`personal`** — the one shipped preset with no C-suite
(Navigator / Librarian / Reviewer, for an operator who owns a project, not
a company). An explicit `cabinet.preset` always outranks it, and the
resolved slug must have a `presets/<slug>/preset.yml` or the hatch stops
with a named handback. If the captain chose
`developer`, also add its extra env-var NAMES — `NEON_API_KEY`,
`VERCEL_API_KEY`, `VERCEL_TEAM_ID` — to `integrations.mcp_env_names` so
`setup-env.sh` walks them (values still go only in `cabinet/.env`).

### 4. Autonomy posture — GUARDIAN at init; sovereign is a post-init Captain ratification

(Superseded 2026-07-05 by the sovereign-posture amendment, apply token
`apply sovereign posture` — this section previously said "NOT negotiable
at init"; init is still guardian-only, but the interview now RECORDS the
target so the generator can render the inert scaffold.)

State it, don't ask for permission tuning:

> Every deployment STARTS **guardian**: propose-first everywhere, and the
> **hard ceilings** — secrets, spend, external communications, production
> deploys, network writes, credential grants — **never resolve
> UNCONDITIONAL auto in any posture.**
>
> The **sovereign posture** is not an init option — it is a **post-init
> Captain ratification**: the generator renders an INERT
> `instance/config/posture.yml` scaffold (guardian by default; a `mini*`
> org cabinet id or an explicit `autonomy.target_posture: sovereign`
> renders a sovereign target), and NOTHING changes until the Captain
> edits `basis`/`ruled_at`, commits, and runs
> `sudo bash cabinet/scripts/germline-lock.sh lock` — the schg lock IS
> the signature; unlocked/absent/mismatched always resolves guardian.
> Under a ratified sovereign posture, ceilings resolve `standing_grant`
> (auto ONLY under a Captain-signed locked grant with its hard-scope
> satisfied; else the step gates + files a NEED and the chain proceeds).
>
> Per-cell autonomy is still **earned from evidence**: the consequence
> ledger (`framework/docs/consequence-ledger.md`) records every action's proposal
> decision, outcome, and review verdict; graduation math reads only that
> ledger, and posture never enters graduation — bars define PROOF,
> posture defines what unproven states UNLOCK.

**Axes interview (axes spec 2026-07-05 §1/§5) — ask ONE question per
axis, then act on the matching preset:**

1. **Level** — "guardian (the default — trust-first on reversible
   classes, lost on evidence), earn_up (everything proposes; cells climb
   only on Captain-granted rungs), or sovereign (boundless under standing
   grants — requires the attested lock ritual)?" Default **guardian** on
   any unclear answer.
2. **Flavor** — "org (a product org cabinet: senses product telemetry,
   machine-probe labels) or personal (your own surfaces, captain-verdict
   labels)?" Record `autonomy.flavor`. External-comms grantability is NOT
   flavor-structural (Captain correction 2026-07-05): a captain who never
   wants a class granted lists it under `never_grant:` in posture.yml
   (e.g. `[external_comms]` — ACT-AND-DRAFT), in any flavor.
3. **Deployment target** — "macbook (shared daily machine), mac_mini
   (dedicated host), or docker (container — attestation is the host-side
   `:ro` bind mounts)?" If unanswered, omit `deployment_target:` and the
   resolver infers (`/.dockerenv` ⇒ docker, else macbook).

The three shipped presets are pre-filled points on these axes —
`instance/config/posture-presets/{personal-macbook,org-macmini,org-docker}.yml`
(personal-macbook: guardian·personal·macbook + a `never_grant` example;
org-macmini: sovereign·org·mac_mini; org-docker: guardian·org·docker).
Any axis combination is valid — copy the nearest preset and set the
differing fields.

**Write rules (the skill acts here; the generator never overwrites an
existing ruling):**

- **guardian or earn_up** level, and `instance/config/posture.yml` is
  ABSENT: copy the matching preset to `instance/config/posture.yml`, set
  `deployment:` to the cabinet id, `posture:` to the chosen level, and
  `flavor:` / `deployment_target:` / `never_grant:` from the answers.
  Leave it unlocked — guardian is the fail-closed default anyway, and
  `earn_up` is honored even unattested (it can only narrow). NEVER
  overwrite an existing posture.yml.
- **sovereign** level: do NOT write a sovereign ruling — print the
  attestation ritual verbatim instead (widening is a Captain act, never
  an init side-effect):

  ```
  sudo bash cabinet/scripts/germline-lock.sh unlock   # Captain unlock window
  cp instance/config/posture-presets/org-macmini.yml instance/config/posture.yml
  $EDITOR instance/config/posture.yml   # deployment: <cabinet id>; basis/ruled_at
  git add -A && git commit
  sudo bash cabinet/scripts/germline-lock.sh lock     # the lock IS the signature
  ```

  (docker target: the ritual is host-side — edit in the host checkout and
  keep the `:ro` bind mount.) Record `autonomy.target_posture: sovereign`
  so the generator's inert scaffold carries the target; the deployment
  runs guardian until the Captain performs the ritual.

Record `autonomy.posture: propose_first` as before and move on. Runtime
narrowing never needs a ritual: `CABINET_POSTURE=guardian|earn_up` env,
the Captain's `posture guardian|earn_up` binder verb (writes
`instance/config/posture-narrow`; `posture clear` removes the cap), or
the dashboard `/posture` tile's printed verb — the tile itself is
render-only (`cabinet/scripts/posture-status.py` supplies its JSON).

### 5. Seed outcomes (1–2 bounded campaigns per lane)

Interview each lane for at most 1–2 **campaigns**, applying both tests
from `framework/docs/work-model.md` before accepting one:

- **Inclusion test**: a verifiable STATE CHANGE ("the world changed
  from X to Y"), never an activity ("keep doing X" fails).
- **Campaign test**: the work needs orchestration structure the stream
  cannot give — step ordering, verification gates, risk-tiered
  approvals, cross-role handoffs. A batch of backlog items with a bow
  on it is stream work, not a mission.

Zero seed outcomes for a lane is healthy (officers work the stream).
For each accepted campaign, append an entry to
`instance/config/outcomes.yml.draft` (create the file with a short
header pointing at `framework/schemas/outcome.schema.json` and
`framework/docs/work-model.md` if it doesn't exist) with:

- `status: draft`, `captain_ratified: false` — the captain ratifies
  per outcome later; the compiler ignores drafts.
- `measurable_criteria` as rich nodes where you can (owner_role,
  acceptance_criteria, evidence_required, verifier_role, risk_level);
  owner/verifier use the generated role ids (`<slug>-ceo`, `cos`).
- Mark any production-deploy / external-comms / spend criterion
  `risk_level: high` with an explicit PROPOSE-ONLY acceptance line.

On re-run: never duplicate — skip ids that already exist in the draft.
Validate the draft parses against the schema before finishing.

### 6. Integrations checklist

Walk it with the captain; config carries env-var NAMES and `TOKEN-TBD`
placeholders only:

- **Telegram bot** (the single human surface): create ONE bot via
  BotFather (`/newbot`), record the bot USERNAME in the answers, and
  put the token ONLY in `cabinet/.env` under the chosen env-var name —
  canonical: `TELEGRAM_<OFFICER_UPPER>_TOKEN` (e.g.
  `TELEGRAM_COS_TOKEN=...`; legacy `TELEGRAM_BOT_TOKEN_<UPPER>` still
  resolves as a fallback). Never reuse a token another
  poller uses — two pollers on one token steal each other's updates.
  Optional warroom group: create the group, invite the bot, store the
  group chat id env name the same way.
- **macOS TCC grants** (Mac-native deployments): run
  `bash cabinet/scripts/grant-mac-permissions.sh` — interactive; the
  OS requires human clicks. This and the bot token are typically the
  only captain-blocking steps.
- **MCP env var NAMES**: list the env vars the deployment's MCP servers
  need (database, hosting, search APIs) in
  `integrations.mcp_env_names`; values go in `cabinet/.env`
  (chmod 600, gitignored). `bash cabinet/scripts/setup-env.sh` walks
  key entry interactively.

## Write answers + generate

1. Write the assembled answers to
   `instance/config/cabinet-init.answers.yml`. Schema (also available
   via `python3 cabinet/scripts/generate-instance.py --example`):

   ```yaml
   version: 1
   captain: {name, timezone, telegram_chat_id,
             availability}                      # OPTIONAL time budget: away |
                                                #  minimal | part_time |
                                                #  substantial | full_time.
                                                #  OMIT to leave UNKNOWN — never
                                                #  a placeholder number
   mission:                                     # Phase 0 (purpose-first interview)
     purpose: <one sentence>                    #  purpose/success_90d/never_touch:
     success_90d: <one sentence>                #  the generator IGNORES them (pinned
     never_touch: []                            #  by test); only genesis reads them
     altitude: contributor                      #  OPTIONAL rung: contributor | project
                                                #  | team | function | company. NOT
                                                #  inert — selects the preset AND
                                                #  reshapes every card's proof line.
                                                #  OMIT to leave it UNKNOWN
   cabinet: {id, mode: single|multi, org_shape: portfolio|functional|custom, officer_model,
             preset}                             # preset OPTIONAL (§3b) — slug only,
                                                 #  e.g. developer; absent = shape default
   lanes:                                      # [] IS LEGAL once discovery ran —
     - {name, slug, repos: [], task_system, boards: [],   # see §2; the generator
        neon_project, vercel_project,            # NAMES only    accepts an empty list
        linear_team_key, linear_workspace_url}   # when task_system: linear
                                                 # only when a derived-estate artifact
                                                 # exists for this deployment
   autonomy: {posture: propose_first,            # fixed at init
              flavor: org,                       # org | personal (§4; also gates the
                                                 #  sources.yml recall binding — org emits
                                                 #  OrgSource, personal emits LocalNotesSource)
              target_posture: guardian}          # optional; guardian default, 'mini*' org ⇒ sovereign
                                                 # (an earn_up choice rides the preset-written
                                                 #  posture.yml from §4, not this key)
   sources:                                     # OPTIONAL, personal flavor only
     notes_root: ~/Documents/notes              #  the ONE folder recall reads,
                                                #  read-only. NO DEFAULT: omit it and
                                                #  recall resolves UNSET (available()
                                                #  False, every gather honestly empty).
                                                #  ASK for it on flavor: personal —
                                                #  an unpointed personal box has no
                                                #  recall at all
   integrations:
     telegram: {ceo_bot, bot_token_env}          # username + ENV VAR NAME
     mcp_env_names: []                           # ENV VAR NAMES
   ```

2. Run the generator and show the captain its output:

   ```bash
   python3 cabinet/scripts/generate-instance.py            # add --dry-run to preview
   # Clone ships a PREVIOUS deployment's instance/ (hand-authored
   # sources.yml, an unmanaged officers block, live contexts)? Use:
   python3 cabinet/scripts/generate-instance.py --adopt
   # --adopt archives each conflicting file to instance/_pre-adopt-<stamp>/
   # (never deletes) and generates fresh; an existing posture.yml ruling is
   # still never touched. The overwrite refusal teaches this itself: when
   # instance/config/platform.yml carries a DIFFERENT captain_name than the
   # answers, the refusal names the previous captain and suggests --adopt.
   ```

   It generates (portfolio shape): per-lane
   `instance/config/contexts/<slug>.yml` + `projects/<slug>.yml`,
   `instance/agents/<slug>-ceo.md` (rendered from the lane-CEO
   template), the marked `officers:` block + captain keys in
   `instance/config/platform.yml` (plus an `org_vault_dir:` key —
   only when absent, and never over a hand-edited legacy
   `product_brain_dir:` key — defaulting to `vault`, relative to the
   deployment root; canonical resolver
   `framework.env.org_vault_dir()`, `CABINET_ORG_VAULT_DIR`
   overrides, legacy `CABINET_PRODUCT_BRAIN_DIR` alias honored),
   `instance/config/roster.yml`
   for `bootstrap-roles.sh --roster` — the HIRE record, carrying the
   Chair plus ONLY those lane CEOs both germline files already
   authorize (see "Hiring is authorization-gated" below),
   `instance/config/active-project.txt` (first lane slug, only when
   absent — bootstrap-roles.sh needs it for the product slug and
   start-officer-mac.sh reads it for CABINET_LANE; **NOT written at all
   when `lanes: []`** — a placeholder slug there would be a value
   pretending to be an answer, so the generator prints the ratification
   path instead), and — only when absent — the INERT
   `instance/config/posture.yml` ruling scaffold (§4; an existing ruling
   is never regenerated, not even with --force).

   **Recall binding** (`instance/config/sources.yml`): when
   `autonomy.flavor` is anything but `personal` (i.e. `org`, the
   default), the generator emits a marked `sources.yml` binding
   `framework.sources.org:OrgSource` — so a fresh org instance has
   real recall instead of fail-closing to `NullPersonalSource` (zero
   hits). No `dispatch:` is emitted (writes fail-close to
   `NullPersonalDispatch`, draft-capture-only). `flavor: personal`
   ALSO emits a marked `sources.yml` — binding
   `framework.sources.local:LocalNotesSource` over a `local_root:`
   taken from the answers' `sources.notes_root`, read-only, with no
   write side and no `dispatch:` either.

   **ASK for `sources.notes_root` whenever `flavor: personal`.**
   CHANGED 2026-07-28: `local_root:` used to be HARDCODED to `vault`
   with no answers-file override, and `<root>/vault` is the
   cabinet's OWN shipped documentation (`vault/README.md`,
   `vault/architecture.md` are tracked) — so a fresh personal hatch
   silently bound the framework's own docs as the operator's notes
   and reported `available()` True. There is now NO default: an
   undeclared folder emits `local_root:` commented out, the adapter
   resolves UNSET, and the first briefing says so with the fix. An
   honest unavailable beats a plausible wrong folder, because the
   operator can act on the first and cannot even see the second.
   CHANGED 2026-07-27: before
   that, `personal` emitted nothing at all and a personal box
   fail-closed to `NullPersonalSource` (`available()` False,
   `search()` returning no hits) — so the ONE flavor shaped for an
   operator who does not run a company was the one flavor that
   shipped inert. An existing hand-authored sources.yml (no
   generated-by marker) is never clobbered on either flavor.

   **Hiring is authorization-gated** (roster-authz, 2026-07-26). An
   officer is only usable when `cabinet/officer-capabilities.conf`
   grants it capability rows AND `cabinet/mcp-scope.yml` lists it
   under `agents:`; without both, every capability-gated behavior is
   off for it and `pre-tool-use.sh` rejects every `mcp__*` call its
   session makes. Both files are germline — neither this generator
   nor `hatch.sh` may write them — so the generator READS them and
   rosters only what they already cover. A lane whose CEO is not yet
   authorized still gets its context, project and agent file (all
   inert) and is recorded as PENDING in `roster.yml`, with the exact
   rows printed for the captain to paste. Re-running the generator
   after the captain applies them hires the lane CEO. This is why
   step 2 below is OPTIONAL and blocks nothing: a fresh hatch
   completes Chair-only and green.
   `framework/tests/test_roster_conf_lockstep.py` is the gate that
   fails any deployment whose roster names an unauthorized officer.

   It refuses path escapes, secret-shaped values, and clobbering
   hand-authored files, and validates every written YAML.

## Print the exact next steps

Relay the generator's printed list, expanded:

1. `echo <preset> > instance/config/active-preset` (portfolio /
   work / developer / custom preset slug — developer is the OPTIONAL
   software product-kind kit, §3b).
2. **Germline edits — OPTIONAL, blocks nothing (propose to the
   captain; the captain applies):** add each un-hired `<slug>-ceo`
   under `agents:` in `cabinet/mcp-scope.yml` and add its capability
   rows to `cabinet/officer-capabilities.conf`, then re-run the
   generator to HIRE it. Until then that lane CEO is generated but
   not rostered — deliberately, so no officer is ever hired into a
   silent capability/MCP-scope lockout. Relay the exact rows the
   generator printed; do not invent an `mcps:` list (it prints
   `mcps: []`, fail-closed — the servers a lane needs are the
   captain's call).
3. Bot token into `cabinet/.env` under the recorded env-var name
   (canonical `TELEGRAM_<OFFICER_UPPER>_TOKEN`, e.g.
   `TELEGRAM_COS_TOKEN`; config keeps `TOKEN-TBD`). Multi-cabinet
   deployments also set `CABINET_MODE=multi` + `CABINET_ID=<id>` in
   `cabinet/.env` — in multi mode boot aborts without a CABINET_ID,
   and the outcomes deployment gate compiles missions only when
   CABINET_ID matches.
4. `bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml`
   (functional shape: plain `bootstrap-roles.sh`; add `--prune` to
   retire roles left over from a previous roster). It reads the product
   slug from `instance/config/active-project.txt`, which the generator
   wrote from the first lane — edit that file first to seed under a
   different lane.
5. `bash cabinet/scripts/grant-mac-permissions.sh` (TCC, interactive).
6. `bash cabinet/scripts/load-preset.sh`, then deploy selectively —
   `deploy-mac.sh` for the coordinating role only; lane CEOs are
   on-demand consultants and need no persistent deploy.
7. Ratify seed outcomes. NOTE: the repo may ship a LIVE
   `instance/config/outcomes.yml` pinned to another deployment via its
   top-level `deployment:` key — the compiler refuses any file whose
   `deployment` value differs from this machine's `CABINET_ID`, so a
   pinned file is inert everywhere else (the repo no longer ships an
   `outcomes.yml.draft`; the draft file from phase 5 is just this
   interview's staging scratch). A new deployment REPLACES the shipped
   `outcomes.yml` with its own ratified outcomes (`status: active` +
   `captain_ratified: true`) carrying its own CABINET_ID as the
   deployment key — or no deployment key at all for a single-cabinet
   setup.

Close by restating what is and isn't live: roles seeded, nothing
polling, no lane active, no outcome compiled — each activation is a
separate explicit captain action.
