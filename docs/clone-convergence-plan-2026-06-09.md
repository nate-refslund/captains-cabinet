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

### P0 — Hygiene & stabilization (½ day)
- Model-routing commit above (benefits Mini immediately).
- Remove the 2 zombie LaunchAgents (`com.cabinet.cost-summary`, `com.cabinet.heartbeat-watchdog` — point at dead `convergence` worktree, failing sends since May 26): `launchctl bootout` + delete plists. Reinstalled later by P2 from v2 templates.
- Event-ledger durability: set `CABINET_EVENT_LOG_DIR` to a durable path (e.g. `$HOME/Library/Application Support/cabinet/events`) in all `cabinet/launchd/*.plist` templates + shell defaults (`framework/events/emitter.py:156` default is volatile `/tmp/cabinet-events`). Upstream commit → Mini inherits.
- screenpipe live defects: provision `SCREENPIPE_API_AUTH_KEY` into launchd pipe env (fixes hourly meeting-intel `unauthorized`; key exists in pi-agent env — mirror into `_shared/.env`, consumed via `sp_lib.load_env`); voice-profile plist `StartInterval 604800` → `StartCalendarInterval` (weekly intervals never fire across reboots); decide self-knowledge (re-enable plist or move to `state/retired-pipes/`).
- Make webhook URLs out of code defaults (`email_lib.py:58,68`, `teams_graph_lib.py:26,32`) → env-only (`_shared/.env`), then rotate the Make webhook URLs.
- `git -C ~/captains-cabinet merge --ff-only claude/convergence-v2` on master.
- **Gate:** pipe-health green incl. a new outcome-check for meeting-intel; Mini pulls and still boots.

### P1 — Brain MCP bridge (1–2 days, keystone)
New `~/.screenpipe/pipes/brain-mcp/server.py` — FastMCP **stdio** server (HTTP warm instance later), reusing existing libs (no new logic where a lib exists):
- `search_brain(query, top_k, filter)` → shells `embeddings/search.py --json`
- `gather_context(handle, budget)` → `_shared/context_lib.gather`
- `read_note(path)` → vault-rooted, path-traversal-guarded, denies `0-Self/` raw reads
- `person_intel(slug)`, `open_commitments(direction)` → `draft_lib` / `commitments_lib`
- `voice_profile()`, `nate_model(layer)` → `me_signal.nate_model` with **privacy fence**: content may shape drafts; never quoted into outbound text or web queries (enforced in tool docstring + P4 hook check)
- `ask_nate(text, kind, payload)` → `sp_lib.tg_prompt` (the universal human gate)
- `queue_draft(person, channel, draft, why)` → `tg_prompt(kind="draft-reply", payload=…)` — inherits approve→`_deliver`→outbox audit for free; **officers get no direct send tools**
- `log_reasoning(...)` → `_shared/agent_reasoning.log`; `record_run(...)` → `fleet_lib`
- Writes: append-only agent-inbox (`0-Inbox/agent-inbox.md`) + convention-enforcing helpers only (OWASP memory-poisoning mitigation)
- Register: `instance/config/extra-mcps.json` + `cabinet/mcp-scope.yml` (officer allowlist) + `.claude/rules/brain-bridge.md` (conventions, single-egress rule). pytest suite: traversal attempts, privacy-fence leaks, payload schemas.
- **Gate:** an officer answers "what do I owe Lisa and how would I tell her" purely via MCP; test draft lands in Telegram.

### P2 — MacBook "hq" cabinet instance (1–2 days)
- Instance config: distinct `cabinet_id`, new officer bot tokens, `instance/config/contexts/{polads,stephie,stepnetwork,system-self,adhoc}.yml`, `instance/config/projects/*.yml`.
- Author `instance/config/outcomes.yml` (schema ready at `framework/schemas/outcome.schema.json`): rolling window of 1–2 active bounded outcomes per lane per `docs/work-model.md` (stream/missions/intake — standing intake is a CoS routine, not an outcome); `bootstrap-roles.sh`.
- Roster profile: CoS LaunchAgent KeepAlive (persistent, Fable 5); CTO/CPO/CRO/COO **on-demand** (no KeepAlive plists; spawned by CoS / mission-supervisor trigger, idle-stop 30 min — mechanism exists in post-tool-use idle detection).
- `deploy-mac.sh` selective: skip kiosk; include chrome-profile (Monday/Vercel logins); **skip setup-mac Step 9 screenpipe brew-install** — point the `screenpipe` MCP entry at the existing instance (`localhost:3030` + auth key).
- dev-tasks plugin via `instance/config/extensions.yml` (the sanctioned Monday route — no Monday adapter by design); leave task-sync disabled or `github-issues` only.
- TCC grants (`grant-mac-permissions.sh`); `test-recovery.sh`; one workday soak.
- **Gate:** one real mission per lane completes with `work_item_completed/verified` events; quota burn over the soak day measured and acceptable.

### P3 — Work-intake loop (1–2 days)
- Monday "Nate's Todos" (board 5098236573) + Tasks board → CoS **intake routine** (scheduled cron sweep — machinery, not an outcome; see `docs/work-model.md` Intake): classify to lane, gather-then-decide, propose via `ask_nate`, never auto-claim.
- Completions write back: Monday status via dev-tasks plugin + `log_reasoning` + `record_run` — so reasoning-review/architect govern officers like pipes.
- Cabinet status → morning-brief fuel file (`0-Inbox/brief-fuel-cabinet.md`); ask-my-brain cites officer work.
- New vault pillars the clone needs (flagged missing in vault analysis): `7-Resources/Runbooks/`, `4-Projects/projects-status.md`, and the **live autonomy manifest** (`0-Self/autonomy-manifest.md`) — single table of lane → ceiling → graduation state, consumed by both screenpipe lanes and cabinet `autonomy.yml`.
- **Gate:** a todo Nate never touched is proposed → approved → executed → closed in Monday → appears in next morning brief.

### P4 — Comms-as-Nate (2–3 days)
- Hard ceiling enforced in cabinet hooks AND autonomy.yml: external_comms/secrets/spend/prod-deploy = always-propose. Officers' only outbound path = `queue_draft`.
- Inbound quarantine: trust-scoring + injection-sanitization pass in `draft_lib`/inbox-triage **before** any LLM sees mail content (EchoLeak-class defense).
- Promote the typed policy engine (`cabinet/scripts/lib/policy_engine.py`, 1,042 lines) from shadow to enforcing (CI parity eval exists).
- Shadow-mode (`autonomy_lib.record_shadow`) for every comms lane; graduation per existing bar.
- **Gate:** first lane (internal Teams replies) reaches the bar; Nate flips it to auto with one Telegram tap.

### P5 — Mac-native pool mode (1–2 weeks; the only structural piece)
- Port `--project` pool mode from `start-officer.sh` (Docker) into `start-officer-mac.sh`: per-(officer,project) tmux windows, per-project env, `CABINET_ACTIVE_PROJECT` cost fields; kill global `active-project.txt` for the hq instance; implement the CoS project-router the step-network preset specifies; fix `switch-project.sh` `/opt` default.
- Optional: vault git-sync read-mirror for the Mini (deferred — Mini stays brain-less per topology decision).
- **Gate:** PolAds + STEPhie missions run simultaneously under one roster without context bleed.

### P6 — Ramp (ongoing)
Weekly OVI + role evals + reasoning-review over officers; lanes graduate one at a time; metric = % of weekly output (commits, replies, Monday closures) produced by the system with zero quality flags / voice corrections.

---

## Execution model

- Each phase = one **Workflow** run authored at kickoff (P1 script drafted in the analysis message); workers `claude-sonnet-4-6`, verification lenses (security / correctness / conventions) before merge; repo edits via worktree-isolated agents; `~/.screenpipe` edits direct (not a git repo — Workflow makes a timestamped backup of touched files first).
- Corridor `analyzePlan` before each phase's code generation (house rule).
- Commits on `claude/convergence-v2`; docs updated in the same commit (docs-track-code rule).
- Write the full strategic plan (this file + the analysis) to `docs/clone-convergence-plan-2026-06-09.md` in convergence-v2 as the first P0 commit.

## Verification

- **P0:** `pipe-health` reports all green + meeting-intel outcome-check passes; `launchctl list | grep cabinet` shows only intended agents; Mini re-runs `setup-mac.sh --check` clean after pulling.
- **P1:** pytest suite green; live MCP smoke from a Claude Code session (search_brain / voice_profile / queue_draft TEST draft → Telegram).
- **P2:** `test-recovery.sh` passes; one mission per lane end-to-end; cost-summary shows Fable-5 pricing rows.
- **P3/P4:** scripted end-to-end scenarios above; shadow-ledger entries visible in `autonomy_outcomes.jsonl`.
- Each phase ends with `run-golden-evals.sh` + the cabinet CI suite locally.

## Risks (mitigations in-plan)

1. Quota contention (two fleets + interactive on one Max x20) → roster choice, Sonnet workers, Mini-overnight choreography, idle-stop, watch weekly caps first fortnight.
2. Safety inversion on primary laptop (skip-permissions + live creds) → policy-engine promotion (P4), hard ceiling, scoped PATs, single egress.
3. Inbound prompt injection → P4 quarantine before LLM, runtime-enforced tiers.
4. Vault/Library split-brain → vault = Nate-truth, Library = product-truth; bridge read-first; gated writes only.
5. `[1m]` suffix or Fable-5 availability quirks in officer boot → fallback to `claude-fable-5`, verified at first start.
