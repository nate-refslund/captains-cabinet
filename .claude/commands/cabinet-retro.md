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
- Captain-intent ledger scan — append new latent goals to `shared/interfaces/captain-intents.md`
- Skill promotion candidates (validated drafts → foundation)
- Role evolution proposals (with Captain ratification required before apply)
- Process-improvement proposals for Captain approval

Read `memory/skills/cross-officer-retro.md` (or the lifted skill
`.claude/skills/cross-officer-retro/`) for the full procedure before running.
