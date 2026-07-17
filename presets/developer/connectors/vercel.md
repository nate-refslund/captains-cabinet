# Vercel — REST + probes, deliberately NOT MCP (ON)

**Why/when.** Deploy state for a software product: latest prod/preview
deploy, build failures, promotion/rollback outcomes. The CTO deploys
(Captain approval for prod); the COO validates.

**Why NOT an MCP.** The official Vercel MCP is **OAuth-only** — an
interactive browser flow a headless 24/7 officer cannot complete, so it
is un-declarable as a standing surface. The kit's rule: **OAuth for the
human once at setup, keys for the headless steady state.** Standing
access is token/REST:

- Officers act via the Vercel REST API / CLI with `VERCEL_TOKEN`.
- Verdicts come from `probe-vercel` (cabinet/services.yml verdict-supply
  rows): deploy_ready / rolled_back / deploy_error superseded onto their
  proposals.

(A pinned third-party Vercel MCP exists in `.mcp.json` for legacy lanes;
retiring it is a separate filed follow-up — this kit neither uses nor
touches it.)

**Env names (the real split — read carefully).**

- `VERCEL_TOKEN` — the legacy `.mcp.json` entry + the `setup-env.sh`
  static walk use this name.
- `VERCEL_API_KEY` + `VERCEL_TEAM_ID` — what the probe actually reads
  (`framework/probes/probe_vercel.py` reads both from env; team scoping
  is load-bearing because the v9 projects list truncates ids, so probes
  query by app name within the team). Declare both in
  `integrations.mcp_env_names` so the walk prompts for them.

**Scope to grant.** No MCP scope needed for the REST path; deploy
authority rides `officer-capabilities.conf` (`deploys_code` → CTO,
`validates_deployments` → COO) — Captain-applied.

**Trifecta leg.** **B** — deploy metadata and env-var NAMES are private
data (values never transit). Production deploys stay Captain-approved
regardless of connector wiring.
