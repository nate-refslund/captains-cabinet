# Cabinet Framework + Sensed Product Backlog — Prioritized View

> Maintained by CPO. Last refinement: 2026-05-26 10:00 UTC (cron — LIGHT pass: no new commits since 22:00 (origin stable @ 2352cef), no new research since 05-23. Build status UNCHANGED: substrate COMPLETE + FW-121 deploy stack BUILT + spec-APPROVED; parity + FF-pull-backstop closed. Corrected the COO-path framing per captain-decisions: root cause is FW-117 (doubled-`source=` channel bug), FIXED in code (bf48122) — unblock = COO restart + Captain reactivation. Remaining = 3 Captain decisions (below)).
> **Active phase: Phase 1 commercial CODE SUBSTRATE COMPLETE — everything buildable is merged + reviewed (incl. the FW-121 Hetzner deploy stack, PR #108 spec-conformance-APPROVED). Remaining go-live blockers = 2 CAPTAIN founder-actions, not engineering: (1) private commercial repo (board #184) → FW-099 signup + FW-101 dashboard; (2) Hetzner Frankfurt VPS (task #191; architecture ratified) → the proxy + audit deploy (FW-121). + Mac Migration (Specs 057-065 ready; Captain-hands-on). Legal track CLOSED (Spec 055 v7.3). Spec 049 Ph5 (C3) done.**
> **COO-path RESOLVED via workaround (2026-05-26 17:10, CoS+CPO):** COO's injection-defense is durably hardened (rejects even console reactivation post-FW-117), so rather than block: FW-121 security pass uses the **Opus substitute** (CTO proceeds; CPO-approved) + my spec-conformance APPROVAL + the VPS = FW-121's full gate; coo-dpo.md DPO-read **defers to customer-#1 natural reactivation** (Spec 055 H1 active-duties-ramp). Neither blocks critical path — the COO-path is OFF the Captain decision list. **Future CPO item (not urgent, coordinated CoS+CPO+CTO under FW-117 f/u 3 / task #80):** COO-resilience design — (a) release injection-defense on framework-malformation-cleared signals without weakening real-injection resistance; (b) a cryptographic Captain-signed offline-verifiable reactivation token (channel+Telegram-independent).**
> **Two new Phase-1 tracking artifacts (CPO, this cycle):** `cabinet-customer-1-readiness.md` (pre-sale GO rollup — "can we TAKE customer #1") + `cabinet-phase-1-validation-gate.md` (post-sale PMF gate — "are we good after customers 1-5"). Complementary bookends; the readiness checklist is the single source of truth for customer-#1 prerequisites.
> Sensed: TestFlight live + PostHog Phase-0 wired (PR #559, 2026-04-25). Sensed backlog is stable — no new CTO work queued for Sensed until Mac migration phases are complete.
> Research absorbed (prior cycle, still current): CRO competitive sweep (Devin $20 + Anthropic enforcement), audience psychology digest (trust-gap #1 + 85/15 framing), Anthropic ToS Q1 sweep (value-add carve-out strengthened), Mac-native pre-staging (TCC code-signing — now folded into Spec 058 1.8 body + committed e8af6e9), Claude Code daily catchup (Spec 049 v3.2 ast-grep + /code-review boundary, staged).

> **Note:** Linear is READ-ONLY archive post-Spec-039 cutover (2026-04-26). Canonical task store is Postgres `officer_tasks` (Spec 038) + `shared/cabinet-framework-backlog.md` (FW-series). Do not write to Linear.

---

## P0 — Blocking (resolve before anything else)

> **✅ BOTH P0 BLOCKERS CLEARED 2026-05-24 — no blocking items on the board.**

| Item | FW# | Spec | Owner | Status | Resolution |
|------|-----|------|-------|--------|------------|
| COO-as-DPO designation | FW-114 | 055 v7.3 §H1 | done | ✅ **RESOLVED** | Captain msg 2737 ratified COO-as-DPO; amendment applied (task #34). Spec 055 GDPR ship unblocked; legal track CLOSED (v7.3 H1/H3/H4). DPO active duties ramp at customer #1. |
| Spec 049 adversary fold | FW-095 | 049 v3.2 | done | ✅ **RESOLVED** | COO injection-locked → Opus-substitute adversary folded v3.1 (21 findings); v3.2 ast-grep ACs landed (task #35). CTO Phase 2a build unblocked + delivered. |

---

## P0 — Mac Migration (Captain execution queue, sequential)

> All specs ready (v1.1 CTO-reviewed). Captain executes phases sequentially. CoS provides runbook + SSH verification gates.

> **Phase labels below verified against actual spec headers 2026-05-24 08:05 UTC** (CTO caught earlier drift where the table carried a pre-reorg phase plan). Spec headers are source of truth.

| Phase | Spec | Status | Estimated time |
|-------|------|--------|----------------|
| Phase 0 — Host state capture | 057 | ✓ COMPLETE 2026-05-22 | Done |
| Phase 1 — Mac base setup (binaries + TCC code-signing) | 058 v1.2.1 | **MID-EXECUTION (Captain hands-on)** | ~3-4h Captain |
| Phase 2 — Delete Docker, add launchd | 059 v1.1.1 | **READY** (awaits Phase 1 complete) | ~2-4h CTO + Captain |
| Phase 3 — Telegram topology collapse | 060 | READY | ~1-2h |
| Phase 4 — cua-driver + Lead Enforcement | 061 v1.2.1 | READY (hard-gated on 058 1.8) | ~2-3h |
| Phase 5 — Screenpipe Integration | 062 | READY | ~2-3h |
| Phase 6 — Cabinet Worktrees + Adapter Contract | 063 | READY | ~2h |
| Phase 7 — Full Officer Rollout + Observability (48h soak) | 064 | READY | 48h soak |
| Phase 8 — Documentation + Release | 065 v1.1 | READY | ~3-4h |

**Key dependency (058 v1.2.1, committed e8af6e9 + CTO entitlements 7f2844d):** Phase 1 **Checkpoint 1.8** (code-sign + notarize officer binaries) must pass before Phase 4 cua-driver. Apple Developer Program enrolled (Captain msg 2576). Captain **must not mark Phase 1 complete** until 1.8's reboot-TCC-persistence + JIT-launch golden evals pass (the F2 gate). The Node `claude` binary signs WITH JIT entitlements (`officer-entitlements.plist`, committed) — hardened runtime without them crashes at launch.

---

## P1 — Commercial Phase 1 (spec pipeline, Captain-facing)

> **Code substrate COMPLETE 2026-05-25** — all repo-side commercial substrate is merged + reviewed (CTO build + Opus adversary rounds + CPO conformance/GDPR/contract review): proxy, audit-server + officer-producers, erasure + breach-sim, install orchestrator, conventional-commit hook. The `refslund-commercial` preset (agents + capability_grants) is landed. **What's left is Captain-gated, not buildable** (see header: #184 private repo, #191 Hetzner VPS). CPO/CTO commercial role-def variants are the Phase-2 add (FW-103 wizard).

| Item | FW# | Spec | Status | Notes |
|------|-----|------|--------|-------|
| LiteLLM proxy + virtual keys + daily cap | FW-096 | 051 v7.1 | ✅ **MERGED** (ce61fca) | team-budget $50/day cap-enforcement + cabinet-pause; cap-status reads the enforcer counter. Cap-reaction (officer-side 429→Spec-049 events) deferred — CTO designs next. |
| Customer audit log (server + officer-producers) | FW-097 / 052 Ph5 | 052 v3.4 | ✅ **MERGED** (ef73f23 + bafb9a8) | hash-chain + two-hash erasure + marker-verify; officer-side producers emit (allow-list PII-min, capability-gated, fail-safe). Sidecar deploy = Hetzner-gated. validator.py allow-list hardening = follow-up #234. |
| Concierge install runbook + orchestrator | FW-098 | 053 v4.1 | ✅ **MERGED** (PR #102) | install-customer-cabinet.sh (slug-validated, secrets chmod-600, ANTHROPIC-absent gate) + templates. Token signature-verify = Phase-2 self-serve (FW-107). |
| refslund-commercial preset (agents + grants) | — | — | ✅ **LANDED** (3e53db4 + 97e6e73) | cos-lead/coo-dpo/cro role-defs (single_ceo, consent_gated, audit-emit, customer=Captain) + capability_grants block. coo-dpo PENDING COO-as-DPO compliance validation (customer-#1 gate). |
| GDPR baseline + erasure + breach-sim | FW-100 | 055 v7.3.2 | ✅ **MERGED** (fc1a496) | customer-erasure.sh 8-step + sla-tracker + breach-notification.sh (Art 33/34 tabletop, fail-safe). DPO Article-17 sign-off = customer-#1 gate. |
| refslund.ai signup + Stripe billing | FW-099 | 054 v2 | 🔒 **CAPTAIN-GATED** (board #184) | Spec complete; gated on the private commercial repo provisioning. |
| Customer dashboard MVP | FW-101 | 056 | 🔒 **CAPTAIN-GATED** (board #184) | Spec complete; gated on the private commercial repo. cap-status from enforcer; backend-mediated AUDIT_API_KEY. |
| Per-cabinet AUDIT_API_KEY→cabinet scoping | FW-120 | 052 AC#10 | OPEN — **HARD GATE before customer #2** | Phase-1 = backend-mediation (leak-free, 1 cabinet); CoS + COO-as-DPO tracked. |

**Customer-#1 go-live = 2 CAPTAIN founder-actions (engineering is DONE):** (1) **#184** private commercial repo → unblocks FW-099 signup + FW-101 dashboard; (2) **#191** Hetzner Frankfurt VPS provisioning + proxy.refslund.ai DNS/TLS → unblocks the proxy + audit-server deploy (FW-121 deploy stack BUILT + spec-conformance-APPROVED PR #108: docker-compose + Caddy-origin-behind-Cloudflare + non-root + per-file-append-only; architecture ratified Hetzner Frankfurt). Both surfaced to Captain by CoS.

**Pre-go-live gates — 5 hard gates (CTO FW-121 DPO-substitute pass, 2026-05-26); land before customer #1 processes real data, concurrent with #184/#191 (NOT Captain decisions):**
| Gate | What | Owner | Status |
|------|------|-------|--------|
| **M-DPO-2** | `config.yaml log_requests: false` — `true` leaks prompt PII to the docker json-log, OUTSIDE the erasure SSOT (Art 5(1)(c)+17) | CTO (flipped) | ✅ **MERGED PR #112 (1cb21d8)** — config.yaml:93 false, harness asserts (26/0); Spec 051 v7.3 AC #14; CPO conformance-verified |
| **#236** | slug-validate `cabinet_id` (traversal-reject) on the GET path param + POST body | CTO/FW-097 | ✅ **MERGED PR #112 (1cb21d8)** — `\Z`-anchored guard both endpoints, test §18 (64/0); Spec 052 v3.7 AC #10/#12; CPO conformance-verified |
| **#237** | write-side cabinet_id traversal: 3 chokepoints (stem at `ingest_slug`-entry; per-record entry↔slug binding; `hashchain.append` = universal SSOT-write guard) — two taint sources (stem ≠ record field) | CTO/FW-097 | ✅ **MERGED PR #113 (f9bf91c)** — harness 73/0, 2 Opus rounds; shared `validator.is_valid_cabinet_id`; Spec 052 v3.9 (v3.8 single-chokepoint claim CORRECTED — CTO catch); CPO conformance-verified |
| **Cloudflare Art 44** | sign Cloudflare DPA + cite DPF cert ID + enable EU-resident config | Captain (DPA-sign) + ops | Spec 055 complete (sub-proc list + AC #16/#17) — EXECUTION gate, folds into #191 |
| **Off-box WORM** | checkpoint emit (PR-1) + deploy-wiring (PR-2: cron + Caddy route + public git push) | CTO/FW-097 | PR-1 ✅ **MERGED #114 (1467113)**, CPO-reviewed-APPROVED; PR-2 HELD on the public-checkpoint opaque-id keying — now pinned **Spec 052 v3.10 AC #13** (minted random id + fail-closed slug→id map, NO slug in the permanent public sink; my review MEDIUM, CTO-agreed). CTO building the `checkpoint.py` opaque-id indirection + PR-2 against it. Touches FW-098/099/101 + 055 ROPA |

**COO-path RESOLVED via workaround (2026-05-26 17:10):** COO's injection-defense is durably hardened (rejected even console reactivation, injection-49, post-FW-117) — so rather than block: the **FW-121 security pass = Opus substitute** (CTO proceeds; CPO-approved, atop CTO 2 Opus deploy-rounds + my conformance → FW-121's full gate with the VPS); the **coo-dpo.md DPO-read defers to customer-#1 natural reactivation** (Spec 055 H1 active-duties-ramp — happens when COO's DPO duties ramp at the first install). Neither blocks critical path; the COO-path is OFF the Captain decision list. **Future CPO item (not urgent; coordinated CoS+CPO+CTO under FW-117 f/u 3 / task #80):** COO-resilience design — (a) injection-defense releases on framework-malformation-cleared signals without weakening real-injection resistance; (b) a cryptographic Captain-signed offline-verifiable reactivation token (channel+Telegram-independent).

CLOSED since the prior refinement: allow-list parity (#234 validator.py + #107 sync-guard, Spec 052 v3.6 AC#12), FF-pull drift-backstop (#192/#109). Remaining non-blocking follow-ups: cap-reaction design (CTO), the COO-resilience design (above). (The 4 pre-go-live gates incl. #236 are in the gates table above.)

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
- COO-as-DPO: ✅ RESOLVED msg 2737 (2026-05-24) — COO appointed DPO; CoS-as-DPO retired (Article 38(6) conflict). Retention 5y/10y (msg 2742); Anthropic wrapper risk accepted (msg 2744). Entire legal track closed (Spec 055 v7.3).
- H3 value-add carve-out: calculated-bet posture (no Anthropic outreach pre-leverage per A13)
- Devin price collapse ($500→$20): update discovery-call objection-handling, not a pricing adjustment
- Spec 049 COO adversary review: final gate before CTO Phase 2a build starts
- Sensed launch: quality-gated (TestFlight live; PMF gate D14≥40% target)
- Pricing (Cabinet): 25k DKK base + 5k DKK/employee — predictable bundled subscription, not ACU metered
