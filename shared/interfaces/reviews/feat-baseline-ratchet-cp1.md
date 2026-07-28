# feat/baseline-ratchet — cp1

Reviewed-Scope-Digest: 84892321b1a3238dad99bffac5ccdf315971a621bde5e1e63781703c7fa22238

## What this closes

The 2026-07-27 expansion-gate landing (PR #245) shut three purchase channels and
NAMED the fourth in four claim surfaces rather than relabelling it covered:

> a baseline line added in the SAME commit as the file it names still empties
> the surplus, and the bijection cannot tell the difference.

Reproduced by execution against master `6ec81460` BEFORE anything was written:
`framework/synthetic_purchase_probe.py` + one line in
`cabinet/config/architecture-baseline-sets.yml` + `maximum` 207→208 and
60164→60167 returned `ok=True` at **248/248 with zero failures and no expansion
row**. The planted module was not in `surplus_members`, which is the whole
purchase.

## Why the fix is a separate git-aware script and not a census arm

The census is gitless BY DESIGN — its own docstring requires it to run in a
clean hatch with no history — so it has no "before" and never will. The
comparison has to come from git. `cabinet/scripts/baseline-set-ratchet.py`
reads the baseline at `merge-base(base, head)` and at `head`, both as COMMITTED
bytes (`git show` / `git archive`), never the working tree.

## The rules, and why the shape

A ratchet that refuses every addition breaks a RENAME, which the baseline
header itself calls the correct remedy (a paired edit in the same commit as the
tree change). One that allows any addition is no ratchet. So, per class, over
the merge-base→head diff:

| # | Rule | What it stops |
|---|---|---|
| A | `len(added) <= len(credited removals)`, where a removal is credited only when the tree at HEAD no longer carries that member | the named residual: a net addition |
| B | an added member must be in that class's observed member set at HEAD | a phantom path, which would otherwise fall through rule C as "not a file" |
| C | an added member that is a tracked FILE must be git's rename destination of a credited removal | the SWAP — delete one real module, add a different unadjudicated one, net zero |

Nothing here is a hand-maintained list. "Is this member a path" is answered by
`git ls-tree` at HEAD; "is this pair a rename" is answered by git's own
similarity scoring at `-M25%`; "what does the tree hold" is answered by the
CENSUS itself (the report now carries `member_sets`), so the two halves of the
gate can never derive the same six member sets differently.

The `credited` qualifier in rule A is load-bearing, not decoration: without it
the ratchet funds itself. Moving an existing baseline member onto an
adjudicated expansion row vacates its baseline line while the member stays in
the tree, and that line would pay for an unadjudicated addition. Arm
`test_a_removal_the_tree_still_carries_buys_nothing` is that attack.

## Residual, named rather than relabelled

Rule C reaches only members that ARE repo paths (today
`framework_production_modules`). For the symbol-shaped classes —
`central_event_types`, `central_action_types`, `services_total`,
`services_enabled`, `duplicate_event_writer_sinks` — a rename is an edit inside
a file, so git has no rename to score and a same-commit swap is
indistinguishable from a rename. It stays open, it costs deleting a live event
type / action type / service row, and it is caught by reading the diff. Closing
it needs a structural row-identity diff of each declaring file — a fourth
derivation of the same data, judged not worth its drift risk here. Stated in
the script's docstring, in the baseline header and in the census docstring.

## Shallow checkouts REFUSED, never skipped

`actions/checkout` is shallow by default and git's merge-base is untrustworthy
past a shallow boundary, so a SHA-diff ratchet that shrugs at a shallow clone
reports green in exactly the environment CI runs it in. This one exits 2 and
names `fetch-depth`. The step is wired into `cognitive-phase4`, the only job
that already carries `fetch-depth: 0`.

## Verification

14 arms, all against a REAL copy of this tree in a scratch git repo — never a
hand-written fixture shaped like the code's expectations.

Both directions on the residual: `test_the_census_alone_still_passes_it`
asserts the CENSUS is still `ok=True` on the mutant tree (if it ever stops, the
ratchet is standing in for a check that already fires and its greens mean
nothing), and `test_the_ratchet_reds_it` asserts the ratchet refuses the same
commit. Every arm that plants a module raises BOTH ceilings first, so the only
thing that can red those trees is the ratchet, never a zero-headroom budget.

The remedies are proven GREEN, not asserted: paired rename, registered
expansion with the baseline untouched, pure deletion, and an unrelated edit.

Degenerate ends are arms: empty diff, baseline absent at the base commit,
shallow clone, and a directory that is not a git work tree — the last two must
ERROR (exit 2), never pass.

The CI step is ROUND-TRIPPED, not grepped: the workflow's real `run:` body is
extracted by name and EXECUTED against both an honest head (exit 0) and the
mutant head (non-zero).

### Mutation sweep — every rule proven load-bearing

Each mutant is the shipped script with one rule disabled, run against the same
14 arms on a scratch copy:

| mutant | arms red |
|---|---|
| M1 rule A (net non-growth) disabled | 5 |
| M2 `credited` qualifier dropped (`credited = set(removed)`) | 1 — the funding attack |
| M3 rule C (rename pairing) disabled | 3 |
| M4 shallow guard disabled | 1 |
| M5 rule B (presence) disabled | 1 |

## Not touched

`cabinet/config/cognitive-architecture-contract.yml`,
`cabinet/scripts/egg-export-manifest.txt` and
`cabinet/scripts/tests/test_egg_export.py` are inside the frozen COG-4 §15
review scope. No byte of any of them moves here, so the Reviewed-Scope-Digest
of that phase is unmoved and no re-bind is needed. The new script ships in the
egg by default (the manifest is delete-based); it needs no `expect-present`
row, and adding one would have moved the frozen scope for a verification line.

No allowance row and no budget change: the ratchet adds no `framework/` module
and no `framework/` line, and names no module-level symbol matching the
`VERDICT` vocabulary pattern the `cabinet/scripts` budget counts.
