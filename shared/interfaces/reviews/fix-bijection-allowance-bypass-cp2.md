# fix/bijection-allowance-bypass — cp2 (reviewer findings R3 + R4)

Reviewed-Scope-Digest: a7b425a837732a4ef5bccbee07033c79f5ca7769ea991e679ee250d5fbddedff

The full reviewer report named four fixes. cp1 closed D1/R1 (the allowance
bypass) and R2 (the four false claim surfaces). This checkpoint closes the
other two. Both premises were re-measured against master's census before
anything was written, because a fix built on a trusted premise is the defect
this branch exists to correct.

## R3 — the rename false positive, which TEACHES the bypass

Premise verified by execution against master's census. Renaming one production
module:

```
[0 clean]  ok=True  modules=246/246  failures=0
[RENAME]   ok=False modules=246/246  failures=2
    framework_production_modules  unregistered set member
      [framework/authority/ownership_renamed.py]
    framework_production_modules  expansion row names a member that is not present
      [framework/authority/ownership.py]
```

Zero net growth, count unmoved at 246/246, two reds. The two green paths are a
full expansion row — two blind arms and a written adjudication, for a *move* —
or a hand edit to the baseline. Nothing shipped said which was correct, so the
cheap one wins by default and routine work normalises exactly the edit D1's
bypass is made of.

The rule is now stated in the baseline header and repeated in the census
docstring: **a rename is a PAIRED edit in the same commit as the tree change**
— remove the old member, add the new one, and move any expansion row's `member`
with it. Never one half without the other.

The clause that stops the paired edit from becoming the bypass is
machine-enforced, not just written: **a line is never added for a member the
tree does not already have** — the absent-baseline-member red from cp1. A
rename satisfies it by construction, because the new path exists at the commit
that adds it.

Three arms: the friction itself is pinned (so the rule cannot outlive the
problem it describes), the paired remedy is proven GREEN (a documented remedy
nobody tested sends the next author back to the instrument being closed), and
the half-edited rename — new name added, old one left — is RED.

## R4 — `consumer` disjointness defeated by two characters

Premise verified by execution against master's census, on the live contract's
own expansion row:

| `consumer` | master's census |
|---|---|
| `framework/authority/ownership.py` (the member) | REFUSED |
| `./framework/authority/ownership.py` | **`ok=True`** |
| `./framework` (the declaring path) | **`ok=True`** |

The comparison was plain string equality. Both sides now normalise through
`_normalized_repo_path` (`PurePosixPath(...).as_posix()`), and the declaring
path normalises too — the reviewer named the member case; the declaring-path
case was found by checking rather than trusting, and it was open the same way.

The honesty half matters as much. The docstring now says plainly that
`consumer` is an **existence-and-disjointness check, never a use check**:
nothing reads the named file or asks whether it consumes the member, and any
path that exists satisfies it — `.git/config` does, measured in a real clone.
An overclaimed check is the whole subject of this branch, so the claim now
matches the code rather than the intent.

Four arms parametrized over the bare and `./` spellings, plus an over-breadth
arm proving a genuine consumer is still accepted — without which an
over-tightened rule would red every real expansion with every other arm green.

## Pre-change proof

Master's census with this branch's tests: `3 failed, 10 passed`. The three
failures are exactly the three new properties — the half-edited rename, and the
`./` spellings of both consumer arms. The ten passes are the direction and
over-breadth arms, which are correct to pass in both directions.

The pre-fix baseline used was `ff011924`; `cognitive-architecture-census.py`
and `architecture-baseline-sets.yml` are byte-identical there and at the true
`origin/master` (`0276820a`), verified by blob SHA, so it is a valid reference.

## Ceremony

This checkpoint does not touch
`cabinet/config/cognitive-architecture-contract.yml`, so the frozen COG-4 §15
digest is unmoved and needs no re-bind. cp1 did touch it, and re-bound it in
the same commit as the bytes that moved it — re-verified green after the
`origin/master` merge.

## Recorded as NOT defects, so a later session does not re-litigate them

The empty registry at landing was the honest state and is kept non-vacuous by
permanent synthetic both-ways arms · the adjudication binder is correctly
egg-excluded and exercised on synthetic pass/absent/touched/stale documents
every run · `merge_refuted` being a shape-only anchor is stated honestly · the
three shadow-law allowlist entries are exact single-path exemptions with a
stated why.

Per the 2026-07-07 full-autonomy grant.
