# preset-developer-pack

Marketplace entry for the **developer preset** — the software
product-kind kit: the product-team roster (First Mate (CoS) / CTO / CPO /
CRO / COO) plus day-1 connector declarations so a fresh software
deployment does not start bare. First of a product-kind family under the
general product-org shape (e-commerce/services kits are later siblings).
OPTIONAL always — activating it is an explicit deployment choice; the
fallback preset stays `work`.

## What is copied vs referenced (honest inventory)

- **Copied into this pack:** ONLY the orientation/activation guide
  (`skills/preset-developer/SKILL.md`) and this README.
- **Referenced, NOT copied:** the preset payload itself —
  `presets/developer/` (preset.yml, agents/, terminology.yml,
  constitution/safety addenda, schemas.sql, validate.sh, connectors/,
  starter-spaces/product-journal.yml, starter/probes.yml, the day-1
  README runbook). It ships with the core `captains-cabinet` plugin /
  repo clone. Installing this pack alone does NOT put the preset on
  disk.

## Install

1. Install the core plugin first:
   `/plugin install captains-cabinet@captains-cabinet-marketplace`
2. Then this pack:
   `/plugin install preset-developer-pack@captains-cabinet-marketplace`
3. Activate via the `cabinet-init` skill (guided — the interview asks
   the optional preset question for the functional shape) or
   `echo developer > instance/config/active-preset` (manual) — the full
   day-1 path (env names, the 2-minute Captain scope-grant step, probes
   install, Product Journal seed) is `presets/developer/README.md`.

Governed path for deployments: declare the pack under `plugins:` in
`instance/config/extensions.yml` and run
`bash cabinet/scripts/install-extensions.sh`
(see `cabinet/docs/cabinet-plugin-installation.md` § Capability packs).

Extension gate:
`bash cabinet/scripts/validate-extension.sh packs/preset-developer-pack`
(manifest: `manifest.yml`).
