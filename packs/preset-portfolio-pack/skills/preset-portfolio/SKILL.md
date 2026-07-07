---
name: preset-portfolio
description: Activate the Cabinet portfolio preset — one persistent Chair + on-demand per-lane CEO officers. Use when a captain runs several product lanes on one Cabinet and asks how to select, activate, or understand the portfolio preset.
---

# Portfolio Preset — Orientation & Activation

The **portfolio preset** is the multi-lane Cabinet shape: one persistent Chair
(id `cos`, single Telegram bot) plus one on-demand CEO officer per product
lane, generated from a template. Functional depth comes from hats + hat
graduation and crew subagents, not from extra fulltime officers.

## Where the payload lives (referenced, NOT copied)

This pack ships orientation only. The preset payload lives in the core
captains-cabinet plugin / repo clone at `presets/portfolio/`:

- `preset.yml` — preset metadata
- `agents/cos.md` — the persistent Chair role definition
- `agents/_lane-ceo.md.template` — per-lane CEO role defs are GENERATED from
  this into `instance/agents/` (gitignored, deployment-specific)
- `terminology.yml`, `constitution-addendum.md`, `safety-addendum.md`,
  `schemas.sql`, `validate.sh`

If `presets/portfolio/` is not present, install the core `captains-cabinet`
plugin (or clone the repo) first — this pack cannot activate a preset that
is not on disk.

## Activation

1. **Guided (recommended):** run the `cabinet-init` skill. It interviews the
   captain (profile, lanes, org shape, autonomy posture, seed outcomes),
   writes `instance/config/cabinet-init.answers.yml`, and runs
   `cabinet/scripts/generate-instance.py` — which generates lane contexts,
   `instance/config/projects/<lane>.yml`, the lane-CEO role definitions,
   and (for org-flavor answers, i.e. `autonomy.flavor` other than
   `personal`) `instance/config/sources.yml` binding
   `framework.sources.org:OrgSource` so a fresh org instance has real
   recall; `platform.yml` also gains a `product_brain_dir:` key when
   absent (default `product-brain`, relative to the deployment root).
2. **Manual:** `echo portfolio > instance/config/active-preset`, fill
   `instance/config/` per `presets/README.md`, then let the preset loader
   (`cabinet/scripts/load-preset.sh`, called by `start-officer.sh`) assemble
   framework + preset + instance into `/tmp/cabinet-runtime/` at session
   start.

Nothing activates by itself: generated instance config is inert until the
captain starts officers.

## Fit

Choose portfolio when one captain runs multiple products/lanes and wants a
single coordinating Chair instead of a full functional officer fleet per
product. Single-product deployments usually fit the `work` preset instead.
