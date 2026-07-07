---
name: ovi-publish
description: Use when computing or publishing weekly OVI and sanitized learning digests for Captain's Cabinet.
argument-hint: "<YYYY-MM-DD week start>"
allowed-tools: Bash
---

# OVI Publish

OVI is verified value divided by burden. Publish only from verified work or explicit fixture inputs.

## Slash usage (`/ovi-publish <YYYY-MM-DD week start>`)

- No argument → determine the current week start (Monday of the current ISO week) before running anything.
- Always `ovi compute` first; run `ovi publish` only when the verified value and burden inputs are known, or the current work-graph state already contains verified value.

Use:

```bash
python3 cabinet/scripts/org-runtime.py ovi compute --week-start YYYY-MM-DD
python3 cabinet/scripts/org-runtime.py ovi publish --week-start YYYY-MM-DD --actor cos
python3 cabinet/scripts/org-runtime.py digest publish-sanitized --week-start YYYY-MM-DD --title "<title>" --content-file <path> --actor cos
```

Sanitized digests must not expose secrets, private identifiers, sensitive URLs, personal email addresses, or legacy product names unless deliberately approved.
