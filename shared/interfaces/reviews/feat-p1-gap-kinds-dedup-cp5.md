# feat/p1-gap-kinds-dedup — checkpoint 5 (the landing merge with master)

Landing agent, Opus 5, 2026-09-08. The unit was approved at `d09d0619`; master had
moved to `d997a575` (U4-red, PR #374). This checkpoint records the one SEMANTIC
interaction the merge produced and how it was resolved. Every claim carries the
command that produced it, run this session in a fresh clone at
`/private/tmp/.../land/U3a` under `python3.12` (3.12.13).

## The merge itself

`git merge origin/master` — clean, no textual conflict. The two units' file sets
are disjoint: U4-red adds `cabinet/scripts/drills/{one-responsibility.sh,lib/*}`
and `docs/plans/declared-residuals-register.md`; U3a touches the gap plane, the
dashboard and `framework/tests/test_interpreter_pin.py`.

## The interaction: a whole-tree ratchet meets a new file

`test_interpreter_pin.py` scans a DERIVED scope — every tracked unlocked
`.sh`/`.ts`/`.tsx` mentioning a gap/pull-plane token — precisely so a new file is
in scope the day it is written. U4-red wrote such a file. On the merged tree,
before any fix:

```
$ python3.12 -m pytest framework/tests/test_interpreter_pin.py -q -p no:cacheprovider
FAILED TestA03InterpreterPin::test_no_bare_python3_in_an_unlocked_plane_exec_string
E  A0.3: unlocked exec strings on the gap/pull plane must pin `${CABINET_PYTHON:-python3.12}`.
E      cabinet/scripts/drills/one-responsibility.sh:135  BOX_PY="python3"   # what the locked hook pins (session-task-inject.sh:28)
1 failed, 13 passed
```

The scanner is right that the line is there and wrong that it is a defect.

## Why the drill's bare interpreter is CORRECT, not a miss

`BOX_PY` has exactly one consumer, drill stage P2h
(`one-responsibility.sh:945-951`): it imports `framework.missions.session_bridge`
under the box's own interpreter and fails 21 if that import breaks. That stage IS
how contract A0.3's locked half — "every module the locked hook can import stays
importable and correct under Python 3.9" — is measured at all, because the locked
hook (`session-task-inject.sh:28`) execs a bare `python3` and cannot be pinned
without a Captain ceremony. Pinning line 135 would make the drill assert 3.12
against itself and report nothing about the interpreter an officer actually walks:
the sensor would be testing something other than the control. Contract A4.1 says
this in as many words — "the hook stage runs the locked bytes with the box's own
`python3`".

So the resolution preserves both intents: the drill keeps its bare interpreter,
and U3a's ratchet keeps every other line of that file in scope.

## The resolution — one line excused, self-retiring, in the module's own idiom

`SANCTIONED: Dict[str, Dict[str, str]]` beside the existing `PENDING`, keyed by
path AND exact code text, with three new arms. Keying by code text rather than by
path is the whole point: a file-level waiver would have hidden every future bare
interpreter in a 1,370-line drill.

RED before / GREEN after — each arm run against a mutated tree this session,
`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` purged:

| # | arm | mutation | RED evidence | after restore |
|---|---|---|---|---|
| 1 | `test_sanctioned_lines_are_still_bare` | drill line 135 pinned to `${CABINET_PYTHON:-python3.12}` | ``FAILED … E AssertionError: cabinet/scripts/drills/one-responsibility.sh — `BOX_PY="python3"` no longer carries a bare interpreter; delete this SANCTIONED row`` · 1 failed, 16 passed | 17 passed |
| 2 | `test_no_bare_python3_in_an_unlocked_plane_exec_string` (narrowing) | a SECOND bare `python3` added to the sanctioned file (`SNEAK=$(python3 -c "print(1)")`) | `E  cabinet/scripts/drills/one-responsibility.sh:136  SNEAK=$(python3 -c "print(1)")` — still a finding | 17 passed |
| 3 | same arm (the core invariant, unchanged) | `record-capability-gap.sh` pin reverted to bare `python3` | `E  cabinet/scripts/record-capability-gap.sh:54  "python3" - <<'PY'` · 2 failed (the positive arm reds too) | 17 passed |
| 4 | `test_every_sanctioned_file_is_actually_on_the_plane` | a row added for `cabinet/scripts/germline-lock.sh` (locked, never scanned) | ``E AssertionError: ['cabinet/scripts/germline-lock.sh']`` | 17 passed |

Arm 2 is the one that matters: it proves the excuse is a LINE, not the file.
Arm 1 makes the row self-retiring — the day someone pins or deletes that line the
row goes red and must be re-argued, exactly as `PENDING` rows do.

`test_a_sanctioned_file_is_not_a_sanctioned_file` pins arm 2's property as a unit
test on the pure function, so the narrowing survives without a mutated tree.

## What did NOT need resolving

- **A0.10 PENDING rows** — both (`cabinet/scripts/work-graph-complete.sh`,
  `cabinet/cron/mission-supervisor.sh`) are still violating on the merged tree;
  `test_pending_entries_are_still_violating` is green. Neither owner has landed.
  U2's lander deletes the first row; U3b's the second.
- **Event registration (A0.9)** — U3a registers no event type; nothing to sum.
- **`cognitive-architecture-contract.yml` maxima** — U4-red raised none, so there
  is no two-sided raise to add. `python3.12 cabinet/scripts/cognitive-architecture-census.py
  --check` → `PASS`, `framework_production_noncomment_lines: 79520 <= 79520` on the
  merged tree (the +72 lines here are a test module; the budget counts production).
- **Locked set** — `git diff --name-only origin/master...HEAD` ∩ the set parsed
  live from `germline-lock.sh` (73 FILES, 7 DIRS) = `[]`.
