# feat/salience-loop — checkpoint 1

## What this branch does

Master's connector lane (#289) reads the estate honestly and then makes two
further claims **without saying so**: that the activity it read is the
OPERATOR'S, and that the period it covers is REPRESENTATIVE of their work.
Neither is settled by reading more rows. This branch states both bases, asks
where it has none, and closes a floor that was deleting what another rule
promised to keep.

Note on scope: this branch originally carried its own sweep engine
(`framework/onboarding/look.py`). #289 landed an equivalent lane while it was in
flight, so the engine was **dropped rather than landed beside it** — two
producers for one state key is worse than either. What remains is only what
master does not have.

## Files

| File | What |
|---|---|
| `framework/onboarding/research.py` | `operator_identity` · `attribution_basis` · `period_read` · `presence_question` · `who_and_when(_lines)`; the actor survives onto the emitted rows; the identity docstring corrected in place |
| `framework/onboarding/salience.py` | estate-identity tokens are exempt from the furniture/concentration floors — demotion was already promised and the floors were breaking it |
| `framework/onboarding/journey.py` | `gather_connectors` resolves the operator from the onboarding record and puts who/when into the disclosure the operator reads |
| `framework/onboarding/tests/test_who_and_when.py` | 20 arms |
| `cabinet/config/cognitive-architecture-contract.yml` | +200 measured lines; NO new module |

## The findings, each measured on the live 665-row estate

1. **Attribution had no basis and no way to get one.** The actor was extracted
   per item and collapsed to a distinct COUNT — "how many people", never "which
   of them is you". Nothing downstream could separate the operator's rows from
   anyone else's, and nothing said so.
2. **The credential is not the operator.** The connectors' `identity` calls ask a
   token who it is; on a shared integration that is a service account. Fine for
   DEMOTION (what does this estate call itself), wrong for attribution. The
   docstring calling those strings "the operator's own name" is corrected in
   place so the wrong use cannot be re-derived from the old words.
3. **A window assumes somebody was present.** `period_read` states the window in
   the rows' own terms (2023-11-15 to 2026-07-29, 607 of 665 dated) and names
   the assumption; `presence_question` hands a fortnight of the operator's own
   silence back as a question with three answers.
4. **A floor was breaking another rule's promise.** `salience` says identity is
   demoted, never deleted. The furniture floor reached the same token by another
   route: one connector names every row `<org>/<thing>`, so the org token sits in
   100% of that connector's rows and the estate's busiest live site was floored
   as filing structure. Measured before: **deleted**, listed among the floored
   words. Measured after: **rank 3 of 47, all four connectors, flagged demoted.**
   The arm proving an UNDECLARED high-share token is still floored rides beside
   it — an exemption handed to everything would disable the floors.

## Verification

| Gate | Result |
|---|---|
| new arms vs master `4c49b798` | 17 of 18 RED (the 18th is the degenerate-end guard, green both directions by design) |
| `framework/onboarding/tests/` | 492 passed, 1 skipped |
| `cognitive-architecture-census.py` | PASS, observed == maximum |
| live estate | 14 calls, 665 rows, 4/4 connectors, offer rendered with the full disclosure |

## What the loop actually asks him

> Of everything I found, which should I go deep on first?
> **[1] website** — spans code, databases, hosting, tracker (11 rows)
> **[2] media** — code, hosting, tracker (9 rows)
> **[3] networkwebsite** — code, databases, hosting (5 rows)
> **[4] None of these — I will name it**
>
> What I did not reach: … 47 candidates ranked, showing 3 … no usable
> last-touched clock on databases, hosting … dated 2023-11-15 to 2026-07-29
> (607 of 665 carried a date), and I am assuming that period is representative
> of your work; I cannot tell which actor is you in code, databases, hosting,
> tracker, so I am not claiming any of that activity is yours.
