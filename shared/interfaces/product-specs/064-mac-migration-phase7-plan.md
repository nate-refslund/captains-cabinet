# Spec 064 — Mac Migration Phase 7 Plan (Full Officer Rollout + Observability)

- **Version:** v1.0
- **Date:** 2026-05-23 (07:35 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** DRAFT — ready for CTO tech review + Captain execution

- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 7 ("Full officer rollout + observability — 1-2 days")
- **Predecessors:** Spec 057-063 (Phases 0-6)
- **Successor:** Spec 065 (Phase 8 — Documentation + release)

---

## 1. Phase 7 goal (from directive)

All 5 officers running as native macOS LaunchAgents. Observability live (log aggregation, heartbeat alerts, cost dashboards). 48h soak test under real Sensed workload passes. The Mac mini operates Cabinet at full strength autonomously, on par with the Hetzner deployment's stability bar.

## 2. Inputs from Phase 6

- Cabinet worktree lifecycle works (worktree-add.sh + worktree-remove.sh + task-completion hook via Postgres NOTIFY)
- Adapter contract documented + `_template/` skeleton committed
- Constitution carries Lead-only Telegram + Lead-only computer-use clauses
- CoS LaunchAgent + CTO LaunchAgent (Phase 3.6) already running stably
- Daily-digest LaunchAgent firing 08:00 local (Phase 5)
- Worktree-listener LaunchAgent listening on Postgres NOTIFY (Phase 6.3)

## 3. Captain ratifications carried forward

- **Mac Migration Directive §Phase 7:** 48h soak under real workload is the gate.
- **A11 Library + /tasks canonical** — must remain authoritative during soak.
- **A12 (PROPOSED ratification):** officer-in-loop on architecture preserved.
- **A14 (msg 2612):** don't self-stop during soak — handle by logging incidents to Library + continuing.
- **Captain reader-friendly tone (msg 2583):** soak-incident reports use plain language.

## 4. Checkpoint structure

Phase 7 decomposes into **10 checkpoints**. Directive estimates 1-2 days; realistic 1.5 days focused + 48h soak wall-clock.

### Checkpoint 7.1 — Bring up CPO LaunchAgent (Telegram-dark)

- **Pre-conditions:** Phase 6 complete.
- **Actions:**
  1. Run `bash cabinet/scripts/deploy-mac.sh --officer cpo` (Spec 059 substrate)
  2. Verify CPO LaunchAgent active via `launchctl print gui/$(id -u)/com.cabinet.officer.cpo`
  3. Verify CPO Telegram-dark (no `--channels plugin:telegram`) per Spec 060 capability gate
  4. Verify CPO heartbeat: `redis-cli GET cabinet:heartbeat:cpo` returns recent
  5. Send a test trigger via `bash cabinet/scripts/notify-officer.sh cpo "Phase 7 dispatch test"` — CPO sees it
- **Golden eval:**
  - CPO LaunchAgent active per `launchctl print`
  - No Telegram channel attached (CPO bot already revoked Phase 3)
  - Heartbeat fresh + trigger round-trip works
- **Rollback:** `launchctl bootout` CPO LaunchAgent.
- **Effort:** 30 min.

### Checkpoint 7.2 — Bring up CRO LaunchAgent (consultant type)

- **Pre-conditions:** 7.1 PASS.
- **Actions:**
  1. CRO is `consultant` type per `instance/config/platform.yml` (not fulltime) — Phase 1 cron schedule fires it
  2. Either: (a) launchd `StartCalendarInterval` mimicking Hetzner cron schedule (every 4h research sweep), OR (b) keep Hetzner-cron equivalent on Mac via `cabinet/cron/research-sweep.sh` + LaunchAgent
  3. Decision: use (b) — research-sweep LaunchAgent fires every 4h (matches Hetzner)
  4. Verify next-fire timestamp via `launchctl print`
- **Golden eval:**
  - CRO LaunchAgent registered (NOT KeepAlive — consultant fires on schedule)
  - Manual invocation works: `bash cabinet/cron/research-sweep.sh` produces a brief
  - Scheduled fire (wait or set test interval) produces a brief
- **Rollback:** `launchctl bootout` CRO LaunchAgent.
- **Effort:** 45 min (consultant-type pattern differs from fulltime).

### Checkpoint 7.3 — Bring up COO LaunchAgent

- **Pre-conditions:** 7.2 PASS.
- **Actions:**
  1. `bash cabinet/scripts/deploy-mac.sh --officer coo`
  2. Verify LaunchAgent + heartbeat + dispatch round-trip (same pattern as 7.1)
  3. COO is fulltime per platform.yml — KeepAlive enabled
- **Golden eval:**
  - COO LaunchAgent active
  - COO heartbeat fresh + trigger round-trip works
  - Telegram-dark
- **Rollback:** `launchctl bootout`.
- **Effort:** 20 min.

### Checkpoint 7.4 — Verify all 5 officers active simultaneously

- **Pre-conditions:** 7.1-7.3 PASS.
- **Actions:**
  1. `launchctl list | grep com.cabinet.officer` — expect 4 fulltime PIDs visible (CoS + CTO + CPO + COO; CRO is consultant so may be inactive between fires)
  2. `bash cabinet/scripts/list-officers.sh` (existing — covers Mac via launchctl path)
  3. Verify heartbeats all <15min:
     ```bash
     for o in cos cto cpo coo; do
       redis-cli GET "cabinet:heartbeat:$o" | xargs -I{} echo "$o: {}"
     done
     ```
- **Golden eval:**
  - 4 fulltime officers heartbeating
  - CRO consultant fires per schedule (verified by `cabinet:schedule:last-run:cro:research-sweep` recency)
  - No officer in crash-restart loop (verify `launchctl print` for restart counter)
- **Rollback:** N/A — diagnostic.
- **Effort:** 20 min.

### Checkpoint 7.5 — Stand up log aggregation (Mac unified logs)

- **Pre-conditions:** 7.4 PASS.
- **Actions:**
  1. Each officer LaunchAgent already writes stdout + stderr to `/var/log/cabinet/<officer>.{out,err}.log` per Spec 059 plist (`StandardOutPath` + `StandardErrorPath`)
  2. Add `cabinet/scripts/log-tail-all.sh`:
     ```bash
     #!/bin/bash
     # log-tail-all.sh — multi-tail all officer logs
     for o in cos cto cpo cro coo; do
       (tail -f "/var/log/cabinet/$o.out.log" | sed "s/^/[$o] /" &)
     done
     wait
     ```
  3. Verify rotation: macOS `newsyslog` rotates `/var/log/*` by default; add custom rule for `/var/log/cabinet/*.log` rotation at 100MB / 7 days:
     ```
     # /etc/newsyslog.d/cabinet.conf
     /var/log/cabinet/*.log  cabinet:staff  644  7  102400  *  Z
     ```
- **Golden eval:**
  - log-tail-all.sh streams 5 officer logs (4 fulltime continuously + 1 consultant during fire)
  - newsyslog config valid: `sudo newsyslog -v -F` reports cabinet rule OK
- **Rollback:** revert config files.
- **Effort:** 30 min.

### Checkpoint 7.6 — Heartbeat alerts (silent-officer detection)

- **Pre-conditions:** 7.5 PASS.
- **Actions:**
  1. Write `cabinet/cron/heartbeat-watchdog.sh`:
     ```bash
     #!/bin/bash
     # heartbeat-watchdog.sh — every 5 min, check fulltime officer heartbeats
     # If >15min stale, DM Captain via CoS Telegram + log incident
     for o in cos cto cpo coo; do
       LAST=$(redis-cli GET "cabinet:heartbeat:$o" || echo "")
       if [ -z "$LAST" ]; then continue; fi
       AGE=$(( $(date +%s) - $(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LAST" +%s 2>/dev/null || echo 0) ))
       if [ "$AGE" -gt 900 ]; then
         # Stale — alert (deduped by Redis 1h TTL key)
         if redis-cli SET "cabinet:alert:heartbeat-stale:$o" 1 NX EX 3600 | grep -q OK; then
           bash cabinet/scripts/send-to-group.sh "[HEARTBEAT] $o stale ${AGE}s — check launchctl"
         fi
       fi
     done
     ```
  2. Register as LaunchAgent firing every 5 min:
     `cabinet/launchd/com.cabinet.heartbeat-watchdog.plist`
- **Golden eval:**
  - Watchdog fires every 5 min (verified via `launchctl print` next-fire)
  - Test: `launchctl bootout` CTO briefly → wait 16+ min → CoS DMs Captain "[HEARTBEAT] cto stale"
  - Restart CTO → next watchdog tick does NOT re-alert (1h TTL dedup)
- **Rollback:** bootout watchdog LaunchAgent.
- **Effort:** 45 min.

### Checkpoint 7.7 — Cost dashboard (per-officer + cabinet-wide)

- **Pre-conditions:** 7.6 PASS.
- **Actions:**
  1. Cost-tracking logging already on (Spec 059 v1.1 split — logging always on, enforcement gated). Counters in Redis: `cabinet:cost:daily:<officer>:<YYYY-MM-DD>` + `cabinet:cost:monthly:<officer>:<YYYY-MM>`
  2. Write `cabinet/cron/cost-summary.sh` — daily 23:00 local digest:
     ```bash
     # cost-summary.sh — daily 23:00 → HQ group
     TODAY=$(date +%Y-%m-%d)
     echo "💰 Cabinet cost summary $TODAY"
     for o in cos cto cpo cro coo; do
       DAILY=$(redis-cli GET "cabinet:cost:daily:$o:$TODAY" || echo "0")
       echo "  $o: \$$DAILY"
     done | bash cabinet/scripts/send-to-group.sh --stdin
     ```
  3. Register as LaunchAgent at 23:00 local: `cabinet/launchd/com.cabinet.cost-summary.plist`
  4. (Optional, Phase 7 nice-to-have) Dashboard `/cost` route on customer-dashboard reads same Redis keys. Defer if time-constrained.
- **Golden eval:**
  - Manual fire: `bash cabinet/cron/cost-summary.sh` posts a digest to HQ group
  - Scheduled fire at 23:00 produces the same
- **Rollback:** bootout LaunchAgent.
- **Effort:** 30 min (45 min if dashboard route included).

### Checkpoint 7.8 — 48h soak under real Sensed workload (the directive gate)

- **Pre-conditions:** 7.1-7.7 PASS; Captain has at least one open Sensed PR/issue for officers to work on during soak.
- **Actions:**
  1. Captain DMs CoS with the first real task: "CoS, coordinate <real task>." 
  2. Soak window starts. CoS dispatches CTO/CPO/COO via Redis as needed; CRO consultant fires per schedule.
  3. **No CoS intervention to fix flakes during soak** — incidents logged to Library `incidents` space + auto-detected by watchdog (7.6). Captain reads digest + heartbeat alerts.
  4. Verify after 48h wall-clock:
     - All 4 fulltime LaunchAgents stayed up (KeepAlive worked) — restart counter low (<3 per officer ideal)
     - Captain saw 2 daily digests (08:00 each day)
     - CRO fired 12x (every 4h × 48h = 12)
     - Worktree lifecycle worked at least once (worktree created + cleaned)
     - Cost-summary fired twice (23:00 each day)
     - No silent-officer alert fired (or if fired, was self-corrected by KeepAlive)
- **Golden eval:**
  - 48h uptime metrics within tolerance (specifics above)
  - Captain provides qualitative thumbs-up: "Cabinet on Mac felt as responsive as Hetzner"
- **Rollback:** If soak fails (e.g., officer crash loop, heartbeat-watchdog firing repeatedly), document failure mode → Phase 7 doesn't gate; iterate fixes + re-soak.
- **Effort:** 48h wall-clock; CoS-side ~1-2 hours total responding to dispatches as normal.
- **Stop-the-line:** if more than one officer enters crash-restart loop (>5 restarts in 30 min), HALT soak + investigate KeepAlive config + officer-specific logs.

### Checkpoint 7.9 — Stabilize any flakes from 7.8

- **Pre-conditions:** 7.8 SOAK COMPLETE (or in progress with identified issues).
- **Actions:**
  1. For each incident logged during 7.8: root-cause + fix
  2. Common likely flakes (anticipated):
     - LaunchAgent `ThrottleInterval:30` may need tuning if a particular officer restarts faster than its boot time
     - `SoftResourceLimits NumberOfFiles=4096` may need raising for Library/Postgres-heavy officers
     - Redis connection drops under load (mitigated by Spec 058 1.5 AOF + persistence)
  3. Re-soak short window (12h) post-fix
- **Golden eval:** all flakes resolved or documented + accepted with monitoring.
- **Rollback:** N/A — diagnostic + fix.
- **Effort:** Variable; budget 4-6 hours.

### Checkpoint 7.10 — Phase 7 baseline doc + commit

- **Pre-conditions:** 7.1-7.9 PASS.
- **Actions:**
  1. Write `docs/migration-phase7-baseline.md` with all sections:
     - 5 LaunchAgent inventory (PIDs, start times, restart counts)
     - log-tail-all.sh path + sample rotation log
     - Heartbeat-watchdog firing cadence
     - Cost-summary firing cadence + first 2 digests
     - 48h soak incident log (sanitized)
     - Flake-fix changelog
  2. Commit + push.
- **Golden eval:** baseline doc on `mac-native` branch.
- **Effort:** 45 min.

## 5. Effort estimate (whole Phase 7)

**Realistic: 1.5 days focused + 48h soak wall-clock.** Directive's 1-2 days matches when wall-clock is excluded from the "focused" portion.

## 6. Stop-the-line gates

1. **7.4 officer in crash-restart loop** (KeepAlive misconfigured). Halt + investigate `ThrottleInterval` + plist `SuccessfulExit:false` ratification (Spec 059 v1.1 Captain decision 1).
2. **7.6 heartbeat-watchdog false-positives** (date-parsing brittleness). Halt + fix the GNU-vs-BSD `date` divergence.
3. **7.8 soak surfaces unrecoverable flake** (Postgres conn drop, Redis OOM, etc.). Halt + Phase 7.9 fix loop.

## 7. Phase 7 → Phase 8 handoff

When Phase 7 completes:
- Cabinet on Mac runs all 5 officers autonomously, on par with Hetzner stability
- Observability covers heartbeats + costs + logs
- 48h soak validates real-workload behavior
- Phase 8 documents + tags the release + suspends Hetzner

## 8. Open items folded forward

- **Customer-dashboard `/cost` route** — Phase 7.7 deferred-optional; refine in Phase 8 if Captain asks
- **Per-officer cost-cap enforcement** — Spec 059 v1.1 split kept LOGGING on + ENFORCEMENT off; Phase 7 keeps enforcement off; revisit if costs balloon

## 9. Sign-off

DRAFT ready for CTO tech review. Captain ratifies the soak window start + final qualitative gate (7.8). All other checkpoints CoS-executable.
