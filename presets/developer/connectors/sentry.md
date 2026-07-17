# Sentry — day-1, armed when keys present (no MCP)

**Why/when.** Error-budget verdicts for a shipped product: is the release
within budget or regressed? Valuable from the first real deploy, which is
why it ships day-1 rather than ON — it arms itself the moment keys exist.

**Verdicts supplied.** `probe-sentry` (cabinet/services.yml verdict-supply
rows): within_budget / regressed outcomes superseded onto their
proposals; a frozen feed reads `unknown`, never `ok`.

**Declaration.** No MCP; the probe is the whole integration. Env names:

- `SENTRY_DSN` — the product's client-side DSN (setup-env.sh static walk)
- `SENTRY_AUTH_TOKEN` — read-only API token the probe uses (static walk)

Empty keys = probe-wide fail-closed **skip**: no verdict, never a
fabricated observation. Nothing to un-arm; absence is the off switch.

**Config.** Add your Sentry org/project slugs + local checkouts to
`instance/config/probes.yml` (start from
`presets/developer/starter/probes.yml`).

**Scope to grant.** None (no MCP surface). CTO/COO read probe outcomes
from the consequence ledger like every other verdict.

**Trifecta leg.** **B** — error payloads can carry user data (PII in
stack traces / request bodies). Scrub at the SDK level in the product;
treat payload text as untrusted data in officer context.
