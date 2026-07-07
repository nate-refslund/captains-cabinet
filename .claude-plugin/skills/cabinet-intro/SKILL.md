---
name: cabinet-intro
description: Captain's Cabinet plugin orientation — what this plugin installs (officers, missions, OVI, durable role registry, three-layer framework) and where to find the operating context. Use when a fresh session needs to bootstrap into Cabinet mode, or when the user asks "what does this plugin do?", "how is the Cabinet organized?", or "where is the Constitution?".
---

# Captain's Cabinet — Plugin Orientation

You are operating inside a Claude Code session that has the **Captain's Cabinet** plugin installed. This plugin ships an autonomous, self-improving AI organization framework — Captain (the founder) plus officers (Chief of Staff, CTO, CPO, CRO, COO) with event-sourced missions, a durable role registry, OVI (Outcome Value Index) measurement, and a pattern-learning ledger.

## What the plugin contributes

- **Skills** (`.claude/skills/`): officer playbooks (engineering-development-loop, individual-reflection, cross-officer-retro, evolution-loop, agent-team-workflow, deploy-and-verify, holistic-thinking, production-quality-ownership, telegram-communication, spec-quality-gate), plus mission/org/OVI tooling (mission-compile, org-status, ovi-publish), task routing (cabinet-task, cabinet-route-tasks, cabinet-work-graph-complete).
- **Slash commands** (`.claude/commands/`): `/activate-project`, `/cabinet-briefing`, `/cabinet-retro`, `/cabinet-research-sweep`, `/cabinet-route-tasks`, `/cabinet-work-graph-complete`, `/cabinet-backup`, `/mission-compile`, `/org-status`, `/ovi-publish`, `/role-eval`.
- **Officer agents** (`presets/work/agents/`): five officer role definitions (CoS, CTO, CPO, CRO, COO) loaded as Claude Code subagents with frontmatter (`name`, `description`, `model`, `effort`, `maxTurns`).
- **MCP servers** (`.mcp.json`): the canonical Cabinet MCP set — Notion, Linear, Neon, Vercel, Cabinet (inter-Cabinet comms), Library (structured knowledge).

## Where the operating context lives

The plugin's CLAUDE.md file at the repository root is **not** auto-loaded into Claude Code session context (Claude Code intentionally does not load plugin-root CLAUDE.md). Officers bootstrap their context at session start by reading these files from the installed plugin directory:

1. `/tmp/cabinet-runtime/constitution.md` — assembled by `load-preset.sh` from `framework/constitution-base.md` + the active preset's `constitution-addendum.md` + `instance/`-specific overrides. **The operating principles.**
2. `/tmp/cabinet-runtime/safety-boundaries.md` — assembled the same way from safety addenda. **Hard limits, never violated.**
3. `constitution/ROLE_REGISTRY.md` — who does what.
4. `.claude/agents/<role>.md` (populated from active preset) — the officer's own role definition.
5. `instance/memory/tier2/<role>/` — the officer's working notes.
6. `instance/config/product.yml` — product-specific config (Notion IDs, Telegram bots, captain name).
7. `shared/interfaces/captain-decisions.md` — the Captain Decision Trail.
8. `memory/skills/holistic-thinking.md` — universal L1/L2/L3 improvement lens.
9. `memory/skills/production-quality-ownership.md` — the 6-question craftsman checklist.
10. `shared/interfaces/captain-patterns.md` — implicit Captain preferences + standing behaviors.
11. `shared/interfaces/captain-intents.md` — inferred latent goals (the 5th improvement loop).

## How to enter Cabinet mode

If you are a Captain starting a new session and want to operate inside the Cabinet:

```bash
# Pick or confirm the active preset (defaults to "work")
cat instance/config/active-preset

# Boot an officer (CoS, CTO, CPO, CRO, COO)
bash cabinet/scripts/start-officer.sh cos
```

The boot script runs `load-preset.sh` to assemble runtime artifacts, attaches the officer's MCP servers, loads their role definition, and starts a tmux-detached session that the supervisor restarts on crash.

## Three-layer architecture

| Layer | Path | Purpose |
| :---- | :--- | :------ |
| **Framework** | `framework/` | Universal base — constitution-base, safety-boundaries-base, schemas-base. Shared across all presets and deployments. |
| **Preset** | `presets/<active>/` | Use-case configuration (`work` for product orgs, `personal` for coaching). Adds agent archetypes, terminology, addenda, additional schemas. |
| **Instance** | `instance/` | This deployment's specifics — `instance/config/` (product.yml, platform.yml, active-preset), `instance/memory/tier2/` (officer working notes), `instance/agents/` (per-deployment overlays). |

`load-preset.sh` concatenates framework + preset + instance into `/tmp/cabinet-runtime/` at session start.

## Further reading

- Full Captain operating context: `CLAUDE.md` at the repo root. Read this file directly with the Read tool if you need the complete instructions — it is intentionally not auto-loaded by the plugin loader.
- Per-component reference: `cabinet/docs/cabinet-slash-commands.md`, `cabinet/docs/mac-mini-deploy-runbook.md`.
- Governance: `constitution/` directory.

For any Cabinet operation, defer to the assembled `/tmp/cabinet-runtime/` artifacts as the source of truth.
