# Installing extensions (plugins, MCPs, skills)

The Captain's Cabinet is a **universal** product. Out of the box it installs
**no** third-party extensions — it ships only its own framework + the curated
core MCP set. Any Captain can add **any** Claude Code plugin, MCP server, or
skill, exactly like Claude Desktop / Claude Code — the cabinet just makes
your choices **declarative + idempotent** so a fresh clone (or a new Mac
mini) re-applies them.

## TL;DR

```bash
cp instance/config/extensions.yml.example instance/config/extensions.yml
$EDITOR instance/config/extensions.yml          # uncomment / add what you want
bash cabinet/scripts/install-extensions.sh      # idempotent; re-run anytime
```

`setup-mac.sh` runs this automatically as Step 13. Your real `extensions.yml`
is gitignored (deployment-specific); the `.example` template stays tracked.

## The three kinds

| Kind | How it installs | Where it's declared |
|---|---|---|
| **Plugin** (skills + agents + hooks + MCP + commands bundled) | `claude plugin marketplace add` + `claude plugin install` (user-level — covers all 5 officers) | `plugins:` in extensions.yml |
| **MCP server** (standalone) | rendered into `instance/config/extra-mcps.json`, deep-merged into every officer's `.mcp.json` at boot | `mcps:` in extensions.yml |
| **Skill** (single `SKILL.md`) | drop a file at `.claude/skills/<name>/SKILL.md` — auto-discovered, no installer; or it comes bundled in a plugin | file-drop, or `plugins:` |

## Granting officers access to what you installed

Officer tool access is scoped per-officer in `presets/work/agents/<officer>.md`
(`tools:` frontmatter). The universal preset lists only the core tools every
"work" cabinet has. To give an officer a newly-installed plugin/MCP tool
**without editing the universal preset**, drop a deployment overlay:

```
instance/agents/<officer>.md     # extended `tools:` list; merged over preset
```

`sync-agents.sh` applies `instance/agents/*.md` at highest precedence, so your
deployment grants exactly what it needs while the shipped preset stays clean.

For an extra MCP server (declared in `mcps:`), it's added to every officer's
`.mcp.json` automatically — but the officer still needs the matching
`mcp__<name>` entry in its `tools:` allowlist to call it. Same overlay
mechanism.

## Worked example — an org-internal workflow plugin

Say your org has an internal `dev-flow` plugin (a Monday.com + GitHub +
Vercel workflow bundle: MCP tools, skills like `/dev-flow:pickup-task` +
`/dev-flow:ship-pr`, subagents, hooks). Org-internal plugins typically need
`gh` auth with org membership plus their own API tokens, and may hard-fail
on repos outside the org by design — it's **not** shipped by default; only
enable one if it's YOUR stack. A Captain enables it:

1. `instance/config/extensions.yml` (the shipped
   `extensions.yml.example` carries this exact commented shape):
   ```yaml
   plugins:
     - name: dev-flow
       marketplace: dev-flow-marketplace
       source: <your-org>/dev-flow
       required_env: [MONDAY_API_TOKEN]
       optional: false
   ```
2. `MONDAY_API_TOKEN` in `cabinet/.env` (the secrets wizard prompts for it).
3. Any project config the plugin documents (e.g.
   `cp .claude/project-config.json.template .claude/project-config.json` and
   fill the product ids).
4. Grant officers: e.g. `instance/agents/cto.md` with
   `tools: …, mcp__plugin_dev-flow_dev-flow`.
5. `bash cabinet/scripts/install-extensions.sh` → installs + verifies.

The cabinet's own `task_adapters/monday.py` was removed in favor of exactly
this kind of plugin — for Monday users, a maintained org plugin is strictly
better than a homegrown adapter.

## Creating your own (skills, MCPs, plugins, officers, presets)

You don't have to consume only what exists — the Cabinet is built to be
extended by you. The `extend-cabinet` skill (`/extend-cabinet`, shipped in
`.claude/skills/`) is the full router; the short version:

| Create a… | How |
|---|---|
| **Skill** (auto) | The cabinet induces its own from experience — `skill_induction.py` drafts to `memory/skills/evolved/`, `evolution-loop` validates + promotes. This is the Hermes-style self-building loop, already running. |
| **Skill** (manual) | Drop `.claude/skills/<name>/SKILL.md` (auto-discovered), or use the first-party `skill-creator` skill for a guided scaffold + evals. |
| **MCP server** | Build with the first-party `mcp-builder` (or `vercel-mcp-builder`), declare it under `mcps:` here, grant via an `instance/agents/<o>.md` overlay. |
| **Plugin** | Scaffold with the first-party `create-cowork-plugin`, then declare under `plugins:` here. The cabinet itself ships as a plugin — read `.claude-plugin/plugin.json` as a worked example. |
| **Officer** | `bash cabinet/scripts/create-officer.sh <abbrev> <title> <domain> <bot-user> <bot-token>` |
| **Preset** | The `create-preset` skill (`memory/skills/create-preset.md`) — a whole use-case bundle under `presets/<name>/`. |

**Rule of thumb:** don't rebuild what's first-party (`skill-creator`,
`mcp-builder`, `create-cowork-plugin`); don't hand-author what the cabinet
can induce from experience. Reserve manual authoring for net-new capability,
then feed it back so the induction loop learns from it.

## Removing an extension

Delete its entry from `extensions.yml` and re-run `install-extensions.sh`.
Plugins: `claude plugin uninstall <name>`. Extra MCPs: removed from
`extra-mcps.json` automatically when no longer declared.
