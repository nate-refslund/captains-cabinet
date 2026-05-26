# Org Runtime Native Rule

Claude Code is the working surface. The org runtime is the durable truth.

- Use native Claude Code Tasks for active execution, but include Cabinet metadata so task hooks can project work into `org_events` and `claude_native_tasks`.
- Treat `org_events` as the first durable record for meaningful organizational transitions: mission changes, role work, task lifecycle, evidence, verification, policy decisions, and learning.
- Do not make `/tasks`, markdown notes, Redis state, Telegram text, or local memory the only source for a state transition.
- If a native Task lacks a mission, node, owner role, acceptance criteria, evidence requirement, verifier role, or risk level, add the missing metadata before relying on it as Cabinet work.
- `/tasks` is a compatibility projection until the cutover is complete; prefer mission/work-graph state for new work.
- Hooks and broker decisions should carry role, mission, node, risk, and evidence context whenever that context is available.
