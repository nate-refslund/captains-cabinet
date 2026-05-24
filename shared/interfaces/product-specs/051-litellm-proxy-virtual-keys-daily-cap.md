# Spec 051: LiteLLM Proxy + Virtual Keys + Per-Cabinet Daily Cap (FW-096 Phase 1 Priority 1)

**Version:** v5 (CoS architecture review fold + Captain Q1 ratification cleanup) — v4 superseded
**v5 changelog:** CoS architecture review surfaced 3 BLOCKERs + 1 IMPROVEMENT applicable to Spec 051. Resolutions:
- **CoS B1 currency contradiction:** AC #3 cap-hit payload was DKK-field-only despite v2 USD-commit. v5 aligns AC #3 payload to USD primary (`cap_usd` + `spent_usd`) with explicit DKK display fields (`cap_dkk_display` + `spent_dkk_display`) for dashboard render only. Audit-log JSON schema also aligned (cost_raw_usd + cost_marked_up_usd) — was already correct in §audit-log-emission. Three contradiction sites cleaned.
- **CoS B3 phasing stale vs Q1 ratification:** Phasing table Phase 1 (line 224) previously treated Q1 sub-processor list as gate; Captain msg 2583 Q5 cross-spec ratification (per Spec 055 v3 fold + v4 retention) already resolved this Anthropic-only Phase 1. v5 updates Phase 1 row to RESOLVED status; Phase 6 fallback wiring stays "wired but DISABLED" per Q5 ratification.
- **CoS I2 llm_routing schema cross-spec citation:** new `cabinet/scripts/lib/llm-routing.sh` helper + `agent-instructions.md → llm_routing` schema field referenced in v2 fold but not cross-referenced to Spec 049 agent-instructions.md schema. v5 adds explicit Spec 049 reference inline + flags as Spec 049 v3.2+ candidate amendment for next agent-instructions schema bump.

**v4 prior changelog preserved below** (FW-085 Path A absorption + 4-OQ resolution).
**v2 prior changelog further below** (CPO self-review + CTO tech review fold).
**Priority:** P0 — gates the rest of Phase 1 commercial build (FW-097/098/099/100/101)
**Framework ticket:** FW-096 (in `shared/cabinet-framework-backlog.md`) — note: existing FW-096 backlog entry frames cap as per-officer; supersede with per-cabinet TOTAL per Captain msg 2565 ratification.
**Owner:** CPO (spec) + CTO (architecture + implementation) + CoS (Captain ratification pipeline)
**Scope:** New refslund.ai-hosted proxy substrate + per-cabinet virtual-key issuance + per-cabinet daily-cap enforcement + audit-log emission for FW-097
**Canonical artifact home:** Library Specs Space (per A11)
**Three-layer naming clarification (per Captain msg 2565 ratification):** "Cabinet" = commercial product Spec 051 builds for; "Captain's Cabinet" = open-source framework substrate; "refslund.ai" = practice/business. Spec 051 lives in the open-source `captains-cabinet` repo (BSL 1.1) since substrate; commercial-customer-facing surfaces (signup, dashboard, billing) move to private repo per Captain msg 2559+2560 BSL boundary.
**Evidence:** Captain msg 2565 (2026-05-20 13:58 UTC per captain-decisions.md — Path A generic + Danish-first + 25k DKK base + 5k DKK/employee, max 7 employees, **$50/day USD per-cabinet cap TOTAL across all officers — NOT per-officer**); CRO brief `2026-05-20-customer-grade-dev-tool-precedent.md`; CoS Spec 050 commercial-direction master (v1.1 amendment overnight per 14:00 UTC trigger).
**v2 changelog:** CPO self-review (3 BLOCKERs + 5 IMPROVEMENTs + 3 POLISH) + CTO tech review (7 substrate + 3 architectural + 2 nits) folded in single pass. Resolutions:
- **B1 daily-cap value:** $50/day USD per-cabinet TOTAL (confirmed via captain-decisions.md 2026-05-20 13:58 UTC, not "0/day" — CoS relay had transcription error). Removes Open Question #1.
- **B2 currency commit:** proxy enforces cap in USD (denominated against Anthropic raw cost which is USD-billed); customer-facing dashboard displays USD-equivalent DKK (rate-locked at signup, refreshed weekly). Audit-log fields renamed `cost_raw_usd` + `cost_marked_up_usd` + `cap_usd` for proxy-side; customer-display layer translates to DKK.
- **B3 `confidence_low` hallucinated field removed:** Sonnet+Opus-advisor routing uses real mechanisms only — (a) officer-set `X-LLM-Preference: opus-advisor` request header, (b) LiteLLM config-level model routing by prompt-pattern matching, NOT a fabricated API field. Tool-call-depth trigger removed (LiteLLM can't observe; client-side state).
- **I1 margin markup decision:** 100% markup is correct default per derivable margin math ($50/day cap × 30 = $1500/mo Anthropic raw cost; min 25k DKK ≈ $3500 revenue → 133% gross margin pre-other-costs). CPO-resolved, not Captain-gated. Removes Open Question #2.
- **I2 Stripe Token Billing Phase 1:** ON (B1 resolution collapses track-but-don't-charge interpretation). Removes Open Question #3.
- **I3 state-file mismatch:** per-cabinet-per-day spend stored in Redis key `cabinet:proxy-spend:<cabinet-slug>:<yyyy-mm-dd>` (NOT `.claude/active-task.json` which is per-(officer, task)); separate substrate, separate concern.
- **I4 sub-processor DPA gate:** Anthropic-outage fallback to OpenAI/Gemini gated on FW-100 DPA template enumerating all 3 providers + customer signature at signup. Until FW-100 ships, fallback DISABLED (Anthropic-only routing); Anthropic outage = proxy-degraded state per AC #8.
- **I5 audit-log path clarification:** logs live on refslund.ai infra at `proxy/logs/audit/<cabinet-slug>.jsonl` (server-side, NOT customer-local). FW-097 substrate consumes via proxy admin API or direct log access.
- **POLISH P1:** calendar-time effort estimates removed from Phasing per CLAUDE.md AI-speed framing.
- **POLISH P2:** tool-call-depth Opus trigger removed (no LiteLLM-side mechanism).
- **POLISH P3:** Open Question #4 (sub-processor DPA list) stays — genuinely Captain-only legal call.

CTO tech-review fold:
- **CTO #1 deployment topology:** dedicated VPS (Hetzner Frankfurt EU OR Fly.io) — LiteLLM is long-running, not Lambda; Vercel serverless cold-starts unacceptable for streaming. Updated §Topology + §Dependencies.
- **CTO #2 99.9% SLA = ≥2 instances:** Phase 1 starts 1-instance with state in Redis cluster (2-instance-ready from day one). AC #8 SLA target preserved; Phase 2 ramps to 2-instance.
- **CTO #3 cap-tracking storage:** LiteLLM-managed Redis (Phase 1) → external Redis cluster (Phase 2). Per CTO #2, Redis from day one.
- **CTO #4 DKK conversion timing:** per-billing-cycle FX snapshot, NOT per-request. Proxy logs USD raw + DKK marked-up at cycle-start exchange rate; reconcile at month-end via Stripe Token Billing FX support. AC #5 updated.
- **CTO #5 tool-call-depth header injection:** officer-side `cabinet/scripts/lib/llm-routing.sh` injects `X-LLM-Preference: opus-advisor` headers based on agent-instructions.md `llm_routing` config + officer-side depth counter. Proxy never tracks per-session state; reads request headers only.
- **CTO #6 `confidence_low` workaround:** Phase 1 uses system-prompt-wrap asking model to self-classify uncertainty in structured output; flagged for Anthropic-partnership Phase 2 (if Anthropic ships native uncertainty signal). AC #11 updated.
- **CTO #7 proxy.refslund.ai DNS + TLS:** Cloudflare + origin VPS pattern (TLS via Cloudflare); deployed via FW-098 Phase 2 substrate.
- **CTO #8 Spec 049 dependency ordering:** extend `cabinet/scripts/migrate-active-task.sh` (per Spec 049 CTO #5 fold) to handle BOTH `proxyCostDkkToday` + `visualUatCost` incrementally. **Actually:** v2 moves `proxyCostDkkToday` to Redis (NOT state file) per CPO self-review I3; conflict resolved — no state-file collision with Spec 049.
- **CTO #9 provider-migration customer-impact:** FW-098 concierge runbook (commit a9fd5a8 v0.1) gets line: "During provider outages, your officer may briefly reset conversation context." Officer SHOULD self-detect provider switch via audit-log header + emit Captain-visible event.
- **CTO #10 no-direct-API-fallback validation:** FW-098 concierge runbook adds install-validation step: `grep -q ANTHROPIC_API_KEY cabinet/.env` must return FAIL (key absent in customer env). Only `LLM_PROXY_KEY` present.
- **CTO #11 cap-bump anti-abuse Redis counter:** `cabinet:capbump:<cabinet-slug>:<date>` INCR + 2× price multiplier on second bump. Folds into FW-099 Stripe integration.
- **CTO #12 sub-processor disclosure:** confirmed handled in CPO self-review I4 (FW-100 DPA gate on fallback enablement).
- **A13 absorption (Captain msg 2540+2565+2568 third-occurrence auto-encode, 2026-05-20 14:09 UTC):** "Don't seek permission from gatekeepers before you have leverage." Spec 051 v1 cited Anthropic-partnership outreach for native uncertainty signal; v2 removes that proposal — Cabinet ships under value-add carve-out interpretation + waits for organic leverage (5-10 paying customers + revenue + relationship) before vendor outreach. AC #11 updated accordingly.

---

## Problem

Cabinet's commercial launch requires three substrate primitives that don't exist today:

1. **Per-cabinet LLM access metering.** Today's cabinets call Anthropic API directly via Claude Code's built-in auth. Commercial customers need their LLM usage attributable to their cabinet + capped at a per-cabinet daily spend ceiling (per Captain msg 2565 — single ceiling across all officers in a cabinet, not per-officer).
2. **Margin on LLM token cost.** Captain's pricing model (25k DKK base + 5k DKK/employee, max 7 employees → 25k-60k DKK/mo range per cabinet) bundles LLM cost into the subscription. Cabinet pays Anthropic raw cost; customer pays Cabinet's marked-up rate. The margin model needs a proxy layer to intercept + mark up calls.
3. **Provider routing + fallback.** Captain msg 2540 ratified Sonnet+Opus-advisor model routing (Sonnet drives the loop, Opus only on hard subproblems — 80% cost cut). Provider routing also enables Anthropic-primary with OpenAI/Gemini fallback if a provider has an outage.

LiteLLM (open-source MIT-licensed proxy server, BerriAI; production-grade, mature) is the natural fit. Cabinet builds the integration; LiteLLM is the substrate.

## Solution

`refslund.ai/proxy` (LiteLLM proxy server hosted on Cabinet infrastructure) sits between officer Claude/OpenAI/etc. API calls and the actual provider. Each customer cabinet gets one virtual key issued at signup. Proxy enforces:

- Per-cabinet daily-spend cap: **$50 USD/day TOTAL per cabinet** (Captain msg 2565, captain-decisions.md 2026-05-20 13:58 UTC — RESOLVED, not pending; configurable at signup, this is the default ceiling)
- Per-cabinet audit log emitted to customer-audit substrate (FW-097)
- Margin markup on Anthropic raw cost (Cabinet's pricing model; transparent to customer in dashboard)
- Provider routing (Anthropic primary; OpenAI/Gemini fallback on Anthropic outage; Sonnet+Opus-advisor pattern per Captain msg 2540)

### Topology

```
Customer MacMini (cabinet)
    ↓ all LLM API calls via HTTPS (LLM_PROXY_KEY = sk-...)
proxy.refslund.ai (LiteLLM on Hetzner Frankfurt EU-resident VPS OR Fly.io)
    ↓ marked-up + routed + capped + audited (cap state in Redis cluster)
Anthropic API (primary) / OpenAI / Gemini (sub-processor fallback, FW-100 DPA-gated)
```

Proxy lives on refslund.ai infrastructure (NOT customer MacMini) — critical for margin enforcement: customer can't bypass proxy by editing local config. Customer's cabinet `.env` has ONLY the virtual key (`LLM_PROXY_KEY=sk-...` + `ANTHROPIC_API_BASE=https://proxy.refslund.ai/v1`); real Anthropic API key never leaves refslund.ai.

**Deployment topology (resolves CTO #1+#2+#3+#7):**
- **VPS NOT Vercel serverless** — LiteLLM is long-running server, not request-response Lambda. Cold-starts (100-500ms per cold request) unacceptable for streaming. LiteLLM docs explicitly recommend VPS/K8s.
- **Hetzner Frankfurt EU-resident OR Fly.io** — both EU-resident options; Phase 1 picks ONE.
- **Redis cluster for cap-tracking state from day 1** — Phase 1 starts 1-instance with state in Redis (2-instance-ready from day 1; Phase 2 ramps to 2-instance for 99.9% SLA per AC #8).
- **DNS + TLS:** Cloudflare + origin VPS pattern (TLS via Cloudflare).

**Phase 2 substrate architecture ratification (per A12 officer-in-loop on architecture, CTO request 2026-05-20 22:29 UTC):** Hetzner Frankfurt vs Fly.io pick is an architecture call requiring CTO ratification before Phase 2 substrate build kickoff. Default recommendation: **Hetzner Frankfurt** (cheaper, simpler VPS model, true EU-resident with no US-mirror routing; Fly.io has EU regions but US-parented org adds slight third-country-transfer surface). CTO ratifies via standalone trigger before Phase 2 entry; CPO accepts CTO architecture authority per A12 (officer-in-loop on architecture — CTO domain).

### Virtual-key model

**One virtual key per cabinet, NOT per (cabinet, officer).** Rationale per Captain msg 2565: "Cap: 0/day per cabinet TOTAL across all officers (not per-officer; whole-cabinet ceiling)." Single virtual key simplifies cap enforcement + audit attribution. Officer identity carried in request metadata (LiteLLM custom metadata field) for audit-log granularity.

Virtual key issued at customer signup via FW-099 (refslund.ai signup + Stripe Token Billing). Key persists for cabinet lifetime; rotation on customer request OR security incident.

### Provider routing + Sonnet+Opus-advisor

Default routing per request:
1. **Sonnet 4.6** as primary execution model (cost-optimized per Captain msg 2540 — 80% cheaper than Opus 4.7)
2. **Opus 4.7 advisor escalation** when Sonnet returns confidence-low signal OR officer-config explicitly requests Opus for hard subproblems
3. **OpenAI GPT-X / Gemini fallback** ONLY on Anthropic provider outage (HTTP 503 / rate-limit cascade); falls back to nearest-quality model per LiteLLM provider-mapping config

Routing logic configurable per officer in `.cabinet/agent-instructions.md → llm_routing` (default + per-officer overrides). Provider preference cascade is the substrate-default; officers can pin to Opus for known-hard tasks.

### Cap enforcement

- **Daily cap:** **$50 USD per-cabinet TOTAL across all officers** (Captain msg 2565 ratification per captain-decisions.md 2026-05-20 13:58 UTC; NOT per-officer, NOT DKK-denominated proxy-side). Customer dashboard displays USD-equivalent DKK (FX rate-locked at signup, refreshed weekly). Resets at 00:00 UTC each day.
- **Storage:** Redis key `cabinet:proxy-spend:<cabinet-slug>:<yyyy-mm-dd>` (INCRBY on each request; expires 7 days post-date for audit-window retention). State in Redis cluster (NOT `.claude/active-task.json` which is per-(officer, task) and lives in customer's local repo — wrong scope for per-cabinet-per-day spend).
- **Soft warning at 80% ($40 USD):** customer dashboard surfaces "cap-approach" yellow indicator; CoS notified via `notify-officer.sh cos "<cabinet> cap at 80%"`; officer sessions emit `CAP_APPROACH` event (reuse Spec 049 event chain).
- **Hard block at 100% ($50 USD):** proxy returns HTTP 429 with structured payload `{"error": "daily-cap-exceeded", "resets_at": "<iso>", "cap_usd": 50, "spent_usd": 50.04, "cap_dkk_display": <fx-converted>}`; officer sessions emit `CAP_HIT` event + block tool calls; customer dashboard surfaces "cap-exceeded" banner with "Bump cap one-shot OR wait until reset" CTA.
- **Cap bumps:** customer-initiated via customer dashboard → Stripe one-shot charge → cap raised for current day only. Anti-abuse: Redis counter `cabinet:capbump:<cabinet-slug>:<yyyy-mm-dd>` INCR per bump; second bump same day = 2× price multiplier (per CTO #11). Appended to FW-097 audit log + (if cumulative-bump-USD >$25 USD OR second-bump-same-day) `shared/interfaces/captain-decisions.md` per Spec 049 §cost-cap-audit pattern. **Threshold $25 USD** = CPO v4 fold compromise mid-point between Spec 049 per-task $10 + prior-spec-051 $100; pending Captain X1 ratify in morning briefing (per CRO X1 finding). Threshold configurable in agent-instructions.md cap-bump-audit-threshold key.

### Audit log emission (integrates with FW-097)

Every proxy request emits JSONL to `cabinet/logs/proxy-audit/<cabinet-slug>.jsonl` with:

```json
{
  "ts": "2026-05-20T14:30:00Z",
  "cabinet_id": "<cabinet-slug>",
  "officer": "<officer-slug>",
  "request_id": "<uuid>",
  "model": "claude-sonnet-4-6",
  "provider": "anthropic",
  "tokens_in": 1234,
  "tokens_out": 567,
  "cost_raw_usd": 0.42,
  "cost_marked_up_usd": 0.84,
  "margin_pct": 100,
  "cap_remaining_dkk": 4998.16,
  "cap_pct_used": 16.7
}
```

FW-097 substrate consumes this stream for customer audit-trail + retro analytics. Customer dashboard (FW-101) queries last-N-day aggregates from this log.

---

## Acceptance criteria

1. **Virtual-key issuance AC** — at customer signup (FW-099), refslund.ai backend calls LiteLLM proxy admin API to mint one virtual key per cabinet. Key stored encrypted in cabinet's `refslund.ai customer record` (server-side); never exposed in plaintext to customer. Cabinet MacMini install (FW-098) injects key into customer's `cabinet/.env` as `LLM_PROXY_KEY=sk-...` + sets `ANTHROPIC_API_BASE=https://proxy.refslund.ai/v1`.

2. **Per-cabinet daily-cap config AC** — daily cap stored as USD-denominated integer cents in Redis key `cabinet:proxy-spend:<cabinet-slug>:<yyyy-mm-dd>` (NOT in customer record; NOT in `.claude/active-task.json`). Default cap = $50 USD per Captain msg 2565 ratification (captain-decisions.md 2026-05-20 13:58 UTC). Cap resets at 00:00 UTC daily via LiteLLM scheduled job (Redis key TTL expires). Cap configurable per-cabinet at signup (Phase 1 = default $50 only; Phase 2 self-serve allows custom tier-tied caps). Bump-able by customer via Stripe one-shot per AC #3.

3. **Cap-hit behavior AC** (v5 currency-align per CoS B1) — at 80% cap: proxy adds `X-Cap-Warning: <pct>` response header; FW-101 customer dashboard surfaces yellow indicator; CoS receives notify-officer alert. At 100% cap: proxy returns HTTP 429 with body `{"error": "daily-cap-exceeded", "resets_at": "<iso>", "cap_usd": 50, "spent_usd": <float>, "cap_dkk_display": <fx-converted-int>, "spent_dkk_display": <fx-converted-float>}`; officer Claude Code sessions interpret 429 as a hard-stop + emit `CAP_HIT` event per Spec 049; customer dashboard surfaces red banner + bump CTA. USD-denominated proxy-side (cap enforcement + audit-log emission); DKK customer-display fields ONLY for dashboard render (FX rate-locked at signup, refreshed per-billing-cycle per CTO #4).

4. **Provider routing AC** — every request defaults Sonnet 4.6 (Captain msg 2540 cost-optimization). Officer config overrides routed via Claude Code request metadata `X-LLM-Preference: opus-advisor` (forces Opus) or `X-LLM-Preference: sonnet-only` (denies Opus escalation). Anthropic provider outage (HTTP 503 OR rate-limit cascade ≥3 retries) triggers fallback to OpenAI GPT-X or Gemini per LiteLLM provider-mapping config. Fallback logged as `provider: openai-fallback` in audit-log entry.

5. **Margin enforcement AC** — proxy applies markup configurable in `proxy/config.yaml → margin_pct` per-model. Default markup = 100% (customer pays 2× Anthropic raw cost) per derivable margin math: $50/day cap × 30 = $1500/mo Anthropic raw cost; min revenue 25k DKK ≈ $3500/mo → 133% gross margin pre-other-costs. Markup transparent in audit-log entry (`cost_raw_usd` + `cost_marked_up_usd` + `margin_pct` fields, USD-denominated per CTO #4). Customer dashboard shows `cost_marked_up_usd` AND its FX-converted DKK display (rate-locked at signup, refreshed weekly per CTO #4 per-billing-cycle FX timing). Raw cost is internal.

6. **Audit-log emission AC** — every proxy request produces a JSONL line per schema above to `cabinet/logs/proxy-audit/<cabinet-slug>.jsonl`. Log retained per FW-100 GDPR baseline retention policy (default 90 days hot, 7 years cold archive for billing reconciliation). FW-097 substrate consumes this stream for customer-facing audit-trail surface.

7. **Customer dashboard visibility AC** — FW-101 dashboard queries proxy-audit JSONL aggregated by day. Shows: today's spend (DKK), cap remaining (DKK), cap-pct-used progress bar, last-7-days trend chart, per-officer breakdown table.

8. **Failure modes AC** — proxy unavailable (refslund.ai infra outage) → cabinet's Claude Code sessions fail with structured error `{"error": "proxy-unavailable", "retry_in_s": <int>}`; officer sessions enter "proxy-degraded" state + emit `PROXY_DOWN` event; CoS receives high-priority alert. **NO direct-API fallback** (would bypass margin + cap); cabinet waits for proxy recovery. SLA target: 99.9% uptime; sub-30s detection + alert.

9. **Cost computation + Stripe Token Billing integration AC** — daily proxy-audit JSONL totals fed to Stripe Token Billing meter daily at 00:05 UTC. Stripe meter ID per cabinet stored in customer record. Monthly Stripe invoice generated from meter; included in 25k DKK base + 5k DKK/employee subscription. Token consumption above included quota billed as overage. Specifics in FW-099 Stripe integration spec.

10. **Auth + key rotation AC** — virtual keys signed per LiteLLM standard. Rotation triggers: (a) customer-initiated via dashboard, (b) security incident detected (compromised key in audit log — known patterns), (c) every 12 months mandatory rotation. Rotation flow: mint new key, push to customer MacMini via refslund.ai control channel, customer cabinet receives + reloads `.env` (cabinet/scripts/rotate-llm-key.sh handles), old key revoked after 24h overlap grace period.

11. **Sonnet+Opus-advisor routing AC** (resolves self-review B3 + CTO #5+#6) — Sonnet 4.6 is default model for officer requests. Opus 4.7 invocation triggers, in priority order:
    - **(a) Officer-config explicit `X-LLM-Preference: opus-advisor` request header** — set by officer-side `cabinet/scripts/lib/llm-routing.sh` based on `.cabinet/agent-instructions.md → llm_routing` config (per-officer overrides; tool-call-depth tracked client-side, header injected by officer Claude Code session when depth ≥3 OR per agent-instructions threshold).
    - **(b) System-prompt-wrap self-classified uncertainty** (Phase 1 workaround for absence of Anthropic-native uncertainty signal) — Sonnet's system prompt asks model to emit structured output `{"uncertainty": "low|medium|high"}` per response. LiteLLM extracts the field; if `"high"` AND no opt-out flag set, retry request with Opus 4.7. Phase 2 may swap to Anthropic-native signal IF Anthropic ships one publicly. **Per A13 (don't seek permission from gatekeepers before you have leverage): Cabinet does NOT initiate Anthropic partnership outreach for native-signal access — we ship under value-add carve-out interpretation + wait for organic leverage (5-10 paying customers + revenue + relationship) before any vendor outreach.**
    
    **Proxy NEVER tracks per-session state** (CTO #5) — all routing signals arrive via request headers OR response payload. Opus invocation logged separately for cost-attribution analytics; Captain receives weekly Opus-usage summary per cabinet in morning briefing.

12. **Test harness AC** — `cabinet/tests/test-litellm-proxy.sh` covers: virtual-key issuance + injection into MacMini env; per-cabinet daily-cap enforcement (mock-clock advance + ledger check); cap-warning at 80% triggers correctly; cap-hit at 100% returns 429 with correct payload; Anthropic outage → OpenAI fallback; margin markup applied per audit-log; proxy-unavailable failure surfaces structured error; key rotation flow end-to-end. ≥10 assertions.

13. **Spec 049 coexistence AC** — Spec 049 §cap-event-chain (`CAP_APPROACH` / `CAP_HIT` events with structured payload, cost-cap > token-cap priority) reused for FW-096 cap-hit handling. No duplicate event-emission; FW-096 cap-hit events flow through Spec 049 event chain. State-file (`.claude/active-task.json → visualUatCost`) gets new sibling field `proxyCostDkkToday` populated from proxy-audit log.

---

## Edge cases

- **Cap-bump immediately followed by another cap-hit** — customer bumps cap to $X then immediately exceeds new ceiling. Proxy enforces new ceiling; second bump in same day requires 2× the bump fee (anti-abuse). FW-099 Stripe integration handles billing.
- **Provider migration mid-request** — Anthropic outage hits mid-conversation; LiteLLM provider-mapping resolves to OpenAI fallback. Conversation context may not transfer cleanly (different system-prompt formats). Spec recommends: officer sessions handle fallback as new turn, not in-conversation continuity. Audit-log entry flags `provider_migration: true` for retro analysis.
- **Virtual key compromised** — if proxy detects suspicious patterns (sudden 100x rate, geo-shift, unusual model-mix) per LiteLLM security guards, key auto-rotated; customer notified via dashboard + email; cap frozen pending investigation. CoS notified high-priority.
- **Cabinet cabinet-bootstrap fails after key issued** — virtual key minted but MacMini install (FW-098) fails. Key remains in idle state; refslund.ai customer-success follows up. Stripe billing pauses (no consumption charged). Retry MacMini install OR refund per FW-099 cancellation flow.
- **Sub-processor disclosure on Anthropic outage fallback** — falling back to OpenAI or Gemini changes sub-processor list mid-flight. Per FW-100 GDPR baseline, customer DPA must list ALL potential providers (Anthropic + OpenAI + Gemini) at signup. Fallback is not a new sub-processor introduction; pre-disclosed.
- **Cap-hit during officer Captain-attention payload** — officer mid-composing a Captain-attention reply when cap hits at 100%. Reply queued (Spec 034 v3 AC #74 single_ceo CEO escalation queue); officer notifies customer via dashboard; customer bumps cap to unblock. CoS handles communication.
- **0/day cap interpretation (Captain msg 2565 wording)** — if "0/day" literally means zero spend (track-but-don't-charge pilot mode), Phase 1 customers pay subscription only, all LLM cost absorbed by Cabinet. Acceptable for pilot per Captain's concierge approach. Cap setting "0" means proxy passes through without billing meter; audit-log still emits. Need Captain explicit ratification — see Open Questions.

---

## Open questions for Captain ratification

CPO self-review + captain-decisions.md cross-reference + A13 absorption resolved 3 of the original 4 Open Questions. Q1 RESOLVED via Captain msg 2583 cross-spec ratification (2026-05-20 22:26 UTC):

1. ~~Provider fallback sub-processor list ratification~~ → **RESOLVED: Anthropic-only Phase 1.** OpenAI + Gemini fallback DISABLED per Captain msg 2583 (Spec 055 Q5 + FW-096 Q1 same ratification). Anthropic outage = proxy-degraded state per AC #8 (no fallback, customer notified). Re-evaluation at 5+ paying customers per CoS DPO+counsel risk-class trigger.

**Self-resolved (no Captain ratification needed):**
- ~~Daily-cap actual value~~ → $50 USD per Captain msg 2565 ratification (captain-decisions.md 2026-05-20 13:58 UTC; CoS relay had transcription error)
- ~~Margin markup default~~ → 100% per derivable margin math (CPO I1 fold)
- ~~Stripe Token Billing on/off Phase 1~~ → ON per B1 resolution collapse (CPO I2 fold)
- ~~Anthropic-partnership outreach for native uncertainty signal~~ → DROPPED per A13 (don't seek permission from gatekeepers before leverage; wait for 5-10 paying customers + revenue + relationship)

CoS routes Q1 to Captain alongside FW-100 DPA template ratification (FW-100 priority 2 in CoS Phase 1 batch).

---

## Dependencies

- **CTO substrate:** LiteLLM proxy on Hetzner Frankfurt EU-resident VPS OR Fly.io (CTO architecture pick at Phase 2 entry). Redis cluster from day 1 (cap-tracking state). Provider API keys (Anthropic primary; OpenAI + Gemini wired but inactive pending FW-100 DPA + Captain Q1 ratification) stored in proxy server env, never customer-side. LiteLLM config at `proxy/config.yaml` covering provider routing + margin markup + cap enforcement. Cloudflare DNS + TLS via origin VPS.
- **CTO substrate:** customer MacMini install (FW-098 v0.1 commit a9fd5a8) sets `ANTHROPIC_API_BASE=https://proxy.refslund.ai/v1` + `LLM_PROXY_KEY=<virtual-key>` in cabinet `.env` via concierge install script. **Install-validation step:** `grep -q ANTHROPIC_API_KEY cabinet/.env` MUST return FAIL (raw Anthropic key absent in customer env). Only `LLM_PROXY_KEY` present.
- **CTO substrate (new per CTO #5):** officer-side helper `cabinet/scripts/lib/llm-routing.sh` injects `X-LLM-Preference` headers based on `.cabinet/agent-instructions.md → llm_routing` config + officer-side tool-call-depth counter. Proxy reads request headers only; no per-session state proxy-side.
- **CTO substrate (new per CTO #11):** Redis counter `cabinet:capbump:<cabinet-slug>:<yyyy-mm-dd>` + 2× price multiplier on second bump per day (anti-abuse). Folds into FW-099 Stripe integration.
- **FW-097 dependency:** customer audit-log substrate consumes proxy-audit JSONL stream at refslund.ai `proxy/logs/audit/<cabinet-slug>.jsonl`.
- **FW-098 dependency:** concierge install runbook (v0.1 commit a9fd5a8) carries install-validation step + provider-migration customer-doc line ("During provider outages, your officer may briefly reset conversation context.").
- **FW-099 dependency:** Stripe Token Billing meter wired to per-day audit-log aggregates; virtual-key issuance triggered by Stripe signup completion webhook; cap-bump charges via one-shot Stripe payment.
- **FW-100 dependency:** GDPR DPA template enumerates Anthropic + OpenAI + Gemini as sub-processors at signup; customer signs DPA before key issuance. **Phase 1 ships with Anthropic-only routing UNTIL FW-100 lands** — fallback to OpenAI/Gemini disabled until DPA covers them + Captain Q1 ratifies.
- **FW-101 dependency:** customer dashboard reads proxy-audit JSONL aggregates for spend visibility (USD primary + DKK display per AC #5 per-billing-cycle FX).
- **Spec 049 dependency (state-file conflict resolved per CPO I3 + CTO #8):** per-cabinet-per-day spend stored in Redis (`cabinet:proxy-spend:<cabinet-slug>:<yyyy-mm-dd>`), NOT in `.claude/active-task.json`. No state-file collision with Spec 049. Cap-event-chain (`CAP_APPROACH` / `CAP_HIT` structured events) reused.
- **CoS coordination:** Captain ratification of Q1 sub-processor list (only remaining Open Question post self-review + CTO + A13 fold) before AC #4 fallback enablement.

---

## Out of scope

- **Custom model fine-tuning per customer** — Phase 2. Phase 1 uses stock Anthropic + OpenAI + Gemini models.
- **Multi-region provider routing** (EU vs US data residency for Anthropic API) — Phase 2 "EU-resident GDPR-native" positioning per Captain msg 2565 Phase 2 trigger. Phase 1 uses Anthropic default routing.
- **Customer-supplied API keys (BYOK)** — Phase 2 option. Phase 1 always uses Cabinet's virtual-key model.
- **Real-time WebSocket cap-status streaming** — Phase 2 polish. Phase 1 customer dashboard polls daily-aggregate every 60s.
- **Provider cost-arbitrage** (route to cheapest provider per request) — Phase 2. Phase 1 routing is quality-first (Anthropic primary), not cost-first.
- **Custom prompts injected by Cabinet at proxy layer** — explicitly excluded for trust + transparency reasons. Proxy is request-routing only; no prompt mutation.

---

## Phasing

Phase-gated (not calendar-time per CLAUDE.md AI-speed framing). Phases marked `║` parallelize after prior phase clears.

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | ~~Captain ratification of Q1 sub-processor list~~ → **RESOLVED Captain msg 2583 Q5 cross-spec ratification — Anthropic-only Phase 1, OpenAI+Gemini fallback DISABLED.** No remaining Open Questions on Spec 051. | n/a (resolved) | ✓ Phase 1 unblocked |
| 2 | LiteLLM proxy deploy on Hetzner Frankfurt VPS (or Fly.io) + Redis cluster + provider keys + config.yaml + Cloudflare TLS | v2 LANDED | Proxy live at proxy.refslund.ai/v1 with passing healthcheck |
| 3 ║ | Virtual-key admin API + customer-record schema + key-rotation script | Phase 2 GREEN | Key mint + rotation manual-tested end-to-end |
| 4 ║ | Per-cabinet daily-cap enforcement ($50 USD ceiling) + cap-event integration with Spec 049 event chain + Redis spend-tracking keys + cap-bump anti-abuse counter | Phase 2 GREEN | Mock-clock test passes; cap-warning + cap-hit events flow; bump 2× pricing works |
| 5 ║ | Audit-log JSONL emission + retention policy + FW-097 integration | Phase 2 GREEN | Audit-log entries verified per schema; FW-097 consumes |
| 6 ║ | Provider routing + Sonnet+Opus-advisor + system-prompt-wrap uncertainty self-classify + officer-side `cabinet/scripts/lib/llm-routing.sh` header-injection helper | Phase 2 GREEN | Sonnet+Opus-advisor verified; uncertainty signal triggers Opus retry; OpenAI/Gemini fallback wired but DISABLED until Q1+FW-100 clear |
| 7 ║ | Customer dashboard wiring (read-only Phase 1 spend visibility — USD + DKK display) | Phase 2 GREEN, couples to FW-101 | Dashboard shows today's spend + cap-remaining + 7-day trend |
| 8 | Test harness `cabinet/tests/test-litellm-proxy.sh` (≥12 assertions) | Phases 3, 4, 5, 6, 7 GREEN | All assertions passing in CI |
| 9 | End-to-end pilot: one Phase 1 customer cabinet provisioned through full proxy flow | Phase 8 GREEN + FW-098 install runbook + FW-099 Stripe signup + FW-100 DPA + FW-101 dashboard MVP | Customer logs in; Telegram DMs reach officers; spend visible in dashboard |

**Critical path:** v2 LANDED → Phase 2 (proxy deploy) → Phases 3-7 parallel-friendly → Phase 8 test → Phase 9 e2e pilot (multi-spec dependency chain). 5 of 8 phases parallelize after Phase 2 substrate base.

---

## Review process

1. **CoS architecture review** — proxy topology + auth + key-rotation flow + Stripe Token Billing integration (couples to FW-099).
2. **CTO tech review** — LiteLLM deployment architecture (Vercel serverless vs dedicated VPS), config.yaml schema, provider-mapping design, cap-enforcement implementation discipline.
3. **CRO adversary review** — Stagehand-grade adversarial-input audit: virtual-key brute-force surface, cap-bump abuse patterns, provider-fallback information disclosure, audit-log PII leak vectors.
4. **COO adversary review** — multi-failure-mode interaction: proxy down + cap-hit + provider outage simultaneously; what breaks for officer sessions + customer dashboard + audit log.
5. **CPO self-spawned review subagent** — fresh-context audit before commit (per [Review Before Commit] discipline; will run pre-CoS-route).

Iterate until all 5 reviewers ack. Captain ratification on the 4 Open Questions BEFORE CTO build starts.

---

**v1 LANDED 2026-05-20 14:30 UTC** (CPO authored under CoS Phase 1 unblock 14:00 UTC). CPO self-spawned review queued next.
