# fix/claim-surfaces — cp1

Reviewed-Scope-Digest: df8c7bfb9465e768b63598c0dd84ecb5c50dcbf1dbdf202493231ccc8789ca17

Verdict: PASS

## What was wrong, measured before anything was changed

Three public entry points documented properties their bodies do not enforce. Two
were found by reviewers of `fix/identity-picker-tail` and left unlanded on
purpose — a docstring line costs architecture-census headroom, and the census
was at zero. That is a defensible call for a reviewer inside a landing and the
wrong outcome to leave standing, because `framework/` and the dashboard card
both ship in the public export and a stranger reads these sentences as the
contract.

### 1. `framework/onboarding/research.py::identity_candidates`

```
"""EVERY account identifier this connector reported, busiest first.
...
FREQUENCY ORDERS THE LIST; IT NO LONGER DECIDES MEMBERSHIP.
```

over

```python
ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
return [{"identifier": name, "rows": count}
        for name, count in ranked[:MAX_IDENTITY_CANDIDATES]]
```

Above `MAX_IDENTITY_CANDIDATES` (200) both sentences are false and frequency
decides membership again, at a higher number. Reproduced against master's bytes:

```
distinct accounts on the connector = 203
identity_candidates(...) returned   = 200
```

Nothing misbehaves today because the only production caller compensates —
`identity_question` counts the estate itself with `_distinct_actors` and
publishes `accounts` / `withheld` / `complete`, and the surface opens a typed
field where the cap binds. The exposure is a NEW surface written against the
function, which is told the offer is exhaustive and has nothing in the return
value to contradict it.

### 2. `cabinet/dashboard/src/components/onboarding/journey-card.tsx`

```
<details> rather than React state — the
rest must be reachable with scripting off.
```

and, on `IDENTITY_SHOWN`:

```
every account it offers is reachable here without scripting.
```

The component is `'use client'` and its entire content arrives from
`await fetch('/api/onboarding')` inside a `useEffect`; `journey` is `null` until
that resolves. With scripting off there is no picker, no account list and no
question to disclose — so the disclosure cannot be reachable without scripting,
and neither can anything else on the card. The choice of `<details>` is right;
the stated reason was not.

### 3. `framework/onboarding/research.py::inventory_mcp_estate` — found by the sweep

```
``sources`` lists the root-relative paths actually consulted.
```

A file that exists and will not parse IS consulted — read off disk, handed to a
parser, thrown away — and then omitted. Reproduced by execution against master:

```
both files exist: True True
{'consented': True, 'servers': [], 'sources': []}
```

byte-identical to the result for a root that does not exist. This module's own
section header names that exact conflation ("nothing is connected" vs "I never
looked") as the failure it exists to refuse.

## The fix, and why this shape

**Text changed; not one line of behaviour.** Each cap, bound and empty is
deliberate and stays. What changed is that each sentence now says what the code
does, names what the code cannot distinguish, and — where a caller needs an
answer the function cannot give — says where that answer comes from.

`identity_candidates` opens by naming its cap, states that the rank-free
membership property holds BELOW the cap only, names `identity_question` as the
caller that counts the estate, and names the three fields that carry the honest
offer. `inventory_mcp_estate` describes `sources` as the paths that yielded a
reading, states that a broken pair is indistinguishable from a bare root, and
names the arm that pins that behaviour so the gap is documented rather than
argued away. The dashboard comment keeps the `<details>` and replaces its reason
with a true one (the browser owns the open/closed bit, so it costs no hook, and
keyboard and assistive tech get it free), then states plainly that no-script
reachability was never a property of this card so the belief cannot come back.

**Census paid visibly.** +19 non-comment lines in `framework/`, all of them
docstring, measured with `cognitive-architecture-census.py` (75972 -> 75991) and
paid by a `maximum` raise 61433 -> 61452 with the reason in the contract. Never
an allowance: an allowance promises a deletion gate, and a public entry point's
own account of what it returns is never deletable. `framework_production_modules`
unchanged at 248, so no bijection class moves. The COG-4 review-scope re-bind
rides this same commit, because the contract sits inside that frozen scope.

**Rejected:** shrinking the honest sentence to fit the ceiling (that is exactly
how these shipped); adding a `not_read` key to `inventory_mcp_estate` (a real
behaviour change against a pinned arm, and a separate unit — recorded in the
docstring instead of done silently); editing the landed review artifacts'
history rather than appending a dated supersession.

## Verification — every arm executed, both directions, caches purged

New arms: 4 in `framework/onboarding/tests/` (3 in
`test_who_and_when.py::TestTheCandidateOfferDescribesItselfHonestly`, 1 in
`test_research.py`), 3 in `journey-card.test.ts`.

**Against pre-change master (`f4afc746`), the new arms copied onto a clean
clone: 5 of 7 fail.** All four Python arms fail; the no-script arm fails on
`expected … not to match /reachable with scripting off/`.

The remaining two dashboard arms are green in both directions **by design** —
they assert the property that makes the old sentence false (nothing renders
before the fetch resolves) and the property the new sentence promises (every
offered account is on the card), neither of which this branch changes. So each
was **mutation-tested** rather than left as an unfalsifiable pass:

| Mutation | Result |
|---|---|
| loading branch forced off (`{loading ?` → `{false ?`) | `renders nothing of the identity ask before the client fetch resolves` RED |
| disclosure tail truncated (`slice(IDENTITY_SHOWN)` → `slice(IDENTITY_SHOWN, IDENTITY_SHOWN + 2)`) | `still promises what it can keep` RED (and the pre-existing tail arm survives, so this one is not a duplicate) |

**The honesty arm does not share the assumption it checks.** The estate size in
the cap arm is counted with a plain set over the fixture's own rows, never
through the module's `_distinct_actors` — an arm that borrows the helper it is
checking is how this program has passed sensors against the defect they name.

Batteries, this session, on the committed shape:

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework/ -q` | 7772 passed, 26 skipped, **1 failed** — `test_retro_shim.py::test_reexports_constants`, the known LOCAL-ONLY red (env-driven model-id pin), reproduced on a clean master clone |
| `python3.12 -m pytest framework/onboarding/tests/ -q` | 674 passed, 1 skipped |
| census-adjacent `cabinet/scripts/tests/` (census, baseline ratchet, residuals register, adjudication binding) | 180 passed, 6 skipped |
| `npx tsc --noEmit` (dashboard) | clean |
| `npx vitest run` (dashboard, full) | 2894 passed, 1 skipped, 141 files |
| `cognitive-architecture-census.py --check` | PASS, `framework_production_noncomment_lines: 75991 <= 75991`, observed == maximum, zero headroom on every class |
| `baseline-set-ratchet.py --base f4afc746 --check` | PASS |
| `check-layer-separation.sh` | OK — new=0 |
| `docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353) |
| `cognitive-phase4-review-scope.py --verify` | BLOCK before the re-bind (correctly), OK after |

## The deliberate sweep

Every public entry point in `framework/onboarding/research.py` (14) plus the
dashboard card's exported surface and its property-asserting comments, read
docstring-against-body. Three false claims found (above), and the checks that
came back clean are recorded in the pull request rather than only the failures,
because "no open items" is only true inside the surface actually swept.

## What this does NOT claim

The sweep covered the entry points this change touches, not the whole framework.
`inventory_mcp_estate`'s inability to distinguish an unreadable file from an
absent one is now documented and still true — the sentence was fixed, the
behaviour was not, and that is stated rather than implied. The landed review
artifacts for `fix/identity-picker-tail` and COG-4 keep their original text; each
carries an appended dated note, because a record that is edited to look right was
never a record.
