# feat/p1-drill-red — checkpoint 2: every stage verdict fails CLOSED

Reviewer verdict on cp1 (d53740f6) was REJECT on one blocking finding. This
checkpoint closes it and the four notes filed with it. Nothing about the unit's
scope changed: no subject unit is built, no CI job is wired, no
test_drill_wiring.py (both U4g, per §8 L6 / A4.9).

## The blocking finding, restated in one line

Six stage verdicts and three P7 event counts scored an assertion that could not
RUN as a PASS. `PROBLEMS="$(python …)"; [ -z "$PROBLEMS" ] || fail` reads a
crashed block's empty stdout as "no problems found"; at P1 the block's stderr
was folded (`2>&1`) into the very file the verdict was parsed from, so one
library line made the payload unparseable and the stage printed a claim that
was false in every clause; `[ "$ROLLED" != "0" ]` reads an empty count as "more
than none". The reviewer proved it live in both directions.

## What changed

- NEW `cabinet/scripts/drills/lib/verdict.sh` — the fail-closed contract in one
  place: every assertion block prints one `{code, problems}` json line then a
  sentinel line only a block that ran to its end can print, with its stderr in a
  SEPARATE file. `read_verdict` refuses a non-zero block exit, a missing
  sentinel, a non-json verdict, a verdict that is not `{code, problems}`, a pass
  that names problems and a failure that names none — each becomes a failure of
  that stage carrying the stage's own exit code. `vfield` refuses a field the
  verdict did not carry (the old readers printed the string `None`).
  `event_count`, `sha256_of` and `ledger_lines` refuse a value they could not
  take. None of them may be called inside `$( )`: `exit` there exits only the
  subshell, which would restore the fail-open being removed.
- All nine stage sites (P1, P2, P2b, P3, P4, P2h ×2, P5, P6) route through it.
- P7: the three event counts, the preserved-path digest pair and the locked-path
  digest pair are taken fail-closed; the second `publish`'s rc is checked and
  `LOCK_SHA` is guarded for emptiness exactly as `BUNDLE_SHA` is.
- P3: the killed holder's claim token must be readable and non-empty, or P4
  cannot tell a NEW claim from the dead holder's old one.
- Hermeticity: the before-picture files must exist before the after-comparison.
- `set -m` plus a group kill in the trap: the locked-hook legs are pipelines
  whose children are in nobody's `$WORKER_PIDS`.
- `worker.py --pause-timeout` default 60 s → 30 s and the P3 call site 40 → 30,
  inside the contract's "every wait a bounded inline poll (≤ 30 s)".
- `docs/plans/declared-residuals-register.md`: RES-028 registers the §4 P4
  task-002 second race as superseded by A2.3.

## Sensors — red before, green after, measured this session

| Sensor | Red on d53740f6 | Green on this tree |
|---|---|---|
| Live P1, control: staged tree with `captain_ratified: False` | `FAIL [P1] exit 10 — row captain_ratified is False` | same, exit 10 |
| Live P1, probe: the same defect plus ONE stderr line during the block | `PASS [P1] resp-001 ratified through the terminal door by nate, one event, actor operator` then exit 20 at P2 | `FAIL [P1] exit 10 — row captain_ratified is False` |
| Stage decision code, all 9 sites × 4 degenerate ends (block died / printed nothing / claimed a pass while naming a defect / found a defect with stderr noise) | 15/36 cells fail-closed, **21 NOT** | **36/36** |
| P7 counts and digest pairs at the degenerate end (ledger unimportable, files absent) | 0/5 fail-closed | 5/5 |
| A background hook leg's grandchild after the trap fires | stray survives | no stray |

The stage-decision probe lifts each site's shell region VERBATIM out of the
drill under test and replaces only the python body, so what is measured is the
shipped construct in both directions.

## The contracted red arms still hold on this tree

| Arm | Exit | Reason |
|---|---|---|
| unstubbed, master's subjects | 10 | `No module named 'framework.outcomes'` |
| P1 stubbed through `--tree` | 20 | 8 got the item, 0 `work_item_started` events landed |
| pull path removed (A4.1) | 21 | an ImportError is not the red the claim invariant names |
| export manifest with every `delete instance/` line stripped | 64 | refuses to hatch this deployment's own state |
| A4.3, hostile `DATABASE_URL`/`ORG_RUNTIME_DB`/`REDIS_*`/`CABINET_*`/`PYTHONPATH`/`OFFICER_NAME` | 20 | normalized verdict identical to the clean run; zero "db write failed" lines |

Residue after this session's runs: no stray worker/stub/hook process, no
`/tmp/.session-task-injected-drill-*`, no surviving scratch dir.

## Locked set

`git diff --name-only origin/master...HEAD` plus the working tree, intersected
with the parsed `germline-lock.sh` FILES (73) / DIRS (7): EMPTY.
