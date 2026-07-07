# Role Registry

*Last updated: 2026-06-10 — Preset-derived roster reframe*

---

## Active Officers — preset-derived

The officer roster is **derived from the active preset + instance roster**,
not hardcoded here. Per deployment, the operational source of truth is
`instance/roles/active/*.yml` — seeded and refreshed by
`cabinet/scripts/bootstrap-roles.sh` (from `instance/config/roster.yml`
when present, otherwise the built-in functional seed), with
`officer_type:` distinguishing always-on **fulltime** officers from
on-demand **consultants**.

### `work` preset (functional, single product)

| Officer | Role | Domain |
|---------|------|--------|
| Chief of Staff (CoS) | Orchestrator | Captain comms, org management, briefings, hooks ownership, pipeline monitoring, infrastructure |
| Chief Technology Officer (CTO) | Engineering Lead | Codebase, architecture, deploys, infrastructure, captain decision logging |
| Chief Research Officer (CRO) | Intelligence Lead | Research streams, pgvector storage, tech radar, research action pipeline |
| Chief Product Officer (CPO) | Product Lead | Product backlog, specs, prioritization, UX, pipeline ownership, proactive product audits |
| Chief Operating Officer (COO) | Operational Lead | Exploratory testing, Sentry triage, deployment validation, Playwright E2E, quality gate |

### `portfolio` preset (multi-lane)

| Officer | Role | Domain |
|---------|------|--------|
| Chair (officer id `cos`) | Orchestrator — fulltime, the ONLY Telegram-bot officer | Captain comms, intake, briefings, cross-lane coordination, captain-attention queue |
| `<lane>-ceo` (one per lane, e.g. `polads-ceo`, `stephie-ceo`) | Lane CEO — on-demand consultant, Telegram-dark | The lane end-to-end: stream + missions, codebase, boards, quality; functional depth via hats + Sonnet crew |

Other presets (`step-network`, `personal`, custom) declare their own
rosters the same way: preset agents + instance roster →
`bootstrap-roles.sh` → `instance/roles/active/`.

## Role Definitions

Each Officer's full role definition lives in `.claude/agents/<role>.md`,
populated by the preset loader from `presets/<active>/agents/` with
`instance/agents/` overlays (e.g. generated lane-CEO defs). These are
loaded into the Officer's context at session start.

## Shared Interfaces

| Interface | Location | Writers | Readers |
|-----------|----------|---------|---------|
| Product Specs | `shared/interfaces/product-specs/` | CPO | CTO, CoS |
| Research Briefs | `shared/interfaces/research-briefs/` | CRO | CPO, CoS, CTO |
| Deployment Status | `shared/interfaces/deployment-status.md` | CTO | CoS, CPO, COO |
| Operational Health | `shared/interfaces/operational-health.md` | COO | CoS, all Officers |
| Sprint Backlog | `shared/backlog.md` | CPO | CTO, CoS |
| Captain Decision Trail | `shared/interfaces/captain-decisions.md` | Any Officer (receiving) | All Officers (before UI/feature work) |
| Tech Radar | `shared/interfaces/tech-radar.md` | CRO | CoS, all Officers |
| Redis Triggers | `cabinet:triggers:<officer>` | Any Officer, Cron | Target Officer (via hook, auto-delivered) |
| Research Vector Store | PostgreSQL (pgvector) | CRO (embed), all (search) | All Officers |

## Hooks

| Hook | Location | Fires | Purpose |
|------|----------|-------|---------|
| post-tool-use.sh | `cabinet/scripts/hooks/` | After every tool call | Heartbeat, logging, cost, trigger delivery, idle detection, decision enforcement |
| pre-tool-use.sh | `cabinet/scripts/hooks/` | Before every tool call | Kill switch, spending limits, prohibited actions |
| post-compact.sh | `cabinet/scripts/hooks/` | After context compaction | Essential skill refresh to prevent behavioral drift |
| post-reply-voice.sh | `cabinet/scripts/hooks/` | After Telegram replies | Voice message generation (when enabled) |

## Organizational Notes

- CoS is the hub — all Captain communication flows through CoS unless the Captain messages an Officer directly
- CoS owns hooks and Cabinet infrastructure — other Officers propose changes through CoS
- CPO owns the work pipeline — CTO must never be idle due to CPO failing to feed work
- CRO research flows through the Research Action Pipeline — findings are tagged, owned, and tracked
- Officers interact organically — the Registry defines ownership, not workflows
- Any Officer can propose changes to this Registry via the self-improvement loop
- The Captain can restructure the entire organization by updating this file
