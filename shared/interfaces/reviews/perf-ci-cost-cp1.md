# Checkpoint review — perf/ci-cost cp1 (2026-07-28)

Reviewed-Scope-Digest: 6c39b5c26127df86f77f781401689fc531f6654fcab77a419bf5b936a56741db

Scope: `.github/workflows/cabinet-ci.yml` (+166/−2), `docs/plans/ci-cost-2026-07-28.md` (+278).
444 LOC. Change class: **CI cost, enforcement-plane adjacent.** That class gets
the harder read, because the failure mode is not a broken build — it is a green
one over bytes nothing tested.

## What the diff does

1. Drops the dead `feat/fidelity-harness-design` ref from both trigger lists.
2. Adds a push-only `tree-dedupe` job that answers one question: has this exact
   git tree already been taken to green by a `pull_request` run?
3. Puts `needs: [tree-dedupe]` and one guard condition on all eight gate jobs.

## The one thing that could go badly wrong, and why it cannot

A job skipped by an `if:` is reported to branch protection as **success**. So
the whole risk of this change is a code path where a *pull request* gets its
required checks skipped — that is a green merge button over an ungated tree,
which is strictly worse than the bill it saves.

Checked, not assumed:

- Each guard reads `!cancelled() && (github.event_name != 'push' || …)`. On
  `pull_request` and `schedule` the second clause short-circuits **true** before
  any dedupe output is consulted. There is no expression value — no output, no
  conclusion, no absent job — that can make a non-push run skip.
- `tree-dedupe` itself carries `if: github.event_name == 'push' && github.ref
  == 'refs/heads/master'`, so it does not exist on the runs it could not help.
  A skipped `needs` dependency plus `!cancelled()` still runs the dependants;
  `needs.tree-dedupe.outputs.skip` is then `''`, which is `!= 'true'` anyway.
  Two independent reasons, either sufficient.
- A **failed** `tree-dedupe` also runs all eight, for the same `!cancelled()`
  reason. This is the direction that matters: the degenerate outcome of this
  job is a full run, never a skipped one.

## Fail-closed: executed, not read

The `run:` body was extracted **from the workflow file** (not retyped, which is
how a fixture ends up agreeing with the defect it was written from) and driven
against a mock `gh` across nine arms:

| arm | result |
|---|---|
| tree matches 1st candidate / 2nd candidate | `skip=true` |
| no candidate carries the tree | `skip=false` |
| head tree unresolvable | `skip=false` |
| candidate-runs query fails | `skip=false` |
| candidate list empty | `skip=false` |
| one candidate unresolvable, a later one matches | `skip=true` |
| every candidate unresolvable | `skip=false` |
| `gh` broken entirely (exit 3 on all calls) | `skip=false` |

Both directions present: the positive arms reach `skip=true` only through a
proven tree match, and every degenerate end — zero, empty, absent, error —
yields `skip=false`. `skip` is written once, from an `EXIT` trap, so no partial
path can leave a stale or duplicate value in `$GITHUB_OUTPUT`.

## Coverage argument

The claim is not "less testing is fine". It is that the skipped work is a
**second execution of identical bytes**. A git tree is the complete content of
the checkout; branch protection's `strict: true` forces a PR up to date with
master before merge, so the merge commit's tree equals the `refs/pull/N/merge`
tree already tested.

The two gates that read history rather than content were checked one at a time:

- `gitleaks` on push scans the pushed commit range — under `strict: true` the
  same commits the PR run scanned — and the full-history sweep is the nightly
  `schedule` run, which is never skipped.
- the architecture baseline ratchet compares base→head; its push base
  (`github.event.before`) equals the PR base for an up-to-date branch.

No other step in the file reads `github.event*` (verified by grep over the
workflow; no script reads `GITHUB_EVENT_NAME`).

## Self-certification chain

Evidence is accepted only from `event=pull_request` runs — a class this job can
never have skipped — so a skipped-and-therefore-"successful" run cannot become
the evidence for the next skip. Candidates are additionally filtered on
`head_repository.full_name == github.repository`.

## Weaker points, recorded rather than smoothed over

- **Evidence window is the last 40 successful PR runs.** A merge delayed past
  40 subsequent PR runs stops matching and runs fully. Wrong in the safe
  direction; costs money, never coverage.
- **`gh api` is a network dependency in the critical path.** Mitigated by
  fail-closed, proven above.
- **The saving depends on `strict: true` staying on.** If it is turned off,
  trees stop matching and the bill returns. Again: degrades toward more
  testing.
- **Latency**: master pushes wait ~10-20s on `tree-dedupe` before the gates
  start. PR runs are unaffected (the job is skipped).
- **The one-minute floor**: `tree-dedupe` costs ~304 billable minutes/month,
  already netted out of the reported saving.

## Security

zizmor 1.16.3 `--no-online-audits` over `.github/workflows/`: **no findings**
(advisory and `--min-severity high`). All untrusted-ish inputs enter the step
through `env:`; nothing is interpolated into a `run:` body. Job permissions are
`contents: read` + `actions: read`, the minimum for reading this workflow's own
run history.

## Verdict

**approve.** The saving is 21.1% measured over 30 days and 25.8% at the current
rate, with no gate removed, relaxed, path-filtered or thresholded. The three
cheaper options that would have paid in coverage — cancelling superseded master
runs, dropping the master push trigger, path-filtering docs — are recorded as
rejected in §5 of the plan doc rather than quietly not taken.
