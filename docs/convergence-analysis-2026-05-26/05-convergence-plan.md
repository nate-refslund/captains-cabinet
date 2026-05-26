# Captain's Cabinet Convergence Plan

**Date:** 2026-05-26
**Authoring session:** Opus 4.7 (1M ctx)
**Branches compared:** `claude/funny-fermi-8daf32` (≈ master) vs. `origin/claude/clever-tesla-CS3Su-rebuild`
**Status:** Draft for Captain ratification → triggers implementation `/goal`

---

## 0. Executive Recommendation

**Use `claude/clever-tesla-CS3Su-rebuild` as the structural foundation. Selectively backport 5 high-value capabilities from `master`. Add 9 net-new completions. Sequence into 10 dependency-ordered phases on a new `claude/convergence` branch, executed continuously via `/loop` until the MacMini-readiness checklist is fully green.**

Composition: **~60% rebuild architecture + ~25% master backport + ~15% net-new.**

Operating constraints (Captain-locked 2026-05-26):
- Captain triplet: **restore + autoMemoryEnabled** (best of both)
- Branch base: **`claude/convergence` cut from `origin/claude/clever-tesla-CS3Su-rebuild`**
- CC risk appetite: **go all-in on experimental flags**, but **OAuth-only Max x20** → all officers run as `claude` CLI processes; Managed Agents (API-key feature) is **out**; Agent Teams flag is **in**
- Cadence: **continuous `/loop`** through all phases

---

## 1. Why This Approach

Three converging arguments:

1. **The rebuild already nails the durable-role-system spine.** `framework/events/`, `framework/roles/lifecycle.py`, `framework/missions/compiler.py`, `framework/ovi/compute.py`, `framework/measurement/`, `framework/policies/` are exactly the event-sourced, entity-modeled architecture the goal requires. The rebuild's CLAUDE.md is 140 lines (vs master's 850+) precisely because the architecture carries more weight than documentation. Recreating this on master would be weeks; backporting master's assets onto rebuild is days.

2. **Master has battle-hardened operational assets the rebuild dropped.** The `pre-tool-use.sh` v3.7.2 word-boundary engine (developed across FW-029 through FW-051), the ElevenLabs voice + Gemini image stack, the Library pgvector knowledge system with wiki-links and graph view, the Captain triplet (4th + 5th loops), and the 300+ test corpus are years of engineering investment. Cherry-picking them onto the rebuild preserves that work cleanly.

3. **Critical gaps exist in both branches.** Neither closes the mission-completion loop, wires OVI to the event ledger, models per-role eval history, supports task-system adapters (Monday/Jira/Asana/Linear), or implements hat graduation. These must be built net-new on whatever foundation we choose. The rebuild's spine makes them smaller, isolated additions; master's spine would make them sprawling, intrusive changes.

---

## 2. The Synthesis Matrix

| Component | Source | Why |
|---|---|---|
| `framework/events/` (emitter, schema, replay) | **rebuild** | Event-sourcing foundation — the entire durable role system depends on it |
| `framework/roles/lifecycle.py` (charter, hats, lineage) | **rebuild** | Role-as-entity model — closest to the goal |
| `framework/missions/compiler.py` + `session_bridge.py` | **rebuild** | Goal-to-work-graph compilation |
| `framework/ovi/compute.py` + `components.yml` | **rebuild** | Outcome Value Index |
| `framework/measurement/scenarios/` | **rebuild** | Closed-loop capability evals |
| `framework/policies/` + `cabinet/scripts/lib/policy_engine.py` | **rebuild** | Typed safety, replaces 700+ lines of bash regex |
| `cabinet/scripts/lib/work_graph.py` | **rebuild** | DAG executor primitives (cycle detection, ready_tasks, topo sort) |
| `.claude/rules/*.md` | **rebuild** | Path-scoped native CC rules |
| `.claude/settings.json` (autoMemoryEnabled, hook map, AGENT_TEAMS=1) | **rebuild** | Native CC integration |
| New hooks: `session-task-inject.sh`, `session-stop.sh`, `on-notification.sh`, `post-subagent.sh` | **rebuild** | Closed-loop session lifecycle |
| `cabinet/scripts/setup-mac.sh` + `deploy-mac.sh` | **rebuild** | Mac deployment scripts |
| LaunchAgent: `com.cabinet.ovi-weekly.template.plist` | **rebuild** | Scheduled OVI computation |
| Officer lifecycle scripts (create/start/suspend/resume + start-officer-mac.sh) | both (identical) | Officer execution surface |
| Tier 2 memory dirs | both (identical) | Per-officer working notes |
| Telegram plugin wiring | both (identical) | Captain DM channel |
| **`shared/interfaces/captain-decisions.md`** | **master backport** | 4th-loop persistence; queryable, role-owned |
| **`shared/interfaces/captain-patterns.md`** | **master backport** | 4th-loop encoded behaviors |
| **`shared/interfaces/captain-intents.md`** | **master backport** | 5th-loop inferred WHY |
| **`pre-tool-use.sh` stateful Redis layers (kill switch, spending, Layer 1 gate)** | **master backport** | Wrap the new typed policy engine; the Python engine doesn't replace stateful Redis checks |
| **`post-reply-voice.sh` + ElevenLabs stack** | **master backport** | Per-officer voice personalities |
| **Gemini image gen + naturalize prompts** | **master backport** | Multi-modal Captain channel |
| **`cabinet/sql/library.sql` + Library MCP + dashboard `/library`** | **master backport** | Knowledge system (pgvector + wiki-links + graph) |
| **`memory/skills/*` 13 foundation skills** | **master backport** | Universal officer skills |
| **CI corpus** (shell + Python + Vitest + golden evals + regression harnesses) | **master backport** | Safety net for evolution |
| **`record-experience.sh` + experience records pipeline** | **master backport** | Per-task learning loop |
| `notify-officer.sh` + Redis Streams + `lib/triggers.sh` | both (identical) | Inter-officer comms |
| Cron triggers (briefing, retro, research-sweep, backlog-refine) | **master backport** | Scheduled work delivery |
| 🆕 **Mission completion hook** (officer marks work_graph_node done from session) | NEW | Closes the loop the rebuild left open |
| 🆕 **Mission execution supervisor** (cron polls ready tasks → routes to officers) | NEW | Drives mission autonomously |
| 🆕 **OVI data wiring** (event-ledger → component sources) | NEW | Makes OVI computable end-to-end |
| 🆕 **`role_evals` table + 50-eval suite** (10 × 5 officers) | NEW | Eval-driven role evolution |
| 🆕 **Transactional outbox** | NEW | Prevents Postgres/Notion/Linear dual-write failures |
| 🆕 **Hat graduation mechanism** (`role_hat_promoted` event handler) | NEW | Closed-loop role adaptation |
| 🆕 **Task-system adapter layer** (Monday + Jira + Linear + Asana + GitHub Issues) | NEW | Product-agnostic backlog |
| 🆕 **Product-detection bootstrap** (introspect repo → generate config + holistic exploration) | NEW | Onboard any product in one command |
| 🆕 **Code-signing/notarization runbook** (resolve master's existing stub) | NEW | MacMini 24/7 prerequisite |

---

## 3. Target Architecture: Durable Adaptive Role System

### 3.1 The Three Concentric Loops

**Inner loop (per session):** Officer wakes → session-task-inject reads charter + active hats + assigned mission step from `framework/missions/session_bridge.py` → executes ReAct loop → on session-stop hook, flushes outbox + writes mission step completion + experience record.

**Middle loop (per mission):** Captain declares outcome (Telegram DM or direct edit of `instance/config/outcomes.yml`) → mission compiler decomposes into work graph → execution supervisor cron routes ready tasks to officers via Redis Stream → validator officer verifies evidence → OVI components updated → next mission's ready tasks surface.

**Outer loop (per role lifecycle):** Weekly cron runs all 50 scenario evals → failure-pattern detector flags ≥3 same-type failures → role evolution proposal drafted → fresh-context Sonnet review → Captain ratifies → `role_evolved` governance event → role projection updated → re-eval on first 5 missions to verify the change.

### 3.2 Target Data Model

```sql
-- Captain layer
captain_outcomes         (id, text, priority, success_criteria_jsonb, ratified_at, closed_at)
captain_boundaries       (id, type, rule_jsonb, scope, active, created_at)
captain_decisions        (id, message_ref, decision, why, affected_jsonb, logged_at)
captain_patterns         (id, slug, rule, why, how_to_apply, evidence_jsonb, encoded_at, occurrence_count)
captain_intents          (id, inferred_goal, evidence_jsonb, confidence, observed_at, superseded_by)

-- Role layer (durable entities — from rebuild + role_evals extension)
roles                    (id, slug, display_name, charter_jsonb, authority_level, status, created_at, retired_at, superseded_by, archive_path)
role_hats                (id, role_id, hat_slug, description, context_trigger, capabilities_added_jsonb, active, expires_at, uses_count)
role_lineage_edges       (predecessor_id, successor_id, relationship, rationale, effective_at)
role_evals               (id, role_id, scenario_id, session_id, score, passed, findings_jsonb, evaluated_at)
role_memory_artifacts    (id, role_id, artifact_path, artifact_type, write_access_role_ids uuid[])

-- Mission layer (from rebuild + execution state extension)
missions                 (id, outcome_id, compiled_plan_jsonb, status, compiled_at, verified_at)
mission_steps            (id, mission_id, step_order, description, assigned_role_id, depends_on uuid[], status, started_at, completed_at, verified_at, evidence_jsonb)
officer_tasks            (id, role_id, session_id, mission_step_id, status, due_at, claimed_at, completed_at)  -- existing master schema; extended with mission_step_id FK

-- Event ledger (rebuild)
org_events               (id, event_type, actor, payload_jsonb, parent_id, timestamp)
governance_events        (id, event_type, role_id, payload_jsonb, parent_id, timestamp)

-- OVI (rebuild + wiring)
ovi_snapshots            (id, components_jsonb, composite_score, trend, computed_at)

-- Net-new: outbox for cross-system writes
outbox                   (id, destination, payload_jsonb, attempt_count, last_attempt_at, dispatched_at)

-- Net-new: task adapter sync state
task_sync                (canonical_task_id, external_system, external_id, last_synced_at, sync_state, sync_hash)
```

### 3.3 Officer-Session Contract (formalized)

**On `SessionStart` hook + `UserPromptSubmit` (first prompt sentinel):**
- Load role charter + active hats from `instance/roles/active/<slug>.yml` (rebuild's source of truth)
- Read `shared/interfaces/captain-patterns.md`, `captain-intents.md`, `captain-decisions.md` (master backport)
- Read Tier 2 working notes from `instance/memory/tier2/<slug>/`
- Drain pending triggers from Redis Stream via `lib/triggers.sh::trigger_read`
- Fetch next ready mission task via `framework/missions/session_bridge.py`
- `autoMemoryEnabled` loads semantic memory automatically
- Emit `session_started` event via `framework/events/emitter.py`

**On `Stop` hook:**
- Flush outbox (commit any pending cross-system writes)
- Update Tier 2 notes with new knowledge if significant
- Write experience record via `record-experience.sh` if work threshold met
- Mark current `officer_tasks.completed_at` if applicable
- Clear heartbeat (signals clean exit vs. crash to supervisor)
- Emit `session_ended` event

This contract is *the* primitive for 24/7 operation. The supervisor can safely restart any officer at any moment because the session-start/stop contract is idempotent.

---

## 4. Implementation Approach

### 4.1 Continuous `/loop` Mechanics

The Captain has chosen continuous `/loop` until MacMini-ready. Implementation pattern:

- **Outer loop:** A persistent `/loop` slash-command on the implementing session, with `ScheduleWakeup` checkpoints between phases so context can compact cleanly.
- **Phase resume signals:** Each phase writes a Redis key `cabinet:convergence:phase:<N>:status` = `in_progress` / `complete` / `blocked` and a per-phase log file at `docs/convergence-analysis-2026-05-26/phase-<N>-log.md`. Resuming sessions read these to know where to pick up.
- **Per-step Corridor analyzePlan:** Per the user's global CLAUDE.md, every code-generation step calls `mcp__corridor__analyzePlan` first. Implementation drafts each phase's plan, runs Corridor, addresses findings, then generates code.
- **Agent Teams + subagents:** Aggressive use of `Agent` tool with subagent_type=Plan/Explore/general-purpose for parallel work. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is already set in the rebuild's `.claude/settings.json`.
- **Cost discipline:** Per-officer Redis token counters with daily cap (existing). Implementation session has its own daily cap; on breach, halt + alert Captain.
- **Escalation:** Failures that can't be auto-resolved trigger Telegram DM to Captain. Implementation pauses until reply.
- **Each phase ends with:** a commit + golden eval pass + structured experience record + Redis status flip + phase log update.

### 4.2 Branch & Commit Strategy

```
git fetch origin claude/clever-tesla-CS3Su-rebuild
git checkout -b claude/convergence origin/claude/clever-tesla-CS3Su-rebuild
# Phase 0: foundation merge / master backports
# Phase 1-9: feature additions, each with its own commit(s)
# Final: PR to master (or direct merge with Captain approval)
```

Commits follow Conventional Commits style with phase tags:
- `feat(phase-0): backport captain triplet from master`
- `feat(phase-1): close mission completion loop`
- `feat(phase-2): role_evals table + 50-scenario suite`
- etc.

### 4.3 Validation at Each Phase

Each phase has three gates:
1. **Tests:** all existing tests + new tests pass (`bash cabinet/tests/run-all.sh && pytest framework/`)
2. **Capability eval:** a designated scenario eval passes (proves the new behavior works end-to-end)
3. **Captain artifact:** the deliverable is visible (file, table row, dashboard panel, golden eval green)

Gates failing → phase status remains `in_progress`, escalate to Captain if blocked >2 cycles.

---

## 5. Phased Plan

Each phase below specifies: Goal, Deliverables, Acceptance gates, Evidence, Dependencies, Risk. The plan assumes the **rebuild's existing code is the baseline** and master's files referenced are backports.

### Phase 0 — Foundation Merge

**Goal:** Cut `claude/convergence` from `origin/claude/clever-tesla-CS3Su-rebuild`, backport the high-value master assets, verify everything still compiles and tests pass.

**Deliverables:**
- New branch `claude/convergence`
- Backports from master onto rebuild:
  - `shared/interfaces/captain-decisions.md`, `captain-patterns.md`, `captain-intents.md` (the triplet)
  - Master's `pre-tool-use.sh` stateful Redis sections (kill switch, spending limits, Layer 1 gate) — wrap the rebuild's new policy_engine.py call so both layers run
  - `cabinet/scripts/hooks/post-reply-voice.sh` + ElevenLabs config
  - Gemini image-gen scripts + naturalize prompt logic
  - `cabinet/sql/library.sql` + Library MCP + dashboard `/library` route
  - `memory/skills/*` 13 foundation skills (overwrite rebuild's if newer)
  - `cabinet/scripts/record-experience.sh` + `publish-skill-update.sh`
  - Cron scripts: `briefing.sh`, `retro-trigger.sh`, `research-sweep.sh`, `backlog-refine.sh`
  - CI workflows: full `.github/workflows/cabinet-ci.yml`
- Updated `CLAUDE.md` (~250 lines): framework-first architecture + 5-loop discipline + Captain triplet references + ToolSearch + Agent Teams + Corridor MCP usage
- Updated `presets/work/agents/*.md`: agent frontmatter with `model: claude-opus-4-7`, `effort: max`, `allowedTools`, skill list

**Acceptance gates:**
- All existing CI passes: `bash cabinet/tests/run-all.sh && pytest framework/`
- Framework tests pass (events/roles/missions/ovi/measurement scenarios)
- Smoke test: `bash cabinet/scripts/setup-mac.sh --dry-run` succeeds
- Captain triplet files readable, parseable, indexable

**Evidence:** Phase log `docs/convergence-analysis-2026-05-26/phase-0-log.md` with diff stats, test results, commit SHAs.

**Dependencies:** None (entry point).

**Risk:** Backport conflicts (e.g., the rebuild's slimmed-down pre-tool-use.sh vs. master's 1510-line version). Mitigation: incremental cherry-pick with test runs between each.

---

### Phase 1 — Close the Mission Loops

**Goal:** Make the org runtime actually loop. An officer can mark a mission step done from within their session; OVI gets real data from the event ledger; the supervisor routes the next ready task.

**Deliverables:**
- `cabinet/scripts/work-graph-complete.sh <node_id> [--evidence FILE] [--status done|failed]` — callable from a session. Writes `work_item_completed` event + updates `mission_steps.completed_at` + writes to outbox.
- Hook glue: a small file-write hook detects when officers create/update an evidence artifact matching a mission step's contract path and auto-calls work-graph-complete with the right `node_id`.
- Mission execution supervisor cron `cabinet/cron/mission-supervisor.sh` (every 5 min): SQL-queries `mission_steps` for `status='ready' AND assigned_role_id IS NOT NULL AND no officer_task row`. For each, creates `officer_tasks` row + pushes Redis trigger to assigned officer.
- OVI data wiring: replace `source: computed` placeholders in `framework/ovi/components.yml` with concrete event-ledger queries (e.g., `verification_pass_rate` = `COUNT(mission_steps WHERE verified_at IS NOT NULL) / COUNT(mission_steps WHERE completed_at IS NOT NULL)` over the last 7 days). Update `compute.py` query functions.
- Transactional outbox table + relay process `cabinet/cron/outbox-relay.sh` (every 1 min). Idempotent dispatch with retry + backoff.
- Scenario eval `outcome_to_verified`: Captain outcome → mission compiled → officer completes a node → validator verifies → OVI components reflect the change.

**Acceptance gates:**
- Scenario eval `outcome_to_verified` passes end-to-end
- OVI compute returns non-stub values for all 5 components on real data (synthetic or otherwise)
- Outbox: simulated Postgres write + Notion write are atomic from caller's perspective (Postgres commit + relay dispatch + Notion update)

**Evidence:** `phase-1-log.md` + CI green + a single mission walked through manually with timing/event traces.

**Dependencies:** Phase 0.

**Risk:** OVI queries may require new event types or extra emission points. Mitigation: extend the event vocabulary as needed; emitter.py is permissive.

---

### Phase 2 — Role Eval Infrastructure

**Goal:** Closed-loop, eval-driven role evolution. Per-role scenario evals run weekly; failure patterns flag charter amendments; Captain ratifies.

**Deliverables:**
- SQL migration: `role_evals` table (per role-system research § Reference Architecture)
- 50 scenario evals total (10 × 5 officers). Authored by the implementing session with Captain review pass at end of phase. Examples:
  - **CoS:** compile a mission from a vague Captain DM; detect a 4th-loop pattern in 3-turn convo; arbitrate two officers writing the same memory artifact
  - **CTO:** evaluate a PR for production-readiness; design a no-downtime migration; spot a security vulnerability
  - **CPO:** decompose a Captain outcome into specs; prioritize a backlog given conflicting constraints; identify product-market signal
  - **CRO:** evaluate research source quality; spot a stale "evergreen" brief; identify a tech-radar opportunity
  - **COO:** trace a GDPR data-flow; identify a compliance gap; structure a DPA for a new customer
- Eval runner `cabinet/scripts/run-role-evals.sh <role-slug> [--scenario N]` — spawns a fresh `claude` session in headless mode with the scenario as initial prompt, scores against rubric, writes to `role_evals`
- Weekly cron `cabinet/cron/role-evals-weekly.sh` — runs all 50, emits `eval_recorded` events
- Failure-pattern detector `cabinet/scripts/detect-eval-patterns.sh` — flags 3+ same-type failures in 4 weeks
- Role evolution proposal generator: on flagged pattern, draft a charter amendment YAML in `instance/roles/proposals/`, spawn fresh-context Sonnet review agent, on pass DM Captain with diff. Captain ratifies via Telegram → CoS applies via `framework/roles/lifecycle.py`

**Acceptance gates:**
- 50 evals authored and runnable (each finishes in < 5 min headless)
- Weekly eval cron green on a dry-run
- Synthetic role-evolution proposal walks end-to-end: induce a failure pattern, detector flags, draft, review, Captain ratifies, charter updates

**Evidence:** `phase-2-log.md` + populated `role_evals` table + one fully-cycled proposal example

**Dependencies:** Phase 1 (events flowing, missions running).

**Risk:** Eval authoring quality varies. Mitigation: each eval has a Captain-style rubric; reviewer-agent (Sonnet) checks rubric adherence; Captain spot-checks 10/50 before promoting.

---

### Phase 3 — Captain Intent Layer (4th + 5th loops)

**Goal:** The 4th (pattern listening) and 5th (intent inference) improvement loops are wired into hooks, durable, queryable, and continuously growing.

**Deliverables:**
- The triplet files were already backported in Phase 0; this phase wires them deeply:
  - Mirror them into Postgres (`captain_patterns`, `captain_intents`, `captain_decisions` tables) via post-write hook (file = source of truth, Postgres = queryable index)
  - Pre-reply hook (UserPromptSubmit when message from Captain): scan for 4th-loop meta-signals, append inline encode-offer to draft reply, count pattern occurrence in Redis `cabinet:patterns:seen:<slug>`
  - Post-reply hook: detect decision phrasing in officer reply, log to `captain-decisions.md` automatically (with WHY extraction)
  - 5th-loop integration: pre-reply WHY scan reads `captain-intents.md`, augments reply context with relevant intents
- Cross-officer broadcast on pattern encoding: `notify-officer.sh` blast to all active officers when a new pattern is encoded
- 48h retro extension: CoS's retrospective skill scans recent `captain-decisions.md` entries, extracts latent goals, appends candidates to `captain-intents.md`
- Library Space "Captain" — auto-indexed projection of the triplet for semantic search

**Acceptance gates:**
- Synthetic Captain DM with meta-signal triggers inline encode-offer
- Two occurrences of same pattern → auto-encode + cross-officer broadcast
- 48h retro adds at least one non-trivial intent on dry-run
- Triplet → Postgres mirror is eventually-consistent (≤ 60s lag)

**Evidence:** `phase-3-log.md` + before/after triplet files showing growth

**Dependencies:** Phase 0 (triplet files), Phase 1 (event ledger for `captain_pattern_encoded` events)

**Risk:** False positives (encoding behavior the Captain didn't intend as durable). Mitigation: two-count rule; Captain can `unencode <pattern-slug>` via DM

---

### Phase 4 — Latest CC Adoption (skills, ToolSearch, Agent Teams, /loop/goal)

**Goal:** Cabinet aggressively uses the latest Claude Code primitives. OAuth+Max x20 constraint respected throughout.

**Deliverables:**
- Verify `.claude/settings.json`: `autoMemoryEnabled: true`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"`. Add `enableToolSearch: true` if not present
- New skills authored in `cabinet/skills/<name>/SKILL.md`:
  - `cabinet:mission-compile` — wraps `framework/missions/compiler.py`
  - `cabinet:role-eval` — wraps `cabinet/scripts/run-role-evals.sh`
  - `cabinet:org-status` — wraps `framework/ovi/compute.py` + recent events summary
  - `cabinet:ovi-publish` — publishes weekly OVI to dashboard + Telegram
  - `cabinet:role-evolve` — interactive role-amendment review + apply
  - `cabinet:product-bootstrap` — new project onboarding (Phase 6 prep)
  - `cabinet:product-explore` — holistic product exploration
  - `cabinet:work-graph-complete` — wraps the new completion script
- `/loop` patterns: officers can invoke `/loop` for multi-step autonomous tasks; cost guard halts on budget breach
- `/goal` pattern: Captain outcomes containing "until X is true" map to `/goal`-style autonomous iteration with explicit success criteria
- Subagent discipline: each officer uses `Agent` tool (foreground) for synchronous research; background mode for parallel deep work; subagent_type=Plan for design tasks; Explore for codebase searches
- ToolSearch enforcement: deferred MCP tools loaded only via ToolSearch (reduces context cost). Update officers' boot prompts.
- Per-session token cap: officer halts on Redis counter > daily budget
- `mcp__corridor__analyzePlan` usage: documented in skills; every code-generation skill calls it first

**Acceptance gates:**
- All 8 new skills callable via Skill tool from an officer session
- Measured: average context tokens per session drops ≥ 15% with ToolSearch
- One officer demonstrably uses `/loop` for a 5+ step task without check-in
- Cost-per-officer-per-day stays under platform.yml-configured cap

**Evidence:** `phase-4-log.md` + skills index page on dashboard + sample `/loop` transcript

**Dependencies:** Phase 0 (CLAUDE.md updated)

**Risk:** Agent Teams experimental flag breaks in CC update. Mitigation: feature-flag the flag; graceful degradation to non-teamed Agent calls

---

### Phase 5 — Task-System Adapters

**Goal:** Cabinet's canonical `officer_tasks` + `mission_steps` sync bidirectionally with any external task system. Captain configures which system per project.

**Deliverables:**
- Adapter base interface: `cabinet/scripts/task_adapters/base.py` with abstract methods: `pull()`, `push()`, `delete()`, `link()`, `health_check()`
- 5 concrete adapters in `cabinet/scripts/task_adapters/`:
  - `monday.py` — monday.com GraphQL API; board ID + column mappings configured per project
  - `jira.py` — Jira REST API v3; project key + issue-type mappings
  - `linear.py` — Linear GraphQL API (used for read of legacy Linear archive)
  - `asana.py` — Asana REST API; workspace + project + section mappings
  - `github_issues.py` — gh CLI or GitHub REST API; repo + label mappings
- Each adapter: token-from-env, paginated, idempotent upserts, mapping between canonical schema and external system's fields
- Sync runner `cabinet/cron/task-sync.sh` (every 5 min): pulls external changes, pushes pending canonical changes, resolves conflicts (canonical wins, warning logged)
- `task_sync` table tracks per-task sync state + hash for diff detection
- Project config schema extension: `instance/config/projects/<slug>.yml` gains:
  ```yaml
  tasks:
    system: monday|jira|linear|asana|github_issues
    auth_env: MONDAY_API_TOKEN   # or JIRA_TOKEN, ASANA_TOKEN, etc.
    config:
      board_id: 1234567          # adapter-specific
      column_status: status_1
      column_owner: person
  ```
- Conflict policy: canonical authoritative; external system gets overwritten on conflict. Warning logged to `governance_events` with `task_sync_conflict` type.

**Acceptance gates:**
- Each adapter passes a synthetic round-trip test (create canonical → sync → modify external → sync back → verify canonical updated correctly)
- One real project configured + synced (the current active project, sensed OR a fresh test project)
- Switching active project switches active task system without code changes (just config)

**Evidence:** `phase-5-log.md` + adapter test reports + screenshot of dashboard /tasks showing synced items

**Dependencies:** Phase 1 (officer_tasks / mission_steps in place)

**Risk:** API rate limits and per-system schema quirks. Mitigation: each adapter has its own retry/backoff config; test against sandbox accounts where possible.

---

### Phase 6 — Product-Agnostic Onboarding

**Goal:** Given a repo URL + task-system credentials + Captain name, bootstrap a new project in one command. The Cabinet then explores the product holistically and surfaces what it learned to the Captain.

**Deliverables:**
- `cabinet/scripts/bootstrap-project.sh <repo-url> <project-slug> [--task-system monday]`:
  - Clone repo to `~/work/projects/<slug>/`
  - Detect: language(s) via file extensions + package manifests; framework(s) via package.json / pyproject.toml / Gemfile / Cargo.toml / go.mod; test runner(s); DB(s) referenced; deploy target(s) (Vercel / Heroku / Docker / etc.); CI provider (GitHub Actions / CircleCI / etc.)
  - Generate `instance/config/projects/<slug>.yml` from `_template.yml`, populating detected fields
  - Generate `cabinet/env/<slug>.env` skeleton
  - Interactive Telegram DM to Captain to confirm: Telegram chat ID, task-system + token, Notion workspace (optional), notable channels, etc.
- Holistic product exploration playbook (skill `cabinet:product-explore`):
  - CTO officer (or designated explorer) crawls the repo: top-level READMEs, docs/, dependency tree, recent PRs (`gh pr list --state merged --limit 30`), open issues, recent commit cluster analysis, hot file detection (most-modified in last 90 days)
  - Writes `instance/memory/tier2/cto/product-snapshot.md` (or whichever officer explores) with: stack summary, architecture sketch, hot areas, recent themes, top contributor patterns, deployment topology, open quality concerns
  - Embeds the snapshot into pgvector via `embed-research.sh` for cross-officer retrieval
  - CRO officer reviews the snapshot, queries task system + Notion (if linked) for product context, surfaces gaps
- Structured DM to Captain: "Cabinet has explored <project>. Top observations: X, Y, Z. Open questions: A, B, C. What's the first outcome you want me to pursue?"

**Acceptance gates:**
- Bootstrap from cold succeeds on 3 test projects: a Node app, a Python app, a polyglot monorepo
- Each: Captain receives a well-formed exploration DM within 30 min of bootstrap completion
- Active-project switching works mid-flight (officers re-read config on next session start)

**Evidence:** `phase-6-log.md` + 3 example product-snapshot.md files + 3 Captain-DM transcripts

**Dependencies:** Phase 4 (skills), Phase 5 (task adapters)

**Risk:** Detection heuristics miss exotic stacks. Mitigation: detection is non-fatal — falls through to "I don't recognize this stack, here's what I see, can you tell me more?" + manual config

---

### Phase 7 — Self-Improvement Completion

**Goal:** The evolutionary loops are closed, observable, and producing new artifacts.

**Deliverables:**
- Hat graduation handler: when a `role_hats.uses_count` ≥ 5 across 5+ missions AND OVI doesn't regress during those missions, generate `role_hat_promoted` proposal. Captain ratifies. Lifecycle.py moves the hat's capabilities into the role's permanent charter.
- Structured experience records (Reflexion-style): extend schema with `lesson_type` (enum: blocker, optimization, pattern, anti-pattern, surprise), `trigger_signal`, `applicability_scope`. Records become indexable by future sessions.
- Voyager-style skill induction: when 3+ experience records describe the same successful pattern (semantic match via pgvector), draft a new skill in `memory/skills/evolved/`. Run through a designated golden eval (skill-validation suite). Promote on pass.
- Closed-loop scenario test: synthetic "the CTO needed a code-review hat for missions involving security work" event → evals fail with same type → hat proposed → Captain ratifies → hat graduates after 5 uses → role charter updates → next eval shows the gap closed.

**Acceptance gates:**
- Synthetic hat-graduation end-to-end succeeds (synthetic uses_count manipulation)
- One synthetic skill induced + promoted via golden eval
- 48h retro produces non-trivial intent + pattern additions on real-ish data

**Evidence:** `phase-7-log.md` + before/after role YAML showing hat→charter promotion + new skill in `memory/skills/evolved/`

**Dependencies:** Phase 2 (evals), Phase 3 (intent layer)

**Risk:** Skill induction generates noise / low-quality skills. Mitigation: golden eval gate before promotion; Captain can `archive-skill <slug>` via Telegram

---

### Phase 8 — MacMini Hardening

**Goal:** Resolve all open Mac-deployment stubs; prove unattended runtime stable for a 72h soak.

**Deliverables:**
- Resolve `docs/mac-mini-setup.md` Checkpoint 1.10 (code-signing/notarization). Full runbook, scripted where possible. Use Apple Developer ID + `codesign` + `xcrun notarytool`. The Cabinet's officer-entitlements.plist already exists; needs the signing + notarize workflow.
- LaunchAgent post-deploy verification automation: `cabinet/scripts/verify-launchagents.sh` — checks all 6 plists registered + running + KeepAlive working + log files rotating
- Heartbeat watchdog hardening: detect dead officers via Redis TTL expiry; restart via `launchctl kickstart`; alert on repeat failures (>3 restarts in 1h)
- Tailscale + remote SSH setup runbook
- UPS monitoring (apcupsd) — verified shutdown hook; test by simulating power loss
- Cost guard at OS level: daily token counter aggregator; hard halt at 100% of cap; warn at 80%
- Secrets management: macOS Keychain integration for API tokens (replacing .env where feasible); fallback to `~/.config/cabinet/secrets/` with 600 permissions
- Backup automation: nightly Postgres `pg_dump` + Redis `BGSAVE` snapshot. Target: local NAS via SMB (Captain choice; deferred to open-decisions) OR S3 via aws-cli.

**Acceptance gates:**
- 72h soak: 5 officers running on a test Mac, no manual intervention, briefings + retros + OVI all firing automatically. No data loss across the soak.
- Forced crash test: `kill -9` an officer; supervisor restarts within 30s; session resumes from last-committed state.
- Mac restart test: power-cycle the Mac; all officers come back up automatically; Captain receives "Cabinet is back online" DM.

**Evidence:** `phase-8-log.md` + soak-test report with metrics + crash-recovery log + restart-from-cold drill log

**Dependencies:** All prior phases (we test the whole system)

**Risk:** Code-signing fails for unexpected reasons (cert issues, notarytool errors). Mitigation: dry-run signing in early Phase 8; engage Apple Developer support if blocked.

---

### Phase 9 — Final Validation + Convergence Merge

**Goal:** Prove end-to-end. Merge `claude/convergence` to master. Captain has a runbook ready for MacMini physical deployment.

**Deliverables:**
- Full golden eval suite passes (existing 6 + scenario evals across all framework subsystems)
- 50-eval role suite passes ≥ 80% per officer
- OVI baseline: 4 weeks of synthetic + real data showing stable trend
- End-to-end Captain-outcome shipped: declared → compiled → executed → verified → OVI updated, all autonomously
- `claude/convergence` merged to master (or PR opened for Captain to ratify)
- Updated README, CLAUDE.md, captains-cabinet-guide.md to reflect converged architecture
- Captain receives runbook: "How to deploy this Cabinet to a fresh Mac Mini" (`docs/mac-mini-deploy-runbook.md`)
- Suspension of obsolete branches (the rebuild branch can be archived after merge)

**Acceptance gates:**
- All evals passing
- Captain explicit ratification to merge
- Runbook complete
- MacMini-readiness checklist (below) fully green

**Evidence:** `phase-9-log.md` + final eval report + merged PR or commit-on-master + runbook

**Dependencies:** Phases 0–8

**Risk:** Merge conflicts with any concurrent master work. Mitigation: freeze master writes during final merge window; rebase if needed.

---

## 6. MacMini Readiness Checklist

To be true before shipping to a physical Mac Mini:

- [ ] All 10 phases complete (gate per phase met)
- [ ] Code-signing + notarization runbook executed once on a test Mac
- [ ] `setup-mac.sh` + `deploy-mac.sh` idempotent on a freshly installed macOS
- [ ] All 6 LaunchAgent plists registered with correct paths + KeepAlive working
- [ ] Redis (Homebrew with AOF) + Postgres (Postgres.app or Homebrew 17) + tmux + Claude Code (npm or DMG) installed and verified
- [ ] Cabinet bootstrap from cold completes in <30 min on a fresh Mac
- [ ] All 5 officers spin up, heartbeat alive, can DM Captain
- [ ] OVI computes weekly without manual intervention
- [ ] Cost daily cap enforced (Redis counter + halt + Telegram alert)
- [ ] Tailscale + remote SSH working
- [ ] UPS monitoring active + shutdown hook tested
- [ ] Backups configured + verified (one successful restore drill)
- [ ] Restart-from-cold drill passed (Mac power-cycle → full Cabinet back up unattended within 5 min)
- [ ] 72h soak passed (5 officers, no manual intervention, all scheduled work fires)

---

## 7. Open Decision Points

These don't block the plan but need Captain input during implementation. The implementing session should DM the Captain at the relevant phase:

1. **Backup destination:** local NAS, S3, both? (Phase 8)
2. **Notion vs. Library as primary knowledge canon for new projects** — pull from Notion or use only the Library? (Phase 6)
3. **Officer count for v1:** keep all 5 (CoS/CTO/CPO/CRO/COO) or trim to 3 to start lighter? (Phase 9)
4. **Voice on/off default** for new deployments? (Phase 4 / 6)
5. **Captain triplet scope:** scoped to one project, or universal Captain memory across all projects? (Phase 3)
6. **`/loop` autonomous iteration limit:** how many cycles before mandatory Captain check-in? (Phase 4)
7. **Eval rubric format:** Captain-authored YAML rubric vs. natural-language description? (Phase 2)
8. **Hat graduation threshold:** uses_count ≥ 5? Other? (Phase 7)

---

## 8. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| Agent Teams experimental flag breaks in CC update | M | Feature-flag; graceful degradation to standard `Agent` calls |
| Mission compiler heuristics get edge cases wrong | M | Captain can override via Telegram; learn over time via experience records |
| OVI components get gamed by the Cabinet itself | H | Multi-component; Captain-authored evals; 20% eval rotation quarterly; held-out set |
| Task adapter API breakage on external systems (Monday/Jira/Asana) | M | Adapters are isolated modules; failures don't cascade; per-adapter health checks |
| Token cost spike from `/loop` | M | Hard daily cap; alert at 80%; auto-halt at 100% |
| Code-signing/notarization harder than expected | H | Pre-flight on test Mac early in Phase 8; engage Apple Developer support if blocked |
| Role evolution drift (system gets "weird") | H | Captain approval required on every charter change; lineage DAG preserves history; Captain can roll back any change via `role-revert <slug> <to-event-id>` |
| Captain triplet files diverge from Postgres index | L | File is source of truth; reconciliation cron every 1h |
| OAuth-only constraint blocks future feature | M | We're already designing around this. If a future CC feature requires API key, document the gap and surface to Captain |
| Backport conflicts in Phase 0 | M | Incremental cherry-picks; test runs between; phase-0-log.md tracks each |
| Heuristic role assignment in mission compiler is wrong | M | Captain can re-assign via Telegram or by editing the compiled mission YAML before activation |

---

## 9. Operating Principles (for the implementing session)

These apply throughout implementation:

1. **Corridor analyzePlan first:** Every code-generation step calls `mcp__corridor__analyzePlan` before writing code. No exceptions.
2. **Read CLAUDE.md afresh each phase start:** the project's CLAUDE.md may be updated by prior phases; always re-read.
3. **Commit small, often:** each meaningful change is its own commit; phase-end commits tag the phase.
4. **Tests before commit:** never commit a phase-end without `bash cabinet/tests/run-all.sh && pytest framework/` passing.
5. **Capture surprises:** any unexpected behavior → experience record. Use Reflexion-style structure (lesson_type, trigger_signal, applicability_scope).
6. **Escalate, don't loop:** if blocked >2 cycles on the same problem, DM Captain with diagnosis + options.
7. **Document the WHY:** each commit message includes the WHY in the body, not just the WHAT.
8. **Cost discipline:** check Redis token counter before expensive operations; halt + DM Captain if approaching cap.
9. **Use Agent Teams for parallel work:** when 2+ independent tasks exist, spawn subagents in parallel (single message, multiple Agent tool uses).
10. **Use Plan agents for design:** before non-trivial code, spawn `subagent_type=Plan` to draft an approach. Then Corridor. Then code.

---

## 10. Glossary

- **Charter:** YAML document defining a role's mission, scope, success criteria, authority
- **Hat:** Temporary capability bag granting extra tools/permissions; can graduate to permanent capability
- **Lineage:** Append-only DAG of role evolution (predecessors → successors via 'evolved' / 'split' / 'merge' / 'spawned')
- **Mission:** Compiled DAG decomposing a Captain outcome into work nodes with role assignments
- **OVI:** Outcome Value Index — weighted multi-component composite measuring org performance
- **Triplet:** captain-decisions.md + captain-patterns.md + captain-intents.md (the Captain memory layer)
- **4th loop:** Inline pattern listening on Captain DMs; auto-encode on 2nd occurrence
- **5th loop:** Pre-reply WHY scan (intent inference) before composing Captain-facing outbound
- **Session bridge:** `framework/missions/session_bridge.py` — module mapping mission state → officer session context at session start
- **Officer-session contract:** Formalized commit/restore semantics making sessions ephemeral execution surfaces for durable roles
- **Outbox:** Postgres table holding pending cross-system writes; relay process dispatches them idempotently
- **Convergence branch:** `claude/convergence`, cut from rebuild, the working branch for this plan

---

## 11. Implementation Kickoff Command

When ready to begin Phase 0, the implementing session's `/goal` is:

> `/goal Execute the convergence plan at docs/convergence-analysis-2026-05-26/05-convergence-plan.md, phase by phase via /loop, until the MacMini-readiness checklist is fully green. Begin with Phase 0. Use Corridor analyzePlan before every code-generation step. Use Agent Teams for parallel work. Escalate to Captain via Telegram if blocked >2 cycles on the same issue. Commit per phase. Maintain phase-<N>-log.md and Redis status keys for resume.`

---

## 12. Cross-references

- Detailed branch analysis (current): `01-branch-funny-fermi-analysis.md`
- Detailed branch analysis (rebuild): `02-branch-rebuild-analysis.md`
- Claude Code features research: `03-claude-code-features.md`
- Durable role-system research: `04-durable-role-system.md`
- Index: `00-INDEX.md`

---

*End of convergence plan.*
