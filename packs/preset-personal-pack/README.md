# preset-personal-pack

Marketplace entry for the **personal preset** — the single-operator shape for
someone who owns a project rather than a company. Navigator / Librarian /
Reviewer plus two longitudinal coaches, consent-gated autonomy, and read-only
recall over a local notes folder.

## What is copied vs referenced (honest inventory)

- **Copied into this pack:** ONLY the orientation/activation guide
  (`skills/preset-personal/SKILL.md`) and this README.
- **Referenced, NOT copied:** the preset payload itself —
  `presets/personal/` (preset.yml, coaching agents, terminology.yml,
  constitution/safety addenda, schemas.sql, measurement seed, validate.sh,
  README.md). It ships with the core `captains-cabinet` plugin / repo clone.
  Installing this pack alone does NOT put the preset on disk.
- **Maturity:** ACTIVE since 2026-07-27. `presets/personal/README.md` remains
  the preset's statement of record — read it before activating, especially the
  section on what this preset does and does not promise.

## Install

1. Install the core plugin first:
   `/plugin install captains-cabinet@captains-cabinet-marketplace`
2. Then this pack:
   `/plugin install preset-personal-pack@captains-cabinet-marketplace`
3. Activate via the `cabinet-init` skill (guided) or
   `echo personal > instance/config/active-preset` (manual) — details in the
   pack's `preset-personal` skill.

Governed path for deployments: declare the pack under `plugins:` in
`instance/config/extensions.yml` and run
`bash cabinet/scripts/install-extensions.sh`
(see `cabinet/docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate:
`bash cabinet/scripts/validate-extension.sh packs/preset-personal-pack`
(manifest: `manifest.yml`).
