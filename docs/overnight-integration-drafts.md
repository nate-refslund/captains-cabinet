# Overnight integration drafts — for morning authorization (Nate)

Autonomous overnight work parks every change that would touch a GERMLINE file
here instead of applying it. Nothing below is applied. Review, then apply by
hand (or tell an officer to) if you agree.

Germline = read-only for officers/loops: `framework/authority/*` (classifier,
lane, matrix, veto, deploy_classifier), `framework/fidelity/graduation.py`,
`cabinet/scripts/lib/policy_engine.py`, `framework/policies/*`,
`cabinet/mcp-scope.yml`, `cabinet/officer-capabilities.conf`, `.claude/rules/*`,
`instance/config/autonomy.yml`, `memory/golden-evals/*`, `constitution/*`.

---

## T3 — let the graduation bar read the now-measurable intent signal

**Context (audit finding #1, the measurement-validity blocker).** The F4 scorer
computes `decision_verdict` / `intent_verdict` / `intent_composite` on each
`CaseScore`, but until T3 the consequence event the scoring path emitted carried
NONE of them and hardcoded `review.verdict = "unknown"`. Graduation reads ONLY
the consequence ledger and keys its bar on `review_confirmed_rate`
(`framework/fidelity/graduation.py:248`), whose denominator is `confirmed +
wrong`. With every scored case landing `unknown`, that denominator was 0 forever
→ `review_confirmed_rate` was always `None` → every cell was permanently
`unmeasured` and could never graduate. The bar was structurally un-feedable.

**What T3 already shipped (all NON-germline, applied on `feat/fidelity-harness-design`):**

- `framework/schemas/consequence-event.schema.json` + the hand-rolled validator
  in `framework/fidelity/consequence.py` now accept four OPTIONAL fields:
  `decision_verdict`, `intent_verdict`, `intent_composite`, `endorsement`
  (absent = unmeasured default; `additionalProperties:false` still holds).
- New F4 scoring-path emit `fidelity_events.build_case_scored` /
  `emit_case_scored` populates those fields from a `CaseScore` AND maps
  `review.verdict` from the intent verdict:
  `intent-aligned → confirmed`, `intent-divergent → wrong`,
  `intent-partial / error / "" → unknown`.
- `GraduationRatios.intent_match_rate` = `intent_aligned / (intent_aligned +
  intent_divergent)`, `None` when the denominator is 0, counted in
  `compute_ratios` from the new `intent_verdict` field.
- `framework/events/emitter.py` registered the new `fidelity_case_scored`
  org-event type.

**The consequence (no germline edit strictly required to unblock the bar).**
Because `emit_case_scored` maps the intent verdict ONTO `review.verdict`, the
EXISTING graduation line `match_rate = ratios.review_confirmed_rate` already
starts measuring intent the moment scored cases are emitted — `review_confirmed_rate`
is now an intent-derived rate, not a forever-`None`. So the minimal path is:
**ship T3, wire the scoring batch to call `emit_case_scored`, change nothing in
graduation.py.** That is the SAFE default.

**The optional germline change (your call — semantics decision).** If you want
the bar to read the intent signal DIRECTLY rather than through the
intent→review.verdict mapping, change the one line in
`framework/fidelity/graduation.py`:

```diff
--- a/framework/fidelity/graduation.py
+++ b/framework/fidelity/graduation.py
@@ def evaluate(
-    match_rate = ratios.review_confirmed_rate  # the decision-match channel
+    match_rate = ratios.intent_match_rate  # the eval-intent channel (T3)
```

(everything downstream — the `None → unmeasured` fail-safe, the sample floor,
the demote cluster, the recency-clean gate — is unchanged; `intent_match_rate`
has the same `float | None` contract as `review_confirmed_rate`.)

**The semantics decision you are actually making:**

- **Keep `review_confirmed_rate` (recommended default).** The bar reads the
  *reviewed-consequence* channel. Today that channel is fed by the F4 eval
  (intent verdict mapped to confirmed/wrong), but it is the SAME field the
  live reasoning-review / architect loop writes when it confirms or refutes a
  real action's expectation against reality. So as live-outcome reviews start
  landing, the bar transparently blends eval-intent AND live-outcome review
  under one rate — which is the "fitness = intent-served (outcome + review)"
  north-star. No germline edit. **This is what T3 is wired for.**

- **Switch to `intent_match_rate`.** The bar reads the *pure eval-intent*
  channel only (`intent-aligned` vs `intent-divergent`), ignoring any live
  `review.verdict` that did not originate from an intent scoring. Cleaner as a
  bootstrap-only signal, but it walls the bar off from live-outcome review and
  needs the germline edit above. Pick this only if you want graduation to be
  eval-intent-exclusive while the harness is still bootstrapping.

**Recommendation:** keep `review_confirmed_rate` (no germline edit); the intent
signal already reaches the bar through the T3 mapping, and the channel stays
open to live-outcome review for the post-bootstrap world. Authorize the germline
switch to `intent_match_rate` only if you explicitly want eval-intent-only
graduation.

**Not yet wired (separate, NON-germline follow-up — not done overnight):** the
F4 scoring batch (`framework/fidelity/run_f1.py:run_batch`, which computes the
`CaseScore` but only emits the pre-score evaluated event inside `run_case`)
still needs a call to `emit_case_scored(cs, officer_role, case.lane,
action_type=..., endorsement=case.endorsement)` after `scorer_fn(...)` returns,
so the scored rows actually land in the ledger. That is a small wiring change in
a non-germline file; flagged here so it is not forgotten, but left for explicit
sign-off since it changes what the live batch writes.
