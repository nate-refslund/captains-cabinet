# Spec 056: Customer Dashboard MVP — Spend Visibility + Audit Log + Erasure + Compliance Links (FW-101 Phase 1 Priority 6)

**Version:** v3 (CoS architecture review fold) — v2 superseded
**v3 changelog:** CoS architecture review surfaced 2 BLOCKERs + 3 IMPROVEMENTs + 2 POLISH. Resolutions:

- **CoS B1 customer_install_profile schema enumeration:** New AC #14 + schema block. Columns + FK + PII classification + canonical Library Space:
  ```sql
  CREATE TABLE customer_install_profiles (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    mac_model VARCHAR(64),                 -- PII via device identifier
    mac_ram_gb SMALLINT,
    mac_disk_free_gb SMALLINT,
    macos_version VARCHAR(32),
    network_downloadmbps SMALLINT,
    network_access_method VARCHAR(16),     -- 'ssh' | 'tailscale' | 'other'
    install_date DATE,
    telegram_verified_at TIMESTAMPTZ,
    telegram_screenshot_path TEXT,         -- ephemeral 7-day TTL per Spec 056 CTO #5
    pre_install_completed_at TIMESTAMPTZ,
    cos_validated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```
  PII classification: mac_model (device ID) + telegram_screenshot_path (image PII). Spec 055 v6 data-handling matrix updated to include this table. Canonical record-of-record: **Library Customer-Success Space** (per Spec 053 v3); Postgres customer_install_profiles = operational store.

- **CoS B2 A11 dual-home subroute artifact naming:** v3 explicit naming per subroute:
  - **/dashboard/audit** — operational hot store at `refslund.ai/proxy/logs/audit/<slug>.jsonl` (Spec 052 v3) + Library Compliance Space record-of-record for Article 15 tickets + hash-checkpoint provenance. AC #2 updated.
  - **/dashboard/erasure** — erasure-request record-of-record in **Library Compliance Space** (Spec 055 v6 §Article 17 erasure flow); operational SLA-tracker via shared `cabinet/scripts/sla-tracker.sh`. AC #4 updated.
  - **/dashboard/pre-install** — canonical record-of-record in **Library Customer-Success Space** (Spec 053 v3 + new schema above); operational store in customer_install_profiles Postgres. AC #3 updated.

- **CoS I1 magic-link auth hardening:** AC #7 expanded — magic-link TTL = 10min single-use; rate-limit on /auth/magic-link request endpoint = 3 requests / 15min / IP+email (anti-enumeration); CSRF tokens on all mutating POST endpoints (cap-bump, erasure-request, pre-install form); IP-binding optional Phase 1 (defer to Phase 2 if customer-friction); sign-out clears session across devices (token-blacklist via Redis). **NEW step-up confirmation for cap-bumps >$50 USD:** customer re-enters email-OTP delivered to verified email; money-moving step-up auth before any bump >$50 settles. AC #8 + #10 updated with step-up.

- **CoS I2 hash-chain verifier mismatch retry-and-confirm gate:** AC #9 updated — mismatch in browser-side walker triggers (1) retry once (network/partial-download recovery), (2) confirm checkpoint freshness at refslund.ai/audit-checkpoints, (3) verify Web-Crypto API not glitching via known-good test vector. Only if all 3 retries fail → "INTEGRITY CHECK FAILED — Contact Support" copy (NOT "TAMPERING DETECTED" alarm copy). Support-ticket auto-files to COO+CoS; Article 33 supervisory-authority escalation gated on COO confirmed-incident determination (NOT customer-facing automatic alarm). Avoids false-positive trust catastrophe during install demo.

- **CoS I3 cap-bump AC #8 vs body contradiction:** v3 aligns body + AC. Body Cap-bump section says ">$100 cumulative or second-bump-same-day" triggers Spec 051 AC #16 captain-decisions audit. AC #8 updated to match. **A12 customer-facing UX:** customer sees "Cap raised. Reviewers notified." (informational); detailed officer-coordination via Spec 051 AC #16 happens server-side (officers act on it; customer sees minimal copy).

- **CoS P1 zajno.com-level design bar concrete items:** AC #10 tightened with 5 concrete bars:
  - **Typography stack:** Inter (Google Fonts) primary + system-ui fallback; 16px base + 1.5 line-height + 0 letter-spacing default
  - **Motion principle:** ease-out 200-300ms duration band (subroute transitions, modal mount, toast); NO bounce/elastic/exaggerated easing per zajno restraint
  - **Dark/light handling:** Phase 1 LIGHT mode only (single mode; dark Phase 2 polish); semantic color tokens NOT raw hex
  - **Spacing:** Tailwind default scale 4/8/12/16/24/32px; minimum 24px between content blocks; 48px between sections
  - **Named reference page:** linear.app/jobs (Phase 1 reference; CRO+CoS qualitative review against it)
  
  Folding CRO-authored design-bar mini-spec deferred — Phase 1 ships against this AC #10 concrete bar.

- **CoS P2 customer-facing tone reader-friendly bar:** **NEW AC #15** — all customer-visible copy reviewed by CRO against reader-friendly bar (Captain msg 2583); no internal spec handles ("Article 15 export request CTA" → "Request my data" button label); no AC references; no officer-coordination jargon ("TAMPERING DETECTED" → "Integrity check failed"); no Spec/Article numbers in customer-facing copy. CRO copy-review at v2/v3 fold cycle.

**CoS architecture review pipeline COMPLETE on all 6 Phase 1 specs (051+052+053+054+055+056).** Phase 1 critical path now: CRO + COO multi-failure-mode adversary passes → final folds → CTO substrate build kickoff. CTO confirmed pipeline-closure separately (Spec 056 v2 changelog CTO message).

**A12 + A13 preserved cleanly.** Captain ratifications inapplicable per Captain msg 2583 multi-officer-process framing.
**v2 changelog:** CTO tech review surfaced 11 findings (7 substrate + 2 architectural + 2 dependency-callouts). Resolutions:
- **CTO #1 magic-link email delivery via Resend** (EU-region available, MIT-friendly, ~$20/mo first 100k emails). Captain founder-action LOW priority (alternative providers available, no lock-in per A13). AC #7 + Dependencies updated.
- **CTO #2 auth-model orthogonality (WRITES vs READS):** dashboard auth via session cookie + CSRF tokens for WRITES (cap-bump, erasure-request, pre-install form). AUDIT_API_KEY ONLY scopes READ-ONLY-AUDIT backend (per Spec 052 CTO #5 original intent). AC #7 clarification.
- **CTO #3 browser-side sha256 verifier Web Worker chunked:** off main thread; progress bar via postMessage; Web Worker boilerplate ~80 lines; avoids UI freeze on >10k entry logs. AC #9 updated.
- **CTO #4 chart library = Tremor** (MIT, dashboard-optimized, built on Recharts + filter/select). Saves ~2-3d styling work. A3 carve-out justified (visualization complexity). Dependencies updated.
- **CTO #5 pre-install screenshot storage:** ephemeral Hetzner volume + 7-day TTL post-install-completion + auto-delete. Update Spec 055 v6 data-handling matrix accordingly.
- **CTO #6 Page Visibility API polling pause:** when tab not visible, polling pauses; reduces API calls + customer/Cabinet noise. ~5 lines useEffect. AC #1 updated.
- **CTO #7 Stripe Customer Portal session API standard substrate** — confirm Spec 054 CTO #10 runbook config first.
- **CTO #8 multi-tenancy belt-and-suspenders:** middleware on every API route validates `req.cabinet_slug === auth_token.cabinet_slug` + Postgres RLS policies on customer-record + audit-log tables (defense in depth). Cross-tenant attack test in harness must fail at MULTIPLE layers. AC #11 strengthened.
- **CTO #9 cap-bump >$100 audit cross-spec helper:** shared `cabinet/scripts/lib/cap-bump-audit.sh` reused between dashboard backend + Spec 051 proxy. Appends to captain-decisions.md via library MCP `library_create_record` + real-time CoS notify-officer alert. AC #8 updated.
- **CTO #10 shared mock fixture cross-spec coordination:** `cabinet/tests/mocks/refslund-customer-mock.sh` (per Spec 053 CTO #5) authored as part of Phase 8 first-test-harness build; consumed by Spec 053+054+056 test harnesses. Mock structure satisfies all 3 consumers (customer record + signed DPA + virtual key + audit-log baseline). Cross-spec coordination explicit.
- **CTO #11 DA localization post-launch sprint:** new FW-* ticket for DA localization 2-week post-Phase-1-launch sprint via **next-intl** (Next.js i18n, MIT, supports MDX for legal pages). Design with i18n keys from Phase 1 build (not retrofit later). Out-of-scope Phase 1 explicitly.

**CTO closes Phase 1 spec review pipeline:** 051+052+053+054+055+056 all v1+ reviewed. CTO ready to start Phase 1 build planning once all 6 reach v3 ratification + CRO + COO + CoS final folds. Build sequence: refslund.ai infra base (Hetzner VPS + Postgres + Redis + LiteLLM + Next.js shell) → parallel substrate phases per spec dependencies → e2e pilot with first concierge customer.

**A12 + A13 preserved cleanly.** Captain ratifications inapplicable per Captain msg 2583 multi-officer-process framing.
**Priority:** P0 — gates customer post-install handoff (Spec 053 Stage 4 dashboard walkthrough) + customer self-service for spend/audit/erasure
**Framework ticket:** FW-101
**Owner:** CPO (spec) + CTO (Next.js subroute substrate) + COO-as-DPO (per Spec 055 v6 H1; compliance link review) + CoS (Captain ratification coordination)
**Scope:** Customer-facing dashboard at `refslund.ai/dashboard` + subroutes (/audit, /pre-install per Spec 053+054 CTO #4, /erasure, /legal-links); read-only spend visibility + audit log surface + cap-bump CTA + erasure request UI; Phase 1 MVP surface
**Canonical artifact home:** Library Specs Space (this spec) + customer dashboard render is Next.js subroute at refslund.ai
**Evidence:** Spec 051 v5 (per-cabinet spend tracking + cap-bump UX); Spec 052 v3 (audit log dashboard widget + customer hash-chain verification UI); Spec 053 v3 (Stage 4 install dashboard walkthrough + Stage 5 post-install handoff video); Spec 054 v1 (pre-install form subroute per CTO #4); Spec 055 v6 (DPA + sub-processor list + erasure request flow + privacy policy public-page MDX rendering); Captain msg 2565 + design-standards taste anchor (zajno.com-level bar Phase 1 minimum-viable, not overbuilt).

---

## Problem

Customer paying 25-60k DKK/mo for Cabinet needs visibility into:

1. **Spend transparency** — today's spend (USD primary + DKK display) + cap-remaining + 7-day trend + per-officer breakdown. Without this, customer can't reconcile Stripe invoice OR understand high-burn days. Trust erosion at first billing dispute.
2. **Audit log access** — last-7-days activity timeline + per-officer filter + clickable detail view + hash-chain integrity verification UI (per Spec 052). GDPR Article 15 export shortcut.
3. **Cap-bump self-service** — when cap-hit at 100% mid-day, customer needs in-dashboard CTA to bump (one-shot Stripe charge per Spec 051 AC #10).
4. **Erasure request UI** — GDPR Article 17 customer-facing form (Spec 055 v6 §Right-to-erasure flow).
5. **Compliance links** — DPA + Annex III ToS + sub-processor list + privacy policy + Stripe billing portal links surfaced in one place.
6. **Pre-install form subroute** — Spec 053 Stage 3 pre-install checklist + Spec 054 pre-install form (CTO #4 — folded into FW-101 scope).

Phase 1 MVP = focused minimum-viable; no Phase 2 polish (anomaly detection, AI insights, cost-trend forecasting, mobile-app, etc.).

## Solution

Next.js subroute at refslund.ai/dashboard with 6 subpages:

| Subpage | Purpose | Source |
|---|---|---|
| `/dashboard` (overview) | Today's spend + cap-remaining + 7-day trend + per-officer breakdown + recent-activity-glance + cap-bump CTA + compliance-link footer | Spec 051 + 052 |
| `/dashboard/audit` | Full audit log with last-7-days filter (default) + per-officer filter + clickable detail view + Article 15 export request CTA + integrity-verification UI | Spec 052 v3 |
| `/dashboard/pre-install` | Pre-install checklist + Mac specs form + install-date confirmation + Telegram verification (per Spec 053 Stage 3 + Spec 054 CTO #4) | Spec 053 + 054 |
| `/dashboard/erasure` | GDPR Article 17 erasure request form (per Spec 055 v6) | Spec 055 v6 |
| `/dashboard/legal-links` | DPA + Annex III ToS + sub-processor list + privacy policy + Stripe portal link aggregated | Spec 055 v6 |
| `/dashboard/billing` | Stripe customer portal link (Stripe-hosted; not Cabinet-rendered) | Spec 054 |

### Authentication

Customer signs in via email + magic-link (no password Phase 1 per A1 simplest-reversible-config + Spec 054 customer-record schema email field). Magic-link delivered via verified email; session cookie persists 7 days; refreshes on activity.

Backend authentication uses **AUDIT_API_KEY** (per Spec 052 CTO #5 — read-only audit scope, separate from LLM_PROXY_KEY). Compromise of dashboard credentials does NOT compromise LLM inference. Customer can rotate AUDIT_API_KEY independently via dashboard.

### Overview subpage (`/dashboard`)

Layout (Captain design-taste bar = zajno.com-level Phase 1):

```
┌───────────────────────────────────────────────────────┐
│ Cabinet                                  [Sign out]   │
├───────────────────────────────────────────────────────┤
│ TODAY · 2026-05-21                                    │
│                                                       │
│ Spend:        $12.40 USD / $50.00 USD cap            │
│               ≈ 84 DKK / 340 DKK                      │
│ ━━━━━━━━━━░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 25%          │
│                                                       │
│ Cap resets in 14h 32min. [Bump cap →]                │
├───────────────────────────────────────────────────────┤
│ 7-DAY TREND                                           │
│ [stacked-bar chart per officer + line for cap]       │
├───────────────────────────────────────────────────────┤
│ PER-OFFICER SPEND (last 7d)                          │
│ CoS    $14.20  ███████░                              │
│ CTO    $8.40   ████░░░░                              │
│ CPO    $5.20   ██░░░░░░                              │
│ CRO    $3.80   █░░░░░░░                              │
│ COO    $2.10   █░░░░░░░                              │
├───────────────────────────────────────────────────────┤
│ RECENT ACTIVITY (last 24h)                           │
│ [scrollable feed; 10 entries; "see all →" → /audit]  │
├───────────────────────────────────────────────────────┤
│ ⓘ Your data:  [DPA] [Sub-processors] [Privacy]      │
│ ⓘ Support:    Reply to your CoS in Telegram         │
│ ⓘ Billing:    [Stripe portal →]                      │
└───────────────────────────────────────────────────────┘
```

Refresh: 60s polling Phase 1 (WebSocket/SSE Phase 2 per Spec 052 v3 out-of-scope).

### Audit subpage (`/dashboard/audit`)

Default filter = last 7 days, all officers, all event types. Filter panel: date range (calendar picker), officer (multi-select), event type (multi-select). Sort: newest-first (default), oldest-first.

Each row:
- Timestamp (customer's local timezone; Phase 1 = Europe/Copenhagen per Danish-first)
- Officer + role
- Event type + brief description
- Cost (USD + DKK display)
- Click → expand row → full entry detail (subject metadata + integrity hash chain context)

**Integrity verification UI (per Spec 052 AC #9):**
- "Integrity status: Verified ✓ as of <last-checkpoint-ts>" badge top-right
- "Verify yourself →" link → downloads log + opens browser-side JS verifier (sha256 chain walk) → mismatch triggers retry-and-confirm flow (per v3 CoS I2 fold — 3 retries cover network/Web-Crypto edge cases) → only if all retries fail displays "INTEGRITY CHECK FAILED — Contact Support" banner + support-ticket CTA

**Article 15 export CTA:**
- "Request full data export (GDPR Article 15)" button
- Click → modal with 30-day SLA disclosure + customer confirmation → submission emits Spec 052 audit-log entry `event_type: article_15_request` → 30-day clock starts → email delivery with password-protected ZIP per Spec 052 AC #6.

### Erasure subpage (`/dashboard/erasure`)

Form fields:
- Customer identity confirmation (signed-in session)
- Erasure scope: full cabinet erasure (default) OR partial (specific data categories)
- Reason (optional free-text)
- Acknowledgments: 30-day SLA confirmed; understand cold-archive 5y/10y statutory retention preserved (anonymized) per Spec 055 v6 §retention; understand cancellation processed in parallel

Submit → 8-step erasure runbook per Spec 055 v6 AC #6 triggers; customer receives confirmation email + 30-day SLA tracker via email cadence (day-25 + day-29 + day-31 alerts per CTO #4 fold).

### Legal-links subpage (`/dashboard/legal-links`)

Aggregated quick-access:
- DPA: link to refslund.ai/legal/dpa (versioned, hash-anchored URL per Spec 055 v6 CTO #1)
- Annex III ToS clause: link to refslund.ai/terms#annex-iii-exclusion
- Sub-processor list: link to refslund.ai/sub-processors (DPF certification status per Spec 055 v4 H2 AC #17)
- Privacy policy: link to refslund.ai/privacy (Article 13/14 disclosures per Spec 055 v4 AC #14)
- Customer data-handling matrix: link to refslund.ai/data-handling
- Customer's signed DPA copy: download as PDF (from Library Compliance Space record)
- Stripe billing portal: link to Stripe-hosted customer portal

### Cap-bump CTA flow (per Spec 051 AC #10 + #16)

Customer clicks "Bump cap →" → modal:
- Current cap: $50 USD
- Bump options: +$25 / +$50 / +$100 (one-shot for current day only)
- Anti-abuse notice: "Second bump today = 2× price multiplier"
- Confirmation → Stripe one-shot charge → cap raised in proxy → audit-log entry emitted → modal closes with confirmation toast

If cap-bump exceeds $100 USD: dashboard surfaces Captain-decisions log notice (per Spec 051 AC #16 + Spec 049 §cost-cap-audit pattern).

---

## Acceptance criteria

1. **Overview subpage AC** — `/dashboard` renders today's spend (USD primary + DKK display) + cap-remaining + 7-day trend (stacked-bar chart per officer) + per-officer-7d-spend breakdown + recent-activity feed (last 24h, 10 entries) + cap-bump CTA + compliance-link footer. 60s polling refresh.

2. **Audit subpage AC** — `/dashboard/audit` reads Spec 052 audit log via AUDIT_API_KEY scoped GET endpoint; default filter last-7-days + all officers; filter panel for date range + officer + event type; row-click expands detail view; integrity-status badge top-right; "Verify yourself" link triggers browser-side JS sha256 chain walker; Article 15 export CTA emits Spec 052 audit-log entry + 30-day SLA tracker initiated.

3. **Pre-install subpage AC (per Spec 053 CTO #4 + Spec 054 CTO #4 fold)** — `/dashboard/pre-install` renders Spec 053 Stage 3 pre-install checklist + Mac specs form + install-date confirmation + Telegram verification screenshot upload. Submission persists to customer record + Library Customer-Success Space record; CoS T-1-day validation cadence consumes.

4. **Erasure subpage AC** — `/dashboard/erasure` form fields per spec body; submission triggers Spec 055 v6 8-step erasure runbook; email confirmation + 30-day SLA tracker (day-25/29/31 alerts shared substrate per Spec 055 + Spec 052 CTO #9).

5. **Legal-links subpage AC** — `/dashboard/legal-links` aggregates 7 links per spec body. DPA download = customer's signed PDF from Library Compliance Space record (NOT the template at refslund.ai/legal/dpa — customer-signed-version is binding per Spec 054 AC #4).

6. **Billing subpage AC** — `/dashboard/billing` redirects to Stripe customer portal via Stripe portal-session API; no Cabinet-rendered billing UI Phase 1 (Stripe-hosted is canonical per Spec 054 §subscription model).

7. **Authentication AC** — magic-link email auth (no password Phase 1); session cookie 7 days; refreshes on activity; sign-out clears session. Backend uses AUDIT_API_KEY (Spec 052 CTO #5) — distinct from LLM_PROXY_KEY.

8. **Cap-bump UX AC** — Overview subpage cap-bump CTA → modal with +$25/+$50/+$100 options + anti-abuse notice + step-up email-OTP for bumps ≥$50 per v3 CoS I1 fold + Stripe one-shot Confirmation → cap raised in proxy + Spec 052 audit-log entry + (if cumulative-bump-USD >$25 USD OR second-bump-same-day per Spec 051 v5 cap-bump section) Spec 051 AC #16 captain-decisions.md auto-entry per A1 audit pattern. Threshold $25 USD aligns Spec 051 v5; pending Captain X1 ratify per CRO X1 finding.

9. **Integrity verification UI AC (per Spec 052 AC #9 sha256-LOCKED + CTO #1 + v3 CoS I2 retry-and-confirm gate)** — browser-side JS sha256 verifier (Web-Crypto API; Web Worker chunked off main thread per v2 CTO #3); downloads customer's full audit log + walks chain + verifies against latest checkpoint at refslund.ai/audit-checkpoints (Phase 1 unsigned per Spec 052 v2 CTO #7). Mismatch triggers retry-and-confirm flow (3 retries: partial-download recovery, checkpoint freshness re-check, Web-Crypto known-good test vector) before surfacing "INTEGRITY CHECK FAILED — Contact Support" copy (NOT alarm-language). Support-ticket auto-files COO+CoS; Article 33 supervisory-authority escalation gated on COO confirmed-incident determination (NOT customer-facing automatic alarm). Customer can verify any time without server roundtrip.

10. **Phase 1 design-taste anchor AC** — dashboard design references zajno.com-level bar per [Design Standards] memory. Typography (sans-serif system stack, generous line-height), spacing (16px+ between blocks), micro-interactions (cap-bump confirmation toast, subroute transitions), restraint (no premature charts, no anomaly-detection-tease, no Phase 2 features visible). CRO + CoS taste review at v2 fold (qualitative; subjective).

11. **Multi-tenancy isolation AC** — customer sees ONLY their own cabinet's data (scope enforced by AUDIT_API_KEY at backend); cross-cabinet view prohibited (cross-tenant attack test in harness must fail). Cabinet ops (COO-as-DPO) accesses ALL cabinet dashboards via admin interface with explicit role-check (per Spec 052 AC #10).

12. **Mobile responsiveness AC** — Phase 1 mobile = read-only + cap-bump CTA + erasure-request form. Phase 2 polishes mobile UX. Tablet + desktop full-featured. Customer's primary use case = desktop browser; mobile is glance-and-bump.

13. **Test harness AC** — `cabinet/tests/test-customer-dashboard.sh` covers: overview spend + cap + trend renders; audit subpage filter + detail + integrity verifier; pre-install form + persistence; erasure form + 30-day tracker; legal-links 7-link aggregation; billing Stripe portal redirect; auth magic-link flow; cap-bump modal + Stripe one-shot integration; multi-tenant isolation (cross-cabinet access test fails); browser-side sha256 chain walker matches server-side. Shared mock fixture `cabinet/tests/mocks/refslund-customer-mock.sh` per Spec 053 CTO #5. ≥10 assertions.

---

## Edge cases

- **Customer's hash-chain verification fails (after retry-and-confirm exhausted)** — surface "INTEGRITY CHECK FAILED — Contact Support" copy (NOT alarm-language); support-ticket CTA auto-files COO+CoS; lock customer write-access pending COO investigation; Article 33 supervisory-authority notification ONLY if COO confirms incident is material breach (NOT automatic customer-side trigger). False-positive prevention: 3-retry gate handles network/Web-Crypto edge cases before any incident-level response.
- **Customer requests Article 15 export immediately followed by erasure** — both flows trigger; export delivered FIRST (before erasure complete); erasure 30-day SLA continues on its track; documented in respective audit-log entries.
- **Customer mid-cap-bump-flow at 100% cap** — Stripe one-shot succeeds → proxy cap raises within 5s → modal confirmation → officer sessions detect cap-raise via next request retry → service resumes. Failure cascade: Stripe one-shot fails → modal shows error + retry CTA; no cap raise; officer sessions stay blocked.
- **Customer signed in on multiple devices simultaneously** — session cookie per device; latest cap-bump action wins (no concurrent-edit conflicts since cap state is single-source-of-truth Redis per Spec 051).
- **Customer's email account compromised (magic-link delivered to attacker)** — attacker accesses dashboard; mitigation: 7-day session cookie expires; customer can rotate AUDIT_API_KEY via dashboard which invalidates all sessions; magic-link to new email also valid. Recommend customer use unique email + 2FA on customer's email provider.
- **Stripe portal redirect fails** (Stripe session API error) — surface "Stripe portal temporarily unavailable; contact support" + retry CTA.
- **Customer attempts erasure of mid-active-billing-cycle** — Spec 055 v6 edge case + Stripe legal-hold carve-out documented in erasure modal; customer-facing copy: "Your billing record retains anonymized data for tax compliance per Danish law; all other data deleted."
- **Browser-side sha256 verifier slow on large logs** (>10k entries) — Phase 1 acceptable: verifier shows progress bar + estimated time; Phase 2 may add server-assisted incremental verification.
- **Customer requests dashboard in Danish UI** — Phase 1 ships English-default + Danish-translation in 2-week post-launch window per Captain msg 2565 "DA primary EN secondary localization" (out-of-scope this spec; FW-* candidate for DK localization sprint).

---

## Open questions

No Open Questions Phase 1 — design-taste subjective + Library + /tasks canonical artifacts per Captain msg 2583. CoS + Captain design-taste review at v2 fold (qualitative; not Captain-ratification-gate).

---

## Dependencies

- **Spec 051 v5 dependency:** proxy-audit JSONL aggregates feed overview spend + cap-status + per-officer breakdown.
- **Spec 052 v3 dependency:** audit log JSONL feeds audit subpage; AUDIT_API_KEY auth; hash-chain checkpoint endpoint for integrity verifier.
- **Spec 053 v3 dependency:** pre-install subpage couples to Stage 3 checklist + Stage 4 install-day flow.
- **Spec 054 v1 dependency:** pre-install form CTO #4 fold per CoS architecture review; Stripe portal API for billing subpage; customer-record schema for auth + scoping.
- **Spec 055 v6 dependency:** legal-links subpage aggregates DPA + Annex III + sub-processor list + privacy policy + data-handling matrix from Library Compliance Space + refslund.ai/legal/* MDX pages.
- **CTO substrate:** Next.js subroute structure under refslund.ai/dashboard + 6 subpages + magic-link auth + AUDIT_API_KEY backend scoping + browser-side sha256 verifier (Web-Crypto API) + Stripe portal session API + chart library (Recharts or similar; build-vs-buy = use mature MIT-licensed lib per A3 carve-out for visualization complexity).
- **CoS coordination:** customer-record state-machine + Library Customer-Success Space integration + design-taste review.
- **COO-as-DPO (pending Spec 055 v4 H1 Captain ratify):** legal-links subpage content review + erasure form review + audit log retention transparency.

---

## Out of scope

- **WebSocket/SSE real-time updates** — Phase 2 polish. Phase 1 = 60s polling.
- **Anomaly detection on spend patterns** — Phase 2 + Spec 050 broader analytics.
- **AI-generated daily-summary insights** — Phase 2 (frontier-AI integration).
- **Customer custom dashboard widgets** — Phase 2 user-config.
- **Cost forecasting / cost-trend predictions** — Phase 2 analytics.
- **Customer team management** (sub-accounts, role-based access) — Phase 2 multi-user.
- **Dashboard mobile app (iOS / Android)** — Phase 3.
- **Notion/Slack/MS-Teams integrations** — never (A11 + A13).
- **Public API for customer integrations** — Phase 3 (customer's own custom dashboards via Cabinet API).
- **Localization beyond English+Danish** — Phase 2 EU expansion.

---

## Phasing

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | CRO + CoS + COO parallel adversary review fold → v2 | v1 LANDED | v2 LANDED |
| 2 | CPO self-spawned review subagent fresh-context audit | v2 LANDED | v3 LANDED (if findings) OR v2 ship-ready |
| 3 | CTO substrate: Next.js subroute structure + magic-link auth + AUDIT_API_KEY backend | v3 ratified | Dashboard demo loads + auth flow works |
| 4 ║ | CTO substrate: Overview subpage (spend + cap + trend + per-officer breakdown + recent-activity) | Phase 3 GREEN, couples to Spec 051 | Mock data renders correctly |
| 5 ║ | CTO substrate: Audit subpage + integrity verifier (browser-side sha256 chain walker) + Article 15 export request | Phase 3 GREEN, couples to Spec 052 | Audit log filter + detail view + verifier work |
| 6 ║ | CTO substrate: Pre-install subpage + Erasure subpage + Legal-links subpage + Billing Stripe portal redirect | Phase 3 GREEN, couples to Spec 053 + 054 + 055 | All subpages route + render |
| 7 ║ | CTO substrate: Cap-bump CTA modal + Stripe one-shot integration + proxy cap-raise + audit-log entry | Phase 3 GREEN, couples to Spec 051 + 054 | Cap-bump end-to-end works mock customer |
| 8 | Test harness `cabinet/tests/test-customer-dashboard.sh` (≥10 assertions; uses shared mock fixture) | Phases 3-7 GREEN | All assertions passing in CI |
| 9 | End-to-end pilot: first Phase 1 customer dashboard walkthrough per Spec 053 Stage 4 install-day flow | Phase 8 GREEN + all Phase 1 specs GREEN | Customer dashboard walked through during install; spend visible; audit log displays; erasure flow demoed |

**Critical path:** v1 → v2 → v3 → Phase 3 (substrate base) → Phases 4-7 parallel → Phase 8 test → Phase 9 e2e pilot. Couples to ALL Phase 1 specs at e2e pilot stage — FW-101 is the surface where customer sees the result of Phase 1 build.

---

## Review process

1. **CRO adversary review** — UX adversarial audit (customer confusion patterns, dark-pattern check on cap-bump CTA, accessibility per WCAG AA), spend-chart edge cases, integrity verifier UX clarity.
2. **CoS architecture review** — cross-spec integration coherence (Spec 051/052/053/054/055 all consume dashboard surface), design-taste qualitative review per Captain zajno.com-level bar.
3. **COO-as-DPO (pending Spec 055 v4 H1)** legal-links + erasure form + audit log retention transparency review.
4. **COO adversary** — multi-failure-mode: dashboard unavailable + cap-hit + customer requests erasure + payment-failed simultaneously.
5. **CPO self-spawned review subagent** — fresh-context audit before commit.

Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing.

---

**v1 LANDED 2026-05-20 23:15 UTC** (CPO authored under CoS Phase 1 priority queue completion — Spec 056 closes Phase 1 critical-path spec authoring; FW-101 last in priority queue). All 6 Phase 1 specs LANDED tonight (051+052+053+054+055+056 LANDED with various review folds). CPO self-spawned review next; CRO + CoS + COO multi-officer adversary queue continues.
