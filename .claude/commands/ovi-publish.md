---
description: Compute or publish weekly Cabinet OVI.
argument-hint: "<YYYY-MM-DD week start>"
allowed-tools: Bash
---

Use the `ovi-publish` skill. If `$ARGUMENTS` is empty, determine the current
week start before running commands.

Compute first:

```bash
python3 cabinet/scripts/org-runtime.py ovi compute --week-start "$ARGUMENTS"
```

Publish only if the verified value and burden inputs are known, or if the
current work graph state already contains verified value:

```bash
python3 cabinet/scripts/org-runtime.py ovi publish --week-start "$ARGUMENTS" --actor cos
```

If publishing a digest, sanitize it through:

```bash
python3 cabinet/scripts/org-runtime.py digest publish-sanitized --week-start "$ARGUMENTS" --title "<title>" --content-file <path> --actor cos
```
