# perf/local-ci — checkpoint 3: the dedup precondition, made executable

Reviewed-Scope-Digest: 498308bf51b79985ed425fd169856ee6a1de4c61b45ebdb9e7281f0ba3ab629a

## Why this checkpoint exists
PR #272 landed `tree-dedupe` on master while this branch was in CI, solving the
same problem this branch's `duplicate-tree-guard` solved. This branch deleted
its own mechanism rather than shipping a second skip path on one workflow.

## What was reviewed
`tree-dedupe`'s safety argument rests on two header claims. Claim 1 — a
pull_request run can never be skipped — is the load-bearing one, because GitHub
reports an `if`-skipped job as SUCCESSFUL to branch protection. Claim 5 — a
run-level success means all eight jobs ran — is NOT a property of GitHub (a run
concludes success when jobs are merely skipped); it is true here only because
of claim 1. Both are properties of expression strings in a YAML file.

- `test_ci_dedupe_cannot_skip_a_pr.py` evaluates the REAL `if:` expressions
  under a simulated pull_request context, for every value of the dedupe output,
  across pull_request / schedule / workflow_dispatch.
- The evaluator parses via a restricted AST walk, not `eval`, and REFUSES any
  node or identifier it does not model rather than guessing — a silent
  mis-parse would be a sensor agreeing with what it failed to read.
- The workflow comment now states the precondition instead of asserting the
  conclusion, and names the test.

## Non-vacuity, both directions
- The same evaluator must report the gate jobs SKIPPED on a master push with
  `skip=true` — so it measures the mechanism rather than agreeing with it.
- Nine mutation arms strip the event guard from each gate job in turn (and one
  inverts it) and require the check to FAIL.
- Three evaluator arms in both directions plus a refusal arm.
- Run against the pre-`tree-dedupe` workflow (a70bcfb5), three arms FAIL —
  wired to the live artifact, not to a fixture.
- 25/25 green on this tree; the workflow body is otherwise byte-identical to
  master's (comment-only change, verified by diff).

## Residual, stated
This does not add a per-job assertion to `tree-dedupe`'s runtime evidence
check. The hole it would close is unreachable today — proven by the arms above,
which is precisely why a test is the right control and a second runtime
mechanism is not.
