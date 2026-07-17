---
name: preset-developer
description: Activate the Cabinet developer preset — the software product-kind kit (work roster + day-1 connector declarations for GitHub, Playwright, read-only Neon, Vercel-by-REST, Sentry). Use when a captain ships a software/web/app product and asks how to select, activate, or understand the developer preset.
---

# Developer Preset — Orientation & Activation

The **developer preset** is the software product-kind kit: the classic
product-team roster — First Mate (CoS, machine id `cos`), CTO, CPO, CRO,
COO — flat-copied from the `work` preset, plus day-1 connector
declarations so a fresh software deployment does not start bare. Family
framing: Flavor B is a GENERAL product org; this preset is its SOFTWARE
kit, first of a family (e-commerce/services kits are later siblings).

**Optional always.** Never a default flip — the fallback preset stays
`work`. Activating developer is an explicit deployment choice.

## What the kit declares (env-var NAMES only, zero secrets)

- **GitHub MCP** (`github`, first-party remote, `GITHUB_PAT`) — PR/issue
  work surface + probe-github verdicts. ON.
- **Playwright MCP** (`playwright`, first-party npx, zero-credential) —
  browser verdicts. ON.
- **Neon read-only MCP** (`neon-ro`, `?readonly=true`, `NEON_API_KEY`) —
  default DB grant; read-write `neon` is a Captain escalation. ON.
- **Vercel by REST + probes** (NOT MCP — the official MCP is OAuth-only,
  un-declarable for headless officers; `VERCEL_TOKEN` walked,
  probes read `VERCEL_API_KEY` + `VERCEL_TEAM_ID`). ON.
- **Sentry** — day-1: probe-sentry arms itself when
  `SENTRY_DSN`/`SENTRY_AUTH_TOKEN` exist, skips fail-closed when empty.
- **Stripe / PostHog / Resend** — declared-OFF (documented in
  `presets/developer/connectors/`, nothing declared or granted).

Scope grants are NEVER automatic: the Captain applies the printed
mcp-scope/capabilities diffs (the 2-minute step in the preset README).

## Where the payload lives (referenced, NOT copied)

This pack ships orientation only. The preset payload lives in the core
captains-cabinet plugin / repo clone at `presets/developer/`:

- `preset.yml` — metadata + onboarding defaults
  (`lane_mcps: [library, telegram, github, playwright, neon-ro]`)
- `agents/` — the five officer role defs + three scaffolds
- `README.md` — the day-1 runbook (activation → env names → Captain
  scope grant → probes → Product Journal seed → hiring)
- `connectors/` — 8 capability-first one-pagers
- `starter-spaces/product-journal.yml`, `starter/probes.yml`,
  `terminology.yml`, constitution/safety addenda, `schemas.sql`,
  `validate.sh`

If `presets/developer/` is not present, install the core
`captains-cabinet` plugin (or clone the repo) first — this pack cannot
activate a preset that is not on disk.

## Activation

1. **Guided (recommended):** run the `cabinet-init` skill. For
   `org_shape: functional` it asks the optional preset question; opting
   in records `cabinet.preset: developer` and the generator prints the
   exact activation step.
2. **Manual:** `echo developer > instance/config/active-preset`, then
   `bash cabinet/scripts/load-preset.sh` and
   `bash presets/developer/validate.sh`; continue with the preset
   README's numbered day-1 path.

Nothing activates by itself: declarations are inert until env names get
values (`setup-env.sh`) and the Captain applies the scope grants.

## Fit

Choose developer when the org ships ONE software/web/app product and
wants the day-1 software surfaces declared. Multi-product captains use
`portfolio`; non-software or mixed work fits `work`; a one-CEO-per-product
founder uses `org_shape: portfolio` — topology stays orthogonal to the
preset choice.
