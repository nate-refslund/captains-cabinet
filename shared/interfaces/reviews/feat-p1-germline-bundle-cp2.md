# Checkpoint review — feat/p1-germline-bundle (cp2, fixer round 1)

Reviewed-Scope-Digest: 7b0509a7ac9aa106b28f8039a7a80cdf5bc46ed434a6750f79c70963aecd03bf

Reviewer: fixer, closing the independent reviewer's REJECT of `f181f86b`. Every
number below was produced by a command in this clone, in this session.

## The reject, restated in one line

The bundle was verifiable on master and NOT on the tree the ceremony runs on:
G3's declared post-image digest is master-relative, the ceremony applies G3.diff
to the schg-locked tree, and the two provably differ — so `verify.sh` would have
exited 10 at step 4 of a window that cannot be delegated, for a failure the doc
asserted would not happen.

## Reproduced first, then fixed

```
$ git show 5dce39d5:cabinet/scripts/hooks/session-task-inject.sh > fixture/...   # the
                                       # bytes a locked tree with no window since
                                       # 2026-07-31 still holds (5338cb42 changed
                                       # this file on master, OUTSIDE G3's hunk)
$ bash <shipped f181f86b verify.sh> --repo fixture --checks-only
[verify] G3 FAIL: post-image sha256 c89c578f… != declared 5f2e177b…
BUNDLE VERIFY FAIL (rc=10 rows=2 applies=1 already-at-target=1)
```

`applies=1` is the defect in one field: the shipped gate APPLIED a patch to bytes
it was never built from, then reported the wrong-looking result. The refusal
named neither the bytes it saw nor the ones it wanted, so nobody reading it can
tell "rebuild the bundle" from "the bundle is corrupt".

## What changed

**Every row is now decided by digest, not by an assumption about which tree this
is.** `BUNDLE_ROWS` gained a **pre-image sha256** column:

| id | pre-image | post-image | state |
|---|---|---|---|
| G1 | `856db3fc…` (`00c3acd3^`) | `bd5dcd46…` (master today) | landed |
| G3 | `8e37461f…` (master today) | `5f2e177b…` | proposed |

`current == pre` ⇒ apply, and the result must equal the declared post-image.
`current == post` ⇒ already-at-target, a pass. **Neither ⇒ exit 10 naming all
three digests, with no `git apply` attempted at all** — because a clean apply on
foreign bytes is the most misleading answer this script could give.

```
$ bash verify.sh --repo <same fixture> --checks-only
[verify] G3 FAIL: … is neither the pre-image this bundle was built against nor
                  the post-image it produces — DRIFT.
[verify]   current       sha256 88c9d97d…
[verify]   expected pre  sha256 8e37461f…
[verify]   expected post sha256 5f2e177b…
[verify]   REBUILD the bundle against the current bytes; never force-apply.
BUNDLE VERIFY FAIL (rc=10 rows=2 applies=0 already-at-target=1)
```

**The ceremony gates BEFORE the sudo.** Doc §5 gains a step 0: run `verify.sh`
against the tree that owns the locked bytes; every row must report `applies` or
`already-at-target`, and a DRIFT row means rebuild and re-file — the window is
not requested. It writes nothing and needs no privilege, so there was never a
reason to spend the unlock first. `test_the_ceremony_gates_before_it_unlocks`
asserts the ordering rather than asking for it.

**The unmeasurable claim is deleted and replaced by a measurement.** The doc no
longer says what the Captain's box holds. §2 now names both digests per row, the
exact reason G3 can need a rebuild (`5338cb42`, and the `c89c578f…` it produces),
and §7 states the box's bytes as UNMEASURED. `test_amendment_doc_lint.py` gained
`"the forward patch applies"` to `forbidden_lower` and `"pre-image sha256"` /
`"before the unlock"` to `anchors_lower`, so neither the claim nor its absence
can drift back silently.

## Sensors — red for the right reason, then green

| sensor | red before | green after |
|---|---|---|
| `test_every_row_declares_the_pre_image_it_was_built_against` | rows carried 4 fields; no pre-image existed | rc 0 |
| `test_the_historical_locked_bytes_are_refused_not_silently_patched` | shipped gate applied the diff and printed `c89c578f…` | rc 0 |
| `test_the_ceremony_gates_before_it_unlocks` | `assert 743 < 324` — verify.sh ran after the unlock | rc 0 |
| `test_the_doc_declares_the_digests_the_captain_is_accepting` | doc stated neither digest | rc 0 |
| `test_amendment_doc_lint[employee-phase1]` | missing anchor `'pre-image sha256'`; and separately, the re-inserted false claim | rc 0 |
| `test_a_locked_path_written_during_the_run_is_caught` (exit 12) | the channel had no inverted arm at all | rc 0 |
| `test_the_golden_eval_stage_is_wired_in_both_directions` (exit 13) | the stage had no automated sensor at all | rc 0 |
| `test_a_germline_landing_must_be_recorded_in_the_tree_not_declared` | the exemption did not exist | rc 0 |

**Mutation arms — each sensor proved to discriminate, on the FIXED tree:**

| mutation to `verify.sh` | what went red |
|---|---|
| pre-image branch accepts any bytes (`= PRE` → `!= WANT`) | the two drift arms + the historical arm (3 failed) |
| `LOCKED_BEFORE != LOCKED_AFTER` → `false` | `test_a_locked_path_written_during_the_run_is_caught` |
| `GOT_SHA != WANT_SHA` → `false` | `test_a_diff_that_stopped_producing_its_declared_post_image_is_refused` |
| `bash run-golden-evals.sh` → `true` | `test_the_golden_eval_stage_is_wired_in_both_directions` |

The exit-12 arm's seam is `CABINET_PYTHON`: the locked-set digest is the only
thing `verify.sh` launches, once at each end of the window it guards, so a
wrapper that mutates on its second call writes in exactly that window. The write
lands in a fixture tree; no live switch and no real locked path is ever in a
write set (`git status --porcelain` empty after every run, including the full
form).

## The guard's one exemption (reviewer note N1)

`test_phase1_touches_no_locked_path` was unconditional and permanent, so it would
have redded every future landed-then-ceremonied germline branch — the pattern
CLAUDE.md §8 sanctions and that `00c3acd3` and `5338cb42` both used, with
`--admin` bypass forbidden. It now accepts `CABINET_GERMLINE_LANDING=<CG-id>`,
but **the declaration has to be true of the TREE**, not of the caller: the CG row
must exist exactly once in the ledger AND a `docs/proposals/germline-amendment-*`
package must name both that row and every path being landed. A bare env var is a
claim about intent that travels into shells and CI recipes and leaves nothing
behind — the failure `cabinet/scripts/lib/evals-redis-sandbox.sh` documents at
length. Four refusal arms and one accept arm; `test_the_guard_is_not_exempted_on_
this_branch` proves the exemption is not what makes THIS branch green.

## Reviewer notes closed, and the one that is not mine

* N3 (exit-12 had no inverted arm) — closed, above.
* N4 (golden-eval THIN) — the THIN is withdrawn and replaced by a measured green:
  the FULL form ran here, rc 0, **Total 32 / Pass 32 / Fail 0**, ephemeral redis
  on `127.0.0.1:28529`, live redis untouched, 158 s. It stays a battery row
  rather than a unit arm at that cost; the stage's WIRING now has both-direction
  arms that run in milliseconds.
* N5 (the `~90 FILES` comment) — corrected to the measured 73 FILES + 7 DIRS.
* **N2 is not in this diff and not mine to land.** The divergence is real and I
  re-measured it: the drill names `fail 20 P2h` at
  `cabinet/scripts/drills/one-responsibility.sh:944` and `fail 21 P2h` at `:951`
  (the review said :952) — there is no `exit 25` anywhere in that file. The stale
  `25` is in the CONTRACT (§7 invariants and the §10 merge-note row), which is the
  orchestrator's adjudication of record and has other concurrent readers. This
  unit's doc already cites 20/21 and its lint entry forbids `exit 25` from
  resurfacing in the package; the contract edit is flagged for the orchestrator.

## The reject's own remedy, and why the other half of it is not here

The reviewer offered two fixes: land G3's bytes on master, or pin the pre-image
and gate before the window. **The first is forbidden to this unit** —
`cabinet/scripts/hooks` is a locked DIRECTORY and the unit's hard invariant is
that nothing under a locked path is modified, enforced by the same guard this
diff extends. So the second was taken, in full, plus the pre-image pin the
reviewer's option (b) only asked to be *named*: it is checked, and it is checked
before the sudo.
