---
name: org-status
description: Inspect current org runtime state, Claude native task projections, missions, roles, OVI, and recent org events.
argument-hint: "[mission_id|task_id|role_slug]"
allowed-tools: Bash
---

# Org Status

## Slash usage (`/org-status [mission_id|task_id|role_slug]`)

- `mission_*` id → `python3 cabinet/scripts/org-runtime.py missions status "<arg>"`
- `task_*` id → `python3 cabinet/scripts/org-runtime.py claude-tasks show "<arg>"`
- a role slug → `python3 cabinet/scripts/org-runtime.py roles show --role "<arg>"`.
  Valid slugs are whatever `roles list` / `instance/config/roster.yml` says is
  active — never a hardcoded fleet (the live portfolio roster is cos,
  polads-ceo, stephie-ceo, comms-officer).
- no argument → run the standing checks below.

Use the local org runtime CLI for durable state checks:

```bash
python3 cabinet/scripts/org-runtime.py org-event list --limit 20
python3 cabinet/scripts/org-runtime.py claude-tasks list --limit 20
python3 cabinet/scripts/org-runtime.py tasks drift-report
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
