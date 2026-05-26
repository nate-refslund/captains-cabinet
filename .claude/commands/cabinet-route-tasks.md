---
description: Manually trigger the mission supervisor to route ready work-graph tasks to officers. Normally runs every 5 minutes via cron.
argument-hint: "[--dry-run|--mission <mission_id>]"
allowed-tools: Bash
---

Force the mission supervisor to scan all active missions for ready tasks
and route them to officers. Useful right after a Captain ratifies a new
outcome (don't wait the 5-minute cron tick) or right after a batch of
completions has changed the ready set.

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
