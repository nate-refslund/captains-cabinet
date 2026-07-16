<!-- model-card: Fable 5 (orchestrator + judgment subagents). Source: platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5. Cached 2026-07-16 — refresh on Anthropic revision or a newer model. -->

# Prompting Fable 5 — orchestrator + judges / planners / verifiers

- De-prescribe: give goal + constraints, not step recipes. Prior-model scaffolding measurably degrades its output.
- One brief instruction ≈ an enumerated behavior list — trust it to generalize.
- State boundaries: "a problem described is not a fix requested — report findings and stop." It takes adjacent unrequested actions otherwise.
- Long runs: require evidence-grounded progress ("audit each status claim against a tool result from this session") — nearly eliminates fabricated status.
- Verify with fresh-context verifier subagents on a cadence; that beats self-critique.
- Delegate freely to async parallel subagents; say explicitly when to delegate.
- Give it a lessons file: one lesson per file, one-line summary, update don't duplicate, delete wrong notes.
- Autonomous pipelines: add an anti-early-stop reminder; never surface context-budget countdowns.
- Never ask it to transcribe or echo its own reasoning — it triggers a reasoning-extraction refusal and falls back to Opus.
- Expect minutes-long turns; thinking is always on; effort high default, low/medium still strong for routine work.
