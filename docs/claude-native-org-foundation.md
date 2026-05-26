# Claude Code Native Org Foundation

This branch makes Claude Code's native surfaces the front door for Captain's
Cabinet, while keeping `org_events` as the durable organization truth.

## What Is Native Now

- `.claude/settings.json` registers `TaskCreated` and `TaskCompleted` hooks.
- `cabinet/scripts/claude-task-bridge.py` records native Task lifecycle events.
- `claude_native_tasks` projects current native Task state for local SQLite and
  the Postgres schema contract.
- `.claude/skills/*` teaches officers how to create Cabinet-shaped native
  Tasks, inspect org status, compile missions, and publish OVI.
- `.claude/commands/*` exposes `/org-status`, `/mission-compile`,
  `/ovi-publish`, and `/role-eval` as project slash commands.
- `.claude/rules/org-runtime-native.md` states the core invariant: Claude Code
  is the working surface, `org_events` is durable truth.
- `.claude/agents/*.md` now have frontmatter so they can act as native custom
  subagent definitions instead of only role manuals.

## Task Metadata Contract

Every material Claude Code Task should include:

```text
mission_id: <mission id or unassigned>
node_id: <work graph node id or unassigned>
owner_role: <cos|cto|cpo|cro|coo>
acceptance_criteria: <observable finish condition>
evidence_required: <artifact, test, metric, or review needed>
verifier_role: <role that verifies completion>
risk_level: <low|medium|high>
```

Warn mode is the default. Missing metadata produces a system message but still
records the task. Enforcement is intentionally left for the policy-broker phase:

```bash
CABINET_TASK_BRIDGE_MODE=enforce
```

## Verification

Run:

```bash
bash cabinet/scripts/test-claude-native-task-bridge.sh
bash cabinet/scripts/test-org-runtime.sh
```

## Next Cutover Work

- Start officer sessions through native `--agent` or equivalent once the local
  Claude Code launch path is validated against the installed CLI.
- Project `/tasks` from `claude_native_tasks` and work graph nodes instead of
  treating `/tasks` as an independent source of truth.
- Move policy shadow toward broker enforcement with role and mission context
  from native Tasks.
- Extend the mission compiler beyond the current one-node fixture so native
  Tasks are generated from real multi-node missions.
