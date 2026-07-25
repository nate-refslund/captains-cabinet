<!-- model-card: Opus 5 (orchestrator + judgment + execution). Source: platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5. Cached 2026-07-25 — refresh on Anthropic revision or a newer model. Lines marked [cabinet] are this org's own calibration, not vendor guidance. -->

# Prompting Opus 5 — the primary model

- Runs existing Opus 4.8 prompts well out of the box. Migration deltas: thinking is ON by default, and disabling it is capped at `high` effort.
- Give the COMPLETE task spec up front and let it run. It finishes tasks rather than leaving stubs, and long-horizon agentic work is its strength.
- **Delete self-verification scaffolding.** "Add a final verification step", "use a subagent to double-check", "re-verify before responding" cause over-verification and cost tokens with no quality gain — it already checks its own work.
  - [cabinet] This does NOT retire independent review. A fresh-context reviewer is a governance control (someone who does not share the author's blind spots), not self-verification. Keep the cross-agent panel; drop the "now double-check yourself" line inside a single agent's brief.
- **Never tell a reviewer to be conservative.** "Only report high-severity issues" is followed literally and suppresses real findings. Ask for full coverage and filter in a separate pass — its extra findings are mostly real, not noise.
- Effort: `high` is the default; `low`/`medium` hold quality at a fraction of the tokens and are the primary cost/latency lever; `xhigh` for the hardest coding and agentic work. Re-sweep effort on your own evals rather than inheriting a prior model's setting.
- 1M context is both default and maximum, and instruction-following stays consistent across it — long-context work does not need chunking workarounds.
- Coordinates subagent teams well (writer-verifier patterns hold, few overwrite collisions), and delegates readily — cap it: delegate only large, genuinely independent tracks, one agent where one suffices.
- Verbose by default, in three separate places, each needing its own instruction: conversational length ("keep responses focused and brief"), agentic narration ("brief update only on a find or a direction change; lead with the outcome"), and files written to disk ("match document length to the task; no padding, no redundant summaries").
  - [cabinet] Captain-facing messages need the explicit brevity line every time; the default register is far longer than the Captain reads.
- Scope: it can widen a task on its own judgment. For narrow work, say so — deliver what was asked, make routine calls yourself, flag a better approach in one sentence and continue rather than silently transforming the request.
- Self-correction: it narrates corrections more than prior models. If that matters for the surface, instruct it to correct only what changes the reader's decisions and otherwise fix and move on.
- Vision is strong (charts, documents, diagrams, UI replication); retire prompt-side vision workarounds tuned for older models, and give it tools to crop/inspect iteratively rather than more thinking.
- Keep thinking ENABLED and control cost with effort. With thinking off, two artifacts appear: tool calls written as text (never executed, and they poison later turns in an agentic loop) and internal XML tags leaking into output. Never write a rule telling it not to think — that increases tag leakage.
