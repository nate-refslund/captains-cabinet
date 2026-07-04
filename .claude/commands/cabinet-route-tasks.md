---
description: Manually run the mission supervisor to push ready work-graph tasks to officers. Not scheduled anywhere — routing is pull-only (officers pull missions from outcomes.yml each self-wake tick); this is the on-demand push-nudge.
argument-hint: "[--dry-run|--mission <mission_id>]"
allowed-tools: Bash
---

Run the mission supervisor to scan all active missions for ready tasks
and push them to officers as Redis triggers. There is NO cron/LaunchAgent
doing this — routing is PULL-ONLY (Captain ruling): officers pull their
ratified missions from `instance/config/outcomes.yml` on every self-wake
tick (`cabinet/loop-prompts/<officer>.txt`). Use this right after a Captain
ratifies a new outcome (nudge officers before their next tick) or right
after a batch of completions has changed the ready set.

Dry-run first to preview without committing:

```bash
bash cabinet/cron/mission-supervisor.sh --dry-run $ARGUMENTS
```

Then commit:

```bash
bash cabinet/cron/mission-supervisor.sh $ARGUMENTS
```

The supervisor:

1. Loads every active mission's work graph from the event ledger
2. Identifies ready nodes (all dependencies DONE, status==PENDING)
3. Pushes a trigger to each ready task's `assigned_role` via Redis Streams
4. Emits `work_item_assigned` events for the outbox relay

The `cabinet-route-tasks` skill at `.claude/skills/cabinet-route-tasks/`
has the full operator's guide.
