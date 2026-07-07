# preset-personal-pack

Marketplace entry for the **personal preset** — coaching-focused Cabinet
shape with lighter governance and consent-gated autonomy.

## What is copied vs referenced (honest inventory)

- **Copied into this pack:** ONLY the orientation/activation guide
  (`skills/preset-personal/SKILL.md`) and this README.
- **Referenced, NOT copied:** the preset payload itself —
  `presets/personal/` (preset.yml, coaching agents, terminology.yml,
  constitution/safety addenda, schemas.sql, README.md). It ships with the
  core `captains-cabinet` plugin / repo clone. Installing this pack alone
  does NOT put the preset on disk.
- **Maturity:** `presets/personal/README.md` is the preset's maturity
  statement of record — read it before activating (it may still mark the
  preset as a placeholder for a later phase).

## Install

1. Install the core plugin first:
   `/plugin install captains-cabinet@captains-cabinet-marketplace`
2. Then this pack:
   `/plugin install preset-personal-pack@captains-cabinet-marketplace`
3. Activate via the `cabinet-init` skill (guided) or
   `echo personal > instance/config/active-preset` (manual, only once the
   preset is populated) — details in the pack's `preset-personal` skill.

Governed path for deployments: declare the pack under `plugins:` in
`instance/config/extensions.yml` and run
`bash cabinet/scripts/install-extensions.sh`
(see `docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate:
`bash cabinet/scripts/validate-extension.sh packs/preset-personal-pack`
(manifest: `manifest.yml`).
