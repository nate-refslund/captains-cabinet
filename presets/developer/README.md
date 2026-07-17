# presets/developer/ — the software product-kind kit

The **developer preset** is the day-1 kit for founders and developers
shipping a **software / web / app product**. Family framing (Captain
ratified 2026-07-17): Flavor B is a **general** product org — any product
kind; this preset is its **software** kit, the **first of a family**
(e-commerce/physical and services kits are later siblings). It is a flat
copy of `presets/work` (flat only, no inheritance — presets/README.md)
plus software-kit deltas: connector declarations, a product-brain starter
Space, a probes starter config, and this runbook.

**Optional, always.** Activating this preset is an explicit deployment
choice; the fallback preset stays `work`. Nothing here flips by default.

**Declarations only.** The kit ships env-var NAMES, server URLs, and
markdown — zero glue code, zero secrets, zero scope auto-grants. Officer
access to every connector is applied by the Captain (see step 3).

## What you get on day 1

| Surface | How | Status |
|---|---|---|
| GitHub (PRs/issues + probe-github verdicts) | MCP `github` — first-party remote, `GITHUB_PAT` | ON |
| Browser verdicts ("does it actually work") | MCP `playwright` — first-party npx, zero-credential | ON |
| Database reads | MCP `neon-ro` — `?readonly=true` URL knob, `NEON_API_KEY`; read-write `neon` = Captain escalation | ON |
| Deploys (state, build fails, promotion) | Vercel **REST + probes**, NOT MCP — official MCP is OAuth-only, un-declarable for headless officers | ON |
| Error budget (within_budget/regressed) | probe-sentry — armed only when `SENTRY_DSN`+`SENTRY_AUTH_TOKEN` exist; empty = fail-closed skip | day-1 |
| Stripe / PostHog / Resend | documented in `connectors/`, nothing declared | declared-OFF |

Details per connector — why/when, verdicts supplied, env names, scope,
which lethal-trifecta leg it opens: `connectors/*.md`.

## Activation (the whole path)

1. **Activate the preset**

   ```bash
   echo developer > instance/config/active-preset
   bash cabinet/scripts/load-preset.sh
   bash presets/developer/validate.sh   # pre-spawn gate; also run by cabinet-spawn.sh
   ```

2. **Wire the env-var NAMES** (values live in `cabinet/.env`, chmod 600,
   gitignored — never in config):

   ```bash
   bash cabinet/scripts/setup-env.sh
   ```

   - Statically prompted by the walk already: `GITHUB_PAT`,
     `NEON_CONNECTION_STRING`, `VERCEL_TOKEN`, `SENTRY_DSN`,
     `SENTRY_AUTH_TOKEN`, `POSTHOG_API_KEY`.
   - The developer kit's extra names ride the interview's
     `integrations.mcp_env_names` list in
     `instance/config/cabinet-init.answers.yml` — add
     `NEON_API_KEY`, `VERCEL_API_KEY`, `VERCEL_TEAM_ID` there and the
     same walk prompts for them (setup-env.sh reads the declared list;
     UPPER_SNAKE names only, values never land in the answers file).
   - Principle: **OAuth for the human once at setup, keys for the
     headless steady state.** Anything only reachable by an interactive
     OAuth flow (the official Vercel MCP) is not a standing officer
     surface — officers get token/REST paths.

3. **The 2-minute Captain scope-grant step.** Connector access is never
   auto-granted: `cabinet/mcp-scope.yml` and
   `cabinet/officer-capabilities.conf` are Captain-locked (schg), and the
   preset never writes them. The onboarding planner PRINTS the exact
   diffs to apply — `framework/onboarding/plan.py` emits
   `mcp_scope_diff` + `capabilities_diff` per lane, and
   `generate-instance.py` prints the same instruction in its next steps.
   The Captain reviews the printed rows, applies them inside a germline
   unlock window, relocks. New MCP servers (`github`, `neon-ro`,
   `playwright`) also need their `mcp__<name>` rows in
   `.claude/settings.json` `permissions.allow` — same Captain-locked
   surface, same window. That's the whole ceremony — two minutes, once
   per roster change, and the reason a fresh clone of this repo can never
   grant itself anything: until the Captain applies both, the kit's
   declarations are inert.

4. **Install the probes** (verdict supply — deliberate human step). The
   probe service rows are live in `cabinet/services.yml`
   (probe-github / probe-vercel / probe-sentry); installing a plist IS
   the enable flip — each carries `CABINET_PROBES_ENABLED=1` and the
   entrypoints are inert without it (see the services.yml verdict-supply
   comment):

   ```bash
   cp presets/developer/starter/probes.yml instance/config/probes.yml
   $EDITOR instance/config/probes.yml     # your repos/apps + local checkouts
   # then install the probe plists per cabinet/launchd/ + INSTALL-flip.md
   ```

   Probes read env only (`GITHUB_PAT`→`GH_TOKEN` fallback,
   `VERCEL_API_KEY` + `VERCEL_TEAM_ID`, `SENTRY_AUTH_TOKEN`); a missing
   key or checkout skips fail-closed — no verdict, never a fabricated
   observation.

5. **Seed the product brain**

   ```bash
   bash cabinet/scripts/seed-library.sh --preset developer --dry-run   # preview
   bash cabinet/scripts/seed-library.sh --preset developer
   ```

   Seeds the `Product Brain` Space (start-here, product overview, release
   log, incident index, customer feedback) — generic `<placeholders>`,
   idempotent, never overwrites edits.

6. **Hire.** Default-hire guidance for a software product: **CoS (First
   Mate) + CTO day-0**, CPO staged once real specs queue; CRO/COO when
   research volume / deploy validation warrant them
   (`cabinet/scripts/create-officer.sh`).

## Trust posture

- Endpoints in this kit's docs are declarations to be VERIFIED, never
  trusted: `validate.sh` gates the preset shape pre-spawn, and the
  deployment's doctor/init checks verify the concrete endpoints.
- Content arriving THROUGH connectors (issue text, page content, error
  payloads) is untrusted data — see `safety-addendum.md`, which names the
  lethal-trifecta leg each connector opens and keeps the cheapest exfil
  leg (outbound email) declared-OFF.
- Addenda only tighten: this preset adds restrictions on top of
  `framework/safety-boundaries-base.md`, never relaxes it.

## Files

Same layout as `presets/work` (see presets/README.md) plus:

- `connectors/` — 8 capability-first one-pagers (github, playwright,
  neon, vercel, sentry, stripe, posthog, resend)
- `starter-spaces/product-brain.yml` — Library starter Space + seeds
- `starter/probes.yml` — placeholder twin of
  `instance/config/probes.yml.example`
- `terminology.yml` — carries `coordinator_title: First Mate`
  (display-title layer; machine id `cos` frozen)
