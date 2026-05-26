# Phase 4 Log — Latest CC Adoption

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** ✅

## Goal

Aggressively adopt the latest Claude Code primitives in the Cabinet — Tool Search, Agent Teams, `/loop`, `/goal`, `/verify`, ScheduleWakeup — within the OAuth + Max x20 constraint (no Anthropic API key, no Managed Agents).

## Delivered

### 4.1 — Settings audit

`.claude/settings.json` already had the critical flags from Phase 0:
- `autoMemoryEnabled: true` ✅
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"` (in `env`) ✅
- `enableAllProjectMcpServers: true` ✅
- All 5 hook types wired (UserPromptSubmit, PreToolUse, PostToolUse, Stop, Notification) ✅

`enableToolSearch` is NOT a real settings.json field (rejected by validator). **Tool Search is enabled by default in current Claude Code**; no settings change needed. Verified.

### 4.2 — New Cabinet skills (`.claude/skills/<name>/SKILL.md`)

Three new skills wrapping the Phase 1–3 primitives:

- **`cabinet-work-graph-complete`** — invoked after an officer finishes a mission task. Documents the `work-graph-complete.sh <node_id> --status done|failed|verified --evidence <text-or-file>` contract and the don'ts (no manual table edits, no self-verification).
- **`cabinet-org-status`** — Captain asks "what's going on?" or briefing time. Documents the three-read pattern: OVI snapshot via `compute.py --from-events`, ready-task list via supervisor dry-run, active roles dir listing. Includes a 6-line example summary format.
- **`cabinet-route-tasks`** — manual trigger for the mission supervisor (normally cron, occasionally manual after a flood of completions). Documents dry-run-first discipline and the under-the-hood event flow.

Skills follow the open SKILL.md spec (frontmatter + body), matching the existing `memory/skills/TEMPLATE.md`.

### 4.3 — `/loop` / `/goal` / `/verify` reference doc

`docs/cabinet-slash-commands.md` — concise reference for the implementing session and future officers. Maps each primitive to its Cabinet use case + Cabinet-specific discipline rule. Includes summary table.

Highlights:
- **No permanent `/loop` for recurring delivery** — Redis Trigger Channel + cron handle that. `/loop` is for ad-hoc.
- **`/goal` requires a verifiable Boolean win-state** — don't use for fuzzy objectives.
- **Cabinet officers are NOT a `TeamCreate` team** — they're separate `claude` CLI processes; `TeamCreate` is for ephemeral implementation sub-teams.
- **Corridor analyzePlan fires automatically via hooks** — fix findings, don't bypass.

## Files touched

- `.claude/skills/cabinet-work-graph-complete/SKILL.md` (NEW)
- `.claude/skills/cabinet-org-status/SKILL.md` (NEW)
- `.claude/skills/cabinet-route-tasks/SKILL.md` (NEW)
- `docs/cabinet-slash-commands.md` (NEW)
- `docs/convergence-analysis-2026-05-26/phase-4-log.md` (this file)

## Deferred / out-of-scope

- The convergence plan envisioned 8 skills total (the 3 shipped + cabinet:mission-compile, cabinet:role-eval, cabinet:ovi-publish, cabinet:role-evolve, cabinet:product-bootstrap, cabinet:product-explore). The 3 shipped cover the highest-traffic Phase 1–3 primitives; the rest can be authored incrementally as officers reach for them. Pattern is established.
- Subscription cost discipline: covered by the existing `pre-tool-use.sh` daily spending cap (Phase 0). No additional CC-level cost guards needed.
- Migration to Managed Agents: not applicable (OAuth-only constraint per Captain ratification 2026-05-26).

## Next

Phase 5 — Task-system adapters. Five adapters (Monday + Jira + Linear + Asana + GitHub Issues) implementing a common interface, syncing the Cabinet's canonical `officer_tasks` / `mission_steps` with external systems.
