# Discovery Call Script — 30min

Per Spec 053 v3 Stage 1. Captain leads with CoS for structure + note-taking.

## Pre-call (5min before)

- Pull prospect's brief intro / inbound from Library Customer-Success Space (if any prior contact)
- Confirm video link works (Zoom / Google Meet / Captain preference)
- CoS opens fresh per-customer Library Customer-Success Space record (slug from prospect's company name)

## Open (3min)

> "Thanks for making time. Quick frame: this is a 30-min call to see if Cabinet's a fit for you. No pitch — just questions, your turn to ask anything, then I'll be honest about whether you're a fit for our first 5 customers. Sound good?"

Ground rules: honest both ways. We pick our first customers carefully.

**Honest-disclosure beat (30 sec):** After the frame, before the first question:

> "One thing upfront: I'll tell you what Cabinet does reliably today and what's still early-stage. You shouldn't have to discover the difference later — that's expensive. So I'll be straight."

This builds trust faster than any feature description. Founders who've been burned by AI hype appreciate it immediately. (Source: Wharton April 2026 — trust gap = #1 SMB AI adoption barrier.)

## Questions (20min)

### 1. What does your week look like?

> "Walk me through a typical week. Where does your time go? What gets in the way of higher-leverage work?"

**Listen for:** scattered context-switching, manual work that could route through Cabinet officers, repetitive decisions that AI could surface.

### 2. What does your team look like?

> "Are you founder-solo, 1-2 people, larger SMB?"

**Maps to:** employee_count in Stripe pricing (25k + 5k × employees, max 7).

### 3. Which officer roles sound most useful?

Walk through 5 officer roles in ≤2min each:

- **CoS (Chief of Staff)** — your single Telegram point of contact, coordinates the others
- **CTO (Chief Technology Officer)** — engineering opinions, build/buy framing, technical sanity checks
- **CPO (Chief Product Officer)** — product specs, user-facing audits, what to ship/cut
- **CRO (Chief Research Officer)** — market sweeps, competitive intel, lateral angle research
- **COO (Chief Operating Officer)** — operational simplicity, process design, compliance hygiene

> "Which 1-2 jump out as 'wish I had this today'?"

**Note:** customer can start with subset; full roster always available; usage patterns aggregate to CoS retro.

### 4. Mac & network readiness

> "Do you have a Mac at your office or home that can stay on 24/7? macOS Sequoia or later? Stable internet?"

**Maps to:** pre-install checklist (Spec 053 Stage 3). 16GB+ RAM, 200GB+ free disk, port 22 or Tailscale.

### 5. Compliance considerations

> "Any compliance constraints we should know about — regulated industry, special-category data handling, EU AI Act high-risk use cases like hiring decisions, credit scoring, biometric ID?"

**Critical:** Phase 1 ToS excludes Annex III high-risk use cases per Captain msg 2565. If prospect surfaces any, route to Spec 053 §Edge case "Customer requests Annex III mid-Day-3" graceful refusal + offboarding-if-pivot-impossible.

### 6. Why now?

> "What changed recently that made you look at this? Other tools you tried? What didn't work?"

**Listen for:** real pain vs curiosity tourism. Buyers who can articulate the gap convert; curiosity tourists churn.

### 7. Pricing expectations

> "Cabinet is 25,000 DKK base + 5,000 DKK per employee per month, max 7 employees. So between 25k and 60k DKK monthly. Sound reasonable for what we've talked about?"

**Listen for:** sticker shock vs measured response. If shock, recalibrate fit. If yes, proceed.

## Their turn (5min)

> "What questions do you have for me?"

Common questions + honest answers:

- **"What does Cabinet do that ChatGPT doesn't?"** — Cabinet's an executive team, not a chatbot. Multiple officers, persistent context, audit trail, integrates into your week via Telegram. You stay in the loop on architecture and the big calls; officers handle execution. Unlike autonomous-agent products (which are 85% right + 15% quietly wrong at production scale), Cabinet is structured oversight — officer roles + audit trail + you-in-the-loop.
- **"Devin is €20/mo. Why are you 25,000 DKK?"** — Different problem. Devin is a software-development agent — it writes code. Cabinet is an executive layer for founders: five officers (CoS, CTO, CPO, CRO, COO), persistent memory, GDPR-native audit trail, and a concierge setup where I'm physically at your Mac. You're not buying a coding assistant — you're buying an AI executive team with Danish compliance baked in. If you only need code written, Devin's a good pick. If you need someone to help you think, coordinate, and run your operations, that's Cabinet.
- **"What happens to my data?"** — Your Mac holds your data. Audit log on our server (you can verify integrity client-side). DPA + sub-processor list at signup. EU-resident infrastructure.
- **"What if I cancel?"** — Stripe cancels anytime via portal. 7-day satisfaction guarantee for full refund. After that, prorated. Your data deletes per GDPR Article 17 (30-day SLA).
- **"What does install look like?"** — I come to your location (Odense / Copenhagen / DK reachable) for 60-90min, set up your Cabinet on your Mac, walk you through first interactions. Concierge.
- **"How long until I see value?"** — Day 1 you'll send your first DM. Day 7 we check in. Day 30 we look at NPS. Most founders feel weird about it for a week, then it clicks.

## Close (2min)

If yes fit: > "OK — I think Cabinet's a fit. Let me send you a signup link tomorrow with the pre-install checklist. We can target [date] for install. Sound good?"

If maybe fit: > "Let me think on this overnight. I'll send you a yes/no by tomorrow morning with reasoning either way."

If no fit: > "Honestly, I don't think Cabinet's the right fit for you right now. [Specific reason]. If [condition changes], reach back out."

## CoS post-call (within 30min)

- Update Library Customer-Success Space record with discovery-call notes + Go/No-Go decision
- If Go: schedule signup window (T+0 to T+7) + Captain calendar block for install (60-90min)
- If Maybe: surface decision to Captain by morning with recommendation
- If No: archive record + note pattern for CoS retro

## Discovery-call decision criteria

**Go (✓):**
- Real founder pain articulated
- Mac + network ready (or willing to procure)
- Pricing reasonable to them
- No Annex III high-risk use case
- Danish customer within physical reach OR willing to video-screen-share for install
- Honest engagement (asks real questions, pushes back where reasonable)

**No (✗):**
- Curiosity tourism (no specific pain, browsing the future)
- Out-of-DK billing address
- Annex III high-risk use case + unwilling to pivot
- Compliance constraints we can't meet Phase 1 (e.g., on-prem-only, no internet)
- Pricing shock that doesn't resolve

**Maybe (?):**
- Real pain + uncertain fit
- Possible scope creep (wants something Cabinet isn't yet — Phase 2?)
- Need to think overnight + verify gut

Document the decision + reasoning in Library Customer-Success Space record.

---

*This script is intentionally short. Captain personal touch over scripted flow. Adapt per prospect.*
