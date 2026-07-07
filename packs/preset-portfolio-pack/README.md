# preset-portfolio-pack

Marketplace entry for the **portfolio preset** — one persistent Chair +
on-demand per-lane CEO officers.

## What is copied vs referenced (honest inventory)

- **Copied into this pack:** ONLY the orientation/activation guide
  (`skills/preset-portfolio/SKILL.md`) and this README.
- **Referenced, NOT copied:** the preset payload itself —
  `presets/portfolio/` (preset.yml, `agents/cos.md`,
  `agents/_lane-ceo.md.template`, terminology.yml, constitution/safety
  addenda, schemas.sql, validate.sh). It ships with the core
  `captains-cabinet` plugin / repo clone. Installing this pack alone does
  NOT put the preset on disk.

## Install

1. Install the core plugin first:
   `/plugin install captains-cabinet@captains-cabinet-marketplace`
2. Then this pack:
   `/plugin install preset-portfolio-pack@captains-cabinet-marketplace`
3. Activate via the `cabinet-init` skill (guided) or
   `echo portfolio > instance/config/active-preset` (manual) — details in
   the pack's `preset-portfolio` skill.

Governed path for deployments: declare the pack under `plugins:` in
`instance/config/extensions.yml` and run
`bash cabinet/scripts/install-extensions.sh`
(see `docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate:
`bash cabinet/scripts/validate-extension.sh packs/preset-portfolio-pack`
(manifest: `manifest.yml`).
