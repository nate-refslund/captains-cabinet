# Mac Mini Deployment Runbook

The end-to-end runbook for taking the Cabinet from "code on GitHub" to "running 24/7 on a Mac Mini." Authored by Phase 8 of the convergence plan.

This document is opinionated and idempotent — every step can be re-run safely. Steps that require Captain-physical actions (plugging hardware, entering Apple Developer credentials) are flagged with `[CAPTAIN]`.

---

## Hardware prerequisites

- Mac Mini, Apple Silicon (M1 or newer recommended)
- macOS Sequoia 15 or newer
- 16 GB RAM minimum (32 GB recommended for full officer set)
- 512 GB SSD minimum
- UPS (APC Back-UPS or similar) — required for graceful shutdown on power loss
- Wired ethernet (Wi-Fi works but Tailscale + officer-to-officer Redis is happier wired)
- Apple Developer ID (`[CAPTAIN]` — costs $99/yr; required for code-signing officer entitlements)

---

## 1. Base macOS setup `[CAPTAIN]`

1. Run macOS through initial setup. Sign in to iCloud (optional but recommended for Tailscale auth).
2. Install Xcode Command Line Tools:
   ```bash
   xcode-select --install
   ```
3. Install Homebrew (https://brew.sh).
4. Disable mac sleep when on power:
   ```bash
   sudo pmset -c sleep 0 displaysleep 30
   ```
5. Disable Wi-Fi power saving + USB autosuspend:
   ```bash
   sudo pmset -a tcpkeepalive 1 networkoversleep 0
   ```

## 2. Cabinet repository clone

```bash
mkdir -p ~/work
cd ~/work
git clone <your-fork-url> captains-cabinet
cd captains-cabinet
git checkout claude/convergence-v2    # OR master once this branch is merged
```

## 3. Cabinet bootstrap (orchestrator)

```bash
bash cabinet/scripts/setup-mac.sh
```

`setup-mac.sh` is the single orchestrator; the default (also `--fast`) is a
FAST boot. In order it: runs the **key wizard** (Step 0 — `setup-env.sh`;
every key is recommended or optional, nothing is critical-tier — it opens
signup pages, masks paste input, and writes `cabinet/.env` at `chmod 600`;
`setup-env.sh --defaults` writes a minimal local-only `.env` with zero cloud
accounts and generates the private Telegram webhook authentication secret),
installs missing Homebrew deps (tmux, jq, python3, redis), starts
Redis (+ enables AOF), provisions the LOCAL work store when no connection
string is configured (`provision-local-postgres.sh` — PostgreSQL 16 +
pgvector; Neon is the documented cloud alternative, no longer a
prerequisite), creates required directories, bootstraps officer roles,
installs the Captain-layer Mac tool stack, installs any declared extensions
(`instance/config/extensions.yml`), loads the preset, verifies the policy
engine, and runs the FAST proofs (null-hatch gate + clean-room pytest
subset). Idempotent.

Opt-in flags (combinable): `--with-sensors` (the old Steps 9-11: screenpipe,
cua, browser MCPs, Cabinet Chrome profile, TCC grant prompts),
`--with-dashboard` (npm ci + dashboard build), `--full-suite` (full
framework pytest suite), `--all` (all of the above).

Verify: `bash cabinet/scripts/setup-mac.sh --check` returns exit 0.

> The wizard already created `cabinet/.env`. To re-run it later (add/replace
> keys): `bash cabinet/scripts/setup-env.sh --force`. Headless (CI/clone):
> `bash cabinet/scripts/setup-env.sh --defaults`, or
> `SKIP_ENV_WIZARD=1 bash cabinet/scripts/setup-mac.sh` to skip the wizard
> and fill `.env` yourself. To sign in without printing the generated
> dashboard password, run `bash cabinet/scripts/dashboard-password.sh --copy`
> on the Cabinet Mac and paste from the clipboard.

## 4. Configuration

1. Keys are already set by the Step 0 wizard above (`NEON` / `NOTION` /
   `ELEVENLABS` if voice / `GEMINI` if image-gen / `MONDAY_API_TOKEN` etc. for
   your task system, plus officer Telegram bot tokens + Captain chat id). Re-run
   `bash cabinet/scripts/setup-env.sh --force` to change any.
2. Set Captain identity in `instance/config/platform.yml`:
   ```yaml
   captain_name: "<your-name>"
   captain_telegram_chat_id: <id>
   captain_timezone: "Europe/Berlin"   # or your IANA timezone
   ```
4. Initialize the Captain triplet:
   ```bash
   bash cabinet/scripts/bootstrap-captain-triplet.sh
   ```
5. Posture ruling `[CAPTAIN]` (sovereign amendment 2026-07-05, apply token
   `apply sovereign posture`). `cabinet-init` renders an
   `instance/config/posture.yml` scaffold from the flavor answer (default
   guardian; a `mini-*` org cabinet id renders `posture: sovereign`). The
   scaffold is INERT until YOU ratify it — `resolve_posture` answers
   `sovereign` only for a present + schema-valid + `deployment == CABINET_ID`
   + **schg-locked** ruling; anything else (including this unlocked scaffold)
   is guardian, today's rules. To ratify:
   ```bash
   $EDITOR instance/config/posture.yml       # your ruling words in basis: + real ruled_at:
   printf 'version: 1\ngrants: []\n' > instance/config/standing-grants.yml
   git add instance/config/posture.yml instance/config/standing-grants.yml && git commit -m "posture ruling"
   sudo bash cabinet/scripts/germline-lock.sh lock    # the lock IS the signature (D5)
   bash cabinet/scripts/germline-lock.sh status       # confirm both files LOCKED
   ```
   Ceiling grants change ONLY via `sudo bash cabinet/scripts/grant-apply.sh
   NEED-<8hex>` after a `grant NEED-<hex>` Telegram binder approval; arm the
   binder needs verbs by setting `CABINET_NEEDS_WIRED=1` in the generated
   cos-inbound plist (dark by default). Do NOT
   `launchctl load com.cabinet.gate-apply` — the germline code-apply daemon
   stays DARK until the unprivileged sandbox harness is built and you
   explicitly arm it (D15). Emergency brake at any time:
   `CABINET_POSTURE=guardian` in the environment narrows every session
   (env can only narrow — `CABINET_POSTURE=sovereign` is ignored).

   **Axes (cabinet-axes amendment 2026-07-05, apply token
   `apply cabinet axes`).** The ruling file now carries the full axis
   point: this deployment is the `org-macmini` preset —
   `cp instance/config/posture-presets/org-macmini.yml
   instance/config/posture.yml` pre-fills `flavor: org` +
   `deployment_target: mac_mini` (schg attestation backend) before you
   edit `basis:`/`deployment:` and lock. Optional keys: `never_grant:`
   (list of ceiling classes structurally non-grantable on THIS deployment
   — grant rows in those classes are dropped fail-closed) and
   `deployment_target:` (absent ⇒ inferred; a docker deployment uses the
   `ro_mount` backend — germline/posture/grants mounted read-only from
   the HOST, `cabinet/deploy/docker/README.md`). A third narrow surface
   joins the env brake: the Captain binder verb `posture guardian|earn_up`
   writes `instance/config/posture-narrow` (deliberately unlocked — it
   can only NARROW; `posture clear` removes it). `earn_up` — everything
   proposes, cells climb only on Captain-granted rungs — is honored even
   unattested (narrowing needs no lock); check the effective point any
   time with `python3 cabinet/scripts/posture-status.py`.

## 5. First product onboarding

```bash
bash cabinet/scripts/bootstrap-project.sh <repo-url> <slug>
# example: bash cabinet/scripts/bootstrap-project.sh https://github.com/your/app bakery
```

Generated `instance/config/projects/<slug>.yml`. Activate it:

```bash
echo "<slug>" > instance/config/active-project.txt
```

`[CAPTAIN]` review the generated YAML; tune `tasks.system`, `tasks.config.*`, `product_metadata` fields as needed.

## 6. Code-signing + notarization `[CAPTAIN, ~30 min]`

Required so TCC permissions (Accessibility, Full Disk Access, screen recording for the optional cua-driver MCP) persist across reboots. Without this, every officer restart re-prompts for permissions and the Cabinet can't run unattended.

### 6.1 Apple Developer setup
1. Sign in to https://developer.apple.com with your Apple ID.
2. Enroll in the Apple Developer Program ($99/yr) if you haven't already.
3. In Keychain Access, request a **Developer ID Application** certificate from a certificate authority. Download + double-click to install.
4. Verify:
   ```bash
   security find-identity -v -p codesigning
   ```
   You should see `Developer ID Application: <Your Name> (TEAM_ID)`.

### 6.2 Sign Cabinet entitlements
The Cabinet ships an `officer-entitlements.plist` at `cabinet/launchd/officer-entitlements.plist`. Sign it:

```bash
codesign --force \
  --options runtime \
  --entitlements cabinet/launchd/officer-entitlements.plist \
  --sign "Developer ID Application: <Your Name> (TEAM_ID)" \
  $(which claude)
```

(Yes, you sign the `claude` binary because Claude Code is the process holding TCC permissions. The codesign embeds the entitlements.)

### 6.3 Notarize

```bash
xcrun notarytool submit $(which claude) \
  --apple-id "<your-apple-id>" \
  --team-id TEAM_ID \
  --password "@keychain:AC_PASSWORD" \
  --wait
```

`@keychain:AC_PASSWORD` references an app-specific password you previously stored via `xcrun notarytool store-credentials AC_PASSWORD`.

### 6.4 Grant TCC permissions

Open System Settings → Privacy & Security:
- Add Terminal (or iTerm) to **Accessibility**, **Full Disk Access**, **Screen Recording** (only if cua-driver MCP needed).
- Add the `claude` binary path to the same lists.

After signing + notarization, these consents persist across reboots.

## 7. Deploy LaunchAgents

Before reconciling or deploying a live checkout with local changes, capture a
verified recovery point. This does not stash, reset, fetch, stop services, or
print secrets:

```bash
bash cabinet/scripts/pre-dogfood-snapshot.sh --root /Users/<captain>/captains-cabinet
```

The mode-700 destination contains a verified all-refs Git bundle, exact dirty
files and patches, a separate local-only runtime-secret archive, and a freshly
validated Postgres snapshot when configured. Redis is deliberately excluded:
the script records that exclusion instead of duplicating a weaker capture path.
Before reconciliation or dogfood, run the separate mandatory Redis T0 gate:

```bash
bash cabinet/scripts/backup.sh
bash cabinet/scripts/restore-drill.sh
```

`worktree-before.txt` must be identical to `worktree-after.txt`; otherwise the
checkout/Postgres capture fails and must be repeated from a quiescent state.
Never attach `runtime-secrets.tgz` to the shareable dogfood evidence bundle.

```bash
CABINET_ROOT="$(pwd)" bash cabinet/scripts/deploy-mac.sh --all --dry-run
CABINET_ROOT="$(pwd)" bash cabinet/scripts/deploy-mac.sh --all
```

`--all` is an exact reconciliation, not an additive installer. It validates
the entire manifest before changing launchd, renders and lints every enabled
daemon/watchdog/cron row, and installs:

- `com.cabinet.officer.<slug>.plist` — one per officer, fleet **derived from
  `instance/config/roster.yml`** (F0.2; no roster file ⇒ refuse, never a preset
  default). Example portfolio roster: `cos`, `bakery-ceo`, `newsletter-ceo`,
  `comms-officer`.
- every non-disabled row in `cabinet/services.yml` (including
  `com.cabinet.limit-reset-watchdog.plist` and `com.cabinet.dashboard.plist`).

Installed or loaded `com.cabinet.*` jobs outside that exact set are booted out
and their plist is parked as `.plist.disabled`; this includes rows marked
`disabled: true`, retired templates, and previous roster officers. The
launchd-owned `com.cabinet.egress-proxy` is the sole preserved out-of-manifest
job because `egress-guard.sh` owns it; fleet deployment never creates an
unenforced interval. Each service replacement has a local rollback: if the new
job cannot bootstrap, the previous plist/job is restored and the deploy exits
non-zero. `cabinet/launchd/generated/` is also pruned to exactly the current
enabled manifest outputs.

`com.cabinet.dashboard.plist` is the control panel + office-display server on
`:3100`. Port/bind config (Wave D app-feel): `CABINET_DASHBOARD_PORT` (default
3100) and `CABINET_DASHBOARD_HOST` (default `127.0.0.1` — loopback-only since
the CC-LOOP / OC-LOOPBACK ruling, 2026-07-12); explicit env (launchd plist) >
`cabinet/.env` > default. Remote reach is explicit: front the dashboard with
`tailscale serve` (the blessed path), or opt out with
`CABINET_DASHBOARD_HOST=0.0.0.0` in the mini's `cabinet/.env` for plain
tailnet/LAN reach at `http://<host>:3100`. **Migration step (pre-existing in
this runbook; operative now the flip is ruled)**: a box that must keep plain
tailnet http reach adds `CABINET_DASHBOARD_HOST=0.0.0.0` to its `cabinet/.env`
BEFORE deploying the flip (or fronts the dashboard with `tailscale serve`) —
no silent loss of documented reach.

A template outside the manifest can still be installed as a deliberate,
single-service diagnostic act, but it is not a production-ready state: Doctor
will stay red until the extra is removed or promoted into `services.yml`, and
the next exact `--all` will park it again:

```bash
bash cabinet/scripts/deploy-mac.sh --daemon <name>
```

`com.cabinet.dashboard-kiosk.plist` is therefore not part of the Doctor-gated
fleet today. Do not install it for the observe-only dogfood; promote it to an
enabled manifest row with matching tests before treating kiosk mode as ready.

Verify the declared set, absence of extras, loaded state, and service freshness:

```bash
bash cabinet/scripts/cabinet-doctor.sh
```

Exit 0 = pass. An unexpected loaded job or installed `.plist` is a hard Doctor
failure; a parked `.plist.disabled` is retained evidence and is not active.

> **Portfolio-preset note.** A **portfolio** deployment (one persistent Chair
> `cos` + domain officers, e.g. `comms-officer` + one `<lane>-ceo` per lane) is
> what `--all` deploys when the roster says so; its daemons (e.g.
> `com.cabinet.intake-surface`, `com.cabinet.frontdoor-briefing`,
> `com.cabinet.officer-supervisor-mac`) are enabled manifest rows installed by
> the same exact reconcile. (Historical: `--all` used to hardcode the retired
> `work`-preset `cos cto cpo cro coo` fleet, and later installed only two
> manifest services — both gaps are closed by roster derivation + exact
> manifest reconciliation.)
>
> **TEMPORARY backstop (`com.cabinet.status-sweep`).** A 30-min `StartInterval`
> cron (`run-status-sweep.sh`) that pushes a STATUS-SWEEP trigger to the Chair
> (`cabinet:triggers:cos`) so the Chair periodically sweeps in-flight work + DMs
> the Captain a digest — a backstop to the Redis trigger Channel, which can't wake a
> slept/idle session. Beginner-cadence only; disable when no longer needed:
> `launchctl bootout gui/$(id -u)/com.cabinet.status-sweep`. NOTE: `StartInterval`
> does not fire while the Mac is asleep — wake-time backstop on the MacBook; true
> 24/7 needs the always-on Mac mini.

### 7.0z Limit-reset auto-continue watchdog (`com.cabinet.limit-reset-watchdog`)

`cabinet/cron/limit-reset-watchdog.sh` (every **3 min**, `StartInterval=180`)
recovers an officer that hit the **account session limit** — the case where
Claude Code prints `You've hit your session limit · resets H:MMpm` and the
active turn dies (the never-stop Stop hook can't fire, because the turn failed
rather than stopped). It runs two phases each tick:

1. **Detect + parse + store.** Scans each `officer-<slug>` tmux pane
   (`tmux capture-pane`) for the limit banner. A line must carry **both** a
   limit phrase **and** a `reset(s) <clock>` clause (so the watchdog's own
   resume nudge and relayed triggers that merely mention "session limit reset"
   never false-arm). It resolves the clock in the Captain timezone
   (`platform.yml → captain_timezone`, Copenhagen/Berlin — am/pm aware, and if
   the time already passed today it rolls to **tomorrow**), then stores the UTC
   epoch at `cabinet:limit-reset:<slug>` (12 h TTL self-clear guard).
2. **Watch + wake.** When `now ≥ cabinet:limit-reset:<slug>`, it atomically
   `GETDEL`s the key (fire-exactly-once) and fires the **existing** wake —
   `notify-officer.sh <slug> "Session limit reset — resume your active-task"`
   (durable trigger XADD + `trigger_wake_officer` tmux nudge). The woken officer
   reads its own `cabinet:active-task:<slug>` flag and resumes via the
   never-stop loop. The watchdog never creates the active-task flag (only the
   officer knows its task) and never `kickstart`s — a limit-blocked officer is
   **alive**, so this is wake-only. (That's why it is a **separate** daemon from
   `heartbeat-watchdog`, which restarts *dead* officers.)

```bash
# install (also done by deploy-mac.sh --all)
bash cabinet/scripts/deploy-mac.sh --daemon limit-reset-watchdog
# unit-test the time parser (no Redis/tmux side effects)
CABINET_LRW_SELFTEST=1 bash cabinet/cron/limit-reset-watchdog.sh
# inspect / clear an armed reset
redis-cli GET  cabinet:limit-reset:<slug>
redis-cli DEL  cabinet:limit-reset:<slug>
# logs
tail -f ~/Library/Logs/cabinet/limit-reset-watchdog.err.log
```

If Redis is unreachable the watchdog no-ops and retries next tick. Like all
`StartInterval` crons it does not fire while the Mac is asleep — true 24/7
recovery needs the always-on Mac mini.

### 7.0a Officer self-wake (loop-prompts + supervisor)

Mac officers run as **separate** `officer-<role>` tmux sessions and only advance
when they take a tool action (the post-tool-use hook is what surfaces their
queued triggers + carded work). So each domain officer is given a durable
self-wake `/loop`:

- **Per-role loop prompt:** `cabinet/loop-prompts/<role>.txt` (gather-then-decide
  sweep — check triggers + intake + the lane's captain-attention backlog, do the
  next due lane step, surface to the Chair, never DM the Captain). R091: lane
  prompts are instance materializations (untracked; canonical copies in
  `instance/loop-prompts/`); an officer with no per-role file gets the generic
  parameterized tick rendered from `cabinet/loop-prompts/_template.txt`
  (`{{officer}}` slots). Only if the template is also absent does the officer
  have no self-wake.
- **First arm at boot:** `start-officer-mac.sh` submits `/loop 5m <prompt>` after
  the boot prompt via `officer_loop_arm` (in `lib/officer-boot.sh`).
- **Recurring safety-net:** `com.cabinet.officer-supervisor-mac.plist` (every 2h)
  runs `officer-supervisor-mac.sh`, which re-sends the `/loop` into each live
  `officer-<role>` session so a session that exited its loop is re-armed without
  a full restart. Crash-restart itself stays owned by each officer's LaunchAgent
  KeepAlive. (This is the Mac counterpart to the Docker `officer-supervisor.sh`,
  which targets a single `cabinet` session-with-windows and is a no-op on Mac.)

Re-arming is idempotent: Claude Code's `/loop` registers a cron keyed on
`(interval, prompt)` and re-uses the same job id rather than stacking duplicates.

Verify an officer is self-waking:

```bash
# heartbeat should be seconds-fresh (post-tool-use writes it every tool call)
redis-cli -h localhost GET cabinet:heartbeat:bakery-ceo
# the loop registered a cron (look for "Scheduled <id> (Every 5 minutes)")
tmux capture-pane -t officer-bakery-ceo -p | grep -i scheduled
```

### 7.1 Interactive one-time steps (login / OAuth) `[CAPTAIN]`

Officers run unattended with full host shell access, so they self-install
plugins/MCPs via the `claude plugin` / `claude mcp` CLI. The only things they
*can't* do alone are inherently-interactive auth prompts — `gh auth login`
(needed once for private plugin marketplaces, e.g. a Monday-integration plugin),
`claude /login` if you're not using an API key, OAuth device-code pastes.

Do those once by attaching to a live officer session and typing as the user:

```bash
tmux attach -t officer-cos     # or officer-cto, etc.
# …run the interactive command, complete the auth…
# DETACH with:  Ctrl-b  then  d     ← do NOT press Ctrl-C (that kills the officer)
```

After detaching, the officer keeps running with the new auth. This is also how
you'd run any ad-hoc command (including a REPL `/`-command) in an officer's
exact environment.

## 8. Tailscale (remote access) `[CAPTAIN]`

The Mac Mini needs remote SSH for the Captain to check in, especially during the 72h soak.

1. Install Tailscale: https://tailscale.com/download
2. Sign in. Add the Mac Mini to your tailnet.
3. Enable Tailscale SSH (Tailscale settings → SSH). Tailscale handles authentication; no need to expose port 22 to the internet.
4. From any machine on your tailnet:
   ```bash
   ssh <mac-mini-tailscale-name>
   ```

## 9. UPS + apcupsd

If using an APC UPS:

```bash
brew install apcupsd
sudo cp /opt/homebrew/etc/apcupsd/apcupsd.conf.sample /opt/homebrew/etc/apcupsd/apcupsd.conf
# Edit /opt/homebrew/etc/apcupsd/apcupsd.conf:
#   UPSCABLE usb
#   UPSTYPE usb
#   DEVICE
sudo brew services start apcupsd
```

Verify with `apcaccess`. The shutdown hook (`/opt/homebrew/etc/apcupsd/apccontrol`) handles graceful officer shutdown on low-battery (it sends `SIGTERM` to `claude` processes before pulling power).

Test by unplugging the UPS from wall power and watching the officers shut down cleanly (~5 min before forced shutdown).

## 10. Backup strategy

The Cabinet's durable state lives in three places:

| Where | What | Backup |
|---|---|---|
| **Postgres (Neon)** | event ledger, role entities, work graph, OVI snapshots | Neon's built-in continuous backup (free tier: 7 days PITR) |
| **Filesystem** | `shared/interfaces/captain-*.md`, `instance/roles/active/*.yml`, `memory/skills/evolved/*.md`, `memory/tier3/experience-records/` (canonical store since 2026-07-04 — both `.jsonl` and `.md` records) | Daily `rsync` to local NAS OR S3 |
| **Filesystem (out-of-repo)** | `~/Library/Application Support/cabinet/` — audit events, attention feed, undo journal, evidence store, and `captain-inbound/` (the durable verbatim Captain-DM archive, 2026-07-17 — a truth surface: the case ledger source and every attention metric's denominator; read it with `cabinet/scripts/captain-inbound.py latest\|get\|search [--semantic]`, never the redis ring) | ⚠ NOT yet in any backup set (pre-existing gap the archive inherits) — add to the manifest-owned backup job |
| **Redis** | Heartbeat, cost counters, trigger streams | Bounded fresh RDB; healthy multipart AOF fallback is drained, replayed, repaired, exactly proved, converted to RDB, and exactly re-proved if BGSAVE is stuck |

**The backup job is manifest-owned (lane-ops 2026-07-04)** — do NOT hand-roll
a cron script (the old `~/bin/cabinet-backup.sh` rsync snippet that used to
live here predates the fleet manifest and described none of the real
machinery). The pieces:

- **`cabinet/scripts/backup.sh`** — the actual backup (topology-preserved filesystem artifacts +
  a bounded fresh Redis RDB transfer, with a write-paused, globally drained,
  replayed, repaired, converted-to-RDB AOF fallback + automatic `pg_dump` whenever `DATABASE_URL` or
  `NEON_CONNECTION_STRING` is configured; use `--no-pg` only deliberately). Scheduled by
  the `backup` row in `cabinet/services.yml` (daily 03:00 local,
  `--retention-days 14`, destination `~/Cabinet-Backups`; the row's `expected:`
  floor puts it under outcome-watchdog no-silent-cron coverage). Render/load
  via `cabinet/scripts/generate-plists.py`.
  Under `CLIENT PAUSE WRITE`, global AOF drain means a bounded wait for
  `aof_buffer_length=0`, `aof_pending_bio_fsync=0`, last write OK, and no AOF
  rewrite; it is not described as a global-fsync guarantee. The AOF copy is
  replayed in a disposable Redis, known Streams operational omissions are
  repaired from an identifier-only manifest, and exact v3 state is proved.
  The result is converted to RDB, booted in a second disposable Redis, and
  exactly re-proved before publication as an RDB with `aof-converted`
  provenance. The exact v3 logical-state proof—not the drain—is the
  authoritative completeness gate.
  Each Redis capture includes `redis-state.txt`: the v3 proof hashes canonical,
  type-aware logical state with SHA-256, separates durable keys from keys with
  absolute expiry deadlines, and allows a volatile key to be absent after its
  recorded deadline. Changed, unexpected, prematurely missing, or unsupported
  values fail closed. Its blocking source fingerprint has a 55-second internal
  deadline inside the 60-second write pause, so keyspace growth fails the
  backup clearly instead of overrunning the capture window. Restore drills
  retain strict compatibility with legacy
  v2 snapshots without weakening their exact comparison.
- **`cabinet/scripts/restore-drill.sh`** — prove a snapshot actually restores
  (newest snapshot → full restore into a throwaway temp dir → artifact
  verification; read-only against the backup, deliberately no `--apply`). A
  backup nobody has restored is a hope, not a backup.
- **Deliberately NOT wired (Captain decision, recorded on the services.yml
  `backup` row):** an off-machine copy (recommended: post-backup rsync of
  `~/Cabinet-Backups` to the UpCloud CPH box over Tailscale — a local
  snapshot dies with the disk). Redis AOF is already enabled on the live host
  and is now a verified fallback for the daily capture.
- **Ledger-hygiene backups are separate** from this daily job: the one-shot
  purge tools (`cabinet/scripts/ledger-purge-testrows.sh` for the JSONL
  event families, `cabinet/scripts/purge-sqlite-mirror.py` for the
  org-runtime SQLite Store mirror, `cabinet/scripts/feed-purge-testrows.sh`
  for the attention feed journal) each take their own verified pre-mutation
  snapshot (`ledger-backups/` sibling dir / `cabinet/cache/mirror-backups/`
  / `feed-backups/` sibling dir) — see each script's header for the gate +
  rollback contract.

## 11. Verification — 72h soak

For a no-authority-expansion dogfood, first follow
`docs/runbooks/observe-only-dogfood.md`. Do not start the clock until its
process, CUA, source-write, posture, spend, and egress assertions are recorded.
After everything is in place:

1. Start a representative outcome:
   ```bash
   cat >> instance/config/outcomes.yml <<'EOF'
   - id: outcome-soak-001
     name: 72-hour readiness test
     description: Continuous Cabinet operation with mission execution + OVI tracking
     measurable_criteria:
       - Officers respond to Captain DMs within 5 min
       - Officers pull + progress their ready mission tasks each self-wake tick (routing is pull-only; see .claude/skills/cabinet-route-tasks/)
       - OVI snapshot fires Monday 08:00 with non-zero data
       - No officer process exits abnormally for 72 hours
     status: active
     captain_ratified: true
   EOF
   ```
2. Verify the exact fleet and all service freshness floors:
   ```bash
   bash cabinet/scripts/cabinet-doctor.sh
   ```
3. Verify mission flow:
   ```bash
   bash cabinet/cron/mission-supervisor.sh --dry-run --json
   ```
4. Send a test Captain DM via Telegram → verify your officer replies + voice fires (if enabled).
5. Force-kill an officer: `pkill -9 -f 'claude.*officer.cos'` → supervisor should restart within 30s.
6. Record the exact non-reboot recovery drill before a physical power cycle:
   ```bash
   bash cabinet/scripts/test-recovery.sh --dry-run
   bash cabinet/scripts/test-recovery.sh \
     --evidence-dir "$HOME/.cabinet-readiness/$(date -u +%Y%m%dT%H%M%SZ)/recovery"
   ```
   This is an exact equality gate, not a minimum-process-count smoke test. It
   derives the only restartable labels from enabled `cabinet/services.yml`
   rows plus the deployment roster, refuses any loaded disabled/legacy label,
   leaves the separately attested egress proxy running, tears down the exact
   roster tmux sessions, and requires labels, sessions, active kill switch,
   observe posture, egress attestation, Redis, and Cabinet Doctor's semantic
   result to match the pre-state. Its failure trap only restores allowlisted
   labels; it never globs installed `com.cabinet.*` plists.
7. Power-cycle the Mac → all enabled services and roster officers should come
   back up automatically; Captain should receive a "Cabinet is back online"
   DM. Re-run `test-recovery.sh --dry-run` to verify the exact
   post-power-cycle state without another teardown.
8. Wait 72 hours. Re-run `cabinet-doctor.sh` + check OVI snapshot count via:
   ```bash
   python3 framework/ovi/compute.py --from-events --window-days 7
   ```

If all checks pass: the Cabinet is deployed.

## Troubleshooting

| Symptom | Diagnosis | Fix |
|---|---|---|
| Officer keeps restarting (`ThrottleInterval` cycles) | Crash on boot — check `~/Library/Logs/cabinet/officer-<slug>.log` | Usually missing env var (e.g. `TELEGRAM_BOT_TOKEN`) — fix `.env`, `launchctl unload + load` |
| TCC permission re-prompt after reboot | Code-signing not in effect | Re-run step 6.2 + 6.3; check `codesign -dv $(which claude)` shows your identity |
| OVI snapshot returns all zeros | Event ledger empty (no work yet) | Expected on cold start; populates as officers work |
| Tailscale SSH refuses connection | Tailscale not started on Mac Mini | `tailscale up`; check status with `tailscale status` |
| Redis trigger delivery silent | `REDIS_HOST` not set to `127.0.0.1` | Officer env or hook missing default; check `.env` and Phase 3 hooks |
| `cabinet-doctor.sh` reports a service missing or unexpected | `deploy-mac.sh` skipped/failed, or a legacy/diagnostic plist is still installed | Re-run exact `deploy-mac.sh --all`; inspect the named label and parked `.plist.disabled` evidence |

## Captain-readable summary

After deployment, the Captain sees:

- Telegram DMs from officers — initially silent, then proactive as missions arrive
- Weekly OVI snapshot DM (every Monday 08:00)
- Briefing DMs at 07:00 + 19:00
- Daily cost summary DM
- Founder-action items in the morning briefing if any are overdue
- Role evolution + hat graduation + skill induction proposals as they're drafted

Captain authoritative inputs:
- `instance/config/outcomes.yml` — declare what the Cabinet should pursue
- Telegram DMs — clarify, ratify proposals, override
- `instance/roles/proposals/*.yml` — approve/reject by editing the file's `status:` field (or via the dashboard if `/governance` route is deployed)

The Cabinet handles the rest.
