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
git clone https://github.com/nate-step/captains-cabinet.git
cd captains-cabinet
git checkout claude/convergence-v2    # OR master once this branch is merged
```

## 3. Cabinet bootstrap (orchestrator)

```bash
bash cabinet/scripts/setup-mac.sh
```

`setup-mac.sh` is the single interactive orchestrator. In order it: runs the
**API-key wizard** (Step 0 — `setup-env.sh`, which walks you through every
required + optional key, opens signup pages, masks paste input, and writes
`cabinet/.env` at `chmod 600` — no hand-editing), installs missing Homebrew
deps (tmux, jq, python3, redis), starts Redis (+ enables AOF), creates required
directories, bootstraps officer roles, installs the Captain-layer Mac tool
stack, launches the Cabinet Chrome (sign into Linear/Notion/etc. when it
opens), prompts for TCC grants, installs any declared extensions
(`instance/config/extensions.yml`), builds the dashboard, loads the preset,
verifies the policy engine, and runs the framework test suite. Idempotent.

Verify: `bash cabinet/scripts/setup-mac.sh --check` returns exit 0.

> The wizard already created `cabinet/.env`. To re-run it later (add/replace
> keys): `bash cabinet/scripts/setup-env.sh --force`. To bootstrap headless
> (CI/clone) and fill `.env` yourself: `SKIP_ENV_WIZARD=1 bash cabinet/scripts/setup-mac.sh`.

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

## 5. First product onboarding

```bash
bash cabinet/scripts/bootstrap-project.sh <repo-url> <slug>
# example: bash cabinet/scripts/bootstrap-project.sh https://github.com/your/app polads
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

```bash
CABINET_ROOT="$(pwd)" bash cabinet/scripts/deploy-mac.sh --all
```

This `envsubst`-substitutes paths into the plist templates in `cabinet/launchd/` and registers them in `~/Library/LaunchAgents/`:

- `com.cabinet.officer.<slug>.plist` (per officer)
- `com.cabinet.heartbeat-watchdog.plist`
- `com.cabinet.cost-summary.plist`
- `com.cabinet.worktree-listener.plist`
- `com.cabinet.mission-supervisor.plist`
- `com.cabinet.task-sync.plist`
- `com.cabinet.role-evals-weekly.plist`
- `com.cabinet.outbox-relay.plist`
- `com.cabinet.ovi-weekly.plist`
- `com.cabinet.self-improvement-loop.plist`
- `com.cabinet.chrome-profile.plist` (Captain-layer authenticated browser)
- `com.cabinet.dashboard.plist` (control panel + office-display server on `:3100`)

`com.cabinet.dashboard-kiosk.plist` is **opt-in** (needs a physical monitor) — deploy it separately on the office Mac mini:

```bash
bash cabinet/scripts/deploy-mac.sh --daemon dashboard-kiosk
```

Verify all registered + running:

```bash
bash cabinet/scripts/verify-launchagents.sh
```

Exit 0 = pass. Re-deploy if any fail.

> **Portfolio-preset note.** `deploy-mac.sh --all` registers the legacy `work`
> preset fleet (`cos cto cpo cro coo` + the daemon list above). The **portfolio**
> deployment (one persistent Chair `cos` + domain officers `comms-officer`,
> `polads-ceo`, `stephie-ceo`, plus the `com.cabinet.intake-surface`,
> `com.cabinet.frontdoor-briefing`, and `com.cabinet.officer-supervisor-mac`
> daemons) is registered by `cp`-ing each plist into `~/Library/LaunchAgents/`
> and `launchctl load -w`-ing it — the install commands are in each plist's
> header comment.

### 7.0a Officer self-wake (loop-prompts + supervisor)

Mac officers run as **separate** `officer-<role>` tmux sessions and only advance
when they take a tool action (the post-tool-use hook is what surfaces their
queued triggers + carded work). So each domain officer is given a durable
self-wake `/loop`:

- **Per-role loop prompt:** `cabinet/loop-prompts/<role>.txt` (gather-then-decide
  sweep — check triggers + intake + the lane's captain-attention backlog, do the
  next due lane step, surface to the Chair, never DM Nate). An officer with no
  prompt file (e.g. `cos`, the Chair) has no self-wake by design.
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
redis-cli -h localhost GET cabinet:heartbeat:polads-ceo
# the loop registered a cron (look for "Scheduled <id> (Every 5 minutes)")
tmux capture-pane -t officer-polads-ceo -p | grep -i scheduled
```

### 7.1 Interactive one-time steps (login / OAuth) `[CAPTAIN]`

Officers run unattended with full host shell access, so they self-install
plugins/MCPs via the `claude plugin` / `claude mcp` CLI. The only things they
*can't* do alone are inherently-interactive auth prompts — `gh auth login`
(needed once for private plugin marketplaces like STEP-Network/dev-tasks),
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
| **Filesystem** | `shared/interfaces/captain-*.md`, `instance/roles/active/*.yml`, `memory/skills/evolved/*.md`, `memory/experience_records/*.jsonl` | Daily `rsync` to local NAS OR S3 |
| **Redis** | Heartbeat, cost counters, trigger streams (ephemeral) | Optional `BGSAVE` daily snapshot if you want to recover pending triggers across a hard restart |

Backup script (run via cron or LaunchAgent — your choice):

```bash
#!/usr/bin/env bash
# ~/bin/cabinet-backup.sh
set -euo pipefail
DEST="${BACKUP_DEST:-/Volumes/NAS/cabinet-backups}"
DATE=$(date +%Y-%m-%d)
mkdir -p "$DEST"

# Postgres (if you operate a self-hosted DB; skip if using Neon)
# pg_dump $DATABASE_URL | gzip > "$DEST/postgres-$DATE.sql.gz"

# Filesystem (Cabinet artifacts only — the .git tree is in GitHub)
rsync -a --delete \
  ~/work/captains-cabinet/shared/interfaces/ \
  ~/work/captains-cabinet/instance/ \
  ~/work/captains-cabinet/memory/skills/evolved/ \
  ~/work/captains-cabinet/memory/experience_records/ \
  "$DEST/$DATE/"

# Redis (optional)
redis-cli SAVE  # synchronous; or BGSAVE for async
cp /opt/homebrew/var/db/redis/dump.rdb "$DEST/redis-$DATE.rdb"
```

Schedule via launchd (per `cabinet/launchd/com.cabinet.cost-summary.template.plist` as a template for crontab-style timing).

## 11. Verification — 72h soak

After everything is in place:

1. Start a representative outcome:
   ```bash
   cat >> instance/config/outcomes.yml <<'EOF'
   - id: outcome-soak-001
     name: 72-hour readiness test
     description: Continuous Cabinet operation with mission execution + OVI tracking
     measurable_criteria:
       - Officers respond to Captain DMs within 5 min
       - Mission supervisor routes ready tasks every 5 min
       - OVI snapshot fires Monday 08:00 with non-zero data
       - No officer process exits abnormally for 72 hours
     status: active
     captain_ratified: true
   EOF
   ```
2. Verify all officers running:
   ```bash
   bash cabinet/scripts/verify-launchagents.sh
   ```
3. Verify mission flow:
   ```bash
   bash cabinet/cron/mission-supervisor.sh --dry-run --json
   ```
4. Send a test Captain DM via Telegram → verify your officer replies + voice fires (if enabled).
5. Force-kill an officer: `pkill -9 -f 'claude.*officer.cos'` → supervisor should restart within 30s.
6. Power-cycle the Mac → all officers should come back up automatically; Captain should receive a "Cabinet is back online" DM.
7. Wait 72 hours. Re-run verify-launchagents.sh + check OVI snapshot count via:
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
| `verify-launchagents.sh` shows agent missing | `deploy-mac.sh` skipped or failed | Re-run deploy; check `launchctl bootstrap gui/$(id -u) <plist>` directly |

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
