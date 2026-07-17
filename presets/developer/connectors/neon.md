# Neon — MCP `neon-ro` (ON) / `neon` rw (Captain escalation)

**Why/when.** Database reads for a software product: schema, migration
state, row counts, live data shape. The CTO's first assignment starts
here; every officer benefits from read access to state.

**Verdicts supplied.** None directly (no probe row) — this is the
officers' data-shape surface. The Cabinet's own memory/Library ride Neon
via `NEON_CONNECTION_STRING` (separate, statically prompted).

**Declaration.** Neon is the ONLY connector with a URL-declarable
least-privilege knob, and the kit uses it:

- `neon-ro`: type `http`, url `https://mcp.neon.tech/mcp?readonly=true`,
  auth `Bearer ${NEON_API_KEY}` — the **default DB grant**.
- `neon` (read-write, url without the knob): pre-exists in `.mcp.json`
  for stack-detected lanes — granting it to a product-DB-writing officer
  is a **CAPTAIN ESCALATION**, never a preset default.

`NEON_API_KEY` rides `integrations.mcp_env_names` in the interview
answers so `setup-env.sh` walks it (README step 2).

**Scope to grant.** Captain grants `neon-ro` broadly (all officers,
read); `neon` rw per officer, per need, with the escalation recorded.

**Trifecta leg.** **B** — product data is private data. Read-only by URL
knob caps the blast radius at disclosure; the rw escalation is where
destructive potential enters, which is why it is Captain-gated. Data read
from the DB can still carry attacker-authored text (user content) —
untrusted data rules apply.
