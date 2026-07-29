# fix/salience-ranking — checkpoint 1

**Unit.** Two properties the salience ranker was REPORTED to have and, re-run
against the same live estate, did not have; plus the instrument that would have
caught both.

**Model.** Opus 5 (1M), single session, execution tier. Not a direction gate:
the premise (both claims false as executed) arrived measured, and the
constraints — no scoring function with named weights, no fixed signal list, no
taxonomy, aliases joined by judgment and not by a stemming table, identity-shaped
tokens demoted and never deleted — were given, not chosen here.

Reviewed-Scope-Digest: 271197cf23bad6e4082dc85704320f59f7e14781b8ce89708cef392e2e1ec032

---

## 1. What was claimed, and what re-execution measured

The sweep was re-run READ-ONLY against the real estate before a line was
changed: 4 connectors, 665 names, 14 HTTPS requests, 0 writes. Every request a
GET or a GraphQL document asserted mutation-free before the socket opened.

| Claim on master | Measured on master, same estate |
|---|---|
| the alias union closed the split | **FALSE.** Cold, the entity stood as FIVE candidates at ranks 6, 11, 21, 33 and 34. The union only ever happens if the operator types the second name, and even then three fragments stay separate — nothing had asked anyone. |
| demote-never-delete was closed | **FALSE.** Three identity-shaped candidates were REMOVED with reason `connector_furniture` — 60, 59 and 12 occurrences gone from the ranking. Exactly one unrelated cluster was actually demoted. |

**Why the identity exemption did not close it.** It fires only for strings the
connectors report about *themselves*. The code connector's identity call answers
with the credential's user; 52 of 56 repositories are owned by an organisation
whose name never entered that set, so the token sitting in 93% of that
connector's rows was deleted as filing structure — and it is also the name of
the estate's busiest live site. The rule's own docstring said it never deletes
anything.

## 2. What replaced them

**Floors became discounts.** `_apply_floors` (deleted a token) is now
`_explained` (marks which of a token's occurrences one connector's filing
accounts for). Both measurements are unchanged; the verdict is no longer "this
token does not exist". The token keeps its span and every unexplained
occurrence, `rows` and `rows_standing` are both reported, and the connector span
is counted over the standing occurrences — a system whose own filing explains
every occurrence there is not evidence that the name recurs across systems, so
it does not vote. No new constant, no new weight: the score is the ratified
`connectors² × recency × (1 + min(n,20)/20) × identity` with `n` counted over
what is left standing.

**The owner joins the identity strings.** `rows_from_state` now feeds each row's
reported actor into the demotion set alongside the identity calls. Agnostic by
construction — it is whatever the connectors reported, never a list — and it is
what makes the org token demotable rather than deletable. It stays out of
attribution, where the same string means nothing.

**Aliases are joined by judgment.** `join_proposal(clusters)` emits every
candidate's label and the estate's own names for it UNMODIFIED — no stemming, no
lowering, no normalising, because the joinable evidence lives in the surface
form — and carries no scores, because a judge shown a score is being told the
answer. `rank(join=…)` hands that payload over and takes back groups of labels,
refusing and RECORDING any group naming a candidate the ranking never produced
or naming fewer than two. Nothing in the module compares two strings to decide
that a fuzzy-match table is a hand-maintained list wearing an algorithm.

**`check` is the oracle.** It grades a ranking against answers the OPERATOR
supplies — never a list living in the framework, which would be right for one
estate and a fiction for the next — and separates `offered` / `below_the_cut`
from `not_a_candidate` / `never_seen`. That distinction is the whole instrument:
"ranked eleventh" is a shortlist to scroll, "not a candidate" is an answer the
mechanism lost, and every deleting version of this ranker produced the second
while looking like the first.

**Its live consumer is the loop itself.** `answer_salience` grades the ranking
against the target the operator just picked, at the cut they were actually
shown. Every real answer, on any estate, in the operator's own words, becomes a
datapoint on whether the ordering works — with no fixed list anywhere.

## 3. The actual ranked output, real estate, read-only

Cold (no judgment, no operator answer), top of 49 — the union is still open,
which is the honest state before anyone is asked:

| # | candidate | score | span | rows | standing |
|---|---|---|---|---|---|
| 1 | website | 24.80 | 4 | 11 | 11 |
| 2 | media | 13.05 | 3 | 9 | 9 |
| 3 | *(the org name)* | 12.80 | 4 | 62 | 62 · demoted |
| 4 | networkwebsite | 11.25 | 3 | 5 | 5 |
| 5 | mediasummit | 10.80 | 3 | 4 | 4 |
| 6 | polads | 10.80 | 3 | 4 | 4 |
| 7 | devtasks | 10.35 | 3 | 3 | 3 |
| 11 | politiskeannoncer | 6.48 | 3 | 4 | 4 |
| 12 | tasks | 5.00 | 2 | 34 | 5 · demoted |

With judgment reading the emitted names and answering six groups, top of 39:

| # | candidate | score | span | rows |
|---|---|---|---|---|
| 1 | website | 24.80 | 4 | 11 |
| 2 | **polads** (5 fragments unioned) | 24.00 | 4 | 10 |
| 3 | media | 13.05 | 3 | 9 |
| 4 | *(the org name)* | 12.80 | 4 | 62 · demoted |

**Deltas against master, same rows, same clock.** The org name goes from DELETED
to rank 3 carrying all four connectors and all 62 rows, flagged demoted. Its two
sibling tokens go from deleted to merged into that one candidate instead of
standing as three. The split entity goes from five candidates at 6/11/21/33/34
to one candidate at rank 2. 33 tokens are discounted and **0** are lost from the
ranking — the arm that checks this counts every discounted token against the
clusters plus the named non-candidates.

**And the correction the oracle forced on this review's own first draft.**
Master's ranking was graded with the new `check` on the same rows, and its
HEADLINE IS IDENTICAL: 1 offered, 3 reached, 0 lost, deepest 16. So the honest
statement of the deletion defect is narrower than "it loses a correct answer on
this estate". What the deletion lost here is the SPECIFIC name and its evidence:
`stepnetwork` and `network` were removed, and the answer survived only because
the generic four-letter fragment inside them happened to remain and rank third.
An operator was therefore shown a word nobody calls anything, standing in for a
candidate whose 62 rows across four connectors had been deleted underneath it.
That the fragment survived is luck, not a mechanism — nothing in the deleting
version reports which answers it removed, which is why the same run can look
clean on a headline and be one estate away from silence. Stated here rather than
left implied, because a review that let its own strongest number stand
unexamined is the exact failure this branch was sent to fix.

**The honest verdict, which is not a green tick.** The oracle grades the
operator's three known answers: cold, 1 offered in the top 3, 3 of 3 reached,
0 lost, deepest rank 17. Judged, still 1 offered, 3 reached, 0 lost — the
union moves the split entity into the shortlist and moves the org name out of
it. **The shortlist is better and is still not an oracle-clean 3 of 3, and the
mechanism now says so in its own output instead of a report saying otherwise.**

**Re-measured after merging `origin/master` (`feat/look-capabilities`, which
lands epoch-millisecond clock decoding and plural row actors in the same read
lane).** A second read-only sweep — 14 calls, 665 rows, 4/4 connectors, 0
writes — reproduces the table above unchanged except that the estate itself
moved a day: one candidate enters at rank 13 and the third answer sits at 17
rather than 16. The actor harvest follows master's rename from a single `actor`
to plural `actors` in the same commit, so the demotion set still contains the
organisation and the org name is still rank 3 rather than deleted.

**Open and NOT claimed fixed.** (a) The generic descriptor still outranks the
specific one — `website` is rank 1 and merges four unrelated sites; no rule
derived from this estate separates them, and the join API can union candidates
but cannot split one. (b) One of the three answers is demoted because the
estate's own identity string and a real target are the same word; that is the
ratified demotion working, and it costs that answer the shortlist. (c) The join
proposal shows CANDIDATES only, so a fragment that recurs inside a single system
cannot be joined by judgment either — the count of those is disclosed in the
not-reached sentence and `check` reports such an answer as `not_a_candidate`
rather than hiding it.

**One measured result for the next direction gate, not acted on here.** Ranked
with the identity set EMPTIED — no demotion of the estate's own name at all —
the oracle scores the same three answers at deepest rank 8 instead of 17, better
on every one of them. The identity demotion is costing this estate a real answer
in order to suppress a noise that is also a real answer, which is the collision
the demotion was ratified to hold both sides of. It is a gate decision with two
blind arms behind it and a single execution session is the wrong place to
overturn it; recorded here with the number so the next gate argues with evidence
rather than with the original reasoning alone.

## 4. Verification

| Gate | Result |
|---|---|
| `framework/onboarding/tests/` | 592 passed, 1 skipped (final merged tree) |
| `framework/` full suite | 7690 passed, 26 skipped, 1 failed = `test_retro_shim.py::test_reexports_constants` (known local-only red, unrelated) |
| new arms vs master `26ad54c0` | 46 of 46 in the new suite RED; 6 of 6 rewritten arms in the two existing suites RED; 2 of 2 new journey arms RED. Both directions, `__pycache__` purged. |
| `cognitive-architecture-census.py` | PASS, observed == maximum (75256 on the final merged tree), zero headroom |
| `check-layer-separation.sh` | `new=0` — OK |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353) |
| `cabinet/scripts/tests/` ratchet + adjudication binding | 19 passed |
| live estate | 14 calls, 665 rows, 4/4 connectors, offer rendered, 0 writes |

**The mass raise is visible, not an allowance.** +311 non-comment lines in
`framework/`, all inside `salience.py` and `journey.py`; zero new production
modules; the reason is recorded on the `maximum` line the zero-headroom law is
read from. The COG-4 review digest is re-bound in this same commit because
`cabinet/config/cognitive-architecture-contract.yml` is inside its frozen scope.

**Two arms exist to stop this defect class returning by name.**
`test_a_discounted_word_is_still_reachable_and_never_removed` counts discounted
tokens against everything the ranking can still name, and the estate it runs on
is GENERATED from nonsense syllables over twelve seeds — so it asserts the
mechanism finds a planted answer, never that it reproduces a list. The
previously-passing arm asserting an undeclared high-share token is DELETED is
INVERTED, not weakened: it now asserts the discount still bites and that the
token is still named with its numbers.

## 5. External-write status

**NONE.** Every request this session was a GET or a GraphQL document
mechanically asserted mutation-free before send. No Telegram call. No Voyage
call. No write to any external system. Credentials read by NAME only; no value
printed, logged, committed or fixtured.

## 6. CI, read per job

Run `30495277643` on head `17b965ab`, `conclusion: success`, every job read
individually rather than off the run line: `ci` SUCCESS · `framework-tests`
SUCCESS · `null-hatch` SUCCESS · `cognitive-phase4` SUCCESS · `gitleaks`
SUCCESS · `tree-dedupe` SKIPPED (push-only job, absent by design on a pull
request). Four earlier runs on this branch read `cancelled`, every one of them
because a later push superseded it — a cancelled run is not a red and is not
counted here as a pass either.

Three merges of `origin/master` landed inside this branch while it was in
flight, each into the same read lane. Every number above is measured on the
FINAL merged tree, not carried forward from the pre-merge measurement: the
mass ceiling was re-measured at each merge rather than summed on paper, and the
live-estate sweep was re-run rather than quoted.
