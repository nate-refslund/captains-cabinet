# feat/p1-drill-red — checkpoint 3: a stage that nobody ATTENDED is a stage that failed

Reviewer verdict on cp2 (05fd38b6) was REJECT on one blocking finding and two
must-fixes. This checkpoint closes all three plus the four notes. Nothing about
the unit's scope changed: no subject unit is built, no CI job is wired, no
`test_drill_wiring.py` (both U4g, per §8 L6 / A4.9).

## The blocking finding, restated in one line

cp2 closed the channel that carries a stage's VERDICT and left open the channel
that carries its PARTICIPATION. P2 counted winners and started events; a holder
that died before it reached the pull path was silently a well-behaved loser, and
the eight background workers' exit statuses were thrown away by a bare `wait`.
Seven dead holders, one winner and one started event scored `{"code": 0}` — the
drill would print `PASS [P2] 8 holders, 1 claim` on a crowd of one. P2h had the
same shape twice: an empty hook output was `continue`d (silence is what a LOSER
looks like) and `wait "$HA" … || true` discarded both legs' status; on the
holder's own re-tick, silence is what the stage PASSES on, so a leg that crashed
would have been the proof.

## What changed

- **P2 collects every holder's exit status, one `wait` at a time**, and the
  assertion block refuses the stage unless all eight results parse and carry no
  `error` / `module_error` / `ok != true` and each exited 0. The
  all-unimportable ⇒ 21 branch is kept; a NEW all-dead branch also gives 21
  ("not one of the 8 holders reached the pull path"); a PARTIAL failure is 20
  and names which holders were absent and why.
- **P2h asserts both hook legs exited 0** before reading their silence, and the
  holder's own re-tick asserts its own status first — that leg passes on
  silence, so an unrun leg is the strongest possible false proof.
- **P7 counts became per-leg DELTAS.** Three legs share one install and one
  ledger; `event_count … cabinet_update_applied` then `[ "$APPLIED" -gt 0 ]`
  is answered by an earlier leg's row, and `ls .updates/snapshots | wc -l` is
  cumulative where the contract says "one snapshot". Each count (and the
  snapshot count, through a new fail-closed `dir_count` helper) is now taken
  immediately before its leg and compared after it: rolled-back, applied,
  snapshot and refused must each be exactly 1 FOR THAT LEG.
- **A2.9** — `CABINET_CLAIM_LEASE_FLOOR_SECONDS=1` is exported beside the other
  pins, with the amendment's reason: production keeps `MIN_LEASE_SECONDS = 60`
  and this is the only sub-floor path, so without it P3's 3 s lease is clamped
  to 60 and P4's bounded wait can never see an expiry.
- **A5.14** — P7 REFUSES to run its gate-red leg unless the installed update
  path actually reads `CABINET_DASH_RESTART_CMD`. Measured against
  `origin/feat/p1-update-path`: that updater restarts through
  `cabinet_dash_restart()` in `cabinet/scripts/lib/dashboard.sh` and reads no
  restart-command variable at all, and A5.14 renames its two health-gate
  command seams to `CABINET_UPDATE_TEST_*`. A drill driving a seam nothing
  reads would watch the dashboard restart normally and report the whole
  rollback arm against a healthy server.
- **P4's resume argv is an array**, and the forbidden-token scan reads the same
  array one element per line, so a `--root` with a space cannot word-split the
  stage into failing for the wrong reason.
- **P3 names its known race** in the header, and when nothing holds the task the
  assertion reads the killed holder's own recorded `expires_at`: an expiry that
  beat the assertion is reported AS that (still a failure — a stage that could
  not measure what it names has not measured it) instead of as a claim-path
  defect.
- **The `set -m` job-control notice is explained** beside the line that causes
  it, not suppressed: suppressing it would mean discarding the drill's own
  stderr, which is the failure this whole unit exists to be the opposite of.

## Sensors — RED before, GREEN after, controls open

Every sensor drives the SHIPPED bytes: the P2 / P2h / P3 assertion blocks and
the whole P7 body are lifted verbatim out of each version of the file by an
awk/sed range, and the two end-to-end arms run the real drill through its
documented `--tree` seam.

| sensor | before | after |
|---|---|---|
| P2 block, 7 module-error holders + 1 winner + 1 started event | `code 0` (PASS) | `code 20`, names the 7 |
| P2 block, 7 crashed holders (no JSON at all) + 1 winner + 1 event | `code 0` (PASS) | `code 20` |
| P2 block, 1 winner + 7 honest losers + 1 event — CONTROL | `code 0` | `code 0` |
| P2 block, 8 module-error holders (A4.1 arm) | `code 21` | `code 21` |
| P2 block, 8 winners + 0 events (contracted red 4b) | `code 20` | `code 20` |
| P2 block, all 8 crashed | `code 20` (wrong reason) | `code 21` |
| END TO END: real drill, `--tree` where 7 holders die and the 8th claims and emits one started event | `PASS [P2] 8 holders, 1 claim`, exit 21 at P2b | `FAIL [P2]`, exit 20 |
| END TO END CONTROL: `--tree` with a real flock, 8 live holders, 1 winner, 1 event | P2 pass | P2 pass |
| P2h block, leg a crashed (exit 1, silent), leg b won | `code 0` (PASS) | `code 20` |
| P2h block, both legs ran, one won — CONTROL | `code 0` | `code 0` |
| P2h re-tick block, the holder's own tick crashed | `code 0` (PASS) | `code 20` |
| P2h re-tick block, the tick ran and injected nothing — CONTROL | `code 0` | `code 0` |
| P7 body vs a scripted updater: leg (b) emits no applied event, an earlier leg did | `PASS [P7]` | `FAIL [P7]` delta 0 of 1 |
| P7 body: leg (b) keeps no snapshot, an earlier leg did | `PASS [P7]` | `FAIL [P7]` delta 0 of 1 |
| P7 body: leg (c) records no refusal, an earlier leg did | `PASS [P7]` | `FAIL [P7]` delta 0 of 1 |
| P7 body: leg (a) records no rollback, an earlier leg did | `PASS [P7]` | `FAIL [P7]` delta 0 of 1 |
| P7 body, every leg honest — CONTROL | `PASS [P7]` | `PASS [P7]` |
| A2.9: real drill, `--tree` whose pull path dumps its environment | floor absent from all 8 pull-path environments | `CABINET_CLAIM_LEASE_FLOOR_SECONDS=1` in all 8 |

Two of the notes are DIAGNOSIS sensors, and are reported as such rather than
dressed up as red-to-green: with the seam renamed out of the updater, and with
`live_claim` empty because the lease already expired, BOTH versions fail — the
changed one names the actual cause where the old one named a plausible wrong
one. The argv note is a plain measurement: the old shape splits
`/tmp/a root with spaces` into five arguments, the new one passes one.

## Contracted red arms, unchanged (the unit is still authored RED)

| arm | exit |
|---|---|
| unstubbed, committed tree (§4 Inv.4a) | 10 at P1, `No module named 'framework.outcomes'` |
| P1 stubbed through `--tree` (§4 Inv.4b) | 20 at P2, 8 got the item, 0 started events |
| the pull path's module absent (A4.1) | 21, distinct from 20 |
| export manifest with every `delete instance/` line stripped | 64 at hatch |
| hostile `DATABASE_URL` / `ORG_RUNTIME_DB` / `REDIS_*` / `CABINET_*` / `PYTHONPATH` / `OFFICER_NAME` (A4.3) | 20, normalized stderr and verdict IDENTICAL to the clean run, zero postgres/redis lines, nothing written to the repo |

## Battery

`framework/` 8269 passed / 31 skipped (rc 0) · `cabinet/scripts/tests` as four
foreground chunks over an exhaustive round-robin split of all 226 `test_*.py`
(union 5367 passed / 34 skipped / 1 failed — the documented pre-existing
`test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`)
· task_adapters 56 passed · mcp 95 passed · layer-separation, docs-sweep,
ledger-parity, triggers, mac-dry-run, state-persistence-preflight all rc 0 ·
hook-regression 11/19, per-harness verdict set diffed line by line against the
documented pre-existing failing set: IDENTICAL · `bash -n` and
`shellcheck --severity=warning` clean · both python modules compile and answer
`--help` under /usr/bin/python3 3.9.6 (A0.3) · locked-set intersection EMPTY.

ONE FLAKE, recorded rather than buried: the first run of chunk 4 failed
`test_killswitch_telegram_card.py::test_halt_tap_end_to_end_arms_the_switch` and
`::test_officer_hook_still_refuses_while_poller_door_deactivates`, both on
`_get_key(sandbox_redis) == ''` — the disposable redis the fixture starts on
port 26400 did not hold the key. The same command on the same tree passed on
re-run (1114 passed), the same command on a pristine `origin/master` worktree
passed, the file alone passed five times in a row, and `git grep` proves nothing
outside `cabinet/scripts/drills/` references either changed file, so no test in
that chunk can execute a byte of this diff.

## Still THIN, and why

P3–P7 end to end (unreachable by design: the drill is authored red and exits
10/20 first; `cabinet/scripts/cabinet-update.sh` does not exist yet) ·
`--with-rebuild` (no node toolchain, and unreachable for the same reason) ·
A4.1's literal mutated-tree arm (needs `framework/missions/claims.py`, U2's
file; the `--tree` seam it will use exists and is documented) · GitHub Actions
checks (billing-locked, 0 steps).
