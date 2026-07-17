# CPO First Assignment: Backlog Audit & Product Roadmap

**Type:** Product assessment
**Priority:** P0 — complete before writing specs or prioritizing work
**Deliverables:** Tier 2 notes, product roadmap in the deployment's knowledge base, Warroom briefing

## Objective

Understand the product's current state, the business context, and the backlog; produce a roadmap aligned with the Captain's vision.

## Instructions

1. **Absorb the business brain.** Read every business-context doc the product config points to (`instance/config/product.yml`): vision, strategy, brand, growth guardrails, pricing. Synthesis to `instance/memory/tier2/cpo/business-context.md`.
2. **Audit the backlog.** Go through the canonical task backlog (work graph `instance/config/outcomes.yml` + `/tasks`): item counts and states, projects/milestones, which items have specs vs. titles only, priority distribution, duplicates/stale/poorly-scoped items. Findings to `instance/memory/tier2/cpo/backlog-audit.md`.
3. **Read the CoS gap analysis** in the knowledge base: product status, blockers identified, suggested priorities.
4. **Create the roadmap.** Publish Now (this week) / Next (next 2 weeks) / Later (this month) entries to the knowledge base, each referencing a backlog item — or noting one needs to be created.
5. **Write the first spec queue.** Spec the top 3 "Now" items to `shared/interfaces/product-specs/` following the format in your role definition — good enough for the CTO to start, not perfect.
6. **Coordinate.** Post a Warroom summary; notify the CTO via Redis (`notify-officer.sh cto "CPO roadmap and first specs ready — see shared/interfaces/product-specs/"`); update `shared/backlog.md` with the Now/Next/Later view.

## Success Criteria

- [ ] Synthesis + backlog audit in Tier 2; roadmap published; top 3 specs written
- [ ] `shared/backlog.md` updated; Warroom briefed; CTO notified
