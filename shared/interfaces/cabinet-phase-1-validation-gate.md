# Cabinet Commercial Phase 1 → Phase 2 Validation Gate

**Date:** 2026-05-23
**Owner:** CPO (drafts) → CoS (ratifies) → Captain (final go/no-go on Phase 2 investment)
**Trigger:** Spec 050 §Phase 1 names "Phase 2 trigger (5 Cabinets stable)" but never defines *stable* as measurable criteria. Same gap the Sensed `pmf-gate-phase-2.md` closed for the consumer app. CRO audience-psychology digest 2026-05-23 supplies the B2B-founder PMF signals.
**Scope:** Defines the explicit gate that closes Cabinet Phase 1 (5 Danish concierge installs) and authorizes Phase 2 investment (self-serve .pkg + signup → install → first-officer flow, FW-102/103/107). This is **not** a Phase 3 (international expansion) gate — that's a separate Captain decision at 20 cabinets / 1M DKK MRR.

---

## Why this gate exists

Spec 050 Phase 1 has **technical** acceptance criteria (A1–A5: officer runs 30 days unattended, cap pauses + DMs, audit queryable, erasure receipt, install <4h). Those prove the substrate *works*. They do **not** prove **product-market fit** — a Cabinet can run flawlessly for 30 days and still be a product the customer quietly stops valuing.

Phase 2 is a large engineering investment (FW-102 notarized .pkg ~60h + FW-103 wizard + FW-107 self-serve onboarding). Pouring that in before the concierge cohort proves PMF is the classic premature-scaling error. This gate keeps the spend honest: **don't build self-serve until 5 humans paying real money prove they'd miss Cabinet if it disappeared.**

The gate must be **small-N appropriate.** N=5 makes statistical retention curves meaningless. So the gate is renewal-anchored + qualitative-heavy, mirroring how B2B concierge SaaS actually validates (Sean-Ellis-at-small-N, not cohort funnels).

---

## The core gate (AND — all three green)

Phase 2 investment does not start until **all three** are simultaneously true across the Phase 1 cohort (min 4 paying customers; 5 is target):

### 1. Renewal: ≥4 of 5 customers renew into month 2 (paying, past the 7-day guarantee)

- **Definition:** Customer's Stripe subscription bills a second month without cancellation. The 7-day satisfaction-guarantee window has closed and they did not refund-cancel. This is the single strongest PMF signal for a paid product — they voted with a second payment.
- **Why this number:** At N=5, one churn is tolerable (use-case pivot, wrong-fit discovery miss — natural). Two+ churns means the concierge model isn't producing durable value, and self-serve (which removes the Captain's personal-touch retention lever) would churn worse. 4/5 renewal = the human-touch model holds; automate it.
- **Measurement source:** Stripe subscription status + Library Customer-Success Space record. Cross-check against offboarding cancellation taxonomy (`concierge-offboarding-script.md`) — a churn classed "use-case pivot" / "no longer needed" is neutral signal; a churn classed "pricing-value mismatch" / "trust-gap on autonomous failures" is a **gate-failing** signal even if 4/5 renew (see §Disqualifiers).

### 2. Value-moment: ≥4 of 5 customers cite a *specific accomplished goal*, unprompted

- **Definition:** In a Day-7 or Day-30 check-in, the customer names a concrete outcome Cabinet delivered — "my CoS set up the morning briefing and I stopped starting my day in my inbox," not "it's neat" or "I like having it." Wharton April 2026: *users accomplish meaningful goals, they don't wander features.* The week-1 cheat-sheet 3-goals beat is designed to seed exactly this; the gate measures whether it landed.
- **Why this number:** A vague-positive cohort is a churn cohort with a delay. Specificity is the tell that the product crossed from novelty to utility. 4/5 naming a real outcome = utility is reproducible across customer types, not a single power-user fluke.
- **Measurement source:** Day-7 + Day-30 check-in notes in Library Customer-Success Space (Captain captures the quote verbatim). CoS tags each as `value-moment-specific` or `value-moment-vague`.

### 3. Economic fit: cap-hit is the exception, not the norm

- **Definition:** Across the cohort over the gate window, the $50/day per-cabinet cap is hit on <10% of customer-days, AND no single customer hits it >3 days in any week. Frequent cap-hits = the customer's real usage exceeds what the pricing tier economically supports = pricing-value mismatch (the #1 cancellation class in the offboarding taxonomy).
- **Why this number:** The margin math (Captain msg 2565) assumes ~$1500/mo Anthropic cost against 25–60k DKK revenue. Routine cap-hits mean either (a) we're under-pricing that customer's usage, or (b) officers are running hot inefficiently. Either way it's a pre-Phase-2 fix, not a scale-it signal. Rare cap-hits = pricing tier matches value.
- **Measurement source:** Audit-log cost data (Spec 052) + `visual-uat-cost.jsonl` cap-bump events + Stripe. Cross-reference Day-7 "I'm worried about cost" friction signal.

---

## Why AND, not OR

Each criterion alone is gameable:
- **Renewal** can be high if customers are friends-of-founder or haven't yet felt the cost (criterion 3 guards this).
- **Value-moments** can come from one highly-engaged outlier (the 4/5 floor + cross-type requirement guards this).
- **Economic fit** is necessary but not sufficient — a cheap-to-run product nobody values still passes (criteria 1+2 guard this).

The AND keeps it honest. Missing one = Phase 1 keeps iterating with the next concierge cohort; we do not start Phase 2 engineering.

---

## Health indicators (informative, not hard-gating at N=5)

These are noisy at N=5 so they don't gate, but a red reading here is a yellow flag worth a retro before declaring the gate green:

| Indicator | Healthy reading | Why it matters | Source |
|---|---|---|---|
| **Trust engagement** | ≥3 of 5 open audit-log / dashboard ≥1× unprompted | Audit-trail + governance is Cabinet's stated buy reason (Wharton: security+governance = primary B2B AI trust drivers). If nobody checks it, the trust story isn't a real buy reason — it's a feature we *think* matters. | Dashboard access logs (Spec 056) |
| **Usage depth** | Median customer engages ≥2 officers + DMs ≥3×/week by week 3 | Distinguishes "active executive layer" from "paid-then-ignored." Single-officer + sparse DMs = a chatbot relationship, not the multi-officer value prop. | Audit log + Telegram metadata |
| **Day-7 NPS-light** | Median ≥4/5 | Early honeymoon read; ≤3 triggers the Day-7 off-track escalation already specced. | Day-7 check-in pulse |
| **Day-30 NPS** | ≥1 promoter (9–10) + zero detractors who renew | Proper NPS at renewal decision point. | Day-30 call |

---

## Disqualifiers (any one fails the gate regardless of the 3 core criteria)

- **A churn classed "trust-gap on autonomous failures"** in the offboarding taxonomy. This is existential, not a fit miss — it means officers produced confident-wrong output that broke trust (the 85%/15% failure the whole positioning warns against). One such churn = stop and fix the trust surface (Spec 049 visual-UAT gate strengthening + onboarding framing) before Phase 2 scales the failure.
- **Captain onboarding-touch time exceeds 4 hrs/wk ceiling, sustained, at N=5** (Spec 053 AC #13). If concierge is already over-ceiling at 5 customers, Phase 2 self-serve isn't optional polish — it's a hard prerequisite, and the Phase 2 *shape* must lead with removing Captain touch, not adding officer features. This reshapes Phase 2 rather than blocking it, but it must be surfaced as a Captain decision.
- **Any unresolved GDPR / Annex III compliance incident** open at gate-evaluation time. Compliance is the trust substrate; an open incident means the foundation isn't proven.

---

## The graduation decision

When the 3 core criteria are green ≥2 consecutive weeks AND no disqualifier is active:

1. **CPO** assembles the gate-evidence packet (per-customer scorecard from Library Customer-Success Space).
2. **CoS** ratifies the read + scans for cross-customer friction patterns that should shape Phase 2 scope.
3. **Captain** makes the final go/no-go on Phase 2 investment — this is a business-model + spend decision, Captain-owned per autonomy boundaries.

A **no-go** is not failure — it routes back to "iterate Phase 1 with the next cohort" with a named reason (which criterion missed + why), exactly like the Sensed gate.

---

## Relationship to other artifacts

- **Spec 050 §Phase 1 ACs** — technical floor (substrate works); this gate is the PMF ceiling (customers value it). Both must pass.
- **`concierge-offboarding-script.md` cancellation taxonomy** — the failure-signal capture that feeds criterion 1 + the disqualifiers.
- **`check-in-day-7.md` + Day-30 call** — the touchpoints that capture criteria 2 + the NPS health indicators.
- **`pmf-gate-phase-2.md` (Sensed)** — sibling gate for the consumer product; same philosophy (validation-gated not calendar-gated), different metrics (B2C statistical vs B2B small-N qualitative).
- **CRO audience-psychology digest 2026-05-23** — the source for value-moment specificity (Wharton meaningful-goals), trust-engagement (security+governance trust drivers), and the 85/15 trust-gap disqualifier.

---

## Open questions for Captain (non-blocking — gate is usable as-is)

1. **Renewal floor at smaller N.** If Phase 1 lands only 3 paying customers (Danish SMB AI demand softer than hoped per Spec 050 Risk), is 3/3 renewal sufficient to graduate, or do we hold for a 4th customer first? CPO recommendation: hold for ≥4 customers before graduating — 3/3 is too thin to trust against selection bias.
2. **Reference-ability as a 4th core criterion?** The Sensed gate includes a word-of-mouth criterion. For B2B Danish concierge, "would you be a reference for another Danish founder" (from the offboarding script's honest-reference ask, applied to *renewing* customers) could be a 4th gate. CPO recommendation: keep it as a health indicator for Phase 1, promote to core gate for Phase 2→3. Surfacing for Captain call.

---

*Validation-gated, not calendar-gated. Don't build self-serve until the concierge cohort proves 5 humans would miss Cabinet if it disappeared.*
