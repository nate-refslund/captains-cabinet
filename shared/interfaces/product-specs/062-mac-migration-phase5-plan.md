# Spec 062 — Mac Migration Phase 5 Plan (Screenpipe Integration)

- **Version:** v1.1 (CTO 3 MUST-fold pin + token-budget + constitution-placement)
- **Date:** 2026-05-23 (v1.0 → v1.1 07:20 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** READY for CTO re-confirm + Captain execution

**v1.1 changelog — CTO MUST-fold findings (msg 2026-05-23 06:58 UTC):**
- **(1) Pin screenpipe-mcp version (5.1).** Same discipline as cua-driver (Spec 058 1.6). `npx -y screenpipe-mcp@<pinned-tag>` not `@latest`. Record pinned tag at `cabinet/config/screenpipe-mcp-version.txt`.
- **(2) Daily-digest Sonnet token budget (5.4).** 24h cross-reference of screenpipe activity + officer session JSONLs likely exceeds Sonnet 4.6 200K context window without pre-aggregation. Add pre-aggregation step: group + summarize per-app per-hour BEFORE handing to Sonnet, so Sonnet receives an aggregated digest input not raw events.
- **(3) Constitution-clause placement: framework, not preset.** Same bundled ratification as Phase 3 + Phase 4. Phase 5 doesn't add a new constitution clause (digest cadence + Screenpipe scope are config not constitution) so this is a no-op for this spec — noted for cross-spec coherence.
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 5 ("Screenpipe integration — 1 day")
- **Predecessors:** Spec 057-061 (Phases 0-4)
- **Successor:** Spec 063 (Phase 6 — Cabinet worktrees + adapter contract)

---

## 1. Phase 5 goal (from directive)

Universal screen observability. Daily 08:00 digest in HQ group. Reflection loop augmented with screenpipe cross-reference. Screenpipe is read-only-queryable by all officers (NOT Lead-scoped — different from cua-driver).

## 2. Inputs from Phase 4

- Screenpipe installed in Phase 1 Checkpoint 1.7
- CoS LaunchAgent runs with cua-driver MCP
- Lead-only computer-use clause in constitution
- Daily-digest LaunchAgent plist from Phase 2 Checkpoint 2.6 (placeholder script)

## 3. Captain ratifications + Phase 5-specific

- **Captain constraint (Mac Migration Directive):** Screenpipe is retrospective observability ONLY, not primary memory. Daily restart needed.
- **Captain reader-friendly tone (msg 2583):** daily-digest message tone matches.

## 4. Checkpoint structure

Phase 5 decomposes into **9 checkpoints**. Directive estimates 1 day; realistic 5-6 hours focused.

### Checkpoint 5.1 — Add screenpipe MCP to framework-level `.mcp.json`

- **Pre-conditions:** Screenpipe installed + permissioned (Spec 058 1.7 + 1.8).
- **Actions:**
  1. **Pin screenpipe-mcp version (v1.1 CTO #1):** resolve latest stable tag via npm + record:
     ```bash
     PINNED_TAG=$(npm view screenpipe-mcp version)
     echo "$PINNED_TAG" > cabinet/config/screenpipe-mcp-version.txt
     ```
  2. Edit `.mcp.json` using pinned tag (NOT `@latest`):
     ```json
     {
       "mcpServers": {
         "screenpipe": {
           "command": "npx",
           "args": ["-y", "screenpipe-mcp@<PINNED_TAG>"],
           "transport": "stdio"
         }
       }
     }
     ```
  2. Distinct from cua-driver — screenpipe is in framework-level .mcp.json (all officers get it) vs cua-driver in instance/agents/cos/mcp.json (CoS-only overlay).
- **Golden eval:**
  - All officers' `claude mcp list` includes screenpipe (post re-bootstrap)
  - Sample query: `screenpipe search --query "test" --limit 1` from any officer returns
- **Rollback:** `git revert` .mcp.json edit.
- **Effort:** 10 min.

### Checkpoint 5.2 — Configure Screenpipe exclusions

- **Pre-conditions:** 5.1 PASS.
- **Actions:**
  1. Open Screenpipe app settings.
  2. Add capture exclusions per directive (sensitive surfaces):
     - 1Password
     - Banking apps
     - Personal email clients
     - Any other where surveillance would be inappropriate
  3. Save config to `~/.screenpipe/config.toml` (Screenpipe writes this).
- **Golden eval:**
  - Exclusion list reflects directive
  - Briefly visit 1Password — Screenpipe's last-capture timestamp doesn't update
- **Rollback:** Remove exclusions in Screenpipe settings.
- **Effort:** 15-20 min.

### Checkpoint 5.3 — Set Screenpipe retention policy (30 days full / OCR-only beyond)

- **Pre-conditions:** 5.2 PASS.
- **Actions:**
  1. Configure retention via Screenpipe settings or `~/.screenpipe/config.toml`:
     - 30 days at full fidelity
     - OCR-only beyond
     - Auto-prune
- **Golden eval:**
  - `~/.screenpipe/config.toml` shows retention config
  - Disk usage in `~/.screenpipe/` stays bounded over time (manually verified in Phase 7 soak test)
- **Rollback:** Restore default retention in Screenpipe settings.
- **Effort:** 10 min.

### Checkpoint 5.4 — Write `cabinet/cron/daily-digest.sh`

- **Pre-conditions:** 5.3 PASS.
- **Actions:**
  1. Write `cabinet/cron/daily-digest.sh` with PRE-AGGREGATION (v1.1 CTO #2 — Sonnet 200K budget):
     ```bash
     #!/bin/bash
     # daily-digest.sh — Captain morning digest at 08:00 local time
     # Pre-aggregates 24h activity + session JSONLs BEFORE Sonnet to fit 200K context.

     set -euo pipefail

     # Step 1: Query screenpipe MCP for last 24h, aggregated per-app per-hour
     #         (NOT raw events — 24h × 6 apps × hourly = ~144 buckets, fits comfortably)
     # Step 2: Aggregate officer session JSONLs per-officer per-hour (tool call counts,
     #         file-modify counts, no raw content) — keeps under 50K tokens total
     # Step 3: Hand AGGREGATED summary (not raw) to Claude Sonnet 4.6 with digest prompt
     #         → reader-friendly output
     # Step 4: Post to HQ group via send-to-group.sh
     ```
  2. Use the Captain reader-friendly tone (msg 2583): plain language, no IDs/jargon.
  3. Include opt-out path: `~/.cabinet/digest-disabled` flag file checked first.
- **Golden eval:**
  - `bash -n` passes
  - Dry-run with `--dry-run` flag prints what would be queried + summarized
  - Manual invocation in non-dry mode posts a sample digest to HQ group
- **Rollback:** `rm cabinet/cron/daily-digest.sh`.
- **Effort:** 1-2 hours (the Sonnet prompt + cross-reference logic is the substance).

### Checkpoint 5.5 — Register daily-digest LaunchAgent

- **Pre-conditions:** 5.4 PASS; Phase 2 plist template at `cabinet/launchd/com.cabinet.daily-digest.plist` already exists.
- **Actions:**
  1. Substitute variables in the plist (StartCalendarInterval Hour=8 Minute=0).
  2. Install via deploy-mac.sh: `bash cabinet/scripts/deploy-mac.sh --daemon daily-digest`
  3. Verify: `launchctl print gui/$(id -u)/com.cabinet.daily-digest`
- **Golden eval:**
  - LaunchAgent active per `launchctl print`
  - `StartCalendarInterval` correctly shows 08:00
  - Survives next-day reboot (verified in Phase 7 soak)
- **Rollback:** `launchctl bootout` daily-digest LaunchAgent.
- **Effort:** 20 min.

### Checkpoint 5.6 — Daily-digest fires test (manual + scheduled)

- **Pre-conditions:** 5.5 PASS.
- **Actions:**
  1. Manual invocation: `bash cabinet/cron/daily-digest.sh` → check HQ group for the digest
  2. Wait until 08:00 next morning → verify LaunchAgent-fired digest appears in HQ group
- **Golden eval:**
  - Manual digest posts to HQ group with reader-friendly content
  - 08:00-fired digest posts to HQ group autonomously
- **Rollback:** N/A — test only.
- **Effort:** ~24h wall time (one digest cycle).

### Checkpoint 5.7 — Write `cabinet/scripts/reflection-with-screen.sh`

- **Pre-conditions:** 5.6 PASS.
- **Actions:**
  1. Write `reflection-with-screen.sh` augmenting the existing Reflection skill:
     ```bash
     #!/bin/bash
     # reflection-with-screen.sh — Reflection-skill helper for GUI-involved tasks.
     # When officer-session JSONL shows GUI tool calls (cua-driver, browser ops),
     # cross-reference with screenpipe data for the same time window.
     # Surfaces the rich context the officer should reflect on.
     ```
  2. Update `memory/skills/individual-reflection.md` or `memory/skills/evolved/reflection-with-screen.md` (the evolved version) to call `reflection-with-screen.sh` when JSONL indicates GUI tool calls.
- **Golden eval:**
  - Script syntactically valid
  - Reflection skill calls the script when GUI tool calls detected
- **Rollback:** `git revert`.
- **Effort:** 1 hour.

### Checkpoint 5.8 — Screenpipe queryable test

- **Pre-conditions:** 5.1-5.7 PASS; Screenpipe running for >2 hours capturing.
- **Actions:**
  1. Captain DMs CoS: "What apps did I have open between 14:00 and 15:00 today?"
  2. CoS uses screenpipe MCP to query the time window
  3. CoS replies via Telegram with the app list
- **Golden eval:**
  - Captain receives a coherent app-window list for the time window
  - Excluded apps (per 5.2) do NOT appear
- **Rollback:** N/A — test only.
- **Effort:** 20 min.

### Checkpoint 5.9 — Phase 5 baseline doc + commit

- **Pre-conditions:** 5.1-5.8 PASS.
- **Actions:** Write `docs/migration-phase5-baseline.md` with all sections; commit + push.
- **Golden eval:** baseline doc on `mac-native`.
- **Effort:** 30 min.

## 5. Effort estimate (whole Phase 5)

**Realistic: 5-6 hours focused** + 24h wall time for 5.6 scheduled-digest verification. Directive's 1 day estimate matches.

## 6. Stop-the-line gates

1. **5.4 daily-digest Sonnet prompt produces low-quality digests.** Iterate the prompt until it matches Captain reader-friendly bar.
2. **5.8 screenpipe queries return non-excluded sensitive data.** Bug in 5.2 exclusion list. Halt + fix.

## 7. Phase 5 → Phase 6 handoff

When Phase 5 completes:
- Universal screen observability across all officers
- Daily 08:00 digest in HQ group
- Reflection loop GUI-aware

Phase 6 (Cabinet worktrees + adapter contract) is independent substrate.

## 8. Sign-off

DRAFT ready for CTO tech review. Captain executes 5.2 (Screenpipe exclusion config) hands-on; rest CoS-executable.
