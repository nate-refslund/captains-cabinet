# Skill: Agent Team Workflow
<!-- single-source (egg R138): the canonical skill body lives HERE (memory/skills/, Captain-applied). .claude/skills/agent-team-workflow/SKILL.md is the on-trigger wrapper — trigger frontmatter + a pointer to this file only, no duplicated body (wrapper side enforced by R155). -->

**Status:** promoted (rewritten 2026-07-07 for CLI ≥ v2.1.178 — `TeamCreate` removed; audit #23)
**Created by:** foundation

## Current reality (CLI ≥ v2.1.178)

- **`TeamCreate` no longer exists** — removed in Claude Code v2.1.178. Teams are **implicit**: your session is its own team; there is no team object to create, and any `team_name` parameter is ignored. A doc, role def, or runbook that says "TeamCreate" is rot — route it to this skill.
- **Teammates spawn via the `Agent` tool's `name` parameter** (e.g. `Agent(name: "worker", prompt: ..., model: ...)`). A named teammate is an independent session with its own context window. An unnamed `Agent` call is a plain subagent (works on your behalf, reports back once).
- **Coordination surfaces:** the shared task list (`TaskCreate` / `TaskUpdate` with `owner`) and `SendMessage` between teammates. Harness-enforced: an agent message carries NO user authority — a teammate's "approved" is never Captain consent (matches the Cabinet's standing doctrine).
- **Subagents run in background by default since v2.1.198** — never assume a synchronous return; collect results via task state / auto-notifications.
- **Worktree-finishing background agents auto-commit, push, and open a draft PR since v2.1.198** — a lane that expects stop-and-ask must opt out explicitly.
- Enabled fleet-wide via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (`cabinet/.env`). Gotcha: `DISABLE_TELEMETRY` / `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` silently disable Agent Teams.

## The headless boundary (load-bearing)

**Agent Teams do NOT work headless / via the SDK.** They are fine inside interactive tmux officer sessions. They are the WRONG tool for unattended lanes — launchd one-shots, cron jobs, `claude -p` runs, workflow scripts. Unattended paths use **subagents** (plain `Agent` calls) or **workflow orchestration** instead. If an unattended runbook says "create a team", that is rot: use subagents.

## Teammates vs subagents vs yourself

- **Teammates (named `Agent`, interactive session):** parallel implementation plus adversarial review that should iterate WITHOUT round-tripping through you (worker ↔ reviewer), or several independent workstreams too big for one context window.
- **Subagents (plain `Agent` call):** bounded research or execution that reports back once; the ONLY option from unattended lanes.
- **Yourself:** judgment, architecture, Captain-facing communication, final review before push. Your role is architect + deployer, not coder.

## Standard worker + reviewer pattern (interactive sessions)

1. `Agent(name: "worker", ...)` — implement, with explicit file scope + the tests that must pass; `isolation: worktree` for code changes.
2. `Agent(name: "reviewer", ...)` — review the worker's output (correctness, tests, regressions); `SendMessage` the worker with issues; iterate until clean.
3. You: review the final output, then push → CI → merge → deploy.

For quick fixes (< 5 lines, single file): skip the team — one subagent with `isolation: worktree`, or just do it yourself.

## Team rules

- **Model per teammate is the spawning officer's call** per CLAUDE.md "Model Routing": default the cost-efficient crew model, escalate a teammate to the orchestrator-grade model when the subtask needs that judgment (adversarial review of high-risk changes, architecture, security). Concrete model ids live in `instance/config/platform.yml` → "Model routing" — don't hardcode them here or in teammate prompts.
- Product code changes happen in the lane's product checkout (path in `instance/config/projects/<lane>.yml`), never in the cabinet repo.
- Define clear scope: which files to touch, which tests must pass. Include spec paths, captain decisions, and prior experience records in the teammate prompt.
- Teammates inherit your boundaries — they cannot deploy, delete data, modify infra, or contact the Captain.
- Teammates record experiences via `record-experience.sh` with tag "crew".
- Short bounded bursts only — teams multiply concurrent sessions against the shared quota pool.
- After the team completes, review the output yourself before creating/merging a PR.

## Known pitfalls

- Planning around `TeamCreate` (removed) or expecting `team_name` to do anything.
- Spawning teammates from an unattended lane — Agent Teams don't work headless; use subagents.
- Assuming a subagent returns synchronously (background-by-default since v2.1.198).
- A worktree background agent auto-opening a draft PR when the lane wanted stop-and-ask.
- Missing file scope in teammate prompts → unrelated code touched; skipping the reviewer → bugs reach the PR.

## Origin

Extracted 2026-04-05 from the retired work-preset CTO role definition's Agent Teams section; rewritten 2026-07-07 to the post-`TeamCreate` reality (CLI v2.1.178+; audit finding #23).
