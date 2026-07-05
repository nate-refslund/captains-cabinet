---
name: cabinet-work-graph-complete
description: After an officer finishes a mission task, record the completion (or failure or verification) to the event ledger so the work graph advances and the next ready task surfaces to the next session.
---

# Cabinet — Mark Mission Task Complete

## When to use

Invoke this skill whenever an officer has just finished work that corresponds to a mission work-graph node. Trigger phrases:

- "I just shipped X" / "X is done"
- "PR merged for X" / "deploy succeeded for X"
- The session-task-inject hook injected a task at session start; you've now done it.
- Validator officer is signing off on someone else's work (use `--status verified`).

## How

Use the existing convergence script:

```bash
bash cabinet/scripts/work-graph-complete.sh <node_id> --status done --evidence <file_or_inline_text>
```

Where:

- `<node_id>` is either shape the work graph uses (both accepted since 2026-07-05):
  - a compiler-generated task id `<outcome_id>-task-NNN` (string criteria), or
  - a **ratified explicit `node_id` from `instance/config/outcomes.yml`** (e.g. `polads-001-ci`, `sys-001-parity`) — the script resolves the owning outcome from the outcomes file itself, since these ids are not string-prefixed with their outcome id. An id in neither shape exits 2 without emitting (a typo never mints a completion).

  Find the id in the session-task-inject context or via `python3 -m framework.missions.supervisor --json --dry-run`.
- `--status` is one of `done` (default), `failed`, or `verified`.
- `--evidence` is either a path to an evidence file (e.g., test output, deploy log) or inline text describing what was accomplished.

The script emits the appropriate event (`work_item_completed`, `work_item_failed`, or `work_item_verified`) into the org ledger, which the compiler will overlay onto the work graph at the next session start so completed tasks don't re-inject.

## Example

After shipping the auth endpoint:

```bash
bash cabinet/scripts/work-graph-complete.sh \
  outcome-launch-mvp-task-002 \
  --status done \
  --evidence /tmp/deploy-output.log
```

Returns the emitted event UUID on stdout. Status message on stderr.

## Don't

- Don't manually edit `mission_steps` or `work_graph_nodes` rows — the event ledger is the source of truth.
- Don't fire `--status verified` on your own work — validators verify, executors complete.
- Don't include sensitive evidence (production credentials, raw PII) inline — pass a file path instead so the JSONL log doesn't keep secrets.
