# Runbook — granting calendar Full Access to the launchd officer context

**Scope:** why the signed `cabinet-calread` helper reads all calendars from Nate's
Terminal but is silently denied in the officer context, and how to make the
launchd-spawned officer chain reliably granted. This is the remedy the officer
boot self-check line (`cabinet/scripts/calendar-boot-selfcheck.sh`) points to.

> **A green boot probe covers the EventKit READ grant only.** Create + delete/undo
> also run through the same signed fullAccess helper now (delete subcommand), but
> the writer (`CALENDAR_EVENT_SCRIPT`) is still AppleScript `Calendar` automation —
> a SEPARATE Automation-Calendar TCC surface this probe does not touch. A quiet
> boot check is necessary, not sufficient.

## The root cause (machine-grounded, macOS 26.6)

macOS attributes a TCC request to the **responsible process** — found by walking
the process tree up to the first GUI/registered app, not the immediate caller.
The officer chain is `launchd (gui/501) → /bin/bash start-officer-mac.sh → tmux
new-session -d → claude → helper`. `tmux new-session -d` daemonizes the tmux
server and reparents it to launchd (PPID 1), so the helper's ancestry dead-ends at
launchd with **no GUI app in the chain**. Result: worst case is a **silent deny,
no prompt** (tccd can't build an attribution chain → default deny; and/or a
responsible process without the matching usage string → synchronous silent deny,
stricter on macOS 15/26).

Granting Terminal never helps a launchd-spawned child: the helper that "works from
Terminal" is riding **Terminal's** calendar grant, and a helper whose chain heads
at launchd never benefits from that row.

**Reconcile the two in-tension facts** (Terminal-works vs rebuild-invalidates) with
the diagnostic before assuming: `bash cabinet/scripts/diagnose-calendar-tcc.sh`
plus `sudo launchctl procinfo $(pgrep -n cabinet-calread) | grep responsible` in
Nate's Terminal. If `responsible` is Terminal/iTerm → the grant is Terminal's and
never reaches the officer; if it's the helper's own cdhash-keyed row → it dies on
rebuild. Either way the path below fixes it.

## The durable fix (one rebuild / one re-grant; PPPC removes even the bootstrap)

1. **Wrap the helper in a real `.app` bundle** (`CabinetCalread.app/Contents/MacOS/
   cabinet-calread` + a genuine `Contents/Info.plist`). It already carries
   `CFBundleIdentifier com.cabinet.calread` + `NSCalendarsFullAccessUsageDescription`
   (currently linker-embedded via `-sectcreate __info_plist`); move them into the
   bundle plist. Add a foreground setup entry (`NSApplication.setActivationPolicy(.regular)`
   + `app.run()` around the first `requestFullAccessToEvents`) so the initial
   prompt can actually present — a bare async request silently returns false.

2. **Sign with a STABLE certificate, not ad-hoc.** Preferred: a **Developer ID
   Application** cert — removes the re-grant-on-rebuild pain (the TCC row is keyed
   to the code's Designated Requirement, not the cdhash) AND passes Gatekeeper.
   Fallback with no paid account: a **stable self-signed Code Signing cert** in the
   login keychain (also stabilizes the grant across rebuilds; does not pass
   `spctl`). **This box currently has ZERO signing identities** — a real
   prerequisite Nate must install first.

3. **Make the helper its OWN responsible process** (escape the launchd dead-end):
   - Primary: `open -W -a CabinetCalread.app --args read <s> <e> --out <tmp>` —
     LaunchServices detaches it into its own responsible client.
     **⚠ `open -W` SEVERS stdio → the helper must write JSON to a temp file
     (`--out`) that the caller reads back. That is NOT a drop-in: it changes the
     helper invocation contract and would make `calendar_read._parse_events` read
     EMPTY stdout as `[]` = "no conflict" = a double-book. It can be adopted ONLY
     with a coordinated change to (i) the reader's runner, (ii) the GERMLINE
     `action_exec` injected runner (a patch, not an edit), and (iii) a new
     fail-closed guard: treat "claimed-success exit but empty stdout AND
     missing/empty --out file" as `CalendarReadError`, never `[]`.** Do NOT bake
     `--out` into `build-calendar-helper.sh`'s default output; keep it a separately
     gated migration.**
   - Alternative: a small signed `POSIX_SPAWN_SETDISCLAIM` launcher (keeps stdio;
     non-public API).

4. **Bootstrap the grant ONCE** from Nate's granted GUI login via the app's
   foreground setup path. Because identity is now certificate-stable and the app is
   its own responsible process, the resulting TCC row is keyed to
   `com.cabinet.calread` + its DR and the launchd officer runs reuse it — no prompt.

5. **Clean-room Mac Mini upgrade (if MDM-enrolled):** push a **PPPC profile**
   (identifier `com.cabinet.calread`, `codeRequirement` = the helper's DR,
   `kTCCServiceCalendar = Allow`) — pre-grants headlessly, no bootstrap, no
   interaction. This box is NOT MDM-enrolled today, so PPPC is not available here.

**Fail-closed note:** none of this weakens the cardinal rule. If the granted read
still can't be obtained in the officer context, `calendar_read` raises
`CalendarReadError` and the double-book gather refuses to write — exactly as today.
The change only converts a guaranteed silent-deny into a reliable grant; it never
converts a denial into a silent empty.
