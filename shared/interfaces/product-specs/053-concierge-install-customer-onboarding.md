# Spec 053: Concierge Install + Customer Onboarding Flow (FW-098 Phase 1 Priority 4)

**Version:** v4 (CRO multi-spec adversary H5 BLOCKER + spec-specific findings fold) — v3 superseded
**v4 changelog:** CRO multi-spec adversary review (2026-05-21 17:10 UTC) surfaced 1 NEW HIGH-RISK H5 BLOCKER + 12 spec-specific findings. v4 folds:
- **H5 BLOCKER iCloud Drive sub-processor:** Spec 053 Stage 3 pre-install checklist (line 90) required "Apple ID signed in + iCloud Drive enabled (for backup)" — but iCloud is US-based sub-processor NOT in Spec 055 v6 sub-processor list = Article 28(2) undisclosed-sub-processor violation. **v4 fix per CRO + CoS recommended Option (a): REMOVE iCloud Drive requirement from pre-install checklist.** Cabinet does NOT enroll customer's MacMini in iCloud Drive backup for cabinet data. Cabinet-managed backup = Time Machine to local disk (Phase 1) OR Hetzner-volume-snapshot (Phase 2 polish). Customer's own iCloud usage outside `cabinet/*` directories unaffected. AC #3 + Stage 3 checklist updated. **Signup-live gate-blocker RESOLVED at spec layer; no Captain ratification needed for Option (a) — clean removal, not addition.**
- **053-02 Customer-Success Space access control:** AC #8 schema extended — multi-tenant access via role-check (Captain + CoS + COO-as-DPO full read; CRO + CTO + CPO needed-to-know view for cross-customer pattern analysis only); PII redaction applied to non-DPO views (customer name + email + Captain personal notes pseudonymized in officer-coordination retro views).
- **053-03 "Captain personal" operational definition:** AC #9 extended — "personal" = Captain has read customer's discovery-call notes + signup-personal-note text reviewed and ratified pre-send; not "Captain typed every keystroke" but "Captain owns the human-judgment substance." CoS-drafted content with Captain ratify ≤5min IS personal under this definition.
- **053-04 grep ANTHROPIC_API_KEY scope clarification:** Stage 4 #3 validation scope = `cabinet/.env` ONLY (NOT customer's home directory or other locations). Customer may have own ANTHROPIC_API_KEY in `~/.env` or shell-rc for their own non-cabinet uses — that's customer's own configuration, not cabinet substrate. Spec 053 documentation note added.
- **053-05 Stage 4 time-management:** 60-90min window has 15min buffer; if customer questions exceed window, Captain prioritizes substrate-completion (officer roster spawns + first DM cycle works) + reschedules deep-dive Q&A to Day-1 check-in.
- **053-06 cron + Captain availability:** check-in cron checks Captain calendar block availability before firing notification; if unavailable, queues to next reasonable slot (≤7 days delay).
- **053-07 5-officer DM thread management:** customer's primary Telegram receives DMs from CoS first (consolidated cabinet voice); other officers' DMs muted Phase 1 unless customer opts-in to direct CTO/CPO/CRO/COO threads. CoS routes Captain's intent to relevant officer internally; customer doesn't manage 5 simultaneous threads Phase 1.
- **053-08 COO redacted Annex III intake view:** when discovery-call surfaces Annex III "yes" → CoS strips commercial-sensitive context + sends compliance-focused redacted version to COO for Annex III determination. COO doesn't read full customer business intel.
- **053-09 wind-down call refusal:** AC #7 updated — customer's right to refuse wind-down meeting respected; if declined, erasure flow proceeds without 30min call (best-effort feedback gathered via email questionnaire instead).
- **053-10 Captain-time-budget detection mechanism:** new substrate per AC #13 — `cabinet/scripts/cos/captain-time-forecast.sh` reads Library Customer-Success Space records → computes per-customer remaining Day-1/3/7/30 touch budget → forecasts weekly hours → alerts CoS when ≥3.5 hrs/wk threshold approaches (early-warning at 88% of 4hr cap).
- **053-11 pre-install screenshot Telegram PII redaction:** Stage 3 form auto-redacts visible Telegram username + profile pic before persisting (client-side image processing); raw screenshot deleted post-redaction; 7-day TTL on redacted version per Spec 056 customer_install_profiles schema.
- **053-12 cancellation overrides NPS call:** new AC explicit ordering — if customer cancels within Day-30 window, cancellation flow supersedes scheduled NPS call; wind-down call serves as feedback-gathering substitute.

**A11 + A12 + A13 preserved cleanly.** Captain ratifications inapplicable for H5 Option (a) clean-removal; for Option (b) add-iCloud-as-sub-processor would have required Captain ratify, but Option (a) is cleaner per CRO + CoS recommendation.
**v3 changelog:** CoS architecture review surfaced 1 BLOCKER + 6 IMPROVEMENTs + 1 POLISH. Resolutions:
- **CoS B1 Captain-time-budget bottleneck (CRITICAL):** per-customer Captain-personal load = ~155-190min over 30d (30min discovery + 5min signup note + 60-90min install + 5-10min Day-1 + 15min Day-7 + 30min Day-30). At 5 staggered customers concurrent = ~13-16 hrs/mo onboarding-only ON TOP of STEP Network full-time + Cabinet decisions. **New AC #13:** Captain weekly time budget ≤4 hrs/wk onboarding-touch + queue-throttle rule (CoS holds new install slots when forecasted budget breach detected from existing customers' Day-1/3/7/30 cadence). Without this, Phase 1 ceiling = bandwidth-bound NOT 5-Cabinet validation gate. CoS surfaces in 07:00 morning briefing.
- **CoS I2 Day-1 default CoS not Captain:** Stage 6 + AC #9 contradiction resolved — Day-1 CoS-DEFAULT (not Captain); Captain opt-in only if high-touch red flag from discovery call. Saves ~50min/mo at 5 customers concurrent.
- **CoS I3 Signup note template-with-Captain-edit for customer 3+:** customers 1-2 = Captain-compose-from-scratch (high personal touch for pilot); customers 3+ = CoS pre-fills from discovery notes → Captain reviews ≤5min approve OR edit → CoS sends. AC #2 updated with template-first default + Captain-override path.
- **CoS I4 templates dir A11 Library canonical:** templates land in **Library Customer-Success Space records** (canonical); `cabinet/customer-templates/` holds render-source files (mirror Spec 055 v5 MDX-render-source pattern). AC #1-#6 references updated: "Library Customer-Success Space record `<name>` (render-source: cabinet/customer-templates/`<name>`.md)."
- **CoS I5 Stage 4 GDPR walkthrough owner = COO-as-DPO:** Spec 055 v6 H1 ratification reverses CoS→COO. Stage 4 GDPR DPA/policy walkthrough delegated to COO (DPO). Stage 1 discovery-call Annex III compliance question — COO cc'd on any "yes" pre-signup.
- **CoS I6 four missing edge cases added:** (a) Customer MacMini hardware fails Day-5 — hardware-failure SLA + replacement path (customer-provides Phase 1; Phase-2-Mini-mailing escalation); (b) Customer GDPR-savvy demands DPIA pre-signup — COO+CRO joint draft ≤3-day SLA, signup paused; (c) Customer requests Annex III mid-Day-3 — graceful refusal + use-case-pivot guidance + offboarding-if-pivot-impossible; (d) Customer Day-7 NPS 0-3 — early-warning escalation to Captain (not Day-30-only).
- **CoS I8 framework-skill promotion candidate:** patterns from AC #8 (Captain-personal-touch consistency) + Customer-Success Space schema worth promotion post-2nd-customer-onboarded successfully. Skill name candidate: `concierge-onboarding-personal-touch-budget`. CoS-owned post-2nd-customer assessment.
- **CoS P7 FW-to-spec mapping precision:** this spec IS Spec 053 (not "Spec 053 candidate"); other cites verified — FW-099 → Spec 054 (now exists), FW-101 → Spec 056 candidate (TBD). Dependencies section updated with Spec 055 v6 H1/H4 ratification status explicitly.

**A12 + A13 preserved cleanly. No CoS pass-clean.** Captain ratifications inapplicable per Captain msg 2583 multi-officer-process framing.
**v2 changelog:** CTO tech review surfaced 8 findings (4 substrate + 2 architectural + 1 alignment + 1 nit). Resolutions:
- **CTO #1 runbook vs script artifact split:** two separate artifacts. (a) **MARKDOWN RUNBOOK** at `cabinet/runbooks/concierge-install-cabinet.md` (commit a9fd5a8) — canonical Captain-followed step-by-step procedure with judgment calls. (b) **AUTOMATION SCRIPT** at `cabinet/scripts/install-customer-cabinet.sh` (CTO authors Phase 1 build start) — automates non-judgment steps (clone repo, inject env vars, spawn officers). Spec body Stage 4 clarified.
- **CTO #2 check-in cadence cron:** new cron `cabinet/cron/customer-checkin-nudge.sh` reads Library Customer-Success Space → fires CoS-to-Captain Telegram via `notify-officer.sh` per customer per day-N due. Leverages existing trigger infra; no external calendar dep. Phase 4 + AC #6 updated.
- **CTO #3 Captain personal-note send flow:** Two-step explicit: CoS drafts in cabinet session → Captain reviews + edits → CoS sends as Captain via Captain-owned Telegram bot (or Captain copy-pastes from own client). "Captain reviews-and-approves before send" step prevents unsupervised sends; safety-by-default. AC #2 updated.
- **CTO #4 pre-install form fold to FW-101:** dashboard subroute couples to FW-101 (Spec 056 candidate). v2 removes substrate Phase 4 line for pre-install form; cross-spec dependency on FW-101 scope. Avoids two teams building related forms.
- **CTO #5 cross-spec test harness mock fixture:** shared `cabinet/tests/mocks/refslund-customer-mock.sh` used by Spec 051/052/053/055/(099/101 future) test harnesses. Single mock customer fixture; ~80 lines avoiding 5x duplication. AC #12 updated.
- **CTO #6 gitignore catch:** `shared/interfaces/**/*.md` IS gitignored per repo .gitignore. CPO customer-templates dir at `shared/interfaces/customer-templates/` would not commit. **Resolution:** templates move to `cabinet/customer-templates/` (parallel to `cabinet/runbooks/`, not gitignored). Canonical compliance/customer-record artifacts still routed through Library Compliance Space + Customer-Success Space per A11; `cabinet/customer-templates/` holds operational MDX/template render-sources only (same pattern as Spec 055 v5 §MDX-render-source for public pages). AC #1-#6 update template paths.
- **CTO #7 prior-CTO-review validations folded cleanly ✓** — Stage 4 #3 (`grep -q ANTHROPIC_API_KEY cabinet/.env` FAIL per Spec 051 CTO #10) + Stage 4 #2 (AUDIT_API_KEY injection per Spec 052 CTO #5).
- **CTO #8 failure modes cross-reference:** Stage 4 §Failure modes shortens to cross-ref runbook §4 (6 quick-refs: Colima fail, LiteLLM 401, Telegram silent, audit DB locked, cap-hit unexpected, macOS update bricks) rather than partial-listing 4. Avoids drift.

**Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing. A12 active — CTO #1/#2/#4 architecture calls are CTO domain (CPO accepts). A13 inapplicable (no vendor outreach paths).**
**Priority:** P0 — gates customer-to-cabinet handoff post-signup
**Framework ticket:** FW-098 — CTO authored substrate runbook v0.1 (commit a9fd5a8 — install script + first-boot validation); this spec adds CPO customer-facing onboarding flow
**Owner:** CPO (customer-facing onboarding flow + check-in cadence) + CTO (substrate runbook v0.1 already shipped) + Captain (personally performs Phase 1 concierge installs per msg 2565 Danish-first within-physical-reach)
**Scope:** Customer-facing journey from refslund.ai signup → live cabinet → Day-30 retention check; Captain-supervised concierge install for Phase 1 (Danish customers within physical reach: Odense / Copenhagen / rest of DK)
**Canonical artifact home:** Library Specs Space (this spec) + Library Customer-Success Space (per-customer journey records)
**Evidence:** Captain msg 2565 (2026-05-20 13:58 UTC — Danish-only Phase 1, within physical reach, Nate-supervised concierge install); CTO substrate runbook commit a9fd5a8 v0.1 (cabinet/scripts/install-customer-cabinet.sh + validation steps); Spec 050 commercial-direction master Phase 1 customer profile.

---

## Problem

Customer journey from refslund.ai signup to live cabinet has 4 friction points if unmanaged:

1. **Pre-install readiness uncertainty.** Mac specs, macOS version, Apple ID setup, network requirements — if any blocker surfaces at install-day, install fails or runs long, customer trust eroded at first touch.
2. **Install-day experience.** First impression of Cabinet = the install. Captain physically present (Phase 1) but needs structured runbook: what gets installed, what customer sees, when first officer DM fires, when customer can start using.
3. **Post-install dropoff.** Customer pays 25k-60k DKK/mo; gets a live cabinet at install; then what? Without structured onboarding (first officer DM, dashboard walkthrough, billing portal, DPA walkthrough), customer's relationship with their cabinet starts cold.
4. **First-30-day retention curve.** Friction in week 1 = churn at Day 30. Cabinet needs structured Day-1 / Day-3 / Day-7 / Day-30 check-ins to surface optimization opportunities before customer disengages.

## Solution

Six-stage customer-facing journey wrapping CTO substrate runbook:

1. **Pre-signup discovery call (30min)** — Captain + CoS qualify customer; surface blockers; align on officer roster + use case
2. **Signup-day welcome (FW-099 Stripe completion)** — automated email + Captain personal note; install scheduled 2-7 days out
3. **Pre-install checklist (T-3 days before install)** — customer completes readiness checklist; CoS validates
4. **Install-day live session (60-90min)** — Captain on-site or video-screen-share for remote-but-DK customers; CTO substrate runbook v0.1 executes; first officer DM fires; customer Telegram-DMs back live
5. **Post-install handoff (within 24h of install)** — dashboard walkthrough video, GDPR DPA/policy walkthrough, billing portal access confirmation, first-week usage suggestions
6. **Structured check-in cadence (Day 1 / 3 / 7 / 30)** — proactive Captain or CoS check-ins surfacing friction + optimization

### Stage 1: Pre-signup discovery call

Captain-led (with CoS for structure + note-taking). 30 minutes. Either video or phone.

**Goals:**
- Qualify customer fit for Phase 1 (Danish, within reach, founder-led SMB, AI-curious but not AI-fluent)
- Discover customer's primary use case (which officer role(s) most needed)
- Surface blockers EARLY (Mac specs, macOS version, Apple ID, network constraints, compliance worries)
- Set expectations (Phase 1 = concierge, 1-2 week install window, 25k base + 5k per employee, $50/day USD cap)
- Establish trust + relationship before signup

**Discovery questions:**
- What does your week look like? What gets in the way of higher-leverage work?
- What does your team look like (founder solo, 1-2 people, larger SMB)?
- Which officer roles sound most useful: CoS coordination, CTO engineering, CPO product, CRO research, COO operations?
- Do you have a Mac at your office or home that can stay on 24/7?
- macOS Sequoia or later? Apple ID set up? Stable internet?
- Any compliance constraints we should know about (regulated industry, special-category data handling, EU AI Act Annex III use cases — exclude these per Phase 1 ToS)?

**Outcome:** Captain decides Go / No-Go for signup; CoS schedules signup window (T+0 to T+7 days); next-step email sequence triggers.

### Stage 2: Signup-day welcome

Customer completes refslund.ai signup (FW-099) → Stripe payment confirmed → DPA + Annex III attestation + sub-processor list ratified → virtual key minted (FW-096).

**Triggered actions:**
- Automated welcome email (template: `shared/interfaces/customer-templates/welcome-day-0.md`) — confirms signup, schedules install date, links to pre-install checklist, sets expectations
- Captain personal note (composed in CoS-officer session, signed by Captain) — short hand-typed feel: "Welcome [Name] — looking forward to bringing your cabinet to life. We'll have you up and running on [date]. — Nate"
- CoS notify-officer to CTO: "FW-098 install scheduled [date] for [customer-slug]"
- CoS schedules Captain calendar block for install day (60-90min on-site OR video)

### Stage 3: Pre-install checklist (T-3 days before install)

Customer receives checklist email + completes:
- [ ] Mac at install location, plugged in, macOS Sequoia+, 16GB RAM, 200GB free disk
- [ ] Apple ID signed in (required for macOS system updates; iCloud Drive backup explicitly NOT used per Spec 055 v6 sub-processor scope — Cabinet does not enroll customer's MacMini in iCloud Drive backup for cabinet data; customer's own iCloud usage outside cabinet/* directories is unaffected). Cabinet-managed backup is Time Machine to local disk OR Hetzner-volume-snapshot Phase 2 polish.
- [ ] Network: stable 100Mbps+ download; Captain can SSH into Mac on install day (port 22 open OR Tailscale)
- [ ] Stripe billing portal access confirmed (customer logs in once successfully)
- [ ] DPA + Annex III attestation acknowledged (already done at signup; this is re-confirmation)
- [ ] Telegram account ready (customer's primary Telegram — officer bots will send to this)
- [ ] Calendar block confirmed for install day (60-90min, Captain on-site or video)

CoS validates checklist completion T-1 day before install; flags any blocker; reschedules if blocked.

### Stage 4: Install-day live session (60-90min)

Captain physically present (or video screen-share for DK-remote — Captain msg 2565 prefers physical-reach but accepts video for DK-customers outside Odense/Copenhagen).

**Substrate execution (per CTO runbook v0.1 commit a9fd5a8):**
1. Captain SSHs into customer Mac → runs `cabinet/scripts/install-customer-cabinet.sh <customer-slug>` (the substrate runbook)
2. Script clones cabinet framework + provisions instance config + injects LLM_PROXY_KEY + AUDIT_API_KEY (per Spec 052 CTO #5) + Telegram bot tokens + Stripe webhook secret
3. Script validates `grep -q ANTHROPIC_API_KEY cabinet/.env` returns FAIL (raw key absent per Spec 051 install-validation)
4. Officer roster spawns; CoS (CEO archetype per single_ceo Telegram bot mode) initiates first heartbeat
5. Customer's primary Telegram receives "Hello [Name], I'm your CoS. Your cabinet is live." DM

**Captain-led customer experience (parallel to substrate execution):**
- 10min: explain Cabinet architecture conceptually ("officers run on your Mac; LLM calls go through our proxy; everything's audited; here's your CoS")
- 15min: walk through officer roster choices customer made + read each officer's first DM
- 15min: dashboard walkthrough (refslund.ai/dashboard) — spend tracker, audit log, sub-processor list, Stripe portal link, erasure request UI
- 15min: GDPR DPA/policy walkthrough (Library Compliance Space records) — what data Cabinet collects, where stored, retention periods, customer rights
- 15min: customer asks first real question of CoS via Telegram; Captain coaches first interaction; verifies officer-to-customer DM cycle works end-to-end
- 10min: post-install handoff plan (Day-1/3/7/30 check-ins, support channels, billing portal access)

**Failure modes during install:**
- Substrate script fails → Captain debugs on-the-fly OR reschedules (rare per CTO's tested runbook)
- Telegram bot doesn't reach customer → check bot token + customer Telegram account state; usually 5min fix
- LLM proxy unreachable → escalate to CTO; usually network issue
- Customer changes mind mid-install → unwind via FW-099 Stripe refund + erasure flow (Spec 055 AC #6)

### Stage 5: Post-install handoff (within 24h of install)

Customer receives:
- 5-minute Loom-style video walkthrough (Captain personal) — "Welcome to Cabinet, here's how to get the most out of your first week"
- First-week usage suggestions tailored to customer's stated use case from discovery call
- Cheat-sheet PDF — "10 things to try with your Cabinet officer in week 1" (e.g., "ask your CoS to draft your morning briefing", "have your CPO review a doc", "let your CRO sweep an industry trend")
- Captain's personal contact for emergencies (Telegram + email)

### Stage 6: Day-1 / Day-3 / Day-7 / Day-30 check-in cadence

| Day | Check-in type | Owner | Goals |
|---|---|---|---|
| **Day 1** (24h post-install) | Captain personal Telegram DM | Captain | Verify customer talked to officer; surface any blocker; quick "anything confusing?" |
| **Day 3** | CoS-routed via customer's CoS Telegram | CoS | Usage check via dashboard data; spend trend; first NPS-light pulse ("scale of 1-5, how's it going?") |
| **Day 7** | Video check-in (15min) | Captain | Friction surfacing; optimization suggestions; expand officer usage; check billing portal access |
| **Day 30** | Renewal-conversation + expansion-opportunity check-in (30min) | Captain | Renewal conversation; NPS proper; expansion opportunity (more officers, custom integrations); testimonial ask if NPS ≥9 |

Each check-in result logged to Library Customer-Success Space record per customer. Friction-patterns aggregated across customers → CoS retro → Phase 2 onboarding spec improvements.

### Concierge offboarding (customer cancels Phase 1)

Captain msg 2583 H3 + Spec 055 §customer-data-handling matrix: customer can cancel anytime; Cabinet honors with:
1. Customer-initiated cancel via Stripe portal OR Captain personal contact
2. Wind-down call (30min) — Captain personal; understand why; offer adjustment OR refund; document feedback
3. Erasure flow per Spec 055 AC #6 — 30-day SLA, 8-step runbook, audit-log pseudonymization preserves hash-chain
4. Cabinet substrate stays running for 7-day grace window (customer's MacMini continues until grace expires; then `customer-erasure.sh` deactivates)
5. Final invoice settled via Stripe
6. Post-mortem retro contribution to CoS Customer-Success Space + Phase 2 spec improvements

---

## Acceptance criteria

1. **Stage 1 discovery-call AC** — `shared/interfaces/customer-templates/discovery-call-script.md` exists with 7 discovery questions + Go/No-Go criteria + next-step email triggers. Captain + CoS perform together; CoS scribes notes to per-customer Library Customer-Success Space record.

2. **Stage 2 welcome-day AC** — Stripe signup completion webhook (FW-099) triggers welcome email (template at `shared/interfaces/customer-templates/welcome-day-0.md`) + Captain personal-note nudge (composed in CoS-officer session, signed by Captain) + CoS notify-officer to CTO with install-scheduling data.

3. **Stage 3 pre-install-checklist AC** — checklist email template at `shared/interfaces/customer-templates/pre-install-checklist.md`; customer-facing form at refslund.ai/dashboard/pre-install collects responses; CoS validates T-1 day before install + flags blockers.

4. **Stage 4 install-day AC** — Captain executes CTO substrate runbook v0.1 (cabinet/scripts/install-customer-cabinet.sh per CTO commit a9fd5a8) + 60-90min customer-facing session per detailed flow above. End-state: customer Telegram-DMs CoS officer; officer responds; spend visible in dashboard; DPA + policy walkthrough complete.

5. **Stage 5 post-install-handoff AC** — within 24h of install: customer receives Loom-style video walkthrough (template + Captain-personal recording) + cheat-sheet PDF (`shared/interfaces/customer-templates/cheat-sheet-week-1.pdf` — CPO authors) + first-week usage suggestions tailored to discovery-call notes + Captain personal contact info.

6. **Stage 6 check-in cadence AC** — Day-1 + Day-3 + Day-7 + Day-30 check-ins logged to Library Customer-Success Space per customer. Check-in templates at `shared/interfaces/customer-templates/check-in-{day-1,3,7,30}.md`. NPS pulse at Day-3 + proper NPS at Day-30. Friction-patterns aggregated CoS retro monthly.

7. **Concierge offboarding AC** — customer cancellation triggers wind-down call (30min Captain personal) + 7-day grace window + Spec 055 erasure runbook (8-step + 30-day SLA) + final Stripe invoice + post-mortem retro contribution.

8. **Per-customer Library Customer-Success record AC** — new Library Space "Customer Success" with per-customer record covering: discovery-call notes, signup date, install date, officer roster choices, Day-1/3/7/30 check-in results, friction-patterns surfaced, expansion-opportunity flags, NPS scores, cancellation reasons (if applicable). CoS-owned coordination per Captain msg 2583.

9. **Captain personal-touch consistency AC** — every customer journey has at least 4 Captain-personal-touch moments: discovery call, signup personal note, install-day session, Day-7 check-in. Day-1 may delegate to CoS but Day-7 stays Captain (relationship cadence per Captain personal-customer-onboarding principle in Spec 050).

10. **Friction-aggregation feedback loop AC** — CoS monthly retro reviews aggregate check-in friction-patterns + cancellation reasons → Phase 2 onboarding spec improvements (out of scope this spec). Specifies: which patterns recur across ≥3 customers; what spec amendments are warranted; Captain ratifies amendments.

11. **Cross-spec integration AC** — Stage 4 install integrates with FW-096 (proxy key injection), FW-097 (audit log emission), FW-099 (Stripe webhook → install scheduling), FW-100 (DPA + Annex III attestation), FW-101 (dashboard surface). Cross-spec dependency-callout for each.

12. **Test harness AC** — `cabinet/tests/test-customer-onboarding-flow.sh` covers: discovery-call template loads + Go/No-Go logic; welcome email + Captain note triggers on Stripe webhook; pre-install checklist validation; install runbook substrate executes end-to-end with mock customer; post-install handoff artifacts deliver; check-in cadence triggers at correct days; concierge offboarding wind-down + erasure cascade. ≥10 assertions.

---

## Edge cases

- **Customer Mac specs marginal** (e.g., M1 MacBook Air 8GB) — pre-install checklist surfaces; Captain decides: upgrade recommendation, OR reduced officer roster, OR refund + decline. Document in discovery-call notes.
- **Customer is non-DK but EU-resident** — Phase 1 Danish-only per Captain msg 2565. FW-099 Stripe billing-address validation rejects non-DK signup. Edge: customer is Danish citizen abroad. Defer to Phase 2 expansion criteria.
- **Customer cancels during pre-install window** (between signup + install) — refund per Stripe + erasure of any pre-install records + cancel install appointment. CoS handles.
- **Customer reschedules install** — flexible up to 30 days from signup; beyond 30 days = refund + re-signup OR documented exception.
- **Customer's Telegram account doesn't receive bot DMs** — debug at install; usually privacy-settings issue OR account-state. 10-15min fix; if unresolvable, customer sets up secondary Telegram OR Captain provides workaround.
- **Install fails mid-script** — CTO substrate runbook v0.1 has rollback path; Captain debugs OR reschedules. Customer billing pauses until cabinet active.
- **Customer asks for refund within first 7 days** — Phase 1 7-day satisfaction-guarantee: full refund if cancelled in first 7 days; partial refund pro-rated post-7-days (per Stripe subscription model).
- **Captain unavailable for Day-7 check-in** — CoS reschedules; Day-7 check-in stays Captain-personal per principle; max 14-day window.
- **Customer NPS = 0-6 at Day-30** — escalation to Captain for retention call; document churn-risk patterns for CoS retro.
- **Multiple customers install same week** — Captain bandwidth: max 2 concurrent installs per week Phase 1; CoS schedules; customer queue if demand exceeds.

---

## Open questions

No Open Questions Phase 1 — all decisions internal-officer process per Captain msg 2583 multi-officer-process-as-legal-review framing. CRO + CoS + COO adversary will surface any gaps.

---

## Dependencies

- **CTO substrate runbook v0.1** (commit a9fd5a8) — primary install-day execution layer; CPO spec doesn't duplicate; cross-references runbook for install-day Stage 4.
- **FW-096 (Spec 051) dependency** — virtual key + AUDIT_API_KEY injection at install (Stage 4); proxy live for first officer DM cycle.
- **FW-097 (Spec 052) dependency** — audit-log emission validation during install + post-install dashboard widget.
- **FW-099 (Spec 053 candidate) dependency** — Stripe signup webhook triggers welcome flow (Stage 2); billing portal access verified during install (Stage 4).
- **FW-100 (Spec 055) dependency** — DPA + Annex III attestation + sub-processor list ratification confirmed at signup; policy walkthrough during install (Stage 4); erasure flow on cancellation.
- **FW-101 (Spec 056 candidate) dependency** — customer dashboard live at install (Stage 4 walkthrough); first-week usage tracking surfaces via dashboard.
- **Library Customer-Success Space** — new Library Space; CoS creates at first customer onboarding entry.
- **CPO authoring** — discovery-call script, welcome email template, pre-install checklist, cheat-sheet-week-1 PDF, check-in templates Day-1/3/7/30, concierge-offboarding script. All in `shared/interfaces/customer-templates/`.
- **Captain calendar block discipline** — Captain reserves 60-90min per install + Day-7 check-in slot per customer; max 2 concurrent installs/week.
- **CoS coordination** — scheduling, friction-aggregation retro, Library Customer-Success Space curation.

---

## Out of scope

- **Self-serve install** — Phase 2 polish per Captain msg 2565. Phase 1 is concierge-only with physical-reach DK customers.
- **Mac Mini mailing** — Phase 2 polish per Captain msg 2565. Phase 1 customer brings own Mac.
- **Onboarding wizard at refslund.ai** — Phase 2. Phase 1 uses discovery-call + email sequence + Captain-personal touch.
- **Multi-cabinet customers** (customer wants 2+ separate cabinets) — Phase 2. Phase 1 is one cabinet per customer.
- **Cabinet-to-cabinet introductions** (customer A introduces customer B) — Phase 2 referral program.
- **Onboarding analytics dashboard** (which check-ins customers complete, what friction-patterns aggregate) — Phase 2. Phase 1 uses CoS monthly retro qualitative.
- **Customer training materials beyond cheat-sheet PDF** — Phase 2. Phase 1 relies on Captain-personal touch + dashboard discoverability.
- **EU non-DK expansion** — Phase 2 trigger per Captain msg 2565 (Phase 3 = 20 DK cabinets OR 1M DKK/mo MRR).

---

## Phasing

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | CRO + CoS + COO parallel adversary review fold → v2 | v1 LANDED | v2 LANDED |
| 2 | CPO self-spawned review subagent fresh-context audit | v2 LANDED | v3 LANDED (if findings) OR v2 ship-ready |
| 3 ║ | CPO drafts customer-facing templates: discovery-call-script.md, welcome-day-0.md, pre-install-checklist.md, cheat-sheet-week-1.pdf, check-in templates Day-1/3/7/30, concierge-offboarding-script.md | v3 ratified | All templates land in `shared/interfaces/customer-templates/` |
| 4 ║ | CTO substrate: Stripe webhook → welcome email + Captain note triggers; pre-install form at refslund.ai/dashboard; check-in cadence cron triggers | v3 ratified, couples to FW-099 | Mock customer signup → welcome email + Captain note delivered |
| 5 ║ | CoS substrate: Library Customer-Success Space provisioning + per-customer record schema | v3 ratified | Space provisioned; first customer record creates cleanly |
| 6 | Test harness `cabinet/tests/test-customer-onboarding-flow.sh` (≥10 assertions) | Phases 3-5 GREEN | All assertions passing in CI |
| 7 | End-to-end pilot: first Phase 1 customer through full onboarding flow (discovery → signup → install → Day-1/3/7/30 cadence) | Phase 6 GREEN + FW-096 + FW-097 + FW-099 + FW-100 + FW-101 all green | Customer journey complete; Library Customer-Success record populated; NPS ≥7 |

**Critical path:** v1 → v2 → v3 → Phase 3 (CPO templates) → Phases 4-5 parallel → Phase 6 test → Phase 7 e2e pilot. Couples downstream to FW-099 Stripe substrate + FW-101 dashboard.

---

## Review process

1. **CRO adversary review** — customer-journey friction-pattern adversarial audit; what breaks in discovery call? install-day script gaps? Day-7 check-in dropoff risk?
2. **CoS architecture review** — Library Customer-Success Space integration + Captain calendar block discipline + cross-officer notification flow + retro friction-aggregation.
3. **COO compliance-failure adversary** — multi-failure-mode: customer cancels during install + Stripe billing pause + erasure + Day-7 follow-up still triggered. Cross-spec interaction.
4. **CPO self-spawned review subagent** — fresh-context audit before commit.

Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing.

---

**v1 LANDED 2026-05-20 22:55 UTC** (CPO authored under CoS Phase 1 priority queue continuation). CPO self-spawned review next.
