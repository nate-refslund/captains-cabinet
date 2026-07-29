# perf/local-ci — checkpoint 1: CI duplicate-tree guard

Reviewed-Scope-Digest: d2ebdb822a7cf73cc53cc6fd14748e48f4de6e1acafdd4305bfbc5d2066c92b9

## What this checkpoint contains
- `.github/workflows/cabinet-ci.yml` — new `duplicate-tree-guard` job; all
  eight existing jobs gated on its `skip` output.
- `cabinet/scripts/ci-duplicate-tree-guard.py` — the decision, pure and
  fail-open.
- `cabinet/scripts/tests/test_ci_duplicate_tree_guard.py` — 57 arms.

## What was reviewed, and against what
The only expensive defect here is a FALSE SKIP: GitHub counts a `skipped`
check run as SUCCESSFUL for branch protection, so a guard that emitted skip on
a `pull_request` would report all seven required contexts green over a tree
nothing ran on. Reviewed against that single question.

- **Double lock on the event.** The workflow gates the guard JOB on
  `push` + `refs/heads/master`; `decide()` independently re-derives the
  same predicate and refuses otherwise. Either alone suffices. Both are pinned,
  and the shape checker is proven to FAIL when either is removed (six mutation
  arms, one per lock).
- **Fail-open direction.** Every unknown, error and degenerate input returns
  skip=False. Verified explicitly for: empty required set, zero-job run,
  non-list jobs, junk candidate entries, unresolvable git, empty API result.
  The CLI always exits 0 — the guard cannot itself red master.
- **The evidence is per-JOB, not per-run.** A run concluding `success` with a
  required job skipped is not proof for that job; one arm per required job
  drops it and one reds it, 14 arms total.
- **Cancelled is not green.** Explicit arms for conclusion=cancelled and
  status=in_progress/queued.
- **Lossless, argued from the tree hash.** Identical tree == identical bytes
  for every file the suite reads. The two history-reading steps
  (`cognitive-phase4`'s baseline ratchet, `gitleaks`) resolve to the same
  comparison on a merge as on its second parent under `strict: true`; the
  nightly schedule run, never skipped, remains the environment-drift sensor.

## Non-vacuity, both directions
- 57/57 pass on this tree; the 8 workflow-shape arms FAIL against
  `origin/master`'s workflow (measured, cache purged) — the sensor is wired to
  the live artifact, not to a fixture.
- The skip path was exercised end-to-end against the LIVE API on three real
  master merges (8bab4c32, adab6ec0, 49ed144e): skip=true naming runs
  30397272506 / 30394947770 / 30389656699; the same three return skip=false
  when the event is `pull_request`.

## Residual, stated
Same-day environment drift on an already-tested tree is not re-observed on the
merge push. The nightly run is the designed control for that class and is out
of the guard's scope by construction.
