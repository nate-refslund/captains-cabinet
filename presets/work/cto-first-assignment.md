# CTO First Assignment: Codebase Deep Dive & Engineering Assessment

**Type:** Technical assessment
**Priority:** P0 — complete before taking on implementation work
**Deliverables:** Tier 2 notes, engineering assessment in the deployment's knowledge base, Warroom briefing

## Objective

Deeply understand the codebase, database, and deployment pipeline; produce an engineering assessment that becomes your reference for all future work.

## Instructions

1. **Explore the codebase.** The product checkout path is in `instance/config/product.yml`. Map the layout (monorepo? workspaces? packages?), framework versions, key directories, entry points, shared libraries. Findings to `instance/memory/tier2/cto/codebase-map.md`.
2. **Understand the database.** Query Neon: full schema (tables, constraints, indexes), relationships, row counts (data maturity), migration state. Findings to `instance/memory/tier2/cto/database-schema.md`.
3. **Assess build & deploy.** `package.json` scripts; does the build succeed? Tests present and passing? Vercel config and required env vars; CI/CD and pre-commit hooks.
4. **Identify technical debt.** Error handling, test coverage, hardcoded values that should be env vars, unused dependencies, performance, security.
5. **Publish the engineering assessment:** codebase health, database health, build pipeline state, tech-debt top 10 ranked by impact, recommended first engineering tasks.
6. **Coordinate.** Post a Warroom summary; notify the CPO via Redis (`notify-officer.sh cpo "CTO assessment complete"`); read the CoS gap analysis for context.

## Success Criteria

- [ ] Codebase map + schema in Tier 2; build pipeline tested; tech debt ranked
- [ ] Assessment published; Warroom briefed; CPO notified
