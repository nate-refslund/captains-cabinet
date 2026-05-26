---
description: Trigger a CRO research sweep (normally every 4h). Scans configured sources for changes in market, competitors, regulatory, or Cabinet-relevant tech.
argument-hint: "[--topic <topic-slug>|--full]"
allowed-tools: Bash
---

Trigger the CRO research sweep on demand. Normally CRO runs this every 4h
via cron; force it here when the Captain asks for fresh research before the
next scheduled tick.

```bash
bash cabinet/cron/research-sweep.sh $ARGUMENTS
```

Output goes to:

- New research briefs embedded into the pgvector store (voyage-4-large)
- Tech radar updates at `shared/interfaces/tech-radar.md`
- Tagged findings per the action pipeline: `[ACTIONABLE]` / `[OPPORTUNITY]` / `[AWARENESS]`
- Captain visibility per `instance/config/platform.yml → communication.research_visibility`

Read `memory/skills/cro-research-sweep.md` for the full sweep methodology.
