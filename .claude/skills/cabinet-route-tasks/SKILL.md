---
name: cabinet-route-tasks
description: Manually run the mission supervisor to push ready work-graph tasks to officers as Redis triggers. NOT scheduled anywhere — routing is PULL-ONLY (Captain ruling): officers pull their ratified missions from instance/config/outcomes.yml on every self-wake tick. Use this only as a push-nudge after declaring a new outcome, or to debug why a task isn't surfacing.
---

# Cabinet — Route Ready Mission Tasks (manual push-nudge)

## How routing actually works (pull-only — read this first)

There is **no cron / LaunchAgent running the mission supervisor**. The Captain
ruled routing PULL-ONLY for now: `mission-supervisor` is deliberately absent
from `cabinet/services.yml` (the fleet manifest) and not installed in
`~/Library/LaunchAgents`. Instead, each officer's self-wake loop prompt
(`cabinet/loop-prompts/<officer>.txt`, re-armed by `officer-supervisor-mac.sh`
every 2h) instructs them to PULL their ACTIVE ratified missions from
`instance/config/outcomes.yml` (their `owner_role` nodes) as standing work on
every tick — an empty trigger stream is NOT "nothing due"; the wake mechanism
delivers triggers, not missions.

This skill is the manual PUSH complement: running the supervisor emits
`work_item_assigned` events and Redis Stream triggers so an officer is nudged
about a ready task *now* instead of on their next pull tick.

## When to use

- A Captain just ratified a new outcome and you want officers nudged before
  their next self-wake tick.
- A batch of tasks just completed (via `work-graph-complete.sh`) and downstream
  tasks became ready — accelerate the hand-off.
- Debugging why an officer isn't seeing a task they should have (the `--dry-run`
  output shows exactly what the compiler considers ready and for whom).

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

- Don't schedule this as a cron/LaunchAgent or a permanent `/loop` — that would
  reintroduce push routing against the pull-only ruling. If the Captain re-rules
  push routing, the scheduled entry belongs in `cabinet/services.yml`, not here.
- Don't run this in a tight loop expecting to "force" a task to a different officer — role assignment is keyword-matched against role capabilities in the compiler; change the role's charter instead.
- Don't push Redis triggers manually outside this script — bypassing the idempotency check leads to duplicate notifications.
