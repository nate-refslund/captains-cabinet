---
name: cabinet-init
description: Onboarding interview for a new Cabinet deployment. Use when a captain sets up this repo for the first time (or adds/changes lanes) — interviews for captain profile, lanes, org shape, autonomy posture, and seed outcomes, writes instance/config/cabinet-init.answers.yml, runs cabinet/scripts/generate-instance.py, and prints the exact activation steps. Idempotent on re-run.
---

# Cabinet Init — the onboarding interview

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

## Flow

Work through the six phases in order. Ask conversationally, batch
related questions, and confirm the assembled answers back before
generating. If an answers file already exists, load it first and only
ask about gaps/changes.

### 1. Captain profile

Collect:
- **Name** — display name officers use (e.g. `Ada`).
- **Timezone** — IANA identifier (e.g. `Europe/Madrid`). All officer
  communication renders times in it.
- **Telegram chat id** — the captain's numeric chat id (an address, not
  a secret; the bot TOKEN never goes in config). If unknown, it can be
  read from any incoming message's `chat_id` after the bot exists —
  leave it for a re-run rather than guessing.

### 2. Lanes

A **lane** is a product/venture/area the Cabinet works (see
`framework/docs/work-model.md` — products are lanes, not outcomes). Per lane:

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
   captain: {name, timezone, telegram_chat_id}
   cabinet: {id, mode: single|multi, org_shape: portfolio|functional|custom, officer_model}
   lanes:
     - {name, slug, repos: [], task_system, boards: [],
        neon_project, vercel_project,            # NAMES only
        linear_team_key, linear_workspace_url}   # when task_system: linear
   autonomy: {posture: propose_first,            # fixed at init
              flavor: org,                       # org | personal (§4; also gates the
                                                 #  sources.yml recall binding — org emits
                                                 #  OrgSource, personal emits none)
              target_posture: guardian}          # optional; guardian default, 'mini*' org ⇒ sovereign
                                                 # (an earn_up choice rides the preset-written
                                                 #  posture.yml from §4, not this key)
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
   # still never touched.
   ```

   It generates (portfolio shape): per-lane
   `instance/config/contexts/<slug>.yml` + `projects/<slug>.yml`,
   `instance/agents/<slug>-ceo.md` (rendered from the lane-CEO
   template), the marked `officers:` block + captain keys in
   `instance/config/platform.yml` (plus a `product_brain_dir:` key —
   only when absent — defaulting to `product-brain`, relative to the
   deployment root; canonical resolver
   `framework.env.product_brain_dir()`, `CABINET_PRODUCT_BRAIN_DIR`
   overrides), `instance/config/roster.yml`
   for `bootstrap-roles.sh --roster`,
   `instance/config/active-project.txt` (first lane slug, only when
   absent — bootstrap-roles.sh needs it for the product slug and
   start-officer-mac.sh reads it for CABINET_LANE), and — only when
   absent — the INERT `instance/config/posture.yml` ruling scaffold
   (§4; an existing ruling is never regenerated, not even with
   --force).

   **Recall binding** (`instance/config/sources.yml`): when
   `autonomy.flavor` is anything but `personal` (i.e. `org`, the
   default), the generator emits a marked `sources.yml` binding
   `framework.sources.org:OrgSource` — so a fresh org instance has
   real recall instead of fail-closing to `NullPersonalSource` (zero
   hits). No `dispatch:` is emitted (writes fail-close to
   `NullPersonalDispatch`, draft-capture-only). `flavor: personal`
   emits NO sources.yml — a Flavor-A captain binds their own personal
   adapter by hand. An existing hand-authored sources.yml (no
   generated-by marker) is never clobbered.

   It refuses path escapes, secret-shaped values, and clobbering
   hand-authored files, and validates every written YAML.

## Print the exact next steps

Relay the generator's printed list, expanded:

1. `echo <preset> > instance/config/active-preset` (portfolio /
   work / custom preset slug).
2. **Germline edits (propose to the captain; the captain applies):**
   add each `<slug>-ceo` under `agents:` in `cabinet/mcp-scope.yml`
   and add its capability rows to `cabinet/officer-capabilities.conf`.
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
