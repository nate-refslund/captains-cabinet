# Branch Analysis: claude/clever-tesla-CS3Su-rebuild

**Date:** 2026-05-26
**Method:** Background general-purpose agent (Sonnet 4.6) with full worktree access
**Worktree:** `/Users/nate/captains-cabinet/.claude/worktrees/rebuild-analysis/`
**HEAD commit:** `a08bcac`
**Branch base:** evolved from the same operational foundation as master, with a focused new `framework/` layer added on top.

---

## 1. New Framework Architecture

The rebuild introduces a clean six-subsystem `framework/` layer as a typed Python runtime sitting above the existing bash operational infrastructure. Each subsystem has its own module, SQL schema, tests, and rules file.

### 1.1 Event Ledger (`framework/events/`)

The foundational design choice: **events are the single source of truth**. Every state change emits to a typed JSONL log and optionally to a Postgres `org_events` table. The vocabulary is explicit and versioned — 40 valid event types covering the entire org lifecycle:

- Captain actions (`captain_goal_declared`, `captain_outcome_ratified`, `captain_decision_logged`)
- Role lifecycle (`role_created`, `role_charter_changed`, `role_hat_assigned`, `role_hat_promoted`, `role_retired`)
- Mission lifecycle (`mission_created`, `mission_activated`, `mission_completed`, `mission_failed`)
- Work graph (`work_item_created`, `work_item_assigned`, `work_item_completed`, `work_item_verified`)
- Policy, measurement, learning, system events

The `emit()` function (`framework/events/emitter.py:86-118`) is callable from both Python and shell scripts (`python3 emitter.py <type> <actor> <payload_json>`). It writes JSONL locally first, then best-effort to Postgres — so a dead DB connection never loses events. A `replay()` function supports filtering by time, type, and actor, enabling projection of any derived view.

**Schema** (`framework/events/schema.sql`): the `org_events` table has a `parent_id` causal-chain column, enabling event genealogy. Five indexes including a GIN index on the JSONB `payload` column.

### 1.2 Role Lifecycle (`framework/roles/lifecycle.py`)

Roles are modeled as durable entities in YAML files at `instance/roles/active/<slug>.yml`. This is the most important conceptual shift: roles are not agent personas or session configurations — they are persistent entities with:

- `charter` (what this role is responsible for)
- `capabilities` (list of capabilities that drive task assignment)
- `authority_level` (observer / standard / elevated / admin)
- `status` (active / suspended / retired)

**Hats** (`assign_hat()`) are temporary specializations: bounded by mission, optionally time-expiring, carrying extra capabilities. Effective capabilities = base role caps + all active hat caps. A hat that proves permanently valuable gets promoted to a permanent capability.

**Lineage** (`_append_lineage()`) is append-only YAML at `instance/roles/lineage.yml`. Every adaptation — creation, charter change, capability add/remove, hat assignment, suspension, retirement — gets a lineage entry with `evidence`, `rationale`, `approved_by`, and a link to the event that triggered it. Retiring a role moves its YAML to `instance/roles/archive/` but never deletes; lineage is preserved and can be queried.

**SQL schema** (`framework/events/schema.sql:26-80`): the `roles`, `role_lineage`, and `role_hats` tables mirror the filesystem structure in Postgres for queryable org state. The schema enforces the constraint that `role_lineage.adaptation_type` must be one of a closed set of valid values.

### 1.3 Mission Compiler (`framework/missions/compiler.py`)

Captain outcomes live in `instance/config/outcomes.yml` (validated by `framework/schemas/outcome.schema.json`). The compiler transforms them into executable work graphs:

1. Each `measurable_criterion` becomes a `WorkNode`
2. Nodes are assigned to roles via keyword-matching against role capabilities (`_match_role_for_task()`)
3. Dependencies are inferred: schema/database tasks early, deploy/production tasks late, everything else middle (`_infer_dependencies()`)
4. A `WorkGraph` is validated (cycle detection via Kahn's algorithm, reachability check)
5. A `mission_created` event is emitted

The dependency inference is heuristic and simple — it classifies criteria into three phases based on keyword presence and orders them sequentially within each phase. This gets about 80% of cases right without requiring the Captain to specify dependency graphs manually.

**Session bridge** (`framework/missions/session_bridge.py`): reads `instance/config/outcomes.yml`, compiles all active outcomes into missions, and finds the first `ready` task (all dependencies met) assigned to the current officer's role. This is consumed by the `session-task-inject.sh` hook, which fires on `UserPromptSubmit` (first prompt only) and injects mission context into the officer session.

### 1.4 OVI Computation (`framework/ovi/`)

Five weighted components:

| Component | Weight | Direction | Source |
|-----------|--------|-----------|--------|
| `outcome_progress` | 0.30 | normal | computed |
| `task_throughput` | 0.25 | normal | DB query |
| `captain_attention_cost` | 0.20 | **inverse** | DB query |
| `learning_rate` | 0.15 | normal | DB query |
| `verification_pass_rate` | 0.10 | normal | computed |

Each component has a `default_range` for normalization. The `captain_attention_cost` inverse component is the most significant design choice: the org's score goes **up** when the Captain needs to intervene less.

`compute_ovi()` validates all components are provided, normalizes each to 0–1 (clamped), computes a weighted average, determines trend vs. previous snapshot (±2% threshold), and emits `ovi_snapshot_computed`. A `compute_sample()` CI mode generates synthetic data and verifies mathematical invariants.

**LaunchAgent** (`cabinet/launchd/com.cabinet.ovi-weekly.template.plist`): runs `python3 framework/ovi/compute.py` every Monday at 08:00 via launchd. The OVI score is thus a weekly heartbeat about organizational health.

### 1.5 Measurement Scenarios (`framework/measurement/`)

A lightweight scenario runner (`scenario_runner.py`) auto-discovers scenario modules from `scenarios/`. Each scenario has `setup()`, `execute()`, and `verify()` phases and returns named assertions. Unlike golden evals (which test "does the machinery work"), scenario evals test "is the organization capable."

Four scenarios are defined:

- `outcome_to_mission` — Captain declares an outcome, Cabinet compiles a valid mission with no cycles, all nodes assigned
- `role_adaptation` — Role receives adaptations, lineage intact, effective capabilities correct
- `role_retirement` — Role retired, learning preserved in archive, lineage complete
- `policy_enforcement` — Dangerous commands blocked, safe commands allowed

These run in CI under the `Framework tests — Event ledger + Roles + Missions + OVI + Scenarios` step.

---

## 2. Policy Engine (`cabinet/scripts/lib/policy_engine.py`)

At 1,042 lines with 1,458 lines of tests, this is the most battle-hardened new component. It replaces the bash-regex command-matching sections (sections 3-5) in `pre-tool-use.sh`.

The design innovation is using Python's `shlex` for shell parsing rather than regex, which handles:
- Quote splicing (`"su"do`, `'su'do`)
- Backslash escapes (`\sudo`)
- ANSI-C quoting (`$'sudo'`)
- Heredoc injection
- Brace expansion (`{,sudo} ls`)
- `eval` and `bash -c` wrapping
- Full-path invocations (`/usr/bin/sudo`)
- `env VAR=val` prefix stripping

Policy types supported (per `policy.schema.json`):
- `binary_block` — block specific binaries regardless of invocation form
- `destructive_rm` — block `rm -rf` targeting dangerous paths
- `command_contains` — block commands matching string patterns (any or all)
- `path_block` — block writes to protected paths (glob patterns)
- `bash_write_to_path` — block bash redirect writes to path patterns
- `tier2_isolation` — officers can only write to their own tier2 directory

Policies are layered: `framework/policies/base-safety.yml` (universal) → `presets/*/policies/*.yml` (preset-level) → instance overrides. The work-preset adds codebase ownership rules (only CTO can modify `/workspace/product`), production deploy protection, and infrastructure file protection.

The engine is invoked directly from `pre-tool-use.sh` section 3 — it reads the full hook input JSON on stdin, evaluates all loaded policies, and exits 2 with a block message if any policy matches. The old bash regex sections 3-5 are **deleted and replaced** by this single Python call.

The pre-tool-use.sh retains its stateful bash sections (kill switch, spending limits, Layer 1 gate, CI Green gate) because these require Redis state lookups that the pure Python engine doesn't handle. The Layer 1 gate in the bash section is itself extraordinarily complex — hundreds of lines of battle-hardened regex developed over a dozen FW-0xx iterations (FW-029 through FW-051). The rebuild hasn't replaced this section.

---

## 3. Work Graph (`cabinet/scripts/lib/work_graph.py`)

A pure Python stdlib-only DAG implementation (224 lines). Nodes are `WorkNode` dataclasses with status, verification criteria, and evidence fields. `WorkGraph` supports:

- Cycle detection (Kahn's algorithm)
- Reachability validation
- `ready_tasks()` — tasks whose dependencies are all DONE
- `complete_task()` — marks DONE or FAILED based on verification result
- `topological_sort()` — dependency-ordered execution order
- JSON serialization/deserialization

329 lines of tests cover edge cases: empty graphs, self-loops, disconnected components, cycle detection, verification semantics.

---

## 4. Claude Code Native Integration

This is where the rebuild makes its most distinctive structural bets:

**`.claude/settings.json`** enables `autoMemoryEnabled: true`, explicitly sets `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"`, and wires five hook types:
- `UserPromptSubmit` → `pre-captain-dm.sh` + `captain-rule-encoder.sh` + **`session-task-inject.sh`** (new)
- `PreToolUse` → `pre-tool-use.sh` + `build-vs-buy-precheck.sh` + `captain-posture-warroom.sh` + `captain-reply-refine.sh`
- `PostToolUse` → `post-tool-use.sh` + `post-reply-voice.sh` + `post-reply-memory.sh` + **`post-subagent.sh`** (new) + `post-file-write-memory.sh`
- `Stop` → `stop-hook.sh` + **`session-stop.sh`** (new)
- `Notification` → **`on-notification.sh`** (new)

**Path-scoped rules** (`.claude/rules/*.md`): five rule files with glob patterns that inject domain-specific constraints only when working in relevant directories:
- `framework.md` — framework code rules (event-first, no product-specific logic)
- `hooks.md` — hook development rules (50-line limit, stderr for blocks, emit events)
- `missions.md` — mission/OVI rules (Captain-only outcomes, DAG validation required)
- `policies.md` — policy engine rules (YAML+Python, not bash regex)
- `roles.md` — role management rules (create slowly, adapt frequently, lineage append-only)

**Agent frontmatter** (`presets/work/agents/cos.md`): officer agents now carry YAML frontmatter specifying `model: "claude-opus-4-7"`, `effort: "max"`, `allowedTools`. This makes model routing declarative rather than a flag passed to the `claude` CLI.

**CLAUDE.md rewrite**: the project CLAUDE.md is radically condensed from the 3,000+ word multi-topic document in master to a ~140-line focused system map. Key differences:
- References the framework subsystems directly (`framework/events/`, `framework/roles/`, etc.)
- `autoMemoryEnabled` is described as the persistence mechanism (not manual tier2 writes)
- The session bridge is surfaced as the mechanism for mission task injection
- Three-layer architecture (framework/presets/instance) is the primary mental model

---

## 5. New Hooks

Four hooks are brand-new in the rebuild:

**`on-notification.sh`** (Notification hook): fires when CC receives any notification. Logs receipt and emits `session_started` event. 24 lines.

**`session-stop.sh`** (Stop hook): fires when the CC session ends. Writes last-session timestamp to Redis (24h TTL) and emits `session_ended` event. 29 lines.

**`post-subagent.sh`** (PostToolUse matcher: Agent): fires after any Agent tool completes. Logs subagent completion and, if the prompt references a task ID matching `(TASK|FW|PROD)-\d+`, emits `work_item_completed`. 29 lines.

**`session-task-inject.sh`** (UserPromptSubmit): fires only on the first prompt of each session (sentinel file guard). Calls the session bridge Python module to find the next ready mission task for the current officer, formats it, and returns `hookSpecificOutput.additionalContext` to inject the task context into the session. This is the key "mission → session" integration point.

---

## 6. Configuration and Product-Agnosticism

**Projects** (`instance/config/projects/_template.yml`): per-project slug, GitHub repo, Vercel/Neon IDs, Telegram chat ID, workspace path. No product-specific logic in framework code.

**Contexts** (`instance/config/contexts/`): context slugs (adhoc, personal) link to project slugs. An "active project" (`instance/config/active-project.txt`) gates which project is currently in focus.

**Outcomes** (`instance/config/outcomes.yml`): the only input the Captain provides to drive the mission compiler. Validated by JSON Schema. No product knowledge required in framework code.

**Three-layer separation** enforced by rule: `framework.md` rule explicitly states "Never import from `instance/` or `presets/` in framework code." The framework modules only import from each other. Instance and preset configuration flows in through environment variables and path conventions.

---

## 7. Mac-Native Readiness

The rebuild has the most complete Mac-native setup of any branch:

- `cabinet/scripts/setup-mac.sh`: one-command Mac Mini setup (Homebrew deps, Redis, Python packages, directories, preset load, policy engine verify, framework tests, config check)
- `cabinet/scripts/deploy-mac.sh`: `envsubst`-based plist deployment to `~/Library/LaunchAgents/` with dry-run support
- **Six LaunchAgent plists**: officer (per-officer), heartbeat-watchdog, cost-summary, worktree-listener, OVI-weekly, plus `officer-entitlements.plist`
- The OVI-weekly plist runs every Monday at 08:00 — directly invoking the new framework OVI compute module
- Proper KeepAlive semantics (`SuccessfulExit: false`), `ThrottleInterval: 30`, `SoftResourceLimits.NumberOfFiles: 4096`, `~/Library/Logs/cabinet/` log paths
- `start-officer-mac.sh` exists alongside Docker `start-officer.sh`

---

## 8. What Was Preserved

All critical operational infrastructure is intact:

- **Officer lifecycle**: `create-officer.sh`, `start-officer.sh`, `start-officer-mac.sh`, `suspend-officer.sh`, `resume-officer.sh`, `list-officers.sh` — all present
- **Tier 2 memory**: `instance/memory/tier2/` with directories for all five officers (cos, cto, cpo, cro, coo)
- **Telegram/warroom communication**: `notify-officer.sh`, `send-to-group.sh`, `send-to-warroom.sh`, `send-voice.sh`, `post-reply-voice.sh` — all present
- **Experience records**: `record-experience.sh`, `publish-skill-update.sh` — present
- **Skills system**: `memory/skills/` with 13 foundation skills, `evolved/` subdirectory
- **Briefing/retro crons**: `cabinet/cron/briefing.sh`, `retro-trigger.sh`, `retrospective.sh`, `backlog-refine.sh`, `research-sweep.sh`
- **Five preset officer agents**: cos, cto, cpo, cro, coo in `presets/work/agents/`
- **CI pipeline**: full `cabinet-ci.yml` including the new framework tests steps
- **Library MCP**: `cabinet/channels/library-mcp/`
- **Redis trigger channel**: `cabinet/channels/redis-trigger-channel/`

**Captain decisions/patterns/intents** (`captain-decisions.md`, `captain-patterns.md`, `captain-intents.md`): these files are **absent** from the `shared/interfaces/` directory in the rebuild branch. The directory only contains `captain-rules-index.yaml` and `research-briefs/`. The 4th and 5th improvement loops described in CLAUDE.md (master) are not explicitly represented in the rebuild's CLAUDE.md. This is a deliberate simplification — `autoMemoryEnabled` is the replacement mechanism.

**Phase-1 commercial specs (050-065)**: absent. The `specs/` directory doesn't exist. These were removed intentionally — the rebuild is product-agnostic and the commercial specs are deployment-specific.

**Cutover scripts** (Linear → `/tasks`): no dedicated cutover script found. The rebuild branch positions the `/tasks` backlog as established infrastructure rather than something being migrated to.

---

## Scores (1–5)

**Maturity: 3/5**
The new framework modules are complete and tested. But they sit alongside (not replacing) the existing operational bash infrastructure. The two layers are not yet fully integrated — the bash side doesn't update mission work graph node statuses when tasks complete, OVI data sources are documented in `components.yml` but not hooked into the actual bash cron, and the session bridge produces the right output but the officer still has to act on it manually.

**Product-agnosticism: 4/5**
The framework layer is genuinely product-agnostic. The three-layer architecture is clean and enforced by rules. `instance/config/projects/_template.yml` and `contexts/_template.yml` make onboarding a new project straightforward. The work-preset policies assume `/workspace/product` which could be parameterized further (score held at 4 rather than 5).

**Self-improvement maturity: 3/5**
The event ledger creates a durable organizational memory that was absent before. OVI trend detection provides a quantitative signal. Scenario evals test capability, not just machinery. But the learning loops themselves (reflection, retro, evolution) are still description-driven in agent docs rather than programmatically triggered. `autoMemoryEnabled` is the main improvement mechanism and it's mostly passive.

**Role-as-entity maturity: 4/5**
This is the branch's strongest contribution. Roles as YAML entities with charter, capabilities, authority level, and append-only lineage is a well-designed persistent entity model. The hat system is elegant — temporary specializations that can graduate to permanent capabilities. SQL schema enforces the model in Postgres. What's missing: eval history is not modeled per role (there's no `role_evals` table), and memory ownership (which tier2 notes belong to which role) is conventional rather than enforced by the role entity.

**Mission compilation maturity: 3/5**
The compiler works end-to-end and is tested. But it's heuristic — keyword matching for role assignment and phase-classification for dependency inference are approximations. There's no feedback loop: if a task is assigned to the wrong role, the system doesn't learn from that. The session bridge correctly injects the next ready task, but there's no mechanism for an officer to mark a task complete in the work graph from within their session.

**OVI measurement maturity: 3/5**
The math is correct, the components are thoughtfully chosen, and the weekly LaunchAgent will run. But two of the five components (`outcome_progress`, `verification_pass_rate`) are marked `source: computed` in `components.yml` with no query — they require external data inputs that aren't yet specified. The database queries for the other three components reference tables (`work_graph_nodes`, `decision_log`, `experience_records`) that may not be populated by current operational scripts.

**Policy enforcement maturity: 5/5**
The typed Python policy engine is the most mature component. 1,042 lines of production-quality code with 1,458 lines of tests covering dozens of bypass forms. It's wired into `pre-tool-use.sh` and evaluated on every tool call. The JSON Schema for policy files ensures policies can be added by non-Python authors without introducing broken YAML. The layered framework → preset → instance architecture allows customization without modifying universal safety rules.

**Autonomy ceiling: 3/5**
The `session-task-inject.sh` hook means officers wake up knowing what to work on — a significant improvement over manual task fetching. But the loop isn't closed: there's no mechanism to mark work graph nodes done, so the same task would be re-injected on the next session start. The OVI LaunchAgent and cron infrastructure provide scheduled autonomy, but the actual execution still depends on officers receiving triggers and acting on them.

**Mac-Mini readiness: 4/5**
The setup is more complete here than in any other branch — setup script, deploy script, six plist templates, proper KeepAlive semantics. What's missing: no automated post-deploy verification that all services came up cleanly, and the `CABINET_SOURCE_REPO` path in `deploy-mac.sh` still defaults to `~/work/captains-cabinet` which is a hardcoded assumption.

**Claude Code feature utilization: 5/5**
The rebuild uses essentially every available CC feature: `autoMemoryEnabled`, path-scoped rules, all five hook types (UserPromptSubmit, PreToolUse, PostToolUse, Stop, Notification), agent YAML frontmatter for model/effort/tools, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. The hook coverage of session lifecycle events (start, stop, notification, subagent completion) is complete.

---

## Top 5 Strengths

1. **Event ledger as org black box** (`framework/events/emitter.py`, `framework/events/schema.sql`): every state change is recorded. The causal chain (`parent_id`) enables replaying org history. This is the foundation that makes role lineage, OVI computation, and measurement possible without custom scraping.

2. **Typed policy engine** (`cabinet/scripts/lib/policy_engine.py`): replaces 700+ lines of brittle bash regex with a structured Python evaluator using `shlex`. The JSON Schema for policy YAML makes the safety layer auditable, extensible, and layered. 1,458 lines of tests.

3. **Role-as-entity with lineage** (`framework/roles/lifecycle.py`, `framework/events/schema.sql:46-80`): the first design in the codebase where roles are modeled as persistent entities rather than prompt configurations. Charter, capabilities, authority level, hats, append-only lineage, and archive on retirement. The evidence/rationale fields on lineage entries are what will enable org learning over time.

4. **Claude Code native integration** (`.claude/settings.json`, `.claude/rules/*.md`): full utilization of CC hooks including the new `Notification` and `Stop` hooks plus `UserPromptSubmit` for task injection. Path-scoped rules ensure domain-specific constraints apply exactly when relevant.

5. **Setup-to-deploy coherence for Mac** (`cabinet/scripts/setup-mac.sh`, `cabinet/scripts/deploy-mac.sh`, `cabinet/launchd/*.plist`): the path from a bare Mac Mini to a running Cabinet is scripted end-to-end. `setup-mac.sh` even runs the framework tests as a post-install verification step.

---

## Top 5 Weaknesses

1. **The work graph is write-once from session context** (`framework/missions/session_bridge.py:51-87`): the session bridge injects the next ready task, but there is no hook or script for an officer to call `complete_task()` on a work graph node after finishing it. Tasks will be re-injected on every new session start until the node is manually marked done.

2. **OVI has incomplete data sources** (`framework/ovi/components.yml:lines 19-36`): `outcome_progress` and `verification_pass_rate` are marked `source: computed` without a corresponding query or computation path. The weekly OVI LaunchAgent will silently fail or require manual data construction until these are wired.

3. **Captain decisions/patterns/intents system was dropped** (`shared/interfaces/` only contains `captain-rules-index.yaml`): the 4th and 5th improvement loops (pattern listening, intent inference) — which are sophisticated behavioral feedback mechanisms in master — have no analog in the rebuild. The `autoMemoryEnabled` replacement is less structured and harder to audit.

4. **Role entities aren't yet wired to agent frontmatter** (`instance/roles/active/` vs `.claude/agents/`): role YAML entities in `instance/roles/active/` are the declared source of truth, but `presets/work/agents/*.md` files still define the agent frontmatter. There's no script or mechanism to compile role entities into agent `.md` files. The two representations can drift.

5. **Mission compiler dependency inference is heuristic** (`framework/missions/compiler.py:105-141`): the `_infer_dependencies()` function classifies criteria by keyword presence (setup vs. deploy) and creates sequential dependencies. This works for simple cases but has no way to express parallel tasks, external dependencies, or tasks that depend on Captain decisions rather than prior tasks.

---

## Top 5 Gaps vs. the Goal

1. **No feedback loop from task completion to work graph state**: the org runtime can compute what to work on but cannot record that work was done. An officer completing a task has no programmatic way to advance the mission. The gap between "task injected" and "work graph updated" is manual.

2. **OVI has no connection to the event ledger's rich data**: the event ledger records every `work_item_completed`, `eval_passed`, `experience_recorded`, etc. but the OVI compute module reads from tables like `decision_log` and `experience_records` that aren't populated by the event emitter. The richest data source (the event stream) is disconnected from the measurement layer.

3. **Role eval history is unmodeled**: the schema has `role_lineage` but no `role_evals` table or eval history concept. The goal is roles with "eval history" — a record of how well each role performed on specific scenarios over time. This would enable data-driven charter evolution rather than manual captain-approved adaptations.

4. **No mission execution supervisor**: there's a compiler (outcome → work graph) and a bridge (work graph → session context), but no execution supervisor that polls unassigned or stuck tasks and routes them to available officers. The system can express a work graph but cannot autonomously drive it to completion without officer check-ins.

5. **Product-agnosticism is complete at framework level but incomplete at preset level**: `presets/work/policies/work-safety.yml` has hardcoded paths (`/workspace/product`, `/workspace/*/`) that assume Docker deployment. The Mac-native context uses direct filesystem paths. A new preset deployer must manually adjust these.

---

## Top 5 Unique Opportunities

1. **Event replay → org autopsy**: the append-only event ledger with causal chains enables a future `org-autopsy` tool — replay any mission from `mission_created` forward, reconstruct every decision made, identify where it stalled. This doesn't exist anywhere else in the codebase and would be uniquely powerful for the self-improvement loop.

2. **OVI as Captain-facing outcome signal**: `captain_attention_cost` as an inverse OVI component is an elegant framing — the Cabinet's score improves when the Captain needs to intervene less. Making this visible in the dashboard (trend: up/down/flat vs. last week) could replace the current "Captain asks for status" DM pattern.

3. **Hat graduation to capability**: `role_hat_promoted` event type is defined in the emitter but not yet implemented in lifecycle.py. The scenario where a repeatedly-useful hat automatically gets promoted to a permanent capability (with lineage evidence) is a concrete, testable self-improvement mechanism that doesn't require AI judgment.

4. **Scenario evals as org capability passport**: the `scenario_runner.py` infrastructure can be extended to run organizational capability scenarios before any major change (role retirement, charter change, new officer hire). A "can the org still compile a mission after this change?" check as a pre-commit gate would be a novel form of organizational regression testing.

5. **`autoMemoryEnabled` + event ledger = cross-session institutional memory**: the combination of CC's native auto-memory with the event ledger means that role entities have two memory systems: CC's semantic memory (past conversations, decisions) and the event ledger (structured org history). A role-aware memory retrieval that queries both — "what events has this role been involved in?" alongside "what has this session remembered?" — would be substantially richer than either alone.

---

## Critical Question: Did the Rebuild Lose Anything Important?

| System | Status |
|--------|--------|
| Mac-native infrastructure (LaunchAgent plists, deploy-mac.sh) | **Preserved and extended** — 6 plists now including OVI-weekly |
| Officer lifecycle (create/start/suspend/resume) | **Preserved** |
| Telegram/warroom communication | **Preserved** (notify-officer.sh, send-to-group.sh, send-voice.sh) |
| Tier 2 memory system | **Preserved** (instance/memory/tier2/ with all 5 officer dirs) |
| Captain decisions/patterns/intents trail | **Dropped** — shared/interfaces/ is nearly empty; replaced by autoMemoryEnabled |
| Experience records / skills system | **Preserved** (record-experience.sh, memory/skills/) |
| Cutover scripts (Linear → /tasks) | **Not present** — treated as migrated/irrelevant |
| Phase-1 commercial specs (050-065) | **Removed** — no specs/ directory; deliberate product-agnosticism |

The most meaningful thing dropped is the Captain decisions/patterns/intents system — the structured behavioral feedback files that feed the 4th and 5th improvement loops. These are not trivially replaced by `autoMemoryEnabled`, which is unstructured. In the rebuild's model, this learning is implicit in the event ledger and auto-memory rather than explicit in indexed files.

---

## Key Files Inventory

| File | Purpose |
|------|---------|
| `framework/events/emitter.py` | Core event emission — write to JSONL + Postgres; callable from Python and shell |
| `framework/events/schema.sql` | SQL schema for org_events, roles, role_lineage, role_hats, outcomes, missions, work_graph_nodes/edges, ovi_snapshots, policy_evaluations |
| `framework/roles/lifecycle.py` | Role CRUD with lineage tracking and hat management |
| `framework/missions/compiler.py` | Transform outcomes YAML into WorkGraph missions with heuristic role assignment |
| `framework/missions/session_bridge.py` | Find next ready mission task for a given officer role |
| `framework/ovi/compute.py` | Weighted OVI composite score computation with trend detection |
| `framework/ovi/components.yml` | 5 OVI component definitions with weights and data sources |
| `framework/measurement/scenario_runner.py` | Organizational capability scenario harness |
| `framework/measurement/scenarios/outcome_to_mission.py` | End-to-end scenario: outcome → compiled mission → validated work graph |
| `framework/measurement/scenarios/role_adaptation.py` | Role adaptation scenario: lineage preserved, capabilities updated |
| `framework/policies/base-safety.yml` | Universal safety policies (dangerous binaries, destructive SQL, constitution readonly) |
| `framework/policies/policy.schema.json` | JSON Schema for policy YAML files — 6 policy types |
| `framework/schemas/outcome.schema.json` | JSON Schema for Captain outcomes YAML |
| `cabinet/scripts/lib/policy_engine.py` | 1,042-line typed policy engine replacing bash regex sections 3-5 |
| `cabinet/scripts/lib/work_graph.py` | Pure Python DAG with cycle detection, ready_tasks(), topological_sort() |
| `cabinet/scripts/hooks/session-task-inject.sh` | UserPromptSubmit hook: inject next mission task on session start |
| `cabinet/scripts/hooks/session-stop.sh` | Stop hook: emit session_ended event |
| `cabinet/scripts/hooks/on-notification.sh` | Notification hook: emit session_started on notification receipt |
| `cabinet/scripts/hooks/post-subagent.sh` | PostToolUse:Agent hook: emit work_item_completed if task ref found |
| `cabinet/scripts/setup-mac.sh` | One-command Mac Mini setup with dependency check, Python install, tests |
| `cabinet/scripts/deploy-mac.sh` | envsubst-based plist deployment to ~/Library/LaunchAgents/ |
| `cabinet/launchd/com.cabinet.ovi-weekly.template.plist` | LaunchAgent: run OVI compute every Monday 08:00 |
| `cabinet/launchd/com.cabinet.officer.template.plist` | LaunchAgent template for officer sessions with KeepAlive + resource limits |
| `.claude/settings.json` | autoMemoryEnabled, all 5 hook types wired, CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 |
| `.claude/rules/framework.md` | Path-scoped rule: event-first, no product logic, tests required |
| `.claude/rules/roles.md` | Path-scoped rule: role management constraints including append-only lineage |
| `.claude/rules/missions.md` | Path-scoped rule: Captain-only outcomes, DAG validation required |
| `.claude/rules/policies.md` | Path-scoped rule: YAML+Python not bash regex, positive+negative tests required |
| `instance/config/outcomes.yml` | Captain-declared outcomes — the only Captain input to the mission compiler |
| `instance/config/platform.yml` | Platform config: spending limits, communication prefs, officer types, voice settings |
| `presets/work/preset.yml` | Work preset metadata: archetype list, naming style, autonomy level |
| `presets/work/policies/work-safety.yml` | Preset-level policies: codebase ownership, deploy protection, infrastructure files |
| `CLAUDE.md` (rebuild rewrite) | Condensed 140-line system map replacing the 3,000-word CLAUDE.md from master |
