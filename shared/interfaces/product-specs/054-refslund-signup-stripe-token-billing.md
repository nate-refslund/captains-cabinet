# Spec 054: refslund.ai Signup + Stripe Token Billing (FW-099 Phase 1 Priority 5)

**Version:** v2 (CTO tech review + CoS architecture review parallel fold) — v1 superseded
**v2 changelog:** CTO (11 findings: 8 substrate + 2 architectural + 1 founder-action) + CoS (7 findings: 3 BLOCKER + 3 IMPROVEMENT + 1 POLISH) reviews folded in single pass. Resolutions:

CTO substrate fold:
- **CTO #1 customer-record state machine:** Postgres ENUM TYPE + BEFORE UPDATE transition-validator trigger. Allowed transitions: `pending_install → active → cancelling → erased`. ~30 lines DDL. AC #9 updated.
- **CTO #2 + CoS F3 BLOCKER Stripe webhook idempotency (overlap):** dedupe via `stripe_events_processed` table keyed on `event.id` (7-day TTL via Redis) + handler returns 200 on already-processed events. Substrate ~20 lines. AC #12 + #8 updated.
- **CTO #3 webhook signature secret rotation:** Captain founder-action — choose secrets-management approach (Hetzner-managed secrets store OR HashiCorp Vault). Rotation annual + on personnel-change. Runbook at `cabinet/runbooks/stripe-webhook-secret-rotation.md`.
- **CTO #4 cron schedule collision:** Spec 054 Stripe meter daily cron shifts to **00:10 UTC** (was 00:05); Spec 052 hash-chain checkpoint stays 00:05 UTC. AC #3 updated.
- **CTO #5 pgcrypto encryption scope:** `dpa_document_hash` is sha256 (one-way function output); encryption provides zero benefit. v2 drops encryption on dpa_document_hash; encrypted-at-rest scope = `llm_proxy_key + audit_api_key` only. AC #9 schema updated.
- **CTO #6 eIDAS clickwrap React component reuse:** single `<EIDASClickwrap document_url document_hash />` reused 3× (DPA + Annex III + sub-processor list). POST `/api/clickwrap/record` → receipt-id → customer record + Library Compliance Space. AC #4 updated.
- **CTO #7 mid-wizard abandonment client-side state:** Phase 1 = browser localStorage (cleared on Stripe Checkout success OR explicit "start over"); no server-side ephemeral session storage. AC #1 updated.
- **CTO #8 customer-record migration discipline:** `cabinet/migrations/refslund/*.sql` numbered + idempotent + `_migrations_applied` tracking table. New AC #14.
- **CTO #9 cap-bump cross-spec ownership:** Redis counter `cabinet:capbump:<slug>:<date>` owned by Spec 051 schema; Spec 054 reads+increments via shared lib `cabinet/scripts/lib/cap-bump.sh` (Lua INCR-with-multiplier-lookup, race-safe). AC #10 + cross-spec dependency callout updated.
- **CTO #10 Stripe Customer Portal config:** allowed actions whitelist = `[update_payment_method, view_invoices, cancel_subscription]`; deny `update_subscription_quantity` (officer count change via Captain personal contact per Spec 053). Runbook `shared/interfaces/runbooks/stripe-customer-portal-config.md`. New AC #15.
- **CTO #11 FOUNDER ACTION DK VAT registration:** Stripe Tax requires Cabinet (refslund.ai) VAT-registered in customer jurisdictions. Phase 1 DK-only → DK VAT registration required. **Captain founder-action ticket needed BEFORE Phase 1 customer signup goes live** — CoS surfaces in 07:00 morning briefing. New AC #16.

CoS architecture fold:
- **CoS F1 BLOCKER cancellation-erasure cascade gap:** `customer.subscription.deleted` webhook + 7-day grace expiry → erasure-cascade job zeroizes PII columns (email/captain_name/mac_specs/stripe_customer_id), retains audit-anchored fields (cabinet_slug + hashed signing artifacts per Spec 055 v6 erasure runbook), transitions cancelling→erased, emits Spec 052 audit-log entry. New AC #17. Cross-spec coordination with Spec 055 v6 §Article 17 erasure runbook.
- **CoS F2 BLOCKER scope contradiction:** AC #7 + heading renamed "DK-only billing-address validation Phase 1" (was "EU-only"). Phase 2 Nordic/EU widening explicitly in Out-of-scope (not Phase 1 AC).
- **CoS F4 mac_specs race resolution:** create new `customer_install_profile` table owned by FW-101 (Spec 056); mac_specs / install_date / network move there. customers table stays billing-pure. Schema updated; cross-spec dependency on Spec 056 explicit.
- **CoS F5 customer.tax_id webhook drop:** Stripe Tax auto-handles 25% Danish B2C VAT; B2B reverse-charge rare Phase 1. Drop from webhook set (8→7 events). Phase 2 may re-add for multi-currency.
- **CoS F6 wizard copy USD-line clarity:** AC #2 updated — wizard copy clarifies USD line shows underlying Anthropic-cost transparency (NOT price customer pays); customer pays DKK subscription which bundles cap-budget. Avoids dual-currency confusion.
- **CoS F7 POLISH Captain-time-budget leaks:** AC #12 payment-failed Captain-personal intervention + refund handling → rate-bounded ≤1/wk per Spec 053 v3 AC #13; CoS-queue throttle reference added. Phase 2 routes to COO at scale.

**A12 + A13 preserved cleanly both reviews.** Captain ratifications inapplicable per multi-officer-process-as-legal-review framing EXCEPT new CTO #11 FOUNDER ACTION (DK VAT registration) which CoS surfaces in 07:00 morning briefing alongside Spec 055 v4 H1+H3+H4.
**Priority:** P0 — gates customer signup live; wires DPA + Annex III attestation + sub-processor list ratification + Stripe billing per Captain msg 2565 pricing
**Framework ticket:** FW-099
**Owner:** CPO (spec) + CTO (substrate + Stripe wiring) + COO-as-DPO (RATIFIED Captain msg 2737; compliance integration) + CoS (Captain ratification pipeline)
**Scope:** refslund.ai signup wizard + Stripe Checkout + Stripe Token Billing meter + DPA clickwrap + Annex III attestation + sub-processor list ratification + Stripe webhook receivers (signup completion, cap-bump, subscription state changes) + customer-record schema
**Canonical artifact home:** Library Specs Space (this spec) + Library Compliance Space (signed customer DPAs + Annex III attestations)
**Evidence:** Captain msg 2565 (pricing 25k DKK base + 5k DKK/employee, max 7 employees, $50/day USD cap, Danish-first Phase 1); Spec 051 v5 (virtual key issuance at signup completion); Spec 052 v3 (AUDIT_API_KEY issuance at signup; signup audit-log entry); Spec 053 v2 (Stripe webhook → welcome email + Captain note + install scheduling); Spec 055 v6 (DPA + Annex III + sub-processor list signed at signup; Library Compliance Space record-of-record).

---

## Problem

refslund.ai needs end-to-end customer signup flow that:

1. **Captures customer intent + qualifying data** — discovery-call notes from Spec 053 Stage 1 inform pre-signup; signup wizard captures Mac specs, delivery date, cabinet name, officer roster choice, attestation toggles.
2. **Wires Stripe billing per Captain pricing** — 25,000 DKK base + 5,000 DKK per employee, max 7 employees → 25k-60k DKK/mo subscription range. Stripe Token Billing meter consumes FW-096 proxy-audit aggregates for per-cabinet-per-day spend tracking.
3. **Embeds compliance ratifications** — clickwrap DPA (per Spec 055 v6 + CTO #1) + Annex III attestation checkbox + sub-processor list ratification, all signed during Stripe checkout, persisted to Library Compliance Space as record-of-record.
4. **Triggers downstream flows** — Stripe webhook fires → virtual-key + AUDIT_API_KEY minted (Spec 051+052) → install scheduled (Spec 053 Stage 2) → audit-log entry emitted (Spec 052) → cap-bump one-shots wired (Spec 051 AC #10).
5. **Handles failure modes** — payment fails, customer changes mind mid-signup, sub-processor list updates mid-cycle, DK-only billing-address validation rejects non-DK (Phase 1 Danish-first per Captain msg 2565).

## Solution

Signup wizard at `refslund.ai/signup` integrates Stripe Checkout + Stripe Token Billing + clickwrap compliance + customer-record schema. Wizard is 4-step:

1. **Cabinet config** — slug + officer roster choices + employee count + Mac specs + delivery preferences
2. **Compliance review** — DPA + Annex III + sub-processor list with clickwrap (NOT externally-managed e-sign; eIDAS-compliant clickwrap per Spec 055 v6 CTO #1)
3. **Stripe Checkout** — Stripe-hosted checkout with subscription pricing (25k + 5k × employees) + payment method
4. **Confirmation + next steps** — signup confirmed, install date scheduled, welcome email + Captain note triggered (Spec 053 Stage 2), dashboard link delivered

### Stripe Token Billing model

Per Captain msg 2565: ONE pricing tier, 25k DKK base + 5k DKK/employee, max 7 employees per cabinet (25k-60k DKK/mo range), $50/day USD per-cabinet cap TOTAL (Anthropic raw cost; customer pays subscription which bundles cap-budget).

**Subscription structure:**
- **Base fee:** 25,000 DKK/mo subscription
- **Per-employee surcharge:** 5,000 DKK/mo × employee_count (capped 7 employees)
- **Token usage:** included in subscription up to $50 USD raw Anthropic cost/day (= ~$1500 USD/mo at full burn = ~10,400 DKK/mo at par DKK/USD). Subscription absorbs.
- **Cap-bumps:** customer-initiated one-shot via dashboard; charged as Stripe one-shot via additional invoice item; price per cap-bump = base USD increment × 2 (anti-abuse per Spec 051 CTO #11 + AC #16).
- **Currency:** subscription DKK-denominated (customer-facing); cap enforcement USD-denominated proxy-side (per Spec 051 v5 B1); per-billing-cycle FX rate-locked (per CTO #4) — variance absorbed into subscription bundle.

Stripe Token Billing meter integration (Stripe ships native token-billing primitives) consumes FW-096 proxy-audit JSONL aggregates daily → meter reports actual usage → next invoice cycle reconciles included quota vs overage (overage = $0 if within cap; $0 if customer pays subscription only).

### Customer-record schema

Stored in refslund.ai database (Postgres alongside LiteLLM proxy on Hetzner Frankfurt VPS per Spec 051 deployment topology):

```sql
CREATE TABLE customers (
  id UUID PRIMARY KEY,
  cabinet_slug VARCHAR(64) UNIQUE NOT NULL,
  email VARCHAR(255) NOT NULL,
  captain_name VARCHAR(128) NOT NULL,
  company_name VARCHAR(255),
  billing_country CHAR(2) NOT NULL,            -- 'DK' Phase 1
  employee_count SMALLINT NOT NULL CHECK (employee_count BETWEEN 1 AND 7),
  officer_roster TEXT[],                       -- e.g., {'cos','cto','cpo','cro','coo'}
  -- mac_specs + install_date moved to customer_install_profiles table per v2 CoS F4 fold
  -- (owned by Spec 056 / FW-101; customers table stays billing-pure)
  stripe_customer_id VARCHAR(255),
  stripe_subscription_id VARCHAR(255),
  stripe_meter_id VARCHAR(255),                -- Token Billing meter
  llm_proxy_key VARCHAR(255),                  -- encrypted at rest; from Spec 051
  audit_api_key VARCHAR(255),                  -- encrypted at rest; from Spec 052 CTO #5
  dpa_signed_at TIMESTAMPTZ NOT NULL,
  dpa_signed_ip INET NOT NULL,
  dpa_document_hash VARCHAR(64) NOT NULL,      -- SHA256 of DPA template version signed
  annex_iii_attested_at TIMESTAMPTZ NOT NULL,
  subprocessor_list_ratified_at TIMESTAMPTZ NOT NULL,
  subprocessor_list_version VARCHAR(16) NOT NULL,
  status VARCHAR(32) NOT NULL,                 -- 'pending_install' | 'active' | 'cancelling' | 'erased'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

Indexed on cabinet_slug + email + stripe_customer_id. Encrypted-at-rest fields use pgcrypto per Spec 055 v5 CTO #6.

### Stripe webhook receivers

| Webhook event | Action |
|---|---|
| `checkout.session.completed` | Customer signed up. Mint LLM_PROXY_KEY + AUDIT_API_KEY (per Spec 051 + 052). Set status=`pending_install`. Trigger Spec 053 Stage 2 welcome email + Captain note + install scheduling. Emit Spec 052 audit-log entry `event_type: signup` + `dpa_signed` + `annex_iii_attested` + `subprocessor_list_ratified`. |
| `customer.subscription.created` | Confirm subscription active; set status=`active` after install completes (FW-098 Stage 4 completion). |
| `customer.subscription.updated` | Subscription change (employee_count or cancellation). Update customer record. Emit Spec 052 audit-log entry. |
| `customer.subscription.deleted` | Customer cancelled. Trigger Spec 053 §Concierge offboarding (wind-down call + 7-day grace + Spec 055 erasure runbook). Set status=`cancelling`. |
| `invoice.paid` | Monthly invoice succeeded. Reset cap-bump anti-abuse counter (per Spec 051 CTO #11). |
| `invoice.payment_failed` | Payment failed. Trigger CoS notify-officer alert; customer dashboard surfaces banner; 7-day grace before service-pause; Captain personal intervention if grace expires. |
| ~~`customer.tax_id.created/updated`~~ | DROPPED Phase 1 per v2 CoS F5 fold (Stripe Tax auto-handles 25% Danish B2C VAT; B2B reverse-charge rare). Phase 2 may re-add for multi-currency. |
| Cap-bump one-shot custom event | Customer-initiated cap-bump → Stripe one-shot charge → cap raised for current day per Spec 051 AC #10. |

### Clickwrap compliance (per Spec 055 v6 CTO #1)

Wizard Step 2 surfaces three checkboxes (each clickwrap-individual; no "accept all" bundle):

1. **DPA acceptance** — "I acknowledge and accept the Data Processing Agreement as required by GDPR Article 28. [Read DPA]" → link to refslund.ai/legal/dpa (versioned, hash-anchored).
2. **Annex III attestation** — "I warrant and represent that I will NOT use Cabinet to perform any AI processing falling under EU AI Act Annex III high-risk categories. [Read full clause]" → link to refslund.ai/terms#annex-iii-exclusion.
3. **Sub-processor list ratification** — "I acknowledge the sub-processor list and accept Anthropic as the LLM sub-processor for Phase 1. [View sub-processor list]" → link to refslund.ai/sub-processors.

Each click captures: timestamp (UTC), IP address, document_hash (SHA256 of clicked-version), customer-record FK. Persisted to customer record AND Library Compliance Space (per Spec 055 v5 A11 dual-home pattern). eIDAS-compliant clickwrap evidence.

### Pre-install form (FW-101 dashboard subroute per Spec 053 CTO #4)

After signup, customer accesses refslund.ai/dashboard/pre-install (subroute of customer dashboard; couples to FW-101). Captures:
- Mac specs detail (model, RAM, disk free, macOS version)
- Network details (download speed, port-22 OR Tailscale)
- Install date confirmation OR reschedule
- Telegram account confirmation (DM screenshot or test message)
- Calendar block confirmed

CoS-validated T-1 day before install per Spec 053 Stage 3.

---

## Acceptance criteria

1. **Signup wizard 4-step flow AC** — refslund.ai/signup serves 4 steps (cabinet config → compliance review → Stripe Checkout → confirmation). Progress bar visible; back-button preserves state; mid-wizard abandonment doesn't create customer record (only Stripe Checkout completion creates record).

2. **Stripe pricing structure AC** — Stripe Checkout configured with base price 25,000 DKK + per-employee surcharge 5,000 DKK × employee_count. employee_count slider (1-7) updates total live. Total in DKK + USD-equivalent shown (informational only; customer charged DKK).

3. **Token Billing meter wiring AC** — Stripe Token Billing meter created per customer at signup; meter_id stored in customer record. Daily cron at 00:05 UTC reads FW-096 proxy-audit JSONL for prior-day cap-spend per cabinet → reports to Stripe meter. Monthly invoice reconciles meter against included quota; overage = $0 if within $50/day USD cap; cap-bump one-shots invoiced separately.

4. **DPA clickwrap AC (per Spec 055 v6 CTO #1)** — Step 2 captures DPA acceptance with timestamp + IP + document_hash; persisted to customer record + Library Compliance Space record. eIDAS-compliant. DPA document versioned at refslund.ai/legal/dpa with hash-anchored URL (e.g., `?v=2026-05-20-v1`); old versions archived; customer signs current version.

5. **Annex III attestation AC** — Step 2 surfaces 8-category exclusion checkbox per Spec 055 v6 Annex III ToS clause; customer warrants + represents + acknowledges. Timestamp + IP + document_hash logged. Phase 1 customer attestation gates signup completion.

6. **Sub-processor list ratification AC** — Step 2 ratifies Anthropic-only Phase 1 list per Captain msg 2583 Q5 + Spec 055 v6 §sub-processor list. OpenAI + Gemini NOT listed at signup (DISABLED per Spec 051 v5 + Spec 055 v6); future additions trigger Article 28(2) 30-day objection window per Spec 055 sub-processor change flow.

7. **DK-only billing-address validation AC Phase 1** (per v2 CoS F2 BLOCKER fold) — Stripe Checkout configured with billing country whitelist = `['DK']` Phase 1. Non-DK billing addresses rejected with "Phase 2 international expansion coming" message + email-capture for waitlist. Phase 2 widens to Nordic/EU per Captain msg 2565 phase-trigger (20 DK cabinets OR 1M DKK/mo MRR).

8. **Stripe webhook receivers AC** — refslund.ai serves `/api/stripe/webhook` endpoint receiving + verifying Stripe webhook signatures + processing 8 event types per table above. Webhook handler emits Spec 052 audit-log entries + triggers Spec 053 Stage 2 welcome flow + mints Spec 051 + 052 keys.

9. **Customer-record schema AC** — Postgres `customers` table per schema above; pgcrypto encryption for llm_proxy_key + audit_api_key + dpa_document_hash. Indexed on cabinet_slug + email + stripe_customer_id. Update timestamp on every change.

10. **Cap-bump one-shot Stripe integration AC (per Spec 051 CTO #11 + AC #16)** — customer dashboard "Bump cap" CTA → Stripe one-shot charge endpoint → Stripe webhook custom event → proxy cap-raise for current day → Spec 052 audit-log entry. Second same-day bump = 2× price multiplier per Spec 051 AC #16. Reset on `invoice.paid` (monthly cycle).

11. **Pre-install form AC (couples to FW-101 per CTO #4)** — refslund.ai/dashboard/pre-install subroute (FW-101 scope) captures Mac specs + network + install date + Telegram verification per Spec 053 Stage 3. CoS validates T-1 day before install via Library Customer-Success Space record.

12. **Failure-mode handling AC** — payment-failed → 7-day grace before service-pause; Stripe webhook retry handling via idempotent processing (customer-record state machine); mid-wizard abandonment cleans up (no customer record OR stripe-customer); sub-processor list mid-cycle update triggers Article 28(2) 30-day objection flow per Spec 055 v6.

13. **Test harness AC** — `cabinet/tests/test-refslund-signup-stripe.sh` covers: 4-step wizard end-to-end with mock customer (per Spec 053 CTO #5 shared mock fixture `cabinet/tests/mocks/refslund-customer-mock.sh`); pricing calculator 1-7 employees + total-DKK-USD display; DPA clickwrap captures all 3 fields; Annex III attestation gates completion; non-DK billing rejection; Stripe webhook all 8 event types; cap-bump one-shot price multiplier; customer-record schema validates per pgcrypto; failure modes (payment-failed + mid-wizard abandonment). ≥12 assertions.

---

## Edge cases

- **Customer signs up with wrong officer roster** — Phase 1 concierge allows post-signup roster change via Captain personal contact (Spec 053 discovery-call iteration). Phase 2 self-serve adds dashboard roster editor.
- **Customer changes employee_count mid-subscription** — Stripe subscription proration; subscription updated; customer record updated; emit Spec 052 audit-log entry. Within 7-day grace = pro-rata adjustment.
- **DPA template version changes between signup + install** — customer's signed version is the binding one; new version triggers Article 28(2) 30-day customer notification + objection window per Spec 055 v6.
- **Sub-processor list expands** (e.g., Phase 2 enables OpenAI/Gemini fallback) — Article 28(2) 30-day objection window per Spec 055 v6; existing customers notified; new customers see updated list at signup; mid-objection-window customers can object → refund.
- **Stripe webhook delivery fails** — Stripe retries automatically; refslund.ai endpoint idempotent (customer-record state machine prevents duplicate processing). If retries exhaust, COO alerted.
- **Customer's IP geolocation differs from billing country** — Stripe Checkout enforces billing-country-DK; IP geolocation NOT used as gate (privacy concern + VPN realities).
- **Subscription pricing changes mid-cycle** — customer keeps original pricing until renewal; Phase 2 may introduce price increases via Article 28(2)-equivalent 30-day notification.
- **Customer requests refund within 7-day satisfaction-guarantee window** (Spec 053 §Concierge offboarding) — Stripe full refund via customer portal OR Captain-personal handling; erasure flow per Spec 055 v6.
- **VAT calculation Denmark-resident** — Stripe Tax handles automatically; 25% Danish VAT on B2C subscriptions; customer-record stores tax_id if B2B reverse-charge applies.

---

## Open questions

No Open Questions Phase 1 — all decisions internal-officer process per Captain msg 2583 + Captain ratifications already covered by Spec 055 v4 H1+H3+H4 flow (07:00 briefing) + Captain msg 2565 pricing structure.

---

## Dependencies

- **FW-096 (Spec 051) dependency** — virtual key minting at `checkout.session.completed`; proxy-audit JSONL aggregate consumed by Stripe Token Billing meter.
- **FW-097 (Spec 052) dependency** — AUDIT_API_KEY minting at signup; signup audit-log entry emitted; Stripe webhook events emit log entries.
- **FW-098 (Spec 053) dependency** — Stripe webhook → Spec 053 Stage 2 welcome email + Captain note + install scheduling.
- **FW-100 (Spec 055 v6) dependency** — DPA template versioned + Annex III ToS clause + sub-processor list ratified at signup; Library Compliance Space record-of-record.
- **FW-101 (Spec 056 candidate) dependency** — customer dashboard surfaces signup-completion state + cap-bump CTA + pre-install form subroute.
- **CTO substrate:** refslund.ai signup wizard frontend (Next.js subroute); Stripe Checkout configuration; Stripe Token Billing meter setup; Stripe webhook receiver + signature verification; Postgres customers table + pgcrypto; eIDAS-clickwrap implementation.
- **CoS coordination:** customer-record state-machine review; failure-mode runbook; Library Compliance Space integration.
- **CRO sweep dependency:** quarterly Stripe ToS + Stripe Tax monitoring for Danish VAT changes; CRO 4h sweep cadence covers.

---

## Out of scope

- **Multi-currency subscription support** — Phase 1 DKK only. Phase 2 USD + EUR per regional expansion.
- **Annual subscription discount** — Phase 1 monthly only. Phase 2 may offer annual.
- **Self-serve cancellation via dashboard** — Phase 1 customer contacts Captain personally per Spec 053 §Concierge offboarding wind-down call. Phase 2 self-serve.
- **Referral program** — Phase 2.
- **Custom enterprise pricing** — Phase 1 ONE tier. Phase 3 may add custom enterprise.
- **Marketplace integration (Apple App Store, etc.)** — never; Cabinet ships direct only.
- **Stripe Atlas integration for customer business-entity setup** — not Cabinet's scope; customer's own responsibility.

---

## Phasing

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | CRO + CoS + COO parallel adversary review fold → v2 | v1 LANDED | v2 LANDED |
| 2 | CPO self-spawned review subagent fresh-context audit | v2 LANDED | v3 LANDED (if findings) OR v2 ship-ready |
| 3 | CTO substrate: refslund.ai signup wizard frontend (Next.js); Stripe Checkout configuration; Stripe Tax setup | v3 ratified | Signup wizard demo loads + Stripe Checkout completes |
| 4 ║ | CTO substrate: Stripe webhook receiver + signature verification + idempotent processing | Phase 3 GREEN | Mock webhook events processed end-to-end |
| 5 ║ | CTO substrate: Postgres customers table + pgcrypto + customer-record state machine | Phase 3 GREEN | Schema migration applied; CRUD tested |
| 6 ║ | CTO substrate: Stripe Token Billing meter integration + daily aggregation cron | Phase 3 GREEN, couples to FW-096 + FW-097 | Meter reports to Stripe; invoice reconciliation works |
| 7 ║ | CTO substrate: eIDAS-clickwrap component for DPA + Annex III + sub-processor list | Phase 3 GREEN, couples to FW-100 | Clickwrap captures all 3 fields; persists to Library |
| 8 | Test harness `cabinet/tests/test-refslund-signup-stripe.sh` (≥12 assertions) | Phases 3-7 GREEN | All assertions passing in CI |
| 9 | End-to-end pilot: mock customer signup → Stripe checkout → webhook fires → virtual key minted → install scheduled (FW-098) → audit-log entry (FW-097) → dashboard surfaces (FW-101) | Phase 8 GREEN + all dependencies GREEN | Customer journey from signup → install-ready works |

**Critical path:** v1 → v2 → v3 → Phase 3 (substrate base) → Phases 4-7 parallel → Phase 8 test → Phase 9 e2e pilot. Couples to all Phase 1 specs at e2e pilot stage.

---

## Review process

1. **CRO adversary review** — Stripe webhook attack surface + clickwrap-enforceability adversarial audit + cap-bump abuse patterns + customer-record schema PII minimization.
2. **CoS architecture review** — customer-record state-machine integrity, Library Compliance Space integration, failure-mode runbook completeness.
3. **COO-as-DPO (pending Spec 055 v4 H1 Captain ratify) compliance review** — DPA + Annex III + sub-processor list clickwrap enforceability per eIDAS; PII handling at signup; right-to-erasure scope at customer cancellation.
4. **COO adversary** — multi-failure-mode: Stripe webhook fails mid-flight + customer-record state desync + DPA template version transition + sub-processor list change simultaneously.
5. **CPO self-spawned review subagent** — fresh-context audit before commit.

Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing + Captain msg 2565 pricing already ratified.

---

**v1 LANDED 2026-05-20 23:05 UTC** (CPO authored under CoS Phase 1 priority queue continuation). CPO self-spawned review next.
