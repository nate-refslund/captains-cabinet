# CoS First Assignment: Cabinet Gap Analysis

**Type:** Strategic assessment
**Priority:** P0 — complete before any other Officers come online
**Deliverables:** Gap analysis in the deployment's knowledge base, Warroom briefing, Captain DM

## Objective

You are the first Officer live. Build a clear picture of what exists and what's missing — product, backlog, business knowledge, Cabinet infrastructure.

## Instructions

1. **Discover the product.** Explore the product checkout (path in `instance/config/product.yml`): framework and structure, features built vs. scaffolded vs. missing, database schema (Neon), what's deployed (Vercel). Findings to `instance/memory/tier2/cos/product-discovery.md`.
2. **Audit the business brain.** Read the business-context docs the product config points to (vision, strategy, brand, guardrails, pricing). Complete and coherent, or gapped? Does vision align with what's actually built?
3. **Assess the backlog.** Review the canonical task backlog (work graph `instance/config/outcomes.yml` + `/tasks`): item counts and states, priority clarity, spec coverage.
4. **Evaluate Cabinet readiness.** Shared interface directories created? Memory tier directories present with correct permissions? Knowledge base reachable and writable (test-write, then clean up)?
5. **Produce the gap analysis.** Publish to the knowledge base: product status, business-knowledge status, backlog health, Cabinet infrastructure status, and the top 3–5 recommended first priorities once all Officers are online.
6. **Brief the Captain.** Post a summary to the Warroom group (`"$CABINET_ROOT"/cabinet/scripts/send-to-group.sh`), then DM the Captain with top findings and any decisions needed.

## Success Criteria

- [ ] Discovery notes in Tier 2; brain, backlog, and infrastructure assessed
- [ ] Gap analysis published; Warroom briefed; Captain DM'd with decisions needed
