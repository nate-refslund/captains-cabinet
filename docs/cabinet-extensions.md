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

## Worked example — STEP-Network's dev-tasks plugin

STEP-Network products use the [`dev-tasks`](https://github.com/STEP-Network/dev-tasks)
plugin (Monday.com + GitHub + Vercel workflow: 44 Monday MCP tools, 15 skills,
4 subagents, 34 hooks). It's **not** shipped by default — it hard-fails on
non-STEP repos by design. A STEP Captain enables it:

1. `instance/config/extensions.yml`:
   ```yaml
   plugins:
     - name: dev-tasks
       marketplace: dev-tasks-marketplace
       source: STEP-Network/dev-tasks
       required_env: [MONDAY_API_TOKEN]
       optional: false
   ```
2. `MONDAY_API_TOKEN` in `cabinet/.env` (the secrets wizard prompts for it).
3. `cp .claude/project-config.json.template .claude/project-config.json` and
   fill `monday.productId` etc.
4. Grant officers: e.g. `instance/agents/cto.md` with
   `tools: …, mcp__plugin_dev-tasks_dev-tasks`.
5. `bash cabinet/scripts/install-extensions.sh` → installs + verifies.

The cabinet's own `task_adapters/monday.py` was removed in favor of this
plugin — for Monday users, the plugin is strictly better than a homegrown
adapter.

## Removing an extension

Delete its entry from `extensions.yml` and re-run `install-extensions.sh`.
Plugins: `claude plugin uninstall <name>`. Extra MCPs: removed from
`extra-mcps.json` automatically when no longer declared.
