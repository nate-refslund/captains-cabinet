---
description: Compile a Captain goal into a Cabinet mission/work graph path.
argument-hint: "<Captain goal or outcome id>"
allowed-tools: Bash
---

Use the `mission-compile` skill. Turn `$ARGUMENTS` into a Cabinet mission plan.

If `$ARGUMENTS` is an existing outcome id, inspect it and compile a mission only
when it is ratified:

```bash
python3 cabinet/scripts/org-runtime.py outcomes list
python3 cabinet/scripts/org-runtime.py missions compile <outcome_id> --title "<mission title>" --node-title "<first node>" --owner-role <role> --actor cos
```

If `$ARGUMENTS` is a new Captain goal, propose the outcome first and do not
ratify it unless Captain approval is present in context:

```bash
python3 cabinet/scripts/org-runtime.py outcomes propose --title "<goal>" --metric-name verified_outcome_value --target-value <number> --actor cos
```

After compiling, create native Claude Tasks with Cabinet metadata for each work
graph node.
