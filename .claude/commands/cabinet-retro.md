---
description: Trigger the 48-hour cross-officer retro (CoS-owned). Reviews handoff quality, trigger responsiveness, captain-intent ledger, and produces process-improvement proposals.
argument-hint: "[--force|--since <ISO date>]"
allowed-tools: Bash
---

Run the cross-officer retro. Normally fires when 5 reflections have
accumulated OR 48h has elapsed (whichever first); use this command to
force an early retro.

```bash
bash cabinet/cron/retro-trigger.sh $ARGUMENTS
```

Retro deliverables:

- Cross-officer handoff quality audit (look for late triggers, ignored notifications)
- Captain-Seat Review (Part 1c, Captain-ratified 2026-07-26): the read-only
  evidence pack (`cabinet/scripts/meta-cognition/captain-seat-pack.sh`) handed
  to a fresh context that relives the window AS the Captain — at most 3
  findings, each citing an artifact of his own and a cost paid IN-WINDOW, each
  naming one mechanical fix; a quiet, healthy window yields NO FINDINGS
- Captain-intent ledger scan — append new latent goals to `shared/interfaces/captain-intents.md`
- Skill promotion candidates (validated drafts → foundation)
- Role evolution proposals (with Captain ratification required before apply)
- Process-improvement proposals for Captain approval
- Part 5 consolidation (MANDATORY terminal step): 3–5 distilled cross-officer
  beliefs — at least one failure-pattern — queued to Cabinet Memory as
  `consolidated_belief` / `trust: reflection` rows (never `trust: captain`);
  plus the boot-pack freshness tell (`memory-distill.py --check`) when the
  captain-law digest is in use

Read `memory/skills/cross-officer-retro.md` (or the lifted skill
`.claude/skills/cross-officer-retro/`) for the full procedure before running.
