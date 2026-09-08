# feat/p1-no-skeletons — cp2: merge with master (landing agent, 2026-09-08)

Checkpoint 2 is the merge-with-master commit only. No code change to the unit.
Approved head `d540d149a2484332e56cbe5a209e02c3e0a90e77` (independent review,
round 1, APPROVE) is the first parent; `origin/master d8e92778` (U3b — gaps,
not silence) is the second.

## Overlap and its resolution

`git diff --name-only` on the two sides intersects on exactly ONE path:

    cabinet/config/cognitive-architecture-contract.yml

Both sides raised `budgets.framework_production_noncomment_lines.maximum` off
the SAME 66280 base:

| side | raise | to |
|---|---|---|
| origin/master (U3b gap callers + its round-2 fixes) | +238, then +6 | 66524 |
| this branch (U6 no-skeletons) | +83 | 66363 |

Per contract AMENDMENTS round 2 (A0.9) and this file's own MERGE precedent, the
merged ceiling is the **SUM of the raises over the common base**, never the max
of the two: `66280 + 244 + 83 = 66607`. Every expansion paragraph from both
sides is kept verbatim; a `MERGE, 2026-09-08` paragraph naming the disjoint
mass was added above the value.

The two masses are disjoint by file: U3b is `framework/missions/gaps.py`,
`session_bridge.py`, `supervisor.py`, `framework/frontdoor/run_briefing.py` and
one line of `framework/learning/capability_gaps.py`; U6 is
`framework/roles/evolution.py` and the proposal-stage counters in
`framework/learning/self_improvement_loop.py`.

**RE-MEASURED on the merge tree, not added on paper** —
`python3.12 cabinet/scripts/cognitive-architecture-census.py`:

    cognitive architecture census: PASS
      framework_production_modules: 253 <= 253
      framework_production_noncomment_lines: 81345 <= 81345

81345 observed against an effective ceiling of 81345 — zero headroom, exactly
as both source paragraphs promise. (`framework_production_modules` 212 -> 213
came from master alone; U6 adds no production module.)

## Sanctioned resolutions NOT needed here

* **A0.10 (interpreter-pin PENDING rows).** U6 pins no script. Its only
  `cabinet/` edit is a comment block in `cabinet/cron/role-evals-weekly.sh`,
  which is not in `framework/tests/test_interpreter_pin.py::PENDING`. The one
  live PENDING row (`cabinet/cron/mission-supervisor.sh`) is untouched and
  still honest.
* **A0.9 (event registration).** U6 registers no event type. No
  `architecture-baseline-sets.yml` line on either side of the merge.

## Locked set

`git diff --name-only origin/master...HEAD` intersected with the parsed
`cabinet/scripts/germline-lock.sh` FILES + DIRS (prefix match) is empty; the
merge adds no path to that range. Re-run mechanically before the commit.

## Re-verification

The full CI-outage battery was re-run on the merged SHA in this same fresh
clone, and the pre-existing failing set was re-confirmed ONCE on a pristine
`origin/master d8e92778` worktree of it first. Per-test and per-harness verdict
lines were diffed, not counted. The evidence table is on PR #376.
