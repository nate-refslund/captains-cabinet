---
description: Activate an existing project for Captain's Cabinet.
argument-hint: "<slug> --repo-path <path> --name <name>"
allowed-tools: Bash
---

Activate an existing project with the Cabinet project activation contract.

Use:

```bash
bash cabinet/scripts/activate-project.sh $ARGUMENTS --activate
```

Then show the active state:

```bash
python3 cabinet/scripts/org-runtime.py org-event list --limit 10
python3 cabinet/scripts/org-runtime.py claude-tasks list --limit 20
```

If the project is not ready to become active yet, run the same command without
`--activate` and report the prepared project config path.
