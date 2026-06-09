# Captain's Cabinet

An autonomous AI organization that builds, ships, and improves your work — while you steer from Telegram.

## What This Is

The Captain's Cabinet is a framework for running a 24/7 AI development organization. You are the Captain. AI Officers own domains (product, engineering, research). They coordinate, execute, learn, and improve — continuously.

This repo is the **infrastructure**. It contains the organizational framework, memory system, safety boundaries, and Docker configuration. Your product repo is separate — the Cabinet mounts it as a workspace.

> ⚙ **Dashboard modes** — the Cabinet dashboard ships with a Consumer view (4 cards, natural-language status) as the default and an Advanced view for debugging and infrastructure config. Most user-facing docs in this repo (provisioning, hook tuning, preset authoring) assume Advanced mode. Toggle via the sidebar.

## How It Works

```
You (Captain)
  ↕ Telegram
Cabinet (this repo)
├── CoS — orchestration, briefings, self-improvement
├── CTO — engineering, code, deploys
├── CPO — product specs, backlog, prioritization
├── CRO — market research, competitive intel, trends
└── COO — operations, deployment validation, uptime
  ↕ reads/writes
Your Product Repo (mounted at /workspace/product)
```

Each Officer runs as a persistent Claude Code session with Telegram Channels. They read strategy from the **Library** (Cabinet-native structured knowledge), pick up work from **/tasks** (Cabinet-native task backlog), write code in your repo, and report back via Telegram. Notion and Linear remain as legacy adapters for teams that prefer them — configured in `instance/config/product.yml`.

Officer sets are fully configurable per deployment — add, remove, or rename Officers in `instance/config/platform.yml`. The framework is officer-agnostic.

## Quick Start

### 1. Fork This Repo

Click **Fork** on https://github.com/nate-step/captains-cabinet, then clone your fork:

```bash
git clone https://github.com/YOUR-GITHUB-USERNAME/captains-cabinet.git
cd captains-cabinet
```

### 2. Provision the Cabinet (Library + /tasks + state)

The cabinet-bootstrap script provisions a brand-new Cabinet end-to-end: runs the Neon SQL migrations (Library schema, `officer_tasks` table, Cabinet Memory), seeds the starter Library Spaces (Business Brain, Specs, Research, Decisions, Captain Patterns, Customer Success, Compliance, etc.), and registers the cabinet with its preset.

```bash
bash cabinet/scripts/cabinet-bootstrap.sh "YourProductName" --preset work --captain-name "YourName"
```

Re-runs are idempotent. Then add your strategy docs (vision, brand guidelines, etc.) as records in the Business Brain Space via the `/library` dashboard route.

**Optional: legacy Notion / Linear integration.** If your team already lives in Notion or Linear, run `bash cabinet/scripts/bootstrap-notion.sh "YourProductName"` and/or set the Linear workspace in `instance/config/product.yml`. Officers will read from those surfaces and migrate content into the Library over time via `migrate-notion-to-library.sh` and `import-linear-to-library.sh`.

### 3. Configure Your Product and Platform

Edit two config files:

- `instance/config/product.yml` — what you're building: product name, Neon project, voice settings, Telegram bots, optional Notion / Linear IDs if using legacy adapters
- `instance/config/platform.yml` — how the Cabinet operates: timezone, accountability tone, communication preferences, briefing cadence, officer set (fulltime vs consultant)

### 4. Set Up Telegram Bots

Create one bot per Officer via @BotFather (default set: CoS, CTO, CPO, CRO, COO — 5 bots) and a "YourProduct HQ" group. You can add or remove Officers later via `bash cabinet/scripts/create-officer.sh` and `cabinet/scripts/suspend-officer.sh`.

### 5. Fill In Credentials

```bash
cp cabinet/.env.example cabinet/.env
# Fill in all API keys and tokens
```

### 6. Deploy

```bash
# On your server (Hetzner/DO/AWS, Ubuntu 24.04)
# Clone into the location you want — we use /opt/cabinet as an example
cd /opt/cabinet/cabinet
docker compose build
docker compose up -d postgres redis
docker compose up -d officers watchdog
```

### 7. Start Your First Officer

```bash
docker exec -it cabinet-officers bash
./start-officer.sh cos
# Authenticate with claude /login (one-time)
# Pair Telegram bot
# Send: "Read the Constitution and report for duty"
```

## Architecture

| Component | Purpose |
|-----------|---------|
| **Officers** | Persistent Claude Code CLI sessions in tmux, one per domain |
| **Crew** | Agent Teams spawned by Officers for parallel execution |
| **Library** (default) | Cabinet-native structured knowledge — user-defined **Spaces** (Business Brain, Specs, Decisions, Research, Customer Success, etc.) containing typed **records**. Semantic search via pgvector, `[[wiki-links]]` between records, automatic backlinks, graph view. Accessed via the `/library` dashboard route or the `library` MCP server. **Canonical business-brain since 2026-04-26.** |
| **/tasks** (default) | Cabinet-native task backlog — Postgres `officer_tasks` table. Officer assignment, WIP=1 per officer (enforced), `due_at` timestamps with auto-triggers to the assigned officer when due, status (todo / in_progress / blocked / done). Accessed via the `/tasks` dashboard route or direct Postgres queries. **Canonical backlog since 2026-04-26.** |
| **Neon (Cabinet Memory)** | Universal semantic search over all Cabinet-produced text (logs, briefings, experience records, decisions). Query via `bash cabinet/scripts/search-memory.sh "<query>"`. |
| **Notion** (legacy adapter) | Optional business-brain integration for teams already using Notion. Configured in `instance/config/product.yml`. Treated as read-only archive post-Library cutover. |
| **Linear** (legacy adapter) | Optional task backlog for teams already using Linear. Configured in `instance/config/product.yml`. Treated as read-only archive post-/tasks cutover. |
| **Redis** | Kill switch, rate limits, state flags, officer-to-officer triggers |
| **Watchdog** | Health checks, cost tracking, cron triggers, alerts |
| **Telegram** | Captain's command interface |

### Library — how it works

The Library is the Cabinet's structured knowledge store. Think of it as a typed database with the UX of Notion but native to the Cabinet stack.

- **Spaces** are top-level containers. The framework ships starter Spaces (Business Brain, Specs, Research, Decisions, Captain Patterns, Customer Success, Compliance, etc.) and you create your own.
- **Records** live inside Spaces with structured fields (title, body, status, owner, tags) plus free-form Markdown content.
- **Wiki-links** — write `[[Onboarding Spec]]` or `[[Decision: Pricing Tiers]]` in any record body and the Library auto-resolves the link to the target record.
- **Backlinks** — every record shows which other records link to it, automatically.
- **Semantic search** — pgvector (Voyage AI embeddings) lets officers ask "where did we decide X" or "what specs touch the audit log" and get relevant records ranked by meaning, not keywords.
- **Graph view** — visual map of records and their wiki-link relationships. Useful for spotting orphaned records or clusters.
- **Access** — officers query via the `library` MCP server (read-anywhere, write-into-their-Space); operators view + edit via the `/library` dashboard route.

### /tasks — how it works

`/tasks` is the Cabinet's task backlog, replacing Linear for teams that don't already have it.

- **Officer assignment** — every task has exactly one assigned officer (CoS, CTO, CPO, etc.). The officer owns the work.
- **WIP=1 enforced** — each officer has at most one task `in_progress` at any time. Forces sequential execution per officer, prevents multitasking degradation.
- **Status** — `todo` → `in_progress` → `done` (plus `blocked` for waiting-on-input). Officers move their own tasks through states.
- **Due dates** — `due_at` timestamps trigger an auto-DM to the assigned officer when the deadline arrives. No forgotten work.
- **Context slugs** — tasks tag which project/cabinet they belong to (e.g., `sensed`, `cabinet-framework`, `personal-cabinet`). Filters the dashboard view per context.
- **Access** — officers query their work via `cabinet/scripts/my-tasks.sh` or direct Postgres `officer_tasks` queries; operators view + manage via the `/tasks` dashboard route.

Both surfaces ship as part of the framework — no external SaaS dependency.

## The Five Pillars

1. **Dynamic Roles** — Officers are markdown files, not code. Restructure the org in one message.
2. **The Operator as Captain** — You set direction, the Cabinet figures out how. Works for founders, employees, team leads, solo operators — anyone running a system that benefits from always-on AI delegation.
3. **Memory That Compounds** — Three tiers: always-loaded constitution, working notes, episodic recall. Plus the **Library** for structured knowledge and Cabinet Memory for universal semantic search.
4. **Self-Improvement Loops** — Five nested loops:
   - **Task** — per-task experience records.
   - **Reflection** — event-triggered (after compaction or completion milestones).
   - **Evolution** — cross-officer retro every 5 reflections or 48h, whichever first.
   - **Captain-pattern listener** (4th loop, inline) — every officer scans Captain DMs for meta-signals ("we should always X", "let's track Y so we don't forget") and offers to encode as standing behavior; auto-encodes on the second occurrence. Patterns persist in `shared/interfaces/captain-patterns.md` and are loaded at every session start.
   - **Captain-intent inference** (5th loop, proactive) — every officer hypothesizes the Captain's latent WHY before composing any Captain-facing outbound and shapes the reply around the WHY, not just the surface WHAT. Inferred intents persist in `shared/interfaces/captain-intents.md`.

   Foundation skills ship with the repo (`memory/skills/*.md` with YAML frontmatter per the open SKILL.md spec) and improve over time via evolved overlays (`memory/skills/evolved/`).
5. **Safety Boundaries** — Hard limits enforced by hooks and Redis. Read-only constitution. Kill switch.

## Presets — adapting the Cabinet to different use cases

Captain's Cabinet is preset-aware. The framework is universal; a **preset** adapts it to a specific use case without forking.

Shipped presets:

- **`work`** (default) — product-team shape. CoS + CTO + CPO + CRO + COO as officers. **/tasks** backlog + **Library** business brain as defaults; Linear and Notion available as legacy adapters. Product repo mounted as workspace. Default for anyone building and shipping something.
- **`personal`** — coaching-shape practice. 4 coaches (Physical, Mindfulness, Spiritual, Financial) + Personal Assistant orchestrator. Configured for personal-life domains rather than product work; separate Telegram bots + Library Spaces + Postgres-backed `/tasks`. Captain runs a Personal Cabinet alongside a Work Cabinet for full-life coverage.
- **`_template`** — skeleton for creating a new preset. See `memory/skills/create-preset.md` for the full workflow.

A preset defines:
- Which agent archetypes pre-scaffold
- Terminology defaults (e.g. "officer" vs "coach")
- Constitution addendum (on top of framework base)
- Safety addendum (can only tighten, never relax the framework base)
- Additional database schema (additive only, never drop framework tables)
- Default autonomy level and hook defaults

At container start, `cabinet/scripts/load-preset.sh` reads `instance/config/active-preset` (default `work`) and assembles the runtime Cabinet state at `/tmp/cabinet-runtime/` — Officers read from there. Three layers overlay cleanly: `framework/` → `presets/<active>/` → `instance/`.

You can use a shipped preset, customize via `instance/agents/` overlays, or create your own. See `presets/README.md` and `framework/README.md` for detail.

## Repo Structure

```
captains-cabinet/
├── framework/               # Universal Cabinet base (ships with every deployment)
│   ├── constitution-base.md     # Universal Constitution — identity, principles, comms
│   ├── safety-boundaries-base.md # Universal safety rules — approvals, limits, kill switch
│   ├── schemas-base.sql         # Framework schema pointers (see cabinet/sql/ for actual files)
│   └── README.md
├── presets/                 # Use-case configurations (work, personal, custom)
│   ├── work/                    # Default preset: product-team shape (CoS/CTO/CPO/CRO/COO)
│   ├── personal/                # Coaching-shape preset (4 coaches + Personal Assistant orchestrator)
│   ├── _template/               # Skeleton for creating a new preset
│   └── README.md
├── instance/                # This deployment's specifics
│   ├── config/                  # product.yml + platform.yml + active-preset
│   ├── memory/tier2/            # Officer working notes (per-role)
│   └── agents/                  # Per-deployment agent overlays (optional; loaded last)
├── cabinet/
│   ├── scripts/             # Cabinet tooling: hooks, supervisor, load-preset.sh, cabinet-bootstrap.sh, search-memory.sh, my-tasks.sh, etc.
│   ├── sql/                 # Schema files: cabinet_memory.sql, library.sql
│   ├── cron/                # Scheduled triggers (briefings, research sweeps, retro)
│   ├── channels/            # MCP plugins (redis-trigger-channel, library-mcp)
│   ├── starter-spaces/      # JSON templates for Library Spaces (10 shipped)
│   ├── dashboard/           # Next.js operator dashboard
│   └── Dockerfile.officer   # Per-officer container image
├── .claude/agents/          # Derived: populated by load-preset.sh from presets/ + instance/agents/ overlays (gitignored)
├── constitution/            # Legacy constitution files; runtime reads from /tmp/cabinet-runtime/ populated by load-preset.sh
├── memory/
│   ├── skills/              # Foundation + promoted skills (procedures, quality gates)
│   ├── golden-evals/        # Validation scenarios for Cabinet changes
│   └── tier3/               # Experience records, decision log, research archive
├── shared/                  # Inter-Officer interfaces (specs, decisions, tech radar)
├── CLAUDE.md                # Root context loaded every session
└── captains-cabinet-guide.md # The theory document
```

## Customization

Everything is configured in `instance/config/product.yml` and `cabinet/.env`. Key options:

### Model Routing — Fable orchestrator + Sonnet subagents

Officers run as **Fable 5** (`claude-fable-5`) with `--effort max` by default (set via `--model` in `cabinet/scripts/start-officer.sh`). They drive the loop: read tasks, coordinate, execute, reply to the Captain, route work. Parallel subagent and Agent-Team (crew) work runs on **Sonnet 4.6** for cost-efficiency on execution that doesn't need orchestrator judgment.

For deep sub-problems an officer consults Fable explicitly:

- `bash cabinet/scripts/advisor-crew.sh --task "..." --context <file>` — one-shot synthesized consultation (Fable 5 advisor + Sonnet 4.6 executor).
- `Task(model="fable", prompt="...")` — independent Fable subagent with its own context, used for adversarial reviews, fresh-context audits, or multi-step subloops.

Rollback: `CABINET_MODEL=claude-sonnet-4-6 bash cabinet/scripts/start-officer.sh <officer>` downgrades one officer to Sonnet; flip the default in `start-officer.sh` for fleet-wide rollback.

### Captain decisions, patterns, intents — the institutional-memory triplet

Three shared interfaces persist what the Captain has said and what officers have inferred:

- `shared/interfaces/captain-decisions.md` — append-only log of every Captain decision with the WHY. Officers must check this before any design / feature / UI work. The receiving officer logs decisions in real-time.
- `shared/interfaces/captain-patterns.md` — explicit standing behaviors from Captain feedback. Auto-encoded on second occurrence per the 4th loop. Officers re-read on every Captain DM.
- `shared/interfaces/captain-intents.md` — inferred latent goals (5th loop). Officers hypothesize the WHY behind every Captain-facing outbound and shape replies around it.

Together these three files mean officers don't re-litigate decisions, don't re-ask Captain things he's already answered, and shape their work around the latent goals Captain hasn't explicitly stated.

### Host access (CoS-only)

The Coordinating Officer (CoS) has scoped host-machine access via a privileged `host-agent` running as a separate systemd service. Six tools available: `run`, `rebuild_service`, `restart_officer`, `tail_logs`, `edit_file`, `read_file`. Auth via `SO_PEERCRED` on a Unix socket at `/run/cabinet/host-agent.sock`; CoS UID-pinned at 60001. Every action audited to `/var/log/cabinet/cos-actions.jsonl`. Kill-switch via `/run/cabinet/host-agent.paused` halts immediately.

This lets the CoS rebuild Docker services, restart officers, tail container logs, and patch host-side scripts without round-tripping every action through the Captain. Other officers do NOT have host access — they propose changes through the CoS.

### Tech Radar

`shared/interfaces/tech-radar.md` — living document tracking tools the Cabinet is watching, evaluating, trialling, or has rejected (with reasons). Research Officer maintains it; the CoS reviews entries in cross-officer retros to surface adoption opportunities.

### Voice Messages (optional)
Officers can send voice messages alongside text via ElevenLabs TTS. Each officer has their own voice.

```yaml
# instance/config/product.yml
voice:
  enabled: true                  # false by default
  model: eleven_flash_v2_5       # fastest model
  mode: all                      # all | captain-dm | group | briefings
  voices:
    cos: "7ceZgj78jCCeAW93ItNk" # override with your own voice_ids
    cto: "AMNzDFTtLuyoKAL3YPnu"
    cpo: "sgk995upfe3tYLvoGcBN"
    cro: "77aEIu0qStu8Jwv1EdhX"
    coo: "YOUR_COO_VOICE_ID"
```

Browse voices at [elevenlabs.io/voice-library](https://elevenlabs.io/voice-library) or via API. Requires `ELEVENLABS_API_KEY` in `.env`.

### Image Generation (optional)
Officers can generate images via Google Gemini (Nano Banana 2) and send them through Telegram. Requires `GOOGLE_API_KEY` in `.env`.

### Improvement Cadences
Default cadences in `CLAUDE.md`:
- **Individual reflection:** event-triggered (after compaction or completion milestones — don't reflect on nothing).
- **Cross-officer retro:** event-triggered (fires at 5 accumulated reflections or 48h since last — whichever first).
- **Evolution loop:** runs alongside retro (Phase 1 retro, Phase 2 skill promotion).
- **Captain-pattern listener (4th loop):** inline on every Captain DM. No cadence — fires on signal.
- **Captain-intent inference (5th loop):** pre-reply WHY scan on every Captain-facing outbound. No cadence — fires on every reply.

### Foundation Skills
Ship with the repo in `memory/skills/` following the open **SKILL.md spec** (YAML frontmatter for discovery + progressive disclosure: `name` + `description` load at session start, full body loads only when a task matches the description trigger). Officers follow these as baseline procedures. The learning loop can improve them by writing evolved versions to `memory/skills/evolved/` — foundation files are never modified directly, evolved versions take precedence.

### Cabinet operating speed (no calendar months)
The Cabinet operates at AI speed, not human team speed. When planning milestones, sequence by **dependencies and validation gates**, not calendar time. Real human-speed bottlenecks: Captain decisions, real-world user feedback. Everything else ships in minutes to hours. Document phases as "after launch + N active users with N+ signals" — not "3-6 months."

### What to Customize After Forking
1. `instance/config/product.yml` — your product name, Telegram bots, voice settings, optional Notion/Linear IDs if you use the legacy adapters
2. `instance/config/platform.yml` — your timezone, accountability tone, briefing cadence, officer set (fulltime vs consultant)
3. `cabinet/.env` — all API keys and tokens (copy from `cabinet/.env.example`)
4. `cabinet/officer-capabilities.conf` — map your officers to capabilities (deploys_code, reviews_specs, etc.)
5. `cabinet/starter-spaces/` — Library Space templates (Business Brain, Specs, Research, Decisions, etc.) seeded on first run; edit to match your domain
6. `.claude/agents/*.md` — officer identity if you add domain-specific context (optional)

## Requirements

- **Server:** Ubuntu 24.04 with Docker (Hetzner CPX31 recommended)
- **Claude:** Max 20x subscription ($200/mo) for 4–5 Officers
- **Neon:** PostgreSQL + pgvector account (powers Library, /tasks, and Memory)
- **Notion:** Business plan — optional (only if you use the legacy business-brain adapter)
- **Telegram:** One bot token per Officer (default 5) + group chat
- **APIs (required):** Neon (Postgres + pgvector — powers Library, /tasks, Memory), Voyage AI (embeddings), Perplexity, Brave Search, Exa
- **APIs (optional):** Notion (legacy business-brain adapter), Linear (legacy task adapter), ElevenLabs (voice messages), Google Gemini (image generation)

## Safety

- Kill switch halts all operations instantly via Telegram or Redis
- Constitution and safety boundaries are read-only mounts
- Pre-tool-use hooks block prohibited actions programmatically
- Spending caps enforced per-session, per-day, per-month via Redis
- Permission inheritance: Crew never exceed Officer boundaries
- Escalation chain: Crew → Officer → CoS → Captain

## License

**Business Source License 1.1** (see [`LICENSE`](./LICENSE))

Free to fork, self-host, modify, and use internally. Commercial hosted/managed offerings competing with the Licensor's paid service are reserved to the Licensor until the Change Date (4 years after each version's publication), at which point that version converts to Apache 2.0.

Short version: if you're a team running the Cabinet for your own organization — whether as a founder, an employee, a solo operator, or anything in between — go ahead. If you want to sell a hosted Cabinet-as-a-Service to third parties, reach out.

**Naming.** The open-source framework you're reading about is **Captain's Cabinet**. A commercial product built on top of this framework — currently in development under refslund.ai — uses the shorter **Cabinet** name. The two are intentionally distinct: this repo (Captain's Cabinet) is the framework you fork and run yourself; **Cabinet** is the commercial productization (installer, billing, customer dashboard, support). Both exist; only this repo is open-source.

See `captains-cabinet-guide.md` for the full framework theory.
