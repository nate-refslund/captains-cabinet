---
name: preset-personal
description: Activate the Cabinet personal preset — coaching-focused shape with lighter governance and consent-gated autonomy. Use when a captain wants a personal/life-operator Cabinet and asks how to select, activate, or understand the personal preset.
---

# Personal Preset — Orientation & Activation

The **personal preset** is the coaching / life-operator Cabinet shape:
coaching agents instead of functional officers, "coach" terminology,
privacy-first constitution addendum, and consent-gated (lower-than-work)
default autonomy.

## Where the payload lives (referenced, NOT copied)

This pack ships orientation only. The preset payload lives in the core
captains-cabinet plugin / repo clone at `presets/personal/`:

- `preset.yml` — preset metadata
- `agents/` — coaching agent definitions (e.g. physical-coach,
  mindfulness-coach)
- `terminology.yml`, `constitution-addendum.md`, `safety-addendum.md`,
  `schemas.sql`, `README.md`

**Read `presets/personal/README.md` FIRST** — it is the preset's maturity
statement of record. If it still marks the preset as a placeholder for a
later phase, do not activate it; the preset loader fails cleanly on an
unpopulated preset, but the honest path is to check before switching.

If `presets/personal/` is not present, install the core `captains-cabinet`
plugin (or clone the repo) first — this pack cannot activate a preset that
is not on disk.

## Activation (once the preset is populated)

1. **Guided (recommended):** run the `cabinet-init` skill and answer for a
   personal/coaching deployment; it writes the `instance/` configuration.
2. **Manual:** `echo personal > instance/config/active-preset`, fill
   `instance/config/` per `presets/README.md`, then let the preset loader
   (`cabinet/scripts/load-preset.sh`, called by `start-officer.sh`) assemble
   framework + preset + instance into `/tmp/cabinet-runtime/`.

A personal Cabinet can run side by side with a work Cabinet — the active
preset is per-deployment state in `instance/config/active-preset`.
