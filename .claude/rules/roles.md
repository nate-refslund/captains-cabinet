---
globs:
  - "framework/roles/**"
  - "instance/roles/**"
  - ".claude/agents/*.md"
---

# Role Management Rules

- Create roles slowly. Adapt roles frequently. Use hats aggressively. Retire roles rarely.
- NEVER delete role learning — lineage is append-only, archive preserves all capabilities.
- Role changes require evidence (what triggered this) and rationale (why this change).
- Agent `.md` files in `.claude/agents/` include YAML frontmatter (description, model, effort, allowedTools).
- Role entities live in `instance/roles/active/` as YAML — these are the source of truth.
- Hats are temporary specializations with optional mission binding and expiry.
- Effective capabilities = base role capabilities + all active hat capabilities.
- Every role adaptation emits an event and appends to the lineage log.
