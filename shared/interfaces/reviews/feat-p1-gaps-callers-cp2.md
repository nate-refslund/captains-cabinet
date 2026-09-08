# feat/p1-gaps-callers — checkpoint 2 (the round-2 fixer, 2026-09-08)

Round-1 verdict on PR #377 was **reject** at `06e2008e`, on three must-fix gaps
and two notes. This checkpoint closes all three must-fixes with sensors, decides
one of the two notes, and records the other as an explicit residual with its
trigger. No behaviour outside the holder-gap surface changed.

Base: `origin/master` = `e34ff1b8`. Interpreter `python3.12` everywhere; A0.3
re-verified by EXECUTION under `/usr/bin/python3` 3.9.6, not by import alone.

## The gaps, and what closes each

| Ref | What was wrong | Change | Sensor |
|---|---|---|---|
| G1 §3 return type | `unchanged` carried every standing gap id TWICE — both loops appended it | the resolve loop owns `unchanged`; the record loop only opens | `test_a_second_pass_reports_the_standing_gap_exactly_once` + a two-subject arm |
| G2 §3 callers | the two new never-raise wrappers had NO sensor: deleting either `except` killed a session or a pass with nothing going red | none (the behaviour was right) | two arms, each proved red by deleting the `except` it guards |
| G3 §3 error channel | `_observe_gaps` reported to stderr, which the only production caller discards (`2>/dev/null`) | `claims.record_error` — the seam the sibling claim path already used; `observe_holder_gaps` writes BOTH channels | the pull-path arm asserts `claims.err`; the record/resolve arms assert it too |
| G4 A3.1 / U3a handover | a Captain decline was silently reverted on the next pass | a declined keyed gap is MUTED — never re-recorded, never resolved | two arms; the second is red against the NAIVE fix (folding declined into `live` starts resolving declined rows) |
| G5 lock width | `claims_lock` spans the whole observation incl. a full `project_gaps()` replay | **not changed** — recorded as a residual with its trigger | — |

## Red-before-green, per arm

Purged `__pycache__`, `PYTHONDONTWRITEBYTECODE=1`, `python3.12 -m pytest -p
no:cacheprovider`.

Red against the PR's own pre-fix bytes (`06e2008e`):

* `test_a_second_pass_reports_the_standing_gap_exactly_once` — rc 1,
  `AssertionError: {'opened': [], 'resolved': [], 'unchanged': ['gap-1a592313',
  'gap-1a592313']}`
* `test_two_standing_subjects_are_two_unchanged_entries` — rc 1, four entries
  for two subjects
* `test_a_declined_holder_gap_is_never_re_recorded` — rc 1,
  `{'opened': ['gap-1a592313'], ...}` after the decline
* `test_a_record_failure_never_kills_the_pass` — rc 1, *the record failure left
  no durable trace*
* `test_a_resolve_failure_is_recorded_durably_too` — rc 1, `FileNotFoundError:
  …/events/claims.err`
* `TestGetNextTask::test_a_failing_observation_never_costs_the_pull` — rc 1,
  *the observation failure left no durable trace*

Red only against a MUTANT, because the behaviour they pin was already correct
and unsensored (this is G2's whole point) — mutant applied, run, restored, and
`git status --porcelain` clean after each:

* delete the `except` in `supervisor.find_unassigned_ready_tasks` →
  `TestFindUnassignedReady::test_a_failing_observation_never_costs_the_pass`
  rc 1, `RuntimeError: the observer is down`
* delete the `except` in `session_bridge._observe_gaps` →
  `TestGetNextTask::test_a_failing_observation_never_costs_the_pull` rc 1, same
  exception
* fold declined gaps into `live` (the naive G4 fix) →
  `test_a_declined_holder_gap_is_not_resolved_either` rc 1,
  `{'resolved': ['gap-492c71b7']}` — the cabinet resolving a row the Captain
  declined

DISCLOSED: `test_a_declined_holder_gap_is_not_resolved_either` is green in both
directions against `06e2008e` (a declined gap was dropped from `live` there too,
so nothing resolved it). It is red against the naive fix above, which is the
thing it exists to stop, and it is stated here rather than counted as a
red-before-green arm.

## Budget (A0.9)

`framework_production_noncomment_lines` maximum `66518 → 66524` (+6), measured
with `cabinet/scripts/cognitive-architecture-census.py` on the committed tree:
observed `81262` against the then-effective `81256`. +3 for the fixes, +3 for
the `_live_gap_with_id` docstring that records where the decision it delegated
landed. Dated paragraph in the row's comment; `framework_production_modules`
unchanged at 253. Zero headroom, observed == maximum. NOTE, for whoever reads
this next: `cognitive-architecture-census.py` prints `FAIL` and `BLOCK` but
exits **0** — the gate here is the printed line, not the exit code.

## Residual, stated rather than implied

The claims lock is held wider than A3.1 asks: `_observe_gaps` holds it across a
full `project_gaps()` ledger replay plus both loops, on every claiming
`get_next_task`. Correct and deadlock-free, and A3.1's letter is satisfied by a
wider hold. Not narrowed here because the phase-1 runtime set is one worker
(A0.7), and narrowing means `observe_holder_gaps` taking the claims lock
itself — the property the module comment relies on to argue it cannot invert
the order. **Trigger: a second concurrent worker.** Candidates: bound the
critical section to the record call, or give `project_gaps` a `since` window.

The `/gaps` ranking residual from cp1 is unchanged and re-stated in
`docs/proposals/holder-gaps-expansion-2026-09-08.md` §4.

## Laws re-checked on this checkpoint

* Locked set: 80 entries parsed out of `cabinet/scripts/germline-lock.sh`
  (73 FILES + 7 DIRS) intersected with the 14 changed paths — empty.
* A0.10: `cabinet/cron/mission-supervisor.sh` is untouched and still unpinned,
  so its PENDING row in `framework/tests/test_interpreter_pin.py` stays.
* A0.3: `/usr/bin/python3` 3.9.6 ran `get_next_task`, `find_unassigned_ready_
  tasks`, a second `observe_holder_gaps` pass and a decline end to end.
* Agnostic: no tool, vendor, industry or role noun entered a name, kind, need
  or doc.
