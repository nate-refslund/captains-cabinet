# feat/answer-merges-aliases — checkpoint 1

**Unit.** The escape hatch could not merge a split candidate, which is the one
job the read-don't-ask design rests on. The operator answers; the merge takes,
and it persists.

**Model.** Opus 5 (1M), single session, execution tier. Not a direction gate:
the premise arrived MEASURED (the same product ranked twice, and answering
changed nothing), and the constraints — no stemming table, no fuzzy threshold,
no translation table, no framework alias list, the merge learned from the
operator and stored as instance state — were given, not chosen here.

Reviewed-Scope-Digest: 65687fc398d55c0ae0c20b1ed8fd0822735c5d63dcfe6860ff75ed9f393f6ca1

---

## 1. The defect, reproduced by driving the real loop

Not argued — executed, through `journey.act`, before a line was changed. An
estate where one entity wears two names sharing no substring (`Lantern` in the
tracker and handbook, `quayside` in the code, database and hosting) plus two
genuinely separate things:

```
SWEEP — shortlist BEFORE the answer
  rank 1: ledger     connectors=['db','docs','host','repo','tracker']
  rank 2: quayside   connectors=['db','host','repo']
  rank 3: lantern    connectors=['docs','tracker']
  ranked total = 4

>>> operator picks 'ledger'           -> shortlist AFTER: byte-identical
>>> operator escapes, types 'quayside' -> shortlist AFTER: byte-identical
```

`quayside` and `lantern` are one product, ranked twice at two positions. The
docstring on `_merge_aliases` said the answer teaches the merge. It did not,
for two reasons that both had to be true:

1. **Picking a candidate could never merge.** The alias group was the answer's
   own tokens, so a pick produced a one-label group and `_merge_aliases`
   requires two. There was no channel by which an operator could say "these two
   are the same thing".
2. **The escape hatch merged only by accident.** A typed name merged when its
   words happened to name two ranked candidates — i.e. when the operator wrote
   *both* names in one sentence. Typing either name alone taught nothing.

A third defect was found while fixing those two, and is the one nothing had
ever claimed:

3. **A learned merge did not survive the next answer.** The alias lived on
   `state["salience"]`, which the next answer replaces wholesale. An operator
   who taught a merge and then changed their mind about where depth goes
   silently reverted to the split they had already fixed — re-asking a settled
   question, one turn later.

## 2. What replaced it

| Part | Where | What it does |
|---|---|---|
| `same_as` on `answer_salience` | `journey._salience_merge_request` | the operator names the candidates that are one thing; validated against what the ranking actually PRODUCED, refused by name otherwise |
| `merge_ask` | `salience.merge_ask`, carried on `offer` and on the `answer_salience` next-action | the question, over EVERY ranked candidate — not the shown three |
| `learn_merge` / `learned_merges` | `salience`, stored at `state["salience_merges"]` | accumulating instance state: appended, deduped by label-set, never overwritten |
| `_closed_alias_groups` | `salience` | reduces each answer to the labels it names, then unions overlapping answers |
| `_merges_note` | `journey` | says back what was merged, on the card the operator reads |

**Nothing on the path compares two names.** Reduction of an answer to the
candidates it names is a set intersection against the ranking's own labels — an
exact match on a token the ranker itself produced. That is what keeps the four
refused instruments out: a stemming table, a fuzzy-match threshold, a
translation table and a shipped alias list are all hand-maintained lists in
disguise, and this program has deleted five of those in a week. The union is
transitive because IDENTITY is transitive, not because two strings resembled
each other.

**Why the merge question reaches past the cut.** Measured on the live estate,
one entity stood as five candidates at ranks 6, 11, 21, 33 and 34. A merge
answerable only over the three shown options cannot reach the split it exists
to fix, so every ranked candidate is nameable in the merge block while the pick
stays three options and an escape hatch.

**Why it travels with the pick rather than as a second action.** It is the same
answer — "this one, and it is also the one you called that". A separate action
would make the operator answer twice to fix a split they can see in one glance.

## 3. Proof, by execution

Same loop, after:

```
1. SWEEP: quayside rank 2, lantern rank 3, ranked total 4
2. ANSWER: choice=quayside, same_as=['lantern']
   stored: {"schema":"cabinet.salience-merges/v1","groups":[
            {"labels":["lantern","quayside"],"learned_at":"…","answer":"quayside",
             "source":"named"}]}
3. SHORTLIST AFTER: ranked total 3; ONE candidate carries both names and spans
   db, docs, host, repo, tracker; ledger and beacon stay separate
   card: "You told me these are the same thing, so I rank them as one:
          lantern = quayside"
4. SECOND ANSWER (choice=ledger, no merge): merge still applied
5. RE-SWEEP (the real gather_connectors action): store survived; rows re-read;
   merge still applied
6. TRANSITIVITY (same_as=['beacon'] later): all three ranked as one
7. REFUSALS: salience_merge_unknown / salience_merge_joins_nothing /
   salience_merge_invalid / salience_merge_too_many
```

## 4. Sensors, and the proof they can fail

Nine new arms. Each was run against PRE-CHANGE code in a separate pristine
clone of `origin/master`, caches purged:

| Arm | Pre-change |
|---|---|
| `test_two_answers_about_one_thing_are_one_answer` | FAILS — "the second answer was dropped", `len([]) == 0` |
| `test_a_learned_merge_is_appended_deduped_and_never_overwritten` | FAILS — no such function |
| `test_reading_the_store_survives_a_row_it_cannot_use` | FAILS — no such function |
| `test_the_merge_question_reaches_past_the_cut_and_echoes_what_it_learned` | FAILS — `offer()` takes no `learned` |
| `test_answering_merges_a_split_candidate_and_the_shortlist_changes` | FAILS — `KeyError: 'merged_with'` |
| `test_a_learned_merge_outlives_the_answer_that_taught_it` | FAILS — `assert []` |
| `test_the_merge_question_offers_every_ranked_candidate` | FAILS — no merge block |
| `test_a_merge_naming_something_never_ranked_is_refused` | FAILS — DID NOT RAISE |
| `test_an_answer_naming_one_candidate_or_none_joins_nothing` | **passes** — a regression guard, stated as one: it pins UNCHANGED degenerate-end behaviour so the closure cannot loosen it |

**The fixtures are lopsided on purpose.** The ranker-level estate carries
candidates of 4 / 3 / 2 rows, so the union keeps `alpha` — which is *not* the
name the second answer is anchored on, and is exactly what makes the second
answer fall on the floor without the closure. A symmetric fixture would have
let the pre-change code pass by accident. The journey-level estate carries two
things that genuinely are separate, so a rule that merged everything would be
as wrong as one that merged nothing; the arms assert both directions.

**The degenerate ends are asserted.** An answer naming one candidate, none, an
empty group and the same label twice all leave the ranking byte-identical. An
unusable row in the store is skipped rather than raised on, because the store
is read on every render of the card.

## 5. Gates

| Gate | Result |
|---|---|
| `pytest framework/ -q` | 7719 passed, 25 skipped, 1 failed — `test_retro_shim.py::test_reexports_constants`, the documented local-only red (model-id constant), unrelated and untouched here |
| `pytest framework/onboarding -q` | 620 passed, 1 skipped |
| `pytest cabinet/scripts/tests/test_cognitive_architecture_census.py -q` | 152 passed, 6 skipped |
| `check-layer-separation.sh` | OK — baseline 24, allowlist 19, current 43, new 0 |
| `cognitive-architecture-census.py` | PASS at zero headroom |
| `null-hatch.sh` (committed tree) | PASS — all four stages; egg boots with no captain data, no instance source, adapters absent |

**Census.** `framework_production_noncomment_lines` 60979 → 61198 (+219
measured, observed 75475 vs the then-effective 75256). RAISED VISIBLY, never an
allowance: an allowance promises a deletion gate, and the only channel by which
an operator can teach the mechanism an identity it provably cannot derive is
permanent. Zero new production modules — every function lands inside
`framework/onboarding/{salience,journey}.py` and the new arms are tests, so the
bijection class is untouched and no allowance was needed or used.

**COG-4 re-bind.** `cabinet/config/cognitive-architecture-contract.yml` sits
inside the frozen COG-4 digest scope, so
`shared/interfaces/reviews/cognitive-core-phase-4-review.md` is re-bound in the
SAME commit and `cognitive-phase4-review-scope.py --verify` is green over the
landed tree.

## 6. Agnostic

No tool, industry, role, person or product noun enters the framework. What is
learned is an IDENTITY — two labels are one thing — never a KIND: nothing
records what sort of thing it is, which is the property that makes the same
mechanism right for an estate of products, of clients or of collections. The
one taxonomy guard in the suite
(`test_the_module_contains_no_taxonomy_of_entity_kinds`) is green and was not
touched.
