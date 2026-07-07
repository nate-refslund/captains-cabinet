# agent-teams-pack

One skill, packaged as an optional Claude Code plugin:

- `agent-team-workflow` — when to use Agent Teams vs sub-agents vs the
  orchestrator; TeamCreate worker+reviewer patterns; worktree isolation;
  model routing for parallel implementation and adversarial review.

**Copied, not moved.** Parallel copy of the skill in `.claude/skills/`; the
core plugin still ships the original this wave. Requires
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in the environment (the Cabinet
sets it fleet-wide in `cabinet/.env`).

Install: `/plugin install agent-teams-pack@captains-cabinet-marketplace`, or
the governed path via `instance/config/extensions.yml` (see
`docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate: `bash cabinet/scripts/validate-extension.sh packs/agent-teams-pack`
(manifest: `manifest.yml`).
