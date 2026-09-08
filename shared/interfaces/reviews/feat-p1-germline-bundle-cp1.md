# Checkpoint review — feat/p1-germline-bundle (cp1)

Reviewed-Scope-Digest: c4956df79b6b55a9c6991ab94df2e05b2fdabbb96626eca4a3190eb38869918f

Reviewer: builder, second pass over the staged bytes with the contract (§7 +
A7.1-A7.4) open beside them. Every claim below was executed, not read.

## What is in the diff

Ten paths, 1074 added lines, 0 deleted. No path is in the germline set — proved
mechanically against `update_bundle.parse_locked_set(germline-lock.sh)` over the
whole staged set, intersection empty, and the same predicate ships as a standing
test arm.

| path | why |
|---|---|
| `docs/proposals/germline-amendment-employee-phase1-2026-09.md` | the apply contract |
| `.../germline-amendment-employee-phase1-2026-09/{G1,G3}.diff` | the proposed bytes, one unified diff per file, full-index blob shas |
| `.../germline-amendment-employee-phase1-2026-09/verify.sh` | the bundle's own gate |
| `cabinet/scripts/tests/test_germline_bundle.py` | the sensors |
| `framework/tests/test_amendment_doc_lint.py` | one `_PACKAGES` entry ("a new package = ONE table entry") |
| `docs/plans/operative-egg-{ledger,plan}-*` | the CG-36 row and its A13 twin |
| `cabinet/scripts/egg-export-manifest.txt` | delete + expect-absent for the sensor, whose subject archives out |
| `.github/workflows/cabinet-ci.yml` | `fetch-depth: 0` on the job that runs the branch guard |

## What I attacked, and what it cost

**The diffs could be decorative.** `git apply --check` alone accepts a patch
whose hunks still match while everything around them has moved. Executed: an
off-hunk edit to each target still applies (G3) or still reverse-applies (G1),
so the check alone would have said "fine". `verify.sh` therefore pins the
post-image `sha256` as a second, independent channel, and
`test_drift_outside_the_patch_context_is_also_a_refusal` is the arm that proves
the pin is load-bearing. Both refusal channels exit 10 and both have an arm.

**The guard could be green in both directions.**
`test_phase1_touches_no_locked_path` passes on a branch that behaved and would
pass identically if `is_locked` answered False to everything. Two arms close
that: `test_the_guard_flags_a_locked_path` drives the predicate with a named
locked FILE, a path under a locked DIRECTORY and two innocent paths; and
`_locked()` asserts the parsed boundary is >= 50 entries before anything is
intersected with it, because an empty boundary makes every claim here trivially
true.

**The guard could silently not measure.** A7.3. `_resolve_base` refuses on a
shallow checkout, on a tree with no git, and on a base ref that does not
resolve — and `test_the_guard_refuses_an_unreachable_base` drives two of those
three to a raised exception. The CI job that runs this directory checked out
shallow, so the guard would have refused there for real; `fetch-depth: 0` is the
wiring that lets it measure, and its comment names the guard.

**The sensor could ship without its subject.** `docs/proposals/` archives out of
the egg entirely (R167) and so does the `docs/plans` pair (R145). A shipped
`test_germline_bundle.py` would be a guaranteed red in a stranger's fresh hatch.
Same class as `framework/tests/test_amendment_doc_lint.py`, which the manifest
already deletes for the identical reason; paired `delete` + `expect-absent` rows
added, matching the convention `test_egg_export.py` enforces elsewhere.

**The post-image could be wrong shell.** `bash -n` runs over every post-image
inside `verify.sh`, and the G3 post-image was syntax-checked standalone during
authoring. Two degenerate ends in the G3 bytes were closed deliberately and are
named in the doc §2: `${HOME:-/tmp}` (the script runs under `set -u`, and an
unset HOME would abort the tick) and `mkdir -p` of the log directory before
first use (appending to a path whose directory is absent fails the redirection
and would silently disable the injector — the exact failure the change exists to
end), degrading to `/dev/stderr` rather than back to `/dev/null`.

## Red-before-green

Nine of the twelve bundle arms and six of the amendment-lint arms were run
against the pre-change bytes (deliverables removed, ledger/plan restored to
master, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`) and failed with the
texts recorded on the PR. The three that do not go red that way are the branch
guard and its two inverted arms — a guard is green by construction on a branch
that behaved, which is why its failure modes carry their own arms rather than
relying on absence.

## Residuals I am NOT closing here

G2 (dropped per A7.1 — its replacement event type is deliberately unregistered
in phase 1, A0.5) and G4 (A7.4). Both are named in the doc §8 and in the CG-36
note. The `CABINET_HOOK_LOG` file has no rotation; that belongs to the log
plane, not to a locked hook.

## Verdict

Approve for landing. Scope is the contract's §7 and nothing else; every
invariant it names has an executed sensor; both new refusal paths have inverted
arms; no locked path is touched.
