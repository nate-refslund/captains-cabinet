# Checkpoint review — fix/hatch-never-strands-the-operator (cp1)

Reviewed-Scope-Digest: 230b95c5c5446fe95135e105187106856b1c239c7ae0bad2ae53f7e616c8c22b

## What this changes and why

A real operator double-clicked `Hatch Cabinet.app` on his own Mac. The app ran
`hatch.sh --defaults --with-launchd`. Every gate passed and the first briefing
was written; then `deploy-mac.sh --officer cos` died with launchd's
`Bootstrap failed: 5: Input/output error`. Because every move-in step was a
hard `run_step`, `step_fail` exited 1 *before* the verdict block and *before*
the browser handover: no dashboard started, no password reached the clipboard,
nothing opened. Terminal printed "Process completed" and he was left holding a
cabinet he could not see. His words: *"it's like the process is stopped. the
process should be smooth and guide the user the whole way."*

Three changes follow from that.

1. **The move-in is non-fatal.** `movein_step` wraps the shared `run_step_soft`:
   the first failure stops the rest of the sequence (each step depends on the
   one before it), records `MOVEIN_FAILED [<step>]` in the flight log beside the
   step's own log, prints one calm line, and returns 0. The run continues to the
   checklist, the flight summary, the verdict and the browser. The app-feel tail
   also self-starts the dashboard when the move-in failed — nothing else did.
2. **Plain operator copy** on every line a person reads on this path: the
   opening banner, the step descriptions, the Telegram warning, the checklist
   (was "ERRAND NOTES"), the closing blocks, the browser handover, and the
   app-shell dialogs and runner. Technical detail did not move — flight log,
   step logs and the printed plan are unchanged in substance.
3. **One bootout-first retry** in `deploy-mac.sh install_plist_file`, closing a
   real asymmetry: hatch.sh's own plist loader has always done an unconditional
   bootout before bootstrap (its comment names this exact error); the officer
   leg went through `install_plist_file`, which only booted out when its
   `launchctl print` probe agreed the job was loaded.

## What is NOT softened

Host setup, instance generation, activation, every proof gate and the first
receipt still stop the run at exit 1. Without them there is no product to open,
so a "front door" would be a lie. Only the optional background helpers became
advisory.

## Exit semantics

`0` green · `1` a real gate failed · `64` usage · **`75` hatched, front door
opened, an optional background helper did not start** (sysexits `EX_TEMPFAIL`;
"retry the move-in"). `HATCH_EXIT` is seeded 0 and the only other assignment in
the file is 75 — pinned by a test. The app-shell runner passes it through with
a plain sentence per disposition, still as exactly one end-of-run notice
(APPSHELL-V05 spec 3.5: exit code + log paths).

## Risk

- `deploy-mac.sh` retry is **additive on the already-failing path**: a
  bootstrap that succeeds first time never reaches it, so no currently-working
  deploy changes behaviour. An unrecoverable failure still rolls back exactly
  as before (the rollback test now spends a 2-failure budget to reach it).
- The tail's start decision changed from `WITH_LAUNCHD != 1` to
  `WITH_LAUNCHD = 1 && MOVEIN_OK = 1 → don't start`. Read via `${MOVEIN_OK:-1}`
  so the tail stays correct when driven standalone; the "successful move-in
  must not stack a second server" arm is tested explicitly.
- Renamed operator strings are pinned in tests, so drift is loud rather than
  silent.
- Not attempted, deliberately: renaming the `Hatch Cabinet.app` bundle. That
  touches the builder, the gate, the manifest exclusion rows and the runbook,
  and is not wording in the shell layer.

## Evidence

- Falsification (§ "does the arm fail against pre-change code"): with
  `movein_step` reverted to `run_step` on the four steps and nothing else
  changed, `test_hatch_movein_nonfatal.py` fails with
  `HATCH FAILED at step [movein-chair]` — the operator's exact failure. With
  `self_start` reverted to ignore `MOVEIN_OK`, the two tail arms fail. With
  `deploy-mac.sh` at origin/master, the retry harness reproduces
  `Bootstrap failed: 5: Input/output error` and rc 2.
- Batteries: `cabinet/scripts/tests` full suite · `null-hatch.sh` ·
  `check-layer-separation.sh` · `appshell/appshell-gate.sh` (fresh egg cut,
  codesign verify, payload sha, headless smoke, pytest, claims-lint) ·
  `bash -n` + shellcheck clean on every edited shell file, matching the
  pre-change baseline · `swiftc -O` compiles `main.swift`.
- No guarded tokens introduced; exact-path adds only.
