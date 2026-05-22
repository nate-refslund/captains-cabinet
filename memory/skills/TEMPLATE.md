---
name: [skill-name-kebab-case]
description: [one-line trigger description — loaded at session start for progressive-disclosure discovery; should make trigger conditions obvious so the model can route correctly]
status: draft
author: [officer slug or "foundation"]
date: YYYY-MM-DD
validated_against: []
usage_count: 0
---

# Skill: [Skill Display Name]

> **SKILL.md spec compliance** (Captain ratified 2026-05-18 msg 2540, Move 2). YAML frontmatter above is the discovery contract — `name` + `description` load at session start; full body loads only when matched. Keep `description` action-trigger-shaped: agent reads it and decides whether the skill applies.

## Status Lifecycle

- `draft` — Written by an officer based on repeated experience. Not yet validated.
- `validated` — CoS has tested against validation scenarios. Ready for Captain approval.
- `promoted` — Captain-approved. Officers follow this skill when trigger conditions match.
- `under-review` — Demotion signal detected (failures citing this skill, unused in domain, or superseded). CoS is investigating.
- `archived` — No longer active. Kept with reason notes so it isn't re-invented. Can be restored if conditions change.

## When to Use

[Describe the trigger conditions — when should an Officer use this skill? Should mirror the frontmatter `description` but with more detail. Be concrete; agents match on this text.]

## Procedure

[Step-by-step procedure. Be specific and concrete.]

1. ...
2. ...
3. ...

## Expected Outcome

[What does success look like?]

## Known Pitfalls

[What can go wrong? List gotchas discovered from experience records.]

## Validation Scenarios

[Specific test cases this skill was validated against before promotion.]

- Scenario 1: [input] → [expected output]
- Scenario 2: [input] → [expected output]

## Origin

[Link to the experience records that led to this skill being created.]

---

## Notes on the SKILL.md contract

The open SKILL.md spec ([agent-skills procedural memory](https://arxiv.org/html/2602.12430v3)) is the community-portable format for agent skills. Cabinet adopts it for two compounding benefits:

1. **Progressive disclosure** — only the frontmatter `name` + `description` loads at session start (cheap). The full body loads when an officer's task matches the description trigger (just-in-time, expensive).
2. **Portability** — skills can be shared/imported across compatible agent platforms (Anthropic Agent Skills, community frameworks). We can publish ours; we can import theirs.

Discovery contract:
- `name` is unique within `memory/skills/` (kebab-case)
- `description` is one line, action-trigger-shaped, ~15-30 words. Anti-pattern: "this is a skill about X" — write trigger conditions, not category labels.
- Status filtering at load: `draft` and `under-review` skills are visible but flagged; `archived` skills do not load.
- Migration policy: existing skills in `memory/skills/` are migrated to this format incrementally; foundation skills retain their content but gain frontmatter on next touch.
