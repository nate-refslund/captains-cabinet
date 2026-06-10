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

## Risks (mitigations in-plan)

1. Quota contention (two fleets + interactive on one Max x20) → roster choice, Sonnet workers, Mini-overnight choreography, idle-stop, watch weekly caps first fortnight.
2. Safety inversion on primary laptop (skip-permissions + live creds) → policy-engine promotion (R4), hard ceiling, scoped PATs, single egress.
3. Inbound prompt injection → R4 quarantine before LLM, runtime-enforced tiers.
4. Vault/Library split-brain → vault = Nate-truth, Library = product-truth; bridge read-first; gated writes only.
5. `[1m]` suffix or Fable-5 availability quirks in officer boot → fallback to `claude-fable-5`, verified at first start.
