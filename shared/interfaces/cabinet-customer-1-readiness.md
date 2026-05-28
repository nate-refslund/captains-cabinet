# Cabinet Customer-#1 Readiness Checklist

**Date:** 2026-05-28 (CPO pressure-test refresh — prior 2026-05-24; see the bottom UPDATE block for what changed)
**Owner:** CPO (Go-to-Market Readiness Tracking — living checklist). CoS plugs in substrate + founder-action status.
**Purpose:** The single consolidated answer to **"can we TAKE the first paying Danish customer at all?"** (pre-sale readiness). Complementary bookend to `cabinet-phase-1-validation-gate.md`, which answers "are we good AFTER customers 1-5" (post-sale PMF). Both needed; neither duplicates the other.
**DRY discipline:** this file REFERENCES source-of-truth artifacts (specs, FW backlog, validation gate, mac-migration phase table in `shared/backlog.md`) — it does not copy their content. Status columns are the rollup; click through to the source for detail.

> **Status legend:** ✅ done · 🟡 in progress · ⛔ blocked · ⬜ not started · 🔵 N/A-for-phase-1

---

## The GO line

Customer-#1 **discovery call** can happen anytime (no prerequisite — it's qualification, not delivery).

Customer-#1 **signup + concierge install** requires **all of A–E green simultaneously.** Today's blocker summary is at the bottom.

---

## A. Platform substrate (dogfood-before-sell)

**TWO architecture paths BY DESIGN (captain-decisions msg 2599/2603, CoS-verified 2026-05-28):** STEP-internal = full Mac-native (this migration, 1-then-clone-to-3 dogfood); **COMMERCIAL customer = Docker-Desktop + FileVault + caps (Spec 050) — a DISTINCT build**, NOT the Mac-native migration. The Hetzner backend was built independent of the migration. **⚠ OPEN (Captain's strategic dogfood-before-sell call; CoS surfacing):** does customer-#1 gate on this migration, or does commercial DECOUPLE (customer-#1 = Hetzner backend + the Docker-Desktop cabinet path + #184/#191 + front-end build, with the Mac-native migration a PARALLEL STEP-internal track)? **CoS leans decouple.** Section A's gating below is PROVISIONAL pending the Captain's answer — CoS routes it back to CPO to pin.

| Item | Source of truth | Status | Notes |
|------|-----------------|--------|-------|
| Mac migration Phases 0-8 complete | `shared/backlog.md` §Mac Migration table (Specs 057-065) | 🟡 | Phase 0 ✅; Phase 1 mid-execution (Captain hands-on); Phases 2-8 ready. **Phase 1 NOT complete until 058 Ckpt 1.8 code-sign + reboot-TCC-persistence + JIT-launch golden eval pass (Phase-4 gate).** |
| Clone-to-3 STEP-internal fleet | Spec 065 §clone plan | ⬜ | After single-Mac Phase 8. Dogfood discipline gate. |
| cua-driver + Lead enforcement validated | Spec 061 Phase 4 | ⬜ | Gated on 058 1.8 (F2 dependency). |

## B. Commercial substrate (FW-096-101)

| Item | Source of truth | Status | Notes |
|------|-----------------|--------|-------|
> **B status (CPO-updated 2026-05-28): the BACKEND substrate is BUILT + merged + CPO-reviewed — the 05-24 "nothing built" note is SUPERSEDED. Remaining = two Captain-gated pieces: FW-099/101 (gated on #184 private repo) + the deploy (gated on #191 VPS). See B2 for the security/WORM/GDPR-deploy gates riding with the deploy.**

| LiteLLM proxy + per-cabinet virtual keys + $50/day cap | FW-096 / Spec 051 v7.3 | ✅ BUILT + merged (PR #99; M-DPO-2 config-flip pending — see B2) | Backend built; deploys via the FW-121 stack on #191. |
| Customer audit log + hash-chain + Art-15 export | FW-097 / Spec 052 v3.10 | ✅ BUILT + merged (PR #100/#105; + #236/#237 traversal hardening + WORM checkpoint) | Backend built + security-hardened; deploys on #191. |
| FW-121 Hetzner deploy stack (docker-compose + Caddy + provision + WORM sidecar) | FW-121 / Spec 050-052 | ✅ BUILT + conformance-APPROVED (PR #108 + #116) | Runs when #191 VPS is provisioned. |
| refslund.ai signup + Stripe Token Billing | FW-099 / Spec 054 | ⛔ NOT built — gated on #184 private commercial repo | The product front door; also delivers E refslund.ai-live + Stripe-configured. |
| Customer dashboard MVP (activity + spend + audit + WORM-checkpoint id) | FW-101 / Spec 056 | ⛔ NOT built — gated on #184 | Single pane the customer sees; surfaces the opaque WORM-checkpoint id (Spec 052 AC#13). |

## B2. Security / WORM / GDPR-deploy gates (pre-pilot — from the 2026-05-26/27 security cluster)

All CODE is merged + CPO-reviewed; ⬜ items are deploy-time execution riding with the #191 deploy.

| Item | Source | Status | Notes |
|------|--------|--------|-------|
| M-DPO-2: `config.yaml log_requests: false` | Spec 051 v7.3 AC#14 | ⬜ deploy-config (CTO flips at deploy) | `true` leaks prompt PII to the docker json-log, OUTSIDE the erasure SSOT (Art 5(1)(c)+17). HARD pre-pilot gate. |
| #236/#237 cabinet_id traversal guards | Spec 052 v3.7/v3.9 | ✅ merged (PR #112/#113) | GET+POST + write-side 3-chokepoint; conformance-verified. |
| Off-box WORM checkpoint (opaque-keyed; served + public git mirror) | Spec 052 v3.10 AC#13 + FW-121 | ✅ merged (PR #114/#115/#116) | Live needs the founder-action repo+token (E) + the id-map write (below). |
| `AUDIT_CHECKPOINT_ID_MAP` write (slug→opaque-id) | Spec 052 v3.10 / FW-098 | ⬜ install writes `cabinet-id-map.json` | FW-098 install MUST mint the opaque id + write the map, or the WORM checkpoint fail-closed-skips (no public anchor). Pin in the FW-098 spec when #184 unblocks. |
| Cloudflare DPA + EU-localization + DPF-cert cite (Art 44) | Spec 055 AC#16/#17 | ⬜ Captain DPA-sign + ops config (rides with #191) | Spec-complete; deploy-execution gate. |

## C. Legal / compliance (no EU customer DPO signs without this)

| Item | Source of truth | Status | Notes |
|------|-----------------|--------|-------|
| GDPR baseline: ROPA + DPIA + DPA template + sub-processor list + erasure command | FW-100 / Spec 055 v7.3 | 🟡 spec-ready, build pending | **Legal track CLOSED 2026-05-24 — no Captain gate remaining.** Spec complete on 5y/10y retention + DPO=COO + wrapper-risk-accepted. CPO+COO build the artifacts (no external counsel; cabinet multi-officer review). |
| COO-as-DPO appointment | FW-114 | ✅ ratified + applied | Captain msg 2737. coo.md DPO appendix committed 47adf02; Spec 055 v7.1 H1 resolved. |
| Retention duration | Spec 055 v7.2 §H4 | ✅ ratified | Captain msg 2742 "drop to 5" → 5y general (Bogføringsloven §10) + 10y tax-relevant (Skatteforvaltningsloven §47). |
| Anthropic wrapper risk-acceptance | Spec 055 v7.3 §H3 | ✅ ratified | Captain msg 2744 "accept then" → ship value-add DPA/ToS as-is; FW-115 defense dossier ready. |
| ToS with Annex III high-risk exclusion | Spec 055 v7 §ToS | ✅ ratified | Captain msg 2565; copy drafted. |
| Danish-lawyer external review | Captain msg 2583 | 🔵 | Captain DECIDED against external counsel for Phase 1 — cabinet multi-officer review process substitutes. Re-evaluate at 5+ customers. |

## D. Onboarding kit (CPO — COMPLETE ✅)

| Item | Source of truth | Status |
|------|-----------------|--------|
| Discovery call script (+ honest-disclosure + Devin objection) | `cabinet/customer-templates/discovery-call-script.md` | ✅ |
| Welcome Day-0 email | `welcome-day-0.md` | ✅ |
| Install-day GDPR walkthrough | `install-day-gdpr-walkthrough.md` | ✅ |
| Week-1 cheat sheet (3-goals beat) | `cheat-sheet-week-1.md` | ✅ |
| Day-1 / Day-3 / Day-7 / Day-30 check-ins | `check-in-day-{1,3,7,30}.md` | ✅ |
| Concierge offboarding + erasure | `concierge-offboarding-script.md` | ✅ |
| Concierge install runbook (substrate) | Spec 053 + `cabinet/runbooks/concierge-install-cabinet.md` (CTO v0.1) | 🟡 | Runbook v0.1 shipped; re-validate against final Mac-native architecture. |

## E. Captain-action prerequisites (founder-action; CoS tracks)

| Item | Status | Notes |
|------|--------|-------|
| Apple Developer Program enrolled | ✅ | Captain msg 2576. Unblocks code-signing/notarization (058 1.8) + future .pkg. |
| refslund.ai domain control + DNS | ⛔ | CoS-verified: NOT live (no A record, domain not pointed). Inside FW-099 (P1), not started. Needed for signup + sub-processor pages + email. |
| Stripe account + products configured (25k+5k/employee tier) | ⛔ | CoS-verified: NOT configured. FW-099 (P1). Subscription→virtual-key issuance depends on it. |
| Customer BotFather bots (per-cabinet Telegram) | 🔁 recurring Captain cost | CoS-verified: MANUAL per-customer; FW-001 upstream-blocked (BotFather has no programmatic creation API). NOT a one-time unblock — Captain taps BotFather per customer cabinet's bot set, every customer, until Telegram ships an API. |
| **#184 — private commercial repo** (provision) | ⛔ **GO-LIVE GATE** | The commercial code's private home → unblocks FW-099 signup + FW-101 dashboard build. CoS tracks. |
| **#191 — Hetzner Frankfurt VPS** (provision + proxy.refslund.ai DNS/TLS) | ⛔ **GO-LIVE GATE** | The deploy target for the BUILT FW-121 stack (proxy + audit-server + WORM). Architecture ratified (captain-decisions 2026-05-25). Carries the Cloudflare DPA/EU-config + WORM checkpoints-repo sub-items. CoS tracks. |
| **Public `refslund-cabinet-checkpoints` repo + write-scoped token** | ⛔ rides with #191 | Off-box WORM tamper-anchor (set `AUDIT_CHECKPOINT_REMOTE`). Served checkpoint works without it; the off-box git anchor is inert until set. CoS tracks (folds into #191). |

## F. Validation instrumentation (so we can MEASURE customer #1)

| Item | Source of truth | Status |
|------|-----------------|--------|
| Phase 1 validation gate defined | `cabinet-phase-1-validation-gate.md` | ✅ (CoS-ratify pending) |
| Library Customer-Success Space schema | Spec 053 AC #8 | 🟡 | Per-customer record: discovery notes, check-in results, NPS, friction, cancellation reason. |
| Captain-time-budget forecast (≤4 hrs/wk) | Spec 053 AC #13 / `captain-time-forecast.sh` | 🟡 | Throttles new-install slots if Captain touch-time breaches ceiling. |

---

## Blocker summary (CPO pressure-test 2026-05-28)

> **What changed since 05-24:** the commercial BACKEND substrate got BUILT this cycle — FW-096 proxy + FW-097 audit-log + the FW-121 deploy stack + the #236/#237/M-DPO-2/WORM security cluster, all merged + CPO-reviewed. So B is no longer "nothing built." The critical path is now Captain-gated DEPLOY + the FW-099/101 front-end build — NOT "build the backend from scratch."

**Critical path to customer #1 (the FULL readiness — broader than the "2 founder-actions" go-live framing):**
1. **#184 private commercial repo** (Captain) ⛔ → unblocks the FW-099 signup front-door + FW-101 dashboard BUILD (+ the opaque-id mint/store/surface fold).
2. **#191 Hetzner VPS** (Captain) ⛔ → deploys the BUILT backend (FW-121 stack) + executes the B2 deploy-config gates (M-DPO-2 `log_requests:false`, the `AUDIT_CHECKPOINT_ID_MAP` write, Cloudflare DPA/EU-config) + the WORM repo+token.
3. **Legal artifacts BUILD** (C, CPO+COO) 🟡 → spec-complete (track closed) but the ROPA/DPIA/DPA/privacy-policy ARTIFACTS still need building. Un-gated; should be ready when #184/#191 open.
4. **Mac-native customer cabinet** (A) 🟡 → the customer cabinet inherits the Mac-native architecture (migration + STEP-internal dogfood). SEE SEQUENCING FLAG.

**⚠ SEQUENCING FLAG (for CoS/Captain):** the recent backlog frames go-live as "2 Captain founder-actions (#184, #191)" — that is the COMMERCIAL-BACKEND deploy gate. But this FULL readiness also requires A (Mac-native cabinet), C (legal artifacts built), B2 (deploy-config gates). **Open question: is the Mac migration a HARD gate for the FIRST commercial customer, or can customer-#1 onboard on the Hetzner backend with a cabinet-delivery that doesn't block on the full migration?** "Dogfood-before-sell" (A) says Mac-native is dogfooded internally first, but the commercial backend was built independent of the migration. **(CoS verified 2026-05-28 — msg 2599/2603 = two architecture paths BY DESIGN: STEP-internal Mac-native vs commercial Docker-Desktop/Spec-050; CoS leans DECOUPLE, surfacing to Captain as his strategic call; pin section A on his answer.)**

**Not blocking (green):** legal SPEC track (C ✅ closed — artifacts still to build), onboarding kit (D ✅), Apple Dev (E ✅), validation gate (F ✅), discovery-call capability (qualify prospects now).

**Recurring (not an unblock):** per-customer BotFather bot taps (E) — standing Captain cost every customer until FW-001 (Telegram API).

**Single biggest lever now:** the two Captain founder-actions (#184 → front-end build; #191 → deploy + B2 gates). The backend is built + waiting; gate-open flips fast to onboarding — hence this pressure-test, so the checklist is clean when it does.

## FW-114 ratification ask — clean framing [RESOLVED msg 2737 — record of how the ask was framed]

- **Spec reference:** Spec 055 **v7** §H1 (DPO-appointment open question — reopened in v4, pending through v7). The "v4 H1" in the FW-114 backlog entry is stale version-pinning; H1 is the issue label, v7 is the current spec.
- **The ask:** ratify **COO-as-DPO designation** (replaces the msg-2583 CoS-as-DPO, which violates Article 38(6) — CoS coordinates processing decisions, can't be independent DPO; CJEU C-453/21 + Proximus €50k precedent).
- **Does it hold while COO is passive (Captain msg 2731)? YES.** (a) DPO is **voluntary** at Phase 1 — Spec 055 I2 confirms Phase 1 scope is NOT Article 37-mandatory (sub-large-scale + Annex III excludes special-categories + no systematic monitoring). (b) **Designation is a governance act** (role-def appendix + dpo@refslund.ai contact + named in DPA/ROPA/privacy) — it doesn't require COO to be actively running. (c) **Active Article 39 duties** (monitoring, breach response, access/erasure fulfillment) only have substance once there's actual customer-data processing — i.e., at customer #1, when COO reactivates for the install GDPR walkthrough + Annex III gate (already COO's per Spec 053 Stage 4). So designation now, active duties ramp at customer #1. No gap.
- **No CoS-as-DPO interim needed** — that would re-introduce the exact Article 38(6) conflict FW-114 fixes, for a pre-launch window with zero processing. Strictly worse.
- **One-word ack:** "ratify COO-as-DPO designation." Amendment pre-staged (`fw-114-coo-dpo-amendment-staging.md`), applies same turn (task #34).

---

*Pre-sale readiness rollup. When A–E are green, we can take customer #1. The validation gate then tells us whether customer #1-5 prove we should build Phase 2.*

---

## UPDATE 2026-05-28 — CPO pressure-test refresh (CoS-requested de-risk pass during the Captain-gate)

The checklist predated the 2026-05-26/27 security/WORM cluster — stale status + missing gates. Corrected so the gate-open is clean (gaps would otherwise surface customer-FACING during onboarding):
- **B (commercial substrate):** was "nothing built"; now reflects FW-096 proxy + FW-097 audit-log + the FW-121 deploy stack BUILT + merged + CPO-reviewed. Only FW-099/101 remain (gated on #184).
- **B2 (NEW section):** security/WORM/GDPR-deploy gates — M-DPO-2 config-flip, #236/#237 traversal guards, the WORM opaque-keyed checkpoint, the `AUDIT_CHECKPOINT_ID_MAP` install-write, Cloudflare DPA/EU-config/DPF-cite. Code merged; ⬜ items are deploy-execution.
- **E (founder-actions):** ADDED the two go-live gates that were MISSING entirely — **#184** (private repo) + **#191** (Hetzner VPS, the deploy target) — plus the WORM public-checkpoints-repo+token.
- **Blocker summary:** rewritten to the current critical path (Captain-gated deploy + front-end build, not from-scratch backend).
- **⚠ Sequencing flag raised:** is the Mac migration a hard gate for the FIRST commercial customer, or has the commercial-backend path decoupled to #184/#191? (CoS/Captain to clarify.)

*Persistence note: this file is gitignored (`shared/interfaces/**/*.md`) — filesystem-shared across officers, NOT git-versioned (no history, not in worktrees, rebuild-risk). Flagged to CoS as an L3 — worth force-adding for history/rebuild-safety, like the specs are?*
