# feat/p1-lease-floor — cp1: merge with master (landing agent, 2026-09-08)

Checkpoint 1 is the merge-with-master commit only. **No code change to the
unit.** The approved head `93a371110d5e962f2bc63885002993b00f9b21dd`
(independent review, round 1, APPROVE, posted on PR #375) is the first parent;
`origin/master 7d3719dcea9439a113f6391d85f6c2dc51a1fec6` (U6 — no skeleton
proposals, itself carrying U3b — gaps, not silence) is the second.

Reviewed-Scope-Digest: e6750aaf64393a011c22df854153da586309d2c1ea5009e453b9b64cd461e9aa

## Overlap and its resolution

`git diff --name-only` on the two sides intersects on exactly ONE path:

    cabinet/config/cognitive-architecture-contract.yml

Both sides raised `budgets.framework_production_noncomment_lines.maximum` off
the SAME 66280 base:

| side | raise | to |
|---|---|---|
| origin/master (U3b gap callers +238, its round-2 fixes +6, U6 no-skeletons +83) | +327 | 66607 |
| this branch (U2b lease floor) | +31 | 66311 |

Per contract AMENDMENTS round 2 (A0.9) and this file's own MERGE precedent, the
merged ceiling is the **SUM of the raises over the common base**, never the max
of the two: `66280 + 244 + 83 + 31 = 66638`. Every expansion paragraph from
both sides is kept verbatim; a `MERGE, 2026-09-08` paragraph naming the
disjoint mass was added above the value.

The masses are disjoint by file: the landed side is
`framework/missions/gaps.py`, `session_bridge.py`, `supervisor.py`,
`framework/frontdoor/run_briefing.py`, one line of
`framework/learning/capability_gaps.py`, `framework/roles/evolution.py` and the
proposal-stage counters in `framework/learning/self_improvement_loop.py`; this
branch is `framework/missions/claims.py` alone.

**RE-MEASURED on the merge tree, not added on paper** —
`python3.12 cabinet/scripts/cognitive-architecture-census.py --check`:

    cognitive architecture census: PASS
      framework_production_modules: 253 <= 253
      framework_production_noncomment_lines: 81376 <= 81376

and the row is a live sensor, not decoration: with the value left at master's
`66607` the same census **BLOCKS** —
`BLOCK framework_production_noncomment_lines: budget exceeded (81376 > 81345)`.
So `+31` on top of the landed ceiling is neither over- nor under-raised.

## A0.10 — interpreter-pin PENDING rows

No resolution needed. This unit pins no script.
`cabinet/scripts/work-graph-complete.sh`'s PENDING row was already retired by
U2 (`framework/tests/test_interpreter_pin.py:110`);
`cabinet/cron/mission-supervisor.sh`'s row stands and is not this unit's to
delete. `framework/tests/test_interpreter_pin.py` is green on the merge tree.

## Locked set

`git diff --name-only origin/master...HEAD` intersected with the set parsed
from `cabinet/scripts/germline-lock.sh` FILES/DIRS (80 entries, exact paths and
directory prefixes): **empty**. Nothing under `cabinet/scripts/hooks`;
`journey.py`, `gate.py`, `grants.py` and the companion are untouched.

## Why no other conflict

The two sides touch no other common path, and the merge is otherwise a
fast-forward of master's files into the branch. The only semantic coupling is
that master's `framework/missions/gaps.py` now calls `claims.record_error` —
the same seam this unit's `resolve_lease_floor()` records its unparseable-floor
line through. Both are exercised green in the post-merge battery
(`framework/missions/tests/test_gaps.py` and
`framework/missions/tests/test_claims.py::test_an_unparseable_floor_is_recorded_and_ignored`).
