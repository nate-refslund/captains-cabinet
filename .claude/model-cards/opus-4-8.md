<!-- model-card: Opus 4.8 (officer fleet). Source: platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-4-8 + models/migration-guide (4.8 deltas). Cached 2026-07-16 — refresh when Anthropic revises that page or a newer Opus ships. -->

# Prompting Opus 4.8 — the officer / orchestrator model

- Literal follower: state scope explicitly ("every section, not just the first"). It won't generalize an instruction past its stated reach.
- Calm imperatives. Reserve MUST/CRITICAL for irreversible or external actions — aggressive language over-triggers on 4.8.
- Steer format with a positive example at the target length, not "don't" lists.
- Narrates a lot by default: for a terse agent add a silence-default ("write only when you find something, change direction, or hit a blocker — one sentence each").
- Asks a lot by default: grant micro-autonomy ("minor reversible choices: pick a sensible option and note it; ask only on scope changes or destructive actions").
- Under-reaches for search / subagents / memory / custom tools: put "call this when…" trigger conditions in each tool description and in the prompt.
- Full task spec in the first turn; effort xhigh for coding/agentic, min high elsewhere; sweep, don't assume.
- Give the reason, not just the request — it generalizes from motivation.
- Mid-run operator note: a role:"system" message in messages[] is honored (4.8 only, cache-safe).
