---
description: Mark a mission work-graph node done from this officer session. Emits work_item_completed event + optionally work_item_verified.
argument-hint: "<task_id> [--evidence <text>|--verify]"
allowed-tools: Bash
---

Use when an officer finishes a mission task and needs to mark it complete in
the durable work graph. Emits the right event for the mission compiler's
event-sourced status overlay so the task doesn't get re-injected next
session.

```bash
bash cabinet/scripts/work-graph-complete.sh $ARGUMENTS
```

Two outcomes:

- **Default**: emits `work_item_completed` with the task_id and outcome_id.
- **`--verify`**: also emits `work_item_verified` so the verifier_role's
  acceptance is recorded. Use only when verification evidence has been
  collected per the spec.

The mission supervisor's next tick (or `/cabinet-route-tasks`) will then
release any downstream nodes whose dependencies are now satisfied.

The `cabinet-work-graph-complete` skill at
`.claude/skills/cabinet-work-graph-complete/` has the full evidence /
verifier flow.
