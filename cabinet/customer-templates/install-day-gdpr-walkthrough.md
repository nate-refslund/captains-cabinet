# Install-Day GDPR Walkthrough Script — 15min

Per Spec 053 v3 Stage 4 install-day session, Captain-led with customer. Captain framing per CRO audience-psychology brief insight 5: **trust signaling not compliance tax.** Lead with "we treat your data like it's ours" not "here are the regulations."

Walks customer through Cabinet's compliance posture in the same install session — same flow as showing them their dashboard. Don't make it feel separate. Don't apologize for it.

## Open (1min)

> "OK — last bit before we wrap. I want to walk you through how Cabinet handles your data, because honestly this was one of the harder parts to get right and it's part of why Cabinet exists in this shape at all. Not the legal-fine-print version. The actual version. About five minutes."

Frame:
- Captain personally cares about this
- Not boilerplate compliance recital
- Time-bounded ("five minutes" — keeps customer engaged)
- "Part of why Cabinet exists" — repositions GDPR work as product DNA, not tax

## Where your data lives (3min)

Show customer the dashboard's data-handling matrix page (refslund.ai/dashboard → /data-handling).

> "Here's what Cabinet stores about you, where, for how long, and who can read it. Three categories:"

**1. Your Mac (cabinet's local storage):**
- Officer working notes (Tier 2 memory)
- Cabinet config files
- Officer audit log (local queue if our server's slow)
- Customer attachments (when officers process files you share via Telegram)

> "All of this is on YOUR Mac. We don't sync it. We don't have access to it. You can grep through it yourself. When you cancel, this gets deleted from your Mac via the offboarding script."

**2. refslund.ai server-side (our infrastructure):**
- Your account profile (email, name, company, install date)
- Stripe payment record
- Audit log of every officer action + LLM call (90-day hot storage, then anonymized 5-year cold archive for Danish bookkeeping compliance)
- Signed DPA + sub-processor list ratification
- Erasure-request records (if you ever submit one)

> "This lives in Frankfurt, EU-resident, on Hetzner. Never leaves the EU for the storage itself. The LLM calls go to Anthropic in the US — they're our sub-processor, and there's a Standard Contractual Clauses agreement covering that transfer."

**3. NOT stored anywhere by Cabinet:**
- Telegram message text (we log the metadata — that you sent a message, timestamp, officer who handled — but NOT the message text)
- LLM prompt + completion text (we count tokens, log model + cost; we don't store what you asked or what Claude said)
- Customer-attached file contents (only filename + type + size)

> "We minimize. Article 5 of GDPR — data minimization principle — says you store only what you need. We don't need your message content for billing or audit. So we don't store it."

## Sub-processors (3min)

Open refslund.ai/sub-processors page.

> "Anyone else processes your data, you should know about them. Here's our full list. Nine companies including us."

Walk through the 9-row table (per Spec 055 v7 sub-processor list):
- **Anthropic** — provides the LLM (Claude). Standard Contractual Clauses + DPF certification.
- **OpenAI** + **Google (Gemini)** — listed but DISABLED Phase 1. If we ever enable as fallback, you'll get 30 days notice + option to object.
- **ElevenLabs** — voice synthesis if you use voice messages.
- **Stripe** — billing.
- **Cloudflare** — DNS + TLS.
- **Hetzner** — EU-resident hosting.
- **PostHog** + **Sentry** — product analytics + error monitoring (us only; not customer-data).

> "If we add a new sub-processor, you get a 30-day notification + option to object. You can cancel rather than accept a sub-processor you don't want. That's Article 28(2)."

> "What we DON'T do: train AI models on your data. Anthropic's terms forbid it for their paid customers — that's contractually binding. And we don't either. Your conversations with your CoS are not training data."

## Your rights (3min)

> "You have rights under GDPR Articles 15-22. Here's the practical version of each:"

- **Article 15 — access**: "Want a copy of everything we have on you? Click 'Request my data' on your dashboard. Within 30 days you get a password-protected ZIP."
- **Article 16 — correction**: "Something wrong in your account? Email me, we fix it within 30 days."
- **Article 17 — erasure**: "Want to delete everything? Click 'Erasure request' on your dashboard. We honor it within 30 days. Some billing records have to stay 5-10 years per Danish tax law, but we anonymize those — the random-token replacement, no way to re-identify you."
- **Article 20 — portability**: "Want your data in a portable format to take elsewhere? Same export endpoint. You own the data."
- **Article 21 — objection**: "Want to object to a specific processing? Tell me. We assess + respond within 30 days."
- **Article 22 — automated decisions**: "We don't use AI to make decisions ABOUT you. The AI makes decisions WITH you. Big difference."

## Audit + integrity (3min)

Show customer the audit log on dashboard (refslund.ai/dashboard/audit).

> "Every officer action — every LLM call, every tool call, every Telegram message they handle — is logged here. Read-only. You can see what they did. You can verify the log hasn't been tampered with — there's a 'Verify yourself' button that walks the hash-chain in your browser. Doesn't even need to talk to our server to verify."

> "If you ever wonder 'wait, did CoS really do that?' — log shows it. If you don't see what you expect — that's a real problem we'd want to know about."

This is the trust differentiator. Most AI products don't ship audit. Cabinet does.

## Annex III (1min)

> "One thing we DO restrict — Phase 1 ToS excludes EU AI Act Annex III high-risk use cases. That means: don't use Cabinet for biometric ID, hiring decisions, credit scoring, law enforcement, that kind of thing. You signed the attestation at signup. If your use case ever shifts that direction, we have to refuse — we'd help you offboard cleanly."

Honest restriction; not apologetic.

## DPO (1min)

> "Last thing: if anything about your data ever bothers you and you want to escalate beyond me, COO is our Data Protection Officer. Email dpo@refslund.ai. Independent oversight role — they can override me if needed."

> "And if Denmark's data authority (Datatilsynet) ever wants to ask about us, they can. Cabinet has full ROPA + DPIA documentation ready. You can lodge a complaint with them directly anytime."

## Close (30sec)

> "OK. That's the data part. Questions?"

Pause. Listen.

Customer questions usually surface here. Common ones:
- **"Where can I read the full DPA?"** → "refslund.ai/legal/dpa — the version you signed. Also downloadable from your dashboard."
- **"What happens if Anthropic has a breach?"** → "Anthropic notifies us; we notify you within 72 hours per Article 33; if there's risk to you, we tell you directly per Article 34."
- **"Can I see exactly when you log my data?"** → "Audit log is real-time. Open the dashboard, see today's activity."

## Captain personal posture throughout

- **Don't apologize for compliance work.** Cabinet exists in this shape BECAUSE of how data is handled, not despite it.
- **Don't use jargon unless customer asks.** "Article 17" is fine — but always pair with "erasure / deletion." Translate as you go.
- **Watch customer body language.** If they're zoning out, condense. If they're engaged + asking, expand.
- **The walkthrough IS the relationship.** Customer who hears Captain personally explain "we don't train on your data" trusts Captain personally for it. Not boilerplate.

## CoS post-walkthrough

Customer surfaces compliance questions Captain couldn't answer in 30sec → CoS notify-officer to COO-as-DPO for follow-up within 24h. CoS records customer's compliance-sensitivity level in Library Customer-Success Space (helps tune future communication).

## When to skip / shorten

- Customer is GDPR-savvy + signaled it in discovery call → skip the rights walkthrough, just point to dashboard. ~5min total.
- Customer is GDPR-fatigued (heard 100 of these) → still do the audit-log demo + Annex III + DPO. ~7min.
- Customer is genuinely curious + asks deep questions → expand audit-log demo + show real captain-decisions trail entry. Up to 25min.

Bound by Stage 4 60-90min total — don't blow install budget on GDPR alone.

---

*"We treat your data like it's ours" → say it once at open + once at close. Make sure customer hears it.*
