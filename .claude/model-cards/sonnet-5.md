<!-- model-card: Sonnet 5 (mechanical bulk crews; minor deltas apply to Sonnet 4.6). Source: platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5. Cached 2026-07-16 — refresh on Anthropic revision or a newer model. -->

# Prompting Sonnet 5 — mechanical / parallel crews

- Most literal tier, strictest low-end effort adherence: at low/medium it does exactly what's written and no more. Write complete, ordered, numbered steps for mechanical work.
- Spell out every scope, edge case, and done-condition; don't rely on inference.
- Name when and how to use each tool; with thinking off it under-reaches — add an explicit nudge.
- Effort: high default; medium ≈ old 4.6-high (the crew cost setting); xhigh only for its hardest work.
- Leave max_tokens headroom — the new tokenizer runs ~30% more tokens than 4.6.
- More agentic than 4.6 out of the box: delete old anti-laziness and forced-progress scaffolding.
- Conservative-reporting instructions are followed literally (reviews: ask for coverage, filter downstream).
- Tell it about compaction / the harness so it doesn't wrap up early near the context limit.
- No temperature knob — get variety and style from the prompt (positive examples).
