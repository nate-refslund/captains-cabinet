# fix/briefing-and-recall — CP1: retrieval, and the eval that could not fail

## What was wrong, measured before anything was written

**The floor was deleting the answer.** Sixteen plainly-worded questions were
written against documents this repository ships (runbooks, transparency, pack
authoring), each one phrased the way a person asks rather than copied from the
document. All sixteen answering documents were confirmed present in the store
(1811 rows, `superseded_by IS NULL`) with embeddings.

Against the store, before any change:

| | |
|---|---|
| answering document is the TOP vector neighbour | 15 of 16 |
| answering document survives the 0.45 vec floor | 9 of 16 |
| recall@10 through the real `retrieval-eval.sh` runner | **0.5000 (8/16)**, MRR 0.5000 |

The pool was never the problem. `WHERE vec_sim >= 0.45` discarded the right
document before the reranker could see it, and the caller printed
"No results found."

**The floor value was never measured.** 0.45 is not in any commit message, any
plan, or any comment as a derived number. Measured now, same store, same model
(`voyage-4-large`, whole-file embeddings):

* answerable — the answering document scores vec **0.344 … 0.583**
* unanswerable — six ordinary off-corpus questions (bread, car repair,
  dynasties, toddlers, pruning, knots) peak at vec **0.125 … 0.213**

`MEMORY_VEC_FLOOR_DEFAULT = 0.28` is the midpoint of that 0.131-wide gap:
0.064 below the hardest true answer, 0.067 above the strongest unrelated one.

**Two axes were swept and rejected, so nobody re-derives them.**

* `input_type: "query"` on the Voyage call (the standard asymmetric-embedding
  fix) moves nothing: 9/16 either way. The stored vectors are untyped, so a
  typed query is not closer to them.
* A relative band (keep rows within a ratio of the pool's best vec) changed
  **nothing** at any floor that holds the abstain arm — it only ever raises the
  floor, so it cannot rescue a discarded answer. It is not in the code because
  it earned no place there.

**The eval guarding all of this could not fail.** `harvest-retrieval-eval.sh`
built every query from the expected document's OWN leading 110 characters —
the corpus asked to find itself — and the nightly gate ran on that harvest. It
reported recall@10 = 1.0000, MRR = 1.0000, for months, while more than half of
real questions returned nothing. It was also the gate standing between the
ranking and its fix: the ranking region is fingerprint-pinned and only a
passing eval may re-stamp it.

## What is true now

| Change | Where |
|---|---|
| vec floor default 0.45 → **0.28**, measured, with the derivation in the header | `cabinet/scripts/lib/memory.sh` |
| the floor VALUE moved INSIDE the fingerprint markers | same |
| question-shaped seed, 16 real questions + 6 unanswerable | `cabinet/scripts/tests/fixtures/retrieval-questions.seed.json` |
| ABSTAIN arm + `--abstain-floor` (default 1.00) | `cabinet/scripts/retrieval-eval.sh` |
| nightly runs the committed seed; presence precheck; harvester deleted | `cabinet/scripts/retrieval-eval-nightly.sh` |
| offline lock: a seed query may not be a copy of its document's opening | `cabinet/scripts/tests/test_retrieval_eval.py` |

**The guard now pins the number it always claimed to pin.** The fingerprint's
docstring said it covered "the vec floor"; it covered the COMPARISON while the
number sat outside the markers. A floor edit could change every answer the
cabinet gives without reddening anything. `test_floor_value_mutant_changes_fingerprint`
is the control.

**The abstain arm is not decoration.** Without it this whole eval is satisfied
by DELETING the floor: recall@k goes to 1.0000 and every off-topic question is
answered out of the nearest unrelated document.
`test_nightly_abstain_leak_fails_the_gate` proves the shape — recall 1.0000,
gate red.

## Proof, both directions

Run store-local, real runner, real store, real Voyage path.

```
BEFORE (memory.sh @ origin/master, NEW eval + NEW seed):
  recall@10 = 0.5000 (8/16)   MRR = 0.5000   abstain = 1.0000 (6/6)
  FAIL — recall@10 0.5000 < floor 0.60

AFTER (this branch):
  recall@10 = 0.9375 (15/16)  MRR = 0.9375   abstain = 1.0000 (6/6)
  PASS

BOTH ARMS (retrieval-eval-nightly.sh --stamp):
  rerank  r@k=0.9375 mrr=0.9375
  blended r@k=0.9375 mrr=0.9062
  pass=true → fingerprint re-stamped by the sanctioned path
```

The new eval FAILS against the pre-change code and PASSES after. The abstain
arm holds at 1.0000 in both, so the recall gain is not the floor being removed.

## Named residuals — recorded, not papered over

* **The one remaining MISS is a labelling artefact, and reading the hits says
  so.** "where can I look up what the org already knows without opening a
  terminal?" returns `product-brain/README.md` ("the org's own knowledge
  corpus") and `vault/README.md` ("the cabinet's knowledge vault") above the
  gold document. Those answer the question. A single-gold-document eval cannot
  score that as anything but a miss.
* **Session exhaust ranks into the top 6 for knowledge questions.**
  `transcript-digest` rows (594 of 1811) appeared at ranks 4-6 for the query
  above. The retired harvester excluded those types from its *pairs*; nothing
  down-weights them at *query* time. A type-aware weighting is a separate unit.
* **Documents are embedded whole and truncated at 32000 characters.** The
  largest is 284372 characters, so most of it has no vector at all. Fixing that
  means re-chunking and re-embedding — a write to the store, deliberately not
  done here.
* **The floor is still one number.** It is now a measured one with both arms
  committed, so a different corpus can re-derive it by running the eval; it is
  not self-calibrating.
