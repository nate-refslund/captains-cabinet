# Spec 050 — Commercial Cabinet Build Plan (refslund.ai)

- **Version:** v1.2 (full-native architecture absorbed)
- **Date:** 2026-05-22 (v1.0 09:19 → v1.1 22:30 → v1.2 23:15 UTC)
- **Author:** CoS (v1.0 Opus synthesis + v1.1 + v1.2 amendments)
- **Status:** RATIFIED on positioning + pricing + caps + full-native (Captain msg 2565 + 2603 + 2605); Phase 1 detail-specs (FW-096 / FW-097 / FW-098 / FW-099 / FW-100 / FW-101 all SHIPPED + multi-officer reviewed)
- **Spec class:** Strategic build plan (parent spec; sub-specs FW-096…FW-113)
- **Supersedes:** none (orthogonal to all live specs; folds into FW-082/088/094 substrate work)

**v1.2 changelog (Captain msg 2599 Mac Migration Directive + msg 2603 Q5 + msg 2605 autonomy + msg 2607 "Go" + CPO cross-spec impact analysis 2026-05-22 23:07 UTC):**

**Two-tier architecture clarified (CPO finding):** the commercial Cabinet has two distinct substrate surfaces. CPO's cross-spec impact analysis caught what my initial v1.2 draft conflated:

| Tier | What runs there | Substrate |
|---|---|---|
| **refslund.ai backend** (cloud: Hetzner Frankfurt VPS or equivalent) | LiteLLM proxy (Spec 051), customer audit sidecar (Spec 052), Stripe webhooks + customers Postgres (Spec 054), customer-facing dashboard (Spec 056), Library Compliance Space + DPA + ROPA + DPIA records (Spec 055) | **Docker stays.** This is the SaaS layer serving all customer Cabinets — customer-isolation + uptime + scale concerns outweigh native simplification. Spec 051-056 Phase 1 substrate work proceeds against Hetzner-Docker baseline as designed. |
| **Customer's Mac mini** (one per paying customer; the appliance they buy) | Officers (CoS + CTO + CPO + CRO + COO), Library local mirror + /tasks local, Cabinet Memory local pgvector, cua-driver (Lead-officer only), Screenpipe | **Full native.** Postgres.app + Homebrew Redis + launchd-managed officer sessions. Matches the Mac Migration Directive (which migrates Captain's own Cabinet, dogfooding the same architecture commercial customers receive). |

- **Phase 2 .pkg installer** = the customer-Mac-side installer. Bundles native binaries + launchd plists + Library starter Spaces seeder. Talks to refslund.ai backend (Tier 1) for proxy + billing + audit. No Docker Desktop on customer Mac.
- **§5 Build-vs-Buy table** — entries split by tier. Backend: keep Docker. Customer-Mac: Postgres.app + Homebrew Redis + native launchd. cua-driver added as Lead-officer scope (customer-Mac CoS gets it; other officers don't).
- **§7 architecture diagram redrawn** — two boxes (refslund.ai backend + Customer Mac), connection paths between them named (LiteLLM proxy, audit emit, Stripe webhooks, dashboard reads).
- **§9 anti-pattern guard expanded.** Added: "Docker on Customer Mac" (Q5: native only on the appliance), "FileVault disabled for STEP-internal" (NOT for commercial customers — they MUST enable FileVault for GDPR Art. 32 per Spec 055; STEP-internal is the explicit exception), "Backend = native macOS" (Captain didn't say that; Tier 1 stays Docker for customer-isolation + scale).
- **§3 Phase 1 (concierge install) unchanged.** Concierge install is laptop-by-laptop scripted setup of the customer-Mac tier; runbook reference now includes Spec 058 (Phase 1 of Mac Migration directive) as the canonical customer-Mac bootstrap.
- **§3 Phase 2 (.pkg installer) scope refined.** Phase 2 productizes the Phase 1 runbook into a one-click installer for the customer-Mac side. Mac Migration Directive Phase 2 (LaunchAgents on Captain's Mac) is the same pattern but hand-installed; Phase 2 .pkg automates it for paying customers.
- **§13 risks updated.** Anthropic terms risk unchanged (still under A13 value-add posture). macOS update risk WIDENED — both cua-driver SPI breakage AND any breakage in our native services (Postgres.app + Redis launchd + officer launchd) are within the customer-Mac macOS-upgrade blast radius. Hold customer-Mac macOS upgrades on a tested-stable channel.
- **§14 compounds with Mac Migration Directive** — Captain's own Cabinet (the directive's target) is the dogfood ground for commercial Cabinet's customer-Mac tier. Same architecture. Tier 1 (refslund.ai backend) is orthogonal to the directive.

**Spec 049 Gate-4 cua-driver distinction (CPO flag #3 — RESOLVED):** Spec 049 Gate 4 (Stagehand v3) is headless-Chrome standalone — it does NOT need cua-driver, so Gate 4 stays per-officer (cua-driver-scope-to-CoS, Mac-migration Phase 4, is for native-macOS-GUI actions, not headless web). Confirmed in Spec 049 v3.1 (Gate 4 = per-officer headless Stagehand; the COO adversary surfaced no cua-driver dependency). No separate v3.2 — ast-grep collapsed into v3.1 (C4).

**v1.1 changelog (Captain msg 2565 + 2568 + 2576+2579 absorbed):**
- **Positioning:** Path A (generic Cabinet positioning) **+ Danish-first geographic phasing**. NOT vertical-anchored (Path B rejected — STEP Network competitive conflict). NOT pure-generic Path A (CRO saturation risk).
- **Pricing model:** Collapsed 4-tier (2.5k/5k/10k/15k DKK) → **ONE tier: 25,000 DKK base + 5,000 DKK per employee, max 7 employees per cabinet** (25-60k DKK/mo range per cabinet).
- **Caps:** Per-tier daily caps ($10/$25/$50) → **$50/day per-cabinet TOTAL across all officers** (not per-officer).
- **Phase 1 customer profile:** Danish-only, within physical reach (Odense, Copenhagen, rest of DK), Nate-supervised concierge install.
- **Phase 2 positioning shift:** "EU-resident, GDPR-native AI organization" — Nordic opportunistic.
- **Phase 3 trigger:** 20 Danish Cabinets OR 1M DKK/mo MRR (whichever first).
- **Localization:** DA primary, EN secondary Phase 1.
- **Compliance posture:** DK + EU baseline (GDPR + EU AI Act limited-risk transparency). Annex III high-risk use cases (HR/credit decisions) **EXCLUDED from Phase 1 ToS**.
- **No vertical employee role catalogs Phase 1** — role-agnostic with CFO/CTO/COO/etc. as examples in marketing.
- **Three-layer naming locked:** "Cabinet" (commercial product), "Captain's Cabinet" (open-source framework), "refslund.ai" (practice).
- **Anthropic outreach DROPPED** per A13 captain-pattern (msg 2568) — "Don't seek permission from gatekeepers before you have leverage." Phase 1 ships under value-add carve-out interpretation. Revisit at 5-10 paying customers with leverage + a story.
- **Apple Developer Program enrollment COMPLETE** (Captain msg 2576) — unblocks .pkg notarization pipeline at Phase 2 start.
- **Captain comms discipline (msg 2576+2579 — CoS-only feedback memory):** milestone-DMs surface each material artifact ship on long-running Captain-assigned tasks; CoS-only scope.

---

## 1. Strategic context

refslund.ai is a **three-offering professional practice** running on top of Captain's Cabinet:

1. **Hire an officer** — primary product. Subscribers get named AI roles (CFO, CTO, PO, etc.) supervised by Nate. Subscription tiers 2,500 / 7,500 / 15,000 DKK per officer per month.
2. **Teach & advise** — workshops, courses, architect engagements. Lead source + credibility.
3. **Crew sprint** — hourly project work in Solo / Pair / Trio / Quad sizes. Tertiary.

**Cabinet's role:** the underlying infrastructure. Customers install Cabinet on a MacMini (sold or self-supplied), or use a hosted instance once one exists. The open-source Cabinet framework stays **BSL 1.1**. The commercial-customer-facing surfaces live in a **private satellite repo** so customer-facing business logic stays unexposed.

**Repo-home split (resolves the Spec 050↔051 contradiction CTO flagged 2026-05-24 — Spec 051 line 16 governs the substrate):**
- `captains-cabinet` (BSL 1.1, public) — the framework, INCLUDING the **proxy SUBSTRATE** (FW-096: LiteLLM routing/config schema, per-cabinet cap-enforcement, audit-log emission, key-rotation, test harness). This is generic framework plumbing any cabinet can run — NOT the commercial secret. FW-096 substrate lands HERE; it is NOT blocked on the private repo.
- `refslund-cabinet-commercial` (private) — the **commercial-customer-facing layer**: signup (FW-099 customer surface), customer dashboard + audit UI (FW-101), billing integration (Stripe→subscription), customer wizards, installer pipeline, **and the margin-markup VALUES** (the pricing config — the actual commercial differentiation). Imports the framework as a dependency. Customers never see this repo. (Earlier "proxy → private" framing was over-broad: the proxy CODE is framework-public per Spec 051; only the margin VALUES + hosted-billing integration are private.)

**Why this matters now:** every hour Nate spends today bolting Cabinet onto each new customer is an hour not invoiced and a moat that competitors can erode while we hand-tune. Phase 1 of this plan converts the **first paying customer** from a 40-hour bespoke setup into a 4-hour assisted setup. Phase 2 converts that into a 30-minute self-serve install.

---

## 2. Timeline validation — honest take

Captain proposed 3-4 months to commercial-ready. **Calibrated answer: 3 months to FIRST PAYING CUSTOMER if scope is held tight; 5 months to SELF-SERVE INSTALL.** Bumping out of Captain's 3-4 month band on the back end.

**Effort math, honest, in Cabinet-hours not calendar weeks:**

| Phase | Scope | CTO hours | CPO hours | Critical-path weeks at evening/weekend cadence |
|---|---|---|---|---|
| **P1** | First-paying-customer unblock (proxy, daily caps, audit log, basic dashboard, manual install runbook) | ~120-160 | ~40 | 6-8 weeks |
| **P2** | Self-serve install (.pkg installer, Sparkle updates, hire-an-officer wizard, customer observability) | ~200-260 | ~60 | 10-12 weeks |
| **P3 (v2)** | Hardening, advanced features (monitor-connected mode, compute-use polish, Bedrock reseller path, multi-officer org orchestration) | ~140 | ~50 | 6-8 weeks |
| **P4 (v3)** | Apple/container migration + hosted-version optionality | ~120 | ~40 | 6 weeks |

**Why this is realistic:** Nate is full-time at STEP Network. The Cabinet itself can grind on slices via Crew agents, but every **architecture decision and Stagehand-grade integration** routes through Nate per A12. The bottleneck is Captain-decision throughput, not engineering velocity.

**What's NOT in this plan:** sales motion, content marketing, course production, partner agreements. Those are practice-building, not platform-building. CPO + CRO will draft a parallel commercial-launch playbook once this spec ratifies.

**Honest disagreement with Captain's 3-4 month frame:** the **first paying customer** can come in within 3 months if we accept a "concierge install" runbook (Phase 1 only). The **product that scales without Nate touching every install** is a 5-month build, not 3-4. Calling that out so we don't quietly slip from "self-serve in 4" to "still doing concierge installs in 6" without a conscious decision.

---

## 3. Phasing — what unblocks what

### Phase 1 (months 1-2): unblock FIRST PAYING CUSTOMER

**Goal:** invoice a real customer for a real officer running on their MacMini, with our economics protected and our compliance posture defensible.

**Scope:**

| ID | Item | Maps to gap |
|---|---|---|
| FW-096 | LiteLLM proxy + per-officer virtual keys (attribution) + **$50/day per-CABINET total hard cap** (LiteLLM team-budget; team=cabinet) | B (API key abstraction), economics |
| FW-097 | Customer audit log (every officer access to customer data, queryable) | H (audit/compliance) |
| FW-098 | Concierge install runbook + cabinet-bootstrap.sh hardening for customer MacMini | A (MacMini installer, manual-grade) |
| FW-099 | refslund.ai signup + Stripe Token Billing wiring | B (key abstraction) |
| FW-100 | GDPR baseline: ROPA template, DPIA template, erasure command, sub-processor list, DPA template | H (compliance) |
| FW-101 | Customer dashboard MVP: officer activity feed, daily spend, audit log viewer | D (observability), H |

**Acceptance criteria (Phase 1 gate):**
- A1: a paying customer can run their cabinet (one-tier 25k DKK base + 5k/employee, Sonnet-default officers) on their MacMini for 30 days with zero Nate intervention beyond install. (The superseded 2,500 DKK / per-officer-tier model is GONE — one tier, per §6/§9.)
- A2: cabinet-total daily Anthropic cost is hard-capped at **$50/day per CABINET** (LiteLLM team-budget, team=cabinet; per-officer virtual keys are for attribution only, NOT per-officer caps — those are explicitly rejected §9). **Breach pauses the CABINET (all officers' keys blocked by the exhausted team budget — at a cabinet-total cap there is no single offender, and pausing only the top spender wouldn't stop the breach) + notifies the customer (CoS DM) with the Spec 056 cap-bump as the override path.**
- A3: customer can query "what did my Cabinet do in the last 24h" via dashboard and get a complete answer from the audit log.
- A4: GDPR erasure command produces a signed deletion receipt customer can hand to their DPO.
- A5: install is documented as a runbook Nate can execute in <4 hours per customer (concierge OK, self-serve NOT required this phase).

**Dependencies:** Move 1 routing (shipped). Spec 049 **v3.1 LANDED** (222be1c — COO adversary 21 findings folded + ast-grep collapsed; Phase 2a ceiling MERGED via Sensed PR #560 + founders-cabinet substrate; 4 Gate-4 leaves shipped: model-pricing/cache-hash/page-allowlist/semaphore; **Gate-4 runner core gated on the one-time Stagehand v3 install — CoS provisioning**). FW-082/088 substrate (in flight). No separate Spec 049 v3.2 — ast-grep collapsed into v3.1 (C4).

**Risks (Phase 1):**
- **Anthropic reseller terms.** Pass-through wrapping is restricted; multi-officer orchestration likely qualifies as value-add. Get written confirmation from Anthropic's partnerships email before first invoice. If unclear → Bedrock route via FW-103, slips P1 by 4-6 weeks.
- **Customer DPO sign-off slower than install.** Mitigate by shipping the DPIA-template-they-fill-in pattern (research finding 5).
- **Daily cap false positives** killing genuine work. Mitigate: cap pause sends DM with "extend by $X for next 24h" override.

**Crew delegation pattern (Nate's evening/weekend reality):**
- CTO (Nate-supervised) authors LiteLLM config + Stripe wiring (architecture).
- Crew agents execute: dashboard scaffold, audit log schema migration, GDPR template authoring.
- Spec 049 4-gate /self-review runs on every PR. **Note (CTO B6):** Gate 4 (Stagehand visual-UAT runner core) is gated on the one-time Stagehand v3 install (CoS provisioning) — so early FW-101 dashboard PRs run the existing 10-point /self-review (Gates 1-3) now; Gate-4 visual-UAT lands + applies to FW-101 once the runner core ships post-install. Not a blocker for early FW-101 work, just the sequencing.

### Phase 2 (months 3-4): unblock SELF-SERVE installation

**Goal:** a customer can buy a MacMini, run our .pkg installer, sign up at refslund.ai, and have a working officer in 30 minutes.

**Scope:**

| ID | Item | Maps to gap |
|---|---|---|
| FW-102 | Notarized .pkg + Sparkle 2 auto-update + signed binary distribution pipeline | A (MacMini-ready installer), G (updates) |
| FW-103 | Hire-an-officer wizard (GUI: pick role, set autonomy boundaries, name your officer, connect tools) — replaces YAML | C (Officer definition UI) |
| FW-104 | Customer-grade Screenpipe integration (retrospective observability layer, 7d retention, FileVault required) | D (observability) |
| FW-105 | Customer-facing CU layer (Stagehand v3 cached primary + Browser Use + Apple Vision OCR; Claude CU escape hatch behind HITL gate) | E (computer-use escape hatch) |
| FW-106 | Sub-spec extension to Spec 049 for production telemetry (per-officer step/token budgets visible in dashboard) | D |
| FW-107 | Self-serve onboarding: refslund.ai → signup → download → install → first-officer-hired in single flow | A, B, C |

**Acceptance criteria (Phase 2 gate):**
- A1: 5 customers complete signup + install + first-officer in <60 minutes without Nate touch.
- A2: customer can upgrade Cabinet via "Check for updates" in the dashboard menu; no terminal commands.
- A3: customer can hire CFO via wizard in <10 minutes without ever seeing YAML.
- A4: customer dashboard shows live officer activity when MacMini has a monitor connected (read-only feed).
- A5: Screenpipe daily-restart + opt-out + erasure all working; no memory leak observable over 14d soak.
- A6: a CU action triggered by an officer is visible in the dashboard with screenshot + DOM snapshot + cost.

**Dependencies:** Phase 1 complete. Apple Developer ID enrolled (3-day check). Sparkle 2 EdDSA signing keys generated and backed up.

**Risks (Phase 2):**
- **macOS 26.x signature regressions.** Tailscale got bricked by 26.2 in 2025. Mitigate: ship pkg compatible with 26.0+ and run a notarization smoke test on each new macOS minor before customer rollout.
- **Notarization queue stalls.** First submission for new developer ID can take 48-72h. Submit dummy pkg in Phase 1 to warm the queue.
- **Sparkle EdDSA key loss.** Mitigate: dual-key with hardware token backup, documented in runbook.

### Phase 3 (v2, months 5+): hardening + advanced

**Scope:**

| ID | Item | Maps to gap |
|---|---|---|
| FW-108 | Monitor-connected mode: live officer activity stream on MacMini display | F (monitor-connected) |
| FW-109 | Bedrock Authorized Reseller migration (when revenue justifies; ~$100K ARR threshold) | B (margins at scale) |
| FW-110 | Multi-officer org orchestration UI (customer has CTO+CFO+PO simultaneously, sees their handoffs) | scale |
| FW-111 | Compliance: EU AI Act Aug 2026 high-risk readiness check + audit-log retention configurability | H |

**Acceptance criteria:** revenue-gated; scope to be re-validated when 10 paying customers exist.

### Phase 4 (v3, months 11+): hosted optionality

**Scope:**

| ID | Item | Maps to gap |
|---|---|---|
| FW-113 | Hosted-Cabinet option for customers who don't want a MacMini | go-to-market |

(v1.2.1: FW-112 Colima → apple/container REMOVED — under v1.2 two-tier architecture, Customer Mac is full-native; no Colima to migrate from. apple/container deferred indefinitely as it's moot for the customer-Mac tier.)

---

## 4. Coverage matrix: 8 gaps × phases

| Gap | Phase | Sub-spec |
|---|---|---|
| A — MacMini-ready installer | P1 (concierge), P2 (.pkg) | FW-098, FW-102 |
| B — API key abstraction | P1 (LiteLLM), P3 (Bedrock) | FW-096, FW-099, FW-109 |
| C — Officer definition UI | P2 | FW-103 |
| D — Customer observability | P1 (audit log), P2 (Screenpipe + live feed) | FW-097, FW-101, FW-104, FW-106 |
| E — Compute-use escape hatch | P2 | FW-105 |
| F — Monitor-connected mode | P3 | FW-108 |
| G — Update mechanism | P2 | FW-102 (Sparkle bundled) |
| H — Audit + compliance | P1 (baseline), P3 (AI Act) | FW-097, FW-100, FW-111 |

Every gap is mapped. P1 covers four gaps to MVP; P2 finishes the customer-facing surface.

---

## 5. Build-vs-buy decisions (with A3 anchor)

A3 = build-our-own beats add-a-dependency, with carve-outs for genuinely commoditized or specialized-expertise problems.

| Component | Build / Buy | Reasoning |
|---|---|---|
| LLM proxy | **Buy: LiteLLM** | Mature OSS, MIT, exactly our use case. Building our own = 4-6 weeks of router/budget/retry work for zero differentiation. |
| Billing | **Buy: Stripe Token Billing** | Card-on-file + metered billing is commodity. Stripe is incumbent. |
| Notarization / signing | **Buy: Apple Developer Program** | No build alternative. |
| Auto-updater | **Buy: Sparkle 2** | Mature OSS, EdDSA-signed, every-Mac-app uses it. |
| Postgres on Customer Mac (Tier 2) | **Buy: Postgres.app** | Native macOS, no Docker. Hosts Library + /tasks + Cabinet Memory locally. (v1.2 native shift.) |
| Redis on Customer Mac (Tier 2) | **Buy: Homebrew `redis`** | Native macOS, no Docker. AOF persistence enabled. (v1.2 native shift.) |
| Officer session supervisor (Tier 2) | **Build: native launchd plists** | Wraps Claude Code sessions per officer. Replaces Linux Docker tmux+supervisor pattern. (v1.2 native shift.) |
| Visual-CU primary | **Buy: Stagehand v3** (already in Spec 049) | Best-in-class, MIT. Headless Chrome — runs native on macOS, not Docker-coupled. |
| Visual-CU DOM agent | **Buy: Browser Use v3** | OSS, Fortune-500 traction. |
| Visual-CU OCR | **Buy: Apple Vision API** | Native, free, fast. |
| Visual-CU LLM fallback | **Buy: Claude CU** (escape hatch only) | Beta-grade, gate behind HITL. |
| Native macOS GUI driver (Lead-only) | **Buy: cua-driver** | Pinned-version curl install per Spec 058 v1.1 Checkpoint 1.6. Scoped to CoS (Lead) only per Mac Migration Directive. (v1.2 new entry.) |
| Retrospective observability | **Buy: Screenpipe** | Now customer-grade (research finding 3). |
| Audit log | **Build** | Cabinet-specific shape (officer × tool × customer-data-type × cost). No buy fits. |
| Hire-an-officer wizard | **Build** | This IS the product UX; differentiation. |
| Customer dashboard | **Build** | This IS the product surface. |
| MacMini installer/runbook | **Build** | Cabinet-specific orchestration; no buy fits. |
| Customer audit UI | **Build** | This IS the product compliance surface. |
| Proxy management UI | **Build** | Cabinet-specific (per-officer virtual keys, daily caps, escalation overrides). |
| Stripe webhooks → cap enforcement | **Build** | Cabinet-specific logic. |
| GDPR templates (ROPA/DPIA/DPA) | **Build (with lawyer review)** | Templates exist; the Cabinet-specific shape is ours. €3-5K Danish lawyer review covers it. |

**Pattern:** buy the commoditized layers (proxy, billing, signing, updater, CU); build the differentiated surface (wizard, dashboard, audit). This is exactly A3.

---

## 6. Cost-margin model (Captain-ratified v1.1, msg 2565)

**Pricing locked: ONE tier per cabinet.**

```
Cabinet base price:        25,000 DKK / month (~$3,500)
Per employee (officer):    +5,000 DKK / month (~$700)
Max employees per cabinet: 7
Cabinet price range:       25,000 - 60,000 DKK / month (~$3,500 - $8,400)
```

This is a B2B SMB price point ("company hires a Cabinet"), NOT a solo-founder hobby tier. It maps to the Danish-first geographic phasing: the customer profile is a Danish company with budget for AI staff, not an individual experimenting.

**Margin math at the new model:**

| Employees | Price (DKK/mo) | Price ($/mo) | Anthropic cost ceiling | Cabinet take-home | Notes |
|---|---|---|---|---|---|
| 1 (base) | 25,000 | $3,500 | $50-150 (Sonnet-dominant) | ~$3,300+ | Generous margin even with heavy Opus on the one officer. |
| 4 | 45,000 | $6,300 | $200-500 | ~$5,800+ | Typical 4-officer cabinet (CoS + CTO + CPO + CRO). |
| 7 (max) | 60,000 | $8,400 | $400-1,000 | ~$7,400+ | Full 5-officer + 2 specialists. Still 88%+ margin at $1k Anthropic. |

**Margin defense (non-negotiable):**
- **$50/day per-cabinet Anthropic cost hard cap** — total across all officers in the cabinet, not per-officer. $50 × 30 = $1,500/mo theoretical max Anthropic; at min revenue $3,500/mo that's 57% margin floor.
- 10 Opus escalations/officer/24h cap (already shipped Move 1) + dollar cap layered on top.
- Per-officer prompt-cache-hit-rate floor (alert if <70%, indicates a bug or runaway).
- Cap breach pauses the offending officer + DMs Captain + opens "extend by $X for next 24h" override path. Override audited to captain-decisions.md per Spec 049 v3.2 atomic-commit-override pattern.

**Why one tier (not 4-tier as CPO initially proposed):** Captain's call — simpler customer story, no sales-motion overhead optimizing tier choice, customer always knows the price by counting employees. Margin is generous enough at base that we don't NEED lower tiers; geographic Phase 2 (Nordic) can introduce localized tiers if the math demands it.

**Why $50/day per-cabinet (not per-officer):** Captain's call — a cabinet IS the customer's "team," and the team's total daily spend is the unit they care about. Per-officer caps complicate the explanation and don't change the margin math at typical workloads (Sonnet-dominant officers stay well under $50/day collectively).

---

## 7. Recommended architecture (text diagram)

```
                       refslund.ai (signup, billing, support portal)
                                       │
                                       ▼
                              Stripe Token Billing
                                       │
                                       │ (issue per-customer subscription
                                       │  + per-officer virtual key allowance)
                                       ▼
                            LiteLLM proxy (EU, Frankfurt)
                              │ per-officer virtual keys
                              │ daily $/officer hard cap
                              │ cache headers
                              ▼
                       Anthropic API (or Bedrock eu-central-1 when reseller path opens)
                              ▲
                              │ (officer LLM calls only — everything else stays local)
   ┌──────────────────────────┴──────────────────────────────────────────┐
   │                                                                     │
   │  CUSTOMER MACMINI (their property, their network, their data)       │
   │                                                                     │
   │  ┌─ launchd ─┐                                                      │
   │  │ supervisor│                                                      │
   │  └─────┬─────┘                                                      │
   │        │ spawns                                                     │
   │        ▼                                                            │
   │  ┌──────────────────────┐    ┌─────────────────────┐                │
   │  │ Officer sessions     │◄──►│ Postgres.app (local)│                │
   │  │ (launchd-managed,    │    │ Redis (brew, AOF)   │                │
   │  │  Claude Code native) │    │                     │                │
   │  └──────────┬───────────┘    └─────────────────────┘                │
   │             │                                                       │
   │             ▼                                                       │
   │  ┌──────────────────────┐    ┌─────────────────────┐                │
   │  │ Visual-CU layer:     │    │ Screenpipe          │                │
   │  │ Stagehand v3 primary │    │ (retrospective only,│                │
   │  │ Browser Use + Vision │    │  3am restart, 7d)   │                │
   │  │ Claude CU (HITL)     │    │                     │                │
   │  └──────────────────────┘    └─────────────────────┘                │
   │             │                                                       │
   │             ▼                                                       │
   │  ┌────────────────────────────────────────────────┐                 │
   │  │ Customer-facing dashboard (Next.js, localhost) │                 │
   │  │  • Hire-an-officer wizard                      │                 │
   │  │  • Activity feed (live + last 24h query)       │                 │
   │  │  • Audit log viewer (every customer-data       │                 │
   │  │    access, queryable)                          │                 │
   │  │  • Spend per officer per day                   │                 │
   │  │  • "Check for updates" (Sparkle 2)             │                 │
   │  └────────────────────────────────────────────────┘                 │
   │                                                                     │
   │  All officer logs, JSONL, audit records, Screenpipe DB              │
   │  stay HERE. Nothing leaves the MacMini except LLM calls.            │
   │                                                                     │
   └─────────────────────────────────────────────────────────────────────┘
```

**Key architectural commitment:** local-first. The ONLY thing that leaves the MacMini is LLM calls (proxied through our EU proxy) and explicit support-bundle uploads (customer-initiated). Officer logs, Screenpipe data, audit records, customer files — all stay local. This is what makes GDPR a €6-8K problem, not a €50K problem.

---

## 8. GDPR / compliance posture

Per research finding 5:

**Pre-launch legal spend: ~€6-8K total.**
- €3-5K Danish lawyer reviews DPA + DPIA + ROPA templates.
- €2K Transfer Impact Assessment for Anthropic sub-processor (Schrems II tail).
- €1K privacy notice + onboarding consent flow.

**What ships in Phase 1:**
- DPIA template customer fills in (we pre-fill the high-risk-processing analysis; they fill in their controller specifics).
- ROPA template.
- DPA template (refslund.ai ↔ customer).
- Erasure command (`cabinet wipe --confirm`) producing signed JSON receipt with pre-wipe inventory hash.
- Sub-processor list: Anthropic, Stripe, Apple (notarization). All disclosed at signup.
- Local-first storage commitment in the privacy notice.

**Hard constraint:** any customer who can't accept Anthropic as a US sub-processor with SCCs + TIA cannot be served on Phase 1. Mitigation = Phase 3 Bedrock migration unlocks Frankfurt-only routing.

**EU AI Act Aug 2026 deadline:** if any officer makes HR or credit decisions (Annex III high-risk), additional obligations apply. Phase 3 FW-111 addresses. Phase 1 acceptable-use clause excludes Annex III use cases.

---

## 9. Anti-pattern guard — what we explicitly DON'T build

These are temptations to avoid:

| Anti-pattern | Why we don't | Captain ratification |
|---|---|---|
| Managed Agents on Anthropic's platform | Rejected. Lock-in + margin compression + loses Cabinet differentiation. | Captain msg 2540 |
| Claude CU as primary visual layer | Beta-grade (78% OSWorld). Stagehand wins on every metric. Claude CU stays as 5% escape hatch behind HITL. | Spec 049 + research finding 4 |
| Centralized cloud Cabinet (we host customers' data) | Compliance nightmare + commoditization risk + violates the "your MacMini your data" promise. Hosted-option deferred to P4 and even then = customer's choice. | This spec |
| Preinstalled-MacMini-as-a-service-on-day-one | Authorized Reseller compliance burden + inventory cash burn + RMA logistics. Customer-self-install first; bundle hardware only after 50+ paying software customers. | Research finding 1 |
| Mac App Store distribution | Sandboxing blocks launchd, Docker, persistent services. Disqualifier. | Research finding 1 |
| Screenpipe as primary memory layer | Daily-restart memory issue + customer-grade only for retrospective observability. Stays retrospective-only. | Captain constraint + research finding 3 |
| Helicone as billing/proxy | Mintlify-acquired Mar 2026 = buyer risk; LiteLLM is the safer bet. | Research finding 2 |
| Per-customer fork of Cabinet | Maintenance explosion. Cabinet stays one codebase; customer config goes in their `instance/`. | Three-layer architecture |
| Notion or Linear as customer-facing artifacts | Cabinet has its own Library + /tasks (A11). Customers don't need our internal tools exposed. | A11 |
| **Premature Anthropic / Apple Reseller / AWS partnership outreach** | A13: don't seek permission from gatekeepers before you have leverage. Phase 1 ships under value-add carve-out interpretation. Outreach revisits at 5-10 paying customers + revenue + a story to tell. | A13 (msg 2568) |
| **Vertical-anchored positioning Phase 1** | CRO recommended media-ops vertical anchor; Captain rejected — STEP Network competitive conflict + low conviction. Generic Cabinet positioning + Danish-first geographic wedge is the actual play. | Captain msg 2565 |
| **Generic global SMB AI-app positioning** | CRO research finding: 95%-of-AI-orgs-stuck-in-pilot risk in the saturated global SMB space. Danish-first defuses by entering a less-saturated geographic wedge. | Captain msg 2565 |
| **Per-officer daily caps** | Captain chose per-cabinet daily cap ($50/day total) over per-officer caps — simpler customer story; the cabinet IS the customer's "team". | Captain msg 2565 |
| **4-tier pricing (Starter/Standard/Senior/Executive)** | CPO originally proposed 4 tiers; Captain collapsed to ONE tier (25k base + 5k/employee, max 7) for customer-story simplicity. | Captain msg 2565 |
| **Docker on Customer Mac (Tier 2)** | Captain Q5 (msg 2603) ratified full native for the customer-Mac tier. Postgres.app + Homebrew Redis + launchd-managed officer sessions. No Colima, no Docker Desktop, no apple/container. | Captain msg 2603 + Mac Migration Directive msg 2599 |
| **Native-ifying refslund.ai backend (Tier 1)** | Backend services (LiteLLM proxy, audit sidecar, Stripe webhooks, customer dashboard) STAY Docker on Hetzner. Customer-isolation + uptime + scale concerns outweigh native simplification at the SaaS layer. v1.2 two-tier split is by design. | CPO cross-spec impact analysis 2026-05-22 |
| **FileVault disabled for commercial customers** | STEP-internal fleet (Captain's own Cabinet) disables FileVault per Captain Q1 msg 2603. Commercial customers in EU MUST enable FileVault for GDPR Article 32 at-rest encryption with Screenpipe captures. Two postures by design. | Captain msg 2603 + Spec 055 v6 |

---

## 10. Naming question — Captain's open ask

**Captain leaned: drop "Captain's" prefix, call the customer product "Cabinet."**

**My position: yes — but with a precise three-layer naming.**

| Layer | Name | Audience |
|---|---|---|
| Open-source framework (BSL 1.1) | **Captain's Cabinet** | Developers, forkers, GitHub stars. Stays as-is — that's the existing brand and the public-source identity. |
| Commercial product (the install + dashboard + officers experience) | **Cabinet** | Paying customers. Cleaner, less military-coded, scales internationally. |
| Practice / service company | **refslund.ai** | Customers buying officers + workshops + crew sprints. Already chosen. |

**Reasoning:**
- "Captain's Cabinet" carries the military framing that resonates with founders but reads weird to a CFO buying an AI accountant. "Cabinet" alone is neutral and works for any role.
- The open-source name stays because (a) it has organic search and Stars equity already, (b) it's the developer-facing identity, and (c) framework users self-select for the military framing.
- Customers buying refslund.ai's officers say "I run Cabinet on my MacMini." Customers cloning the GitHub repo say "I'm forking Captain's Cabinet." Both true.
- Trademark check: "Cabinet" alone is hard to trademark globally (too generic) but "refslund.ai Cabinet" or "Cabinet by refslund.ai" is defensible. The practice name carries the trademark weight; the product name is descriptive.

**Captain action needed:** confirm three-layer naming. If yes, dashboard copy + marketing + installer all use "Cabinet"; framework docs + GitHub repo stay "Captain's Cabinet."

---

## 11. Sub-specs to draft (CPO authors next; CTO builds; COO adversary)

Filed as FW-096 through FW-113 in `shared/cabinet-framework-backlog.md` (parallel artifact). Priority order:

1. **FW-096** LiteLLM proxy + virtual keys + daily caps — earliest unlock for paying customer.
2. **FW-097** Customer audit log schema + viewer — earliest GDPR-defensible posture.
3. **FW-100** GDPR templates + erasure command — legal review can run in parallel.
4. **FW-098** Concierge install runbook — unblocks first customer without waiting on .pkg.
5. **FW-099** refslund.ai signup + Stripe wiring — billing online.
6. **FW-101** Customer dashboard MVP — first customer-visible surface.
7. (Phase 2 begins here once P1 acceptance gates pass.)

Each sub-spec gets full Spec 049 4-gate /self-review treatment + visual-UAT for any UI.

---

## 12. Captain ratification status (v1.1 update)

### Ratified (msg 2565 / 2568 / 2576)
1. ✅ **Three-layer naming** (Cabinet / Captain's Cabinet / refslund.ai) — msg 2565.
2. ✅ **Phase 1 scope freeze** (FW-096 through FW-101 — Anything else gets pushed to Phase 2) — msg 2565.
3. ✅ **Pricing model:** ONE tier — 25,000 DKK base + 5,000 DKK per employee, max 7 employees per cabinet (25-60k DKK/mo range) — msg 2565.
4. ✅ **Hard daily cap default:** $50/day per cabinet TOTAL across all officers — msg 2565.
5. ✅ **Positioning:** Path A + Danish-first geographic phasing — msg 2565.
6. ✅ **Anthropic partnerships outreach DROPPED** — Phase 1 ships under value-add carve-out interpretation per A13 pattern — msg 2568.
7. ✅ **Apple Developer Program enrollment** — Captain enrolled msg 2576.

### Pending Captain ratification
1. **A12 captain-pattern wording** — PROPOSED in `shared/interfaces/captain-patterns.md` ("Officer-in-loop on architecture; agents execute well-defined slices"). Spec 049 AC#12 anchors here. Captain ratification = wording finalization.
2. ✅ **Sub-processor list freeze for Phase 1** — RESOLVED msg 2583 Q5: Anthropic-only Phase 1 (OpenAI/Gemini fallback disabled). Spec 055 v7.
3. ✅ **EU-law counsel identification** — RESOLVED msg 2583 Q1: NO external counsel Phase 1; cabinet multi-officer review process (CPO→CoS→CRO→COO) substitutes. Re-evaluate at 5+ paying customers. Spec 055 v7.
4. ✅ **DPO appointment path** — RESOLVED msg 2737 (2026-05-24): COO-as-DPO (Article 38(6) fix; designation holds while COO passive, active duties at customer #1). Spec 055 v7.1; FW-114 applied.
5. **Private commercial repo creation** — `refslund-cabinet-commercial` private repo for proxy/dashboard/audit code. Confirms BSL 1.1 licensing isolation.
6. **Mac Mini image distribution choice** — CTO P1 BLOCKER #3: bundled 2GB pkg (offline-first, matches "your MacMini your data") vs first-launch registry pull (network dep, smaller pkg). Recommend bundled.
7. ~~**OrbStack vs Colima for Phase 2**~~ → **MOOT** per v1.2.1 full-native (customer-Mac runs native, no Docker/container runtime; FW-112 Colima→apple/container removed). No container-runtime choice to make.

### Founder-action items
- ✅ Apple Developer Program enrolled (Captain msg 2576).
- ⏳ Restart cabinet-host-agent service (~21 days down, parked).
- ⏳ peers.yml ratification (sensed peer).
- ⏳ ELEVENLABS_API_KEY for stephie voice.

---

## 13. Cross-cutting risks the Captain must consciously accept

1. **Anthropic terms-of-service ambiguity** (calibrated by A13). Phase 1 ships under value-add carve-out — Cabinet IS materially value-add (multi-officer orchestration, memory, integrations, not a wrapper). No proactive outreach until 5-10 paying customers + revenue + relationship leverage exists. Risk: if Anthropic preemptively flags us, we either pivot to Bedrock (Phase 3 brings forward) or scale back. Mitigation: document our architecture clearly so the value-add posture is defensible if asked.
2. **macOS signature regressions.** Once a year an Apple update bricks pkg-installed services (Tailscale got hit by 26.2). Calibrate: budget 1 emergency rebuild + customer support hotfix per year.
3. **EU AI Act enforcement.** Aug 2, 2026 high-risk deadline. Annex III use cases (HR, credit decisions) EXCLUDED from Phase 1 ToS. Calibrate: refuse Annex III use cases in Phase 1; build the compliance layer in Phase 3 only if revenue justifies.
4. **Danish-only Phase 1 ceiling.** Hard self-imposed: customer must be within physical reach. Risk: 5-Cabinet validation gate could take longer than expected if Danish SMB AI demand is softer than hoped. Mitigation: Phase 2 trigger (5 Cabinets stable) is phase-gated not calendar-gated; we don't rush.

---

## 14. Compounds with existing patterns

- **A1 (reversibility-gated autonomy):** LiteLLM swap-out reversible. Bedrock migration reversible. Dashboard UI reversible. .pkg distribution = one-way door (can't unpublish a notarized binary), so Phase 2 .pkg ships ONLY after Phase 1 install runbook is field-tested with ≥3 customers. Pricing model swap from 4-tier to one-tier (this v1.1) was reversible — we kept the option open.
- **A3 (build > add-dep, with carve-outs):** see §5; we build the differentiated surface, buy the commoditized layers.
- **A6 (minimal change over additive bolt-on):** every sub-spec scopes one capability; no kitchen-sink milestones. v1.1 amends section-by-section, doesn't rewrite the spec from scratch.
- **A11 (Library + /tasks canonical):** Spec 050 + FW-096..113 file to Library Specs Space (canonical), NOT to Notion/Linear (deprecated). Customer-facing dashboard subroutes (`/audit`, `/spend`, `/activity`) are A11-orthogonal product surfaces.
- **A12 (officer-in-loop on architecture, PROPOSED):** Nate authors all architecture decisions; Crew agents execute slices. Pre-/post-/self-/peer-review gates intact per Spec 049. Spec 050 itself was Opus-synthesized but Captain ratified positioning + pricing + caps before any sub-spec drafting commenced.
- **A13 (don't seek permission from gatekeepers before leverage):** Anthropic outreach dropped. Apple Business Reseller status deferred until 50+ MacMini customers. Bedrock Authorized Reseller deferred until $100K/yr Anthropic spend.
- **CoS milestone-DM discipline (feedback memory, CoS-only):** during long-running Captain-assigned strategic synthesis (this spec was one), surface material artifact ships via direct DM as they land, not just at start + final synthesis. Captain meta-feedback msg 2576 + scoped CoS-only per msg 2579.

---

**End of Spec 050 v1.2 (full-native architecture absorbed; §3 reconciled to the ratified $50/day-per-cabinet + one-tier model 2026-05-24 per CTO B1 review).** Next amendment fires on next Captain ratification of the remaining §12 pending items (A12 wording, commercial repo, Mac image-dist).
