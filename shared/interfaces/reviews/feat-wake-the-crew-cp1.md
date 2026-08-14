# feat/wake-the-crew — checkpoint 1 review

Branch `feat/wake-the-crew` off `origin/master` 268ccdd0. FW-019 artifact for a
change over 300 lines. Reviewed against the class-11 four questions plus an
adversarial pass on the one genuinely dangerous surface: a web page that
manipulates launchd on the operator's Mac.

## What landed

| area | file | why |
|---|---|---|
| the reading | `cabinet/dashboard/src/lib/crew.ts` | pure state machine — six states where there were two |
| the second signal | `cabinet/dashboard/src/lib/crew-state.ts` | roster ∪ store ∪ installed-LaunchAgent, taken honestly |
| the hire record | `cabinet/dashboard/src/lib/crew-roster.ts` | `roster.yml` + lane contexts — the words the operator's answers produced |
| the name | `cabinet/dashboard/src/lib/officer-title.ts` | framework title → roster title → LANE name + job word → Title Case |
| the allowlist | `cabinet/dashboard/src/lib/crew-ops.ts` | two argv shapes, `execFile`, no shell |
| the actions | `cabinet/dashboard/src/actions/crew.ts` | four refusals before a single command runs |
| the poll | `cabinet/dashboard/src/app/api/crew/route.ts` | read-only, `requireDashboardAuth` |
| the posture | `cabinet/dashboard/src/lib/posture-status.ts` | one resolver, shared with `/posture` |
| the card | `cabinet/dashboard/src/components/consumer/card-cabinet.tsx` | calm states, the fold, the alarm that stays |
| the control | `cabinet/dashboard/src/components/consumer/crew-wake.tsx` | consent → progress → measured outcome → undo |
| the stamp | `cabinet/scripts/start-officer-mac.sh` | ISO-8601, matching the other three writers |

## Class-11: the four cheap questions, per sensor

**1. Does the arm FAIL against pre-change code, in both directions?**

- `test_heartbeat_stamp_format.py` — verified red by restoring `date -u +%s` in
  `start-officer-mac.sh` (2 failed / 4 passed), green on restore (6 passed).
  Run in this session, both directions, no cache to purge (pytest, fresh
  interpreter).
- `crew.test.ts` — the never-started arm cannot exist against pre-change code:
  the old `card-cabinet.tsx` had no such state and rendered `🔴 … is offline`
  for it. The *inverse* arm is the load-bearing one and is asserted explicitly:
  `install: installed` + no heartbeat still yields `quiet`, and a STALE
  heartbeat yields `quiet` whatever the install says. A fix that softened the
  died case would red those two.
- `crew-ops.test.ts` — the hostile-slug arm was RED when written
  (`--force` passed `^[a-z0-9-]+$`); the fix is the leading character class plus
  a reserved word. See "adversarial" below.

**2. What does the check do at the degenerate end — zero, empty, absent, null?**

| input | answer | asserted in |
|---|---|---|
| LaunchAgents dir unreadable | `unknown` **not** `not-awake-yet` | `crew.test.ts`, `crew-state.test.ts` |
| no LaunchAgents dir at all (fresh Mac) | measured `absent` | `crew-state.test.ts` |
| non-darwin platform | `unknown` with the reason | `crew-state.test.ts` |
| store did not answer | zero rows + `unreadable`, and `neverWoken:false` | `crew-state.test.ts` |
| roster missing / malformed YAML | zero hires, no crash | `crew-roster.test.ts` |
| contexts dir missing | no lane names, no crash | `crew-roster.test.ts` |
| empty roster | wake refuses, runs nothing | `crew.test.ts`, `crew.test.ts` (`wakeableSlugs([])`) |
| roster of only consultants | wake refuses, runs nothing | `actions/crew.test.ts` |
| empty / whitespace configured title | falls through, never renders blank | `officer-title.test.ts` |
| unparseable stop time | conservative arm (`stop-failed`), never a NaN comparison | `crew-state.test.ts` |
| unreadable heartbeat under a stop marker | `unknown`, not `resting` | `crew.test.ts` |
| script missing on disk | refusal, nothing executed | `crew-ops.test.ts` |
| empty stdout/stderr | `lastLine('') === ''` | `crew-ops.test.ts` |

**3. What does the test environment guarantee that production does not?**

The install reading is filesystem-real in `crew-state.test.ts` (a temp
LaunchAgents dir), because the thing that would actually break it is a path or
an errno and neither survives being stubbed. Its darwin-only arms are
`it.skip`ped off-darwin **and** a complementary arm asserts the non-darwin
answer, so the file cannot go green by skipping everything on the CI runner —
the off-darwin path is exactly the one that must return `unknown`.

`crew-ops.test.ts` mocks `execFile` (running `deploy-mac.sh` for real in a unit
test would mutate launchd), and that mock is the reason the last describe
exists: it asserts the exact program, argv, cwd and the ABSENCE of a `shell`
option, so the file is not just a wall of refusals.

The real launchd mechanics are proven separately, out of band (below).

**4. Is the sensor wired to the LIVE artifact?**

- `crew.ts` is imported by `crew-state.ts`, which is imported by
  `card-cabinet.tsx` (the home card) and `/api/crew` (the poll). No twin.
- `crew-ops.ts` is the only module in the app importing `node:child_process` for
  the fleet; `actions/crew.ts` is its only caller.
- `test_heartbeat_stamp_format.py` discovers its targets by `git grep` over the
  committed tree rather than an enumerated list, so a writer added tomorrow is
  in scope without editing the test. It also carries
  `test_there_are_writers_to_check`, because a grep that matched nothing would
  make every other arm vacuously true.

## Adversarial pass

**Can the wake endpoint be reached unauthenticated?** No. `wakeCrew`/`sleepCrew`
call `requireDashboardAuth()` as the first statement of `preflight()`, and
`actions/crew.test.ts` drives the real exported actions and asserts BOTH that
the result is `Unauthorized` and that `runCrewOp` and the store writes were
never called — the effect, not the flag. `/api/crew` is gated by the same
shared predicate.

**With onboarding incomplete?** No — refused with a plain sentence, and the arm
is asserted on `sleepCrew` as well as `wakeCrew`, because a refusal that guards
one door is not one.

**Can the allowlist be widened by input?** The table has two entries and the
membership check is `Object.prototype.hasOwnProperty` — `OPS['toString']` and
`OPS['__proto__']` both resolve to something truthy through the prototype
chain, so the obvious `if (!OPS[op])` guard would have waved them past and then
crashed on `entry.args`; that is a refusal that never fires, which is the
disabled-sensor shape this program keeps finding. Slugs come from `roster.yml`
and are re-validated at the door. **The first version of that pattern was
wrong**, and its own test caught it: `^[a-z0-9-]+$` accepts `--force`, `--all`
and `-officer`, so the one interpolated field could have widened the allowlist
into the very operations it excludes. Now `^[a-z0-9][a-z0-9-]{0,63}$` plus a
reserved-word set containing `all` — `deploy-mac.sh`'s wildcard for both legs,
where `--stop all` boots out every installed `com.cabinet.*` LaunchAgent, the
dashboard serving the page included. Sixteen hostile ids are asserted refused
with `execFile` never called.

**Does sleep really tear down?** Proven by absence, not by an exit code:
`launchctl print gui/$(id -u)/<label>` fails, `launchctl list` matches zero
rows, and `pgrep -fl` finds no officer process. The plist file staying on disk
is `deploy-mac.sh --stop`'s documented behaviour (redeploy restarts it) and is
why the expectation marker, not the file, is what tells the card the quiet is
deliberate.

**Can the flow claim a stop it did not make?** No: only officers whose command
actually succeeded get `expected:active`; a partial wake says "1 of 2" and
names the rest; a total failure says nothing changed. And the sleep's own
screenshot exposed the inverse lie — a `SETEX 900` heartbeat outliving a
successful stop, so the card read `🟢 … is planning your first week` above
`Your crew is asleep`. Fixed by recording WHEN the stop was requested and
comparing, with the unknowable case taking the alarm rather than the
reassurance.

## Out-of-band proof (the mechanics the unit tests mock)

Real `deploy-mac.sh` against a scratch checkout, a scratch `HOME`, and a unique
label `com.cabinet.officer.wakeproof`:

1. wake → `deployed: com.cabinet.officer.wakeproof`, plist installed in the
   scratch LaunchAgents dir, `launchctl print` shows `state = running`, pid
   2362, tmux session created, the officer program ran.
2. wake again → `deployed:` again, exit 0, **no** `Bootstrap failed: 5`,
   exactly one job with that label, a second run recorded. Idempotent.
3. sleep → `stopped: …`; job gone from launchd, zero rows in `launchctl list`,
   no process; plist still on disk.
4. sleep again → exit 0. Idempotent.
5. The machine's 52 live `com.cabinet.*` jobs were byte-identical before and
   after (`diff` of two `launchctl list` snapshots), nothing was written to the
   real `~/Library/LaunchAgents`, and the tmux session and scratch tree were
   removed.

Plus a full browser drive of the shipping UI (eight frames, in
`docs/plans/wake-the-crew-2026-08-14/`) whose last step ASSERTS the slept card
says `Asleep` and does not claim the officer is working.

## Gates

`npx vitest run` in `cabinet/dashboard` — 3622 passed, 1 skipped, 174 files.
`npx tsc --noEmit` — clean. `check-layer-separation.sh` — `new=0` (baseline 24,
allowlist 19, current 43, unchanged before and after). `python3.12 -m pytest
cabinet/scripts/tests -q` — run for the `start-officer-mac.sh` change. Guarded
tokens grepped across every new file and the new doc — none. Exact-path adds
only.

## Known scope, stated rather than implied

The wake starts the always-on officers. It deliberately does not run the rest
of hatch's move-in (`generate-plists.py` + loading the generated fleet): that
would bootstrap `com.cabinet.dashboard` against the dashboard already serving
the page, and it would park any `com.cabinet.*` job outside the manifest.
Nothing in the flow's copy claims otherwise, and the Telegram step-4 line was
written to stay true either way.
