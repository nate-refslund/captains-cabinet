# packs/ — Capability packs (marketplace rail)

Optional, separately installable Claude Code plugins carved out of the
Cabinet's core payload. Each pack is a self-contained plugin
(`<pack>/.claude-plugin/plugin.json` + `<pack>/skills/`) listed in the
marketplace manifest (`.claude-plugin/marketplace.json`) alongside the core
`captains-cabinet` plugin, **plus** a Cabinet extension manifest
(`<pack>/manifest.yml`) so the same directory passes the governed extension
gate:

```bash
bash cabinet/scripts/validate-extension.sh packs/<pack-name>
```

## The packs

| Pack | Contents | Copied or referenced? |
|---|---|---|
| `doctrine-pack` | 5 doctrine skills: holistic-thinking, production-quality-ownership, individual-reflection, cross-officer-retro, spec-quality-gate | **Copied** — pack frontmatter over the canonical `memory/skills/` bodies (the `.claude/skills/` files are R155 pointer wrappers, not bodies; the two retro skills' copy⇄canonical parity is pinned by `cabinet/scripts/tests/test_memory_distill.py`). Copies carry date-typed `sunset: '2026-10-05'` frontmatter — the apoptosis reaper scans `packs/*/skills/*/SKILL.md` and cards the removal-wave review once it passes |
| `vercel-lane-pack` | deploy-and-verify + engineering-development-loop (both are Vercel-flow skills) | **Copied** from `.claude/skills/` |
| `agent-teams-pack` | agent-team-workflow | **Copied** from `.claude/skills/` |
| `preset-portfolio-pack` | Portfolio-preset activation guide skill + README | Payload **referenced** at `presets/portfolio/` (core plugin/repo) |
| `preset-personal-pack` | Personal-preset activation guide skill + README | Payload **referenced** at `presets/personal/` (core plugin/repo) |
| `preset-developer-pack` | Developer-preset (software product-kind kit) activation guide skill + README | Payload **referenced** at `presets/developer/` (core plugin/repo) |
| `lighthouse-log-pack` | daily-lighthouse-log — the day's keeper's log, composed from the world chronicle into the officer's own tier2 note | **Original — authored in the pack** (no core copy, no `sunset:` line; also the running exemplar for `docs/authoring-a-pack.md`) |

The `work` preset stays CORE payload (it ships inside the `captains-cabinet`
plugin, not as a pack). Instance-specific presets are never packaged into the
marketplace — the marketplace carries only universal payload; anything
deployment-specific stays in `instance/` or a local preset directory.

## Additive posture (this wave)

The core-skill packs are **parallel copies**: the originals remain in
`.claude/skills/` and the core plugin still ships them, because live officers
load them from there. (`lighthouse-log-pack` is the exception — an original
authored in the pack, nothing to copy or reap.)
Copies are content-identical to the originals except for three deliberate
deltas: doctrine copies gain a date-typed `sunset: '2026-10-05'` line (the
apoptosis reaper scans `packs/*/skills/*/SKILL.md` and raises a propose-only
review card once the date passes — the removal-wave trigger), descriptions
containing `": "` are YAML-quoted so every pack passes
`claude plugin validate` clean, and marketplace copies use captain-neutral
wording (role terms like `the Captain`, never a personal name — the originals
keep instance wording, and their quoting quirk, until the removal wave).
Removing the originals (making packs the only source) is a later wave, gated
on its sibling ratchets. Until then, a deployment that installs both the core
plugin and a pack sees the same skill under two plugin namespaces — harmless,
and by design for this transition.

## Install paths

- **Captain, interactive:** `/plugin marketplace add <owner>/<repo>` then
  `/plugin install <pack-name>@captains-cabinet-marketplace`.
- **Officers / deployments (governed path):** declare the pack under
  `plugins:` in `instance/config/extensions.yml` and run
  `bash cabinet/scripts/install-extensions.sh` — never ad-hoc `/plugin`
  calls from officer sessions.

Full instructions: `cabinet/docs/cabinet-plugin-installation.md` § Capability packs —
including the rule that `source.repo`/`source.ref` in the marketplace manifest
point at ONE repo+ref and must be retargeted together per fork.
