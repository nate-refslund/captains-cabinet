# Checkpoint review — `fix/short-answer-binds` cp1

Reviewed-Scope-Digest: 9d4c4514c24b4e78d3ddd3196796023f097a212a531ec7db6ad354b75046cec1

Scope: the 6 staged paths (contract + declared-residuals register +
`framework/onboarding/{journey,salience}.py` + their two suites). Driven end to end against the real journey core before and
after; no grep-only claim below.

## The defect

`fix/answer-binds-depth` landed the right control — the salience answer scopes
depth, enforced rather than asserted — and then derived **both sides of its name
test with the RANKING tokenizer**. `salience.tokenize` drops every part and every
adjacent-pair compound below `_MIN_TOKEN_LEN` (4), which is correct for deciding
what may be a *candidate* and wrong for deciding what a *name* says.

Consequence, measured on the shipped tree (`master` 8346e683):

```
answer typed by the operator: 'BH'
  ranking tokenizer sees: salience.tokenize('BH') -> []

  1. window "bh" (the answer itself) ........... REFUSED   [salience_window_off_target]
        "You pointed me at BH, and "bh" does not carry that name. ..."
  2. window "quarterly-tax-returns" ............ REFUSED   [salience_window_off_target]
        "You pointed me at BH, and "quarterly-tax-returns" does not carry that name. ..."
  3. window "ops-monorepo" + same_thing ........ ACCEPTED  relation=same_thing
  4. window "quarterly-tax-returns" + elsewhere  ACCEPTED  relation=elsewhere
```

An empty set of wanted words intersects nothing, so the control that exists to
refuse ONE window refused EVERY window — **including the folder spelled exactly
like the answer** — and the refusal told the operator that folder "does not carry
that name", which is false about the one thing they can check by eye.

Two properties made it invisible:

* **The shortlist path cannot reach it.** A ranked candidate's label is built out
  of ranking tokens and clears the floor by construction, so every happy-path
  test binds. The escape hatch is the only door a short answer comes through.
* **The victims are a class, not an edge case.** A three-letter product, an
  acronym, an initialism, a short name in any language. In a framework that must
  serve any operator in any industry, that is not a corner.

## The fix

`salience.name_tokens` — the words a name is made of, plus the adjacent-pair
compounds, **no ranking floor**. `salience.tokenize` becomes that list above
`_MIN_TOKEN_LEN`, so the ranker keeps its floor and nothing else borrows it. One
implementation with the floor named at the ranking's own door; two tokenizers
with two floors would drift apart again in a month.

`journey._window_binding` compares names with `name_tokens` on both sides, and
returns the two word sets it compared (`target_words` / `window_words`) so the
refusal carries the evidence for its own claim instead of asserting it.

Every sentence rendered from that function now states the test that actually ran
— *"shares no word with it"* — instead of a containment (`carry`) the code never
tested. Three surfaces: the `propose_window` refusal, the after-the-fact
off-target card note, and the standing depth claim.

**What was deliberately NOT done.** The match was not loosened to substring
containment. `northbayops` still shares no word with `northbay`, that refusal is
real, and it is exactly what the sentence now says happened —
`WINDOW_RELATIONS` is the way through. `"it"` inside `"waiting"` is not a shared name, and a matcher that
cannot tell the difference is a guess, which is the thing this module refuses
five different ways.

**Alias derivation is untouched.** `state["salience"]["aliases"]` feeds the
RANKER (`journey._learned_merges` → `rank(aliases=…)`), so it keeps the ranking
floor; a short alias there could only be reduced away by `_closed_alias_groups`'
intersection against ranked labels, and would be noise in a learned store.

## After

```
  1. window "bh" (the answer itself) ........... ACCEPTED  relation=matched  evidence=['bh']
  2. window "quarterly-tax-returns" ............ REFUSED   [salience_window_off_target]
        "You pointed me at BH, and "quarterly-tax-returns" shares no word with it. ..."
  3. window "ops-monorepo" + same_thing ........ ACCEPTED  relation=same_thing
  4. window "quarterly-tax-returns" + elsewhere  ACCEPTED  relation=elsewhere

  card: "You pointed me at BH, so that is where I spend depth — I refuse a
         window whose name shares no word with it unless you tell me what it is"
```

## Arms, and the proof each one is a sensor

Six new arms. Every one was run against the pre-change tree with the cache
purged, and against two surgical reverts, because a new arm that has never been
red is a fixture, not a test.

| arm | what it fails on |
|---|---|
| `test_a_short_answer_the_ranker_cannot_tokenize_still_binds_its_own_window` | the same short answer, both directions: it must bind `bh` AND refuse `quarterly-tax-returns`. A bind that refuses everything passes a one-sided off-target test exactly as one that accepts everything does. It asserts `tokenize("BH") == []` first, so a future floor change cannot silently retire the class the fixture exists for. |
| `test_a_short_answer_keeps_both_statements_the_operator_may_make` | the two-value escape going unreachable for an answer with no ranking tokens — `same_thing` still binds and still teaches its alias, `elsewhere` still opens and still DROPS the depth claim. |
| `test_no_refusal_states_a_reason_the_code_did_not_apply` | any refusal whose stated reason is false. Ten (answer, folder) rows, deliberately lopsided 7 permitted / 3 refused; every refusal's claim is re-read with `_plain_words`, a split written in the test that never calls the module under test, plus the refusal's own `target_words`/`window_words`, plus a ban on the superseded `carry that name` wording. |
| `test_the_card_does_not_claim_an_unspent_answer_when_the_window_matches` | the same false sentence on the OTHER surface — an answer arriving after a window is open renders its own note, so fixing only the refusal would leave the card lying. |
| `test_the_words_in_a_name_survive_the_floor_that_the_ranking_applies` | the split collapsing in either direction. |
| `test_the_ranking_vocabulary_is_exactly_the_floored_name_words` | the floor-free list leaking into the ranker, which would silently re-rank a real estate. |

**Fails against pre-change (`master` 8346e683, `__pycache__` purged,
`PYTHONDONTWRITEBYTECODE=1`), new suites copied onto the old code:**

```
FAILED test_journey.py::test_a_short_answer_the_ranker_cannot_tokenize_still_binds_its_own_window
FAILED test_journey.py::test_no_refusal_states_a_reason_the_code_did_not_apply
FAILED test_journey.py::test_the_card_does_not_claim_an_unspent_answer_when_the_window_matches
FAILED test_salience.py::test_the_words_in_a_name_survive_the_floor_that_the_ranking_applies
FAILED test_salience.py::test_the_ranking_vocabulary_is_exactly_the_floored_name_words
5 failed, 1 passed
```

The one that passes is `..._keeps_both_statements_...`, and it must: it is the
regression fence proving the fix did not take the escape away, so it is green on
both sides by construction. Stated rather than hidden.

**Two surgical reverts, so the arms are sensitive to the change and not merely to
a new symbol's existence:**

* revert ONLY `_window_binding`'s tokenizer (keep `name_tokens`, keep the new
  wording) → the three journey arms go red, the two salience arms stay green.
* revert ONLY the refusal wording (keep the tokenizer fix) → the honesty arm goes
  red on `assert "carry that name" not in message`, and nothing else moves.

**`tokenize` output is byte-identical to the pre-change implementation**, proven
over a 60,018-name corpus (17 hand-picked shapes + 60,000 randomly composed from
separator/short/long/digit fragments) comparing the new definition against the
old body: 0 divergences. Pinned in-suite by
`test_the_ranking_vocabulary_is_exactly_the_floored_name_words`.

## Gates, run this session on this tree

| gate | result |
|---|---|
| `pytest framework/ -q -rs` | 7760 passed, 25 skipped, 1 failed — `test_retro_shim.py::test_reexports_constants`, the known LOCAL-ONLY red, confirmed identically red on a pristine `master` clone before any edit |
| `pytest framework/onboarding/tests -q` | green |
| `cognitive-architecture-census.py` | PASS, `framework_production_noncomment_lines: 75927 <= 75927`, observed == maximum, zero headroom |
| `check-layer-separation.sh` | OK — baseline=24 allowlist=19 current=43 new=0 |
| `docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353 findings=0) |
| `pytest cabinet/scripts/tests/test_declared_residuals_register.py -q` | 9 passed — the residual paragraph below is registered as RES-024 in this commit, which is how it was found: the gate red-lined the declaration before it could ship unregistered |
| `pytest cabinet/scripts/tests/test_{cognitive_architecture_census,expansion_adjudication_binding,declared_residuals_register,cog4_exit_fixtures}.py -q` | 174 passed, 6 skipped |
| `cognitive-phase4-review-scope.py --verify` | re-bound in this commit (the contract is inside the frozen COG-4 scope) |

## Census

`framework_production_noncomment_lines` 61327 → 61388 (+61 measured, observed
75927 vs the then-effective 75866). **Raised visibly, never an allowance** — an
allowance promises a deletion gate, and neither the binding nor the operator's
own words are deletable while the depth sentence ships. ZERO new production
modules (`framework_production_modules` unchanged at 248: both functions land
inside existing modules, and the six new arms are tests), so no bijection class
moves.

## Merge 2026-07-30 — `fix/short-answer-binds` x master (`fix/identity-picker-tail`)

Two conflicts, both in the shared append surfaces this program has raced on
before, both resolved by keeping BOTH sides verbatim and re-measuring the one
number that is not additive by construction:

* `cabinet/config/cognitive-architecture-contract.yml` — two disjoint visible
  raises on the same budget (+45 the identity picker, +61 this unit). Both notes
  stand; the merged ceiling is **re-measured over the merged tree**
  (`cognitive-architecture-census.py`: PASS, observed 75972 == maximum 61433,
  zero headroom). The paper sum agrees (61327 + 45 + 61 = 61433), which is
  evidence FOR the measurement and not a substitute for taking it.
* `shared/interfaces/reviews/cognitive-core-phase-4-review.md` — both sides
  re-bound the digest line. ONE value stands, recomputed over the merge commit;
  both re-bind sections are kept verbatim at the end of the file.

`framework/onboarding/journey.py` auto-merged and was read rather than trusted:
master's change is in `entry_plan`'s comment and the `record_operator_identity`
handle-length refusal; this unit's is `_window_binding`, `_binding_note`, the
`propose_window` refusal and the module docstring. Disjoint functions.

Full local gate set re-run on the merged tree — see the table above, re-measured.
