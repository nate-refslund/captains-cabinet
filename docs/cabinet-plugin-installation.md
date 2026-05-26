# Cabinet Plugin Installation

The Cabinet ships as a Claude Code plugin so a fresh founder can install it
in one step rather than `git clone + scripts/setup-mac.sh`.

## Plugin packaging status

**Project-only mode (dev preview).** `claude plugin validate .claude-plugin/marketplace.json`
passes cleanly. `claude plugin validate .claude-plugin/plugin.json` passes with
one warning that `--strict` treats as an error:

```
⚠ CLAUDE.md at the plugin root is not loaded as project context.
  To ship context with your plugin, use a skill (skills/<name>/SKILL.md) instead.
```

This is intentional. Cabinet's `CLAUDE.md` at the repo root is the canonical
Captain operating context for direct cabinet operation (`git clone + start-officer.sh`).
For users installing via the marketplace, the equivalent context ships through
the `cabinet-intro` skill at `.claude-plugin/skills/cabinet-intro/SKILL.md`,
which is CC-native discoverable on plugin install.

The warning is unfixable without restructuring cabinet startup. Two paths
forward — pick one depending on your install:

| Install path | Strict-clean? | Context loading |
|---|---|---|
| `git clone` + `scripts/setup-mac.sh` (direct) | N/A | Root `CLAUDE.md` auto-loaded as project context |
| `claude plugin install captains-cabinet` (plugin) | Warns, doesn't block | `cabinet-intro` skill loaded on demand by officers |

The plugin install path is **dev-preview ready** — it works end-to-end, but
the strict-validation warning means it's not "marketplace strict-clean" yet.

## Install via the Cabinet marketplace

```bash
# Once the marketplace is registered on a fresh Mac:
claude plugin install captains-cabinet --source captains-cabinet-marketplace
```

The plugin manifest (`.claude-plugin/plugin.json`) declares:

- **5 agent definitions** (cos / cto / cpo / cro / coo) from the `work` preset
- **16 skills** — 6 cabinet-specific (cabinet-task, cabinet-route-tasks,
  cabinet-work-graph-complete, org-status, mission-compile, ovi-publish) +
  10 lifted foundation skills (holistic-thinking, production-quality-ownership,
  telegram-communication, cross-officer-retro, evolution-loop,
  individual-reflection, agent-team-workflow, deploy-and-verify,
  engineering-development-loop, spec-quality-gate)
- **11 slash commands** — 5 parent (activate-project, mission-compile,
  org-status, ovi-publish, role-eval) + 6 cabinet- prefixed
- **1 path-scoped rule** (org-runtime-native)
- **6 MCP servers** (notion, neon, linear, vercel, redis-trigger-channel, library)
- **settings** with hooks, voice, defaultMode, and statusLine wiring

## Prerequisites (auto-checked by `setup-mac.sh --check`)

- Homebrew (Mac) or apt (Linux)
- `tmux 3.0+`, `jq 1.6+`, `python3.9+`, `redis 6.0+`
- `gettext` (for `envsubst` — needed by deploy-mac.sh's plist renderer)
- `gh` (GitHub CLI — needed by the GitHub Issues task adapter)
- `bun 1.0+` (for the TypeScript MCP channels — redis-trigger-channel + library-mcp)
- Claude Code CLI ≥ 2.0 with Max OAuth (NO Anthropic API key required)

## Post-install steps (Captain-physical, per the deploy runbook)

The plugin install lands the code. Captain-physical work still required:

1. **Configure your instance/** — set `instance/config/active-preset`,
   `instance/config/active-project.txt`, fill `instance/config/product.yml`
2. **Bring up Redis** — `brew services start redis` (Mac) or apt equivalent
3. **Run `cabinet/scripts/setup-mac.sh`** — installs missing deps + runs
   smoke tests + loads the preset
4. **Apple Developer enrollment + code-signing** (see
   `docs/mac-mini-deploy-runbook.md`)
5. **TCC permissions** — System Settings → Privacy & Security → grant Terminal
   the access claude-code needs
6. **Tailscale install + sign-in** — manual sudo step
7. **Deploy LaunchAgents** — `bash cabinet/scripts/deploy-mac.sh`
8. **72h soak + crash test + power-cycle test**

See `docs/mac-mini-deploy-runbook.md` for the full Captain-physical runbook
that the plugin install path does NOT replace.

## Per-preset variants

The marketplace lists two install targets:

- `captains-cabinet` — full work preset (5 officers, mission/role/OVI)
- `captains-cabinet-personal` — personal preset (lighter, coaching-focused)

A founder can install both side by side and choose the active preset via
`instance/config/active-preset`. The preset loader (`cabinet/scripts/load-preset.sh`)
concatenates framework + active-preset + instance into `/tmp/cabinet-runtime/`
at session start.

## Uninstall

```bash
claude plugin uninstall captains-cabinet
```

This removes the plugin's `.claude/` contributions but **does not** touch
`instance/`, `memory/`, or `~/Cabinet-Backups/` — those are durable Cabinet
state that survives the plugin lifecycle.
