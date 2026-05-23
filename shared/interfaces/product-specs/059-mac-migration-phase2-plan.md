# Spec 059 — Mac Migration Phase 2 Plan (Delete Docker, Add launchd)

- **Version:** v1.0
- **Date:** 2026-05-23
- **Author:** CoS (autonomous per Captain msg 2605, msg 2607 "Go", msg 2612 "never stop")
- **Status:** DRAFT — ready for CTO tech review + Captain execution
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 2 ("Delete Docker, add launchd — 1-2 days")
- **Predecessors:** Spec 057 (Phase 0 — COMPLETE 2026-05-22 22:59 UTC), Spec 058 v1.1.1 (Phase 1 — READY for Captain execution)
- **Successor:** Spec 060 (Phase 3 — Telegram topology collapse)

---

## 1. Phase 2 goal (from directive)

CoS officer running as a LaunchAgent on the Mac, surviving crashes, restartable cleanly. Docker substrate removed from the Customer-Mac tier. Cost-tracking infrastructure preserved (Captain Q4) but alert thresholds gated off for personal/STEP-internal use.

## 2. Inputs from Phase 1

- All 12 Phase 1 checkpoints PASS (Mac base setup complete with binaries + permissions)
- `docs/migration-phase1-baseline.md` on `mac-native` branch
- Tailscale active (CoS can SSH-verify golden evals from Hetzner side)
- pg17 + neonctl installed → Phase 0.2 + 0.3 deferred work can complete in this phase too
- Mac Migration deferred items: full pg_dump + Neon round-trip restore test, BGSAVE Redis dump

## 3. Captain ratifications carried forward

- **Q4 (msg 2603):** cost-tracking infrastructure STAYS, alert thresholds OFF for personal/STEP-internal use. Translation for this phase: do NOT delete the cost-tracking module — gate it behind `platform.yml → cost_tracking.enabled` flag (default `false` for personal/STEP fleet, default `true` for commercial Cabinet customers per Spec 050 v1.2.1).
- **Q5 (msg 2603):** Full native — no Docker on the Customer-Mac tier (this phase). refslund.ai backend (Tier 1) keeps Docker per Spec 050 v1.2.1 two-tier.
- **A12:** officer-in-loop on architecture preserved — Crew agents execute slices, CoS reviews.
- **A14 (msg 2612):** don't self-stop; continue until task complete.

## 4. Checkpoint structure

Phase 2 decomposes into **12 checkpoints**. Each has pre-conditions, actions, golden eval, rollback path, effort estimate. Phase 2 directive estimates 1-2 days — fits if checkpoints execute in sequence without re-work.

### Checkpoint 2.0 — Pre-flight: Phase 1 complete + Phase 0 deferred items closed

- **Pre-conditions:** `docs/migration-phase1-baseline.md` exists on `mac-native` branch with all 12 checkpoint PASSes.
- **Actions:**
  1. Verify Phase 1 baseline doc commit reachable on `mac-native`.
  2. Run Phase 0 deferred work (now unblocked by Phase 1 pg17 + neonctl):
     - Full `pg_dump --schema-only` + per-canonical-table `--data-only` against current DATABASE_URL using pg17 client. Replace placeholder `schema-tables.txt` baseline with proper SQL dump.
     - Run Phase 0.3 round-trip restore test per Spec 057 §0.3 procedure (pre-flight `CREATE EXTENSION vector;` on temp branch per CTO finding #1; pgvector top-K verification against captured baseline IDs 1022,744,785,741,740 per CTO finding #3).
     - `redis-cli BGSAVE` + `cp dump.rdb /tmp/cabinet-phase0-snapshots/redis-dump.rdb` (per CTO finding #2, BGSAVE not SAVE).
  3. Update `docs/migration-phase0-baseline.md` with the now-completed deferred items (Mac-side completion notes).
- **Golden eval:**
  - pg_dump version 17.x confirmed in dump output
  - Round-trip restore: counts match Phase 0 inventory ±0%; pgvector top-5 IDs match baseline exactly
  - Redis dump.rdb non-zero size + parses with `redis-cli --rdb` (read-validate)
  - Phase 0 baseline doc updated with deferred-completion notes
- **Rollback:** N/A (read-only verification).
- **Effort:** 30-45 min.
- **Stop-the-line:** if Phase 0.3 round-trip pgvector mismatch hits, halt Phase 2 + investigate per Spec 057 §6.

### Checkpoint 2.1 — Delete `Dockerfile.officer` + `docker-compose.yml`

- **Pre-conditions:** on `mac-native` branch; Phase 2.0 PASS.
- **Actions:**
  1. `git rm cabinet/Dockerfile.officer`
  2. `git rm cabinet/docker-compose.yml`
  3. `git rm cabinet/Dockerfile.watchdog` (if exists; per directive)
  4. Commit: `chore(spec-059): remove Docker substrate from Customer-Mac tier (Spec 050 v1.2.1 two-tier; Hetzner backend keeps Docker separately)`
- **Golden eval:**
  - `ls cabinet/Dockerfile.officer cabinet/docker-compose.yml 2>&1` returns "No such file or directory"
  - Commit lands on `mac-native` branch
  - `master` branch UNCHANGED (refslund.ai backend tier still uses these for Hetzner)
- **Rollback:** `git revert <commit>` restores the files.
- **Effort:** 5 min.
- **Note:** `master` branch keeps these files because Spec 050 v1.2.1 Tier 1 (refslund.ai backend) stays Dockerized. Only `mac-native` branch drops Docker.

### Checkpoint 2.2 — Gate cost-tracking on platform.yml flag (preserve per Captain Q4)

- **Pre-conditions:** 2.1 PASS.
- **Actions:**
  1. Locate cost-tracking module — likely `cabinet/scripts/cost-tracking.sh` or inline in watchdog scripts.
  2. Add `instance/config/platform.yml` flag:
     ```yaml
     cost_tracking:
       enabled: false  # default for personal/STEP-internal; commercial-Cabinet default true
       alert_thresholds:
         daily_per_officer_usd: null  # nullable when disabled
         daily_per_cabinet_usd: null
     ```
  3. Wrap cost-tracking code paths with the flag check: `if read_yaml platform.yml cost_tracking.enabled == true; then ...`
  4. Update `cabinet/scripts/hooks/pre-tool-use.sh` spending-cap branches with the same flag (DO NOT delete the cap logic per Q4 — gate it).
- **Golden eval:**
  - Cost-tracking code paths skip cleanly when flag is false
  - Cost-tracking code paths execute as before when flag is true (commercial test path)
  - `grep -r "cost_tracking.enabled" cabinet/scripts/` returns the new flag check sites
- **Rollback:** `git revert <commit>` restores original behavior.
- **Effort:** 30-45 min.
- **Note:** Captain Q4 explicitly: "Keep! Just no budget cap." This checkpoint honors that — infra preserved, thresholds null.

### Checkpoint 2.3 — Write `cabinet/launchd/com.cabinet.officer.plist.template`

- **Pre-conditions:** 2.2 PASS.
- **Actions:**
  1. Create `cabinet/launchd/` directory.
  2. Write `com.cabinet.officer.plist.template` (placeholder `${OFFICER_ROLE}` for substitution by `deploy-mac.sh`):
     ```xml
     <?xml version="1.0" encoding="UTF-8"?>
     <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
     <plist version="1.0">
     <dict>
       <key>Label</key>
       <string>com.cabinet.officer.${OFFICER_ROLE}</string>
       <key>ProgramArguments</key>
       <array>
         <string>/Users/${USER}/work/captains-cabinet/cabinet/scripts/start-officer-mac.sh</string>
         <string>${OFFICER_ROLE}</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <dict>
         <key>SuccessfulExit</key>
         <false/>
       </dict>
       <key>ThrottleInterval</key>
       <integer>30</integer>
       <key>StandardOutPath</key>
       <string>/Users/${USER}/Library/Logs/cabinet/${OFFICER_ROLE}.out.log</string>
       <key>StandardErrorPath</key>
       <string>/Users/${USER}/Library/Logs/cabinet/${OFFICER_ROLE}.err.log</string>
       <key>EnvironmentVariables</key>
       <dict>
         <key>CABINET_HOST</key>
         <string>mac-mini-local</string>
         <key>CABINET_MODEL</key>
         <string>claude-sonnet-4-6</string>
         <!-- Other env vars sourced from cabinet/.env via start-officer-mac.sh -->
       </dict>
     </dict>
     </plist>
     ```
- **Golden eval:**
  - File exists at expected path
  - `plutil cabinet/launchd/com.cabinet.officer.plist.template` parses cleanly (Apple's plist validator)
  - Template variables resolvable: `OFFICER_ROLE`, `USER`
- **Rollback:** `rm cabinet/launchd/com.cabinet.officer.plist.template`.
- **Effort:** 20-30 min (per-keystroke care on the XML).
- **[Captain decision 1 per directive § Phase 2]:** KeepAlive policy. **Recommendation: `SuccessfulExit: false` with `ThrottleInterval: 30` (30s minimum between restarts).** NOT `Crashed: true` — too aggressive given Claude Code's own retry logic per directive Risk note. ThrottleInterval prevents restart loops on a binary that refuses to start. **No further Captain ratification needed unless you want to override the recommendation.**

### Checkpoint 2.4 — Write `cabinet/launchd/com.cabinet.watchdog.plist`

- **Pre-conditions:** 2.3 PASS.
- **Actions:**
  1. Write `com.cabinet.watchdog.plist` — the watchdog daemon (heartbeat checks, cron triggers, cost-tracking-if-enabled):
     ```xml
     <!-- ... similar structure, Label=com.cabinet.watchdog, ProgramArguments points to /Users/${USER}/work/captains-cabinet/cabinet/scripts/watchdog-mac.sh -->
     ```
  2. Mirror RunAtLoad + KeepAlive + ThrottleInterval pattern from 2.3.
- **Golden eval:** `plutil` parses cleanly.
- **Rollback:** `rm` the file.
- **Effort:** 15 min.

### Checkpoint 2.5 — Write `cabinet/launchd/com.cabinet.screenpipe.plist` (if needed)

- **Pre-conditions:** 2.4 PASS.
- **Actions:**
  1. Check if Screenpipe ships its own LaunchAgent (per Spec 058 §1.7). If yes, skip this checkpoint.
  2. If no (or to standardize naming), write `com.cabinet.screenpipe.plist` wrapping the `screenpipe record` command.
- **Golden eval:** Screenpipe LaunchAgent (its built-in or our wrapper) shows in `launchctl list`.
- **Rollback:** `rm` the file; rely on Screenpipe's own LaunchAgent.
- **Effort:** 10 min (or 0 if Screenpipe's own is sufficient).

### Checkpoint 2.6 — Write `cabinet/launchd/com.cabinet.daily-digest.plist`

- **Pre-conditions:** 2.5 PASS.
- **Actions:**
  1. Write `com.cabinet.daily-digest.plist` for the 08:00 Captain digest (per directive §Phase 5 — but the LaunchAgent itself lives here; the digest script comes later):
     ```xml
     <!-- Label=com.cabinet.daily-digest, ProgramArguments points to cabinet/cron/daily-digest.sh,
          StartCalendarInterval with Hour=8 Minute=0 -->
     ```
- **Golden eval:** `plutil` parses; `launchctl print` shows StartCalendarInterval correctly.
- **Rollback:** `rm` the file.
- **Effort:** 10 min.

### Checkpoint 2.7 — Rename `start-officer.sh` → `start-officer-mac.sh`, strip Docker code

- **Pre-conditions:** 2.6 PASS.
- **Actions:**
  1. `cp cabinet/scripts/start-officer.sh cabinet/scripts/start-officer-mac.sh`
  2. Strip Docker-specific code from `start-officer-mac.sh`:
     - Remove `docker exec` invocations
     - Remove `cabinet-officers-${role}` container assumptions
     - Replace tmux session creation to run native macOS (no container wrapping)
     - Keep: role-specific system prompt loader (preset → instance overlay), MCP attachment loop, Redis heartbeat registration, CABINET_MODEL Sonnet default (Move 1)
  3. Keep `start-officer.sh` unchanged on `mac-native` branch (master branch keeps it untouched too) — so officers on Hetzner-Docker can still launch via `start-officer.sh`.
     OR (cleaner): delete `start-officer.sh` on `mac-native` branch since `master` still has it.
  4. Update `cabinet/officer-supervisor.sh` (or equivalent) to invoke `start-officer-mac.sh` on Mac, `start-officer.sh` on Linux.
- **Golden eval:**
  - `bash -n cabinet/scripts/start-officer-mac.sh` (syntax check) passes
  - `grep -c "docker exec" cabinet/scripts/start-officer-mac.sh` returns 0
  - `grep -c "CABINET_MODEL" cabinet/scripts/start-officer-mac.sh` returns ≥1 (Move 1 routing preserved)
- **Rollback:** `git revert <commit>`.
- **Effort:** 1-2 hours (bash code stripping + verification).

### Checkpoint 2.8 — Write `cabinet/scripts/deploy-mac.sh`

- **Pre-conditions:** 2.7 PASS.
- **Actions:**
  1. Write `deploy-mac.sh` — first-time deployment script per directive:
     ```bash
     #!/bin/bash
     # deploy-mac.sh — bring up Cabinet on Mac mini via LaunchAgents

     set -euo pipefail

     # Step 1: verify binaries installed + permissioned (per Spec 058 Phase 1)
     # Step 2: import Neon snapshots if --restore flag set
     # Step 3: substitute ${OFFICER_ROLE} + ${USER} in plist templates → write to ~/Library/LaunchAgents/
     # Step 4: register LaunchAgents via `launchctl bootstrap gui/$(id -u) <plist>`
     # Step 5: verify all officers start successfully (heartbeat Redis check)
     ```
  2. Implement step-by-step with `--dry-run` flag.
  3. Test on CoS only first (Step 5 limited to single officer for Phase 2 first-pass).
- **Golden eval:**
  - `bash -n` passes
  - `--dry-run` prints expected plist substitutions + launchctl commands without executing
  - Help text shows usage clearly
- **Rollback:** `rm` script.
- **Effort:** 2-3 hours.

### Checkpoint 2.9 — Test with CoS only first

- **Pre-conditions:** 2.8 PASS; Mac mini boots fresh; Phase 0 Neon snapshots available for restore.
- **Actions:**
  1. On Mac mini: `bash cabinet/scripts/deploy-mac.sh --officer cos --restore`
  2. Watch CoS LaunchAgent start: `launchctl print gui/$(id -u)/com.cabinet.officer.cos`
  3. Attach to CoS tmux session: `tmux attach -t officer-cos`
  4. Verify CoS publishes heartbeat to Redis: `redis-cli GET cabinet:heartbeat:cos`
  5. Crash test: `pkill -f "claude.*cos"` and verify LaunchAgent auto-restarts within 30s (ThrottleInterval)
- **Golden eval:**
  - `launchctl print` shows CoS LaunchAgent active
  - `tmux attach -t officer-cos` succeeds; CoS Claude Code session visible
  - `redis-cli GET cabinet:heartbeat:cos` returns recent timestamp (<60s old)
  - After pkill, heartbeat resumes within 30s (KeepAlive triggers ThrottleInterval'd restart)
- **Rollback:** `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist`; `rm` the LaunchAgent.
- **Effort:** 1-2 hours (debug-loop expected).

### Checkpoint 2.10 — Phase 2 baseline doc + commit to mac-native

- **Pre-conditions:** 2.9 PASS.
- **Actions:**
  1. Write `docs/migration-phase2-baseline.md`:
     - Phase 0 deferred items now COMPLETE (with output samples)
     - Files deleted (Dockerfile.officer + docker-compose.yml)
     - Files added (4 launchd plists + deploy-mac.sh + start-officer-mac.sh)
     - CoS LaunchAgent verification log
     - Cost-tracking flag state (`platform.yml → cost_tracking.enabled: false`)
  2. Commit to mac-native + push.
- **Golden eval:** baseline doc on `mac-native` branch with all sections filled.
- **Effort:** 30 min.

### Checkpoint 2.11 — CTO peer review on the full Phase 2 result

- **Pre-conditions:** 2.10 PASS.
- **Actions:**
  1. Notify CTO via `notify-officer.sh` that Spec 059 Phase 2 execution complete; surface mac-native branch HEAD + baseline doc path.
  2. CTO adversary-reviews the launchd plist set + start-officer-mac.sh + deploy-mac.sh + cost-tracking gate.
  3. Fold CTO findings if any.
- **Golden eval:** CTO ack signal with findings count + severity; CoS folds same-day.
- **Effort:** 30 min CoS coordination; CTO review window variable (~1-2 hours).

## 5. Effort estimate (whole Phase 2)

**Realistic: 6-10 hours focused.** Checkpoint 2.7 (start-officer-mac.sh strip) and 2.8 (deploy-mac.sh) are the long-tail; 2.9 debug-loop adds variance. Phase 2 fits in one weekend day if no surprises.

## 6. Stop-the-line gates

1. **Phase 0.3 round-trip restore pgvector mismatch (2.0).** Halt + investigate before proceeding.
2. **Cost-tracking gate accidentally disables cap on commercial path (2.2).** Worth a CTO review specifically on this flag wiring before 2.3.
3. **CoS LaunchAgent crash-loops in 2.9.** ThrottleInterval should prevent runaway but if KeepAlive triggers indefinitely on a binary refusing to start, the directive Risk #6 warns about this — investigate before adding KeepAlive to other officers.

## 7. Phase 2 → Phase 3 handoff

When Phase 2 completes:
- Mac mini runs CoS as a LaunchAgent (the directive's deliverable)
- Phase 0 deferred items closed
- 4 LaunchAgent plists ready for full-officer rollout in Phase 7
- start-officer-mac.sh + deploy-mac.sh ready
- Cost-tracking infra preserved + flagged off for personal-use

Phase 3 (Telegram topology collapse) is independent of Phase 2 substrate but assumes it's stable — so 2.11 CTO review acks before Phase 3 kickoff.

## 8. Open items folded forward

- **start-officer.sh deletion on mac-native:** decide in 2.7 (clean delete vs. keep both for cross-platform). Recommend delete on mac-native since `master` keeps it for Hetzner.
- **Daily-digest script** (referenced in 2.6 but written in Phase 5) — Phase 2 just creates the LaunchAgent plist that will run the eventual script.
- **Officer-by-officer LaunchAgent rollout** — Phase 7 brings up CTO/CPO/CRO/COO as LaunchAgents after Phase 3-6 surface changes are stable.
- **Phase 0 deferred items full closure (2.0)** — also closes Spec 057 Phase 0 properly.

## 9. Sign-off

This Phase 2 plan is **DRAFT, ready for CTO tech review.** CTO has been standing by for it since 23:08 UTC last night (msg 2026-05-22). After CTO review folds, Captain greenlights execution under blanket autonomy grant (msg 2605, 2612).

---

**Captain decision queue entry:**

> Spec 059 Phase 2 plan filed on mac-native branch. No further ratification needed — proceeding under blanket autonomy. CTO tech review fires first; CoS folds findings; Captain executes when Mac mini Phase 1 complete.
