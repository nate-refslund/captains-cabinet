# Outcome-to-OVI Vertical Slice

This branch adds the first end-to-end organization runtime path for one product:
Captain's Cabinet.

## Build Acceptance vs Operational Proof

Build acceptance is code-level proof:

- Active product/context is `captains-cabinet`.
- One Captain-ratified outcome compiles into a mission/work graph.
- One role hat is assigned through `mission_role_assignments`.
- One work-graph node is verified.
- One OVI week is published as value-per-burden.
- One sanitized learning digest is published.
- Every transition lands in append-only `org_events`.

Branch 2 extends that slice with durable adaptive roles:

- `org_roles` is the current projection for persistent role identity.
- Officer sessions are execution surfaces referenced by `officer_session_slug`;
  they are not the organizational identity.
- Role memory, evals, recommendations, and lineage are append-only history.
- Missions and hats require an active role entity.
- Role evolution requires Captain ratification and increments role version.

Operational proof is live runtime evidence after this branch:

- Weekly OVI is published for Captain's Cabinet.
- Full goal proof requires three consecutive real weekly OVI publications with
  positive trend.
- `cabinet/cron/ovi-weekly.sh` triggers CoS to run the weekly publication path.

## CLI

The local/CI CLI uses SQLite by default so it can run without live Neon:

```bash
python3 cabinet/scripts/org-runtime.py outcomes propose \
  --title "Improve Cabinet autonomy per Captain attention" \
  --metric-name verified_outcome_value \
  --target-value 12
```

Main command groups:

- `org-event append/list`
- `outcomes propose/ratify/list`
- `missions compile/compile-plan/status/native-task-packets/complete`
- `claude-tasks list/show`
- `tasks drift-report`
- `roles define/list/show/bind-memory/evolve/record-eval/recommend`
- `roles assign-hat/show-lineage`
- `ovi compute/publish`
- `digest publish-sanitized`

The production schema contract is `cabinet/sql/045-org-runtime-slice.sql`.

## Durable Roles

The durable role loop is:

```text
role defined
↓
memory path bound
↓
mission compiled for active role
↓
temporary hat assigned
↓
work verified
↓
role eval evidence recorded
↓
deterministic recommendation emitted
↓
Captain-ratified role evolution applied
```

`roles recommend` is deliberately deterministic in this branch:

- `promote_hat_to_capability` after 2 passing evals for the same hat with
  score >= 0.8.
- `retire_role_review` after 3 consecutive failed evals and no active mission
  assignments.
- `adjust_charter` when the latest 3 evals average below 0.6.
- `continue_current_role` otherwise.

Retirement remains recommendation-only here. No command suspends officer
sessions or deletes role memory.

## OVI

OVI is a ratio, not a subtraction:

```text
OVI = verified_outcome_value / burden_index
```

The first burden index includes Captain attention minutes, Captain decision
count, spend, policy violations, verification debt, and safety debt. A positive
trend means the current published weekly ratio is higher than the previous
published weekly ratio.

## Typed Policy

`cabinet/scripts/policy-shadow.py` is shadow-only on this branch. It observes
the same hook input as `pre-tool-use.sh`, records structured decisions to
`org_events`, and is tested against live hook behavior. It does not replace
hook decisions yet.

## Claude Code Native Task Bridge

`cabinet/scripts/claude-task-bridge.py` handles Claude Code `TaskCreated` and
`TaskCompleted` hooks. It records `claude_task.created` and
`claude_task.completed` events in `org_events`, then projects the current view
into `claude_native_tasks`.

The bridge expects Claude Tasks to carry Cabinet metadata:

```text
mission_id: <mission id or unassigned>
node_id: <work graph node id or unassigned>
owner_role: <cos|cto|cpo|cro|coo>
acceptance_criteria: <observable finish condition>
evidence_required: <artifact, test, metric, or review needed>
verifier_role: <role that verifies completion>
risk_level: <low|medium|high>
```

Default mode is warn-only. Set `CABINET_TASK_BRIDGE_MODE=enforce` only after
the warning stream has proven reliable enough for blocking.

## Mission Compiler v2

`missions compile-plan` accepts a JSON mission plan with multiple nodes,
dependencies, acceptance criteria, evidence requirements, verifier roles, risk,
rollback notes, budget notes, and Captain-attention estimates. Use
`missions native-task-packets <mission_id>` to produce Claude Task-ready
metadata blocks for each work-graph node.

`tasks drift-report` is read-only. It compares legacy `/tasks` rows,
work-graph nodes, and Claude native task projections before any `/tasks`
cutover work replaces the legacy source.
