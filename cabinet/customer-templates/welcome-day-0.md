# Welcome Email — Day 0 (Signup)

Per Spec 053 v3 Stage 2. Triggered by Stripe `checkout.session.completed` webhook (FW-099 Spec 054 AC #8). Composed in CoS-officer session; Captain reviews ≤5min approve OR edit (per Spec 053 v3 I3 fold: customers 1-2 = Captain compose-from-scratch; customers 3+ = template + Captain edit).

---

**To:** {{customer_email}}
**From:** Nate <nate@refslund.ai>
**Subject:** Welcome to Cabinet, {{customer_first_name}} — install on {{install_date}}

Hi {{customer_first_name}},

Welcome to Cabinet. Your subscription is active.

Quick rundown of what happens next:

**This week ({{date_range_to_install}}):**
- I'll send a short readiness check before install — Mac specs + network details to confirm we're set.
- We're set for **{{install_date}} at {{install_time}}** to bring your Cabinet to life. {{install_location}}.

If you have questions before install, just reply to this email.

**Install day:**
- 60-90min, mostly with you watching me set it up + walking you through the first interactions.
- By the end, you'll have sent your first DM to your CoS in Telegram, and your Cabinet is live. Officers handle execution; you stay in the loop on architecture and the bigger calls.

**First week after install:**
- I'll check in Day-1 (quick text), Day-3 (light usage pulse), Day-7 (15min video call), Day-30 (renewal conversation + NPS).
- Anything broken or confusing in between — just DM your CoS. They handle it.

**Right now:**
- Watch for the pre-install checklist email in the next 24h.
- If anything changes (install date, your Mac availability, anything), reply to this email.

Looking forward to bringing your Cabinet to life on {{install_date}}.

— Nate

---

P.S. Your Cabinet dashboard is at https://refslund.ai/dashboard — bookmark it now. It'll start showing data on install day.

P.P.S. If you're wondering "wait, am I supposed to do anything before install?" — short answer no. I'll reach out if I need anything from you. Just confirm your Mac stays on for the install.

---

## Captain-edit checkpoint (CoS routing)

Before sending: CoS pre-fills template with {{customer_first_name}}, {{install_date}}, {{install_time}}, {{install_location}} (Odense / Copenhagen / DK-other with video-share), {{date_range_to_install}} from Stripe webhook + Library Customer-Success Space record.

Captain reviews ≤5min via CoS-spawned trigger:
- Adjust tone to match Captain's voice for this specific customer (based on discovery-call notes)
- Add any personal touch (referenced inside joke, mutual context)
- Approve OR edit OR replace

CoS sends as Captain's email (via Captain-owned email account; OR copy-paste from Captain's client; never auto-send unsupervised per CTO #3 fold).

## Post-send

- CoS notify-officer to CTO: "FW-098 install scheduled {{install_date}} for {{cabinet_slug}}"
- CoS notify-officer to CPO: "Cabinet onboarding underway for {{customer_first_name}}; cheat-sheet-week-1.md ready for post-install Stage 5"
- CoS adds welcome-sent timestamp to Library Customer-Success Space record
- Schedule pre-install checklist email for T+24h via Spec 053 Stage 3 trigger

---

*Personal tone over template precision. Captain edits make this customer-specific.*
