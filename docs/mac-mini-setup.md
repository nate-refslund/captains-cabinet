# Mac Mini Setup Runbook — Phase 1 + Phase 2

End-to-end runbook for setting up a fresh Mac mini to run Captain's Cabinet natively. Consolidates Spec 058 v1.2 (Phase 1 unbox + base install) + Spec 059 v1.1 (Phase 2 native launchd Cabinet).

**Audience:** Captain hands-on for Phase 1 (most steps need the Mac physically); CoS executes Phase 2 once Phase 1 PASSES.

**Estimated time:** Phase 1 ~3-4 hours focused, Phase 2 ~2-3 hours focused. Total day for a clean run + soak check.

---

## Phase 1 — Base Mac setup (Spec 058 v1.2)

### Checkpoint 1.1 — Unbox + initial macOS setup (~15 min, Captain hands-on)

1. Unbox the Mac mini, connect power + display + keyboard + Ethernet
2. Power on, complete initial macOS setup wizard:
   - User account: create a non-iCloud admin user named `cabinet` (or your preferred name — `USER` env will read this)
   - Set timezone to `Europe/Berlin` (or your zone)
   - Skip Apple ID sign-in (or sign in if you want App Store access; not required for Cabinet)
   - Skip Siri setup
3. Verify the Mac boots to desktop without issues

### Checkpoint 1.2 — FileVault disable (~5 min, Captain hands-on)

Per Captain msg 2603 Q1: STEP-internal deployment, GDPR posture deferred to commercial Cabinet substrate.

```bash
# System Settings → Privacy & Security → FileVault → Turn Off
# (No CLI equivalent for disabling — must be done in UI)
# Verify:
fdesetup status   # should say "FileVault is Off"
```

### Checkpoint 1.3 — Power management (`pmset`) (~2 min)

```bash
# Prevent sleep; cabinet officers + LaunchAgents must stay alive 24/7
sudo pmset -a sleep 0
sudo pmset -a disksleep 0
sudo pmset -a displaysleep 30   # display can sleep; system can't
# Verify
pmset -g
```

### Checkpoint 1.4 — Homebrew + CLI install (~30 min)

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# CRITICAL — node FIRST (required for npm-installed Claude Code + neonctl)
# gettext provides envsubst (used by deploy-mac.sh for plist template substitution)
brew install node gh jq tailscale postgresql@17 redis screenpipe apcupsd gettext

# postgresql@17 is keg-only; ensure PATH:
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
pg_dump --version  # must show 17.x — if 16.x wins, fix PATH

# npm-installed tools (per Spec 058 v1.1 CTO #1 + #3)
npm install -g @anthropic-ai/claude-code neonctl

# Python — system Python3 is fine; psycopg2 needed for worktree-listener.sh
# (Postgres NOTIFY consumer). Audit-fix 2026-05-23: bash psql -c "LISTEN..." can't
# stream NOTIFY payloads; need psycopg2 in the listener.
pip3 install --user psycopg2-binary

# gh authentication (needed BEFORE Checkpoint 1.6 cua-driver pinned-tag pull)
gh auth login   # follow prompts; pick HTTPS + browser OAuth
```

### Checkpoint 1.5 — Redis service start with AOF persistence (~5 min)

```bash
# Enable Redis AOF (append-only file) for durability across restarts
echo "appendonly yes" | sudo tee -a /opt/homebrew/etc/redis.conf
brew services start redis

# Verify
redis-cli ping   # should reply PONG
redis-cli CONFIG GET appendonly   # should show "yes"

# Reboot-survival test (optional but recommended):
# 1. redis-cli SET test-key "hello"
# 2. sudo reboot
# 3. After reboot: redis-cli GET test-key   # should still return "hello"
```

### Checkpoint 1.6 — cua-driver install (PINNED tag) (~10 min)

```bash
# Find the latest stable cua-driver release on GitHub
PINNED_TAG=$(gh release list --repo trycua/cua --limit 1 --json tagName --jq '.[0].tagName')
# Audit-fix 2026-05-23: pin file goes to /tmp here; Checkpoint 1.12 moves it
# into the cloned repo (the repo path doesn't exist yet at this checkpoint).
echo "$PINNED_TAG" > /tmp/cua-driver-version.txt

# Install via gh release download — match the pinned tag exactly
gh release download "$PINNED_TAG" --repo trycua/cua --pattern '*macOS*' --dir ~/Downloads/
# Move into /opt/homebrew/bin/ (or similar)
sudo mv ~/Downloads/cua-driver /opt/homebrew/bin/cua-driver
sudo chmod +x /opt/homebrew/bin/cua-driver
cua-driver --version
```

### Checkpoint 1.7 — Screenpipe install + initial config (~15 min)

```bash
# Screenpipe ships with its own LaunchAgent — register it
brew services start screenpipe
# Open the Screenpipe app, complete setup wizard
# Configure exclusions: 1Password, banking apps, personal email
# Configure retention: 30 days full / OCR-only beyond
```

### Checkpoint 1.8 — macOS permissions grant (~10 min, Captain hands-on)

System Settings → Privacy & Security:
- **Accessibility:** Allow `claude`, `cua-driver`, `screenpipe`, and the LaunchAgent-spawned officer binaries (per Spec 058 v1.2 Checkpoint 1.10 code-signing)
- **Screen Recording:** Allow `screenpipe` and `cua-driver`
- **Full Disk Access:** Allow `claude` and `cua-driver` (needed for ~/.claude/ + worktree paths)

These grants persist across launches ONLY if the binaries are code-signed (Checkpoint 1.10 below). Without code-signing, every Mac reboot loses these consents → cua-driver re-prompts forever.

Enable Remote Login (SSH):
```bash
sudo systemsetup -setremotelogin on
```

### Checkpoint 1.9 — Tailscale join (~5 min)

```bash
# Authenticate Tailscale (for remote access to the Mac)
sudo tailscale up --authkey=<your-auth-key>
# Verify
tailscale status
ssh cabinet@<this-mac-tailscale-name>   # from another machine should work
```

### Checkpoint 1.10 — TCC code-signing + notarization (CRITICAL, ~30-45 min)

Per Spec 058 v1.2 + CRO F2: without code-signing, TCC permissions don't persist across launches → repeated Accessibility prompts → install disaster. Mandatory before Phase 4 cua-driver work.

1. **Import Apple Developer Program certificate** (already enrolled per Captain msg 2576):
   - Apple Developer portal → Certificates → Download `Developer ID Application` cert
   - Double-click to import into Keychain
2. **Wrap each officer-spawning binary** into a code-signed app bundle with reverse-DNS Bundle ID (`dk.refslund.cabinet.officer.{cos,cto,cpo,cro,coo}`)
3. **Notarize** via `xcrun notarytool submit ...`
4. **Verify** TCC persistence: grant Accessibility → reboot Mac → verify grant still in place

(Full code-signing procedure tracked in a separate runbook — currently a stub pending the actual wrapper script work. The Apple Developer Program enrollment is the unblock; the code-signing tooling is straightforward once a cert is in Keychain.)

### Checkpoint 1.11 — apcupsd config (UPS-specific, ~10 min)

```bash
# /opt/homebrew/etc/apcupsd/apcupsd.conf (Apple Silicon Homebrew path)
sudo $EDITOR /opt/homebrew/etc/apcupsd/apcupsd.conf
# Configure UPSCABLE + UPSTYPE per your specific UPS model
brew services start apcupsd
# Test: pull the wall plug briefly; apcupsd should detect + log
```

### Checkpoint 1.12 — Phase 1 baseline + commit

```bash
# Clone repo
cd ~/work
gh repo clone nate-step/captains-cabinet
cd captains-cabinet
git checkout mac-native

# Restore captain-rules from Hetzner export tarball
tar -xzf ~/cabinet-import/host-state.tar.gz -C /tmp/cabinet-import
cp /tmp/cabinet-import/shared/interfaces/captain-*.md shared/interfaces/

# Move the Checkpoint 1.6 cua-driver pin into the repo (chicken-egg unblock)
mkdir -p cabinet/config
mv /tmp/cua-driver-version.txt cabinet/config/cua-driver-version.txt

# Verify Phase 1 baseline state
# (Smoke-test each tool installed in 1.4-1.11)
```

PASS Phase 1 → notify CoS (`bash cabinet/scripts/notify-officer.sh cos "Phase 1 PASS — ready for Phase 2"`). CoS takes Phase 2 from here.

---

## Phase 2 — Native launchd Cabinet (Spec 059 v1.1)

### What CoS does autonomously after Phase 1 PASS

0. **Run preflight checks:**
   ```bash
   bash cabinet/scripts/mac-preflight.sh
   bash cabinet/scripts/mac-tcc-gate.sh
   ```
1. **Edit `instance/config/product.yml`** (Phase 3 prep: collapse to Lead-only Telegram, voice-only-CoS)
2. **Substitute plist templates via envsubst:**
   ```bash
   for o in cos cto cpo cro coo; do
     OFFICER=$o USER=$(id -un) HOME=$HOME REPO_ROOT=~/work/captains-cabinet \
       envsubst < cabinet/launchd/com.cabinet.officer.template.plist \
       > ~/Library/LaunchAgents/com.cabinet.officer.$o.plist
   done
   ```
3. **Bootstrap CoS first** (verify the substrate works on one officer before all 5):
   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist
   bash cabinet/scripts/reload-officer-mac.sh cos  # smoke-test
   ```
4. **Bring up CTO + CPO + COO + CRO** per Phase 7 Spec 064 Checkpoints 7.1-7.3
5. **Register observability LaunchAgents** (heartbeat-watchdog + limit-reset-watchdog + cost-summary + worktree-listener)
6. **48h soak** under real workload (Phase 7 Checkpoint 7.8)
7. **Posture ruling (optional, Captain-only)** — a Mini that should run the
   sovereign posture needs the Captain ratification described in
   `docs/mac-mini-deploy-runbook.md` §4 step 5: edit + commit
   `instance/config/posture.yml` (+ empty `standing-grants.yml`), then
   `sudo bash cabinet/scripts/germline-lock.sh lock`. Skipping this leaves the
   deployment guardian (today's rules) — nothing else changes.
   *Axes (amendment 2026-07-05):* start from the shipped preset —
   `cp instance/config/posture-presets/org-macmini.yml instance/config/posture.yml`
   (axes `flavor: org` · `deployment_target: mac_mini` · schg attestation),
   set `deployment:` to this Mini's `CABINET_ID`, and add a `never_grant:`
   list if any ceiling class should be structurally non-grantable on this
   deployment. Downgrade is always instant and needs no unlock:
   `CABINET_POSTURE=guardian` env, or the Captain binder verb
   `posture guardian` (writes the narrow-only
   `instance/config/posture-narrow` cap). Upgrades happen ONLY via this
   lock ritual — no env var, dashboard, or chat verb can widen.

### Captain involvement during Phase 2-8

Mostly hands-off. Captain joins for:
- Phase 3 Checkpoint 3.1: BotFather revoke 4 officer bot tokens
- Phase 4 Checkpoint 4.6: Figma test (end-to-end cua-driver round-trip)
- Phase 7 Checkpoint 7.8 qualitative sign-off: "Cabinet on Mac felt as responsive as Hetzner"
- Phase 8 Checkpoint 8.5: Hetzner suspension (final docker stop)

---

## Stop-the-line gates

If any Phase 1 checkpoint fails, halt + investigate + fix before continuing. Common failure modes:
- 1.4 `pg_dump 16.x` wins → fix `~/.zprofile` PATH order
- 1.4 `envsubst: command not found` → `brew install gettext` (gettext is keg-only on Mac; may need PATH addition: `echo 'export PATH="/opt/homebrew/opt/gettext/bin:$PATH"' >> ~/.zprofile`)
- 1.5 Redis doesn't survive reboot → verify `appendonly yes` actually wrote to redis.conf
- 1.8 Accessibility prompt re-fires after reboot → 1.10 code-signing wasn't done (skip 1.10 and you'll be stuck in a loop)
- 1.9 Tailscale auth-key expired → generate a new one from the Tailscale admin console

## Per Spec 058 v1.2 + Spec 059 v1.1 — consolidated for Captain operational use.
