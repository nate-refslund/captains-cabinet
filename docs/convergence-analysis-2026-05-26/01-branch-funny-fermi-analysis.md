# Branch Analysis: claude/funny-fermi-8daf32 (≈ master)

**Date:** 2026-05-26
**Method:** Background general-purpose agent (Sonnet 4.6) with full repo access
**Worktree:** `/Users/nate/captains-cabinet/.claude/worktrees/funny-fermi-8daf32/`
**Branch:** `claude/funny-fermi-8daf32` (1 commit ahead of master; effectively IS master)

---

## 1. High-Level Architecture and Mental Model

### What the Cabinet is

The Cabinet is a framework for running a **persistent, autonomous, self-improving AI organization** that executes under a single human Captain. The mental model is explicitly organizational: the Captain sets strategic direction; Officers own domains; Crew (Agent Teams) execute tasks; the organization continuously learns and rewrites its own instructions.

The core insight is articulated in `captains-cabinet-guide.md`: "A Captain's Cabinet is not a chatbot. It is not a pipeline. It is not a script. It is an organization — with roles, memory, judgment, and the capacity to reorganize itself."

### The Five Pillars (per `captains-cabinet-guide.md`)

1. **Dynamic Roles** — Officers are Markdown files, not code. Restructure the org in one message.
2. **Captain as Operator** — One async channel (Telegram) between human and organization.
3. **Memory That Compounds** — Three-tier memory: Tier 1 (always loaded), Tier 2 (working notes), Tier 3 (episodic/semantic via pgvector).
4. **Self-Improvement Loops** — Five nested loops (task, reflection, evolution, captain-pattern listener, captain-intent inference).
5. **Safety Boundaries** — Hard limits enforced programmatically via hooks, kill switch, Redis caps.

### Three-Layer Architecture (implemented in `cabinet/scripts/load-preset.sh`)

```
framework/          → universal base (ships with every fork)
presets/<active>/   → use-case config (work, personal, _template)
instance/           → this deployment's specifics (product.yml, platform.yml, tier2 memory)
```

At session start, `load-preset.sh` concatenates `framework/constitution-base.md` + `presets/work/constitution-addendum.md` → `/tmp/cabinet-runtime/constitution.md`. Officers read from the assembled runtime, not raw source files.

---

## 2. Constitution and Safety Governance

### File Structure

- `framework/constitution-base.md` — universal identity, work principles, comms protocol, quality standards
- `framework/safety-boundaries-base.md` — framework safety rules
- `presets/work/constitution-addendum.md` — work-preset-specific additions
- `presets/work/safety-addendum.md` — preset-level safety tightenings
- `constitution/CONSTITUTION.md`, `SAFETY_BOUNDARIES.md` — legacy files (still exist but runtime reads from `/tmp/cabinet-runtime/`)
- `constitution/ROLE_REGISTRY.md` — single source of truth for active Officers
- `constitution/KILLSWITCH.md` — kill switch protocol

### Governance Layering

The framework layer is genuinely universal: it defines identity (you are an Officer, not a chatbot), work principles (own your domain, ship working work, record everything), communication protocol (Telegram DM, Warroom group, Redis triggers), and quality standards.

Preset addendums can extend but never relax safety (explicitly enforced in `load-preset.sh`). Instance overlays customize further.

**Maturity: 4/5** — Three-layer assembly is complete and deployed. Load-preset.sh is the canonical assembler. The constitution/CONSTITUTION.md legacy split creates mild confusion but is documented.

---

## 3. Officer System

### Identity and Lifecycle

Each officer is defined by a Markdown file at `.claude/agents/<role>.md` (populated from `presets/work/agents/` by `load-preset.sh`, with optional `instance/agents/` overlays taking precedence). The current hired officers are: **CoS, CTO, CPO, CRO, COO** (all with YAML frontmatter including `name`, `description`, and `skills` list). Scaffolded but not hired: operations-officer, compliance-officer, executive-assistant.

YAML frontmatter in agent files (`.claude/agents/cos.md` line 1-8):
```yaml
---
name: cos
description: Coordinate Captain communication, mission compilation, org-runtime governance...
skills:
  - cabinet-task
  - org-status
  - mission-compile
  - ovi-publish
---
```

### Boot Sequence (`cabinet/scripts/start-officer.sh`)

1. Source `cabinet/.env` and active project env.
2. Run `load-preset.sh` (assembles runtime constitution, populates agents).
3. Resolve bot mode (single_ceo vs multi_officer) from project YAML or preset.
4. Write Telegram state `.env` for the officer (or blank it if Telegram-dark).
5. Create officer working directory with symlinks to all shared paths.
6. Launch `claude --model claude-opus-4-7 --dangerously-skip-permissions --effort max --channels plugin:telegram@claude-plugins-official --dangerously-load-development-channels server:redis-trigger-channel` in a tmux window.
7. Send a boot prompt via `officer_boot_drive` from `lib/officer-boot.sh`.

Mac-native variant (`start-officer-mac.sh`) does the same but targets LaunchAgent context, reads `.mcp.json.mac-native`, handles cua-driver MCP overlay for officers with `drives_computer` capability.

### Lifecycle Scripts

- `create-officer.sh` — scaffolds role file, tmux window, Telegram token, Redis expected-active marker
- `start-officer.sh` — boot with tmux + claude
- `start-all-officers.sh` — iterates all active officers
- `suspend-officer.sh` — structured exit, archives state, notifies team
- `resume-officer.sh` — restores from suspension
- `list-officers.sh` — shows status, type, calls, context %, idle time
- `officer-supervisor.sh` — watches heartbeat keys, auto-restarts fulltime officers

### Capability Routing (`cabinet/officer-capabilities.conf`)

Hook behavior is capability-driven, not officer-name-driven:
- `deploys_code` — fires auto-notify to validators on `git push main`
- `validates_deployments` — receives deploy alerts
- `reviews_implementations` — receives deploy alerts
- `reviews_specs` — receives spec creation notifications
- `reviews_research` — receives research brief notifications
- `logs_captain_decisions` — gets decision-logging enforcement prompt post-reply
- `telegram_bot` — officer gets Telegram plugin (Mac mode)
- `drives_computer` — officer gets cua-driver MCP overlay (Mac mode)

**Role as entity vs session:** Officers are persistent *sessions* (tmux + Claude Code `--continue` for session resumption) with *markdown identity files* as their charter. They are NOT typed entities with event ledger, eval history, or versioned role lineage. Identity is in a file; continuity is in Claude Code's session store.

**Maturity: 4/5.** Boot, lifecycle, and capability routing are mature. Missing: typed role entities with OVI-tracked eval history, formal role charter versioning, or mission compiler.

---

## 4. Communication Infrastructure

### Telegram (Captain ↔ Officer)

- Each officer has its own bot (multi_officer mode) or only the CoS/CEO officer has a bot (single_ceo mode, introduced in FW-084).
- Officers receive Captain DMs via the `--channels plugin:telegram@claude-plugins-official` flag.
- Outbound via `mcp__plugin_telegram_telegram__reply`.
- Voice messages via ElevenLabs TTS (`cabinet/scripts/send-voice.sh`), triggered by `post-reply-voice.sh` hook. Per-officer voice personalities are extensively configured in `instance/config/product.yml` with full naturalize prompts.
- Image generation via Google Gemini (`gemini-3.1-flash-image-preview`).

### Warroom Group (Officers → Captain)

- Broadcast-only newsfeed via `cabinet/scripts/send-to-group.sh` / `send-to-warroom.sh`.
- Officers post updates, briefings, alerts. Captain reads but doesn't command.

### Officer-to-Officer (Redis Streams)

- `notify-officer.sh` pushes to Redis Streams.
- `post-tool-use.sh` delivers pending triggers on every tool call via `lib/triggers.sh::trigger_read`.
- Auto-cleared on ACK via `trigger_ack`.
- Crash recovery: unACK'd messages persist on the stream.

### Scheduled Work (Cron → Redis → Officers)

- `cabinet/cron/briefing.sh` (07:00 + 19:00)
- `cabinet/cron/research-sweep.sh` (every 4h)
- `cabinet/cron/retro-trigger.sh` (event + 48h floor)
- `cabinet/cron/backlog-refine.sh`
- All cron scripts push Redis Stream messages → auto-delivered to target officer on next tool call.

**Key design principle:** No permanent `/loop` needed. Redis Trigger Channel delivers all recurring work. `/loop` is for ad-hoc temporary tasks only.

**Maturity: 5/5** — Communication infrastructure is the most mature component. Multi-channel (DM, group, Redis, voice), fault-tolerant (ACK model), capability-gated (single_ceo mode), and deeply integrated into hooks.

---

## 5. Memory and Knowledge System

### Three Tiers

| Tier | Location | Mechanism | Scope |
|------|----------|-----------|-------|
| Tier 1 | `CLAUDE.md` + `/tmp/cabinet-runtime/constitution.md` | Loaded every session | Universal always-loaded context |
| Tier 2 | `instance/memory/tier2/<officer>/` | Read at session start, write after significant work | Per-officer working notes |
| Tier 3 | Postgres `experience_records` + cabinet_memory pgvector | Retrieved on demand | Episodic, semantic search |

### Library (Cabinet-native structured knowledge)

- **Spaces** — top-level containers (Business Brain, Specs, Research, Decisions, Captain Patterns, Customer Success, Compliance, etc.)
- **Records** — typed, versioned, with Markdown content, JSONB schema fields, labels, pgvector embeddings
- **Wiki-links** — `[[Record Title]]` auto-resolves cross-record links
- **Backlinks** — automatic reverse reference tracking
- **Semantic search** — Voyage AI embeddings (voyage-4-large, 1024d) via `library.sql`
- **Graph view** — visual record relationship map in dashboard
- Schema at `cabinet/sql/library.sql`; starter Space templates in `cabinet/starter-spaces/`

### Captain Memory Triplet (shared interfaces)

- `shared/interfaces/captain-decisions.md` — append-only, every Captain decision + WHY
- `shared/interfaces/captain-patterns.md` — explicit standing behaviors (4th loop auto-encodes on 2nd occurrence)
- `shared/interfaces/captain-intents.md` — inferred latent goals (5th loop, proactive WHY-scan before every Captain-facing outbound)

### Cabinet Memory (Universal Semantic Search)

- pgvector-indexed over all Cabinet-produced text (logs, briefings, experience records, decisions)
- Query via `bash cabinet/scripts/search-memory.sh "<query>"`
- Research briefs embedded via `embed-research.sh` (Voyage AI embeddings, with decay tags: evergreen/fast-moving/time-sensitive)

**Maturity: 4/5** — Three-tier memory is built, Library is functional with pgvector, captain-triplet is well-designed. Gap: no automated Tier 2 → Tier 1 promotion pipeline (patterns go to `captain-patterns.md` but no mechanism to condense Tier 2 into CLAUDE.md automatically).

---

## 6. Mac-Native Infrastructure

### Status: Actively in progress, documented but partially deployed

The Mac-native migration is tracked as a 9-phase plan across specs 057-065:
- **Specs 057-065** in `shared/interfaces/product-specs/` define each phase
- **`docs/mac-mini-setup.md`** — consolidated runbook for Phase 1 (base macOS setup) + Phase 2 (native launchd)
- **`cabinet/launchd/`** — LaunchAgent plist templates for officers, heartbeat watchdog, cost-summary, worktree-listener
- **`cabinet/scripts/start-officer-mac.sh`** — Mac-native officer boot (LaunchAgent-aware, cua-driver MCP overlay, .mcp.json.mac-native)
- **`cabinet/scripts/reload-officer-mac.sh`** — reload a running officer via launchctl
- **`cabinet/scripts/deploy-mac.sh`** — substitute plist templates via `envsubst`, register LaunchAgents
- **`.mcp.json.mac-native`** — Mac-specific MCP config (localhost Redis, Mac-local paths)
- **`cabinet/scripts/worktree-listener.sh`** / `_worktree-listener-impl.py` — Postgres NOTIFY listener for PR-triggered officer sessions

### Key Mac-specific details

The LaunchAgent plist (`com.cabinet.officer.template.plist`) uses `KeepAlive: SuccessfulExit=false` + `ThrottleInterval=30` — restarts on any non-zero exit (non-crashes and crashes both restart). `SoftResourceLimits.NumberOfFiles=4096` (default 256 hits EMFILE under MCP load). Code-signing (Spec 058 Checkpoint 1.10) is required for TCC persistence across reboots — without it, Accessibility consent re-prompts after every restart.

### Services on Mac

- **Homebrew Redis** (AOF persistence, `appendonly yes`)
- **Postgres.app** (or Homebrew PostgreSQL 17)
- **tmux** for officer sessions
- **Tailscale** for remote access
- **Screenpipe** for context capture
- **apcupsd** for UPS monitoring
- **cua-driver** (Lead officer only, TCC code-signing gated)

**MacMini-readiness: 3/5** — Architecture is complete and documented. Phase 1 (base setup) and Phase 2 (launchd Cabinet) are spec'd. Open blockers: code-signing/notarization runbook is a stub; cua-driver end-to-end not yet validated; Phase 3-8 not yet executed (per specs 060-065).

---

## 7. Product Coupling

### Sensed-specific content

- `cabinet/env/sensed.env` — project-specific env vars (Telegram group chat ID, Neon connection, product repo path)
- `instance/config/product.yml` — generated by `assemble-config.sh` from `platform.yml` + `instance/config/projects/sensed.yml`, contains hardcoded Sensed Notion IDs, Linear workspace, Telegram bot names
- `Sensed/` directory at root (empty, placeholder)
- `shared/interfaces/` first-assignment files reference Sensed-specific work

### Decoupling mechanisms in place

- Three-layer separation (framework/preset/instance) means `framework/` and `presets/work/` are genuinely product-agnostic
- `cabinet/scripts/create-project.sh` and `switch-project.sh` for multi-project pool mode
- `instance/config/projects/*.yml` pattern for per-project config
- `cabinet/env/*.env` for per-project env
- Bootstrap script (`cabinet-bootstrap.sh`) takes `--preset work` and `--captain-name` as params

**Product-agnosticism: 4/5** — Very good. The only coupling visible is the auto-generated `instance/config/product.yml` still containing Sensed Notion IDs (not committed separately enough from the template).

---

## 8. Phase-1 Commercial Assets

The commercial layer is substantial and actively being built:

### Specs 050-056 (versioned in `shared/interfaces/product-specs/`)

| Spec | Content |
|------|---------|
| 050 | Commercial Cabinet Build Plan (refslund.ai) — two-tier: SaaS backend (Hetzner Docker) + Customer Mac (native) |
| 051 | LiteLLM proxy + virtual keys + daily cap |
| 052 | Customer audit log |
| 053 | Concierge install + customer onboarding |
| 054 | refslund.ai signup + Stripe + token billing |
| 055 | GDPR baseline + DPA + ROPA + DPIA |
| 056 | Customer dashboard MVP |

### Customer templates (`cabinet/customer-templates/`)

Full onboarding sequence: welcome-day-0, check-in-day-1, check-in-day-3, check-in-day-7, check-in-day-30, cheat-sheet-week-1, discovery-call-script, install-day-gdpr-walkthrough, offboarding-script.

### Concierge install runbook (`cabinet/runbooks/concierge-install-cabinet.md`)

4-hour Day-0 install procedure for first paying customers: hardware setup, container runtime, Cabinet bootstrap, officer-mix selection, Telegram provisioning, GDPR walkthrough. Status: SKELETON v0.1 — to be refined per first customer.

---

## 9. Linear → /tasks Cutover System

### What exists

- `cabinet/sql/038-officer-tasks.sql` — `officer_tasks` table with WIP≤3 enforcement via advisory lock, audit history trigger, blocked overlay
- `cabinet/sql/039-linear-to-tasks-schema.sql` — migration schema
- `cabinet/scripts/import-linear-to-library.sh` — ETL from Linear to Library
- `cabinet/scripts/migrate-notion-to-library.sh` — ETL from Notion to Library
- `cabinet/scripts/cutover/` — Python scripts: `linear-freeze.py`, `gh-freeze.py`, `delta-verify.py`, with full test suite

### Cutover status

The Linear cutover (Spec 039) was ratified and executed on 2026-04-26. Linear is now read-only archive. The canonical backlog is `officer_tasks` (Postgres). 560 Linear rows were migrated.

### /tasks design

- Per-(context_slug, officer_slug) WIP cap (currently 3, enforced at DB level with advisory lock to prevent race conditions)
- `due_at` with Redis-based auto-trigger delivery when deadlines arrive
- Context slugs for multi-project filtering
- Status: `queue` → `wip` → `done` / `blocked` (overlay, not status)
- Full audit history in `officer_task_history`

---

## 10. Hooks — Complete Map

All hooks live in `cabinet/scripts/hooks/`. They are configured in `.claude/settings.json`.

### `pre-tool-use.sh` (1510 lines — the most complex file)

1. **Kill switch check** — Redis `cabinet:killswitch` → exit 2 if active
2. **Daily spending limit check** — per-officer and cabinet-wide caps from `platform.yml` / `framework/defaults/spending-limits.yml`. CoS gets 3× multiplier. Telegram comms whitelist bypass with hourly sub-cap. Fail-open on config trouble.
3. **Prohibited actions** — `vercel deploy`, `DROP TABLE/DATABASE`, `TRUNCATE`, `DELETE FROM` blocked.
4. **Word-boundary prohibitions** — v3.7.2 of an extremely hardened regex engine blocking `sudo`, `docker`, `shutdown`, `reboot`, `rm -rf /` etc. across many bypass vectors (quoted-token splice, eval nesting, shell wrappers, env -S, heredoc bodies, full-path invocations). Documented bypass classes and regression history.

Additional hooks found beyond this core:
- `build-vs-buy-precheck.sh` — pre-decision check for build vs buy
- `captain-gate-language.sh`, `captain-posture-compliance.sh`, `captain-posture-warroom.sh`, `captain-reply-refine.sh`, `captain-rule-encoder.sh` — Captain communication quality gates
- `fp-analyze.sh` — false-positive analysis for hook testing
- `personal-work-parity.sh` — personal Cabinet parity check

### `post-tool-use.sh` (572 lines)

1. Heartbeat (Redis SET, 900s TTL)
2. Structured JSONL log to `memory/logs/YYYY-MM-DD.jsonl`
3. Activity string inference (Redis SET, 5-min TTL — drives dashboard Card 1)
4. Captain-attention queue scan (single_ceo mode only)
5. Trigger delivery from Redis Streams
6. Auto-notify deployment validators on `git push main`
7. Deploy verification reminder
8. Cross-validation: notify spec/research reviewers on file write
9. Experience record nudge (count-based, every 50 tool calls)
10. Captain decision logging enforcement (post-reply to Captain)
11. Idle detection (>30min warning with work checklist)
12. Proactive work injection (if no experience record in 2h)
13. Infrastructure review gate (before `git add` of critical files)

### `post-compact.sh`

Fires after context compaction. Injects essential skill refresh (officer-specific), pre-compaction state recovery from `.session-state.json`, mandatory reflection prompt (L1/L2/L3), trigger re-check, loop re-creation.

### `post-reply-voice.sh`

Generates ElevenLabs TTS voice message and sends it via Telegram after officer replies. Per-officer voice, naturalize prompt via Haiku, configurable mode (all/captain-dm/group/briefings).

### `post-file-write-memory.sh`, `post-reply-memory.sh`

Memory indexing hooks.

### `pre-captain-dm.sh`, `pre-compact.sh`, `stop-hook.sh`

Pre-DM quality check, pre-compact state snapshot, stop-hook for session snapshot at context window thresholds.

---

## 11. Dashboard

### Technology

Next.js 14/15 application in `cabinet/dashboard/`. TypeScript, Tailwind CSS, Vitest for tests, Docker deployment.

### Routes (product-agnostic)

- `/cabinets` — list and manage Cabinet instances
- `/costs` — cost tracking
- `/crons` — cron management
- `/governance` — kill switch, constitution viewer
- `/health` — officer health/heartbeat status
- `/integrations` — MCP and external service integrations
- `/library/[spaceId]/[recordId]` — Library space browser with record editor, wiki-links, schema fields
- `/library/graph` — visual record relationship graph
- `/tasks` (implied) — officer task backlog

### Consumer Mode (Spec 032)

Dashboard ships with a toggle between Consumer view (4-card natural-language status) and Advanced view (admin UI). Consumer is the default for first-time users; Advanced toggle is permanent once switched.

**Product-agnosticism:** The dashboard is fully framework-agnostic — it reads from Postgres (`library_spaces`, `library_records`, `officer_tasks`) and Redis (heartbeats, costs, activity strings). No hardcoded product names or Sensed-specific data.

**Maturity: 3/5** — Core Library browser and basic health/cost views exist. The dashboard is functional but missing /tasks board UI, OVI dashboard, and mission/work-graph views.

---

## 12. CI/CD

### GitHub Actions (`.github/workflows/cabinet-ci.yml`)

Comprehensive CI running on PR and push to master:
- Bash syntax check (`bash -n`) on hooks, lib, scripts root, subdirs
- ShellCheck at `--severity=error` on all script surfaces
- Shell unit tests: triggers, memory, backlog-drift, start-officer args (FW-073), post-tool-use JSONL (FW-075), cabinet-spawn (FW-080), cabinet-bootstrap (FW-082), create-project (FW-078), pre-push hook (FW-007)
- Python tests: ETL transforms, Gate 3 idempotency hash, cutover service accounts, MCP server, MCP host-tools, host-agent
- Dashboard typecheck (`tsc --noEmit`) and Vitest
- Golden evals (6 evals covering kill switch, constitution readonly, spending limits, experience records, officer coordination, briefings)
- Captain-rules retrieval eval + encode-pipeline eval
- Hook regression harnesses (FW-041 through FW-051)
- Framework backlog drift audit (advisory)

**Coverage maturity: 4/5** — Exceptionally thorough for a framework of this complexity. Shell scripts are tested, typed, shellchecked, and golden-eval'd. Missing: integration tests against a running officer session.

---

## 13. Self-Improvement Maturity

### Five Loops

1. **Task loop** — `record-experience.sh` after each task. Enforced via nudge in `post-tool-use.sh`.
2. **Reflection loop** — event-triggered (post-compact, post-milestone, CoS nudge). Written to `instance/memory/tier2/<officer>/reflections/`.
3. **Evolution loop** — 5 accumulated reflections OR 48h floor (Redis counter `cabinet:reflections:count`). CoS runs retro + skill promotion.
4. **Captain-pattern listener** (4th loop) — inline on every Captain DM. Two-count rule: auto-encode on second occurrence. Patterns at `shared/interfaces/captain-patterns.md`.
5. **Captain-intent inference** (5th loop) — pre-reply WHY scan. Intents at `shared/interfaces/captain-intents.md`.

### Skill Library

Foundation skills at `memory/skills/*.md` (YAML frontmatter, progressive disclosure). Evolved skills at `memory/skills/evolved/` (gitignored, never overwritten by upstream).

Foundation skills include: `holistic-thinking.md`, `production-quality-ownership.md`, `individual-reflection.md`, `cross-officer-retro.md`, `evolution-loop.md`, `deploy-and-verify.md`, `engineering-development-loop.md`, `agent-team-workflow.md`, `telegram-communication.md`, `research-quality-gate.md`, `spec-quality-gate.md`, `quality-pyramid.md`, `proactive-quality-audit.md`, `create-preset.md`, `cro-research-sweep.md`.

### Golden Evals

Six evals + expanding. `run-golden-evals.sh` runs them all; CI executes on every push.

**Self-improvement maturity: 4/5** — All five loops are designed and enforced via hooks. The mechanisms exist. Gap: no OVI (Outcome Value Index) or quantitative performance measurement. Improvement is qualitative (experience records, retros) rather than metric-driven.

---

## Scoring Summary

| Dimension | Score (1-5) | Rationale |
|-----------|-------------|-----------|
| **Maturity** | 4 | Production-quality codebase with CI, tests, hooks hardened over many adversary passes |
| **Product-agnosticism** | 4 | Framework/preset/instance separation solid; minor residual coupling in product.yml |
| **Self-improvement maturity** | 4 | Five loops designed and enforced; gap is quantitative outcome measurement (no OVI) |
| **Role-as-entity vs role-as-session** | 2 | Roles are session prompts (Markdown files). No typed entities, no eval history, no charter lineage |
| **Autonomy ceiling** | 3 | High autonomy within Telegram-driven workflows. Bottleneck: Captain must initiate most work; no mission compiler to decompose Captain goals autonomously |
| **MacMini-readiness** | 3 | Architecture complete and documented (Specs 057-065). Code-signing stub is the key open blocker |

---

## Top 5 Strengths

1. **Hooks infrastructure depth** (`cabinet/scripts/hooks/pre-tool-use.sh` at 1510 lines, `post-tool-use.sh` at 572 lines). Safety enforcement, spending limits, deploy gating, trigger delivery, cross-validation, and activity tracking are all woven into every tool call. The v3.7.2 prohibited-actions engine has been through multiple adversary passes and has documented bypass classes.

2. **Communication infrastructure completeness** — Multi-modal (text + voice + image), multi-channel (DM + group + Redis triggers), fault-tolerant (Redis Streams ACK model), capability-gated (single_ceo vs multi_officer), with ElevenLabs per-officer personalities. The Telegram integration is production-quality.

3. **Three-layer preset architecture** (`load-preset.sh` + `framework/` + `presets/` + `instance/`). The Phase 0 refactor succeeded: framework is genuinely universal, presets are use-case-specific, instance is deployment-specific. Any founder can fork and configure without touching framework or preset files.

4. **CI/CD rigor** (`.github/workflows/cabinet-ci.yml`). Shell syntax checks, ShellCheck at error severity, unit tests for all major scripts, Python tests, TypeScript typecheck, Vitest, golden evals, captain-rules evals, hook regression harnesses. Exceptional coverage for a framework of this complexity.

5. **Captain memory triplet + improvement loops** (`shared/interfaces/captain-decisions.md`, `captain-patterns.md`, `captain-intents.md`). The 4th and 5th improvement loops (pattern encoding + intent inference) are a genuinely novel design. Auto-encoding on second occurrence and pre-reply WHY scanning are enforced in CLAUDE.md and hooks.

---

## Top 5 Weaknesses

1. **No OVI or quantitative outcome measurement.** Self-improvement is entirely qualitative — experience records, retros, skill promotion. There is no numerical outcome value index, no performance metrics that accumulate over time, and no mechanism to prove the Cabinet is getting measurably better at anything. (`captains-cabinet-guide.md` mentions "evaluates its own performance against defined metrics" in the Evolution Loop spec but no metrics are defined anywhere in the codebase.)

2. **Role-as-session, not role-as-entity.** Officer identity lives in a Markdown file and a Claude Code session. There is no typed role object with charter versioning, eval history, past-decision lineage, or cumulative performance profile. If the CoS session crashes and restarts, the officer reads the same Markdown file — there's no persistent entity that accumulates a history distinct from the raw session files and Redis heartbeats.

3. **No mission compiler.** The Captain communicates strategy to the Cabinet via Telegram DMs. There is no system to decompose a high-level Captain goal into a structured work graph (mission → epics → tasks → assignments) automatically. The CoS skill list includes `mission-compile` in YAML frontmatter, but there is no implementation visible in this branch. This is the largest autonomy ceiling gap: the Cabinet cannot self-initiate work from a stated outcome.

4. **Product.yml is auto-generated and still Sensed-specific.** `instance/config/product.yml` (lines 1-8) self-describes as "AUTO-GENERATED" from sensed.yml. It contains hardcoded Sensed Notion IDs, the Sensed Linear team key, and Sensed Telegram bot names. This is conceptually correct (instance-level) but in practice a new founder forking the repo sees Sensed-specific content in what should be a blank template.

5. **Code-signing/notarization runbook is a stub** (`docs/mac-mini-setup.md` Checkpoint 1.10: "Full code-signing procedure tracked in a separate runbook — currently a stub pending the actual wrapper script work"). This is the key blocking item for persistent TCC permissions across Mac reboots, which is required for stable cua-driver and 24/7 unattended operation.

---

## Top 5 Gaps vs the Goal

1. **No durable role system.** The goal requires roles to be "persistent entities with charters/lineage/eval history." Current implementation: roles are Markdown files that define session behavior. No entity lifecycle, no evaluation trail, no charter versioning.

2. **No mission compiler.** The goal requires the Cabinet to "compile goals into missions/work graphs." Current implementation: Captain states goals in Telegram, officers interpret ad-hoc. The `mission-compile` skill is listed in officer YAML frontmatter but has no backing implementation.

3. **No OVI (Outcome Value Index).** The goal requires measurable outcome value. Nothing in this branch defines, tracks, or reports an OVI. Self-improvement is bounded by qualitative reflection loops.

4. **MacMini 24/7 readiness gap.** The goal requires fully autonomous 24/7 runtime. Current blockers: code-signing runbook is a stub (Checkpoint 1.10), Phase 3-8 of mac-native migration unexecuted (specs 060-065), cua-driver end-to-end validation pending.

5. **Event ledger absent.** The goal (and reportedly the rebuild branch) includes an event ledger as the substrate for durable org state. This branch has JSONL logs (`memory/logs/YYYY-MM-DD.jsonl`) and Redis state but no structured event ledger that the system introspects to drive its own behavior.

---

## Top 5 Opportunities (What This Branch Has That the Rebuild Might Lack)

1. **Battle-hardened hook infrastructure.** The `pre-tool-use.sh` v3.7.2 prohibited-actions engine and `post-tool-use.sh`'s 13-section behavior enforcement represent years of adversarial testing and real-world incident hardening. Any rebuild would need to recreate this from scratch.

2. **Full Telegram + voice + image communication stack.** Multi-modal, per-officer personality voice synthesis with ElevenLabs naturalize prompts, image generation via Gemini, single_ceo vs multi_officer bot modes, all wired into hooks. This is an extremely rich UX layer not easily rebuilt.

3. **Library knowledge system.** The pgvector-backed Library with wiki-links, backlinks, graph view, semantic search, versioned records, and 10 starter Space templates is a complete, working knowledge layer. The dashboard's `/library` route is functional.

4. **Commercial build plan + customer templates.** Specs 050-056, concierge install runbook, customer lifecycle templates (day 0/1/3/7/30), and the refslund.ai two-tier architecture decisions are valuable institutional knowledge that a pure framework rebuild wouldn't have.

5. **CI/CD and test infrastructure.** 300+ shell/Python/TypeScript/golden-eval tests, ShellCheck at error severity, hook regression harnesses, and the framework backlog drift auditor represent significant engineering investment that prevents regressions and makes the codebase safe to evolve.

---

## Key Files Inventory

| File | Purpose |
|------|---------|
| `/CLAUDE.md` | Root session context — loads every session, defines all behavioral rules |
| `/README.md` | Primary documentation and quick-start guide |
| `/captains-cabinet-guide.md` | Framework theory document — the mental model |
| `/cabinet-v2.md` | Captain directive for Phase 0-3 evolution (profiles, multi-context, federation) |
| `framework/constitution-base.md` | Universal constitution base |
| `framework/safety-boundaries-base.md` | Universal safety rules |
| `framework/defaults/spending-limits.yml` | Framework-default spending caps |
| `presets/work/preset.yml` | Work preset definition (officer archetypes, autonomy level, terminology) |
| `presets/work/agents/cos.md` | CoS preset role definition |
| `presets/work/agents/cto.md` | CTO preset role definition |
| `presets/work/constitution-addendum.md` | Work-preset constitution additions |
| `.claude/agents/cos.md` | Active CoS identity file (populated by load-preset.sh) |
| `instance/config/product.yml` | Active project config (auto-generated from platform.yml + sensed.yml) |
| `instance/config/platform.yml` | Platform config (timezone, voice, spending, communication prefs) |
| `instance/config/active-preset` | Which preset is active (currently: `work`) |
| `cabinet/scripts/load-preset.sh` | Three-layer assembly: framework + preset + instance → /tmp/cabinet-runtime/ |
| `cabinet/scripts/start-officer.sh` | Officer boot with tmux + Claude Code (Docker) |
| `cabinet/scripts/start-officer-mac.sh` | Officer boot for Mac-native LaunchAgent context |
| `cabinet/scripts/hooks/pre-tool-use.sh` | 1510-line safety gate: kill switch, spending limits, prohibited actions |
| `cabinet/scripts/hooks/post-tool-use.sh` | 572-line behavior enforcement: heartbeat, logs, triggers, deploy gating |
| `cabinet/scripts/hooks/post-compact.sh` | Post-compaction skill refresh and state recovery |
| `cabinet/scripts/hooks/post-reply-voice.sh` | ElevenLabs TTS voice message sender |
| `cabinet/scripts/notify-officer.sh` | Officer-to-officer Redis Stream push |
| `cabinet/scripts/lib/triggers.sh` | Redis Streams trigger read/ACK library |
| `cabinet/officer-capabilities.conf` | Capability-to-officer mapping for hook routing |
| `cabinet/scripts/create-officer.sh` | Officer provisioning |
| `cabinet/scripts/officer-supervisor.sh` | Officer liveness watchdog and auto-restart |
| `cabinet/sql/library.sql` | Library schema (library_spaces, library_records, pgvector) |
| `cabinet/sql/038-officer-tasks.sql` | officer_tasks table + WIP enforcement + history log |
| `cabinet/scripts/search-memory.sh` | pgvector semantic search over Cabinet memory |
| `cabinet/scripts/embed-research.sh` | Embed and store research briefs |
| `cabinet/dashboard/` | Next.js operator dashboard (Library, /tasks, health, costs, governance) |
| `cabinet/launchd/com.cabinet.officer.template.plist` | Mac LaunchAgent plist template |
| `cabinet/scripts/deploy-mac.sh` | Mac LaunchAgent deployment via envsubst |
| `cabinet/scripts/cabinet-bootstrap.sh` | Full Cabinet provisioning (Neon schemas, Library spaces, Redis state) |
| `cabinet/runbooks/concierge-install-cabinet.md` | Commercial customer install runbook |
| `shared/interfaces/captain-decisions.md` | Captain decision trail |
| `shared/interfaces/captain-patterns.md` | Captain standing behaviors (4th loop) |
| `shared/interfaces/captain-intents.md` | Inferred Captain latent goals (5th loop) |
| `memory/skills/holistic-thinking.md` | L1/L2/L3 improvement lens (all officers) |
| `memory/skills/production-quality-ownership.md` | 6-question craftsman checklist |
| `memory/golden-evals/` | 6 golden eval scenarios (CI-verified) |
| `.github/workflows/cabinet-ci.yml` | CI: bash syntax, ShellCheck, unit tests, Python tests, TS typecheck, golden evals |
| `shared/interfaces/product-specs/050-*.md` through `065-*.md` | Commercial build plan + Mac migration phase plans |
| `cabinet/customer-templates/` | Customer lifecycle templates (day 0/1/3/7/30 check-ins, offboarding) |
| `presets/personal/` | Personal Cabinet preset (placeholder, populated in Phase 2) |
| `cabinet/scripts/cutover/` | Linear → /tasks cutover tooling (freeze, delta-verify, tests) |
| `docs/mac-mini-setup.md` | Mac Mini Phase 1+2 consolidated setup runbook |
