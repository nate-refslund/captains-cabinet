# Check-in — Day 7 (Video Call, 15min)

Per Spec 053 v3 Stage 6 cadence. Captain personal touch (per Stage 6 table + AC #9 — Day-7 stays Captain owned; NOT CoS-delegable except high-touch exceptions). Pre-call: CoS pulls customer's audit-log + Library Customer-Success Space record + Day-1/Day-3 check-in notes.

## Pre-call (5min)

CoS prep brief to Captain (delivered as `notify-officer.sh cpo`-style trigger 15min before call OR Captain reads Library record directly):
- Customer name + cabinet slug
- Officer roster + usage patterns over week 1 (which officers used most, what topics)
- Day-1 + Day-3 friction notes
- This week's audit-log highlights (cost trend, cap-utilization, any cap-bump events)
- Any blockers customer surfaced via CoS in DMs

Captain enters call with context, not generic check-in.

## Open (2min)

> "Hey {{customer_first_name}} — week 1 is the weird week. How's it going? What's been the strangest part?"

Open-ended. Listen to the framing they pick (positive/negative/neutral).

## Friction surfacing (5min)

> "Where's it been clunky? Anything where you thought 'this should be easier'?"

**Listen for common patterns:**
- **"I keep forgetting which officer to ask."** → Reinforce: always start with CoS. CoS routes internally. (Spec 053 v3 fold I7: 5-officer DM thread management — CoS-first.)
- **"Replies aren't quite my voice."** → Officers adapt over time + can pin tone via system-prompt edits. CoS notify-officer to CTO if specific tonal mismatch surfaces.
- **"I'm worried about cost."** → Walk through dashboard: today's spend, 7-day trend, cap-remaining. Show $50/day cap, current usage relative.
- **"Officers feel slow/unsure."** → Audit which officers are running; could be Sonnet+Opus-advisor routing not kicking in for hard subproblems. CoS surfaces to CTO for Spec 051 routing config check.
- **"I'm not delegating much."** → Normal week-1. Encourage 1-2 specific delegations this week. The weirdness fades by week 3.

## Optimization (5min)

Based on customer's stated use case (from discovery-call notes) + observed usage patterns from audit log:

> "Looking at how you've used it this week, here's what I'd push you to try next week..."

Tactical suggestions, NOT abstract advice. Examples:
- "You haven't used your CRO yet — let's pick one research question for them this week."
- "You're routing everything through CoS, which is good. Try asking CoS to ALSO ping CPO when it's a product question — get a second angle."
- "You hit cap once mid-week. Want to bump default to $X? Easy."
- "Your CoS handled X well. Try giving it Y next week — same shape, different content."

## Captain feedback (2min)

> "What would I personally improve about Cabinet for you specifically?"

**Listen for:**
- Feature gaps customer cares about (potential FW-* candidate)
- Concierge process gaps (Spec 053 Stage 6 retro candidate)
- Pricing model friction
- Onboarding gaps not surfaced at install

## Close (1min)

> "Day 30 we'll do a longer call — renewal conversation + NPS + expansion if you want more officers. Between now and then: just DM your CoS, that's all you need to do. I'll personally check in if anything surfaces."

Set expectation: customer doesn't need to be heroic; CoS handles the layer.

## CoS post-call (within 30min)

- Update Library Customer-Success Space record:
  - Day-7 friction-pattern notes
  - Day-7 optimization suggestions given
  - Captain feedback received
  - Customer's stated NPS-light pulse (if surfaced; 1-5 scale)
  - Next-week observation focus (officers customer commits to trying)
- Flag any cross-customer friction-pattern to CoS retro queue (Spec 053 v3 AC #10 friction-aggregation feedback loop)
- If customer surfaced potential feature gap → CoS notify-officer to CPO for Spec backlog assessment
- If customer surfaced cost/cap concern → CoS notify-officer to CTO for Spec 051 routing config check
- Schedule Day-30 call (renewal conversation + proper NPS)

## Captain-time-budget compliance (Spec 053 v3 AC #13)

This is a 15min budget item per customer per week (Captain personal). At 5 concurrent customers concurrent on Day-7 schedule, that's 75min/week budget just on Day-7 checks — fits within ≤4 hrs/wk ceiling. If forecasted breach detected via `cabinet/scripts/cos/captain-time-forecast.sh`, CoS holds new install slots.

## When Day-7 is genuinely off-track

If customer reports >50% of usage clunky, OR cap hit ≥3 times, OR NPS-light ≤3, OR explicit cancellation intent:
- Captain extends to 30min if available
- CoS schedules ad-hoc Day-10 follow-up
- COO + CPO + CTO surface to retro within 48h (cross-officer escalation per Spec 053 v3 fold I6 Day-7 NPS 0-3 early-warning)

---

*Personal call > scripted. Captain's voice + context-from-discovery-notes + warmth.*
