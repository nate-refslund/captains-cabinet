# Clone Convergence Plan

> Produced 2026-06-09 from a deep analysis of the screenpipe estate, this repo
> (convergence-v2), and external research. Subtitle of the original plan:
> *Clone Convergence: screenpipe × Captains Cabinet on the MacBook*.
> Phases and locked decisions are preserved verbatim from that analysis.

## Context

Nate runs two mature, mutually-unaware systems: the **screenpipe estate** (58 pipes → Obsidian vault "second brain", embeddings search, nate-model/voice identity, Telegram approval gate, gated email/Teams send via Make) and **Captains Cabinet** (autonomous Claude Code officer runtime; `convergence-v2` branch is the designated baseline — 55 ahead / 0 behind master, 678 tests green). Goal: a digital-clone-grade system on the MacBook doing multi-project Head-of-Tech work (PolAds, STEPhie/stepnetwork, system self-maintenance, ad-hoc chores + comms), grounded in the vault, with graduated autonomy. Research verdict (triangulated): keep both systems; nothing on the 2026 market replaces either; the bridge is greenfield.

**Locked decisions (Nate, 2026-06-09):**
1. **Autonomy:** graduated, earn per lane (approve-first now; lanes auto-send only after 15 samples / 90% / 14 clean days).
2. **Scope day 1:** all four lanes — PolAds, STEPhie+stepnetwork.dk, system self-maintenance, ad-hoc+comms.
3. **Roster:** CoS persistent + on-demand consultants, idle-stopped.
4. **Topology: dual-track.** Mac Mini = vanilla convergence-v2 soak (single product, no screenpipe, Telegram) — Nate is setting it up now; its feedback lands as commits on convergence-v2. MacBook = second cabinet instance ("hq") of the **same repo/branch** with brain bridge + multi-project + comms. Distinct `cabinet_id`, separate officer bot tokens, per-machine Redis. Quota choreography: Mini missions overnight, MacBook fleet by day (one Max x20 pool covers both + interactive use; ceiling ≈ 3–4 concurrent sessions).
5. **Models:** officers = **Fable 5**; workers/subagents = **Sonnet 4.6**; **Fable 5 as advisor** for escalations.

Base: extend `convergence-v2` in place. No fork. The `funny-fermi-8daf32` worktree = master = obsolete (its untracked analysis docs are tracked in v2); fast-forward `master` → v2 for hygiene.

> **2026-06-19 RE-ANCHOR (read this first; the prose below is the frozen
> 2026-06-09/06-10 snapshot — preserved, not rewritten).** The program decomposed
> into four tracks — **F** (fidelity/training harness, `docs/fidelity-harness-design-2026-06-18.md`),
> **A** (authority matrix + policy engine, `docs/authority-matrix-design-2026-06-19.md`),
> **R** (this operational roadmap, R1–R5), **P** (productize install flavors +
> private-data layer). Two things in the snapshot are now superseded by F + A
> *as actually built*, and the change is load-bearing for every gate below.
>
> **(a) Graduation/autonomy is no longer the static 15/90/14 ramp.** Locked
> decision #1's "15 samples / 90% / 14 clean days" was the screenpipe
> `autonomy_lib` ramp; it is **superseded by F's measured per-(lane × action_type)
> fidelity gated through A's authority matrix.** There is now exactly **one bar**,
> and it lives in `framework/policies/authority-matrix.yml → bars` (the matrix is
> the single source of truth; F2's `graduation.py` *imports* it, never hardcodes
> its own — `[FIX-1 reconcile]`):
>
> | decision-type | match_rate | samples | max divergent / last 10 | recency-clean days | cooldown (demote) |
> |---|---|---|---|---|---|
> | **default** | ≥ 0.85 | ≥ 20 | ≤ 1 | ≥ 14 | 14d |
> | **internal_comms** | ≥ 0.90 | ≥ 30 | 0 | ≥ 21 | 21d |
> | **deploy_nonprod** | ≥ 0.95 | ≥ 30 | 0 | ≥ 21 | 21d |
>
> The default row mirrors the old 15/90/14 ramp *at the floor* (samples ≥ 20,
> match ≥ 0.85, recency-clean ≥ 14d) but is **finer**: per-(lane × action_type),
> with irreversible types tightened, plus a hard ceiling F can never lift
> (`external_comms`/`deploy_prod`/`spend`/`secrets`/`network_write`/
> `credentials_grant` = `always-gated` regardless of confidence). Fitness =
> `outcome_held × review_confirmed` (positive signal), **not** correction-count
> (gameable — F design correction #3). A cell with no/low ground truth is a
> visible **`unmeasured`** state that **cannot graduate** — never a silent pass.
> So whenever the snapshot or R-gates below say "earn per lane / 15·90·14",
> read it as "earn per (lane × action_type) against the authority-matrix bar,
> measured by F, gated by A."
>
> **(b) Current built state (don't re-plan what shipped).**
> - **F0** — consequence ledger built: `framework/fidelity/consequence.py`
>   (`emit_consequence`/`validate_consequence`/`read_ledger`/`compute_ratios`,
>   `GraduationRatios`); append-only `consequence-events-YYYY-MM-DD.jsonl`.
> - **F1** — officer-under-test runner + scorer built (`officer_runner.py`,
>   `scorer.py`); F1 deliberately measured **surface-only with a context-starved
>   officer**, so its low baseline is *not* the real number.
> - **F4** — **intent-fidelity + leak isolation built**: `officer_runner.py`'s
>   `gather_cutoff_context` (the gather arm serves *intent, not literal surface*;
>   `gather=None` reproduces F1 byte-for-byte) fenced by `leakguard.py`
>   (`assert_thread_pre_cutoff` + `scan_for_leaks` + `filter_mcp_result`; a breach
>   **hard-fails** the case). Scoring weights the DECISION/intent channel far
>   above voice (voice is a *separate authenticity axis*, never collapsed).
> - **`content_ts` consumed** by the cutoff fence (equal-ts counts as a leak,
>   mirroring retrodiction's `test_cutoff_no_post_reply_leakage`).
> - **Shared `action_type` taxonomy** is the join key across F and A:
>   `framework/authority/classifier.py` (`classify_action`/`ACTION_TYPES`) +
>   `lane.py` (`resolve_lane`) — ONE classifier stamps the consequence event
>   *and* drives the gate, so the ledger and the verdict table agree.
> - **A0 fail-safe gate shadow-only**: `framework/policies/authority-matrix.yml`
>   floor + `framework/authority/matrix.py` loader/validator (fail-closed) built;
>   `policy-shadow.py` re-wired to emit the typed authority verdict
>   (`policy_version: authority-shadow-v1`) **without ever blocking**. Confidence
>   is stubbed to `unmeasured` → everything proposes. The judge modules +
>   matrix-data floor are germline-registered (read-only to officers) and
>   CI-asserted.
>
> **(c) The real critical path (not engineering velocity).** The bottleneck to
> a *trustworthy* gate is **measurement coverage + a clean eval login**, not more
> code:
> - **Clean-HOME eval login** — `officer_runner` drives the production officer via
>   the OAuth `claude -p` path; the offline batch evaluator needs a clean-HOME /
>   `CLAUDE_CODE_OAUTH_TOKEN` login so eval runs bill to the Max pool without
>   colliding with interactive/officer sessions.
> - **pi-agent gather-query + content coverage** — F4's intent scoring is only as
>   good as the context the officer can gather as-of cutoff (the Husqvarna/
>   Mosevråvej worked example): the brain-bridge gather path + screenpipe capture
>   must actually surface the conversation's real goal *and* the real-world facts.
>   Thin capture = thin intent = an unfairly low or unmeasurable cell.
> - **The enforce-flip stays Captain-gated.** A's `CABINET_AUTHORITY_ENFORCING`
>   default is `0` (shadow); the flip is itself **propose-only** — the engine
>   cannot enable its own enforcement, and even enforcing-on means *enforcing the
>   fail-safe* (all propose-only) until F graduates a cell. Auto is double-gated
>   behind BOTH the flip AND F graduation.
>
> **(d) R1–R5's good bones are intact** — activate hq (R2), shadow pipes for
> *per-pipe* parity retirement (never big-bang; R3), comms migration via
> `queue_draft` as the only outbound path (R4), lane-CEOs take stream + missions
> (R5). What changed is the *gate definition*: every "shadow parity → cutover"
> and "graduate per lane" gate below now resolves against F's measured cells +
> A's matrix bar, recorded in the consequence ledger — see the per-R notes
> inline ("**[2026-06-19]**").

---

## Model routing change (first commit — upstream so the Mini soak inherits it)

Pattern: every officer-session default `claude-opus-4-7` → `claude-fable-5[1m]` (fall back to `claude-fable-5` if the CLI rejects the suffix at boot — verify on first officer start). Crew/subagents stay/become `claude-sonnet-4-6`. Advisor = Fable 5.

| File | Change |
|---|---|
| `presets/*/agents/*.md` (cos, cto, cpo, cro, coo + step-network/personal scaffolds) | frontmatter `model: claude-fable-5`; keep `effort: max`. `.claude/agents/*.md` are derived — regenerate via `load-preset.sh`, don't hand-edit |
| `cabinet/scripts/start-officer-mac.sh:24` + `start-officer.sh` (Docker parity) | `MODEL="${CABINET_MODEL:-claude-fable-5[1m]}"` |
| `cabinet/scripts/bootstrap-roles.sh` | seeded role model fields → fable-5 |
| `cabinet/scripts/hooks/stop-hook.sh:47-55` | add `*fable*` price case to the cost table (look up current Fable 5 pricing via the claude-api skill at implementation — do NOT guess); keep `*opus*` case for history |
| `cabinet/scripts/advisor-crew.sh` | `ADVISOR_MODEL` default → `claude-fable-5`; note: it uses `ANTHROPIC_API_KEY` (API-billed) — keep for targeted escalations only |
| `CLAUDE.md` (model-routing sections, incl. line ~484) + `README.md` | "Fable 5 drives the officer loop; Sonnet 4.6 for crew; `Task(model=\"fable\")` / advisor-crew for escalations" — docs-track-code rule |
| Redis `opus-escalation` counters / hook references | retarget semantics to fable, keep key names (avoid breaking cost dashboard) |

---

## Phases (each = one Workflow run; gate before next; Corridor `analyzePlan` at each kickoff)

### P0 — Hygiene & stabilization (½ day) — DONE
- Model-routing commit above (benefits Mini immediately).
- Remove the 2 zombie LaunchAgents (`com.cabinet.cost-summary`, `com.cabinet.heartbeat-watchdog` — point at dead `convergence` worktree, failing sends since May 26): `launchctl bootout` + delete plists. Reinstalled later by R2 from v2 templates.
- Event-ledger durability: set `CABINET_EVENT_LOG_DIR` to a durable path (e.g. `$HOME/Library/Application Support/cabinet/events`) in all `cabinet/launchd/*.plist` templates + shell defaults (`framework/events/emitter.py:156` default is volatile `/tmp/cabinet-events`). Upstream commit → Mini inherits.
- screenpipe live defects: provision `SCREENPIPE_API_AUTH_KEY` into launchd pipe env (fixes hourly meeting-intel `unauthorized`; key exists in pi-agent env — mirror into `_shared/.env`, consumed via `sp_lib.load_env`); voice-profile plist `StartInterval 604800` → `StartCalendarInterval` (weekly intervals never fire across reboots); decide self-knowledge (re-enable plist or move to `state/retired-pipes/`).
- Make webhook URLs out of code defaults (`email_lib.py:58,68`, `teams_graph_lib.py:26,32`) → env-only (`_shared/.env`), then rotate the Make webhook URLs.
- `git -C ~/captains-cabinet merge --ff-only claude/convergence-v2` on master.
- **Gate:** pipe-health green incl. a new outcome-check for meeting-intel; Mini pulls and still boots.

### P1 — Brain MCP bridge (1–2 days, keystone) — DONE
New `~/.screenpipe/pipes/brain-mcp/server.py` — FastMCP **stdio** server (HTTP warm instance later), reusing existing libs (no new logic where a lib exists):
- `search_brain(query, top_k, filter)` → shells `embeddings/search.py --json`
- `gather_context(handle, budget)` → `_shared/context_lib.gather`
- `read_note(path)` → vault-rooted, path-traversal-guarded, denies `0-Self/` raw reads
- `person_intel(slug)`, `open_commitments(direction)` → `draft_lib` / `commitments_lib`
- `voice_profile()`, `nate_model(layer)` → `me_signal.nate_model` with **privacy fence**: content may shape drafts; never quoted into outbound text or web queries (enforced in tool docstring + R4 hook check)
- `ask_nate(text, kind, payload)` → `sp_lib.tg_prompt` (the universal human gate)
- `queue_draft(person, channel, draft, why)` → `tg_prompt(kind="draft-reply", payload=…)` — inherits approve→`_deliver`→outbox audit for free; **officers get no direct send tools**
- `log_reasoning(...)` → `_shared/agent_reasoning.log`; `record_run(...)` → `fleet_lib`
- Writes: append-only agent-inbox (`0-Inbox/agent-inbox.md`) + convention-enforcing helpers only (OWASP memory-poisoning mitigation)
- Register: `instance/config/extra-mcps.json` + `cabinet/mcp-scope.yml` (officer allowlist) + `.claude/rules/brain-bridge.md` (conventions, single-egress rule). pytest suite: traversal attempts, privacy-fence leaks, payload schemas.
- **Gate:** an officer answers "what do I owe Lisa and how would I tell her" purely via MCP; test draft lands in Telegram.

> **ROADMAP REWRITE (2026-06-10).** The original P2–P6 assumed the functional
> five-officer roster on hq. The Captain-decided portfolio redesign (one
> Chair + per-lane CEOs, `presets/portfolio/`) supersedes them; the
> remaining work is re-cut as R1–R5 below. P0/P1 stand as completed.
> Substance carried forward: the P3 intake loop is now R3 Chair work; the
> P4 hard ceiling + quarantine land in R4; P5 pool mode is deferred to the
> end of R5 — multi-session pool work only on evidence.

### R1 — Build: the portfolio org refactor (this change-set; DONE when committed)
- `presets/portfolio/` — Chair charter (`agents/cos.md`, id-reuse) + lane-CEO
  archetype template (`agents/_lane-ceo.md.template`).
- `cabinet-init` — onboarding interview skill
  (`.claude/skills/cabinet-init/`) + deterministic generator
  (`cabinet/scripts/generate-instance.py`) with pytest suite.
- Germline set in pre-tool-use (read-only operating rules incl.
  `.claude/rules/courses-of-action.md`) + regression harness.
- Role remap: outcomes draft owners/verifiers → cos/lane-CEO roster;
  `officer-capabilities.conf` + `mcp-scope.yml` lane-CEO rows;
  `bootstrap-roles.sh --roster`.
- Consequence-ledger schema (`framework/schemas/consequence-event.schema.json`
  + `docs/consequence-ledger.md`) — one normalized action+consequence shape
  for pipes, officers, and crew.

> **[2026-06-19]** This consequence schema is the seam F built on: **F0** shipped
> the emitter/reader (`framework/fidelity/consequence.py`) over it, and the
> `[FIX-1]` re-key added a first-class `action_type` enum field (stamped by the
> shared `framework/authority/classifier.py` `classify_action`) so the ledger
> keys cells on `(actor, lane, action_type)` — the exact tuple A's gate reads.
> The schema is no longer an R1 deliverable to design; it is built and consumed.

### R2 — Activate the hq instance (Chair only)

This runbook and the ACTIVATION STEPS header of
`instance/config/hq-instance.yml.draft` are the SAME runbook — keep them in
agreement. Contexts/projects/lane-CEO role defs/roster are already
generated; what remains is, in order:

1. **`cabinet/.env`** (chmod 600, gitignored) gets all four of:
   `TELEGRAM_COS_TOKEN` (the ONE Chair bot from BotFather — canonical name
   `TELEGRAM_<OFFICER_UPPER>_TOKEN`; legacy `TELEGRAM_BOT_TOKEN_COS` still
   resolves), `TELEGRAM_HQ_CHAT_ID`, `CABINET_MODE=multi`,
   `CABINET_ID=hq-macbook`. The deployment gate REQUIRES
   `CABINET_ID=hq-macbook` — `outcomes.yml` missions only compile when
   CABINET_ID matches their deployment key; any other value compiles ZERO
   missions.
2. **Preset:** `instance/config/active-preset` already says `portfolio`
   (deployment-local file, gitignored — nothing to do).
3. **Lane-CEO role defs** already rendered (local, gitignored):
   `instance/agents/polads-ceo.md` + `instance/agents/stephie-ceo.md`.
4. **Bootstrap:** `bash cabinet/scripts/bootstrap-roles.sh --roster
   instance/config/roster.yml --prune` — seeds/updates EXACTLY cos (Chair)
   + polads-ceo + stephie-ceo; `--prune` retires any leftover
   cto/cpo/cro/coo rows (yml archived, org_roles → retired).
5. **TCC:** `bash cabinet/scripts/grant-mac-permissions.sh` (interactive —
   with the bot token, the only Captain-blocking steps).
6. **Deploy:** `deploy-mac.sh --officer cos`, then
   `--daemon mission-supervisor`, `--daemon outbox-relay`, optionally
   heartbeat-watchdog + cost-summary (cron scripts now source
   `cabinet/.env` themselves). SKIP task-sync (no-op for plugin-routed
   lanes — pointless) and SKIP worktree-listener unless
   `NEON_CONNECTION_STRING` is set (30s crash-loop otherwise). Skip kiosk;
   point the screenpipe MCP entry at the existing instance, no brew
   re-install.
7. **Lane CEOs start on demand** (consultants, Telegram-dark):
   `start-officer-mac.sh polads-ceo` when their trigger stream fills
   (mission-supervisor stderr/ledger shows the routing).
8. **Verify with ground truth:** `tmux attach -t officer-cos` +
   `redis-cli XLEN cabinet:triggers:<officer>` — NOT verify-launchagents.sh
   as the gate (it only knows to skip consultants once bootstrap has
   stamped officer_type; tmux + XLEN is authoritative).

- **Gate:** Chair session live on its bot; lane CEOs spawnable; no pipe
  retired, nothing else changed.

### R3 — Chair takes intake + briefings (shadow first)
- Chair runs the intake routine (sweep → classify to lane →
  gather-then-decide → propose-only via the brain gate; machinery, never an
  outcome) and the 07:00/19:00 briefings.
- **Shadows the morning-brief / ask-my-brain pipe family for 1–2 weeks** —
  pipes keep sending; Chair's versions run in parallel for comparison.
- **Consequence ledger adopted**: officers + surviving pipes emit
  `consequence-event` records; graduation math reads only this ledger
  (`docs/consequence-ledger.md`).
- The perception side's architect retires each shadowed pipe **on parity
  evidence, per pipe — never big-bang** (`docs/work-model.md` Pipe
  disposition).
- **Gate:** briefing/digest quality at parity for 1–2 weeks; first pipes
  retired; ledger populated from both estates.

> **[2026-06-19]** "Parity" and "graduation math" here now resolve against the
> built ledger: surviving pipes + officers emit `consequence-event` records via
> F0's `emit_consequence`, and the per-pipe retirement gate reads
> `compute_ratios((actor, lane, action_type))` — not an ad-hoc tally. The
> "graduation math reads only this ledger" promise is realized by F2's
> `graduation.evaluate`, which applies the single `authority-matrix.yml → bars`
> bar (above). Until F2 lands, every cell reads `unmeasured` → propose-only, so
> R3 can run intake/briefing in shadow without any cell auto-graduating.

### R4 — Comms migration (draft-reply → officers)
- Reply drafting moves to officers under the **courses-of-action** rule
  (investigation bar, one card per situation, urgency tiers) with **shadow
  parity** against the existing draft pipe before cutover; the
  Drafting-Lessons corpus is shared so officer drafts inherit every
  recorded correction.
- Hard ceiling enforced in cabinet hooks AND autonomy config:
  external_comms/secrets/spend/prod-deploy = always-propose; officers'
  only outbound path = the brain bridge's `queue_draft`.
- Inbound quarantine (trust-scoring + injection sanitization before any
  LLM sees mail content) + typed policy engine promoted shadow → enforcing
  (both already drafted as system-self outcomes).
- The telegram bot **thins to approval-gate-only** infrastructure — the
  KEEP-CAPTURE disposition: it carries proposals and decisions, composes
  nothing.
- **Gate:** officer drafts at shadow parity; draft pipe retired; gate
  traffic flowing through the thinned bot.

> **[2026-06-19]** This R4 paragraph predates A's design and is *realized* by it,
> not replaced. The "hard ceiling enforced in cabinet hooks AND autonomy config"
> is now A's authority matrix: `external_comms` is `always-gated` with
> `queue_draft` as the *only* outbound path; `internal_comms` graduates only to
> `auto-with-veto-window` (block-then-redirect into a 7-min deferred-send queue,
> never fire-and-forget). "Officer drafts at shadow parity" is measured by **F's
> reply cell** (intent-fidelity, F4), and "promoted shadow → enforcing" is A's
> Cycle-2 flip behind `CABINET_AUTHORITY_ENFORCING` — **Captain-gated, propose-
> only, instant-revert** (independent of the Cycle-1 legacy-engine flip,
> `outcome-system-self-001`). Inbound quarantine + the typed policy engine are
> A's enforcement seam, shipped shadow-only at A0.

### R5 — Lane-CEOs take stream + missions; the estate settles
- Lane CEOs work their lanes end-to-end: stream (claim → execute →
  close-back, propose-first until graduation) + Captain-ratified missions
  from `outcomes.yml`.
- The perception estate settles at its end-state: **capture + reflexes
  only** (sync/index/identity/health + deterministic bookkeeping); all
  judgment/human-facing composition lives in the cabinet.
- Graduation per lane from consequence-ledger evidence; the hard ceiling
  never lifts.
- **Multi-session pool work only on evidence**: port `--project` pool mode
  into `start-officer-mac.sh` (per-(officer,lane) sessions, per-lane env,
  no global active-project) only when single-Chair + on-demand CEOs
  measurably contend — not before.
- **Gate:** two lanes' missions complete concurrently without context
  bleed; weekly output share produced by the system with zero quality
  flags trends up.

> **[2026-06-19]** "Graduation per lane from consequence-ledger evidence; the
> hard ceiling never lifts" is now precise: per **(lane × action_type)** cell,
> F2's `graduation.evaluate` against the `authority-matrix.yml → bars` bar
> (default 0.85/20/1/14, tighter for irreversible types), gated by A; the six
> hard-ceiling classes stay `always-gated` forever. A demoting **thermostat**
> (A's Component 4, hard-gated after F2/F6) flips any cell back to propose-only
> on a bad call / drift spike / divergent cluster / colleague-friction / false-
> positive block, sticky for the cooldown window. "Weekly output share with zero
> quality flags trends up" is the `outcome_held × review_confirmed` fitness
> signal, read from the same ledger.

---

## Execution model

- Each phase = one **Workflow** run authored at kickoff (P1 script drafted in the analysis message); workers `claude-sonnet-4-6`, verification lenses (security / correctness / conventions) before merge; repo edits via worktree-isolated agents; `~/.screenpipe` edits direct (not a git repo — Workflow makes a timestamped backup of touched files first).
- Corridor `analyzePlan` before each phase's code generation (house rule).
- Commits on `claude/convergence-v2`; docs updated in the same commit (docs-track-code rule).
- Write the full strategic plan (this file + the analysis) to `docs/clone-convergence-plan-2026-06-09.md` in convergence-v2 as the first P0 commit.

## Verification

- **P0:** `pipe-health` reports all green + meeting-intel outcome-check passes; `launchctl list | grep cabinet` shows only intended agents; Mini re-runs `setup-mac.sh --check` clean after pulling.
- **P1:** pytest suite green; live MCP smoke from a Claude Code session (search_brain / voice_profile / queue_draft TEST draft → Telegram).
- **R1:** generator pytest suite green (`cabinet/scripts/tests/`); consequence schema meta-validates (2020-12); outcomes draft still schema-valid.
- **R2:** `test-recovery.sh` passes; Chair live on its bot; `bootstrap-roles.sh --roster` seeded exactly the declared roster; cost-summary shows Fable-5 pricing rows.
- **R3/R4:** shadow-parity comparisons recorded per pipe before retirement; consequence-ledger events visible from BOTH estates (officers + surviving pipes); gate traffic through the thinned bot.
- Each phase ends with `run-golden-evals.sh` + the cabinet CI suite locally.

> **[2026-06-19] F/A verification bar (supersedes the implicit static ramp for autonomy).**
> Any R-gate that grants autonomy now verifies against the *measured* gate, not a
> hand-counted streak: (1) F's batch evaluator produces a per-(lane × action_type)
> fidelity cell that **clears the `authority-matrix.yml → bars` bar** (default
> 0.85/20/1/14; irreversible types tighter); (2) A's authority-verdict parity
> corpus shows the shadow verdict matches the intended matrix with ~0 wrongful
> safe-action blocks; (3) the consequence ledger carries `action_type`-keyed
> events from both estates; (4) the prod-never-auto + full-six hard-ceiling
> coverage CI tests are green; (5) the enforce-flip is a Captain-approved
> course-of-action card, not an autonomous toggle. "Unmeasured cell cannot
> graduate" and "external_comms/spend/secrets/network_write/credentials_grant/
> deploy_prod never auto" are golden evals (`memory/golden-evals/eval-011..015`).

## Risks (mitigations in-plan)

1. Quota contention (two fleets + interactive on one Max x20) → roster choice, Sonnet workers, Mini-overnight choreography, idle-stop, watch weekly caps first fortnight.
2. Safety inversion on primary laptop (skip-permissions + live creds) → policy-engine promotion (R4), hard ceiling, scoped PATs, single egress.
3. Inbound prompt injection → R4 quarantine before LLM, runtime-enforced tiers.
4. Vault/Library split-brain → vault = Nate-truth, Library = product-truth; bridge read-first; gated writes only.
5. `[1m]` suffix or Fable-5 availability quirks in officer boot → fallback to `claude-fable-5`, verified at first start.
