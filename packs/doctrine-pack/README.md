# doctrine-pack

Five doctrine skills, packaged as an optional Claude Code plugin:

- `holistic-thinking` — the universal L1/L2/L3 improvement lens
- `production-quality-ownership` — six-question craftsman checklist
- `individual-reflection` — per-officer event-triggered reflection
- `cross-officer-retro` — CoS-driven cross-officer retrospective
- `spec-quality-gate` — pre-publish checklist for product specs

**Copied, not moved.** These are parallel copies of the skills in
`.claude/skills/` — the core plugin still ships the originals this wave
(live officers depend on them). Each copy carries
`sunset: 'undefined +90d review'` frontmatter so the apoptosis reaper can
review the duplication once the removal wave lands.

Install: `/plugin install doctrine-pack@captains-cabinet-marketplace`, or the
governed path via `instance/config/extensions.yml` (see
`docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate: `bash cabinet/scripts/validate-extension.sh packs/doctrine-pack`
(manifest: `manifest.yml`).
