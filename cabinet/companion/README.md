# Cabinet Companion (menu-bar) — v0.6

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

Spec: `DESIGN-companion-2026-07-10.md` (Wave D / D1). Tests:
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
