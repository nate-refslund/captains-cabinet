# Hatch Cabinet.app v0.6.0 — thin-shell runbook (HATCH-APPSHELL-V05)

- **Status**: shipped with Wave D on `feat/perfect-cabinet` (survey base 2d8f99d9).
- **Design of record for the STRANGER launcher**: `docs/plans/world-onboarding-hatching-2026-07-09.md`
  (WORLD-ONBOARDING-V1B, ledger row still `todo` — unmodified by this shell). v0.5 is a
  *forward shim*, not that launcher.
- **Sources**: `cabinet/scripts/appshell/` (stub, builder, runner template, lint, gate) +
  `cabinet/scripts/tests/test_appshell_build.py`. The whole appshell area is dev-side
  tooling: it builds the vehicle and never rides in it (egg-manifest exclusion rows are
  tracked with the `APPSHELL-V05` ledger row).

## What v0.5 honestly is
- A **double-clickable entry to the technical-captain face** — the documented Terminal
  fallback face of `hatch.sh` ("same engine, second face"). Terminal is deliberate: the
  engine has no native-UI mode yet, and a progress window over a headless run would hide
  the checklist and failures (fake status). The engine's checklist renders verbatim in
  Terminal; the shell adds no chrome beyond one end-of-run notice (exit code + log paths).
- The run is **self-recorded**: the runner wraps the engine in `script(1)`, writing
  `~/hatch-logs/hatch-<UTCstamp>/terminal-transcript.txt` beside the engine's own
  `--flight-log` at `~/hatch-logs/hatch-<UTCstamp>/flight.log` (v0 shipped without
  self-recording by design; the shell adds it as pure orchestration).
- **First receipt in minutes once hatched.** Single-install only (one prefix:
  `~/Cabinet/captains-cabinet`).
- Zero hatch logic in the shell: it execs `hatch.sh`, `cabinet-doctor.sh`, and (at build
  time) `egg-export.sh`. Nothing else.

## What v0.5 is NOT — the fenced list
The strings below are WORLD-ONBOARDING-V1B gate items (see that ledger row) or framing
this program forbids. v0.5 does **not** claim them, and
`cabinet/scripts/appshell/claims-lint.sh` mechanically rejects each one — case-insensitive,
widened against respellings — in every user-facing shell string and in this runbook outside
this single fenced block. The fence itself is fail-closed: a fence that is opened but never
closed, or a second fence in the same file, is a lint violation in its own right (an
unterminated fence additionally disables stripping for that file, so nothing below it can
silently escape the patterns):

```forbidden-claims
ZERO Terminal
zero commands, zero ENTER, zero typing
at most one native admin prompt
≤90 min wall-clock
non-technical captain, fresh macOS user account
opens the living world and can never re-hatch
zero hand-edits beyond documented steps
/api/hatch/* 410
byte-identical
multi-cabinet
5-minute install
```

## Build (dev Mac only — the hatch target never compiles anything)
```
bash cabinet/scripts/appshell/build-hatch-app.sh --out /path/outside/repo
bash cabinet/scripts/appshell/appshell-gate.sh          # full acceptance gate, exit 0 = PASS
python3.12 -m pytest cabinet/scripts/tests/test_appshell_build.py -q
```
The builder cuts a **fresh egg** via `egg-export.sh` (git-archive of HEAD shaped by the
manifest — never this working tree), zips it into the bundle, compiles the single-file
Swift stub with `swiftc` (Command Line Tools; no Xcode project), renders the runner and
Info.plist templates, then **ad-hoc signs** the bundle (`codesign --sign -`) and verifies
(`plutil -lint`, `codesign --verify --strict`). Provenance lands in
`Contents/Resources/payload/payload-info.json` (source HEAD + branch, egg-manifest sha256,
payload sha256, build UTC).

### Bundle layout
```
Hatch Cabinet.app/
  Contents/
    Info.plist                      org.captainscabinet.hatch, v0.5.1, macOS >= 14
    MacOS/HatchCabinet              the stub (ad-hoc signed)
    Resources/
      hatch-run.command             runner (installed into the prefix on hatch)
      payload/
        cabinet-egg.zip             fresh egg cut
        payload-info.json           provenance + hashes
    _CodeSignature/                 bundle seal (ad-hoc)
```

## Hand-transport + Gatekeeper (2026 reality)
| Transport of the zip/.app | Quarantine | First-run on macOS 15 Sequoia / 26 Tahoe |
|---|---|---|
| **scp / curl / local share / USB** (v0.5 RECOMMENDED) | No | Double-click runs. Ad-hoc signature suffices on Apple Silicon. |
| **AirDrop / browser download** | **Yes** (propagates into the .app) | "Apple could not verify…" — the right-click→Open bypass was REMOVED in Sequoia and stays gone in Tahoe → Settings ▸ Privacy & Security ▸ **Open Anyway** → second warning → admin auth → runs. Tahoe 26.2 reports: some unsigned apps get "damaged"/auto-trash with NO Open Anyway — test before relying on this row. Captain's-own-machine escape: `xattr -d com.apple.quarantine` (documented here, never scripted by the shell). |
| **Developer ID + notarized + stapled DMG** (v1.0 lane) | Yes (handled) | Single "downloaded from the Internet — Open?" confirm. The only acceptable stranger UX for downloads. $99/yr — Captain purchase call; publishing stays blocked by CG-7 regardless. |

**Hand-transport example** (dev Mac → target; quarantine-free end to end, so the .app
runs on double-click):

```
# dev Mac: zip the built bundle (--keepParent keeps the .app as the zip root)
ditto -c -k --keepParent "/path/outside/repo/Hatch Cabinet.app" "hatch-cabinet-0.5.1.zip"
scp "hatch-cabinet-0.5.1.zip" captain@target-host:~/
# target: unzip, then double-click "Hatch Cabinet.app" in Finder
ditto -x -k "hatch-cabinet-0.5.1.zip" ~/Applications/
```

**Honest empty**: the AirDrop/browser row on a macOS 26.2 box has not been exercised for
this artifact yet — record the observed outcome here after the manual matrix run.

## Launch flows
- **First launch** (prefix absent/empty) — dialog "Set up Captain's Cabinet" offers
  exactly:
  - **[Set up]** (default): engine `--defaults`; move-in stays off (it becomes a checklist
    item instead).
  - **[Set up, and keep it running]** → a SECOND explicit confirm ("Let it keep working
    while you are away?") naming the macOS "Background Items Added" notification
    (one-actuator rule: never one accidental click; on the confirm, **Back is the
    default/Return button** — arming move-in always takes a deliberate click).
    `--with-drill` is NEVER offered (halts a live fleet); `--clean-room` is not offered
    (dev/test face).
  - **[Cancel]**.
  Then: payload unpacked to the prefix (`ditto`), quarantine stripped **on the extracted
  payload only** (never on the .app — no Gatekeeper evasion), runner installed, Terminal
  opened on `hatch-run.command` via Launch Services (`open -a Terminal`) — **the stub
  sends Terminal no Apple events** (verify once per target: no automation/TCC prompt
  should appear). One app driving another is the pairing macOS asks consent for, and the
  handoff never does it. The runner's own end-of-run self-close (see Logs) is a different
  thing: it runs *inside* the window it closes, which is a self-send and prompts for
  nothing.
- **Re-launch over a Cabinet that finished setting up** — "Your Cabinet is already set
  up here" → **[Open my Cabinet]** (default) / **[Start completely fresh…]** /
  **[Check it over]** (`cabinet-doctor.sh`, probe-only/read-only) / **[Quit]**.

  *Open* writes the `open` request and hands off to the runner, which runs
  `cabinet/scripts/open-cabinet.sh`: identity-probe the dashboard on the port recorded in
  `cabinet/.env`; already mine → browser; nothing there → start it, wait on the identity
  probe with the first-build message, then browser; **someone else's app on the port** →
  never stop it and never serve on top of it — take the first free port in 3100-3199,
  append it to `cabinet/.env`, start there, and say so in one line. Then the sign-off and
  the self-close.

  Until 2026-08-25 there was no *Open* at all — a second double-click could only offer a
  read-only check or Quit, and the check `exec`ed its engine so the runner's closing
  sentence never ran. A live re-launch printed nothing and opened nothing. Both halves are
  pinned by tests: the detection arms (`HATCH_APP_PROBE=1`) and the
  no-branch-exits-in-silence arms in `test_appshell_build.py`.

- **Re-launch over anything else** (a partial tree from an interrupted unpack, or a
  folder that is not a Cabinet at all — the dialog says so honestly): "There is something
  else in this folder" → **[Start completely fresh…]** / **[Quit]**. Never re-unpacks,
  never overwrites.

- **Start completely fresh** — the only path that touches an existing install, and it
  **moves, it never deletes**. It states what is in the folder, requires the operator to
  TYPE `START FRESH` (a wrong answer changes nothing and says so), asks the old Cabinet's
  own `deploy-mac.sh --stop all` to stop anything it had running, renames the whole tree to
  a dated sibling `…/archived-<UTCstamp>` (counting up rather than landing on an existing
  name), and only then runs the ordinary first-time setup. The new run's Terminal window
  names where the old one went. `removeItem` appears exactly once in the stub — on the
  app's own handoff script — and a test fails if a second delete-shaped call appears
  anywhere.

  The detection predicate is deliberately narrow: a prefix counts as a Cabinet only when
  `cabinet/scripts/hatch.sh` is there AND a marker only a finished hatch writes
  (`instance/config/active-preset`, non-empty, or `cabinet/.env`) is there too. Both
  markers are gitignored, so neither can arrive from an unpack — which is what keeps the
  launcher off a half-written tree.

- **The runner is refreshed on every handoff** (not only on a first install). It is the
  app's own orchestration script, versioned with the app; an install made by an older app
  carries an older runner that would not understand a newer request and would fall through
  to a full setup. The payload is never re-unpacked and nothing of the operator's is
  touched.
- **Kill-switch**: no control surface in this shell, by absence; `kill-switch.sh` is never
  invoked by any v0.5 path.
- **Headless smoke** (CI): `HATCH_APP_SMOKE=1 CABINET_HATCH_PREFIX=$TMPDIR/prefix
  "Hatch Cabinet.app/Contents/MacOS/HatchCabinet"` → unpack + `hatch.sh --dry-run
  --defaults`, exit 0, no dialogs, no Terminal. `HATCH_APP_SMOKE=fresh` does the same
  after archiving an existing prefix (the move half of *start completely fresh*, run for
  real); it deliberately never asks anything to stop, because `deploy-mac.sh --stop all`
  would boot out LaunchAgents on whatever Mac the suite happens to run on.
- **Headless probe** (read-only): `HATCH_APP_PROBE=1 CABINET_HATCH_PREFIX=…` prints
  `state=absent|empty|cabinet|occupied` and exits. It looks and nothing else — there is a
  test that diffs the prefix across a probe.

## Logs
Every hatch run mints `~/hatch-logs/hatch-<UTCstamp>/` with `terminal-transcript.txt`
(script(1) full transcript; skipped with an honest note when there is no tty) and
`flight.log` (the engine's own flight log). The one shell-added notice at end of run
reports exit code + these paths — still exactly one notice, phrased for a
person since 2026-08-12, with a branch for each of the engine's three dispositions:
`0` set up · `75` set up and open in the browser, one OPTIONAL background helper did not
start (calm, not a failure) · anything else, stopped before finishing.

### Saying goodbye, and closing (2026-08-13)
The notice used to end there, and the window sat on "[Process completed]" — an operator on
a live run did not know it was finished with, or that it was theirs to close. Two answers:

- **The sign-off**, on every path, the last thing printed. Hatched (`0`/`75`):
  "✅ All done — your Cabinet is open in your browser. You can close this window."
  Anything else: "You can close this window once you have read the above." This is the
  half that always works — no permission, nothing to fail.
- **The self-close**, only where it is safe. The runner resolves *its own* Terminal window
  from *its own* tty and closes **that one, by id**, 8s after the shell exits (detached, so
  the window is idle by then and Terminal never asks whether to terminate anything). It
  refuses — silently, leaving the window open — on a run that did not hatch, outside
  Apple's Terminal (another emulator, a pipe, headless/CI: no tty, `TERM_PROGRAM` unset),
  and when no window id resolves or the id is not a plain number.

  Measured on macOS 27, 2026-08-13: the hatched run's own window closed ~8s after exit
  with every other window untouched, a failed run's window was still open 23s later, and
  **no automation prompt appeared and no TCC decision was evaluated at all** — Terminal
  addressing itself is a self-send, which macOS exempts. If a future macOS does prompt and
  the operator declines, the command fails, the detached helper dies, and the window stays
  open with the sign-off on it.

  `cabinet/scripts/tests/test_appshell_build.py` runs the shipped notice bytes for each
  disposition and pins the guard's shape and the id validation; the window physically
  closing is manual-checklist item 7 below, because no test can drive Terminal.app.

## Operator copy (2026-08-12; sign-off 2026-08-13)
Every string the operator reads — the dialogs above and the runner's first and last lines
— is written for whoever double-clicked the icon and for nobody else: what is about to
happen, how long, that they need do nothing, what to do if something is in the way, and
(since the sign-off) that the window is finished with and theirs to close.
This codebase's vocabulary (hatch, move-in, egg, launch agents, First Mate, errand notes)
stays in identifiers, comments and the allowlisted request strings, where it belongs. The
bundle is still named `Hatch Cabinet.app` — renaming the artifact touches the builder,
the gate, the manifest rows and this runbook, and is deliberately NOT part of that pass.

## Dashboard bind status — honest, as of this build (2026-07-10, base 2d8f99d9)
- The shell opens **no ports and no URLs** and never invokes `start-dashboard.sh`. Even
  `hatch.sh --with-launchd` (the move-in this app can offer) deploys the First Mate +
  measurement-plane plists — **not** `com.cabinet.dashboard`.
- When the dashboard IS brought up later (`deploy-mac.sh --all` / `--daemon dashboard`,
  or the forthcoming APP-FEEL hatch tail), the bind default is **all interfaces
  (0.0.0.0)**: at the 2d8f99d9 base `start-dashboard.sh` passes no hostname to Next.js,
  and the APP-FEEL area lands the canonical **`CABINET_DASHBOARD_HOST`** plumbing in this
  same wave with the default **deliberately unchanged** — the live box is reached over
  Tailscale.
- The default flip to loopback (`127.0.0.1`) is **owned by the APP-FEEL area** and
  **gated on the pending OC-LOOPBACK Captain call** (which includes the
  verify-no-LAN-consumer check). Until that ruling lands, treat the bind as **AMBER:
  all-interfaces by default** — stated here so the status is never silent. This shell
  asserts nothing on the variable name and needs no change when the flip happens.
- **Update 2026-07-12 — ruling landed:** the CC-LOOP / OC-LOOPBACK call is ruled and
  `start-dashboard.sh` now defaults to **loopback (`127.0.0.1`)**; remote reach is
  `tailscale serve` (the blessed path) or the `CABINET_DASHBOARD_HOST=0.0.0.0` opt-out
  in `cabinet/.env`. The AMBER treat-as-all-interfaces guidance above is resolved;
  as predicted, this shell needed no change.

## Known limits (honest)
- The payload is an egg export with **no `.git`** — the post-hatch `git pull` update
  story does not apply. Until the Captain rules on a payload-update mechanism, update =
  re-hatch into a fresh prefix (open Captain call in the spec).
- Ad-hoc signed only. Notarization (Developer ID, $99/yr) is the v1.0 stranger lane —
  Captain purchase call; CG-7 blocks publishing either way. This artifact is
  **private-side prep** for the Captain's own machines.
- macOS 14+ (`LSMinimumSystemVersion`), Apple Silicon dev build.

## Manual verification checklist (once per target)
1. Double-click → first-launch dialog appears with the three buttons above.
2. Set up → Terminal opens on the runner; engine plan + checklist render in Terminal.
3. Confirm **no automation/TCC prompt** appears for Terminal (Launch Services handoff).
4. `~/hatch-logs/hatch-<stamp>/terminal-transcript.txt` is non-empty after the run; the
   end-of-run notice shows the exit code + paths.
5. Re-launch the .app → doctor/quit dialog (no re-unpack offered).
6. AirDrop-transport row of the Gatekeeper matrix on a 26.2 box — record outcome above.
7. **The sign-off and the self-close** (the half no test can reach). On a hatched run:
   the ✅ line is the last thing printed, still **no** automation/TCC prompt appears, and
   ~8s later **that window and only that window** closes — any other Terminal window open
   at the time is still there. Then force a non-hatched exit and confirm the window
   **stays open** with its note readable.
