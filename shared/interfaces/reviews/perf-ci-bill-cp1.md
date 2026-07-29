# perf/ci-bill — checkpoint 1 review (FW-019)

Reviewed-Scope-Digest: 1b4657f9e9901e3f5ab3081ac9d38d8ba4279a7f269070e16413173969a5fa89

Branch: `perf/ci-bill` · base `origin/master` @ 70d6ae13 · 2026-07-29
Scope: 7 staged paths (workflow, `null-hatch.sh`, two plan docs, the ledger,
`framework/fidelity/retro.py`, `instance/flavor-a/README.md`).

## What this commit claims

The Actions bill drops by 2,352 billable minutes/month (9.8% of a measured
23,895 over the 30 days to 2026-07-29; 3 of 60 minutes on a full pass at
today's rate) **without removing a single assertion.** Two checks that could
not fail now can.

## The three removals, each with what still catches the class

| removed | why it is not coverage | what catches the class now |
|---|---|---|
| `clean-room-foundation` job | its only work step is `null-hatch.sh` stage 1/4, character for character | null-hatch stage 1 (launcher ratchet + Testburg runtime proof) |
| `clean-room-source` job | its four work steps are null-hatch stages 2-4; the in-workflow CORE import list had already drifted **weaker** (missing `framework.evolution.contracts`) | null-hatch stages 2, 3, 4 — committed tree, throwaway `$HOME`, one module more |
| `zizmor` job | job wrapper only; both invocations, same flags, same pinned 1.16.3, same run, same tree | the same two steps, now inside `gitleaks` |

Nothing was renamed. Branch protection loses three contexts and gains none —
chosen deliberately, because an added context cannot be reported by an open
PR's older workflow and would stall the whole queue (eight PRs draining).

## Verification performed (this session, on these bytes)

- **Superset proof by reading, not by name.** `cabinet/scripts/null-hatch.sh`
  stages 1-4 read side by side against `cabinet-ci.yml` job bodies; the only
  divergence found runs in the *deleted* direction (the workflow copy lacked
  `framework.evolution.contracts`).
- **Census dead-sensor proven by execution, both directions**: `bash -e` +
  pipe to `tail` returns 0 over a pytest exit 2; with `set -o pipefail` it
  returns 2; control without the pipe returns 2.
- **Workflow-reading tests re-run green** against the modified file:
  `test_ci_covers_cron.py` (4 passed — it round-trips the real `run:` bodies,
  so it is not a token sweep), `test_evals_redis_sandbox.py::
  test_ci_declares_its_service_container_disposable` (1 passed — the
  declaration/marker-step ratio still holds, 3 ≥ 2), `test_baseline_set_
  ratchet.py -k step` (2 passed — exactly one baseline-ratchet step still
  present across all jobs).
- **`zizmor --no-online-audits --min-severity high`** over the modified
  `.github/workflows/`: no findings, exit 0. Advisory pass: no findings.
- **YAML parses**; job set 8 → 6; `ci` keeps all 40 steps and all five
  `Bash syntax check` step names plus the shellcheck step (the cron-coverage
  test extracts them by name).
- `check-layer-separation.sh` new=0 · `docs-track-code-sweep.sh` GREEN
  (64 files, 0 findings) · `ledger-status-parity.sh` GREEN (353/353) ·
  A13 parity GREEN (353 ids) · `bash -n` + `shellcheck --severity=error` on
  `null-hatch.sh` clean.
- **Germline untouched**: `cabinet/scripts/germline-lock.sh` not in the diff;
  no `schg` path staged (checked with `ls -lO`, not with a grep of the lock
  script — the grep gave a false "free" verdict for
  `memory/golden-evals/eval-021-source-boundary.md`, which is in fact locked,
  and that file was left alone and recorded as a handback instead).

## Teeth check still owed at CI time

The composed gate must be shown to still FAIL. Post-push, break one arm each
surviving required job owns and confirm red per job before merge:
`null-hatch` (launcher literal into `framework/**`), `gitleaks`+zizmor (a
seeded secret / a high-severity workflow finding), `framework-tests` (the armed
census over a deliberate collection error), `ci` (vitest under a failed
typecheck must now still run).

## Deliberately not done

`pytest-xdist` on `cabinet/scripts/tests` (1,088s — 30% of the bill), the two
361s steps in `ci`, and any move to master-only/nightly. Reasons and the
cutover protocol are in `docs/plans/ci-bill-2026-07-29.md` §5. Short form: the
xdist hazards are measured and the outcome is not, that directory holds the
killswitch and freeze fences, and `strict: true` makes a red master a fleet
stall while `tree-dedupe` has already made the master lane nearly free.
