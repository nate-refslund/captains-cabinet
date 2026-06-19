# Eval: Hollow Surface-Match Scores Zero

Category: quality
Tests: F4 composite gates a `match × intent-divergent` row to 0.0 (design §3.4)

## Scenario
The officer-under-test produces a draft that echoes the literal words of Nate's
held-out reply (decision verdict `match`) but misses the underlying goal — it
serves the wrong intent, hallucinates a fact, goes off-topic, or its intent
reading cannot be grounded in the pre-cutoff material. The intent judge (or the
deterministic anti-rubber-stamp guard in `scorer.judge_with_oauth`) returns
`intent_verdict = intent-divergent`.

A `max(_DEC[dec], intent)` blend would leave this row at 1.0 — rubber-stamping
the hollow echo. F4's decision-dominant, intent-penalizing blend must instead
zero it, so the §3.2 grounding check and the §3.3b topic-overlap floor are
load-bearing rather than inert.

## Expected Behavior
1. `scorer.composite("match", "intent-divergent")` returns `0.0`.
2. The score row records `decision_verdict=match, intent_verdict=intent-divergent,
   intent_composite=0.0` — fully auditable; the surface decision stays visible.
3. The same zero applies to `partial × intent-divergent` and
   `divergent × intent-divergent` — any `intent-divergent` row is gated to 0.0
   regardless of the decision verdict.
4. The `intent-divergent` branch is distinct from the `error`/`""` branch: an
   unavailable intent layer falls back to the decision-only score (`_DEC[dec]`),
   it does NOT zero the row.

## Failure Condition
- `composite("match", "intent-divergent")` returns anything other than `0.0`
  (e.g. a `max`-based blend leaving it at 1.0).
- An `intent-divergent` verdict is credited above 0.0 for any decision verdict.
- A missing/`error` intent layer is wrongly zeroed instead of falling back to
  the decision-only score.
