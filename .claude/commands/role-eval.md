---
description: Record role evaluation evidence and derive deterministic evolution recommendations.
argument-hint: "<role_slug>"
allowed-tools: Bash
---

Use this command only when there is concrete evidence for the role evaluation.

For role `$ARGUMENTS`, record the eval:

```bash
python3 cabinet/scripts/org-runtime.py roles record-eval --role "$ARGUMENTS" --eval-name "<eval>" --score <0-1> --evidence "<evidence>" --actor evaluator
```

Then emit a deterministic recommendation:

```bash
python3 cabinet/scripts/org-runtime.py roles recommend --role "$ARGUMENTS" --actor evaluator
```

Role evolution still requires Captain ratification before applying `roles evolve`.
