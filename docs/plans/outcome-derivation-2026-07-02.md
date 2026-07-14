# Outcome Derivation — 2026-07-02 (first manual direction→outcome pass)

**Method.** Manual one-shot derivation per `instance/config/directions.yml` header
(Captain-confirmed 2026-07-02): read direction contract + `docs/work-model.md`
semantics → scan Monday (READ-ONLY, dev-tasks MCP) → propose outcomes that pass
the inclusion test (verifiable state change X→Y) AND the campaign test
(orchestration the stream can't give), each citing its direction bet + expected
instrument delta. Window cap 1–2 active/lane respected. No Monday writes made.

**Boards scanned (Tasks board 5091706356, Bugs queue, Epics, Sprints).**
- PolAds (productId 2723505568): 15 epics; backlog NR+Ready ≈145 (100 sampled,
  cursor confirms more); In Progress+Stuck 27; bugs Critical 19 / High 34
  (of ~141 total per Captain baseline).
- STEPhie (productId 2730518827): 9 epics; backlog NR+Ready **0**; In Progress 5.
- Sprints: Sprint 11 [Active, since 2026-06-17, goal "registration flow and
  frontpage"]: 198 tasks — NR 13 · Ready 2 · InP 16 · **UAT 62 · PendingDeploy 77**
  · Done 8 · Stuck 2. Queued: S12 (39, NR 27), S13 (6, "Subscription flow"),
  S15 (21, security/test), S16 (13, "Launch PolAds subscription + SSP"),
  S17 (20, "Launch SSP"), S14/18–23 near-empty.
- Spot-verified task statuses via getTask for all 5 June-wave Criticals.

---

## LANE: polads

**Direction recap.** Compliant-by-construction EU political-ads transparency,
self-serve, launch-grade by Sept 1. Bets: subscription & billing (Basic+Pro) ·
publisher dashboard · advertiser registration flow · AI-based support.

**Board evidence.**
- Subscription & Pricing Model epic #2843293535: **0/37 done**, owner colleague-C —
  the named #1 bet is the least-landed epic. But motion exists: Paddle account
  setup InP (3004956577), Paddle EU/US compliance **Stuck** (3004954017), Navision
  requirements InP (3004956572), WS-2a/3b/4b/4d billing follow-ups in NR
  (3018047387, 3019350020, 3018114858, 3019803817); price model approved by
  colleague-C 2026-07-01. Sprint 13/16 goals are subscription launch.
- Basic/Pro entitlement mass sits in Publisher UX #3000598672 (13/84): Basic
  lock/greyout InP (3036217684), Basic wallet/credits NR (3036649194), Pro
  share-credits InP (3038863708), Pro post-login redirect NR (3036567320),
  amendment credit-charge NR (3033388843, 3042031910).
- Publisher dashboard converged-v4: umbrella Critical NR (3024648789); T2/T4/T6/
  T7/T8/T10 all In Progress, T9 tests Ready (3025000015) — active mid-flight mass.
- Advertiser UX #3000574508: 144/220 (65%) — registration flow largely landed;
  remainder is item-shaped fixes (in-kind redesign 3042750167, transparency-notice
  Annex II items 3032301884/3032341304/3032320121, validation/i18n).
- Complaint & Legal #2997809072: 5/27 (19%) — ~10 Art. 15 items queued in S16.
- Bugs: 19 Critical — 12 are security-audit items in **Pending Deploy**, and
  **CI staging bug 2924046344 still "Fixing"** (polads-001's first node is
  verifiably open). 34 High.
- The big picture: Sprint 11 carries a 139-item UAT(62)+PendingDeploy(77) drain
  toward prod — that is polads-001-prod's gate, not new-outcome material.

### Proposed outcome — outcome-polads-004 (fill slot 2, freed by polads-003)

- **id:** outcome-polads-004
- **name:** "PolAds Basic+Pro subscription & billing live end-to-end"
- **State change (one sentence):** From price-model-approved-but-unbillable
  (epic 0/37, Paddle in sandbox/Stuck, entitlements half-enforced) to a customer
  can subscribe, be correctly entitled Basic vs Pro, and be charged with a
  reconciled ledger in production.
- **Direction fit (mandatory):** serves bet **"subscription & billing
  finalization (Basic + Pro)"**. Expected instrument delta:
  `basic_to_pro_conversion` goes from unmeasurable → live-measurable with first
  real upgrades; `v1_live` prerequisite satisfied for the Sept 1 launch-grade
  bar; `self_serve_registration_completion` extended to paid flows.
- **measurable_criteria (node drafts):**
  1. `polads-004-entitlements` — *Basic/Pro entitlement matrix enforced
     server-side, verified on staging.* Acceptance: written entitlement matrix
     (one page, Captain-visible); Basic lock/greyout (3036217684), Basic
     wallet/credits open (3036649194), Pro share-credits (3038863708), dashboard
     T7 Pro-gate (3024648996) each conform to the matrix with a regression test.
     Evidence: matrix doc + PR links + staging verification notes. Risk: medium.
  2. `polads-004-ledger` — *Wallet/credit ledger + checkout correctness closed.*
     Acceptance: wallet-ledger UNIQUE index + qty-from-billed-amount (3018114858);
     UpgradeCheckout state machine unit-tested (3019803817); live-amendment
     1-credit charge wired per rule #3032953940 (3033388843); no
     double-charge path demonstrable. Evidence: merged PRs + green tests +
     ledger-integrity test output. Risk: medium.
  3. `polads-004-paddle` — *Paddle production readiness decided and configured.*
     Acceptance: EU/US compliance investigation (3004954017, currently Stuck)
     resolved with a written disposition; VAT/tax + payout policy documented;
     sandbox→production config plan. **PROPOSE-ONLY: any spend/production Paddle
     config change executes only after explicit Captain approval.** Evidence:
     decision doc + config diff proposal + Captain approval record. Risk: high.
  4. `polads-004-live` — *First real Basic→Pro upgrade + top-up transaction in
     production, reconciled.* Acceptance: prod flip of billing surfaces; one real
     (or Captain-designated pilot) transaction completes and reconciles in the
     ledger; rollback path documented. **PROPOSE-ONLY: production deploy + real
     money — hard ceiling, Captain approval required per step.** Evidence:
     sanitized transaction record + ledger reconciliation + approval trail.
     Risk: high.
- **Deliberately NOT included (stays stream):** publisher-dashboard T-series
  (own mass), advertiser-UX fix queue, complaint/legal queue, Navision *build*
  (only its requirements doc feeds polads-004-paddle), security bug drain.

### Queued draft (NOT active — window cap) — outcome-polads-005

- **id:** outcome-polads-005 (draft; activates only when polads-001 achieves,
  or if Captain rules it stream instead — see ratification card #4)
- **name:** "Publisher dashboard converged-v4 cutover live"
- **State change:** publishers move from old dashboard → converged-v4 (Home/
  Records/Market-Insight/Pro-gate) live in production, 24-locale parity.
- **Direction fit:** serves bet **"publisher dashboard"**. Instrument delta:
  `support_load_per_customer` ↓ (self-serve status answers),
  `basic_to_pro_conversion` ↑ (T7 Free-teaser is the upsell surface).
- **Node sketch:** (1) T-series complete+verified (T2 3024989131, T4 3024990331,
  T6 3024988454, T7 3024648996, T8 3025020850, T9 3025000015, T10 3025762374)
  each w/ tests — medium; (2) i18n 24-locale parity sweep evidence — low;
  (3) prod cutover + smoke — **PROPOSE-ONLY (production)** — high.
- **Honesty note:** this work is already flowing as stream T-tasks in Sprint 11;
  the outcome adds a verification+cutover gate. If the Captain judges the stream
  is carrying it fine, "stream" is a legitimate ruling — cap, not quota.

### Stream, NOT outcome material (discipline list)

- Advertiser registration flow (bet 3): remaining board mass is item-shaped
  fixes/polish (Sprint 12 NR queue) — the campaign already happened in June.
- **AI-based support (bet 4): no epic, no mass** — only Compliance Advisor NR
  (2780384106), RAG chatbot corpus gap (bug 2981096267), AI-assistant
  organisation-advertiser task (3016419163). Needs a spec before it can be
  outcome-shaped; commissioning that spec is stream work (open question #10).
- Complaint & Legal Art. 15 queue (~10 items, S16) — item-shaped today; flag as
  a *future* compliance-push outcome candidate only if it grows ordering needs.
- 12 Critical security bugs in Pending Deploy + Maintenance & Hotfixes (45/105):
  Criticals get pulled because they are Critical (work-model), not wrapped.
- Sprint 11 UAT(62)+PD(77) drain: governed by polads-001-prod's existing gate —
  a stream-SLO ("UAT queue ≤ N", "PD age ≤ N days") is the right control, not
  an outcome.

### Replaced-outcome dispositions

- **outcome-polads-001 — STAYS ACTIVE (slot 1).** Verifiably unfinished: CI
  staging bug 2924046344 still "Fixing" (node polads-001-ci open); prod release
  not shipped; Sprint 11's 139-item UAT/PD drain is exactly what its prod gate
  governs. **Amend with billing-freeze note:** billing/subscription surfaces are
  excluded from polads-001-prod's smoke scope and do NOT ship under its gate
  while polads-004 is in flight — polads-004-live owns the billing prod flip
  (exact wording: ratification card #2).
- **outcome-polads-003 — RECOMMEND ACHIEVED, remainder to stream.** Verified on
  the board 2026-07-02: 4/5 Criticals **Done** — NME logo 2979108084 (done
  06-17, PR #419), Chatbot-DPA 2979102928 (done 06-25), Citizen search
  2979116873 (done 06-17, PR #425), Windows flags 2979117218 (done 06-17,
  PR #468); anchor Beta epic 2833952138 **Done 88/88** (zero NR on it — the
  triage criterion's catch-all is satisfied). Verifiably left, all item-shaped:
  (a) 2979104881 content-overflow — Critical, **Needs Refinement, unassigned,
  now epic-less/sprint-less** (fell off the board's structure); (b) cited triage
  items still NR: 2979083289 VIES (S12), 2975934613 EU-Repository feedback
  (S11); (c) the formal per-item closeback list was never produced. Per
  work-model ("recurring waves are stream; polads-003 runs once as bootstrap"),
  the honest call is achieved-with-remainder: the campaign's state change
  happened; the 3 stragglers are stream items (2979104881 needs re-attachment
  to an epic + sprint), and wave quality lives as a stream SLO hereafter.

---

## LANE: stephie

**Direction recap.** Best 24/7 fast on-demand advertiser/agency ad-booking
service. Bets: generalize the proven job-banner flow (/create/job-banners) into
the booking front-door · officer-backed 24/7 service desk ·
performance-optimization loop.

**Board evidence.**
- Backlog (NR+Ready): **empty — zero tasks.** The lane's entire live board is
  5 In-Progress items, all Banner Creator: feedback round 2 (2983665533 + literal
  "(copy)" duplicate 3004954044), round 3 (2998214826 + duplicate 3004954179),
  CI pipeline improvement (2999287457).
- AI Campaign Planner epic #2730519291: 170/170 (100%, still marked In
  Progress — status lags reality). Banner Builder #2730539032: 13/21 (62%).
  Maintenance #2743418451: 4/4.
- The direction's booking bets map to epics that are **all empty Backlog
  shells**: GAM Campaign Order #2730544524, GAM Reporter #2730542712, GAM
  Optimizer #2730533595, AdForm programmatic #2891789200, Publisher BookingBot
  #2891783966, AdCP integration #2891795729 — no tasks in any of them.
- Conclusion: the new direction has almost no board backing; the successor
  outcome must be derived from the direction bets, and it will *create* the
  first tasks in those epic shells.

### Proposed outcome — outcome-stephie-002 (slot 1; slot 2 deliberately empty)

- **id:** outcome-stephie-002
- **name:** "Booking front-door v0 — job-banner flow generalized to a second
  bookable format with order handoff"
- **State change (one sentence):** From single-purpose job-banner tool
  (/create/job-banners is the only self-serve path) to a booking front-door
  where an advertiser can take ≥1 additional ad format from request → creative →
  structured order draft end-to-end on staging, live behind a flag.
- **Direction fit (mandatory):** serves bet **"generalize the proven AI
  job-banner flow into the booking front-door"** (feeds bets 2–3 later).
  Expected instrument delta: `self_served_booking_rate` from 0/unmeasurable →
  first measurable pilot value; `request_to_live_lead_time` gets its first
  non-job-format baseline measurement.
- **measurable_criteria (node drafts):**
  1. `stephie-002-spec` — *Front-door generalization spec.* Acceptance: format
     model (what makes a format bookable), reuse map of the job-banner canvas
     pipeline, GAM order-handoff shape, measurable acceptance criteria + effort
     estimate; spec passes spec-quality-gate; explicitly bounded by the stephie
     not_goals (Captain must fill the directions.yml TODO first — card #11).
     Evidence: spec doc in shared/interfaces/product-specs/. Risk: low.
  2. `stephie-002-format2` — *Second format creative flow works on preview.*
     Acceptance: an advertiser produces a campaign-ready creative of the chosen
     second format end-to-end on a preview deployment; regression tests on the
     generalized (non-job-specific) pipeline pieces. Evidence: PR links on
     STEP-Network/stephie-mcp + preview URL + verification notes. Risk: medium.
  3. `stephie-002-order` — *Booking request → structured order draft.*
     Acceptance: a submitted booking request yields a validated order object
     (GAM order draft or internal booking record) with read-only GAM
     verification of targeting/inventory references; first tasks created in the
     GAM Campaign Order epic #2730544524. **PROPOSE-ONLY: any GAM write /
     live order creation requires explicit Captain approval.** Evidence: order
     object samples + read-only GAM verification transcript. Risk: medium.
  4. `stephie-002-pilot` — *Live behind flag + pilot measurement.* Acceptance:
     front-door live on ai.stepnetwork.dk behind a feature flag; one pilot
     booking exercised; `request_to_live_lead_time` + `self_served_booking_rate`
     baseline recorded for the direction's trend instruments. **PROPOSE-ONLY:
     production deploy needs Captain approval; any advertiser-facing pilot
     comms go via brain queue_draft (external_comms ceiling).** Evidence:
     deployment id + flag config + baseline measurement note. Risk: high.
- **Deliberately NOT included (stays stream/queued):** the 24/7 service-desk
  bet (needs the front-door to exist; queue as successor candidate
  outcome-stephie-003) and the performance-optimization loop bet (queue behind
  service desk); Banner Creator feedback waves; GAM Reporter/Optimizer, AdForm,
  AdCP, BookingBot epics stay empty until the front-door validates.

### Stream, NOT outcome material

- Banner Creator feedback rounds 2 + 3 (recurring UAT waves = stream per
  work-model; polads-003 set the precedent).
- CI pipeline improvement 2999287457.
- Board hygiene: close the two literal "(copy)" duplicates (3004954044,
  3004954179) and correct AI-Campaign-Planner epic status (170/170 but "In
  Progress") — propose-first Monday writes, one-line each in next briefing.

### Replaced-outcome dispositions

- **outcome-stephie-001 — RECOMMEND VERIFY-ACHIEVE.** Captain states the
  job-banner creator shipped at /create/job-banners (2026-07-02). Board
  corroborates: feedback rounds 2 and 3 exist and are In Progress (waves only
  exist after round 1 closed); Banner Builder epic at 13/21. Verification
  residue before flipping to achieved: confirm the four round-1 fixes carry
  their regression tests, and locate the stephie-001-dragspec artifact — note
  the drag/reposition need is being served by round-2 stream work ("Canva-style
  free movement", 2983665533); if no spec doc exists, fold that intent into
  stephie-002-spec rather than blocking achievement on it.
- **outcome-stepnetwork-001 — RETIRE.** Captain ruling 2026-07-02: stepnetwork
  lane dormant ("someone else is doing this"), no direction authored
  (directions.yml lines 72–74). Retire without successor; residual website
  mini-tasks are parked/unowned pending a future lane decision.

---

## LANE: system-self

**Direction recap.** Self-improving org: verified outcomes per Captain-minute ↑,
escalation rate ↓, evidence never starving. Bets: the two master plans executed
to their milestone ladders.

**Evidence + disposition (no new proposals).** Window already full and healthy:
outcome-system-self-001 (typed policy engine shadow→enforcing) and
outcome-system-self-002 (inbound-mail quarantine) both active, both map directly
to the master-plan bet and the `autonomy_coverage` / `repeat_incident_rate`
instruments. This derivation run itself is the directions-layer milestone from
the plan addendum. No change requested; renewal fires on their achievement.

---

## Captain ratification card (one reply ratifies)

Reply with e.g. "1 ✓, 2 ✓ (wording: …), 3 ✓, 4 stream, 5 ✓, 6 ✓, 7 ✓, 8 ✓,
9 ✓, 10 yes, 11: <not-goals>".

1. **polads-003 → achieved**, remainder to stream (2979104881 re-attach to
   epic+sprint; 2979083289, 2975934613 stay in stream triage). [accept/reject]
2. **polads-001 stays active + billing-freeze note** — proposed wording:
   "billing/subscription surfaces excluded from polads-001-prod smoke scope;
   billing ships only via polads-004-live's gate". [accept/edit wording]
3. **outcome-polads-004** (Basic+Pro billing live) → ratify ACTIVE in polads
   slot 2. [accept/edit/reject]
4. **outcome-polads-005** (dashboard v4 cutover) → hold as QUEUED DRAFT for
   polads-001's slot, or rule it stream. [queued-draft | stream]
5. **stephie-001 → verify-achieve** (evidence check per disposition, then
   achieved). [accept/reject]
6. **stepnetwork-001 → retire** (lane dormant per your 2026-07-02 ruling).
   [accept]
7. **outcome-stephie-002** (booking front-door v0) → ratify ACTIVE in stephie
   slot 1. [accept/edit/reject]
8. **stephie slot 2 deliberately empty**; service-desk then performance-loop
   queue behind 002's validation. [accept]
9. **system-self unchanged** (001 + 002 fill the window). [accept]
10. **AI-based support bet**: commission the scoping spec now as stream work?
    [yes/no]
11. **Fill stephie not_goals** (directions.yml TODO-CAPTAIN) — needed before
    stephie-002-spec finalizes scope. [answer]

*Read-only run: no Monday statuses were changed; this document is the only
artifact produced. Derivation per directions.yml contract — every proposal
cites its bet + instrument delta; outcomes remain Captain-ratified only.*
