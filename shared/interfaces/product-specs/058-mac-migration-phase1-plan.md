# Spec 058 — Mac Migration Phase 1 Plan (Mac Base Setup)

- **Version:** v1.2.1 (CRO/CoS stop-the-line: v1.2 code-signing fold was claimed in changelog but NEVER inserted into a checkpoint body — fold-claim-vs-execute miss; v1.2.1 actually lands it in Checkpoint 1.8)
- **Date:** 2026-05-22 (v1.0 23:02) → 2026-05-23 (v1.1 05:10 → v1.2 08:05) → 2026-05-24 (v1.2.1 08:30 UTC)
- **Author:** CoS drafted (autonomous per Captain msg 2605+2607); CPO authored v1.2.1 body fix (specs are CPO domain per cpo-owns-specs memory; CoS coordinated the stop-the-line)
- **Status:** READY for Captain execution. **Do NOT mark Phase 1 complete as the Phase-4 gate until Checkpoint 1.8 code-signing + reboot-persistence golden eval passes** (Captain directive via CoS 2026-05-24).

**v1.2.1 changelog — fold-claim-vs-execute fix (CRO stop-the-line + CoS verify + Captain briefed 2026-05-24):**
- **The miss:** v1.2 changelog claimed code-signing as "NEW Checkpoint 1.10" + an OS-update "sub-step in 1.8," but grep across checkpoint bodies 1.1-1.12 returned ZERO matches for code-sign/notarize. Checkpoint 1.10 was actually UPS/apcupsd; 1.8 had no sub-step. **Both v1.2 claims were changelog-only, never executed into the body.** Impact: Checkpoint 1.8 granted Accessibility to unsigned npm binaries → TCC grants evaporate on Mac restart → cua-driver re-prompts every launch (the F2 trap the fold was meant to prevent).
- **The fix:** Checkpoint 1.8 retitled + expanded to **"Code-sign + notarize officer binaries, THEN grant macOS permissions"** with Part A (Developer ID cert + codesign + xcrun notarytool, `dk.refslund.cabinet.officer.*` Bundle ID namespace), Part B (grant to SIGNED bundles), Part C (the line-15 OS-update TCC-cache-regression sub-step). Golden eval adds the **reboot → TCC-consent-persists-without-re-grant** F2 check. Checkpoint 1.11 reboot test cross-references it. Placement before 1.8-grant is technically required (sign first, then grant to signed identifier). No renumber → no cross-ref drift.
- **CTO substrate fix folded (hardened-runtime Node/V8 JIT trap):** Part A `codesign --options runtime` on the Node-based `claude` binary WITHOUT JIT entitlements crashes the process at launch. Added Part A step 3 (entitlements requirement: allow-jit + allow-unsigned-executable-memory + disable-library-validation) + step 4 per-binary signing (claude WITH entitlements; cua-driver/tmux WITHOUT; screenpipe pre-signed, don't re-wrap) + golden-eval JIT-crash launch check (codesign --verify does NOT catch this). CTO owns authoring `cabinet/launchd/officer-entitlements.plist` at 1.8 execution (it's the build).
- **Cross-spec:** Spec 059 reload-officer-mac.sh creation gap (061-B) fixed — new Checkpoint 2.9b.
- **LaunchAgent Label namespace — INTENTIONALLY KEPT `com.cabinet.officer.*` (CTO technical correction):** an earlier draft of this changelog claimed it would realign 059's Label to `dk.refslund.cabinet.officer.*` "for TCC attribution" — that was mistaken. macOS TCC keys consent to the binary's **code-signing identifier** (+ responsible-process chain), NOT the launchd job Label; the two are orthogonal namespaces. 058 1.8 signs the binaries as `dk.refslund.cabinet.officer.*` (what TCC actually uses — already correct). Renaming the launchd Label would churn already-SHIPPED code (start-officer-mac.sh + deploy-mac.sh + worktree-listener, commits 28a2143 + 5783274) for purely cosmetic consistency TCC doesn't require. Decision: launchd Label stays `com.cabinet.officer.*`; binary signing identifier is `dk.refslund.cabinet.officer.*`; they differ intentionally and that's fine. No 059 body change for this.
- **Lesson (logged CPO patterns.md P1):** grep-verify every changelog claim landed in the BODY before calling a fold done — claim ≠ execute.

**v1.2 changelog — CRO Finding F2 (Mac-native pre-staging brief 2026-05-23) [SUPERSEDED by v1.2.1 — folds below now live in Checkpoint 1.8 body]:**
- **(1) TCC code-signing trap (now folded into Checkpoint 1.8 Part A — v1.2 mis-labeled it "NEW Checkpoint 1.10" which was already UPS).** macOS Transparency-Consent-Control keys permissions to **code-signing identifier**, NOT binary path. Bare-name binaries (e.g. unsigned `claude` from npm) don't persist permissions across launches → customer Mac restart loses Accessibility/Screen-Recording consent → repeating permission prompts = install-first-impression disaster. Phase 4 cua-driver depends on this. Fix in Phase 1 BEFORE Phase 4 ships:
  - Apple Developer Program already enrolled (Captain msg 2576) — use that cert
  - Pre-flight: install `Developer ID Application` certificate via Apple Developer portal → import into Keychain
  - For each officer-spawning binary (Claude Code wrapper + cua-driver + tmux launcher), wrap into a code-signed app bundle with reverse-DNS Bundle ID (`dk.refslund.cabinet.officer.{cos,cto,cpo,cro,coo}`)
  - Notarize via `xcrun notarytool` (one-time per binary version)
  - Verify TCC permission persists across reboot before Phase 4
- **(2) macOS Sequoia → 26 Tahoe TCC cache regression (now folded into Checkpoint 1.8 Part C).** In-process caches don't invalidate when TCC DB rolls forward during OS update. Add officer-restart-on-OS-update protocol: cron-like LaunchAgent watching for `sw_vers -productVersion` change → reboot officers when major OS version bumps. Folds into Spec 064 Phase 7 observability later.
- **Predecessor:** v1.1 stands; v1.2 INTENDED to add code-signing + an 1.8 sub-step but the fold never reached the body (changelog-only) — v1.2.1 actually lands both in Checkpoint 1.8.
- **CRO trigger:** 2026-05-23 07:16 UTC pre-staging brief shared/interfaces/research-briefs/2026-05-23-mac-native-cabinet-pre-staging.md F2.

**v1.1 changelog — CTO 7 MUST-fold + 1 SHOULD-fold + 1 NIT findings absorbed (msg 2026-05-22 23:08 UTC):**

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

### Checkpoint 1.8 — Code-sign + notarize officer binaries, THEN grant macOS permissions

> **v1.2.1 fix:** v1.2 changelog claimed code-signing as "NEW Checkpoint 1.10" + an OS-update sub-step in 1.8, but **neither landed in any checkpoint body** (1.10 was UPS; 1.8 had no sub-step). This checkpoint folds both in. Sign-first-then-grant is the technically-correct order — see Why below.

**Why this order (CRO F2 TCC code-signing trap):** macOS TCC keys Accessibility/Screen-Recording/Full-Disk consent to the binary's **code-signing identifier**, NOT its path. Granting permissions to unsigned bare-name binaries (npm `claude`, brew `tmux`, `cua-driver`) means consent **evaporates on the next Mac restart** → repeating permission prompts → install-first-impression disaster + Phase 4 cua-driver breaks every launch. So: **sign first, then grant to the signed bundles.**

- **Pre-conditions:** cua-driver (1.6) + Screenpipe (1.7) + claude CLI + tmux (1.4) installed; Apple Developer Program enrolled (Captain msg 2576); Terminal app in use.

- **Part A — Establish Developer ID cert + code-sign + notarize:**
  1. Install `Developer ID Application` certificate from the Apple Developer portal → import into login Keychain. Verify: `security find-identity -v -p codesigning` lists the Developer ID Application identity.
  2. For each officer-spawning binary (claude wrapper, cua-driver, tmux launcher), wrap into a code-signed app bundle with a reverse-DNS Bundle ID under the **`dk.refslund.cabinet.officer.*`** namespace. (Per-officer Bundle IDs `dk.refslund.cabinet.officer.{cos,cto,cpo,cro,coo}` are wired to per-officer LaunchAgents in Phase 2 / Spec 059; Phase 1 establishes the cert + signs the shared binary set under this namespace so TCC attribution is stable.)
  3. **JIT entitlements for the Node-based `claude` binary (CTO substrate fix — hardened-runtime Node/V8 trap):** `claude` is Node/V8 and JIT-compiles JS at runtime, which needs writable+executable memory that `--options runtime` (hardened runtime) BLOCKS by default → **signing `claude` under hardened runtime WITHOUT JIT entitlements crashes the process at launch/first-JIT** (the classic Electron/Node notarization trap — would bite Captain mid-Phase-1, the exact "install first impression" the F2 fold protects). CTO authors `cabinet/launchd/officer-entitlements.plist` at execution time (it's the build) with at minimum:
     - `com.apple.security.cs.allow-jit = true`
     - `com.apple.security.cs.allow-unsigned-executable-memory = true`
     - `com.apple.security.cs.disable-library-validation = true` (needed if claude loads native node modules / MCP native deps signed by a different team)
  4. Sign **per binary, with entitlements applied ONLY to the Node bundle:**
     ```bash
     # claude (Node/V8) — WITH JIT entitlements:
     codesign --force --options runtime \
       --entitlements cabinet/launchd/officer-entitlements.plist \
       --sign "Developer ID Application: <Name> (<TeamID>)" \
       --identifier "dk.refslund.cabinet.officer.<role-or-base>" <path-to-claude-bundle>

     # cua-driver (Rust/Swift native) + tmux (C) — NO JIT entitlements needed:
     codesign --force --options runtime \
       --sign "Developer ID Application: <Name> (<TeamID>)" \
       --identifier "dk.refslund.cabinet.officer.<role-or-base>" <path-to-cua-driver-or-tmux>

     # screenpipe — ships PRE-SIGNED by its vendor; DO NOT re-wrap/re-sign.

     codesign --verify --verbose <path>   # each must report "satisfies its Designated Requirement"
     ```
  5. Notarize via `xcrun notarytool` (one-time per binary version), then staple:
     ```bash
     xcrun notarytool submit <bundle.zip> --apple-id <id> --team-id <TeamID> \
       --password <app-specific-pw> --wait
     xcrun stapler staple <bundle>
     ```

- **Part B — Grant macOS permissions to the SIGNED bundles** (System Settings → Privacy & Security; grant up-front rather than waiting for per-invocation prompts):
  1. **Full Disk Access:** Terminal, signed-claude, signed-cua-driver, screenpipe
  2. **Screen Recording:** Terminal, signed-claude, signed-cua-driver, screenpipe
  3. **Accessibility:** Terminal, signed-claude, signed-cua-driver, screenpipe

- **Part C — OS-update TCC-cache-regression protocol (v1.2 changelog line 15 sub-step, now folded into body):** macOS Sequoia→26 Tahoe (and similar major OS updates) roll the TCC DB forward **without invalidating in-process caches** → long-running officers see stale TCC state → calls fail silently. Install a LaunchAgent watching `sw_vers -productVersion`; on major-version change, restart officers. Phase 1 installs the watcher stub + documents the requirement; full implementation folds into Spec 064 Phase 7 observability.

- **Golden eval:**
  - `security find-identity -v -p codesigning` shows the Developer ID Application identity
  - `codesign --verify --verbose` passes for each signed binary; `spctl --assess --type execute` accepts the notarized bundle
  - **JIT-crash check (CTO):** signed `claude --version` (or a trivial `claude` invocation) actually LAUNCHES without crashing. `codesign --verify` passing is NOT sufficient — the hardened-runtime JIT crash happens at process launch, not at verify. If `claude` crashes here, the JIT entitlements (Part A step 3) are missing/wrong.
  - `cua-driver mcp --claude-code-computer-use-compat` runs briefly (Ctrl-C to exit) without permission error
  - `screenpipe search --query "test" --limit 1` returns without permission error
  - **F2 persistence check (the whole point):** reboot the Mac → re-run the cua-driver + screenpipe checks → **TCC consent intact WITHOUT re-granting.** If a re-prompt appears, signing/attribution is wrong — do not proceed to Phase 4.
- **Rollback:** revoke permissions in System Settings; remove signed bundles (re-sign from source). Notarization submissions are idempotent.
- **Effort:** 45-90 min (cert import + per-binary sign + notarize round-trip is the long pole; notarization can take 5-15 min per submission).

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
  5. **TCC-persistence re-check (Checkpoint 1.8 F2 gate):** post-reboot, re-run `cua-driver mcp --claude-code-computer-use-compat` (briefly) + `screenpipe search --query "test" --limit 1` — both must succeed WITHOUT any re-grant prompt. A re-prompt here = code-signing/TCC attribution is broken; **Phase 1 is NOT complete and Phase 4 must not start** until resolved.
- **Golden eval:** All binaries return valid versions; Redis pings; UPS reports; Mac boots into desktop unattended after reboot; **TCC consent persists across reboot with zero re-grant prompts (the F2 gate).**
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
