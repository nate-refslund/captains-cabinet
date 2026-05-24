# Check-in — Day 1 (Quick Telegram Text, ~5min)

Per Spec 053 v4 Stage 6 cadence. **CoS-default** (Spec 053 fold I2 — Day-1 delegated to CoS unless discovery call flagged a high-touch customer; then Captain opt-in). 24h after install. Goal: confirm the customer actually talked to an officer + catch any first-day blocker before it festers.

## Pre-send (2min)

CoS pulls from Library Customer-Success Space + audit log:
- Did the customer send any DM in the first 24h? (audit log shows officer interactions)
- Any errors / officer non-responses in the first day?
- Install-day notes — anything the customer said they'd "try tomorrow"?

This shapes the message. A customer who's already DM'd 5 times needs a different note than one who's been silent.

## Message variants

**If customer already engaged (DM'd officers in first 24h):**

> "Hey {{customer_first_name}} — saw you've already been talking to your CoS. Nice. Anything feel clunky or confusing on day 1? No wrong answers — first-day friction is the most useful thing you can tell me."

**If customer silent (no DMs in first 24h):**

> "Hey {{customer_first_name}} — your Cabinet's been live a day now. No pressure, but the fastest way to get the feel is to just send your CoS a message — tell it what your day looks like and ask 'anything you'd take off my plate?' Want me to suggest a first thing to try?"

**If customer hit an error / officer didn't respond:**

> "Hey {{customer_first_name}} — I noticed {{specific issue}} yesterday. That's on us, not you. {{what we're doing about it}}. Anything else feel off? Day 1 is exactly when I want to hear it."

## Listen for (the actual point of Day 1)

- **Silence after a silent first day** → soft red flag. Customer may be stuck or hesitant. CoS offers a concrete first-thing-to-try; if still silent by Day 3, flag for Captain.
- **"How do I..." questions** → onboarding gap. Answer + note for cheat-sheet / install-walkthrough improvement.
- **"It said something wrong"** → trust-surface signal. Capture verbatim. This is the 85/15 failure mode — a confident-wrong officer output on day 1 is the most dangerous churn seed. Escalate to Captain + CTO same day if it's a real accuracy failure, not a UX confusion.
- **Enthusiasm** → note what they're excited about; feed it into the Day-7 optimization suggestions.

## CoS post-send (within 30min)

- Log Day-1 result to Library Customer-Success Space: engaged / silent / blocker-surfaced + verbatim of anything notable.
- If trust-surface failure surfaced → escalate to Captain + CTO immediately (do NOT wait for Day-3).
- If silent-after-silent → set Day-3 watch flag.
- If onboarding-gap question → note as cheat-sheet / walkthrough improvement candidate for CoS retro.

## When to pull Captain in on Day 1

Per AC #9 Day-1 is CoS-default, but escalate to Captain personally if:
- Customer surfaced a real trust-surface failure (confident-wrong officer output).
- Customer signaled cancellation intent or strong dissatisfaction in first 24h.
- Discovery call flagged this as a high-touch customer (Captain opted in pre-install).

## Captain-time-budget compliance (Spec 053 v4 AC #13)

Day-1 is CoS-default → ~0min Captain time at baseline. Captain pulled in only on escalation. This is the ~50min/mo saving from fold I2 across a 5-customer cohort.

---

*Day 1 is a tripwire, not a touchpoint. The job is to catch a stuck or burned customer before the silence hardens into churn.*
