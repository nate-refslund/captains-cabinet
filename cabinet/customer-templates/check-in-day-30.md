# Check-in — Day 30 (Renewal + NPS Call, 30min)

Per Spec 053 v4 Stage 6 cadence. **Captain personal** (the renewal conversation is relationship-defining; not CoS-delegable). 30 minutes, video. This is the most consequential touchpoint — it's the renewal decision, the proper NPS capture, the expansion conversation, and the single richest input to the Phase 1 validation gate.

**Note (Spec 053 fold 053-12):** if the customer has already cancelled within the Day-30 window, the cancellation/wind-down flow (`concierge-offboarding-script.md`) supersedes this call. This template is for the renewal path.

## Pre-call (5min)

CoS prep brief to Captain (delivered 15min before OR Captain reads Library record):
- Customer name + cabinet slug + install date (confirm we're at ~30 days)
- Full 30-day usage arc: officer engagement trend, DM frequency, which officers became load-bearing
- NPS trajectory: Day-3 light pulse → Day-7 pulse → now
- Day-7 friction + optimization suggestions given → did the customer act on them?
- Cost arc: 30-day spend, cap-utilization, any cap-bump events (economic-fit read for the validation gate)
- Audit-log engagement: did the customer ever open the dashboard / audit log unprompted? (trust-engagement indicator)
- Expansion signals: did they ask about more officers, integrations, more employees on the plan?

Captain enters knowing the full arc, not a snapshot.

## Open (3min)

> "Hey {{customer_first_name}} — 30 days. Genuinely curious how you'd sum it up. If you had to describe what Cabinet's been for you this month in a sentence, what would it be?"

Listen to the framing they reach for. This sentence is gold — it tells you whether they bought utility ("it runs my morning") or novelty ("it's a cool AI thing"). Capture it verbatim for the validation gate's value-moment criterion.

## The value-moment question (5min)

> "What's something concrete Cabinet did this month that you wouldn't have gotten done otherwise — or would've done worse, slower, or not at all?"

**This is the validation-gate criterion-2 capture.** You're looking for a *specific accomplished goal*, not a vague positive. Push gently for specificity:
- Vague ("it's been helpful") → "Helpful how? Give me the actual thing."
- Specific ("CoS set up my briefing and I stopped drowning in my inbox") → that's the signal. Capture verbatim. CoS tags it `value-moment-specific`.

If they genuinely can't name one after a gentle push → that's a real signal. Note `value-moment-vague`. A renewing customer who can't name a concrete win is a fragile renewal — flag for closer Day-37+ attention.

## Proper NPS (3min)

> "On a scale of 0 to 10 — how likely are you to recommend Cabinet to another founder like you?"

Then the open follow-up regardless of score:
> "What's the main reason for that number?"

- **9-10 (promoter):** proceed to testimonial + reference ask (below).
- **7-8 (passive):** "What would've made it a 9?" — the gap is your Phase 2 roadmap input.
- **0-6 (detractor):** "What's the biggest thing we'd need to fix?" — and if they're renewing despite a detractor score, that's a fragile renewal. Surface to CoS retro + Captain watch.

Log the 0-10 score + verbatim reason to Library Customer-Success Space. This is the validation-gate NPS health indicator.

## Renewal conversation (5min)

By Day 30 the second month is already billing (Stripe subscription) unless they cancelled — so this isn't "will you pay," it's "is this still right."

> "Month two's already underway. Before it rolls, anything about the shape — officers, pricing tier, how we work together — you'd want to change?"

- **Stable renewal:** confirm the fit, move to expansion.
- **Hesitation:** surface it now. "What would make month two clearly worth it?" Better to hear doubt at Day 30 than discover a silent cancel at Day 45.
- **Employee-count change:** if their team grew/shrank, adjust the 5k DKK/employee tier (max 7). CoS updates Stripe.

## Expansion (3min — only if NPS ≥7 and renewal stable)

> "You've been using {{officers they use}}. Is there a corner of your week where you've thought 'I wish I could hand this off too'?"

Expansion paths:
- **More officers** — they started with a subset; activate another role.
- **More employees on the plan** — team grew.
- **Custom integration** — a tool they want their officers connected to (note as FW candidate; don't promise).

Don't push. Expansion that's pulled sticks; expansion that's pushed churns.

## Testimonial + reference ask (2min — only if NPS ≥9)

> "Two things, only if you're comfortable. One — could I quote you on what you said about {{their value-moment}}? Helps the next founder understand what this actually is. Two — would you take a 15-min call from another Danish founder considering Cabinet, just to tell them your honest experience?"

Both are opt-in. A promoter who agrees to be a reference is the strongest Phase-1 validation signal there is — it's the candidate 4th gate criterion (per validation-gate open question #2).

## Close (1min)

> "This was genuinely useful — thank you. You'll keep talking to your CoS day to day; I'll check in personally if anything big surfaces. And if you ever hit something Cabinet should've handled and didn't, tell me. That's the most valuable thing you can send me."

## CoS post-call (within 30min)

- Update Library Customer-Success Space record:
  - 30-day summary sentence (verbatim)
  - Value-moment (verbatim + tag `value-moment-specific` / `value-moment-vague`)
  - NPS score (0-10) + reason (verbatim)
  - Renewal status: stable / hesitant / employee-count-change
  - Expansion flags raised
  - Testimonial consent + reference-call consent (if NPS ≥9)
- **Feed the validation gate:** update the customer's scorecard against `cabinet-phase-1-validation-gate.md` — renewal (criterion 1), value-moment specificity (criterion 2), cap-utilization (criterion 3), NPS + trust-engagement (health indicators).
- Fragile-renewal flag (renewing + vague value-moment OR detractor NPS) → CoS retro + Captain watch + schedule Day-37 closer touch.
- Testimonial consent → CoS drafts quote for Captain approval; reference consent → log to potential-reference list for future discovery calls.
- Expansion flag → CoS notify CPO for spec/backlog assessment + Stripe tier change if employee-count.

## Captain-time-budget compliance (Spec 053 v4 AC #13)

30min Captain personal per customer per month. At 5 concurrent customers staggered, ~2-3 Day-30 calls land in any given week → within the ≤4 hrs/wk ceiling alongside Day-7 calls. If `captain-time-forecast.sh` flags breach, CoS holds new install slots (does NOT compress Day-30 — it's the renewal anchor).

## When Day-30 is a save-attempt (not a renewal)

If the customer signals cancellation intent during the call: do NOT pivot into a hard save. Per offboarding philosophy (honest exit > retention pressure), shift to understanding *why* — that feedback is worth more than a pressured one-month extension. Route to `concierge-offboarding-script.md` Listen section. Offer one honest fix if there's a real fixable gap; accept the exit gracefully if not.

---

*Day 30 is where Phase 1 learns whether it has product-market fit. Capture the signal cleanly — the validation gate depends on honest reads here, not optimistic ones.*
