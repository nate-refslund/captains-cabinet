# Eval: On-Intent Divergence Scores One

Category: quality
Tests: F4 credits a `divergent × intent-aligned` row at 1.0 — the credit path (design §3.4, §7)

## Scenario
The Acme case. The counterparty thread asks, in substance, for help finding
a robotic mower for the large lawn at the new house; the Captain's held-out
reply was a single pasted Acme-mower URL. The context-gathering officer drafts
a short Danish reply naming 2-3 fitting LiDAR mowers for that lawn size, the
Acme among them, with a one-line recommendation.

Against the literal pasted URL the decision verdict is `divergent` (different
surface). But the draft serves the SAME `mission × core` intent — source a
no-boundary-wire mower for ~2500 m² at the new house, decisive, Danish, low
ceremony — equally well or better. A surface-only scorer zeros this (the
artificially-low F1 baseline). F4 must credit it.

## Expected Behavior
1. `scorer.composite("divergent", "intent-aligned")` returns `1.0` — the
   better-than-literal action earns full credit.
2. The credit is NOT a rubber-stamp: before any `intent-aligned`/`intent-partial`
   verdict on a `divergent` decision is accepted, `judge_with_oauth` runs the
   DETERMINISTIC guard over `thread_before` + the fenced cutoff context ONLY
   (never `real_reply`):
   - §3.3b topic-overlap floor: token Jaccard between the draft and the
     reconstructed intent must clear the floor (mowers vs. the mower goal pass;
     a vacuum link fails and is forced `intent-divergent` -> 0.0).
   - §3.2 grounding check: the mandatory `intent_grounded_fact` citation must
     actually exist (substring or high content-token overlap) in the pre-cutoff
     material; a fabricated citation fails and is forced `intent-divergent`.
3. The score row records `decision_verdict=divergent, intent_verdict=intent-aligned,
   composite=1.0` — auditable as the credit path.

## Failure Condition
- `composite("divergent", "intent-aligned")` returns anything other than `1.0`.
- A `divergent × intent-aligned` verdict is credited WITHOUT the deterministic
  grounding + topic-overlap guard having run.
- An off-topic draft (e.g. a vacuum link) or a hallucinated citation is credited
  instead of being forced to `intent-divergent` (composite 0.0).
- The grounding / topic check reads `real_reply` (a leak).
