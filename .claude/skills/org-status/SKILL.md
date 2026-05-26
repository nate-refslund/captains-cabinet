---
name: org-status
description: Inspect current org runtime state, Claude native task projections, missions, roles, OVI, and recent org events.
---

# Org Status

Use the local org runtime CLI for durable state checks:

```bash
python3 cabinet/scripts/org-runtime.py org-event list --limit 20
python3 cabinet/scripts/org-runtime.py claude-tasks list --limit 20
python3 cabinet/scripts/org-runtime.py roles list
```

For a mission:

```bash
python3 cabinet/scripts/org-runtime.py missions status <mission_id>
```

For a native Task projection:

```bash
python3 cabinet/scripts/org-runtime.py claude-tasks show <task_id>
```

Prefer this state over transient chat memory when deciding what is assigned, blocked, complete, or ready for verification.
