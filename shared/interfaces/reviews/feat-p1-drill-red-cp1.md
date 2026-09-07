# Checkpoint review — feat/p1-drill-red cp1

Reviewed-Scope-Digest: a1748e5a0e75f51d61342b9764eb91d75a8cb7d3b9fe494eb558f6f3e93b8d67

Unit U4r of the phase-1 contract (§4 + A4.1–A4.9, A0.2–A0.4, A2.2 drill arm,
A2.7/A4.8 P2b): the acceptance drill, AUTHORED RED. Three new files, nothing
modified, no locked path touched.

| Path | What it is |
|---|---|
| `cabinet/scripts/drills/one-responsibility.sh` | the drill: hatch, seed, P1 tap, P2 claim race, P2b assignment fallback, P3 kill, P4 resume-by-expiry, P2h locked-hook leg, P5 no-re-briefing, P6 receipts, P7 update + rollback, hermeticity |
| `cabinet/scripts/drills/lib/worker.py` | the scripted worker: pull / work / complete, calling exactly what the locked hook calls |
| `cabinet/scripts/drills/lib/stub_dashboard.py` | the health-contract stand-in P7's gate needs (A4.7 + A5.5) |

## What was checked, and how

* **The sensor is red, and red for the right reason.** Three arms run this
  session against a fresh clone of master `97164616`: unstubbed ⇒ exit 10 at
  P1 naming `No module named 'framework.outcomes'`; with P1 stubbed through the
  `--tree` seam ⇒ exit 20 at P2 reporting `8 got the item, 0 work_item_started
  events landed`; with the pull path removed from the staged tree ⇒ exit 21,
  the distinct "the measurement was impossible" code A4.1 requires. Exit 20 and
  exit 21 are therefore proved to be different verdicts, not the same failure
  wearing two numbers.
* **The stub server was proved in both directions.** A stale stamp survives an
  apply that never restarted (the gate-red arm), a real restart picks the new
  stamp up, and a restart onto a port held by a foreign listener returns 1
  rather than reporting success. The first cut of that helper returned 0 on a
  failed restart because it waited on its own leftover state file — a disabled
  sensor inside the sensor — and now waits on a real HTTP answer carrying the
  current stamp.
* **The scratch hatch is a fresh hatch, and that was NOT free.** The committed
  tree ships this deployment's own `instance/config/outcomes.yml`, pinned to
  its deployment id. Staging `git archive HEAD` and hatching on top of it made
  the compiler skip the whole file, so the first stubbed run reported `0 got
  the item` — every stage after the tap would have measured nothing while
  reporting cleanly. The drill now applies the export manifest's own
  `delete instance/...` lines (derived, never hand-listed) and refuses to run
  if that list comes back empty.
* **Hermeticity is asserted, not assumed.** `HOME`, `CABINET_ROOT`,
  `CABINET_EVENT_LOG_DIR` and `CABINET_ID` are pinned; every other `CABINET_*`
  plus `PYTHONPATH`, `DATABASE_URL`, `ORG_RUNTIME_DB` and `REDIS_*` are
  scrubbed; file lists of `$HOME` and of the repo are compared before and
  after. The one path outside the root is the locked hook's own `/tmp`
  debounce sentinel, which is why the drill uses a `drill-<8hex>` slug that
  cannot collide with a live officer's and removes its own on exit.
* **No safety switch is in the write set.** The preserve-set canary is
  `shared/interfaces/captain-rules-index.yaml`, deliberately a non-switch
  member of the same shipped-empty class rather than the veto file the
  amendment names as an example.
* **Statics.** `bash -n` and `shellcheck --severity=warning` clean; all 14
  embedded python blocks compile; both library modules parse and are written
  3.9-clean.

## Residuals, stated

* P3–P7 cannot execute end to end until the claim, receipts and update units
  land; they are reviewed by reading and by their own static checks only.
* The A4.1 mutated-`claim()` red arm needs a claims module to mutate, so it is
  demonstrated here in the equivalent shape (8 winners, 0 started events) and
  is U4g's test to drive through the same `--tree` seam.
* `CABINET_DASH_RESTART_CMD` is a seam this drill names for the update path;
  the contract is silent on how a restart is injected, and U5 must honour it.

---

# Checkpoint review — feat/p1-drill-red cp2 (2026-09-07, second builder)

Re-verified against `origin/master c479b5f5` (cp1's evidence was taken at
`97164616`; PR #368 landed in between). Two contract deviations found by
reading the P7 block against §5 and the amendments, and fixed here.

| Finding | Why it is a defect | Fix |
|---|---|---|
| `apply --from cli` | `--from` already means a SOURCE DIRECTORY on the sibling verb (`publish --from <clone> --to <install>`, A5.10), and `cli` is a door kind outside the sanctioned `terminal \| web \| chat` set (A0.1) — the drill would have pinned the update unit to both mistakes, and the kind would have landed in the ledger on `cabinet_update_applied`. | `apply --door terminal`, matching P1's own tap and A0.1's vocabulary. |
| `--skip-rebuild` hard-coded | A4.7 says P7 runs the FULL apply (stage build, restart, health gate) and that the skip flags exist only for the CI variant, which is labelled THIN. The drill offered only the THIN variant, so the staged-build-and-swap of A5.6 was unreachable — a leg relabelled as covered. | `--with-rebuild` runs the full apply; the default stays node-free and still reports THIN, and the full variant reports PASS for that step instead. |

Everything cp1 recorded was re-proved on the current tree rather than cited:
three red arms (exit 10 / 20 / 21), the four-arm stub-server proof, the
manifest-scrub degenerate guard (exit 64 when the manifest names no instance
path), and a new hermeticity arm — the whole stubbed run under a poisoned
`DATABASE_URL` / `ORG_RUNTIME_DB` / `REDIS_*` / `CABINET_*` / `PYTHONPATH`
environment returns the identical verdict, which is what A4.3 is for.

Battery run on this tree and on a pristine `c479b5f5` clone; per-harness and
per-test verdict lines diffed rather than counted. The two rows that differed
between the runs (`test_cog1_outbox_capture.py::…::test_baselines_hold_the_bound`
on the pristine run, `test_killswitch_test_fence.py::…::test_emergency_stop_writers_cannot_reach_an_unfenced_control_plane`
on this one) both PASS when re-run on BOTH trees: the first is a wall-clock p95
bound, the second a canary `redis-server` the harness could not reach. Neither
is attributable to this branch, which adds no collectable test.
