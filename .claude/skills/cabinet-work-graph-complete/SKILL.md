---
name: cabinet-work-graph-complete
description: After an officer finishes a mission task, record the completion (or failure or verification) to the event ledger so the work graph advances and the next ready task surfaces to the next session.
argument-hint: "<node_id> [--status done|failed|verified] [--evidence <text-or-file>]"
allowed-tools: Bash
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
  - a **ratified explicit `node_id` from `instance/config/outcomes.yml`** (e.g. `acme-001-ci`, `sys-001-parity`) — the script resolves the owning outcome from the outcomes file itself, since these ids are not string-prefixed with their outcome id. An id in neither shape exits 2 without emitting (a typo never mints a completion).

  Find the id in the session-task-inject context or via `python3 -m framework.missions.supervisor --json --dry-run`.
- `--status` is one of `done` (default), `failed`, or `verified`.
- `--actor ROLE` names who is recording the event (overrides `OFFICER_NAME`). Optional for `done`/`failed`; **required for `verified`** — see "Don't" below.
- `--evidence` is either a path to an evidence file (e.g., test output, deploy log) or inline text describing what was accomplished.

The script emits the appropriate event (`work_item_completed`, `work_item_failed`, or `work_item_verified`) into the org ledger, which the compiler will overlay onto the work graph at the next session start so completed tasks don't re-inject. The mission supervisor's next tick (or a manual `/cabinet-route-tasks` push-nudge) then releases any downstream nodes whose dependencies are now satisfied.

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
- Don't fire `--status verified` on your own work — validators verify, executors complete. **This is now enforced, not just asked**: `--status verified` requires an attributed actor (`--actor ROLE`, or `OFFICER_NAME`; the `system` fallback exits 2), and the compiler's status overlay refuses to credit a verification whose actor is the node's own owner, or is not the node's declared `verifier_role`. A refused verification still records completion — it just doesn't count as verified. The actor is self-asserted, so this separates duties; it is not authentication.
- Don't include sensitive evidence (production credentials, raw PII) inline — pass a file path instead so the JSONL log doesn't keep secrets.
