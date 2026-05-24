# Concierge Offboarding Wind-Down Call — 30min

Per Spec 053 v3 §Concierge offboarding. Triggered by customer-initiated cancel via Stripe portal OR Captain personal contact OR Day-7/Day-30 NPS signal that customer is leaving.

Customer's right to refuse this meeting per Spec 053 v3 AC #7 + fold 053-09. If declined, proceed to erasure flow without 30min call (best-effort feedback gathered via email questionnaire).

## Pre-call (5min)

CoS prep brief to Captain:
- Customer name + cabinet slug + signup date + cancellation date
- Officer roster + usage patterns (which officers used heavily / rarely)
- Day-1/3/7/30 check-in notes (especially friction-patterns + NPS trends)
- Stated cancellation reason (if surfaced via Stripe portal cancel-reason form OR CoS DMs)
- Outstanding founder-actions or open Captain-decisions affecting customer

Captain enters call with full context.

## Open (3min)

> "Hey {{customer_first_name}} — thanks for jumping on. This isn't a save call. Cancellation is processed. I just want to understand what didn't work so we can build a better Cabinet for the next founder, and make sure your offboarding is clean. Sound OK?"

Frame: not save attempt. Honest curiosity + commitment to clean exit.

## Listen (15min)

Open-ended questions. Don't lead. Take notes.

> "Walk me through the decision. What changed for you?"

Common patterns (don't probe for these, but recognize when surfaced):
- **Pricing didn't match value**: customer hit cap multiple times + dashboard showed officers running hot.
- **Trust gap**: customer found officers "85% right 15% quietly wrong" — autonomous-feeling failures eroded trust.
- **Wrong fit**: discovery-call Go decision was wrong; customer wasn't the right founder profile for Phase 1 Cabinet.
- **Use-case pivot**: customer's business changed; Cabinet wasn't aligned with new direction.
- **Found alternative**: customer adopted Cursor / Devin / Lovable / different agent-platform that matched their workflow better.
- **No longer needed**: customer hired humans, got time back, doesn't need AI exec layer right now.
- **Cancellation per Annex III mid-use**: customer's use case shifted into Annex III high-risk; we refused; they cancel. (Per Spec 053 v3 fold 053 H5 path.)

For each: **listen first, then ask clarifying questions, then reflect back to confirm understanding.** Don't argue.

> "What's something Cabinet did well that we should keep?"

> "What's something we should kill outright?"

> "If you knew at signup what you know now, what would you have wanted me to say differently?"

This last question is gold — surfaces discovery-call gaps + pre-install-expectation gaps + onboarding-promise misses.

## Offboarding logistics (7min)

> "Here's what happens next, in plain English."

Walk through Spec 053 §Concierge offboarding + Spec 055 v7 §Right-to-erasure flow:

1. **Stripe handles billing.** Final invoice settled. 7-day satisfaction-guarantee refund if within window; pro-rata otherwise.
2. **Your Cabinet stays running for 7 days** as grace window. Officers respond as normal — use them, don't use them, your choice.
3. **After 7 days, customer-erasure.sh runs.** Officers stop. Files at `~/Library/Application Support/refslund-cabinet/` + `~/Library/Logs/refslund-cabinet/` + `~/Library/Caches/refslund-cabinet/` + LaunchAgent plists at `~/Library/LaunchAgents/dk.refslund.cabinet.officer.{cos,cto,cpo,cro,coo}.plist` (per Spec 058 v1.2 reverse-DNS bundle ID convention) deleted via `launchctl bootout gui/$(id -u) <plist>` + `rm -rf`. Mac-side gone.
4. **Refslund.ai server-side erasure** within 30-day GDPR Article 17 SLA. Audit log pseudonymized (NOT deleted — preserves hash-chain integrity per Spec 052 AC #8 two-hash-field schema); cold-archive billing records anonymized per Spec 055 v7 AC #19 (Bogføringsloven 5y / Skatteforvaltningsloven 10y statutory retention with PII stripped).
5. **DPA + sub-processor list + Annex III attestation records** preserved in Library Compliance Space (Article 30 ROPA + audit trail; anonymized).
6. **Customer dashboard at refslund.ai/dashboard** still accessible to customer for 7-day grace window — download full audit log + Article 15 export if desired BEFORE erasure runs.
7. **Erasure completion notification** delivered via email when 30-day SLA closes.

> "Any questions about the offboarding process?"

## Captain ask (3min)

> "Two asks before we wrap. (1) Would you be willing to be a quote-sourced reference if a future Cabinet customer asks why someone might cancel? Honest framing — you don't have to recommend us, just describe your experience accurately. (2) If you ever build something Cabinet should've helped you with, send me a note. I'd want to know."

These two asks are honest — Cabinet learns from honest exit interviews. Customer can decline both, that's fine.

## Close (2min)

> "Honestly, thanks for trying Cabinet. Phase 1 is small and concierge specifically so we can learn from people like you. Your feedback shapes the next version. Safe travels."

Captain signature on the warm exit. Cabinet keeps the door open if customer ever returns.

## CoS post-call (within 30min)

- Update Library Customer-Success Space record with offboarding-call notes
- Log cancellation reason + key feedback to CoS retro queue (Spec 053 v3 AC #10 friction-aggregation feedback loop)
- Trigger Spec 055 v7 §Right-to-erasure runbook (8-step + 30-day SLA tracker per Spec 052 CTO #9 shared SLA substrate)
- Schedule Day-37 (post-erasure-completion) email confirmation to customer
- Captain reflection prompt: "What did you learn from this cancellation? What should the next discovery-call screen for?"
- Friction patterns aggregated across 2+ cancellations → CoS monthly retro + Spec 053 amendment candidates

## Cancellation reason taxonomy (for retro analysis)

| Reason class | Pattern | Spec amendment lane |
|---|---|---|
| **Pricing-value mismatch** | Multiple cap-hits + low officer utilization | Spec 054 pricing structure (Phase 2 commercial-direction) |
| **Trust-gap on autonomous failures** | Officers 85% right + customer perceives 15% as catastrophic | Spec 053 v3 onboarding framing + Spec 049 v3.2 visual-UAT gate strengthening |
| **Wrong fit (discovery miss)** | Customer profile didn't match Phase 1 (curiosity tourist; non-founder; wrong vertical) | Spec 053 v3 Stage 1 discovery-call-script refinement |
| **Use-case pivot** | Customer's business changed | n/a — not Cabinet's fix |
| **Found alternative** | Adopted competitor product | Spec 050 commercial-direction master Phase 2 differentiation |
| **No longer needed** | Hired humans / time back | n/a — natural cabinet lifecycle |
| **Annex III mid-pivot refusal** | Customer wanted Annex III; Cabinet refused | Spec 055 ToS framing + Spec 053 Stage 1 Annex III screening tightening |

## Captain-time-budget compliance

Wind-down call = 30min Captain personal per cancellation. At <5 customers Phase 1 + cancellation rate uncertain, budget impact modest (≤2 wind-down calls per month likely). Within Spec 053 v3 AC #13 ≤4 hrs/wk Captain onboarding-touch ceiling.

## When customer declines wind-down call

Per Spec 053 v3 AC #7 + fold 053-09: customer right to refuse 30min call respected. Substitute:
- Email questionnaire with 5 open-ended questions (mostly from "Listen" section above)
- Erasure flow proceeds normally
- Best-effort feedback gathered async; absence noted in CoS retro

---

*Honest exit > save attempt. Cabinet learns more from cancellations than from happy customers — protect the signal by not muddying it with retention pressure.*
