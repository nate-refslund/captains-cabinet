# Eval: research_dependent Case Is Excluded And Surfaced, Never Zeroed

Category: quality
Tests: F4 excludes-and-surfaces a research-dependent case rather than scoring it 0.0 (design §6)

## Scenario
A held-out `Case` whose faithful answer genuinely required external research the
harness cannot reconstruct as-of-cutoff (e.g. live product options that only a
web search would surface). No officer-under-test makes a live web call during a
held-out eval — web search at eval time is "now" (>= today), a guaranteed
future-leak relative to a May cutoff, and web MCPs are CRO-only-scoped anyway.
The harness therefore cannot fairly score this case from cutoff-safe context.

Silently scoring it `divergent -> 0.0` would punish the officer for the
harness's own blind spot, violating the no-silent-caps rule.

## Expected Behavior
1. The case is marked `research_dependent`.
2. It is EXCLUDED from the scored set — its composite does not enter the headline
   fidelity number.
3. It is SURFACED in the run output (counted and listed as research-dependent),
   so the blind spot is visible, not hidden.
4. It is NEVER silently zeroed — `research_dependent` excluded ≠ `composite 0.0`
   in the scored aggregate.
5. The deferred remedy (a cutoff-dated archival web snapshot that would make such
   cases scoreable without leaking "now") is documented as out-of-F4-scope, not
   silently swallowed.

## Failure Condition
- A `research_dependent` case is scored `0.0` and folded into the headline
  number as if the officer failed.
- A `research_dependent` case is dropped without being surfaced/counted.
- An officer-under-test issues a live web call during a held-out eval.
