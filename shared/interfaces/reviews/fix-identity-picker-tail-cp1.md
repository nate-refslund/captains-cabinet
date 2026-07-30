# fix/identity-picker-tail — cp1

Reviewed-Scope-Digest: 07aa0c2cd622a96d9638bfe195b1cf3444dfc66ba8bdad79edb246df4f0bcc18

Verdict: PASS

## What was wrong, measured before anything was changed

The identity ask offers the estate's own account identifiers so "which of these
is you" is a tap rather than a spelling. It offered the **12 busiest**, and
frequency decided membership.

Re-measured on the real estate the unit was built against: the tracker connector
carries **531 of 665 rows**, reports **30 distinct accounts**, and the
operator's own account carries **exactly one row** — about 25th. Reproduced
mechanically against master's bytes on a fixture of the same shape:

```
A: distinct actors      = 30
A: offered              = 12
A: operator offered?    = False
A: note                 = tracker: 30 account(s) appear across 697 rows;
                          the 12 busiest are offered here, 18 are not
```

The picker is the **only writer** of an identity anywhere in the tree. So on
that estate no sequence of operator actions could resolve the connector holding
80% of it, every claim there stayed correctly withheld, and the card told the
operator to leave it blank. That is the same "a branch only a writer could
reach" defect this whole lane was built to close, still standing in the lane
that closed it. The note beside it was honest about the truncation and honest is
not closed.

Three smaller defects, each reproduced by execution before the fix:

| # | Defect | Evidence against master's bytes |
|---|---|---|
| 1 | The shipped connectors example put `actor_field` under `page:`, where nothing reads it — the header calls that key mandatory | a spec built exactly as the GraphQL example teaches swept `rows: [{...}]` with `actors: None` and `identity_candidates(...) == []` |
| 2 | The bridge claimed an over-long identifier is "refused by name"; it was silently cut | `submitted len = 700  stored len = 500  truncated? True` |
| 3 | A scalar `handles: {code: nate}` in the answers file was iterated per character | `operator_identity -> {'code': ['a','e','n','t']}`, statement `in code I recognise you as a, e, n, t` |

## The fix, and why this shape

**Frequency now ORDERS the offer and no longer decides membership.** Every
account a connector reported is offered, up to a guardrail raised 12 → 200. The
busiest account on a shared tracker is whoever files the most tickets, which is
a fact about process volume and not about who is reading the card; rank must not
decide whether a person can say who they are.

**A bound still exists, because rows are bounded and actors are not.** A sweep
reads up to `_DEFAULT_MAX_ITEMS` (2000) items per connector with up to
`_MAX_ACTORS_PER_ITEM` (8) actors each, so an unbounded offer could put
thousands of strings in a card payload. The question therefore carries
`accounts` (the estate, uncapped), `withheld`, and `complete`.

**`complete` is the field a surface obeys, and it is what makes the doctrine
line true again.** The written line was *"a PICKER over the candidates, never a
free-text field"*. It **changes here, with its reason**, to: a picker always,
and a typed field **only where `complete` is false**.

- Where the offer is complete, "none of these is you" is a **true terminal
  state** — every account the connector reported is on the list — and a
  free-text field could only introduce a spelling the estate does not use, which
  resolves the operator and then matches nothing. The original reason holds
  exactly here, so the original rule holds exactly here.
- Where the guardrail binds, a picker **cannot** be the only door. A connector
  with more than 200 distinct accounts is a large company, not a pathology, and
  this cabinet has no standing to tell a person they are not in their own
  estate. The alternative — keeping "never a free-text field" and accepting that
  such an operator is unresolvable — is the defect above with a bigger number.

Rejected alternatives: a typed fallback *everywhere* (it would have made the
common case worse for a case a complete offer already answers, and would have
retired a rule whose reason is still correct); a "tail rather than head"
ranking (it fits the one measured estate and fails the operator who is
mid-list); leaving the note honest (honest is not reachable).

**Surface.** The busiest `IDENTITY_SHOWN = 8` lead; the rest sit behind a native
`<details>` disclosure — no React state, so every offered account is reachable
with scripting off. The typed field writes to the **same** `handles` entry the
radios write to, so tapping and typing are one field and a stale spelling cannot
be submitted under a corrected pick.

**Smaller defects.** `MAX_IDENTITY_CHARS` is **tied to** `_MAX_FIELD_CHARS`
rather than chosen twice, and asserted so — a smaller bound would refuse a
candidate this module itself offered, a larger one would accept a string no
connector could have reported; over-long is now refused by name, so the bridge's
claim becomes true rather than being narrowed. `_one_or_many` reads a scalar as
the one identifier it plainly is. The GraphQL example moves `actor_field` under
`inventory:` **and** selects `creator { name }` in the document, because the
example taught two wrong things and fixing one would have left a spec that still
yields no actors.

## Verification — every arm executed, both directions, caches purged

New arms: 10 in `framework/onboarding/tests/test_who_and_when.py`, 2 in
`cabinet/dashboard/src/components/onboarding/journey-card.test.ts`.

**Against pre-change master (`8346e683`), the new suite copied onto a clean
clone: 9 failed, 44 passed.** The tenth
(`test_the_rest_example_yields_an_actor_as_built`) is green in both directions
**by design** — it is the guard proving the example harness actually parses and
executes, and it was mutation-tested: moving `actor_field` under `page:` in the
REST block turns it red with
`AssertionError: actor_field sits under page:, where the sweep never reads it`.

The two dashboard arms were run against master's `journey-card.tsx` (with only
the `IDENTITY_SHOWN` export added, so the import resolves and the **render**
stays exactly as it shipped): **2 failed | 28 passed**.

**Fixtures are lopsided on purpose.** `_lopsided_rows()` gives 29 colleagues
10–38 rows each and the operator ONE. A symmetric fixture cannot discriminate a
complete offer from a head — that is how four sensors in this program have
passed against the defect they name — so the operator is last by frequency and
only a rank-independent offer reaches them.

Batteries, this session, on the committed shape:

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework/ -q` | 7763 passed, 25 skipped, **1 failed** — `test_retro_shim.py::test_reexports_constants`, the known LOCAL-ONLY red, reproduced identically on a clean master clone |
| `python3.12 -m pytest framework/onboarding/tests/ -q` | 664 passed, 1 skipped |
| `npx tsc --noEmit` (dashboard) | clean |
| `npx vitest run` (dashboard, full) | 2891 passed, 1 skipped, 141 files |
| `cognitive-architecture-census.py` | PASS, `framework_production_noncomment_lines: 75911 <= 75911`, observed == maximum |
| `check-layer-separation.sh` | OK — new=0 |
| `docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353) |

**Census.** +45 non-comment lines in `framework/`, paid by a **visible
`maximum` raise** (61327 → 61372) with the reason in the contract, never an
allowance: an allowance promises a deletion gate, and an offer that cannot
exclude the person it addresses has nothing to delete. Zero new production
modules, so no bijection class moves. The COG-4 digest re-bind rides this same
commit, because the contract sits inside that frozen scope.

## What this does NOT claim

A recorded handle that matches nothing is still reported as matching nothing
rather than repaired — that is the honest reading and it is unchanged.
A connector that reports **no** actor at all still offers no pick and says why:
the fix there is a declared `actor_field`, not an identity, and the note says so.
The typed branch is exercised by an arm, not by a live estate — no estate here
has more than 200 accounts on one connector, which is precisely why the branch
exists rather than a reason to leave it out.

---

## Corrected 2026-07-30 — two sentences in this review were themselves over-broad

Landed on `fix/claim-surfaces`. Nothing about the fix above changed; two of the
sentences describing it did, because they claimed more than the code does and
both shipped into a public entry point's own documentation.

1. **"Frequency now ORDERS the offer and no longer decides membership. Every
   account a connector reported is offered, up to a guardrail"** — the two halves
   contradict each other, and `identity_candidates`' docstring shipped the first
   half without the second: *"EVERY account identifier this connector reported"*
   and *"FREQUENCY ORDERS THE LIST; IT NO LONGER DECIDES MEMBERSHIP."* over a body
   that returns `ranked[:MAX_IDENTITY_CANDIDATES]`. Above the cap both sentences
   are false and frequency decides membership again at 200 instead of at 12. The
   guardrail is right and stays; the docstring now names it, names the caller that
   compensates (`identity_question`, which counts the estate itself and publishes
   `accounts`/`withheld`/`complete`), and tells a new caller where an exhaustive
   answer actually comes from.

2. **"no React state, so every offered account is reachable with scripting off"**
   — never true of anything on that card. `journey-card.tsx` is a client component
   whose entire content arrives from `fetch('/api/onboarding')`, so with scripting
   off there is no picker, no account list and no question to disclose. The
   `<details>` is still the right element for a different and true reason (the
   browser owns the open/closed bit, so it costs no hook and keyboard and
   assistive tech get it for free). The same false sentence also sat on
   `IDENTITY_SHOWN`.

Both were found by reviewers of the work above and left unlanded because a
docstring line costs architecture-census headroom. The +19 lines are paid by a
visible `maximum` raise (61433 → 61452) with the reason in the contract — the
trade the omission was avoiding, taken the other way.

New arms: 4 in `framework/onboarding/tests/` and 3 in `journey-card.test.ts`.
FIVE of the seven fail against pre-change bytes (all four Python arms plus the
no-script one). The remaining two are green in both directions by design — they
assert the property that makes the old sentence false (nothing renders before
the fetch resolves) and the one the new sentence promises (every offered account
is on the card), neither of which my edit changes — so each was MUTATION-TESTED
red instead of being left as an unfalsifiable pass: forcing the loading branch
off kills the first, truncating the disclosure tail kills the second.
