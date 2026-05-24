# Spec 059 — Mac Migration Phase 2 Plan (Delete Docker, Add launchd)

- **Version:** v1.1.1 (added Checkpoint 2.9b — reload-officer-mac.sh creation, 061-B fold-gap fix)
- **Date:** 2026-05-23 (v1.0 → v1.1 07:05) → 2026-05-24 (v1.1.1 08:38 UTC)
- **Author:** CoS drafted (autonomous per Captain msg 2605, 2607, 2612); CPO added 2.9b (061-B fix; spec domain)
- **Status:** READY for CTO re-confirm + Captain execution

**v1.1.1 changelog — 061-B fold-gap fix (CRO/CoS stop-the-line, 2026-05-24):**
- **New Checkpoint 2.9b — Create `cabinet/scripts/reload-officer-mac.sh`.** The helper is called in 060 Checkpoint 3.2 + 061 Checkpoint 4.5, and changelogs claimed it was "Added as Checkpoint 4.5b" — but no such body ever existed, so execution would fail at the first call (060 3.2). Created here in Phase 2 (earliest use). 060 + 061 changelog refs corrected to point here.
- **LaunchAgent Label namespace:** stays `com.cabinet.officer.*` (NOT renamed to dk.refslund). Per CTO: TCC keys on the binary code-signing identifier (set in 058 1.8 to dk.refslund.cabinet.officer.*), which is orthogonal to the launchd Label; renaming would churn shipped code (28a2143 + 5783274) for cosmetic-only gain. No body change.

**v1.1 changelog — CTO 8 MUST-fold + 4 SHOULD-fold + 2 NIT findings absorbed (msg 2026-05-23 06:56 UTC):**
- **(1) plist variable substitution** — launchd doesn't expand `${OFFICER_ROLE}` / `${USER}` at runtime. **deploy-mac.sh (2.8) MUST `envsubst` the template before writing the per-officer plist** to `~/Library/LaunchAgents/`. Updated 2.8 with explicit `envsubst < template > final.plist` step + golden-eval verification.
- **(2) `WorkingDirectory` key** — added to 2.3 plist template. Without it, scripts can't locate `cabinet/.env` from a launchd-spawned process. `<key>WorkingDirectory</key><string>/Users/${USER}/work/captains-cabinet</string>` added.
- **(3) `SoftResourceLimits NumberOfFiles=4096`** — added to 2.3 plist template. Default 256 hits EMFILE under MCP load (per CTO substrate experience).
- **(4) tmux session lifecycle** — 2.7 strip + 2.9 attach contradicted without explicit `tmux new-session -d`. Added to 2.7 the explicit pattern: `tmux new-session -d -s officer-$OFFICER_ROLE 'claude ...'`. 2.9 attach now works against the detached session.
- **(5) start-officer-mac.sh effort** — revised 2.7 estimate from 1-2h → 2-3h (per CTO honesty: launchd exit-code shaping + tmux orchestration + macOS path conventions are substantive).
- **(6) cost-tracking LOGGING vs ENFORCEMENT split** — 2.2 updated. `cost_tracking.logging.enabled` (default true — keeps audit data for commercial-future) separate from `cost_tracking.enforcement.enabled` (default false personal, true commercial). Captain Q4 honored both ways.
- **(7) Mac timezone Europe/Berlin** — new pre-step in 2.6 before StartCalendarInterval. `sudo systemsetup -settimezone Europe/Berlin`. Without it, 08:00 daily-digest fires at wrong wall-clock time.
- **(8) Skip Checkpoint 2.5** — Screenpipe ships its own LaunchAgent. Removed our 2.5 plist write; 2.5 reduced to "verify Screenpipe's built-in LaunchAgent is registered + healthy."

SHOULD-fold (folded inline): launchctl bootstrap return-code handling, plist file permissions (644 not 600), bootout-vs-disable nuance documented, KeepAlive ThrottleInterval rationale documented.

NIT: held — log paths + plist label format are fine.
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

### Checkpoint 2.2 — Gate cost-tracking: split LOGGING vs ENFORCEMENT (v1.1 CTO #6)

- **Pre-conditions:** 2.1 PASS.
- **Actions:**
  1. Locate cost-tracking module — likely `cabinet/scripts/cost-tracking.sh` or inline in watchdog scripts.
  2. Add `instance/config/platform.yml` flag with **CTO #6 split**:
     ```yaml
     cost_tracking:
       logging:
         enabled: true   # ALWAYS on — preserves audit data for commercial-future Cabinet path
       enforcement:
         enabled: false  # default personal/STEP-internal; commercial Cabinet sets true
         daily_per_cabinet_usd: null  # set when enforcement enabled
         daily_per_officer_usd: null
     ```
  3. Wrap cost-tracking code:
     - **Logging always runs** (records per-officer + per-cabinet costs to Redis + JSONL)
     - **Enforcement gated** (cap-breach pause + DM Captain only if enforcement.enabled)
  4. Update `cabinet/scripts/hooks/pre-tool-use.sh` spending-cap branches with the enforcement flag (logging branches stay always on).
- **Golden eval:**
  - Logging records cost data regardless of flag state
  - Enforcement only fires when enforcement.enabled=true
  - `grep -r "cost_tracking.logging.enabled\|cost_tracking.enforcement.enabled" cabinet/scripts/` returns the new flag check sites
- **Rollback:** `git revert <commit>` restores original behavior.
- **Effort:** 45-60 min.
- **CTO v1.1 #6 rationale:** Captain Q4 said "Keep! Just no budget cap." Logging-vs-enforcement split honors that more cleanly — commercial-future Cabinet customers want audit data accumulating from day one even when their own enforcement is disabled.

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
       <key>WorkingDirectory</key>
       <string>/Users/${USER}/work/captains-cabinet</string>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <dict>
         <key>SuccessfulExit</key>
         <false/>
       </dict>
       <key>ThrottleInterval</key>
       <integer>30</integer>
       <key>SoftResourceLimits</key>
       <dict>
         <key>NumberOfFiles</key>
         <integer>4096</integer>
       </dict>
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
         <!-- Other env vars sourced from cabinet/.env via WorkingDirectory + start-officer-mac.sh -->
       </dict>
     </dict>
     </plist>
     ```
     **CTO v1.1 #2 + #3:** `WorkingDirectory` so scripts find `cabinet/.env`; `SoftResourceLimits NumberOfFiles=4096` so MCP load doesn't EMFILE.
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

### Checkpoint 2.5 — Verify Screenpipe's own LaunchAgent (v1.1 CTO #8 — SKIP our wrapper)

- **Pre-conditions:** 2.4 PASS; Screenpipe installed (Spec 058 §1.7).
- **Actions:**
  1. Per CTO #8: do NOT write `cabinet/launchd/com.cabinet.screenpipe.plist` — rely on Screenpipe's built-in LaunchAgent. Reduces blast radius (one less thing for us to maintain across macOS updates).
  2. Verify Screenpipe's LaunchAgent is registered + healthy: `launchctl list | grep -i screenpipe`
- **Golden eval:** Screenpipe LaunchAgent visible + active.
- **Rollback:** N/A — we own nothing here.
- **Effort:** 5 min verification.

### Checkpoint 2.6 — Mac timezone to Europe/Berlin + write daily-digest plist (v1.1 CTO #7)

- **Pre-conditions:** 2.5 PASS.
- **Actions:**
  1. **Set Mac timezone** (CTO #7 — without this, StartCalendarInterval fires at wrong wall-clock):
     ```bash
     sudo systemsetup -settimezone Europe/Berlin
     sudo systemsetup -gettimezone  # verify Europe/Berlin
     ```
  2. Write `cabinet/launchd/com.cabinet.daily-digest.plist` for the 08:00 Captain digest:
     ```xml
     <!-- Label=com.cabinet.daily-digest
          WorkingDirectory=/Users/${USER}/work/captains-cabinet
          ProgramArguments=[bash, cabinet/cron/daily-digest.sh]
          StartCalendarInterval={Hour=8, Minute=0}
          + standard log paths -->
     ```
- **Golden eval:**
  - `sudo systemsetup -gettimezone` returns Europe/Berlin
  - `plutil` parses the plist
  - `launchctl print` shows StartCalendarInterval Hour=8 Minute=0
- **Rollback:** restore default timezone via systemsetup; `rm` the plist.
- **Effort:** 15 min.

### Checkpoint 2.7 — Rename + strip + tmux session (v1.1 CTO #4 + #5)

- **Pre-conditions:** 2.6 PASS.
- **Actions:**
  1. `cp cabinet/scripts/start-officer.sh cabinet/scripts/start-officer-mac.sh`
  2. Strip Docker-specific code from `start-officer-mac.sh`:
     - Remove `docker exec` invocations
     - Remove `cabinet-officers-${role}` container assumptions
     - Keep: role-specific system prompt loader (preset → instance overlay), MCP attachment loop, Redis heartbeat registration, CABINET_MODEL Sonnet default (Move 1)
  3. **Explicit tmux session lifecycle (CTO #4):**
     ```bash
     # Inside start-officer-mac.sh
     SESSION="officer-${OFFICER_ROLE}"
     if tmux has-session -t "$SESSION" 2>/dev/null; then
       echo "Session $SESSION already exists; attaching not creating"
     else
       # Detached session (-d) so launchd doesn't block on TTY
       tmux new-session -d -s "$SESSION" "exec claude $_BASE_FLAGS $_CHANNEL_FLAGS"
     fi
     # Heartbeat + supervise loop continues outside tmux
     ```
  4. On `mac-native` branch: delete `start-officer.sh` (master keeps it for Hetzner).
  5. Update `cabinet/officer-supervisor.sh` (or equivalent) to invoke `start-officer-mac.sh` on Mac, `start-officer.sh` on Linux (path detection by `uname`).
- **Golden eval:**
  - `bash -n cabinet/scripts/start-officer-mac.sh` (syntax check) passes
  - `grep -c "docker exec" cabinet/scripts/start-officer-mac.sh` returns 0
  - `grep -c "CABINET_MODEL" cabinet/scripts/start-officer-mac.sh` returns ≥1 (Move 1 routing preserved)
  - `grep -c "tmux new-session -d" cabinet/scripts/start-officer-mac.sh` returns ≥1 (CTO #4 detached session pattern)
- **Rollback:** `git revert <commit>`.
- **Effort:** 2-3 hours (CTO #5 honest estimate — launchd exit-code shaping + tmux orchestration + macOS paths are substantive).

### Checkpoint 2.8 — Write `cabinet/scripts/deploy-mac.sh` with envsubst (v1.1 CTO #1)

- **Pre-conditions:** 2.7 PASS.
- **Actions:**
  1. Write `deploy-mac.sh` — first-time deployment per directive:
     ```bash
     #!/bin/bash
     # deploy-mac.sh — bring up Cabinet on Mac mini via LaunchAgents
     set -euo pipefail

     # Step 1: verify binaries installed + permissioned (per Spec 058 Phase 1)
     # Step 2: import Neon snapshots if --restore flag set
     # Step 3: envsubst each plist template → write to ~/Library/LaunchAgents/
     #         (CTO #1: launchd does NOT expand ${VAR} at runtime; substitution
     #          MUST happen before writing the plist)
     # Step 4: register LaunchAgents via `launchctl bootstrap gui/$(id -u) <plist>`
     # Step 5: verify all officers start successfully (heartbeat Redis check)
     ```
  2. **CRITICAL plist envsubst step (CTO #1):**
     ```bash
     # For each officer:
     export OFFICER_ROLE="cos"
     export USER="${USER}"  # already in env
     mkdir -p ~/Library/LaunchAgents
     envsubst < cabinet/launchd/com.cabinet.officer.plist.template \
              > ~/Library/LaunchAgents/com.cabinet.officer.${OFFICER_ROLE}.plist
     chmod 644 ~/Library/LaunchAgents/com.cabinet.officer.${OFFICER_ROLE}.plist  # CTO SHOULD-fold
     plutil ~/Library/LaunchAgents/com.cabinet.officer.${OFFICER_ROLE}.plist  # parse-validate
     launchctl bootstrap gui/$(id -u) \
               ~/Library/LaunchAgents/com.cabinet.officer.${OFFICER_ROLE}.plist
     ```
  3. Implement with `--dry-run` flag.
  4. Test on CoS only first.
- **Golden eval:**
  - `bash -n` passes
  - `--dry-run` prints expected envsubst + launchctl commands without executing
  - **CTO #1 verification:** post-envsubst, `grep -c '\${OFFICER_ROLE}\|\${USER}' ~/Library/LaunchAgents/com.cabinet.officer.cos.plist` returns 0 (variables replaced, no literal `${...}` left)
  - `plutil` validates the written plist
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

### Checkpoint 2.9b — Create `cabinet/scripts/reload-officer-mac.sh` helper

> **v1.1.1 fix:** this helper is CALLED in 060 Checkpoint 3.2 + 061 Checkpoint 4.5, and its creation was claimed in changelogs ("Added as Checkpoint 4.5b") but NO checkpoint body ever created it → execution would fail at the first call in 060 3.2. Created here in Phase 2 — the earliest use, where the bootout/bootstrap pattern is first introduced (2.8/2.9).

- **Pre-conditions:** 2.8 (deploy-mac.sh) PASS — establishes the bootout/bootstrap pattern this helper centralizes.
- **Actions:**
  1. Write `cabinet/scripts/reload-officer-mac.sh`:
     ```bash
     #!/bin/bash
     # reload-officer-mac.sh <officer-role> — bootout + re-bootstrap one officer LaunchAgent.
     # Centralizes the restart cycle used by deploy-mac.sh (Phase 2), 060 3.2 (product.yml reload),
     # 061 4.5 (mcp.json overlay reload), and later phases.
     set -euo pipefail
     ROLE="${1:?usage: reload-officer-mac.sh <officer-role>}"
     PLIST="$HOME/Library/LaunchAgents/com.cabinet.officer.${ROLE}.plist"
     [ -f "$PLIST" ] || { echo "reload-officer-mac.sh: plist not found: $PLIST" >&2; exit 1; }
     launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true   # tolerate not-currently-loaded
     launchctl bootstrap "gui/$(id -u)" "$PLIST"
     sleep 5
     HB=$(redis-cli GET "cabinet:heartbeat:${ROLE}" 2>/dev/null || true)
     [ -n "$HB" ] && echo "reload-officer-mac.sh: ${ROLE} heartbeat OK ($HB)" \
                  || { echo "reload-officer-mac.sh: WARN ${ROLE} no heartbeat yet (may still be starting)" >&2; }
     ```
  2. `chmod +x cabinet/scripts/reload-officer-mac.sh`
  3. (Optional DRY refactor) deploy-mac.sh Step 4 bootout/bootstrap MAY call this helper instead of inline `launchctl` — not required for Phase 2 pass.
- **Golden eval:**
  - `bash -n cabinet/scripts/reload-officer-mac.sh` passes
  - `reload-officer-mac.sh cos` (after 2.9 CoS bootstrap) bootouts + re-bootstraps CoS; heartbeat resumes within 30s
  - Missing-role arg → usage error + non-zero exit; missing plist → clear error + non-zero exit
- **Rollback:** `rm cabinet/scripts/reload-officer-mac.sh`.
- **Effort:** 20-30 min.

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
