# agent-teams-pack

One skill, packaged as an optional Claude Code plugin:

- `agent-team-workflow` — coordinating parallel teammates and subagents from
  an officer session on current CLI reality (≥ v2.1.178): `TeamCreate` is
  removed, teams are implicit, teammates spawn via the `Agent` tool's `name`
  param; worker+reviewer patterns, worktree isolation, model routing, and the
  headless boundary (Agent Teams don't work headless — unattended lanes use
  subagents/workflows).

**Copied, not moved.** Parallel copy of the skill in `.claude/skills/` (canonical
body: `memory/skills/agent-team-workflow.md`); the core plugin still ships the
original this wave. Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in the
environment (the Cabinet sets it fleet-wide in `cabinet/.env`); note that
`DISABLE_TELEMETRY` / `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` silently
disable Agent Teams.

Install: `/plugin install agent-teams-pack@captains-cabinet-marketplace`, or
the governed path via `instance/config/extensions.yml` (see
`cabinet/docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate: `bash cabinet/scripts/validate-extension.sh packs/agent-teams-pack`
(manifest: `manifest.yml`).
