# feat/runtime-stays-up — checkpoint 1 review

Unit U8, "the runtime stays up". Two P1 defects measured on the Captain's
installed Cabinet on 2026-09-21, eleven days after the first real update
applied to it. Base commit 84e03225, merged forward onto origin/master
24971cee (PR #384, the sov6 expiry time-bomb).

## What was wrong

1. **The fleet load was never durable.** `hatch.sh`'s `do_movein_load` walked
   `cabinet/launchd/generated/*.plist` and bootstrapped each file where it lay.
   launchd re-reads agents at login from `~/Library/LaunchAgents` and from
   nowhere else, so every one of those jobs existed only until the next
   restart. One restart (~2026-08-29) cleared all fifty scheduled jobs; the
   fleet was dark until an officer diagnosed it on 09-15, and it could not be
   re-bootstrapped from launchd's own Background manager. `deploy-mac.sh --all`
   has always been the durable verb — it renders from `services.yml` plus the
   roster, writes `~/Library/LaunchAgents` and reconciles launchd to exactly
   that set. It restored 51 jobs on 09-21.

2. **An apply could leave the door unsupervised, silently.** When no launchd
   job answered, `cabinet_dash_restart` started a detached dashboard. That
   orphan dies with its terminal and does not come back after a restart. The
   dashboard the 09-10 apply started was dead by 09-21; the web door — the
   Captain's only no-terminal door — was gone and `status` said nothing about
   it across eleven days of being asked.

## What changed

| Area | Change |
|---|---|
| `cabinet/scripts/lib/dashboard.sh` | `cabinet_launchd_install` (install into `~/Library/LaunchAgents`, bootstrap the COPY, bootout-first, reason in `CABINET_LAUNCHD_INSTALL_ERROR`); `cabinet_launchd_state` (running/loaded/not-loaded/unknown); `cabinet_dash_record_door`; `cabinet_dash_restart` now installs and supervises before falling back |
| `cabinet/scripts/hatch.sh` | `do_movein_load` runs `deploy-mac.sh --all` and then VERIFIES a `com.cabinet.*.plist` landed in `~/Library/LaunchAgents`; the paste-runnable hint names the durable verb |
| `cabinet/scripts/hatch-lib/errands.sh` | the printed errand hands the operator `deploy-mac.sh --all`, not the non-durable loop |
| `cabinet/scripts/cabinet-update.sh` | `restart_dashboard` carries the door verdict out of the restart subshell; the applied and rolled-back state writes carry `door_supervised` / `door_reason`; `cmd_status` reads the door's launchd state AT READ TIME and reports `door_label`, `door_launchd`, `door_supervised`, `door_reason` in json and in words |
| `framework/frontdoor/run_briefing.py` | one arm: a recorded `door_supervised: false` speaks below an apply in flight and above every "open the home page" sentence |
| docs | `docs/runbooks/cabinet-update.md` (new "Supervised, or it says it is not" section, the json shape, the surface order), `cabinet/docs/mac-mini-deploy-runbook.md`, and three runbooks that shipped the same non-durable loop as copy-paste |
| census | `framework_production_noncomment_lines` 66839 -> 66842, +3 measured, dated paragraph |

## Where the judgment went

**A separate `lib/launchd.sh` was refused.** The installer lives in
`lib/dashboard.sh`, next to `CABINET_DASH_LABEL` — already a launchd fact
stated there. A new library would be one more file the updater's run-copy
(`reexec_detached`), the test fixtures and the drill each have to remember to
carry, and a missing one degrades silently. Zero new wiring beats a tidier
name.

**The door is TWO facts, deliberately not one.** `door_supervised` is read
live from launchd when `status` runs — that is what makes a dead orphan
visible the next time anything asks. `door_reason` is what the last restart
recorded. Collapsing them would have reproduced the defect: a field written at
apply time says nothing about a process that died a week later.

**The briefing does not subprocess.** It reads the updater's own state
document, which `_update_notice` already has open — the same reader, not a new
channel (A5.17.6). A briefing pass may never be able to hang on a subprocess,
which is why the live read belongs to `status` and not here.

**A5.19 is untouched.** The rollback still restarts only what was listening
before the run; the supervised path is reached only through
`cabinet_dash_restart`, after that decision has been made.

**The acceptance drill stays hermetic.** `CABINET_UPDATE_TEST_RESTART_CMD`
returns before any launchd work, and an arm pins that ordering against the
code (comments stripped) rather than the prose.

## Sensors, each RED on the base bytes first

| Arm | Red on base |
|---|---|
| ratchet: no shipped shell bootstraps a plist out of `launchd/generated/` (allowlist EMPTY) | 3 findings: `hatch.sh:355`, `hatch.sh:903`, `hatch-lib/errands.sh:100` |
| move-in runs `deploy-mac.sh --all` | the old loop, quoted in the failure |
| move-in verifies `~/Library/LaunchAgents` | `LaunchAgents` absent from the body |
| paste-runnable hints name the durable verb | `hatch.sh:355` quoted |
| unsupervised door is put under supervision | the plist was never installed; launchctl saw only `print` |
| launchd refuses -> fallback + reason | no `door is UNSUPERVISED` line existed |
| no rendered plist is a reason, not a crash | same |
| `status --json` door fields (3 arms) | `KeyError: door_supervised` |
| human `status` prints the door | four lines, none about the door |
| briefing says the home page is not served (2 arms) | `Updated to bbbbbbbb: 4 changes` / `An update is ready to take ... tap Apply` |

Inverse and degenerate arms that pass on base by construction, and are labelled
as such: a supervised door is still kickstarted and not reinstalled; `status`
writes nothing while reporting; a supervised door says nothing in the briefing;
an absent `door_supervised` is not a down door; the restart seam precedes the
real path.

## One sensor was measuring prose

`test_cabinet_update.py::test_no_vendor_noun_and_no_git_in_the_installed_root`
asserted `" launchctl " not in body` over the file's raw text after the status
marker. The comment explaining why a door probe goes THROUGH the library —
which has to name the tool it is not calling — tripped the guard against
calling it. The arm now strips full-line comments and asserts over code, which
is the control it names. Same defect class as the seam arm, found the same way.

## Residuals

* The home card (`cabinet/dashboard/`) does not surface the door yet; the
  fields are on `status --json` for it to read. Deliberately out of this unit —
  the briefing and the terminal are the two surfaces that were silent.
* `deploy-mac.sh::install_plist_file` is a third copy of install-then-bootstrap
  and should fold into `cabinet_launchd_install`. Not folded here: it carries a
  per-service rollback this function does not, and a deploy regression is a
  worse trade than a duplicated 20 lines.
