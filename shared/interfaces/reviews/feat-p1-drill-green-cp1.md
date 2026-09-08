# feat/p1-drill-green — checkpoint 1

Reviewed-Scope-Digest: 84e6a76e3cf4de0de27492319baf0fb368cc786913a24439eb94f92d89b8817c

**What.** The phase-1 acceptance drill, run against master with every subject landed,
fixed where the DRILL was wrong, and wired into a CI job of its own. Five paths:
`cabinet/scripts/drills/one-responsibility.sh`, `cabinet/scripts/cabinet-update.sh`
(the one sanctioned seam), `cabinet/scripts/tests/test_drill_wiring.py` (new),
`cabinet/scripts/tests/test_cabinet_update.py` (one arm), `.github/workflows/cabinet-ci.yml`.

**The rule this checkpoint was held to.** Fix drill bugs only. A subject that fails the
contract is a blocked report, not a patch. Every defect below was measured by running
the drill on a fresh clone of origin/master f07d5b95 and reading what it said, and every
one of them turned out to be the drill mis-reading a subject that was behaving exactly
as its own contract and docstring describe.

## The six drill defects, and how each was proved to be the drill's

| # | Stage | The drill said | What was actually true |
|---|---|---|---|
| 1 | P2b | `observe_holder_gaps opened ['gap-adb8301e'] holder gaps … expected 1` | `observe_holder_gaps` returns LISTS of gap ids (gaps.py:229 docstring, :309 return). The drill compared the list to the integer 1, so a correct single gap read as wrong. |
| 2 | P3 | `w1 never claimed within 10s: {"task": null}` | P2's race winner still HELD task-001 on the production 900 s lease, and A2.3 says a tick that finds its own live claim renews it and returns `None`. Nothing could claim that item for fifteen minutes. The drill never stood the winner down. |
| 3 | P2h | `the locked hook's interpreter (python3, 3.9.6) cannot import the pull path` | The hermetic scrub repoints HOME at the scratch tree, and `pip install --user` puts pyyaml under a directory derived from HOME. The pull path is 3.9-clean; the drill had stripped the box interpreter of its libraries and then blamed the subject. |
| 4 | P7 | `--from is not a checkout (no .git)` | A bundle is a cut of a checkout (`egg-export.sh:154`, refused at `cabinet-update.sh:343`), which is what §4 P7 asks for — "two egg-export.sh --bundle cuts of HEAD". The drill handed it a tar copy. |
| 5 | P7 | `LIVE INSTANCE FILE SURVIVED THE PASS`, then `expected in export but missing` | The drill cut its bundles from `$ROOT` AFTER the hatch had made it a running cabinet. The exporter refusing that is the exporter being right. |
| 6 | P7 | `the inbox reports no latest bundle after publish` | The publish had worked. `status --json` names the bundle id `sha` (cabinet-update.sh:426, :458); the drill read `latest.source_sha`, which is the manifest's key. |

Defects 1, 3, 4, 5 and 6 are read-side mistakes — the drill asking a subject for a
shape it does not have. Defect 2 is a sequencing mistake: a stage whose precondition
the previous stage destroys. None of them required a subject to change.

## The one sanctioned exception — the restart seam

The drill's P7 refuses its gate-red leg unless the installed update path honours the
restart command it drives, and it drove `CABINET_DASH_RESTART_CMD`, which nothing on
the other side read. Reconciled on the side that was wrong — the drill — with the
update path gaining the seam under its own naming law:

* `cabinet-update.sh::restart_dashboard` reads `CABINET_UPDATE_TEST_RESTART_CMD` and
  runs it INSTEAD of `cabinet_dash_restart`, under the same `exec 9>&-` fd discipline
  as the real path so nothing it starts inherits the updater's lock.
* The prefix is A5.14's: a variable that can decide a leg of the health gate is a test
  seam, and the existing guard (`test_health_gate_defaults_are_the_contract_legs`,
  test_cabinet_update.py:688-690) already requires every `CABINET_UPDATE_*_CMD` to
  carry it.

**Why a seam at all, rather than the drill supplying its own dashboard library:** a
bundle SHIPS `cabinet/scripts/lib/dashboard.sh`, so an apply would overwrite any
fixture library halfway through the very run that depends on it. The seam has to be in
the updater. This is written into the code comment so it is not re-litigated.

## Sensors, red before and green after

| Sensor | RED before | GREEN after |
|---|---|---|
| `test_cabinet_update.py::test_the_restart_seam_is_what_restarts_and_it_is_a_test_seam` | `AssertionError: the updater never ran the restart command it was handed …` + stderr `restart: no dashboard library at …/.updates/run/lib/dashboard.sh` | passes; the marker is written, the apply still rolls back on the red gate, `cabinet_update_rolled_back` is emitted and the install stays on the old sha |
| `test_drill_wiring.py::test_the_drill_and_the_updater_name_the_same_restart_seam` | `assert '${CABINET_DASH_RESTART_CMD:-}' in <cabinet-update.sh>` | passes |
| `test_drill_wiring.py::test_the_workflow_carries_the_responsibility_drill_job` | `assert 'responsibility-drill' in {...}` | passes |
| `test_drill_wiring.py::test_the_drill_job_carries_the_claims_and_update_path_suites` | same missing job | passes |
| `test_drill_wiring.py::test_the_drill_job_does_not_skip_itself_on_a_master_push` | same missing job | passes |
| `test_drill_wiring.py::test_drill_fails_without_claim` | — (an inverted arm: it MUTATES `claims.py` so nobody is ever found holding a task and requires exit 20) | passes |
| `test_drill_wiring.py::test_drill_fails_on_missing_subject` | — (deletes `session_bridge.py` and requires exit 21, NOT 20) | passes |
| `test_drill_wiring.py::test_the_drill_passes_on_the_committed_tree` | — (the third leg: two red arms with no green one is a sensor that says no to everything) | passes, asserting the STAGES ARRAY, never exit 0 alone |

The two red arms are cut with `git archive HEAD`, never the working tree, and a
checkout that cannot produce one FAILS rather than skipping.

## What this checkpoint deliberately did NOT do

* No subject behaviour changed. The only non-drill, non-test edit is the 21-line
  restart seam, which is inert unless the variable is set.
* No `framework/` line was added, so the production-line census budget is untouched.
* No locked path is in the diff (checked against `update_bundle.parse_locked_set`).
* No ledger row: phase-1's status stays `in-flight` (A0.8), and no unit but U7 carries
  a CG row.
