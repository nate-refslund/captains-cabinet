# Cabinet Convergence Analysis — 2026-05-26

**Captain:** Nate
**Method:** Four parallel deep-analysis subagents (Sonnet 4.6) + synthesis (Opus 4.7 1M)
**Branches compared:** `claude/funny-fermi-8daf32` (≈ master) vs `claude/clever-tesla-CS3Su-rebuild`

---

## Executive Recommendation

**Use `claude/clever-tesla-CS3Su-rebuild` as the structural foundation.** Selectively backport 5 high-value capabilities from master (Captain triplet, battle-hardened safety hooks, voice/image comms stack, Library knowledge system, CI test corpus). Add 9 net-new completions identified by research (close mission loops, OVI data wiring, role evals, transactional outbox, mission supervisor, hat graduation, latest CC adoption, task-system adapters, product-bootstrap). Sequence into 10 phases on a `claude/convergence` branch, executed continuously via `/loop` until MacMini-deployable.

**Net composition:** 60% rebuild architecture + 25% master backport + 15% new.

**Why not the alternatives:**
- *Master-as-base*: would mean re-implementing the durable-role-system spine the rebuild already nailed (events, roles, missions, OVI, policy engine, native CC rules). Days vs. weeks of work.
- *Fresh rewrite*: throws away years of battle-hardening (the v3.7.2 prohibited-actions engine alone is irreplaceable).
- *50/50 merge*: leaves both halves half-finished. The rebuild's architecture needs to be the spine; master's assets are the cherry-picks.

---

## Files in this analysis

| File | Source | Length | Purpose |
|---|---|---|---|
| `00-INDEX.md` | this synthesis | short | navigation + exec summary |
| `01-branch-funny-fermi-analysis.md` | Agent A (Sonnet 4.6) | ~5000 words | deep dive: current branch (≈master) |
| `02-branch-rebuild-analysis.md` | Agent B (Sonnet 4.6) | ~5000 words | deep dive: rebuild branch |
| `03-claude-code-features.md` | Agent C (claude-code-guide) | ~5200 words | latest CC features research (May 2026) |
| `04-durable-role-system.md` | Agent D (Sonnet 4.6) | ~5500 words | role-system design research + reference architecture |
| `05-convergence-plan.md` | **main deliverable** | ~6000 words | recommendation + 10-phase implementation plan |

---

## How to read this analysis

- **5 minutes:** read `05-convergence-plan.md` sections 0–2 (executive, rationale, synthesis matrix).
- **20 minutes:** read all of `05-convergence-plan.md`.
- **Deep dive:** `01-` + `02-` for branch reality → `04-` for role-system theory → `05-` for synthesis. Use `03-` as a CC feature reference when implementing.

---

## Captain inputs already collected (2026-05-26)

1. **Captain triplet:** Restore captain-decisions/patterns/intents *and* use autoMemoryEnabled. Best of both.
2. **Branch base:** Cut `claude/convergence` from `origin/claude/clever-tesla-CS3Su-rebuild`. Preserve the rebuild's clean architecture history.
3. **CC risk appetite:** Go all-in on experimental features (Agent Teams, ToolSearch, /loop, /goal). **Constraint:** Max x20 subscription + personal OAuth, **no Anthropic API key**. All officers run as `claude` CLI processes, not direct API/SDK calls. Managed Agents (API-key feature) is OUT; Agent Teams (CC feature flag) is IN.
4. **Cadence:** Continuous `/loop` through all phases until MacMini-ready.

---

## Implementation kickoff (next `/goal`)

After this analysis is ratified, the implementation goal is:

> `/goal Execute the convergence plan at docs/convergence-analysis-2026-05-26/05-convergence-plan.md, phase by phase via /loop, until the MacMini-readiness checklist is fully green. Begin with Phase 0.`

Per the global Corridor MCP rule, every code-generation step during implementation will call `analyzePlan` first.

---

## Branch composition note

- Current branch (this worktree): `claude/funny-fermi-8daf32` (≈ master + 1 fix commit). Used purely as the source for backports.
- Target branch: `claude/convergence` (to be cut from `origin/claude/clever-tesla-CS3Su-rebuild` in Phase 0).
- Rebuild worktree: `/Users/nate/captains-cabinet/.claude/worktrees/rebuild-analysis/` (created for this analysis, detached HEAD at `a08bcac`).
