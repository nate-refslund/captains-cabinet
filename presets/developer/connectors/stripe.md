# Stripe — declared-OFF

**Why OFF.** Money movement is the maximum blast radius an org connector
can carry. The kit's rule: **add it when someone says yes** — a paying
customer, a checkout to build — never speculatively.

**When enabled (the known path, not shipped).**

- Env name: `STRIPE_RESTRICTED_KEY` — a **restricted key** scoped to
  exactly the objects needed (read charges / customers; write only what
  the approved flow requires). Never a full secret key.
- Bearer-token REST is sufficient; no MCP declaration ships in this kit.
  If an MCP is wanted later it must pass the same bar as the others:
  first-party, env-name auth, no OAuth-only flow.
- Captain applies the scope grant per officer (`cabinet/mcp-scope.yml`
  diff flow) and the safety addendum gains a row BEFORE first use.

**Verdicts.** None until enabled; billing/revenue verdicts are a later
sibling of the probe family.

**Trifecta leg.** **B + C** — customer/payment data is maximally private,
and a write-capable payments key is itself an exfil/actuation channel
(refunds, payouts). This is why the connector stays documented-but-off:
the doc is the map, the Captain's grant is the territory.
