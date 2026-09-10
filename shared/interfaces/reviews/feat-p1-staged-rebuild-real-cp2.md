# Checkpoint review — `feat/p1-staged-rebuild-real` cp2 (FW-019)

Reviewed-Scope-Digest: c92d226ee6df1687d9dedd147d9f5d094257b660cb4a64c1f400a252de7e8abc

**Scope:** contract amendments A5.18 and A5.19, ruled 2026-09-10 after the first
real apply on the Captain's installed Cabinet. Nine files: the updater, the
dashboard library, the acceptance drill and its health stub, both their test
files, the drill's CI job, the runbook, and the census contract's dated
paragraph.

## The two defects being closed, and the one that hid them

The apply passed the locked-set check, staged the tree, and died inside the
staged build:

```
Symlink [project]/node_modules is invalid, it points out of the filesystem root
```

`cabinet-update.sh` reused the install's dependencies by symlinking them into
the stage. The bundler treats the staged project directory as the root of the
world and refuses a link that leaves it — which is a reasonable thing for a
bundler to do and is not specific to one of them. **A5.18.**

The rollback that followed was correct in every byte. On the way out it started
an unsupervised dashboard on a door where nothing had been listening before the
apply began. The operator asked for an update, did not get one, and was left
running a process he had not been running. **A5.19.**

Neither was caught because the acceptance drill's P7 passed `--skip-rebuild` on
every apply — line 1316 on `ae687861`, with the flag that cleared it opt-in and
passed by no gate. The staged build was the one leg of the update path that
nothing in this repository had ever walked, and the first person to walk it was
the Captain, on his own machine.

## What changed, and why each choice

| Choice | Reason |
|---|---|
| Dependencies materialise as a **hardlink tree inside the stage** (`cabinet_dash_link_modules`) | every path stays inside the project, so no tool has to follow a rope over the wall; same inodes, so it still costs no disk |
| `pax -rwl` → `rsync -a --link-dest` → `cp -R`, in that order, the last one LOUD | this ships to boxes this org does not own; a copy is correct and expensive, and an expensive fallback that says nothing is how a disk fills up quietly |
| One mechanism, in the shipped library, called by BOTH the updater and the drill | a drill with a private copy proves the copy works, which is not the claim. Two arms pin it structurally |
| Dependency staging moved AHEAD of the `BUILD_CMD` seam (`stage_dependencies`) | the seam is called BUILD_CMD and stands in for the BUILD. With the link on the far side of that branch, the one property worth testing was the one property no arm could reach — which is exactly how the symlink survived to meet an operator |
| The drill's bundle now changes a **dashboard** file as well as a framework one | the rebuild is conditional on the plan touching `cabinet/dashboard/`, so dropping `--skip-rebuild` from a framework-only bundle would have changed nothing and the drill would have gone on reporting a build it never ran |
| The health stub reads `build_commit` out of `.next/required-server-files.json` | a stub answering it from a file the drill wrote is green whether or not a build ever ran. The gate now reads the artifact the build produced |
| `--with-rebuild` becomes a DEMAND (reds when the box cannot) rather than a variant | the default is now REAL wherever REAL is possible; the flag's remaining job is to refuse a silent downgrade |
| The CI job installs node + `npm ci` and asserts `p7_rebuild == "REAL"` | THIN is an honest answer on a box with no toolchain and a lie on a runner that just installed one. Without the assertion this gate could switch itself off by regressing to THIN |
| The door is probed **before the first write**, and the reading is used only on the way out | "what was running before" is answerable only before this script has moved anything. An arm reads the log in ORDER rather than trusting the source |
| A rollback restarts only on `mine`; `other`, `down` and `unknown` all decline | `unknown` (no dashboard library) is treated as nothing-was-running because inventing a process is the failure being removed and declining to start one costs the operator a tap |
| A SUCCESSFUL apply still always restarts | the health gate's whole job is to read the new build back off a running process; an update that landed and served nothing is an update nobody can check |
| The drill's update legs get a second throwaway HOME under `$SCRATCH` | measured: with telemetry off and every XDG path redirected, a real build still creates `~/Library/Preferences/<tool>-nodejs` on macOS. `$SCRATCH` is the run's own root, so the hermeticity claim is unchanged and the operator's HOME is exactly as far away as before |

## Sensors, each RED on `ae687861` production bytes

| Arm | RED on ae687861 | GREEN after |
|---|---|---|
| a real staged build with the symlink mechanism | `Symlink [project]/node_modules is invalid, it points out of the filesystem root` (reproduced on this box, Next 16.2.10 / Turbopack) | the hardlink tree builds; `/api/health` reports the bundle sha as `build_commit` |
| `test_the_stage_gets_a_hardlink_tree_and_never_a_symlinked_node_modules` | "the stage has no dependency tree of its own ({'exists': False, ...})" | rc 0 |
| `test_dropping_the_stage_leaves_the_installs_dependency_tree_intact` | "while the stage existed the install's dependency file had None link(s)" | rc 0 |
| `test_a_rollback_does_not_leave_a_dashboard_on_a_door_that_was_empty` | "the rollback started a dashboard on a door where nothing had been listening" | rc 0 |
| `test_a_rollback_puts_back_the_dashboard_it_found` | `'so it is put back' not in <log>` | rc 0 |
| `test_the_door_is_read_before_the_first_write` | "the updater never recorded what was on the door before it began" | rc 0 |
| `test_the_dependency_mechanism_is_the_shipped_one` | "the mechanism is not declared once" | rc 0 |
| `test_the_drill_does_not_hardcode_a_skipped_rebuild` | "the drill has no real-rebuild path at all" | rc 0 |
| `test_the_drill_job_installs_the_dependencies_its_real_rebuild_needs` | "the responsibility-drill job installs no node" | rc 0 |
| `test_the_drill_links_dependencies_through_the_shipped_mechanism` | "the mechanism is not in the shipped library" | rc 0 |
| `test_the_stub_reads_its_build_stamp_off_the_build` | "the stub does not read the build stamp off the built artifact" | rc 0 |
| the FULL drill in a clone that has run `npm ci` | exit 0 with `THIN [P7] rebuild step skipped` and **no `p7_rebuild` field at all** | exit 0, `p7_rebuild: REAL`, P7 reads the bundle sha off the artifact |

## One existing arm changed, and why that is the amendment working

`test_the_restarted_dashboard_does_not_inherit_the_updater_lock` drove a
rollback on a box with an empty door. Under A5.19 that restarts nothing, so the
arm would have measured a restart that never happened. It now starts the
drill's health stub on a real port first — the box IS serving — and APPENDS its
stand-in `cabinet_dash_restart` to the real library instead of replacing the
file, because the door probe needs the real `cabinet_dash_state` and a fixture
that overrides more than the one function it stands in for is a fixture testing
itself. The lock property it exists for is untouched.

## Residual, written down rather than left to be re-derived

* **Two real builds per drill run.** P7's gate-red leg and its gate-green leg
  both rebuild (~1 min each on the reference box), which is why the job's guard
  went 20 → 30 minutes. The gate-red build is not waste: it is the only place
  the rollback path is exercised after a build that actually produced output.
* **`cp -R` is untested end to end.** The fallback is reached only on a box with
  neither `pax` nor `rsync`, which is neither this one nor the CI runner. It is
  covered structurally (the mechanism arm requires the branch to exist) and it
  says what it is doing in the log; a box that takes it will say so.
* **The hardlink tree shares inodes with the install.** Nothing in a build
  writes through them today — the bundler's output goes to `.next` and its cache
  to new files under the stage — and the removal arm reads the link count from
  inside the stage. A tool that rewrote a dependency file IN PLACE would reach
  the install. That is the price of not copying a gigabyte per update, and it is
  the reason the sampled-content assertion is there.
