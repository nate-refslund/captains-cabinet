# Concierge Install Runbook — Commercial Cabinet (refslund.ai)

**Spec:** 050 §3 Phase 1 FW-098
**Status:** SKELETON v0.1 — refined per first customer
**Author:** CTO (2026-05-20)
**Captain ratifications absorbed:** msg 2565 via CoS 2026-05-20 14:00 UTC (pricing 25k+5k/employee max 7, $50/day per-cabinet cap, DK+EU baseline, Annex III excluded, DK-only Phase 1 physical-reach, DA primary EN secondary).

This runbook codifies the 4-hour Day-0 install Nate executes per customer in Phase 1. Each customer install refines this document; first install marks the baseline.

---

## 0. Pre-arrival (T-7 days through T-1)

**Customer side:**

- [ ] Customer signs refslund.ai DPA (template from FW-100).
- [ ] Customer signs DPIA pre-filled by refslund.ai; DPO countersigns.
- [ ] Customer completes refslund.ai signup → Stripe checkout (25k DKK base + 5k DKK × N employees, N ≤ 7).
- [ ] Customer receives install token (signed JWT, embeds customer_id + employee_count + tier) via email.
- [ ] Customer purchases hardware: **M4 Mac Mini 24GB unified memory minimum (Pro chip recommended for 5+ officers; 32GB if 7 employees).**
- [ ] Customer schedules on-site setup with Captain (Phase 1: DK-only, physical reach).

**Captain side:**

- [ ] Capture customer employee_count + officer_mix preferences in refslund.ai admin (which roles among CFO/CTO/COO/CRO/CPO presets).
- [ ] Generate Cabinet install bundle (`.pkg` post-FW-102 ship; pre-ship: zipped framework + bootstrap script).
- [ ] Provision LiteLLM virtual key for this customer (FW-096): `cabinet_<customer_slug>`, model allowlist per tier, $50/day cap, Bedrock+Anthropic dual-route configured.
- [ ] Pre-author per-project agent-instructions.md templates per officer mix (CFO template, CTO template, etc. — Phase 1 hardcoded presets, FW-103 wizard later).

---

## 1. Day-0 install (on-site, ~4 hours)

### 1.1 Hardware + macOS first-boot (~30 min)

- [ ] Unbox MacMini; connect monitor + keyboard + ethernet (Wi-Fi acceptable for setup; ethernet preferred for production).
- [ ] macOS Setup Assistant: skip iCloud signin (customer-data isolation); create local admin user `cabinet`.
- [ ] System Settings → Software Update → install latest macOS minor (notarization compatibility).
- [ ] System Settings → Sharing → enable Remote Login (SSH) for support; document customer's choice to disable post-handoff.
- [ ] Install Xcode Command Line Tools: `xcode-select --install`.

### 1.2 Container runtime (~30 min)

**Captain decision pending (CoS DM): Colima vs OrbStack.** Default to Colima per Spec 050 §5 unless otherwise.

**Colima path:**
- [ ] `brew install colima docker docker-compose` (Homebrew prereq; bundle in `.pkg` post-FW-102).
- [ ] `colima start --cpu 4 --memory 8 --disk 60` (sized for 5 officers + Postgres + Redis + Stagehand Chromium).
- [ ] Verify `docker ps` returns clean output.

**OrbStack path** (if Captain selects):
- [ ] Download OrbStack from orbstack.dev → install → first-launch wizard → license activation (commercial).
- [ ] Verify Docker context active.

### 1.3 Cabinet bootstrap (~60 min)

- [ ] Clone framework: `git clone https://github.com/nate-step/captains-cabinet.git ~/cabinet` (Phase 1; .pkg installer post-FW-102 replaces this).
- [ ] Place install token: `~/cabinet/cabinet/.env` includes `REFSLUND_INSTALL_TOKEN=<customer JWT>`.
- [ ] Run `bash ~/cabinet/cabinet/scripts/cabinet-bootstrap.sh --commercial-tier --customer-slug <slug>`.
- [ ] Bootstrap validates token against LiteLLM proxy, provisions per-cabinet Postgres + Redis, configures audit log SQLite at `~/Library/Application Support/Cabinet/audit.sqlite`.
- [ ] Verify health: `bash ~/cabinet/cabinet/scripts/list-officers.sh` shows expected officer roster (0 officers until §1.5 hire flow).

### 1.4 Officer-mix selection (Phase 1 hardcoded preset, ~30 min)

- [ ] Confirm employee_count from token = expected count (1-7).
- [ ] Walk customer through officer-role options (CFO/CTO/COO/CRO/CPO presets).
- [ ] For each chosen officer: copy template from `presets/work/agents/<role>.md` into customer's `instance/agents/<role>.md`.
- [ ] Customer reviews per-project agent-instructions.md (template pre-filled per Spec 049): they sign off on conventions, anti-patterns, cap defaults.
- [ ] Hire officers via `bash ~/cabinet/cabinet/scripts/create-officer.sh ...` per chosen mix.

**Post-FW-103:** wizard replaces this step entirely (Phase 2).

### 1.5 Telegram bot provisioning (~30 min)

- [ ] Customer creates Telegram bot via @BotFather per pre-shared instructions (still manual until FW-001 unblocked).
- [ ] Customer pastes bot tokens into `~/cabinet/cabinet/.env`: `TELEGRAM_<UPPER_CUSTOMER>_CEO_TOKEN=...`.
- [ ] Start officers: `bash ~/cabinet/cabinet/scripts/start-officer.sh <role>` per officer.
- [ ] Customer DMs CEO officer "hello" via Telegram → officer replies → round-trip confirmed.

### 1.6 Audit + GDPR sanity (~30 min)

- [ ] Dashboard at `http://localhost:3000`: officer activity feed populates, customer sees their initial Telegram round-trip.
- [ ] Audit DB query: `sqlite3 ~/Library/Application Support/Cabinet/audit.sqlite 'SELECT * FROM officer_actions ORDER BY ts DESC LIMIT 10;'` returns entries.
- [ ] Test cap pause: temporarily set $0.50/day cap (override-via-CLI), trigger an Opus call, verify cabinet pauses + DM warns customer + auto-resume after officer-bumps-cap.
- [ ] Restore $50/day cap.
- [ ] Run erasure dry-run: `bash ~/cabinet/cabinet/scripts/cabinet-wipe.sh --dry-run`; verify signed deletion receipt JSON renders (FW-100).

### 1.7 Handoff briefing (~30 min)

- [ ] Walk customer through dashboard: activity feed, daily spend, audit log viewer, "Check for updates" placeholder (Sparkle ships FW-102).
- [ ] Explain $50/day cap: what happens at cap, how to extend one-shot, when to consider tier upgrade.
- [ ] Demo erasure command: customer initiates wipe, sees signed receipt, understands what gets deleted vs preserved.
- [ ] Set escalation expectations: refslund.ai support email + Captain phone for Phase 1 customers; Day-7 + Day-30 check-in scheduled.
- [ ] Customer countersigns concierge install completion form (FW-100 template).

---

## 2. Day-1 validation (next morning, ~30 min remote)

- [ ] SSH or remote-shell check (customer permission):
  - [ ] `redis-cli PING` → PONG (Redis up).
  - [ ] Officer heartbeats: all expected officers TTL <15min (alive).
  - [ ] Audit log: last 24h has officer-action entries.
- [ ] Customer Telegram DMs: confirm each officer replies; voice transcription works if voice-DM sent (FW-066 dependency).
- [ ] Spend check: yesterday's spend vs $50 cap; alert customer if >$25 (50%).

---

## 3. Day-7 + Day-30 check-ins (~15 min each, remote)

- [ ] Spend trend: weekly average, any cap-hits, customer cap-extend events.
- [ ] Officer activity: are officers being used? Any officer dormant 7+ days = scope check.
- [ ] GDPR posture: any DPO follow-up requests; any audit-log export requests.
- [ ] Update availability: customer prompted for any Cabinet update available (manual until FW-102).
- [ ] NPS-style customer satisfaction question; document for sales/case-study consideration.

---

## 4. Failure-mode quick refs

- **Bootstrap fails on Colima not running:** `colima start` → retry bootstrap.
- **LiteLLM proxy returns 401:** install token JWT expired or wrong customer_id; Captain re-issues from refslund.ai admin.
- **Officer Telegram silent:** check `tmux ls` on customer machine, verify officer pane shows Claude prompt running; restart officer if needed.
- **Audit DB locked:** SQLite WAL contention; rare; restart Cabinet container fixes.
- **Cap-hit unexpected:** verify no runaway loop in officer logs; check Claude cache hit rate (<70% = bug signal per Spec 050 §6).
- **macOS update bricks Cabinet (rare):** restore from Time Machine; rebuild Colima VM if needed; document in support hotfix log.

---

## 5. Open items pending Captain ratification

1. **Image distribution** (CTO P1 blocker #3): bundle 2GB Cabinet images in `.pkg` (offline-first, "your MacMini your data") vs first-launch registry pull (network dep). CoS recommends bundled; Captain DM pending.
2. **OrbStack vs Colima**: licensing purity (Colima MIT) vs polished UX (OrbStack commercial). Captain DM pending.
3. **Bedrock dual-path activation**: P1 ships with Anthropic-direct; Bedrock fallback wired but inactive until reseller terms clarify.
4. **Cabinet update mechanism in Phase 1** (before Sparkle FW-102): manual `git pull` + container rebuild OR scripted `cabinet-update.sh`? Recommend latter for Phase 1; flag for Captain decision.
5. **Customer support escalation surface** (CTO P2 flag #9): refslund.ai support email + Captain phone for Phase 1; staffing model for Phase 2+.

---

## 6. Revision log

| Version | Date | Author | Change |
|---|---|---|---|
| v0.1 | 2026-05-20 | CTO | Skeleton authored per Captain ratification msg 2565 + Spec 050 §3 Phase 1. Refines on first customer install. |
