---
name: mission-compile
description: Use when turning a Captain goal or vague work request into a Cabinet mission and work graph.
argument-hint: "<Captain goal or outcome id>"
allowed-tools: Bash
---

# Mission Compile

Material Cabinet work should flow from Captain outcome to mission to work graph node to native Claude Task.

## Slash usage (`/mission-compile <Captain goal or outcome id>`)

- **Existing outcome id** → inspect first (`python3 cabinet/scripts/org-runtime.py outcomes list`), then compile a mission ONLY if the outcome is ratified.
- **New Captain goal** → propose the outcome and stop; never ratify unless Captain approval is present in context.
- After compiling, create native Claude Tasks carrying the Cabinet metadata the schema requires (see `.claude/rules/org-runtime-native.md`) for each work-graph node.

Minimum mission shape:

- Outcome or Captain goal being served
- Mission title
- Work graph nodes with owner roles
- Acceptance criteria
- Evidence requirement
- Verifier role
- Risk level
- Captain attention estimate

For the current vertical slice, use:

```bash
python3 cabinet/scripts/org-runtime.py outcomes propose --title "<outcome>" --metric-name verified_outcome_value --target-value <number> --actor cos
python3 cabinet/scripts/org-runtime.py outcomes ratify <outcome_id> --ratified-by captain --note "<approval note>"
python3 cabinet/scripts/org-runtime.py missions compile <outcome_id> --title "<mission>" --node-title "<first node>" --owner-role <role> --verifier-role <other-role> --actor cos
```

`--verifier-role` is required and may not equal `--owner-role`: work must not be
creatable in a state where only its own owner can sign it off. Completing a node
later requires that same verifier:

```bash
python3 cabinet/scripts/org-runtime.py missions complete <node_id> --verified-value <n> --verification-summary "<what was checked>" --actor <verifier-role>
```

`--actor` has no default — an unattributed verification fails rather than
silently crediting itself to `cos`. The actor is a self-asserted string, so this
separates duties (it stops self-dealing); it is not authentication.

For multi-node work, write a JSON plan and use:

```bash
python3 cabinet/scripts/org-runtime.py missions compile-plan <outcome_id> --plan-file <plan.json> --actor cos
python3 cabinet/scripts/org-runtime.py missions native-task-packets <mission_id>
```

Do not ratify a Captain outcome unless the Captain has actually approved it. If approval is not present, propose the outcome and leave it for review.
