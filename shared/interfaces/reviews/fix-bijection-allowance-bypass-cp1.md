# fix/bijection-allowance-bypass — cp1

Reviewed-Scope-Digest: af7aaa89cf0f93c2d9e0e82da8e5a63d6c975e8a42770bca95b4df705e764cd1

## Why

An adversarial review of the expansion registry (PR #231) rejected it by
EXECUTION. Four shipped files asserted "an allowance CANNOT buy a net-new set
member". It is false, and both halves of the file's own stated defence are
false with it.

## The reproduction, run before anything was changed

Against a clean clone of `origin/master` at `ff011924` (census PASS, 246/246
production modules):

| step | change | census |
|---|---|---|
| 0 | nothing | `ok=True`, 0 failures |
| A | add `framework/synthetic_bypass_probe.py` (a genuinely net-new production module) | `ok=False` — budget exceeded ×2 **and** `unregistered set member` |
| B | + ONE line in `cabinet/config/architecture-baseline-sets.yml` + an ordinary `temporary_allowances` row (+1 modules) + the uncontested line-mass row | **`ok=True`, 0 failures, 0 new expansion rows** |

The module is on disk, counted, and the census reports the surplus as only the
two legitimately-registered expansions. The allowance row was the **twelfth** on
`framework_production_modules`.

Second half, separately reproduced: four phantom baseline members — one per
class, none of which exist anywhere in the tree — were written into the baseline
file alone. `ok=True`, 0 failures. No count moves when a baseline name has no
tree member, so an inventory can be pre-loaded in one commit and consumed in a
later one.

The builder disclosed the substance but named the wrong cost ("the maximum must
be raised too"). Membership and count are two separate purchases; the text named
only the count. That is the class-11 pattern — a partial fix whose text relabels
the rest as covered — and it shipped in the public egg.

## What changed

`cabinet/scripts/cognitive-architecture-census.py`

* `LEGACY_BIJECTION_ALLOWANCES` — the bijection-class allowance rows that were
  live when this landed, pinned as exact `(phase, budget, additional)` triples.
* `load_contract` refuses, at load, any `temporary_allowances` row whose
  `budget` is a bijection class unless its exact triple is in that set, and
  refuses a second row carrying a permitted triple.
* `_bijection_failures` gained a fourth arm: a baseline name the tree does not
  carry is a failure.

The `additional` is part of the permit key deliberately. R1 as proposed keyed
the carve-out on the phase name, which leaves the row **editable**: bumping
`COG-3` from 12 to 13 buys a module for one character, which is the purchase
being closed. Verbatim duplication is refused for the same reason.

## Eleven live rows, not the nine the review named

The review counted nine phases on `framework_production_modules` totalling +38.
Verified against the live contract rather than trusted: there are **eleven**,
totalling +40 (206 base + 40 = 246 observed). The two beyond the review's list
are `personal-preset-live` and `source-ownership-class`, +1 each, landed after
it was written (PRs #239 and #242). Both carry registered expansion rows, so
their *membership* was adjudicated and only their *count* rode an allowance.

No allowance names any other bijection class: every row in the contract names
either `framework_production_modules` or `framework_production_noncomment_lines`.

They are grandfathered rather than refused because refusing them would red
master for already-reviewed work. The widening is stated here and in the census
source rather than made silently, and the pin is asserted verbatim by a test so
a twelfth entry cannot be quiet.

## The phantom rule is a hard red, not a report

A baseline name with no tree member is either a pre-loaded inventory (the
purchase) or a stale line after a real deletion (the correction). Neither is a
state the census should call green.

It is affordable because the remedy is always a SAFE edit: `surplus = observed -
baseline`, so removing a baseline line can only make the surplus LARGER. Nothing
is ever bought by fixing a phantom. A report nobody must act on is the disabled
sensor this program keeps finding in its own tests.

Measured before shipping it: `baseline - observed` is empty for all six classes
on master, and the egg deletes no live bijection member (`framework/evolution/
holdout_gen.py` in the export manifest does not exist in the tree; the other
framework deletion is under `tests/` and is not counted). So the rule needs no
source-only carve-out and binds the derived tree too.

## What is NOT closed, stated rather than relabelled

A baseline line added in the SAME commit as the file it names still removes that
file from the surplus, and the bijection cannot tell the difference. Measured,
not assumed: `file + baseline line + a visible maximum raise` (no allowance)
returns `ok=True`, 247/247, zero failures.

What the fix buys is that this path now costs a visible `maximum` raise on the
line the zero-headroom law is read from, plus a claim about `snapshot_of` that
git blame contradicts. It is caught by reading the diff, not by the census. The
closure would be a git-aware ratchet refusing ADDITIONS to the baseline file —
the baseline is a snapshot of a pinned SHA and has no legitimate reason to grow
— which is a CI-side change of a different shape and is filed rather than
smuggled in here.

## Arms, and their pre-change state

Run against master's census with this branch's test file: **18 failed, 4
passed**.

| arm | pre-change |
|---|---|
| new allowance on each of the 6 bijection classes refused at load | RED ×6 |
| grandfathered row edited upward refused | RED |
| grandfathered row copied verbatim refused | RED |
| phantom baseline member caught, each of the 6 classes | RED ×6 |
| a shrink that leaves the baseline stale is red | RED |
| the reproduced bypass, end to end | RED |
| the pin is verbatim / the live rows load | RED ×2 (constant absent) |
| allowance on a MASS budget still accepted | green (over-breadth arm) |
| removing a baseline line still reds as surplus | green (direction arm) |
| legitimate shrink stays green (mirrored) | green |

Three pre-existing tests were re-pointed, none weakened:
`_contract_with_allowance` moved its synthetic row from `central_action_types`
to `claude_skills` — both arms test allowance ARITHMETIC and neither depends on
which class is named, and a fixture naming a bijection class would encode the
refused shape as valid. `test_legitimate_shrink_stays_green` now mirrors the
deletion into the baseline, with a new companion arm proving the un-mirrored
half reds.

## Provenance

Per the 2026-07-07 full-autonomy grant. Adversarial-review handback,
2026-07-27.
