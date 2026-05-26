---
name: cabinet-route-tasks
description: Manually trigger the mission supervisor to route ready work-graph tasks to officers (normally runs as a 5-minute cron) — use after declaring a new Captain outcome or after a flood of completions changed the ready set.
---

# Cabinet — Route Ready Mission Tasks

## When to use

Normal operation runs `mission-supervisor.sh` every 5 minutes via cron / LaunchAgent. Manually invoke this skill when:

- A Captain just ratified a new outcome and you want officers notified before the next cron tick.
- A batch of tasks just completed (via `work-graph-complete.sh`) and downstream tasks became ready — accelerate the routing.
- Debugging why an officer isn't seeing a task they should have.

## How

Dry-run first to see what WOULD be routed without committing:

```bash
bash cabinet/cron/mission-supervisor.sh --dry-run --json
```

Production run (emits `work_item_assigned` events + pushes Redis Stream triggers):

```bash
bash cabinet/cron/mission-supervisor.sh
```

JSON output mode (machine-readable for chaining):

```bash
bash cabinet/cron/mission-supervisor.sh --json
```

Idempotent — re-running routes 0 tasks until something new becomes ready.

## What it does (under the hood)

1. Reads `instance/config/outcomes.yml`, compiles active outcomes via `framework.missions.compiler.compile_from_yaml`.
2. The compiler replays `work_item_completed` / `work_item_failed` / `work_item_verified` events to overlay current status (Phase 1.1 of convergence).
3. Calls `ready_tasks()` on each work graph — tasks whose dependencies are DONE and status is PENDING.
4. Filters out tasks where a `work_item_assigned` event was already emitted (replay-based idempotency).
5. For each remaining task with an `assigned_role`, emits `work_item_assigned` and pushes a Redis Stream message into `cabinet:triggers:<officer>` via `lib/triggers.sh::trigger_send`.
6. Officers receive the trigger on their next tool call (auto-delivered by `post-tool-use.sh`).

## Don't

- Don't run this in a tight loop expecting to "force" a task to a different officer — role assignment is keyword-matched against role capabilities in the compiler; change the role's charter instead.
- Don't push Redis triggers manually outside this script — bypassing the idempotency check leads to duplicate notifications.
