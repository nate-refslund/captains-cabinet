# FW-019 checkpoint review — fix/census-shift-left cp1

Reviewed-Scope-Digest: 187e5e8c4d110d6a922d8ef2fb2972e1a6c24e55f071220af3e78f214b3b4dfd

Branch: `fix/census-shift-left` · base `origin/master` 0ab0cc2b · 2026-07-27
Provenance: per the 2026-07-07 full-autonomy grant + 2026-07-21 ownership-on-GO;
executes item 3 of the 2026-07-27 direction gate "Catching EXPANSION"
(`LAUNCH-DIRECTION-EXPANSION-GATE-2026-07-27.md`, adjudication of record).

**Honest limit on this review itself:** written by the implementing session, not
a fresh reviewer context — no second agent was dispatchable here. What follows
is therefore stated as *executed evidence* (commands run, outputs observed)
rather than as an independent opinion, and every claim below is reproducible
from the two harnesses in the diff.

## What the change is

Two edits to enforcement files that already run, plus their proofs.

**(a) FW-025c — the architecture census moves LEFT into `pre-push`.**
`cognitive-architecture-census.py --check` now runs on master pushes beside the
existing FW-025b layer-separation gate, between layer-sep (~1s) and the
golden-eval suite (~75s), so a budget breach is refused before it costs 75
seconds and before master goes red for every other writer. The in-tree
precedent is exact: FW-025b is itself a shift-left of a CI check, added after a
2026-07-14 merge landed four layer violations that CI caught and the local gate
did not. Same script, same flag, same working-tree scope caveat (FW-026).

**(b) FW-019's artifact check becomes a digest binding.**
Measured before changing anything: `pre-commit` accepted any file whose *name
contained the branch slug*, preferred one modified in the last 30 minutes, then
**fell back to any age**, and never read a byte. `touch
shared/interfaces/reviews/<branch>-cp1.md` passed it. It now requires the
artifact to carry exactly one

    Reviewed-Scope-Digest: <64-hex>

line equal to a SHA-256 over the sorted, newline-joined canonical records
`<mode> <sha> <path>` of the staged change set, excluding
`shared/interfaces/reviews/` so the artifact is not inside its own digest. The
grammar is lifted from the two in-tree instances that already prove it
(`cabinet/scripts/cognitive-phase{0..4}-review-scope.py`). The one deliberate
deviation: those bind a landed commit and read `git ls-tree -r HEAD`; a
pre-commit hook runs before the commit exists, so the equivalent
committed-bytes source is the index — `git diff --cached --raw`, which reports
the destination mode and destination blob id git is about to write.

## Attacks run against the new check (all now REJECT; all previously PASSED)

Both directions, cache purged, in `memory/golden-evals/framework/fw-019-checkpoint-review.sh`:

| Arm | Forgery | New hook | Pre-change hook |
|---|---|---|---|
| i | `touch`ed / empty artifact | BLOCK "carries 0 … line(s)" | **exit 0, "artifact found"** |
| j | bound artifact, then the staged set moves | BLOCK "staged scope hashes to" | **exit 0** |
| k | artifact copied from a different change | BLOCK "records \<other\>" | **exit 0** |
| l | malformed digest (`deadbeef`) | BLOCK | **exit 0** |
| m | two digest lines (shotgun) | BLOCK "carries 2 …" | **exit 0** |
| n | symlink whose target carries the right digest | BLOCK "symlink" | blocked for the WRONG reason |
| o | staged deletion moves the digest | BLOCK | **exit 0** |
| q | over threshold, only review-plane files staged | BLOCK "no reviewable bytes" | **exit 0** |

Arm (j) carries its own precondition arm: the artifact is asserted ACCEPTED
before the staged set moves, so (j) cannot pass because the artifact was
permanently red. Arm (p) asserts the inverse property — editing the review body
while keeping the digest line still passes — which is what makes the binding
satisfiable rather than merely strict. Arm (r) pins the CLI a reviewer uses.

Measured: new eval vs new hook **21/21 pass**; new eval vs the pre-change hook
(`git show HEAD:cabinet/scripts/git-hooks/pre-commit`) **13 arms fail**,
including i/j/k with `got=0` and the literal stderr
`pre-commit: checkpoint-review artifact found`.

For (a), `cabinet/scripts/test-pre-push-hook.sh` gains the census-gate arms:
it RUNS on master pushes and NOT on feature branches, and it BLOCKS on a real
breach, on an absent script, and on an absent interpreter — with the eval suite
proven *not reached* on the breach path, which is the fail-fast claim. Measured:
**42/42 pass** against the new hook, **9 fail** against the pre-change hook.

## The disabled sensor this also closes

`memory/golden-evals/framework/fw-019-checkpoint-review.sh` had **zero
executors**: `run-golden-evals.sh` has no discovery, and `git grep
fw-019-checkpoint-review` returned only the file, its own header and a
knowledge-classification row. The behaviour it pins was unwatched the entire
time the gate was forgeable. It is now a step in the `ci` job, mirroring the
existing "Golden eval — FW-002 spending limits" step, which was added for
exactly this blind spot. A rejecting arm nobody runs is not a proof.

## What this does NOT close — stated because the omission is the risk

1. **Hooks bind only clones that ran `install-git-hooks.sh`.** Verified: a
   fresh clone has `core.hooksPath` unset and `.git/hooks/` holding samples
   only, and doctrine tells every subagent to work in its own clone — so both
   gates bind **zero subagents by default**. This catches honest mistakes; the
   required CI checks remain the floor. Stated in both hook headers and in
   CONTRIBUTING.md rather than left for a reader to discover.
2. **The digest proves authorship-against-these-bytes, not review quality.**
   `pre-commit --print-scope-digest > artifact` forges it in one command. What
   it kills is the whole class that does not require intent: the stale artifact,
   the copy, the `touch`, the review written before the code. A deliberate liar
   is out of scope for a hook, and the census plus CI are the planes for that.
3. **`COMMIT_NO_REVIEW=1` still bypasses entirely.** Unchanged, Captain-scoped
   to docs-only/trivial commits, and loud on stderr.
4. **Working-tree scope (FW-026).** FW-025c evaluates the working tree, not the
   pushed SHAs — identical to FW-025 and FW-025b, and not made worse here.
5. **`find -name "*<slug>*"` treats the slug as a glob.** A branch name
   containing `[` or `?` could under-match. It can only fail to FIND an
   artifact, i.e. it fails toward BLOCK, so it is a usability edge, not a hole.

## Behaviour changes a future session will notice

- A >300-line commit now needs a digest-bearing artifact; a bare filename match
  no longer passes. The block message prints the exact line to paste.
- A >300-line commit whose staged paths are ALL under
  `shared/interfaces/reviews/` now blocks (previously passed). Hashing an empty
  record set would produce a constant any artifact could record, so the
  degenerate end fails closed; the message names `COMMIT_NO_REVIEW=1`.
- Master pushes from a hook-installed clone now pay ~1s of census before the
  eval suite, and are refused when a budget is breached or an allowance expired.

## Determinism of the digest (the property everything else rests on)

`-c diff.relative=false` (a user's `diff.relative=true` would emit cwd-relative
paths), `-z` (verbatim paths, so `core.quotePath` cannot move it),
`--abbrev=40` (an abbreviated object id is not a binding), `--no-renames` (a
rename record carries two paths and would break the one-path-per-record
grammar), `LC_ALL=C sort` (locale collation), and a newline-bearing path is
refused outright rather than silently splitting into two records. Deletions are
recorded as `000000 0{40} <path>` from git's own raw output, so a commit cannot
change what it removes without moving the digest — proven by arm (o).

## Verdict

APPROVE. No new module, no new schedule, no new Captain surface, no new
decider; both changed files already ran. Every new arm was observed rejecting,
and observed failing against pre-change code.
