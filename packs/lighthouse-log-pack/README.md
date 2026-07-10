# lighthouse-log-pack

One skill, packaged as an optional Claude Code plugin — and the
**authoring exemplar** for third-party packs: `docs/authoring-a-pack.md`
rebuilds this pack from scratch, file by file. Copy this directory's shape
when authoring your own.

- `daily-lighthouse-log` — compose a short, honest keeper's log of the
  day's org events (read from `shared/interfaces/world/chronicle-*.jsonl`,
  plus — solely to demo-check `undo.journaled` rows — the one `ref`-named
  undo-journal line; both read-only) and file it as the officer's own
  Tier 2 note under `instance/memory/tier2/<role>/`. Honest zeros stated
  as zeros; synthetic rows labeled (`(demo)` / `(canary)`); no network,
  no scripts, no other writes.

**Original, not a copy.** Unlike the doctrine / vercel-lane / agent-teams
packs (parallel copies of core `.claude/skills/` skills), this skill is
authored in the pack: there is no core original and no `sunset:` line —
the apoptosis reaper has nothing to card here.

## Install

- **Captain, interactive:** `/plugin marketplace add <owner>/<repo>` then
  `/plugin install lighthouse-log-pack@captains-cabinet-marketplace`.
- **Officers / deployments (governed path):** declare the pack under
  `plugins:` in `instance/config/extensions.yml` and run
  `bash cabinet/scripts/install-extensions.sh` — never ad-hoc `/plugin`
  calls from officer sessions (see
  `cabinet/docs/cabinet-plugin-installation.md` § Capability packs).

## Uninstall

- Interactive installs:
  `/plugin uninstall lighthouse-log-pack@captains-cabinet-marketplace`.
- Governed installs: remove the entry from
  `instance/config/extensions.yml` and re-run `install-extensions.sh`.
- Composed logs are the officer's tier2 notes — uninstalling the pack
  leaves them in place; delete them separately if unwanted.

## Extension gate

```bash
bash cabinet/scripts/validate-extension.sh packs/lighthouse-log-pack
```

(manifest: `manifest.yml`)
