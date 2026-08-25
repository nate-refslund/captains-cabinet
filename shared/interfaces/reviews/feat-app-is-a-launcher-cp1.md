# Checkpoint review — feat/app-is-a-launcher cp1

Reviewed-Scope-Digest: 3c70a3ac7a00238dfb34b53b4822c3f3331bdf941c28b5fb788ed21208208f8f

## What this lands, and what it is answering

Two measured failures on the Captain's Mac, one evening apart, that turn out to
be the same seam — the app knows how to CREATE a Cabinet and nothing else knows
how to GET BACK INTO one.

1. **The silent re-run.** Second double-click of `Hatch Cabinet.app` over a
   healthy install: no message, no browser, a Terminal window whose only
   content was the shell's own teardown. Root cause, established by reading the
   shipped bytes and by execution: the re-launch dialog offered exactly
   `[Check it over]` and `[Quit]` — there was **no branch that opened the
   Cabinet at all** — and the check-over branch `exec`ed `cabinet-doctor.sh`,
   which REPLACES the runner process, so the runner's sign-off and self-close
   (#352) could never run. Whatever the child printed (or didn't) was the last
   thing on screen, and the window ended on `[Process completed]`.
   Corroboration: the app's `kMDItemLastUsedDate` matches the install dir's
   mtime to the second, `.hatch-run-args` is consumed, and there is no
   `~/hatch-logs/hatch-*` for that day — i.e. the run took the doctor branch,
   which is the branch with no closing sentence.

2. **The wrong sensor.** An unrelated local Next.js dev server was listening on
   3100. Every probe in the tree asked `curl -fsS .../api/health` and read ANY
   200 as "the cabinet is up". The foreign app answered 200 with HTML, so the
   sensors said green while the real dashboard was down and nothing was
   restarting it. The health route has carried `service: 'cabinet-dashboard'`
   since the day it was written; the sensors never read it.

## Class-11 four questions (the sensor tests the control)

**Does each new arm FAIL against pre-change code?** Yes, and this was checked
rather than assumed:

| arm | against the old code |
|---|---|
| `test_no_branch_of_the_runner_exits_in_silence[doctor…]` | old runner `exec`s the doctor; nothing after it prints, last line is the stub's output → red |
| `test_the_launcher_branch_runs_its_engine_as_a_child_not_exec` | old runner contains `exec /bin/bash …` → red |
| `test_a_foreign_two_hundred_is_not_my_dashboard` | old probe is `curl -f` + exit status; a 200-with-HTML passes → red |
| `test_a_foreign_app_on_the_port_is_never_reused_as_the_cabinet` | old tail prints "already running … using that one" → red |
| detection arms | old `prefixState` has no `.cabinet` — every non-empty prefix is one bucket → red |
| `test_starting_fresh_moves_…keeps_every_byte` | no fresh path existed → red |

**The degenerate end.** Explicitly covered: an EMPTY `active-preset` is NOT a
cabinet (`test_detection_arms`); a mangled/empty/out-of-range
`CABINET_DASHBOARD_PORT` falls back rather than producing a junk URL
(parametrised); an archive name collision counts up instead of overwriting;
`cabinet_dash_pick_port` returns nothing when the whole range is taken and the
caller says so rather than guessing; `archiveInstall` refuses `/`, the home
directory and any ancestor of it, typed confirmation or not.

**What does the test environment guarantee that production does not?** The
identity arms run REAL sockets and REAL curl against three real handlers
(identity JSON, foreign 200 HTML, 404) — a shimmed curl could not have caught
the original bug, because the bug was in what curl was ASKED. The flow arms do
shim curl, and that is stated in the module docstring with the reason. The
builder/detection arms need `swiftc` and are skipped on Linux CI — the same
shape the appshell suite has always had; the CI-runnable half is the runner
behaviour, the lib, and the static wiring pins.

**Is the sensor wired to the LIVE artifact?** The notice and window-close tests
slice the SHIPPED template between explicit `# >>> … BEGIN/END` markers and run
those bytes (no copy); the silence arms run the rendered runner with stub
engines; the detection and archive arms run the BUILT stub from the bundle;
`test_the_marker_is_the_route_s_own_field` reads `route.ts` and the lib and
asserts they name the same string, so renaming the field turns the probe red
instead of blind.

## Adversarial pass

**Can "start fresh" delete anything? It must be structurally impossible.**
- `archiveInstall` uses `moveItem` and nothing else — a rename on the same
  volume; the tree is intact under the new name and the test byte-compares a
  file through the move.
- `removeItem` appears exactly ONCE in `main.swift`, inside `installRunner`, on
  the app's own handoff files. `test_starting_fresh_can_only_move_never_delete`
  pins the count, pins that it lives in that function, and greps for
  `trashItem` / `removeItemAt` / `-rf` anywhere in the stub.
- The archive destination is uniquified before the move, so it can never land
  on an existing folder.
- Home/root are refused up front (verified by execution: `HATCH_APP_SMOKE=fresh`
  with the prefix set to `$HOME` exits 1 and touches nothing).
- The typed phrase must match exactly; a wrong answer changes nothing and says
  so.

**Can the launcher run against a half-written install?** No. The predicate
needs `cabinet/scripts/hatch.sh` AND a marker only a finished hatch writes
(`instance/config/active-preset` non-empty, or `cabinet/.env`). Both are
gitignored, so neither can arrive from an unpack — a half-finished extraction
has the engine and neither marker and lands in `occupied`, which offers the
move-aside path and never the launcher. Four arms cover it (engine-only,
foreign folder, a file where the folder should be, empty marker file).

**Can the port logic take a port away from another program?** No. `other` never
starts, never stops, never serves on top: it picks a free port, appends it to
`.env`, and says so. `open-cabinet.sh` is grepped for `kill`/`pkill`/
`launchctl`/`lsof -ti` and must contain none.

**Can the `.env` write lose a secret?** The append test asserts the new bytes
start with the ORIGINAL bytes verbatim, that a password value survives, and
that the file is still 0600. A non-numeric port is refused with the file
unchanged.

**Can line 2 of the request file become an injection?** It is accepted only
when it starts with `/`, and it is only ever echoed. Arm plants
`rm -rf ~; echo pwned` and asserts neither the text nor its effect appears.

**Can a newer Cabinet be downgraded by the app's copies?** No: the app-owned
copies live at the TOP of the prefix as dotfiles and are the FALLBACK; the
runner and the opener both prefer `cabinet/scripts/…` when it exists. Pinned by
`test_the_cabinets_own_opener_wins_over_the_app_copy`.

## Known limits, stated

- No test can drive an NSAlert, so WHICH dialog appears and the window
  physically closing stay human-verified (runbook checklist). The static wiring
  tests pin that only `.cabinet` can produce an `open` request and that the
  close is gated on the same flag, by validated id, on its own window.
- `deploy-mac.sh --stop all` is a dialog-path act only. No headless mode
  reaches it, deliberately: it boots out LaunchAgents on whatever Mac the suite
  runs on, and a test must never do that.
- The identity probe proves "my dashboard answered", not "my dashboard is
  healthy". That is the honest boundary of a liveness endpoint.

## Gates run

`bash -n` + `shellcheck` clean on every changed shell source · claims-lint 0
over the appshell sources, both hatch runbooks and README · layer separation
`new=0` · `test_dashboard_identity_probe.py` · `test_appshell_build.py` ·
`test_hatch_app_feel.py` · full `cabinet/scripts/tests` · null-hatch (hatch
surfaces changed) · appshell gate (fresh egg cut + build + smoke + lint).
