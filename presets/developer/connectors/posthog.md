# PostHog — declared-OFF

**Why OFF.** Product analytics has **no verdict value until the product
has traffic**. A fresh deployment gains nothing from an analytics
connector on day 1 — it would be configuration debt with zero signal.

**When enabled (the known path, not shipped).**

- Env name: `POSTHOG_API_KEY` (the `setup-env.sh` static walk already
  prompts for it — wiring the value is cheap the day it matters).
- REST reads (trends, funnels, event counts) are sufficient; no MCP
  declaration ships in this kit.
- Turn-on trigger: real user traffic + a concrete question an officer
  needs answered (activation funnel, feature adoption). Captain applies
  the scope grant; the safety addendum gains a row.

**Verdicts.** Once live, usage deltas can feed CPO success-metrics checks
(the spec format already demands success metrics per feature) — a natural
later probe candidate.

**Trifecta leg.** **B** — behavioral analytics is user data. Read-only
API keys only; aggregate queries over raw event export wherever the
question allows.
