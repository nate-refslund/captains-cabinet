# Cabinet Framework + Sensed Product Backlog — Prioritized View

> Maintained by CPO. Last refinement: 2026-05-23 22:00 UTC (cron).
> **Active phase: Mac Migration (Specs 057-065 ready for Captain execution) + Phase 1 commercial pipeline (FW-096-115) + Spec 049 v3.1 COO adversary fold.**
> Sensed: TestFlight live + PostHog Phase-0 wired (PR #559, 2026-04-25). Sensed backlog is stable — no new CTO work queued for Sensed until Mac migration phases are complete.
> Research absorbed this cycle: CRO competitive sweep (Devin $20 price collapse + Anthropic enforcement), audience psychology digest (trust-gap #1 for SMB + predictable pricing wins + 85%/15% framing), Anthropic ToS Q1 sweep (value-add carve-out strengthened + Claude Marketplace opportunity), Mac-native pre-staging (TCC code-signing already folded into Spec 058 v1.2), Claude Code daily catchup (S2 effort.level hooks + P1 /code-review → Spec 049 Gate 3 boundary clarification needed).

> **Note:** Linear is READ-ONLY archive post-Spec-039 cutover (2026-04-26). Canonical task store is Postgres `officer_tasks` (Spec 038). Shipped/blocked items below are historical references for context; current state is in /tasks dashboard.

---

## P0 — Blocking (resolve before anything else)

| Item | FW# | Spec | Owner | Status | Blocker |
|------|-----|------|-------|--------|---------|
| COO-as-DPO role-def amendment | FW-114 | — | CoS coord + CPO draft | **PENDING Captain ratification** | Gates Spec 055 v4 final ship + all customer GDPR commitments |
| Spec 049 v3.1 (COO adversary fold) | FW-095 | 049 v3.0.2 | COO adversary → CPO fold | **COO adversary PENDING** | Gates CTO Phase 2a build start |

---

## P0 — Mac Migration (Captain execution queue, sequential)

> All specs ready (v1.1 CTO-reviewed). Captain executes phases sequentially. CoS provides runbook + SSH verification gates.

> **Phase labels below verified against actual spec headers 2026-05-24 08:05 UTC** (CTO caught earlier drift where the table carried a pre-reorg phase plan). Spec headers are source of truth.

| Phase | Spec | Status | Estimated time |
|-------|------|--------|----------------|
| Phase 0 — Host state capture | 057 | ✓ COMPLETE 2026-05-22 | Done |
| Phase 1 — Mac base setup (binaries + TCC code-signing) | 058 v1.2 | **READY for Captain execution** | ~3-4h Captain |
| Phase 2 — Delete Docker, add launchd | 059 v1.1 | **READY** (awaits Phase 1 complete) | ~2-4h CTO + Captain |
| Phase 3 — Telegram topology collapse | 060 | READY | ~1-2h |
| Phase 4 — cua-driver + Lead Enforcement | 061 | READY | ~2-3h |
| Phase 5 — Screenpipe Integration | 062 | READY | ~2-3h |
| Phase 6 — Cabinet Worktrees + Adapter Contract | 063 | READY | ~2h |
| Phase 7 — Full Officer Rollout + Observability (48h soak) | 064 | READY | 48h soak |
| Phase 8 — Documentation + Release | 065 v1.1 | READY | ~3-4h |

**Key dependency (from Spec 058 v1.2 CRO fold):** Phase 1 step 1.10 requires Apple Developer ID certificate import before any officer binary is code-signed. Apple Developer Program already enrolled (Captain msg 2576). TCC permission persistence across restarts depends on this — do not defer.

---

## P1 — Commercial Phase 1 (spec pipeline, Captain-facing)

> These specs are drafted (tasks #28-33 complete). CTO implementation blocked on Mac migration completing first (substrate changes). CPO spec lookahead continues in parallel.

| Item | FW# | Spec | Status | Notes |
|------|-----|------|--------|-------|
| LiteLLM proxy + virtual keys + daily cap | FW-096 | 051 v5 | Spec COMPLETE | CTO impl after Phase 5 (Neon/LiteLLM cutover) |
| Customer audit log | FW-097 | 052 v3 | Spec COMPLETE | CTO impl Phase 1b |
| Concierge install runbook | FW-098 | 053 v3 | Spec COMPLETE | Customer templates also complete (see below) |
| refslund.ai signup + Stripe billing | FW-099 | 054 v3 | Spec COMPLETE | CTO impl Phase 2 |
| GDPR baseline (ROPA/DPA/DPIA/erasure) | FW-100 | 055 v4 | **Gated on FW-114** | COO-as-DPO ratification required first |
| Customer dashboard MVP | FW-101 | 056 v2 | Spec COMPLETE | CTO impl Phase 1b |

### Customer templates (all complete, ready for first-customer use)
| Template | File | Status |
|----------|------|--------|
| Discovery call script | cabinet/customer-templates/discovery-call-script.md | ✓ Ready |
| Welcome Day 0 email | cabinet/customer-templates/welcome-day-0.md | ✓ Ready |
| Pre-install checklist | (in Spec 053 §Stage 3) | ✓ Ready |
| Install-day GDPR walkthrough | cabinet/customer-templates/install-day-gdpr-walkthrough.md | ✓ Ready |
| Week-1 cheat sheet | cabinet/customer-templates/cheat-sheet-week-1.md | ✓ Ready |
| Day-7 check-in | cabinet/customer-templates/check-in-day-7.md | ✓ Ready |
| Concierge offboarding script | cabinet/customer-templates/concierge-offboarding-script.md | ✓ Ready |

---

## P1 — CPO spec pipeline (lookahead, no CTO blocked on these yet)

### Spec 049 v3.1 amendments (fold research cycle findings)
- **P1a.** Gate 3 adversary spawns: specify `xhigh` effort level (from Claude Code P2 update — new xhigh tier). Currently unspecified in Gate 3 subagent prompt.
- **P1b.** `/code-review` vs Gate 3 boundary: Claude Code's new `/code-review` command overlaps with Gate 3 (officer-spawned diff critique). Need explicit boundary note in spec — Gate 3 = CPO-owned officer-spawned adversary; `/code-review` = direct user-invokable. NOT consolidated. Document in Phase 1 skills section.
- **P1c.** Spec 049 Phase 2a ready to start after v3.1 COO adversary fold clears (task #27 completes).

### FW-115 H3 defense-dossier (CPO authors)
- Draft `shared/interfaces/legal/anthropic-value-add-architecture.md`
- Five-criterion mapping: multi-stage pipeline, proprietary data, custom post-processing, domain-specific logic, integrations meaningless without product layer (Anthropic's own published definition — Q1 ToS sweep)
- Sections: architecture overview, officer-workflow evidence, audit-log chain, governance layer, Captain pattern absorption, Telegram-DM-as-interface, multi-tenancy model
- CRO + CoS adversary review before Library Compliance Space record
- **Trigger:** wait for 1+ paying customer (A13 leverage posture). But draft now so it's ready.

### Spec 053 v3 amendment candidates (from audience psychology brief 2026-05-23)
1. **Stage 1 discovery call framing**: add "here's what Cabinet does reliably today / here's what's R&D-grade" honest-disclosure beat. Trust-by-honesty > trust-by-marketing (Wharton April 2026 + M1 Anthropic enforcement context).
2. **Stage 5 post-install cheat sheet**: focus on 3-5 *meaningful goals* in week 1 (not feature tour). Wharton: users accomplish goals, don't wander features.
3. **Anti-autonomous positioning**: Stage 1 script should NOT say "Cabinet will run your business autonomously." Instead: "augmented executive layer with officer-in-loop on architecture and the bigger calls." Devin/Cursor are foils (see competitive sweep M2 pricing); Cabinet is a different category. 85%/15% honest framing belongs here.
4. **Devin objection-handling**: customer will cite "$20/mo Devin" in discovery calls. Prepared answer: vertical-anchored exec-layer service vs generic dev agent. Not 1:1 comparable. Add to discovery call script FAQ section.

---

## P2 — Phase 2 commercial spec lookahead

| Item | FW# | Priority | Spec needed | Notes |
|------|-----|----------|-------------|-------|
| Notarized .pkg installer + Sparkle 2 | FW-102 | P2 | Yes — CPO spec | Gated on FW-098 runbook proving install works |
| Hire-an-officer wizard (GUI) | FW-103 | P2 | Yes | Phase 2 onboarding |
| Screenpipe integration (7d, FileVault) | FW-104 | P2 | Yes | After mac-native Phase 7 soak |
| Customer-facing CU layer (Stagehand v3) | FW-105 | P2 | Yes — Spec 049 successor | After FW-095 ships |
| Self-serve onboarding (refslund.ai → install) | FW-107 | P2 | Yes | Folds FW-099 + FW-102 |
| Claude Marketplace partnership watch | — | Watch | No spec yet | Monitor GA + partner program docs |

---

## Sensed — Stable (no new CPO work needed this cycle)

> Sensed backlog is stable pending Mac migration. TestFlight live. No new Sensed CTO work should queue until mac-native Phase 7 soak clears. PMF gate v1.1 (D14≥40%) stands.

| Item | Priority | Spec | Status |
|------|----------|------|--------|
| Implementation intentions onboarding | Medium | Spec 024 | Ready to queue (post-migration) |
| Echo chamber mitigation | Medium | Spec 026 | Ready to queue |
| Dual dates + dual locations | Medium | Spec 028 | Ready to queue |
| Neutral reflection mechanic | Medium | Spec 029 | In Progress (CTO — paused for migration) |
| Dynamic cluster naming | — | Spec 027 | Next after 029 |
| Earth Map Strava-model locations | Medium | Spec 030 | XL, queue post-migration |

---

## Captain Decisions (key — updated 2026-05-23)
- Mac migration: 8-phase native (Captain msg 2599), 1-cabinet-then-clone-to-3 fleet plan (msg 2603)
- LaunchAgent pattern for all officers; LaunchDaemon for background workers
- Cost tracking: logging always ON, enforcement OFF for personal/STEP-internal, ON for commercial customers (Spec 059 §2.2)
- COO-as-DPO: pending ratification (Article 38(6) conflict with CoS-as-DPO)
- H3 value-add carve-out: calculated-bet posture (no Anthropic outreach pre-leverage per A13)
- Devin price collapse ($500→$20): update discovery-call objection-handling, not a pricing adjustment
- Spec 049 COO adversary review: final gate before CTO Phase 2a build starts
- Sensed launch: quality-gated (TestFlight live; PMF gate D14≥40% target)
- Pricing (Cabinet): 25k DKK base + 5k DKK/employee — predictable bundled subscription, not ACU metered
