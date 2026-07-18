---
description: Trigger a manual Cabinet briefing (scheduled slots come from platform.yml `briefing_times`, fleet default 07:30/19:30). Compiles state across missions, OVI, founder-action items, recent decisions.
argument-hint: "[morning|evening|now]"
allowed-tools: Bash
---

Trigger a Cabinet briefing on demand. Normally CoS runs this twice daily via
LaunchAgent / cron; use this command to force an out-of-cycle briefing.

Default to the morning template unless `$ARGUMENTS` specifies otherwise.

```bash
bash cabinet/cron/briefing.sh ${ARGUMENTS:-morning}
```

The briefing assembles:

- Top 5 active missions + their work-graph status
- Latest weekly OVI snapshot
- Open founder-action items (overdue first)
- Captain decisions since the last briefing
- Officer trigger queue depths (Redis)

Briefing output goes to the Captain's dashboard + the warroom group via
`send-to-group.sh`. Don't run during the morning's already-fired window
unless the prior briefing was visibly broken.
