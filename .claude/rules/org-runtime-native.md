# Org Runtime Native Rule

Claude Code is the working surface. The org runtime is the durable truth.

- Use native Claude Code Tasks for active execution, but include the Cabinet
  metadata the org-runtime schema requires so task hooks can project work into
  `org_events` and `claude_native_tasks`. **The required field-set is owned by
  the schema** (`framework/schemas-base.sql` + `framework/events/schema.sql`) —
  consult it, don't re-enumerate it here. As of this writing it covers mission,
  node, owner role, acceptance criteria, evidence requirement, verifier role,
  and risk level; a native Task missing what the schema requires is not yet
  Cabinet work — add the metadata first.
- Treat `org_events` as the first durable record for meaningful organizational
  transitions (mission changes, role work, task lifecycle, evidence,
  verification, policy decisions, learning). Do not let `/tasks`, markdown
  notes, Redis state, Telegram text, or local memory be the ONLY source for a
  state transition.
- `/tasks` is a compatibility projection until cutover; prefer mission/work-graph
  state for new work. Hooks and broker decisions carry the schema's
  role/mission/node/risk/evidence context whenever it is available.
