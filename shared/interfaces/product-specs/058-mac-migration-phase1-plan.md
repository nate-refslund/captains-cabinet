# Spec 058 — Mac Migration Phase 1 Plan (Mac Base Setup)

- **Version:** v1.1 (CTO tech review folded — install mechanics corrected)
- **Date:** 2026-05-22 (v1.0 23:02 UTC) → 2026-05-23 (v1.1 05:10 UTC)
- **Author:** CoS (autonomous per Captain msg 2605+2607)
- **Status:** READY for Captain execution (v1.0 had bugs CTO caught — DO NOT execute v1.0 against the Mac)

**v1.1 changelog — CTO 7 MUST-fold + 1 SHOULD-fold + 1 NIT findings absorbed (msg 2026-05-22 23:08 UTC):**
- **(1) `claude-code` NOT a Homebrew formula.** Anthropic distributes via npm. Checkpoint 1.4 swapped: `npm install -g @anthropic-ai/claude-code`. Node prerequisite added (#4).
- **(2) `postgresql@17` is keg-only.** Added PATH export to `~/.zprofile` + explicit `pg_dump --version` verification ensuring 17.x not 16.x wins.
- **(3) `neonctl` is npm-only**, not Homebrew. Moved to `npm install -g neonctl` after node.
- **(4) `node` added** to 1.4 brew formula list (prerequisite for #1 + #3).
- **(5) macOS Remote Login (SSH) off by default.** New sub-step in 1.9 enables `sudo systemsetup -setremotelogin on` BEFORE Tailscale SSH verification.
- **(6) Redis durability.** New sub-step in 1.5 enables `appendonly yes` in `/opt/homebrew/etc/redis.conf` for AOF persistence; reboot test verifies survival.
- **(7) `apcupsd` macOS path clarified.** Homebrew formula; alternative `nut` if UPS doesn't enumerate.
- **(SHOULD-fold) gh auth ordering.** `gh auth login` moved into 1.4 right after `brew install gh` since 1.6 cua-driver pin uses `gh release list`.
- **(NIT) permission-grant simplification.** Held — over-up-front grants vs trigger-by-app is fine.
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 1
- **Predecessor:** Spec 057 (Phase 0 plan) — COMPLETE 2026-05-22 22:59 UTC
- **Spec class:** Migration phase plan
- **Execution mode:** Hands-on Captain. The Mac mini is in front of you; CoS provides the runbook + verification gates but cannot execute most steps remotely.

---

## 1. Phase 1 goal (from directive)

A Mac mini that boots into the desktop unattended after a power cycle, with all binaries installed and permissioned, ready for Phase 2's LaunchAgent layer.

## 2. Inputs from Phase 0

- `v1-hetzner-docker` tag at master HEAD 4e1a01a (recovery anchor)
- `mac-native` branch on GitHub (Phase 1 onwards commits land here)
- Phase 0 baseline numbers in `docs/migration-phase0-baseline.md`
- Phase 0 deferred items waiting on Phase 1 tooling:
  - pg17 client install → enables Phase 0.2 full pg_dump + Phase 0.3 round-trip restore
  - neonctl install → enables Phase 0.3 round-trip restore
  - BGSAVE not SAVE for Redis dump per CTO #2
  - cua-driver version pin per CoS critical-analysis residual

## 3. Captain ratifications carried forward (msg 2603)

- FileVault: DISABLE (STEP-internal deployment)
- Personal Cabinet: NOT in scope
- 1-then-clone-to-3 fleet model: this Mac is the first; cloning to 3 others comes as separate directive after Phase 8 stable
- Cost-tracking infrastructure: STAYS, alert thresholds OFF (per `cabinet/officer-capabilities.conf` cost flags)
- Full native: no Docker

## 4. Checkpoint structure

Phase 1 decomposes into **10 checkpoints**. Most need Captain's hands at the Mac; CoS provides golden eval verification steps after each. Stop-the-line gates explicit. Effort estimate: 4-6 hours of focused setup, spread however convenient.

### Checkpoint 1.1 — Unbox + initial macOS setup

- **Pre-conditions:** Mac mini M4 Pro (32 GB unified, 1 TB SSD) unboxed; monitor connected; Ethernet ready (wired, not Wi-Fi-only).
- **Actions:**
  1. Connect Mac mini → monitor + Ethernet + power (no UPS yet — that's 1.10)
  2. Boot → setup wizard → create single user account (suggest username `cabinet` or `naref`)
  3. Enable auto-login: System Settings → Users & Groups → user → "Login automatically"
  4. Accept default macOS region/keyboard; skip Apple ID for now (we don't need iCloud per Q5 + H5 ratification)
- **Golden eval:**
  - Boots into desktop after `sudo reboot` without password prompt
  - `whoami` returns expected username
  - `uname -m` returns `arm64` (Apple Silicon)
- **Rollback:** factory reset Mac (system-level rollback)
- **Effort:** 30-45 min.

### Checkpoint 1.2 — Disable FileVault (per Captain Q1 msg 2603)

- **Pre-conditions:** logged in as the new user
- **Actions:**
  1. System Settings → Privacy & Security → FileVault → "Turn Off…"
  2. Wait for decryption (depends on disk usage; SSD is fast)
- **Golden eval:** `fdesetup status` returns `FileVault is Off.`
- **Rollback:** Re-enable FileVault from same settings; decryption is reversible.
- **Effort:** 5 min for command; decryption runs in background.
- **Captain note:** For commercial Cabinet customers in EU, this MUST be reversed. Stripe `commercial-cabinet-installer` documents FileVault as required. Internal STEP fleet is the exception.

### Checkpoint 1.3 — Power management for headless reliability

- **Pre-conditions:** logged in.
- **Actions:**
  ```bash
  sudo pmset -a sleep 0 displaysleep 0 disksleep 0
  sudo pmset -a powernap 0
  sudo pmset -a autorestart 1
  sudo pmset -a wake_on_lan 1
  ```
- **Golden eval:** `pmset -g | grep -E '(sleep|powernap|autorestart|wake_on_lan)'` shows all expected values (sleep=0, autorestart=1, etc.)
- **Rollback:** `sudo pmset -a sleep 1 displaysleep 10 disksleep 10 powernap 1 autorestart 0 wake_on_lan 0` restores defaults.
- **Effort:** 2 min.

### Checkpoint 1.4 — Install Homebrew + core CLI tools (v1.1 CTO fold)

- **Pre-conditions:** power management set; Ethernet active.
- **Actions:**
  1. Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  2. Add brew to PATH per installer instructions (run the two lines the installer prints, typically appending to `~/.zprofile` and `eval`-ing `shellenv`).
  3. Install Homebrew CLIs:
     ```bash
     brew install node redis restic cloudflared tmux jq git gh
     brew install postgresql@17
     brew install --cask tailscale
     # postgresql@17 is keg-only (CTO #2) — add to PATH explicitly
     echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zprofile
     source ~/.zprofile
     ```
  4. Authenticate `gh` BEFORE 1.6 (CTO SHOULD-fold — 1.6 cua-driver pin uses `gh release list`):
     ```bash
     gh auth login --git-protocol https --web
     ```
  5. Install npm-distributed CLIs (CTO #1 + #3 — these are NOT Homebrew formulas):
     ```bash
     npm install -g @anthropic-ai/claude-code
     npm install -g neonctl
     ```
- **Golden eval:**
  - `which claude && claude --version` returns ≥2.1.119 (path under npm global, NOT brew)
  - `which pg_dump && pg_dump --version` returns 17.x with path under `/opt/homebrew/opt/postgresql@17/bin/` (CRITICAL — if it shows 16.x, the PATH didn't apply; re-source `~/.zprofile`)
  - `which neonctl && neonctl --version` returns (path under npm global)
  - `redis-cli --version` returns ≥7.x
  - `restic version` returns
  - `cloudflared --version` returns
  - `tmux -V` returns
  - `gh auth status` shows logged-in state
  - `jq --version`, `git --version`, `node --version`, `npm --version` return
- **Rollback:** `brew uninstall <pkg>` for brew-installed; `npm uninstall -g @anthropic-ai/claude-code neonctl` for npm-installed; full Homebrew uninstall documented at brew.sh.
- **Effort:** 30-45 min (download-speed bound).
- **CTO v1.1 #1+#2+#3+#4 + gh ordering — all folded above.**

### Checkpoint 1.5 — Start Redis as service with durability (v1.1 CTO #6 fold)

- **Pre-conditions:** redis installed.
- **Actions:**
  1. Enable AOF persistence — Cabinet state would be lost on reboot without this (CTO #6):
     ```bash
     CONFIG=/opt/homebrew/etc/redis.conf
     cp "$CONFIG" "$CONFIG.default"   # backup
     sed -i '' 's/^appendonly no$/appendonly yes/' "$CONFIG"
     sed -i '' 's/^# appendfsync everysec$/appendfsync everysec/' "$CONFIG" 2>/dev/null || true
     grep -E '^appendonly|^appendfsync' "$CONFIG"  # verify
     ```
  2. `brew services start redis`
- **Golden eval:**
  - `redis-cli ping` returns `PONG`
  - `brew services list | grep redis` shows `started`
  - `redis-cli CONFIG GET appendonly` returns `appendonly yes`
  - Survives-reboot test:
    ```bash
    redis-cli SET migration:phase1:1.5:test "before-reboot"
    sudo reboot
    # After auto-login:
    redis-cli GET migration:phase1:1.5:test  # must return "before-reboot"
    redis-cli DEL migration:phase1:1.5:test
    ```
- **Rollback:** `brew services stop redis`; restore config from `$CONFIG.default`.
- **Effort:** 10 min + reboot test.

### Checkpoint 1.6 — Install cua-driver (PINNED VERSION per CoS critical-analysis #7)

- **Pre-conditions:** Homebrew + brew CLIs installed.
- **Actions:**
  1. **DO NOT** use the curl-bash one-liner from the directive blindly. Instead pin to a specific commit SHA or release tag:
     ```bash
     # Resolve the latest stable release tag
     LATEST_TAG=$(gh release list --repo trycua/cua --limit 1 --json tagName --jq '.[0].tagName')
     echo "Pinning to tag: $LATEST_TAG"
     # Install pinning to that tag
     CUA_DRIVER_VERSION="$LATEST_TAG" /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/$LATEST_TAG/libs/cua-driver/scripts/install.sh)"
     ```
  2. Record the pinned version in `cabinet/config/cua-driver-version.txt` for repeatability + doc reference.
- **Golden eval:**
  - `cua-driver --version` returns the pinned tag
  - `cabinet/config/cua-driver-version.txt` exists in repo (commit after Phase 4 wires it in)
- **Rollback:** uninstall cua-driver via its install-script's `uninstall.sh` or manual binary removal.
- **Effort:** 15-30 min depending on cua-driver's install dependencies.
- **Captain note:** cua-driver uses Apple private SkyLight SPIs (per directive Risk #1). Any macOS upgrade is a potential break — hold off on macOS upgrades until tested.

### Checkpoint 1.7 — Install Screenpipe

- **Pre-conditions:** macOS configured + Homebrew installed.
- **Actions:**
  1. Download the macOS app installer from https://screenpi.pe (the .dmg)
  2. Drag to /Applications
  3. Launch once to trigger first-run permission prompts
  4. The Screenpipe app installs its own LaunchAgent automatically; verify with `launchctl list | grep -i screenpipe`
- **Golden eval:**
  - Screenpipe app launches without crash
  - `launchctl list | grep -i screenpipe` shows running LaunchAgent
  - Disk usage starts accumulating in `~/.screenpipe/` (let it run a few minutes)
- **Rollback:** Quit app, remove LaunchAgent, delete app + `~/.screenpipe/`.
- **Effort:** 10-15 min.

### Checkpoint 1.8 — Grant macOS permissions

- **Pre-conditions:** cua-driver + Screenpipe + claude CLI installed; Terminal app in use.
- **Actions:** System Settings → Privacy & Security → grant the following to Terminal, claude, cua-driver, screenpipe (you'll be prompted by each on first invocation; faster to grant up-front):
  1. **Full Disk Access:** Terminal, claude, cua-driver, screenpipe
  2. **Screen Recording:** Terminal, claude, cua-driver, screenpipe
  3. **Accessibility:** Terminal, claude, cua-driver, screenpipe
- **Golden eval:**
  - Run `cua-driver mcp --claude-code-computer-use-compat` briefly (Ctrl-C to exit); should NOT error about missing permissions
  - Run `screenpipe search --query "test" --limit 1` from CLI; should return without permission error
- **Rollback:** Revoke individually in System Settings.
- **Effort:** 10-15 min.

### Checkpoint 1.9 — Tailscale for remote access (v1.1 CTO #5 — enable SSH first)

- **Pre-conditions:** Tailscale cask installed.
- **Actions:**
  1. **Enable macOS Remote Login** — off by default per CTO #5, blocks the SSH verification step:
     ```bash
     sudo systemsetup -setremotelogin on
     sudo systemsetup -getremotelogin  # verify "Remote Login: On"
     ```
  2. Launch Tailscale app
  3. Sign in with your Tailscale account
  4. Approve the Mac mini in Tailscale admin console
- **Golden eval:**
  - `sudo systemsetup -getremotelogin` returns "On"
  - `tailscale status` shows the Mac mini IP
  - From another device on your Tailnet: `ssh <user>@<mac-tailscale-ip>` connects (the SSH verification CTO #5 unblocks)
  - CoS can SSH from the Hetzner-side Cabinet via Tailscale to run remaining golden evals (post-1.9 verification automation)
- **Rollback:** `sudo systemsetup -setremotelogin off`; Tailscale logout from app.
- **Effort:** 10-15 min.

### Checkpoint 1.10 — UPS + apcupsd/NUT for graceful shutdown

- **Pre-conditions:** UPS device on hand; Mac mini + monitor plugged into UPS; UPS USB cable plugged into Mac.
- **Actions:**
  1. Identify UPS model — most APC + CyberPower UPSes work with apcupsd or NUT
  2. Install: `brew install apcupsd` (or `brew install nut` for NUT, depending on UPS)
  3. Configure `/opt/homebrew/etc/apcupsd/apcupsd.conf` per UPS docs (Apple Silicon Homebrew path; CTO v1.1.1 fix — Linux uses `/etc/apcupsd/` but macOS Homebrew installs to `/opt/homebrew/etc/`)
  4. Start service: `sudo apcupsd` or via launchd
  5. Test: `apcaccess` reports UPS status
- **Golden eval:**
  - `apcaccess status` shows UPS online + battery level
  - Pull power on UPS for 1 minute; verify apcupsd writes status change
- **Rollback:** `brew uninstall apcupsd`; remove launchd config.
- **Effort:** 30-45 min.

### Checkpoint 1.11 — Verify binaries + final smoke test

- **Pre-conditions:** all prior checkpoints PASS.
- **Actions:**
  1. Run verification matrix:
     ```bash
     for cmd in claude redis-cli pg_dump neonctl cua-driver restic cloudflared tailscale tmux jq gh git; do
       which $cmd && $cmd --version 2>&1 | head -1
     done
     ```
  2. Test Redis: `redis-cli ping`
  3. Test apcupsd: `apcaccess status | head -5`
  4. Reboot the Mac with `sudo reboot`. After reboot, log in (auto-login should fire) and re-run the verification matrix without re-installing anything.
- **Golden eval:** All binaries return valid versions; Redis pings; UPS reports; Mac boots into desktop unattended after reboot.
- **Rollback:** per-checkpoint rollback paths above; or factory reset Mac.
- **Effort:** 15 min including reboot.

### Checkpoint 1.12 — Phase 1 baseline doc on mac-native branch

- **Pre-conditions:** 1.1-1.11 PASS.
- **Actions:**
  1. From Mac mini: `git clone <repo> ~/work/captains-cabinet && cd ~/work/captains-cabinet && git checkout mac-native`
  2. Write `docs/migration-phase1-baseline.md` capturing:
     - macOS version (`sw_vers`)
     - Mac hardware (`system_profiler SPHardwareDataType | head -20`)
     - Homebrew pkg versions for all 10 installed tools
     - cua-driver pinned tag
     - Screenpipe app version
     - Tailscale tailnet IP
     - UPS model + apcupsd version
     - List of granted permissions per app
  3. Commit + push to `mac-native`
- **Golden eval:** baseline doc exists on `mac-native` GitHub branch.
- **Effort:** 20 min.

## 5. Effort estimate (whole Phase 1)

**Realistic: 4-6 hours of focused setup.** Most checkpoints are 5-30 min individually; the long-tail is Homebrew install (1.4) + cua-driver pin (1.6) + UPS config (1.10).

Phase 1 is mostly hands-on with the Mac in front of you. CoS verifies golden evals after each by SSH-ing in via Tailscale (post-1.9) and running the eval commands.

## 6. Stop-the-line gates

Halt + ping CoS if any of these hit:

1. **Homebrew install fails on Apple Silicon.** Rare but real if Apple changed install path.
2. **cua-driver install fails / no recent tagged release.** Need to decide between pinning to a commit SHA vs accepting the curl-bash unpinned install. Captain decision.
3. **pg17 install on Apple Silicon errors** (e.g., on architecture mismatch). Usually `brew install postgresql@17 --build-from-source` resolves.
4. **Screenpipe permission prompts fail to fire** (we've seen this on macOS 26.x in screenpipe forums). Manual permission grant via System Settings, then re-launch.
5. **UPS not detected by apcupsd.** Some UPSes need NUT instead. Switch to `brew install nut`.

## 7. Phase 1 → Phase 2 handoff

When Phase 1 completes successfully:
- Mac mini boots unattended after power cycle ✅
- All 10 CLI binaries + 2 apps installed and permissioned
- Tailscale active (CoS can SSH from elsewhere if needed)
- UPS protecting graceful shutdown
- `docs/migration-phase1-baseline.md` on `mac-native`
- Phase 0 deferred items NOW UNBLOCKED (pg17 + neonctl available; can run full Phase 0.2 + 0.3 from Mac side)
- Captain DMs CoS: "Phase 1 complete, ready for Phase 2"

## 8. Open items folded forward

- Phase 0.2 full pg_dump + Phase 0.3 round-trip restore test: execute on Mac-side after 1.4 (pg17) + 1.4 (neonctl).
- Phase 0.4 BGSAVE Redis dump: re-run when Mac Redis is up.
- Phase 0.6 host-state tarball: still gated on Hetzner host-agent restart.
- cua-driver pinned version: committed in 1.6, referenced in Phase 4 + Phase 8 constitution.

## 9. Sign-off

This Phase 1 plan is **DRAFT, ready for Captain execution.** Captain runs the checkpoints in sequence at the Mac; CoS verifies golden evals via Tailscale post-1.9 (or via Captain pasting outputs to Telegram). Estimated wall time: 4-6 hours focused, or one weekend afternoon.

---

**Captain decision queue entry:**

> Execute Phase 1 (Mac base setup) per Spec 058? Captain hands-on work; CoS verifies golden evals. Estimated 4-6 hours focused. No further ratification needed — proceeding under blanket autonomy grant msg 2605.
