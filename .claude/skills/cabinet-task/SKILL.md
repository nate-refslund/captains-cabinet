---
name: cabinet-task
description: Use when creating, updating, or completing Claude Code native Tasks for Captain's Cabinet work.
---

# Cabinet Task

Claude Code native Tasks are the execution surface. Cabinet org events are the durable record underneath.

When creating or updating a Task, include a Cabinet metadata block in the task description:

```text
mission_id: <mission id or unassigned>
node_id: <work graph node id or unassigned>
owner_role: <cos|cto|cpo|cro|coo>
acceptance_criteria: <observable finish condition>
evidence_required: <artifact, test, metric, or review needed>
verifier_role: <role that verifies completion>
risk_level: <low|medium|high>
```

If no mission or node exists yet, use `mission-compile` first when the work is material. For a small exploratory task, mark `mission_id: unassigned` and `node_id: unassigned`, then link it once the mission is compiled.

Completion requires evidence. Before marking a Task complete, make sure the evidence requirement is satisfied or explicitly state what remains unverified.
