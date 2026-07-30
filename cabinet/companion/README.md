# Cabinet Companion (menu-bar + desk pet) — v0.7

The Captain's hand in the macOS menu bar: renders cabinet state from cheap
Redis reads and forwards intent to the repo's existing scripts. It is **not
another supervisor** — crash recovery stays with the watchdog organs. The
companion process itself only ever READS Redis (PING/GET), never calls
launchctl, and never edits anything; actuations shell the repo's existing
scripts (`kill-switch.sh`, `deploy-mac.sh`), which do their own writing.

`Continue Orientation` opens the authenticated `/onboarding` route. The app
shell keeps no onboarding state and performs no onboarding action itself; the
Dashboard, Telegram, and World all consume the same canonical journey core.
Each handoff carries fresh trace and correlation IDs. The authenticated page
records only a bounded `app_shell_handoff` observation in Evidence Recorder v1;
no source path, credential, or app-shell state is added to the URL or ledger.

Since v0.7 the same binary also carries the **desk pet** — a floating officer
that stands beside the Dock and shows the same five states as a sprite
(`--pet`, see below). `main.swift` is the brain, `pet.swift` is the body; the
pet reads nothing of its own.

Spec: `DESIGN-companion-2026-07-10.md` (Wave D / D1); pet ruling and
measurements: `designs/dock-pet-2026-07-30.md` in the meta workspace. Tests:
`cabinet/scripts/tests/test_build_companion.py`.

## Honesty up front

- **This is NOT the V1B stranger experience** (the ratified bar where no
  Terminal window ever opens). Doctor runs are background-only (log +
  notification, no Terminal window), but fleet start/stop and hatch **open
  Terminal** and their menu items say so.
- The app boots AMBER "no data yet" — never green-by-default. Every non-GREEN
  state carries a machine-built reason. Stale data (last poll >120s old)
  renders AMBER "status stale", not a confident lie.
- The companion is **bind-agnostic**: it always probes the dashboard on
  loopback (`127.0.0.1:<port>`), which is served regardless of which
  interface(s) the dashboard binds. It reads no bind variable at all.

## Build + run (on-target, no third-party deps)

```bash
bash cabinet/scripts/build-companion.sh
open "bin/Cabinet Companion.app"        # menu bar only — LSUIElement, no Dock icon

# with the desk pet (menu bar + a floating officer beside the Dock):
"bin/Cabinet Companion.app/Contents/MacOS/cabinet-companion" --pet &
```

Headless smoke (works on un-hatched Macs — any honest state exits 0):

```bash
"bin/Cabinet Companion.app/Contents/MacOS/cabinet-companion" --smoke
# STATE=GREEN|AMBER|RED|PAUSED|OFF reason=<machine-built reason>
```

Ad-hoc signed (`codesign --sign -`, stable identifier `com.cabinet.companion`).
A locally built bundle has no quarantine xattr, so Gatekeeper never prompts.
Developer ID / notarization is deliberately deferred (OC-3, Captain-gated).
The built bundle is gitignored; the egg ships source + build script only.

## What the tray icon means (state model)

Shape-encoded template icon (adapts to menu-bar appearance; the signal is the
shape + tooltip + accessibility description, never color alone):

| State | Icon | Meaning |
|---|---|---|
| GREEN | filled circle | PONG · presence v1 fresh · killswitch off · doctor GREEN ≤26h |
| AMBER | filled triangle | honest uncertainty — see reason (boot "no data yet", stale poll, presence absent/skewed/unknown schema, doctor never ran / unparseable / silent >26h) |
| RED | filled octagon | doctor heartbeat says `DEAD:<n>` |
| PAUSED | pause bars | kill switch active — officers halt on next tool call |
| OFF | hollow circle, dimmed | no cabinet root / no redis-cli / Redis unreachable |

Degradation table (§8 of the spec):

| Condition | Behavior |
|---|---|
| Repo root not found | OFF "cabinet repo not found at <path>"; menu offers only Quit + Open Companion Log |
| Root ok, Redis down | OFF "Redis unreachable at 127.0.0.1:6379 — cabinet not running"; "Hatch in Terminal…" appears **only** when `cabinet/scripts/hatch.sh` exists on disk; Run Doctor stays enabled (the doctor prints the precise DEAD lines) |
| Redis up, keys absent | AMBER "hatched but quiet — no presence/doctor data" |
| Dashboard probe fails | Open Dashboard / Continue Orientation / Open World disabled with "dashboard not running" — never a dead-URL open |
| Notifications denied/unavailable | events fall back to a "Last event: …" menu line, silently honest |

Root discovery: bundle self-locate (`<root>/bin/Cabinet Companion.app` ⇒ two
dirs up) → `CABINET_ROOT` env → `~/captains-cabinet` (home-relative last resort); each candidate
is validated by `cabinet/scripts/cabinet-doctor.sh` existing.

Dashboard port: `cabinet/.env` is line-scanned for the single anchored
assignment `CABINET_DASHBOARD_PORT=<digits>` (default 3100). The file is
**never sourced or executed** and no other line is retained — it is the
secrets file. Note: until the dashboard port-order fix lands (owned by the
dashboard area), the static-plist launch path ignores the `.env` port; the
1s loopback HEAD probe keeps the companion honest under any mismatch.

## Kill-switch lever (typed confirm)

- The menu shows the CURRENT state as an explicit verb — "⏸ Stop All
  Officers…" or "▶ Resume Officers…" — **never a toggle**, so a stale menu
  cannot invert intent.
- A click does a fresh synchronous Redis read first; if that read fails the
  app **refuses to arm** ("Cannot verify current kill-switch state").
- The confirm dialog's action button stays disabled until you type exactly
  `STOP` (activate) or `RESUME` (deactivate). Cancel is the default button;
  Esc cancels.
- Actuation shells the locked `cabinet/scripts/kill-switch.sh` (with loopback
  `REDIS_URL` pinned — the script's default is a docker-era hostname and it
  reports success even when its write fails), then **post-verifies by GET**
  and notifies honestly: ACTIVE / deactivated / "Actuation FAILED — state
  unchanged" / "Actuation UNVERIFIED" (post-verify read failed).

## Poll cadence + cost

15s timer (5s tolerance), backoff to 60s while OFF; immediate poll on launch,
menu open, after any actuation, and on wake. Per tick: ≤3 `redis-cli` spawns
(PING + presence + doctor heartbeat) + 1 conditional killswitch fallback
(which shells the ONE shared reader, cabinet/scripts/hooks/killswitch-read.sh,
rather than a bare GET — an unreadable switch renders PAUSED "cannot verify",
never "off"),
each with a 2s app-enforced kill-timeout. The doctor NEVER runs on the poll
loop — it is click-only. One `ProcessInfo.beginActivity(.background)` token is
held for the app's lifetime (App Nap); if throttling happens anyway, the 120s
staleness rule renders AMBER.

## The desk pet (`--pet`)

A borderless, always-on-top window holding one officer's 16x32 sprite, standing
on the Dock's top edge. The Captain chose this surface over a real
`NSDockTile` on 2026-07-30, knowing the trade: crisper (one resample instead of
two) and able to roam, but not literally in the Dock.

```bash
cabinet-companion --pet [--pet-officer <slug>] [--pet-scale <1..8>]
cabinet-companion --pet-demo <GREEN|AMBER|RED|PAUSED|OFF>   # forced state, live poll OFF
cabinet-companion --pet-selftest                            # state -> look table
cabinet-companion --pet-render <STATE> <out.png>            # the canvas, source resolution
```

| State | Body | Chip | Motion |
|---|---|---|---|
| GREEN | full colour | — | roams along the Dock |
| AMBER | desaturated | `?` | stands, breathing (idle strip) |
| RED | desaturated | `!` | stands, breathing |
| PAUSED | full colour | `‖` | frozen mid-stride (the world's killswitch idiom) |
| OFF | hollow shell | `?` | stands, breathing |

The rule under all five: **absence must not look like calm.** Every desk pet in
the genre sleeps when idle, and sleeping reads as "all is well" — which, for a
cabinet whose most common truth today is "I cannot see anything", is a lie. The
pet also refuses GREEN when the fleet is green but *its own* officer has no
presence row or is absent: it portrays an officer, so it must not walk
contentedly while that officer is missing.

Facts worth not re-deriving:

- **Zero permissions.** No Accessibility, no Screen Recording. The Dock's
  geometry comes from `NSScreen.frame` minus `NSScreen.visibleFrame`, which any
  app may read. Window-edge tracking (walking along *other* apps' windows) is
  the feature that would need Accessibility, and it is not built.
- **Per-pixel click-through is broken on macOS 26.6** (measured: a transparent
  window that draws nothing still takes the mouse-down across its whole frame).
  The pet therefore sets `ignoresMouseEvents = true` and can never intercept a
  click — the cost is that v1 is not clickable, and interaction stays in the
  menu-bar item. Pinned by `test_pet_click_through_finding_is_pinned`; re-run
  the probe before changing it.
- **Integer scales only** (default 3 = a 48x96pt officer). A resampled pet is a
  failed pet, so `--pet-scale` rejects anything outside 1..8 rather than
  silently accepting a fractional size.
- **Same body as the World.** Officer → sheet uses the World's own FNV-1a hash
  over the owned `originals/characters` cast, and the strip geometry is pinned
  against `dashboard/src/lib/world/sprites.ts` by the test suite, so the two
  surfaces cannot drift apart silently.
- The sprite sheets live under `cabinet/dashboard/public/world-assets/`. The pet
  draws an unmistakable red box and logs the path when a sheet is **missing**,
  when it **decodes at the wrong size** (a truncated or re-exported sheet is
  refused, never resampled into the cell), and when the **frame it needs is
  empty** — never an empty window, which would be indistinguishable from "not
  running".
- `--pet-demo` suppresses the live poll entirely, logs loudly, marks the
  menu-bar tooltip `DEMO (synthetic, not a reading)`, labels the menu
  `DEMO — synthetic <STATE>; the cabinet is NOT being read, and every action is
  disabled`, and **disables every acting item** — the kill-switch lever, the
  Doctor run, the fleet wrappers and the dashboard probe. Actuation was always
  safe (the lever re-reads Redis before arming), but the lever's VERB is
  derived from the state, and "▶ Resume Officers…" computed from a made-up
  PAUSED is a lie in the one menu that must never lie.

## First-run expectations (one-time macOS moments)

- **"Background items added"** banner appears the first time you enable
  Launch at Login (SMAppService; the checkbox is **default OFF** — the
  companion never registers itself).
- **Notification permission** is requested lazily on the first event that
  needs it. If denied — or when running the bare binary outside the bundle —
  events degrade to the "Last event" menu line.
- `Open World` bounces to `/login` on first open — the world page is
  auth-gated; expected.

## Log

`~/Library/Logs/cabinet-companion.log` — state transitions, doctor run output,
kill-switch actuation transcripts (script stdout is recorded but never
trusted), wrapper regeneration. "Open Companion Log" in the menu opens it.
The log is append-only and not rotated by the companion; trim it manually if
it ever grows bothersome.

## Terminal wrappers

Fleet actions launch via static `.command` wrappers regenerated at every
companion start under `~/Library/Application Support/Cabinet Companion/`
(absolute root-stamped paths, fixed content, zero user input), opened through
Launch Services. Start Fleet targets `deploy-mac.sh --all`, Stop Fleet targets
`deploy-mac.sh --stop all` (Wave D / D2), and Deploy Dry-Run targets
`deploy-mac.sh --all --dry-run` — a bare `--dry-run` carries no selector and
is a usage error (exit 64), so the wrapper pins the full-fleet plan invocation
(runtime-verified; on a box with no seeded roster it prints the honest
roster-refusal instead of a plan, and mutates nothing either way).
