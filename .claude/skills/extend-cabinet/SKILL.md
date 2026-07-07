---
name: extend-cabinet
description: How to extend THIS Cabinet — create a skill, MCP server, plugin, officer, or preset. Use when the Captain (or an officer) wants to add a new capability, asks "how do I create a skill/MCP/plugin", wants the cabinet to author its own tooling, or is building a custom Claude-native setup on top of the cabinet.
---

# Extending the Cabinet

The Cabinet is a Claude-native runtime. Everything in it — skills, MCP
servers, plugins, officers, presets — is extensible. There are two modes:
the cabinet extends **itself** (autonomous), and the Captain extends it
**on demand** (manual). Pick the path that matches what you're creating.

## 0. Every extension passes the validation gate (MANDATORY)

Every extension that binds into the cabinet — skill, MCP server, plugin,
channel/source adapter — ships a manifest at its root
(`manifest.yml|.yaml|.json`; schema
`framework/schemas/extension-manifest.schema.json`: name, version, kind,
action_types, risk_classes, undo_contract, axis_compat, entrypoints) and
MUST pass the axes-contract gate before anything loads it:

```
bash cabinet/scripts/validate-extension.sh <extension-dir>
```

Three checks, all fail-closed: manifest schema, entrypoint realpath
containment (traversal/symlink escapes refused), and the axis linter with
an EMPTY allowlist — extensions RECEIVE resolved axis values; they never
read `posture.yml`, the matrix, grants, or any other axis config themselves
(`.claude/rules/axes-contract.md` §2, spec
`docs/plans/cabinet-axes-spec-2026-07-05.md` §6.4). `install-extensions.sh`
runs this gate automatically for every declared extension with a local
`dir:` (or local-path plugin `source`) and SKIPS failures fail-closed,
filing a need. Run the gate yourself before declaring anything, and never
hand-wire an extension around it.

## 1. The cabinet writes its own skills (autonomous — already running)

This is the cabinet's Hermes-style learning loop. You usually don't invoke
it; it runs on its own:

- `framework/learning/skill_induction.py` clusters recurring patterns across
  officers' experience records and **drafts a new skill** to
  `memory/skills/evolved/`.
- The `evolution-loop` skill (CoS, every ~24h) validates each draft against
  scenario evals + golden eval shells. Passing drafts are **auto-promoted**
  with a `skill_promoted` event (`captain_auto_ratified=true`). Drafts with
  `<TODO:>` markers are held for Captain review.

To nudge it manually: `bash cabinet/cron/self-improvement-loop.sh` (add
`--dry-run` to see what it WOULD induce without writing).

## 2. Create a skill on demand (manual)

Two ways:

**Quick / hand-authored** — drop a file. A skill is just a markdown file
with frontmatter:
```
.claude/skills/<name>/SKILL.md     # name: + description: + body
```
Copy the shape from any existing one (e.g. `.claude/skills/org-status/`).
Auto-discovered by Claude Code the moment the file exists — no install step.
Cabinet foundation skills live in `memory/skills/`; the template is
`memory/skills/TEMPLATE.md`. Add a `manifest.yml` (kind: skill) beside the
SKILL.md and run the §0 gate on the skill dir before dropping it.

**Guided** — use the first-party `skill-creator` skill (ships with the
Anthropic skills plugin). It scaffolds, iterates, and can run evals on the
skill. Install it via the extensions mechanism (see §5) if it's not already
in your `/skills` list, then invoke it and describe what you want.

## 3. Create an MCP server on demand (manual)

Use the first-party `mcp-builder` skill (Python FastMCP or Node MCP SDK), or
`vercel-mcp-builder` for a hosted Streamable-HTTP server. Once built:

- Ship a `manifest.yml` (kind: mcp) at the server's root and pass the §0
  gate (`validate-extension.sh <server-dir>`); reference that dir via the
  entry's `dir:` key so the installer re-runs the gate on every apply.
- Declare it in `instance/config/extensions.yml` under `mcps:` →
  `bash cabinet/scripts/install-extensions.sh` renders it into
  `instance/config/extra-mcps.json`, which `start-officer-mac.sh` merges into
  every officer's `.mcp.json` at boot.
- Grant officers access: add `mcp__<name>` to an officer's `tools:` via an
  `instance/agents/<officer>.md` overlay (keeps the universal preset clean).

See `cabinet/docs/cabinet-extensions.md` for the full flow.

## 4. Create a plugin on demand (manual)

Use the first-party `create-cowork-plugin` skill to scaffold a plugin
(bundles skills + agents + hooks + MCP + commands). Publish it to a
marketplace (or keep it local), then declare it in
`instance/config/extensions.yml` under `plugins:` and run
`install-extensions.sh`. A local plugin (dev-path `source` or a `dir:` key)
must carry a manifest and pass the §0 gate — the installer refuses it
otherwise. The cabinet itself ships as a plugin
(`.claude-plugin/plugin.json`) — read it as a worked example.

## 5. Install the first-party creators (if not already present)

`skill-creator`, `mcp-builder`, and `create-cowork-plugin` are first-party
Anthropic skills. If they're not in your `/skills` list, add them like any
other extension — declare the owning plugin in
`instance/config/extensions.yml` (`plugins:` section), then
`bash cabinet/scripts/install-extensions.sh`. See the commented examples in
`instance/config/extensions.yml.example`.

## 6. Create an officer or a preset (cabinet-specific scaffolds)

- **New officer**: `bash cabinet/scripts/create-officer.sh <abbrev> <title>
  <domain> <bot-user> <bot-token>` — scaffolds role definition, memory, bot,
  log entries, supervisor wiring.
- **New preset** (a whole use-case bundle of officers + terminology +
  addenda): use the `create-preset` skill (`memory/skills/create-preset.md`).
  Presets live in `presets/<name>/`; the active one is in
  `instance/config/active-preset`.

## 7. The self-extension flows (self-proposal · account)

Two flows extend the cabinet's reach, both surfacing for the Captain's one-tap
approval — never self-granting. (Scope grants and credentials are hard
ceilings; day-to-day autonomy needs no earning — per the earn-demotion ruling,
captain-decisions 2026-07-03, reversible action classes are trusted from day
one with undo and DEMOTED on evidence. The rung-climbing trust ladder was
removed as the DEFAULT 2026-07-04 and survives only as the opt-in `earn_up`
posture's climb surface — rungs granted solely via `granted:` rows in the
Captain-locked trust-ladder.yml, never self-granted.)

- **MCP/plugin self-proposal** — once you've tested a new MCP/plugin,
  `framework.learning.self_proposal.prepare_mcp_proposal(...)` surfaces the
  exact `mcp-scope.yml` scope line + test evidence as a one-tap card. **The Captain
  applies the scope edit.** The Chair never self-edits `mcp-scope.yml`,
  germline, or the hook (hard line).
- **Account-creation flow** — `cabinet/scripts/prepare-account-flow.sh
  --service <name>` drives a signup to the credential boundary (recipe in
  `instance/config/account-flows.yml`) and surfaces "credential needed."
  Credential entry stays the Captain's. Depends on the Chair holding `claude-in-chrome`
  scope (itself a self-proposal away).

## The rule

Don't rebuild what's first-party (skill-creator / mcp-builder /
create-cowork-plugin). Don't hand-author what the cabinet can induce from
experience. Reserve manual authoring for net-new capability the cabinet
hasn't seen enough of to induce on its own — then feed it back so the
induction loop learns from it.
