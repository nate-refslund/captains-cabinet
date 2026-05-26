---
description: Show durable Cabinet org runtime status.
argument-hint: "[mission_id|task_id|role_slug]"
allowed-tools: Bash
---

Show current Cabinet org runtime status using the local CLI.

If `$ARGUMENTS` looks like a `mission_*` id, run:

```bash
python3 cabinet/scripts/org-runtime.py missions status "$ARGUMENTS"
```

If `$ARGUMENTS` looks like a `task_*` id, run:

```bash
python3 cabinet/scripts/org-runtime.py claude-tasks show "$ARGUMENTS"
```

If `$ARGUMENTS` is one of `cos`, `cto`, `cpo`, `cro`, or `coo`, run:

```bash
python3 cabinet/scripts/org-runtime.py roles show --role "$ARGUMENTS"
```

Otherwise show:

```bash
python3 cabinet/scripts/org-runtime.py claude-tasks list --limit 20
python3 cabinet/scripts/org-runtime.py tasks drift-report
python3 cabinet/scripts/org-runtime.py roles list
python3 cabinet/scripts/org-runtime.py org-event list --limit 20
```
