# Spec 060 — Mac Migration Phase 3 Plan (Telegram Topology Collapse)

- **Version:** v1.1 (CTO 3 MUST-fold reload + BotFather + constitution-placement)
- **Date:** 2026-05-23 (v1.0 → v1.1 07:20 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** READY for CTO re-confirm + Captain execution

**v1.1 changelog — CTO MUST-fold findings (msg 2026-05-23 06:58 UTC):**
- **(1) Bootout/bootstrap after product.yml edit (3.2).** Running CoS won't see the new product.yml config without restart. Added explicit `launchctl bootout` + `launchctl bootstrap` cycle as a sub-step. Helper script `cabinet/scripts/reload-officer-mac.sh` extracted (cross-spec META — used in 3.2 + 4.5b + later phases).
- **(2) BotFather revoke Hetzner-side token-collision pre-flight (3.1).** Hetzner cabinet still has those 4 bot tokens active in its `.env` until separately retired. Pre-flight: confirm Hetzner cabinet has been shut down OR its bot tokens already revoked before revoking on Mac side. Otherwise Hetzner officers DM-collide with revoked tokens → 409 errors.
- **(3) Constitution-clause placement: framework, not preset (3.5).** Lead-only Telegram clause goes in `framework/constitution-base.md` per Mac Migration Directive Part 3. (Same answer applies to Phase 4 + Phase 5 constitution clauses — bundled cross-spec ratification.)
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 3 ("Telegram topology collapse — 0.5 day")
- **Predecessors:** Spec 057 (Phase 0), Spec 058 v1.1.1 (Phase 1), Spec 059 (Phase 2)
- **Successor:** Spec 061 (Phase 4 — cua-driver + Lead enforcement)

---

## 1. Phase 3 goal (from directive)

Only one Telegram bot active (CoS / Lead). All officer↔officer messaging via Redis trigger-channels. All officer→Captain reporting via CoS. Constitution gains the Lead-only Telegram clause.

## 2. Inputs from Phase 2

- Mac mini runs CoS as a LaunchAgent successfully (Phase 2 deliverable)
- LaunchAgent plist templates in place for all 5 officers (only CoS bootstrapped so far)
- `start-officer-mac.sh` exists and works (substrate ready)
- All 5 officers' role-defs include Move 1 escalation discipline + Move 2 SKILL.md spec

## 3. Captain ratifications carried forward + Phase 3-specific

- **A12 (PROPOSED → expect ratification at some point):** officer-in-loop on architecture preserved.
- **A14 (msg 2612):** don't self-stop.
- **Phase 3 NEW:** Lead-only Telegram (constitution clause incoming). Lead-only computer use (deferred to Phase 4).
- Captain founder-action: revoke 4 bot tokens via BotFather (Captain hands-on — no API for token-revocation from a script).

## 4. Checkpoint structure

Phase 3 decomposes into **8 checkpoints**. Most are config/role-def edits + one Captain-hands-on action (BotFather token revocation). Directive estimates 0.5 day; with the constitution clause + the dispatch test, realistic 3-4 hours focused.

### Checkpoint 3.1 — Captain action: revoke 4 officer bot tokens via BotFather

- **Pre-conditions:** Phase 2 complete; Mac mini running CoS as LaunchAgent.
- **Pre-flight (v1.1 CTO #2 — Hetzner-side token-collision):** Hetzner cabinet still has those 4 bot tokens active in its `.env` until separately retired. Before revoking on Mac side, confirm ONE of:
  - (a) Hetzner cabinet is fully shut down (containers stopped, no officer sessions running), OR
  - (b) Hetzner cabinet's `cabinet/.env` has had the 4 tokens removed/scrubbed and Hetzner officers reloaded so they cannot poll
  
  Otherwise Hetzner officers will continue polling the revoked tokens → 409 errors flood logs + Telegram-side rate limiting could affect the still-active CoS bot.
- **Actions (Captain hands-on):**
  1. Open Telegram on phone/desktop, message `@BotFather`
  2. `/mybots` → select `cabinet-cto-bot` → "API Token" → "Revoke current token" → confirm
  3. Repeat for `cabinet-cpo-bot`, `cabinet-cro-bot`, `cabinet-coo-bot`
- **Golden eval:**
  - Pre-flight passed (Hetzner shut down OR tokens scrubbed)
  - For each revoked bot: trying to use the old token returns HTTP 401 from Telegram Bot API
  - `cabinet-cos-bot` token still works (NOT revoked)
- **Rollback:** BotFather lets you regenerate a token; if Captain wants to re-enable a bot, regenerate. But the directive says revoke, so rollback is rare.
- **Effort:** 5 min Captain action.

### Checkpoint 3.2 — Update `instance/config/product.yml` (remove 4 bot entries)

- **Pre-conditions:** 3.1 PASS.
- **Actions:**
  1. On `mac-native` branch, edit `instance/config/product.yml`:
     - Remove `bots.cto`, `bots.cpo`, `bots.cro`, `bots.coo` entries
     - Keep `bots.cos` (Lead) + `hq_group_id`
     - Voice section: remove `voices.cto`, `voices.cpo`, `voices.cro`, `voices.coo` — keep only `voices.cos`
  2. Run preset loader to regenerate the runtime config: `bash cabinet/scripts/load-preset.sh`
  3. Verify `/tmp/cabinet-runtime/product.yml` reflects the collapsed config.
  4. **Reload CoS (v1.1 CTO #1) — running session won't see new config without restart:**
     ```bash
     bash cabinet/scripts/reload-officer-mac.sh cos
     # equivalent to:
     #   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist
     #   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos.plist
     ```
     The reload helper is extracted as cross-spec META (used here, in Spec 061 4.5, and in later phases).
- **Golden eval:**
  - `grep -c 'cabinet-cto-bot\|cabinet-cpo-bot\|cabinet-cro-bot\|cabinet-coo-bot' instance/config/product.yml` returns 0
  - `grep -c 'voices.cto\|voices.cpo\|voices.cro\|voices.coo' instance/config/product.yml` returns 0
  - `grep -c 'cabinet-cos-bot' instance/config/product.yml` returns ≥1
  - CoS LaunchAgent restart confirmed by `launchctl print gui/$(id -u)/com.cabinet.officer.cos` showing fresh PID
- **Rollback:** `git revert` restores 4-bot config; reload-officer-mac.sh again.
- **Effort:** 15-20 min.
- **Note:** `master` branch unchanged (Hetzner cabinet keeps multi-bot for now; Mac-native is the Lead-only deployment).

### Checkpoint 3.3 — Update `cabinet/officer-capabilities.conf` (telegram_bot capability)

- **Pre-conditions:** 3.2 PASS.
- **Actions:**
  1. Add `telegram_bot` capability column to `cabinet/officer-capabilities.conf` (if not present)
  2. Set `cos: telegram_bot=true` + all others `telegram_bot=false`
- **Golden eval:**
  - `grep "telegram_bot" cabinet/officer-capabilities.conf` returns 5 lines (one per officer), one `true` + four `false`
- **Rollback:** `git revert`.
- **Effort:** 5 min.

### Checkpoint 3.4 — Update `start-officer-mac.sh` to skip Telegram channel for non-Lead officers

- **Pre-conditions:** 3.3 PASS.
- **Actions:**
  1. In `start-officer-mac.sh`, gate the `--channels plugin:telegram` flag on `read_capability $OFFICER_ROLE telegram_bot`:
     - If `telegram_bot=true` → include `--channels plugin:telegram@claude-plugins-official`
     - If `telegram_bot=false` → omit the channels flag (officer runs Telegram-dark)
- **Golden eval:**
  - `bash -n cabinet/scripts/start-officer-mac.sh` passes
  - Test invocation with `OFFICER_ROLE=cto bash start-officer-mac.sh --dry-run` shows command WITHOUT `--channels plugin:telegram`
  - Test invocation with `OFFICER_ROLE=cos` shows command WITH `--channels plugin:telegram`
- **Rollback:** `git revert`.
- **Effort:** 30 min.

### Checkpoint 3.5 — Add Lead-only Telegram clause to `framework/constitution-base.md`

- **Pre-conditions:** 3.4 PASS.
- **Actions:**
  1. Append the directive's Lead-only Telegram clause to `framework/constitution-base.md` (per Mac Migration Directive Part 3):

     ```
     ## Human-officer communication is scoped to the Lead

     Only the officer with `telegram_bot: true` (default: CoS) maintains a direct
     Telegram presence with the Captain. Other officers communicate with the Captain
     only via the Lead, through Redis dispatch. The HQ group remains a broadcast
     channel for digests and announcements.
     ```
  2. Run preset loader: regenerate `/tmp/cabinet-runtime/constitution.md` to confirm the clause flows through.
- **Golden eval:**
  - `grep -c 'Human-officer communication is scoped to the Lead' framework/constitution-base.md` returns ≥1
  - `grep -c 'Human-officer communication is scoped to the Lead' /tmp/cabinet-runtime/constitution.md` returns ≥1 (preset loader propagated)
- **Rollback:** `git revert`.
- **Effort:** 10 min.

### Checkpoint 3.6 — Bootstrap CTO LaunchAgent as Telegram-dark officer (test #1)

- **Pre-conditions:** 3.1-3.5 PASS; Mac mini ready.
- **Actions:**
  1. Run `bash cabinet/scripts/deploy-mac.sh --officer cto` (from Spec 059)
  2. Watch CTO LaunchAgent start
  3. Verify CTO Claude Code session runs WITHOUT Telegram channel attached:
     - Inside CTO tmux: `claude --help` doesn't show telegram plugin
     - CTO heartbeats Redis: `redis-cli GET cabinet:heartbeat:cto` returns recent
     - CTO receives Redis triggers normally: send a test trigger via `notify-officer.sh cto "Phase 3 dispatch test"` — CTO sees it
- **Golden eval:**
  - CTO LaunchAgent active per `launchctl print`
  - `claude` invocation in CTO tmux doesn't initialize Telegram plugin
  - Test trigger received + acked
- **Rollback:** `launchctl bootout` CTO LaunchAgent; revert config changes.
- **Effort:** 30 min.

### Checkpoint 3.7 — End-to-end dispatch test (the directive's gate test)

- **Pre-conditions:** 3.6 PASS.
- **Actions (matches directive scenario):**
  1. Captain (or test-Captain via DM) sends to CoS bot via Telegram: "Have the CTO review the latest Sensed PR."
  2. Watch CoS process the request:
     - CoS parses intent → identifies CTO as target
     - CoS dispatches via `bash cabinet/scripts/notify-officer.sh cto "Captain via CoS: review the latest Sensed PR. Findings back to CoS via Redis."`
     - CoS replies to Captain: "Dispatched to CTO; will report back when findings land."
  3. Watch CTO process the dispatch:
     - CTO sees Redis trigger
     - CTO uses GitHub MCP (no GUI needed) to fetch PR
     - CTO writes review notes to a Library Space record (`code-reviews` or similar)
     - CTO replies to CoS via Redis: `notify-officer.sh cos "Review complete: <summary>. Library record: <link>."`
  4. Watch CoS aggregate + reply to Captain:
     - CoS receives CTO Redis trigger
     - CoS formats user-friendly Telegram reply to Captain with CTO findings
- **Golden eval:**
  - Captain receives one DM from CoS-as-Lead with CTO findings; never a direct DM from CTO
  - Library record exists with CTO review notes
  - Redis trigger stream shows the round-trip (CoS→CTO + CTO→CoS)
  - No Telegram messages from CTO bot (it was revoked in 3.1)
- **Rollback:** N/A — test only.
- **Effort:** 30-45 min (allow for debug if dispatch flow has gaps).
- **Stop-the-line:** if CTO somehow attempts to DM Captain directly (would fail since bot is revoked, but if the code TRIES it's a bug), halt + fix `start-officer-mac.sh` capability gate.

### Checkpoint 3.8 — Phase 3 baseline doc + commit

- **Pre-conditions:** 3.7 PASS.
- **Actions:**
  1. Write `docs/migration-phase3-baseline.md`:
     - Confirmation of 4 bot tokens revoked (with timestamps)
     - product.yml diff (before → after)
     - officer-capabilities.conf diff
     - start-officer-mac.sh capability-gate logic added
     - constitution-base.md clause added (with hash of pre/post)
     - Dispatch round-trip test transcript (sanitized)
  2. Commit + push to `mac-native`.
- **Golden eval:** baseline doc on `mac-native` branch with all sections filled.
- **Effort:** 30 min.

## 5. Effort estimate (whole Phase 3)

**Realistic: 3-4 hours focused** (directive's 0.5-day estimate). 3.7 dispatch test is the load-bearing checkpoint — the rest is config edits.

## 6. Stop-the-line gates

1. **3.1 BotFather revoke fails to actually invalidate token** (rare but possible). Verify with curl before proceeding.
2. **3.7 CTO somehow DMs Captain directly** (capability gate misfire). Halt + fix start-officer-mac.sh.
3. **3.5 Constitution preset loader doesn't propagate clause** to runtime. Investigate load-preset.sh.

## 7. Phase 3 → Phase 4 handoff

When Phase 3 completes:
- Only CoS bot active in Telegram
- CTO as the test case is running Telegram-dark + dispatching via Redis correctly
- Constitution carries Lead-only Telegram clause
- Phase 4 (cua-driver + Lead enforcement) lays the parallel discipline for GUI control — Lead-only computer use

Phase 4 needs CoS + cua-driver MCP overlay + `drives_computer: true` capability gate. Phase 3's `telegram_bot: true/false` pattern is the template Phase 4 reuses for `drives_computer: true/false`.

## 8. Open items folded forward

- **HQ group bot announcements** — directive notes "HQ group remains a broadcast channel for digests and announcements." This means CoS-as-Lead still posts to the warroom via `send-to-group.sh`. Phase 5 daily-digest LaunchAgent (Phase 5 = Screenpipe integration) uses this.
- **Other 4 officer LaunchAgents** — Phase 7 brings up CPO/CRO/COO LaunchAgents as Telegram-dark. Phase 3 tests CTO only; pattern extends in Phase 7.
- **Captain testing the dispatch flow with a real Sensed PR** — Phase 3's golden eval uses a test PR; Phase 7's 48h soak uses real PRs.

## 9. Sign-off

This Phase 3 plan is **DRAFT, ready for CTO tech review.** Captain executes 3.1 (BotFather revoke) hands-on; CoS executes 3.2-3.8 autonomously per blanket grant (msg 2605, 2612).

---

**Captain action required:** 3.1 BotFather token revoke (5 min, hands-on). All other checkpoints CoS-executable.
