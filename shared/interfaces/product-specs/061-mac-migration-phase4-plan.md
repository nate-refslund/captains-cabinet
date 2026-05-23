# Spec 061 — Mac Migration Phase 4 Plan (cua-driver + Lead Enforcement)

- **Version:** v1.2 (CRO F2 TCC code-signing dependency surfaced)
- **Date:** 2026-05-23 (v1.0 → v1.1 07:20 → v1.2 08:05 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** READY for CTO re-confirm + Captain execution. **Phase 4 BLOCKED until Spec 058 v1.2 Checkpoint 1.10 (TCC code-signing) is complete.**

**v1.2 changelog — CRO Finding F2 dependency (Mac-native pre-staging brief 2026-05-23):**
- **(1) Pre-condition: code-signed + notarized officer binaries (Spec 058 v1.2 Checkpoint 1.10).** Without code-signing, TCC permissions (Accessibility + Screen Recording) don't persist across launches → cua-driver re-prompts on every restart → unusable. Phase 4 4.5 + 4.6 explicitly require Spec 058 1.10 PASS as a hard pre-condition. **Stop-the-line gate added.**
- **(2) cua-driver re-grant retry tolerates ONE permission loss but not recurring loss.** v1.1 Action #2 added a re-grant check + retry; v1.2 clarifies that recurring loss means code-signing is broken (NOT a retry problem) → escalate to Spec 058 1.10 rework.
- **CRO trigger:** 2026-05-23 07:16 UTC pre-staging brief F2.

**v1.1 changelog — CTO MUST-fold findings (msg 2026-05-23 06:58 UTC):**

**v1.1 changelog — CTO MUST-fold findings (msg 2026-05-23 06:58 UTC):**
- **(1) HIGHEST PRIORITY: 4.3 jq MCP-merge strategy.** v1.0 used `jq -s '.[0] * .[1]'` which is SHALLOW merge — silently OVERWRITES framework `mcpServers` (loses notion + linear + neon + library + etc.) with CoS overlay (only cua-driver). v1.1 uses explicit deep-merge preserving framework MCPs:
  ```bash
  jq -s '.[0] as $base | .[1] as $overlay
         | $base * $overlay
         | .mcpServers = ($base.mcpServers + $overlay.mcpServers)' \
     .mcp.json instance/agents/${OFFICER}/mcp.json
  ```
- **(2) cua-driver permission persistence in LaunchAgent context.** macOS sometimes loses Screen Recording grants for processes launched via launchd vs Terminal. 4.6 adds an explicit re-grant check + retry.
- **(3) Constitution-clause placement: framework, not preset.** Per Mac Migration Directive Part 3 the Lead-only computer-use clause goes in `framework/constitution-base.md`. 4.4 explicit. (Same answer applies to Phase 3 Lead-only Telegram + Phase 5 if more clauses arise — bundled here for cross-spec ratification.)
- **(4) reload-officer-mac.sh helper extraction.** Used 3x (Phase 2 bootout/bootstrap, Phase 3 product.yml-reload, Phase 4 mcp.json-reload). Cross-spec META: extract into `cabinet/scripts/reload-officer-mac.sh` and reference from each. Added as Checkpoint 4.5b.
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 4 ("cua-driver + Lead enforcement — 1 day")
- **Predecessors:** Spec 057-060 (Phases 0-3)
- **Successor:** Spec 062 (Phase 5 — Screenpipe integration)

---

## 1. Phase 4 goal (from directive)

CoS can autonomously drive macOS GUI applications via Telegram instruction. No other officer has this capability. Constitution carries the Lead-only computer-use clause.

## 2. Inputs from Phase 3

- Only CoS Telegram bot active; other officers Telegram-dark
- Constitution carries Lead-only Telegram clause
- Phase 1 cua-driver PINNED install complete (Spec 058 v1.1.1 Checkpoint 1.6)
- `cabinet/config/cua-driver-version.txt` records the pinned tag
- Officer-capabilities.conf supports the per-officer capability pattern

## 3. Captain ratifications + Phase 4-specific

- **Phase 4 NEW:** Lead-only computer-use clause to constitution.
- **CoS critical-analysis residual:** cua-driver vs Stagehand v3 routing distinction explicit in constitution.

## 4. Checkpoint structure

Phase 4 decomposes into **7 checkpoints**. Directive estimates 1 day; realistic 4-5 hours focused.

### Checkpoint 4.1 — Create `instance/agents/cos/mcp.json` CoS-only overlay

- **Pre-conditions:** Phase 3 complete; cua-driver pinned tag from Spec 058 Checkpoint 1.6 recorded.
- **Actions:**
  1. Create `instance/agents/cos/` directory if not present.
  2. Write `instance/agents/cos/mcp.json`:
     ```json
     {
       "mcpServers": {
         "cua-driver": {
           "command": "cua-driver",
           "args": ["mcp", "--claude-code-computer-use-compat"],
           "transport": "stdio"
         }
       }
     }
     ```
- **Golden eval:**
  - File exists; `jq .` parses cleanly
  - `cua-driver` resolvable in PATH (verifies pinned install from Spec 058 1.6)
- **Rollback:** `rm instance/agents/cos/mcp.json`.
- **Effort:** 10 min.

### Checkpoint 4.2 — Add `drives_computer` capability to officer-capabilities.conf

- **Pre-conditions:** 4.1 PASS.
- **Actions:**
  1. Add `drives_computer` capability column:
     - `cos: drives_computer=true`
     - All others: `drives_computer=false`
- **Golden eval:**
  - `grep "drives_computer" cabinet/officer-capabilities.conf` returns 5 lines, one `true` + four `false`
- **Rollback:** `git revert`.
- **Effort:** 5 min.

### Checkpoint 4.3 — Update `start-officer-mac.sh` to merge MCP overlay when `drives_computer: true`

- **Pre-conditions:** 4.2 PASS.
- **Actions:**
  1. In `start-officer-mac.sh`, gate MCP-overlay merge on `read_capability $OFFICER_ROLE drives_computer`:
     - If `drives_computer=true` → merge `instance/agents/$OFFICER_ROLE/mcp.json` into the framework-level `.mcp.json` for that officer's Claude Code invocation
     - If `drives_computer=false` → use framework-level `.mcp.json` only (no cua-driver MCP)
  2. **Use jq deep-merge preserving framework MCPs (v1.1 CTO #1 CRITICAL):**
     ```bash
     # Shallow merge (.[0] * .[1]) would OVERWRITE framework mcpServers with overlay-only.
     # Deep-merge preserves framework MCPs + adds overlay MCPs (e.g. cua-driver):
     jq -s '.[0] as $base | .[1] as $overlay
            | $base * $overlay
            | .mcpServers = ($base.mcpServers + $overlay.mcpServers)' \
        .mcp.json instance/agents/${OFFICER}/mcp.json \
        > /tmp/merged-mcp-${OFFICER}.json
     # Verify cua-driver AND framework MCPs (notion/linear/neon/library/etc) all present
     jq -e '.mcpServers | has("cua-driver") and has("notion") and has("library")' \
        /tmp/merged-mcp-${OFFICER}.json
     ```
- **Golden eval:**
  - `bash -n start-officer-mac.sh` passes
  - Dry-run with `OFFICER_ROLE=cos` shows merged mcp.json includes cua-driver
  - Dry-run with `OFFICER_ROLE=cto` shows mcp.json WITHOUT cua-driver
- **Rollback:** `git revert`.
- **Effort:** 30-45 min.

### Checkpoint 4.4 — Add Lead-only computer-use clause to constitution-base.md

- **Pre-conditions:** 4.3 PASS.
- **Actions:**
  1. Append to `framework/constitution-base.md`:

     ```
     ## Computer use is scoped to the Lead

     Only the officer with `drives_computer: true` (default: CoS) may invoke `cua-driver`
     or other GUI control tools. Other officers requesting GUI work must dispatch via
     Redis to the Lead. This is a coordination measure: it keeps a single source of
     truth for what is happening on the host machine.

     **cua-driver vs Stagehand v3 routing:** cua-driver controls native-macOS GUI
     applications (Figma, browsers, native apps); Stagehand v3 (per Spec 049 Gate 4)
     controls headless Chrome for web-app validation. Different surfaces. Stagehand
     is officer-callable (any officer with the Spec 049 self-review flow) without
     cua-driver scope. Officers reach for cua-driver only via the Lead.
     ```
  2. Run preset loader to regenerate `/tmp/cabinet-runtime/constitution.md`.
- **Golden eval:**
  - `grep -c 'Computer use is scoped to the Lead' framework/constitution-base.md` returns ≥1
  - `grep -c 'cua-driver vs Stagehand v3' framework/constitution-base.md` returns ≥1 (the routing distinction CoS critical-analysis residual)
  - Runtime constitution shows the clause
- **Rollback:** `git revert`.
- **Effort:** 10 min.

### Checkpoint 4.5 — Bootstrap CoS with cua-driver overlay (re-load)

- **Pre-conditions:** 4.1-4.4 PASS.
- **Actions:**
  1. Bootout existing CoS LaunchAgent (from Phase 2): `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist`
  2. Re-bootstrap with updated start-officer-mac.sh (which now merges cua-driver MCP for CoS): `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist`
  3. Inside CoS tmux: `claude mcp list` should show cua-driver as connected.
  4. Verify on CTO (should NOT have cua-driver): bootout/re-bootstrap CTO LaunchAgent, run `claude mcp list` inside CTO tmux — cua-driver should be absent.
- **Golden eval:**
  - `claude mcp list` on CoS includes `cua-driver` connected
  - `claude mcp list` on CTO does NOT include `cua-driver`
- **Rollback:** revert mcp.json + capability flag; re-bootstrap.
- **Effort:** 20-30 min.

### Checkpoint 4.6 — End-to-end Figma test (the directive's gate test)

- **Pre-conditions:** 4.5 PASS; Figma installed on Mac (or any native-macOS app for the test); some Sensed wireframes in Figma.
- **Actions:**
  1. Captain (via Telegram) DMs CoS: "Open Figma, find yesterday's wireframes for Sensed, and tell me what you see."
  2. Watch CoS:
     - Invoke cua-driver to launch Figma
     - Navigate to the project/file containing wireframes
     - Use cua-driver to capture the screen state (or use screenpipe per Phase 5 — but Phase 5 isn't done yet so cua-driver screenshot path)
     - Describe what's visible in the Telegram reply to Captain
- **Golden eval:**
  - Captain receives a coherent description of the wireframes in Telegram from CoS
  - cua-driver activity visible in CoS session logs
  - No other officer was involved
- **Rollback:** N/A — read-only test.
- **Effort:** 45-60 min (debug allowance for first cua-driver-via-Telegram round-trip).
- **Stop-the-line:** if cua-driver fails to launch Figma OR fails to interpret the visible content, halt and investigate cua-driver version + macOS permissions (Screen Recording + Accessibility from Spec 058 Checkpoint 1.8).

### Checkpoint 4.7 — Phase 4 baseline doc + commit

- **Pre-conditions:** 4.6 PASS.
- **Actions:**
  1. Write `docs/migration-phase4-baseline.md`:
     - mcp.json overlay path + content snippet
     - officer-capabilities.conf diff
     - start-officer-mac.sh overlay-merge logic
     - constitution-base.md clause added (with hash)
     - Figma test transcript (sanitized)
     - cua-driver version pinned tag
  2. Commit + push.
- **Golden eval:** baseline doc on `mac-native` branch.
- **Effort:** 20 min.

## 5. Effort estimate (whole Phase 4)

**Realistic: 4-5 hours focused** (directive's 1 day allows debug headroom for the cua-driver round-trip).

## 6. Stop-the-line gates

1. **4.5 cua-driver MCP fails to connect** (permission, version, SkyLight SPI). Halt + check Spec 058 Checkpoint 1.8 permissions + cua-driver pinned tag.
2. **4.6 Figma test inconsistent** (cua-driver describes wrong content). cua-driver visual-acuity is sometimes off; document the case + decide if Phase 5 Screenpipe enrichment improves it.

## 7. Phase 4 → Phase 5 handoff

When Phase 4 completes:
- CoS drives native macOS GUI via Telegram instruction
- Lead-only computer-use clause in constitution
- Pattern extends to Phase 5 (Screenpipe MCP — universal read-only, not Lead-scoped) + Phase 7 (full officer rollout)

## 8. Sign-off

This Phase 4 plan is **DRAFT, ready for CTO tech review.** Captain executes 4.6 hands-on (Telegram → Figma round-trip). All other checkpoints CoS-executable.
