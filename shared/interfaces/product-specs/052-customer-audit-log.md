# Spec 052: Customer Audit Log — Append-Only Activity Log with Hash-Chain Integrity + GDPR Article 15 Export (FW-097 Phase 1 Priority 3)

**Version:** v3.8 (AC #10/#12 — #237 write-side ingest coverage: every cabinet_id→path site guarded at the ingest-entry chokepoint + Python `\Z` anchor) — v3.7 superseded
**v3.8 changelog — #237 write-side ingest path-validation pinned (PR #112 Opus-substitute pass, 2026-05-26):** verifying the merged #236 fix (1cb21d8) confirmed the GET path-param guard (`app.py:248`) + POST-body validator (`app.py:157`) cover the audit-server ENDPOINTS — but the call-graph trace surfaced that the FW-097 INGEST path builds three more `cabinet_id`→filesystem paths from a slug that bypasses those validators (slug = `ingest.py:194 jsonl_file.stem`): `_cursor_path` (`.cursors/<slug>.cursor`, ingest.py:64), the `proxy-audit/<slug>.jsonl` read path (ingest.py:141), and `hashchain._ssot_path` (`audit/<slug>.jsonl`). A chokepoint placed only at `hashchain._ssot_path` (CTO's stated #237 plan) covers the SSOT write but MISSES `_cursor_path` + the proxy-audit read path — so AC #10 now states the GENERAL invariant (every `cabinet_id`→path construction is slug-guarded) and pins the single covering chokepoint at `ingest_slug`-entry (ingest.py:135). Severity is LOW today (the glob `.stem` source is filesystem-constrained, so `../` is not reachable via `ingest_all`), but defense-in-depth + future-caller safety make it a pre-go-live gate. Also pinned the Python anchor caveat (the Opus pass's one MEDIUM, folded in `app.py:102`): Python slug-validators MUST use `re.fullmatch`/`\Z`, not `$` (which matches before a lone trailing `\n`). #236 + M-DPO-2 conformance VERIFIED (config.yaml:93 `log_requests: false`; app.py `\Z` + both guards).
**v3.7 changelog — #236 cabinet_id format-validation pinned (FW-121 DPO-substitute pass, 2026-05-26):** the DPO-substitute pass found the audit-server builds filesystem paths from a caller-supplied `cabinet_id` on BOTH the `GET /dashboard/audit/{cabinet_id}/...` path param AND the `POST /proxy/audit/log` body, with no FORMAT validation — a path-traversal/injection surface (`cabinet_id = "../../etc"`), distinct from and ORTHOGONAL to AC #10's key→cabinet authorization (FW-120 binds the key to a cabinet; this validates the cabinet_id STRING shape before any path is built). AC #10 + AC #12 now require slug-format validation (reuse the `customer-erasure.sh` slug regex) on BOTH endpoints, rejecting any non-conforming `cabinet_id` before path construction. HARD pre-go-live gate (CTO/FW-097 builds it as a focused fix; orthogonal to the FW-120 Phase-2 key-scoping gate — both required, neither replaces the other).
**v3.6 changelog — path-pin wording corrected (FW-121 PR #108 review, 2026-05-25):** the FW-121 docker-compose exposed that my v3.2 path-pin phrasing ("both sides resolve the SAME `LITELLM_AUDIT_LOG_ROOT` env var") was imprecise + dangerous-if-followed-literally. FW-096 (producer) interprets the env as the proxy-audit DIR (writes `<root>/<slug>`); FW-097 (consumer) interprets it as the PARENT (reads `<root>/proxy-audit/`, writes SSOT `<root>/audit/`). So the deploy MUST set the producer value one level DEEPER than the consumer (producer = `<consumer-root>/proxy-audit`), NOT equal — setting them literally equal breaks the ingest. The FW-121 compose got it right (litellm=/data/logs/proxy-audit, audit/ingest=/data/logs); the deploy is the authoritative reference + the §Solution input-stream-1 wording now matches it. (Lesson: a cross-component env-var contract needs the deploy to validate the spec's interpretation — the deploy caught my "same value" imprecision.)
**v3.5 changelog — allow-list parity guard codified (2026-05-25):** the #234 validator.py allow-list closed the client/server defense-in-depth parity (both fail-closed now). CPO review flagged the residual: the two allow-lists (`audit-emit.sh _AUDIT_ALLOWED_KEYS` + `validator.py _ALLOWED_METADATA_KEYS` officer-subset) are DUPLICATED with a manual "keep in sync" comment → silent-drift risk (a server stripping a client-emitted key = silent loss of a field from the customer's GDPR trail). CTO shipped the enforcement (7c9075e PR #107, test-customer-audit-log.sh §17): a one-sided edit on either list FAILS the harness. AC #12 now REQUIRES that parity assertion, codifying the now-enforced invariant. (Pattern: a contract duplicated across two artifacts needs an automated cross-check, not a comment.)
**v3.4 changelog — Spec 052 Ph5 review fold (2026-05-25):** the officer-side audit producers (`audit-emit.sh` + post-tool-use/post-reply hooks + the preset-driven grant reader) merged bafb9a8 (PR #105), reviewed APPROVED + GDPR-safe. AC #3 amended to require the minimization model be **ALLOW-LIST (fail-closed), not deny-list** — the 2 Opus PII-adversary rounds found a deny-list leaks nested/case-variant/arbitrary free-text keys; the merged client producer is correctly allow-list (the primary guarantee). Added follow-up: harden the server-side `validator.py` backstop to allow-list for defense-in-depth parity (task #234, CTO/FW-097). NOT a customer-#1 blocker (client allow-list is primary + solid — producers cannot send past it). Capability gate verified fail-safe (defaults OFF, non-commercial silent); grant reader verified against the `refslund-commercial` preset.yml `capability_grants` contract.
**v3.3 changelog — FW-097 PR #100 review folds (2026-05-24):** two AC gaps the review surfaced against the built code. **AC #8 (erasure):** the spec defined `pseudonym_marker_hash` but never *required* verifying it; the build (correctly) preserved entry_hash + skipped its recompute for pseudonymized entries, but then never checked the marker either → post-erasure content-tampering of an erased entry is undetectable (the marker was dead). AC #8 now mandates the marker recompute+compare as a distinct content-integrity check (ii), separate from chain-linkage (i); AC #9 browser-verifier likewise. **AC #10 (access control):** corrected the credential from `LLM_PROXY_KEY` to the separate `AUDIT_API_KEY` (CTO #5) and pinned the Phase-1 isolation model — the GET endpoint trusts the caller-supplied `cabinet_id`, so Phase-1 safety = backend-mediation (customer never holds the key); per-cabinet key scoping is a HARD GATE before customer #2 (flagged to CoS/COO-as-DPO as an onboarding gate). **AC #12 (test harness)** now requires the AC #8(ii) marker-tamper regression test (tamper a pseudonymized entry → verify() must flag it) + splits the cross-tenant test by phase (Phase-1 backend-mediation/bad-key-reject; Phase-2 key-A-rejected-on-B per FW-120). Substrate APPROVED for the 1-customer pilot once the AC #8(ii) marker-check + the app.py docstring honesty-fix land pre-merge.
**v3.2 changelog — proxy-audit input path-pin (CTO FW-097 pre-build cross-spec, 2026-05-24):** pinned input stream #1 to read from `proxy/logs/proxy-audit/<slug>.jsonl` via the `LITELLM_AUDIT_LOG_ROOT` env the merged FW-096 `audit_logger.py` writes (ce61fca) — both sides MUST resolve the same env var or the FW-097 sidecar ingests an empty stream. Captured CTO build-detail B: the sidecar transforms each FW-096 per-request emit into a 052 entry; FW-096-only fields `request_pct_of_cap` + `status` have no 052 slot → drop or carry as metadata. Also fixed the SSOT-path straggler in §Solution (`refslund.ai/logs/audit/` → `refslund.ai/proxy/logs/audit/` per v3 B2 global rewrite) and made explicit that the SSOT (`proxy/logs/audit/`) is distinct from the raw producer (`proxy/logs/proxy-audit/`). Spec 051 v7.1 pins the matching producer side. Server code + hash-chain + validator + harness are buildable-now on this pin; sidecar deploy is Phase-2 Hetzner-gated.
**v3.1 changelog — COO-as-DPO ratification propagated (decision-propagation-audit, 2026-05-24):** Spec 055 H1 ratified COO-as-DPO (Captain msg 2737, FW-114 applied, Spec 055 now v7.3 with the entire legal track closed), but Spec 052's live references still said "DPO currently CoS pending Spec 055 v4 H1 ratification" in 4 places — Owner line, AC #6 (Article 15 email routing), AC #10 (cross-cabinet access control), and the CoS-coordination dependency. The FW-097 audit-log build would have routed Article 15 requests + admin access-grants to the wrong owner. Fixed all 4 to COO-as-DPO (Spec 055 v7.1 H1). AC #10 additionally notes the DPO=COO dual-role collapse and preserves the Captain access-grant ratification as the independent second control for cross-cabinet access (separation-of-duties retained). Caught by a version-cite sweep across the Phase-1 commercial spec set (050-056).
**v3 changelog:** CoS architecture review surfaced 3 BLOCKERs + 2 IMPROVEMENTs + 1 POLISH. Resolutions:
- **CoS B1 A11 dual-home:** customer audit log IS compliance artifact (Article 30 ROPA + Article 15 access + erasure-runbook integration). v3 explicitly dual-homes: **operational hot store** at `refslund.ai/proxy/logs/audit/<cabinet-slug>.jsonl` (runtime substrate per Spec 051) + **Library Compliance Space** as record-of-record (Article 15 tickets + signed delivery receipts + hash-checkpoint provenance). AC #6 + #11 updated; ticket lifecycle owned by Library Compliance Space record class (parallel to Spec 055 v5 SSOT fix).
- **CoS B2 path inconsistency global rewrite:** Spec 051 owns upstream substrate; its `/proxy/` path wins. v3 rewrites all sites — line 39 + AC #1 + line 130 + line 140 + Spec 051 wiring — to `refslund.ai/proxy/logs/audit/<cabinet-slug>.jsonl` consistently.
- **CoS B3 cross-spec contradiction with Spec 055 erasure step 5:** Spec 055 v5 Article 17 erasure runbook step 5 says "audit log entries scrubbed"; Spec 052 AC #8 says "pseudonymization (NOT deletion) preserving entry_hash via second-layer pseudonymization-marker hash field." Two specs contradicted. **Resolution:** Spec 055 v6 fold lands in parallel to replace "scrubbed" with "pseudonymized per Spec 052 AC #8 two-hash-field schema." This Spec 052 v3 references the Spec 055 v6 fold + ratification cascades through both specs.
- **CoS I1 narrative-bridge:** new Problem-section paragraph clarifies officer-side `cabinet/logs/` stays on customer MacMini (ephemeral, customer-owned, A2 "your MacMini your data" honored); customer-facing audit log lives on refslund.ai because integrity guarantees + Article 15 access + cross-cabinet hash-checkpoint publication require server-side authority. Removes anticipated Captain-facing confusion.
- **CoS I2 framework-hook change capability:** Phase 5 introduces new officer-side `emits_customer_audit_events` capability via `cabinet/scripts/hooks/post-tool-use.sh + post-reply.sh` extending role-defs in `presets/*/agents/*.md` + `cabinet/officer-capabilities.conf` schema extension. CPO+CoS coordinate role-def + capabilities.conf addendum (cross-officer ticket, separate from Spec 052 v3 body). Phasing Phase 5 updated with explicit framework-level capability callout.
- **CoS P1 hash-chain + erasure-safe pseudonymization novel pattern:** post-ship CoS adds memory/skills/ foundation entry "Hash-chain integrity + erasure-safe pseudonymization" (CoS-owned post-v3-ship). Marker for memory-promotion workflow.

**A12 + A13 both preserved cleanly.** Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing.

**v2 prior changelog preserved below** (CTO tech review fold).
**v2 changelog:** CTO tech review surfaced 11 findings (7 substrate + 3 architectural + 1 cross-spec). All folded:
- **CTO #1 sha256 LOCKED** — Web-Crypto API browser-verifier (AC #9) needs sha256; blake3 perf moot at log-entry size; sha3 quantum-safe irrelevant threat model. Open Q1 resolved.
- **CTO #2 sidecar architecture LOCKED** — separate `refslund-audit-server` (FastAPI or Express) on Hetzner VPS, NOT LiteLLM custom Python callback. Clearer separation of concerns + independent scaling + cleaner GET endpoints + simpler auth boundary. Same VPS as LiteLLM proxy; behind nginx/Caddy reverse-proxy on separate port.
- **CTO #3 append-only inverted** — app-layer enforcement PRIMARY (sidecar refuses non-append ops; sidecar runs as non-root `audit` user); chattr +a defense-in-depth SECONDARY (root cron at install-time). Removes "audit-server runs as root" privilege concern. AC #7 updated.
- **CTO #4 hash-chain breakage detection latency** — daily 00:05 UTC checkpoint + per-100-entries milestone checkpoint (whichever first). Lightweight; ~1KB checkpoint per 100KB log; negligible Git-mirror overhead. Reduces tampering-detection window from 24h to <100-entries-per-cabinet. AC #2 updated.
- **CTO #5 separate AUDIT_API_KEY** (read-only audit scope, distinct from LLM_PROXY_KEY). Issued at signup alongside LLM_PROXY_KEY; rotated independently. Removes shared-credential blast-radius on LLM_PROXY_KEY compromise. AC #10 updated; customer-record schema extends.
- **CTO #6 officer-side audit-queue FIFO + UUID dedupe** — strict FIFO replay-before-new-entries; post-then-mark-acked atomic with rollback-on-failure; server-side dedupe on `entry_id` UUIDv4 (handles flaky-network double-post). Edge case #4 updated.
- **CTO #7 Git-mirror checkpoint signing flow** — Phase 1 ships UNSIGNED commits (daily checkpoint job emits commits without PGP signing; hash integrity already verifiable via published hashes). Phase 2 adds Captain PGP signing via hardware-token (Yubikey) + offline weekly co-sign flow OR low-privilege dedicated signing service. Hetzner VPS NEVER holds Captain PGP key (compromise risk). Edge case #6 updated; substrate Q deferred to Phase 2 detail.
- **CTO #8 erasure two-hash-field schema** — pseudonymized entries carry BOTH `entry_hash` (pre-pseudonymization, preserves chain integrity for verification) AND `pseudonym_marker_hash` (post-pseudonymization, customer verifies pseudonymization internally consistent). Browser verifier (AC #9) walks chain via original entry_hash (skipping pseudonym_marker for chain math). AC #8 schema fleshed.
- **CTO #9 SLA-tracker shared substrate** — single `cabinet/scripts/sla-tracker.sh` for both Article 15 (this spec AC #6) + Article 17 (Spec 055 erasure runbook). Day-25 + day-29 + day-31 alert pattern reused. Avoids duplicate implementations. AC #6 updated; dependency callout on Spec 055.
- **CTO #10 sub-processor-change + breach event coordination** — FW-100 (Spec 055) substrate OWNS the notification + breach mechanism; FW-097 (this spec) JUST appends log entry on receipt. Cross-spec dependency callout added; not direct FW-097 substrate.
- **CTO #11 Stripe webhook cap_bump integration** — FW-099 (Spec 053 candidate) substrate has Stripe webhook receiver → proxy cap-raise → audit-log entry emitted. Cross-spec flag, not blocking v2; flagged for FW-099 spec coordination.

**Captain ratifications inapplicable per Captain msg 2583 multi-officer-process-as-legal-review framing. A13 inapplicable (no vendor outreach). A12 active — CTO #2/#3/#7 architecture calls are CTO domain (CPO accepts).**
**Priority:** P0 — gates customer dashboard (FW-101) + GDPR Article 15 access-request fulfillment
**Framework ticket:** FW-097
**Owner:** CPO (spec) + CTO (substrate + integrity layer) + COO (compliance review per Captain msg 2583 multi-officer process) + DPO = COO (Spec 055 v7.1 H1 ratified, Captain msg 2737 2026-05-24; FW-114 applied — CoS-as-DPO retired)
**Scope:** Audit log substrate at refslund.ai (server-side) + customer dashboard widget surfacing last-7-days + downloadable full-history export + GDPR Article 15 access request integration
**Canonical artifact home:** Library Specs Space (this spec) + customer-facing logs at refslund.ai server-side
**Evidence:** Spec 055 §customer-data-handling-matrix (audit log entries 90d hot + 7y cold pending Q3 reduction to 5y/10y); Spec 051 §audit-log-emission (proxy-audit JSONL stream — primary input); GDPR Article 15 (right of access), Article 30 (ROPA cross-reference), Article 33 (breach notification audit trail).

---

## Problem

Customer needs visibility into officer activity for three independent reasons:

1. **Trust + verification.** Customer paying 25k-60k DKK/mo wants to verify officers do what they're paying for — see Telegram DMs handled, actions taken, costs incurred per officer, decisions logged. No-visibility = cabinet-as-black-box = trust erosion.
2. **GDPR Article 15 access right.** EU customer can request a copy of all personal data Cabinet processes about them. Cabinet must respond within 30 days with structured export.
3. **Billing reconciliation.** Customer needs ability to audit cap-spend per officer per day against Stripe Token Billing invoice. Disputes resolved against log.

Today's Cabinet has officer log JSONL files in `cabinet/logs/` (officer-side ephemeral) + proxy-audit JSONL stream (refslund.ai-side per Spec 051). Neither is customer-facing; neither has integrity protection (append-only + hash-chain) required for legal/compliance trust.

## Solution

`refslund.ai/proxy/logs/audit/<cabinet-slug>.jsonl` (server-side) is the single source of truth — the FW-097 hash-chained SSOT, **distinct from the FW-096 raw producer stream at `proxy/logs/proxy-audit/`** (input #1 below). Three input streams feed it:
1. **Proxy-audit stream** (Spec 051 AC #6) — every LLM API request via LiteLLM proxy. The FW-097 sidecar reads this stream from `proxy/logs/proxy-audit/<cabinet-slug>.jsonl`, written by the merged FW-096 `audit_logger.py` (ce61fca). **PATH-PIN (corrected per the FW-121 deploy — `LITELLM_AUDIT_LOG_ROOT` is interpreted DIFFERENTLY by producer vs consumer):** FW-096 (producer) treats `LITELLM_AUDIT_LOG_ROOT` as the proxy-audit **dir** and writes `<root>/<slug>.jsonl`; FW-097 (consumer) treats it as the **parent** and reads `<root>/proxy-audit/<slug>.jsonl` + writes the SSOT `<root>/audit/<slug>.jsonl`. So a deploy MUST set the producer's value ONE LEVEL DEEPER than the consumer's (producer = `<consumer-root>/proxy-audit`) so both resolve to the SAME proxy-audit dir — **NOT the literally-same value** (setting them equal breaks the ingest = empty stream). The FW-121 docker-compose does exactly this (litellm `LITELLM_AUDIT_LOG_ROOT=/data/logs/proxy-audit`, audit-server+ingest `=/data/logs`). The sidecar transforms each FW-096 per-request emit into a Spec 052 entry; FW-096-only fields `request_pct_of_cap` + `status` have no 052 schema slot → drop or carry as `metadata`.
2. **Officer-action stream** — every Telegram DM received/sent + officer tool-call (Edit/Bash/Read/Write) + cabinet-decision logged
3. **Cabinet-event stream** — bootstrap events, key rotations, cap-bumps, erasure requests, breach notifications

Output surfaces:
1. **Customer dashboard widget (FW-101):** last-7-days activity log with per-officer filter + cost trends + clickable row → detail view
2. **Full-history export (refslund.ai/dashboard/audit/export):** CSV + JSON downloads scoped to customer's cabinet
3. **GDPR Article 15 access-request endpoint** — customer submits → 30-day SLA → structured export delivered via secure download link

### Audit log entry schema

```json
{
  "ts": "2026-05-20T22:30:00.123Z",
  "cabinet_id": "<cabinet-slug>",
  "entry_id": "<uuid-v4>",
  "stream": "proxy|officer|cabinet",
  "event_type": "<see types below>",
  "actor": {
    "officer": "<officer-slug>",          # null for cabinet-event stream
    "captain": false                      # true for Captain-initiated events
  },
  "subject": {
    "type": "telegram_dm|tool_call|cap_event|key_rotation|erasure|breach|signup|...",
    "target": "<concrete-target-identifier>",
    "metadata": { ... }                   # type-specific payload (redacted for PII)
  },
  "cost": {
    "model": "claude-sonnet-4-6",
    "tokens_in": 1234,
    "tokens_out": 567,
    "cost_raw_usd": 0.42,
    "cost_marked_up_usd": 0.84
  },
  "integrity": {
    "prev_hash": "<sha256 of prior entry's full entry>",
    "entry_hash": "<sha256 of this entry's fields excluding entry_hash itself>"
  }
}
```

### Event types (Phase 1 minimum-viable set)

| Stream | Event type | Trigger |
|---|---|---|
| proxy | `llm_request` | every LLM API call (Sonnet primary, Opus advisor escalation, fallback if enabled) |
| proxy | `cap_warning` | 80% cap threshold reached |
| proxy | `cap_hit` | 100% cap threshold reached |
| proxy | `cap_bump` | customer-initiated cap raise via dashboard |
| proxy | `key_rotation` | virtual-key rotation event (customer-initiated, security-triggered, mandatory annual) |
| proxy | `provider_fallback` | fallback to OpenAI/Gemini (DISABLED Phase 1 per Captain msg 2583 Q5; reserved for Phase 2) |
| officer | `dm_received` | Telegram DM from Captain to officer |
| officer | `dm_sent` | Telegram DM from officer to Captain (reply or proactive) |
| officer | `tool_call` | officer invokes Edit/Bash/Read/Write/Task/etc.; subject.target = tool name + sanitized argv (no secrets, no PII payloads — minimization principle) |
| officer | `decision_logged` | officer adds entry to captain-decisions.md (cross-reference; full text in canonical file) |
| officer | `experience_record` | officer ships an experience record (memory/tier3 entry) |
| cabinet | `bootstrap` | new cabinet provisioned (FW-082 substrate event) |
| cabinet | `signup` | customer signup completed (FW-099 wiring) |
| cabinet | `erasure_request` | GDPR Article 17 request received |
| cabinet | `erasure_complete` | erasure runbook (Spec 055 step 1-8) completed |
| cabinet | `breach_notification` | sub-processor breach received OR Cabinet incident detected |
| cabinet | `dpa_signed` | customer signs DPA (FW-099 clickwrap event) |
| cabinet | `subprocessor_change` | sub-processor list updated; Article 28(2) notification dispatched |

### Hash-chain integrity

Each entry's `integrity.prev_hash` references the prior entry's `entry_hash`. First-entry-per-cabinet uses `prev_hash = "0000..."` (genesis). Tampering with any entry breaks the chain at that entry forward; periodic checkpoint signing (daily at 00:05 UTC) publishes the latest `entry_hash` to a publicly-verifiable log (refslund.ai/audit-checkpoints).

Customer can verify integrity at any time via:
- Download full log JSONL
- Re-compute hash chain
- Match latest hash against checkpoint published at refslund.ai/audit-checkpoints
- Mismatch = tampering or storage corruption; customer files support ticket + escalation to COO/DPO

Hash-chain is fragile under entry deletion. Erasure (Spec 055 Article 17 flow) requires special handling: per-cabinet erasure deletes all entries (terminal state) OR pseudonymizes PII fields while preserving hash-chain integrity (anonymization runbook per CRO S3 Spec 055 v4 fold).

### PII minimization in log entries

Per Article 5(1)(c) data minimization: subject.metadata fields exclude:
- Full Telegram DM text (only `length`, `language_detected`, `attachment_count` retained; full text lives in officer-side ephemeral log + Cabinet retention per Spec 055 data-handling matrix)
- Tool-call argv content (only tool name + redacted-argv-shape; e.g., `Read{path:redacted}` not full path if path contains customer data)
- Decision-trail full text (only entry-id + cross-reference; full text in canonical file)
- Customer attachment content (only filename + type + size)

PII minimization keeps audit log lean + reduces GDPR scope (less personal data = lower retention burden + faster Article 15 export).

### GDPR Article 15 access-request endpoint

Customer requests via dashboard form OR DPO email. Workflow:
1. Authenticate customer identity (signed-in dashboard OR email-verified DPO inbox)
2. Generate Article 15 export ticket → log to `refslund.ai/proxy/logs/audit/<slug>.jsonl` as `event_type: article_15_request`
3. 30-day SLA (default; reasonable extension on complexity per Article 12(3))
4. Export bundle includes: cabinet's full audit log (CSV + JSON), customer account profile, signed DPA copy, sub-processor list at signup, retention status per data type, sub-processor data exports collected via downstream Article 15 chains (where Cabinet processes downstream and can offer help to customer's own Article 15 cascade)
5. Delivered via secure download link (24h expiration; password-protected ZIP; emailed to customer's verified address)
6. Audit log entry `event_type: article_15_complete` posted on delivery

---

## Acceptance criteria

1. **Audit log emission AC** — proxy substrate (Spec 051) + officer hooks (post-tool-use.sh + post-reply.sh) emit JSONL entries per schema to `refslund.ai/proxy/logs/audit/<cabinet-slug>.jsonl`. Officer-side hook posts via refslund.ai REST API (`POST /proxy/audit/log` with customer's virtual-key auth); refslund.ai server appends to log with hash-chain integrity.

2. **Hash-chain integrity AC** — each entry's `integrity.prev_hash` = sha256(prior_entry_full_json). First-entry-per-cabinet uses genesis `prev_hash = "0000...0"`. `integrity.entry_hash` = sha256(this entry's fields excluding entry_hash itself). Daily 00:05 UTC checkpoint job publishes latest per-cabinet hash to refslund.ai/audit-checkpoints (publicly-readable).

3. **PII minimization AC** — log entry schema enforces minimization per Article 5(1)(c): Telegram DM text NOT logged (only length + language + attachment count); tool-call argv content NOT logged (only tool name + redacted-argv-shape); decision-trail full text NOT logged (only entry-id + cross-reference); attachment content NOT logged (only filename + type + size). Validation runs at log-append time; non-conforming entries rejected + error surfaces to officer + COO/DPO. **Minimization model MUST be ALLOW-LIST, not deny-list (Ph5 review fold, 2026-05-25):** a deny-list has structural blind spots — nested objects (`{"msg":{"body":…}}`), case-variant keys (`{"Text":…}`), and arbitrary free-text keys (`{"dm":…}`) all leak past it. The officer-side PRODUCER `audit-emit.sh` (Ph5, merged bafb9a8) is the PRIMARY guarantee and is correctly allow-list / fail-closed (only enumerated scalar+length-bounded safe keys emit; the producer cannot SEND past it). **Follow-up (defense-in-depth parity):** the server-side `proxy/audit-server/validator.py` backstop is still deny-list — harden it to allow-list so a future producer that bypasses `audit-emit.sh` is still caught server-side. Tracked: **task #234** (CTO-owned, FW-097 audit-server scope). NOT a customer-#1 blocker — the client allow-list is the primary, solid guarantee.

4. **Customer dashboard widget AC** — FW-101 dashboard reads last-7-days entries via refslund.ai REST API + renders activity timeline + per-officer filter + cost trend chart + clickable row → detail view (per-entry expansion). Refresh cadence: 60s polling Phase 1; WebSocket/SSE Phase 2.

5. **Full-history export AC** — `refslund.ai/dashboard/audit/export` endpoint returns CSV + JSON downloads scoped to customer's cabinet. Pagination via cursor (1000-entry pages); full history downloadable in chunks. Export emits `event_type: audit_export` log entry (meta-audit-log).

6. **GDPR Article 15 access-request endpoint AC** — `refslund.ai/dashboard/article-15-request` form OR DPO email-receive (dpo@refslund.ai → COO-as-DPO per Spec 055 v7.1 H1 ratification, msg 2737). 30-day SLA enforced via Spec 055 AC #6 erasure-runbook-equivalent ticketing. Export bundle delivered via password-protected ZIP + 24h expiration link.

7. **Append-only enforcement AC** — log file at refslund.ai is append-only via filesystem ACL (chattr +a on Linux ext4) AND application-layer-enforced (server endpoint rejects any non-append operation). Audit log substrate uses immutable-file pattern; updates produce new entries (e.g., correction = new entry with `event_type: correction` + cross-ref to prior entry-id).

8. **Erasure preservation AC** — Spec 055 Article 17 erasure runbook integrates with hash-chain via pseudonymization (NOT deletion): PII fields in subject.metadata blanked (e.g., `{customer_name: "REDACTED-2026-05-20"}`) but entry_hash preserved via a second-layer `pseudonym_marker_hash` field. A pseudonymized entry has TWO distinct integrity checks, BOTH REQUIRED: **(i) chain linkage** uses the preserved `entry_hash` — the verifier skips entry_hash *recompute* for pseudonymized entries (the pre-blanking original cannot be reproduced) and links via the stored value; **(ii) content integrity** uses `pseudonym_marker_hash` = sha256(canonical(entry minus `pseudonym_marker_hash`)) — the verifier MUST recompute and compare this marker for every pseudonymized entry. Check (i) alone is insufficient: without (ii), post-erasure content-tampering of an erased entry is undetectable and the marker is dead weight (FW-097 PR #100 review). "Skip the marker for chain *math*" (CTO #8) means the marker is not part of the prev_hash chain — NOT that the marker goes unverified. Chain integrity preserved post-erasure; both checks continue to work.

9. **Customer integrity-verification UX AC** (per Spec 056 v3 CoS I2 retry-and-confirm gate alignment) — customer dashboard shows audit-log integrity status: "Verified ✓ as of <last-checkpoint-ts>" badge. Customer can click "Verify yourself" → downloads log + reproduces hash-chain in browser via small JS verifier (Web-Crypto sha256); for pseudonymized entries the verifier ALSO recomputes + compares `pseudonym_marker_hash` per AC #8(ii), not just the chain linkage — otherwise tampering of an erased entry passes the browser check too. Mismatch triggers retry-and-confirm flow (3 retries covering network/Web-Crypto edge cases) before surfacing "INTEGRITY CHECK FAILED — Contact Support" copy (NOT alarm-language). Support-ticket auto-files to COO+CoS; Article 33 supervisory-authority escalation gated on COO confirmed-incident determination, NOT customer-facing automatic alarm.

10. **Access control AC** — a customer sees ONLY their own cabinet's log. Reads authenticate with the **`AUDIT_API_KEY`** (CTO #5 — a separate credential from `LLM_PROXY_KEY`, independent blast radius), NOT `LLM_PROXY_KEY`. **Phase 1 isolation = backend-mediation:** the `GET /dashboard/audit/{cabinet_id}/{cursor}` endpoint trusts the caller-supplied `cabinet_id` path param, so the customer/browser MUST NEVER hold the `AUDIT_API_KEY` — the FW-101 dashboard backend holds it and supplies `cabinet_id` from the authenticated customer session (Spec 056). With a single pilot cabinet this is leak-free. **Phase 2 (HARD GATE before customer #2):** per-customer key→`cabinet_id` binding enforced inside `_authorize_read` (key scoped to exactly its cabinet); this MUST ship before a second cabinet is provisioned, or customer A's key reads customer B's log (GDPR breach + AC violation). Tracked as a customer-#2 onboarding gate with COO-as-DPO concurrence (FW-097 PR #100 review). Cabinet ops accesses ALL cabinet logs via admin interface gated on COO-as-DPO authorization + Captain-ratified access-grant (Spec 055 v7.1 H1 ratified) — with DPO=COO the former "DPO + COO" dual-role check collapses to one officer, so the Captain access-grant ratification is the independent second control preserving cross-cabinet separation-of-duties. No cross-customer leakage. **cabinet_id format-validation (#236 — pre-go-live HARD GATE, orthogonal to the Phase-2 key-scoping above):** independent of authorization, `cabinet_id` is caller-supplied on BOTH the `GET /dashboard/audit/{cabinet_id}/{cursor}` path param AND the `POST /proxy/audit/log` body and is used to build filesystem paths — so it MUST be slug-format-validated (reuse the canonical `customer-erasure.sh:73` slug regex `^[a-z0-9][a-z0-9-]{0,63}$` — same convention as `triggers.sh`/`start-officer.sh`) and any non-conforming value REJECTED (4xx) before any path construction or filesystem touch, on BOTH endpoints. This is a SEPARATE control from the key→cabinet binding (FW-120): format-validation guards the path (traversal/injection: `../`, absolute paths, null bytes); key-scoping guards authorization. Both ship before their respective gates — format-validation pre-go-live, key-scoping pre-customer-#2. **Write-side coverage (#237 — pre-go-live):** the two read endpoints are NOT the only `cabinet_id`→path sites — the FW-097 ingest path builds three more from the slug (`ingest.py` `_cursor_path` → `.cursors/<slug>.cursor`; the `proxy-audit/<slug>.jsonl` read path; `hashchain._ssot_path` → `audit/<slug>.jsonl`), and there the slug originates from `ingest.py:194 jsonl_file.stem` (a glob), NOT the #236-validated endpoints. The invariant is therefore GENERAL: EVERY `cabinet_id`→filesystem-path construction MUST be slug-validated. For the ingest path the single covering chokepoint is `ingest_slug`-entry (ingest.py:135) — validating once there covers all three downstream builds AND any future caller; a validator placed only at `hashchain._ssot_path` misses `_cursor_path` + the proxy-audit read path. Severity is LOW today (the glob `.stem` source is filesystem-constrained, so `../` is not reachable via `ingest_all`), but defense-in-depth + future-caller safety make it a pre-go-live gate (#237, CTO/FW-097). **Python anchor caveat (code-proven, PR #112 Opus MEDIUM):** Python slug-validators MUST use `re.fullmatch` or a `\Z` end-anchor — NOT `$`, which in Python matches before a lone trailing `\n` (so `^…$` would wrongly accept `validslug\n`). `app.py:102` uses `\Z` correctly; the #237 ingest validator must too.

11. **Retention AC** — log entries retained per Spec 055 data-handling matrix: 90d hot (Redis cluster + Hetzner VPS SSD) + 5y/10y cold (Hetzner archive volume; 5y default per Spec 055 v4 H4 reduction to Bogføringsloven §10 statutory; 10y for tax-relevant entries per Skatteforvaltningsloven §47). Hot→cold transition: nightly archive job at 00:30 UTC moves >90d entries to cold storage with anonymization marker.

12. **Test harness AC** — `cabinet/tests/test-customer-audit-log.sh` covers: entry emission per schema; hash-chain integrity (mock-tamper test breaks chain); PII minimization validator rejects oversized entries; customer dashboard widget loads correctly; full-history export CSV+JSON pagination; Article 15 endpoint 30-day SLA tracking; append-only filesystem ACL enforcement; erasure preserves hash-chain post-pseudonymization; **`pseudonym_marker_hash` recompute DETECTS post-erasure content-tampering of a pseudonymized entry (the AC #8(ii) regression test — tamper an erased entry's blanked field, assert verify() flags it; this guards finding #2);** customer-only access scope enforced (Phase-1: assert the GET endpoint is backend-mediated / rejects a bad or missing key; Phase-2 per FW-120: assert a key valid for cabinet A is REJECTED on cabinet B); retention cold-archive transition; **client↔server allow-list parity (§17, #234 sync-guard, merged 7c9075e): assert the officer-subset of `validator.py` `_ALLOWED_METADATA_KEYS` == `audit-emit.sh` `_AUDIT_ALLOWED_KEYS` — a one-sided edit on either FAILS the harness (silent allow-list drift → loud failure; also catches an unreviewed server-only key), enforcing the AC #3 fail-closed-allow-list invariant across both the client producer and the server backstop.** **cabinet_id traversal-reject (#236, pre-go-live): assert BOTH the GET path param AND the POST body reject a non-slug `cabinet_id` (`../../etc`, absolute path, null byte) with a 4xx before any filesystem access.** **ingest write-side traversal-reject (#237, pre-go-live): drop a non-slug-named file in the proxy-audit dir and assert `ingest_all` skips it — no `audit/<bad>.jsonl`, no `.cursors/<bad>.cursor`, no path escape outside the cabinet's own files.** ≥14 assertions total.

---

## Edge cases

- **Hash-chain breakage detected mid-customer-lifecycle** — likely cause: server-side filesystem corruption or out-of-band tampering. Runbook: stop appends + checkpoint freeze + CoS+COO+CTO incident response + customer notification + reconstruct chain from prior checkpoint + log incident in `cabinet/logs/audit-incidents.jsonl` + Article 33 supervisory-authority notification if breach material.
- **Article 15 request during active billing dispute** — billing data retention conflicts with full-export per Stripe legal-hold (Spec 055 edge case). Export contains all Cabinet-side data; billing dispute records pulled separately from Stripe portal with appropriate caveat in delivery letter.
- **Customer's officer logs sensitive content in a tool-call argv accidentally (e.g., grep "password=secret" file)** — argv-redaction validator runs at log-append time; sensitive-pattern detection (`/password=|secret=|token=|api_key=/i`) replaces with `REDACTED`; original officer-side log file (cabinet/logs/jsonl on customer MacMini) may contain unredacted version per officer's own retention but never lands in refslund.ai audit log.
- **Officer hook fails to post audit entry** (network down + retry exhausts) — officer-side fallback queue at `cabinet/logs/audit-queue.jsonl` (local) with retry-on-reconnect; if queue exceeds 1000 entries OR 24h backlog, COO alerted; customer dashboard surfaces "Audit log temporarily unavailable" banner.
- **Customer requests multiple Article 15 exports in short window** — anti-abuse: max 1 export per 7 days per customer (configurable; first-request priority); subsequent requests queue + customer notified.
- **Subpoena / lawful-disclosure request for customer's audit log** — Cabinet receives subpoena (Danish court order OR equivalent EU jurisdiction). Workflow per Spec 055 §supervisory-authority-cooperation + new addendum: notify customer where legally permitted (most subpoenas allow customer notification); export delivered to requesting authority with appropriate redactions per Danish/EU law.
- **Hash-checkpoint publication endpoint compromised** — public verifier endpoint at refslund.ai/audit-checkpoints could be tampered with at the CDN/server layer. Mitigation: checkpoint hashes mirrored to a Git repository (refslund-cabinet-checkpoints — public, immutable Git history) AND signed with Captain's PGP key. Customer can verify via Git history independently of refslund.ai availability.

---

## Open questions for officer reviews (Captain-only items deferred unless escalated)

1. **Hash-chain algorithm** — sha256 default. CTO architecture review confirms (alternatives: blake3 faster, sha3-256 quantum-safer). CPO accepts CTO recommendation.
2. **Checkpoint mirror to Git repo** — adds dependency on Git infrastructure (already exists). COO security-review confirms ledger integrity acceptable; alternative = self-signed signatures only.
3. **Article 15 30-day SLA day-counter precision** — Spec 055 uses requested_at + 30d; this spec reuses same mechanism. Confirm alignment.
4. **Customer can't decrypt cold archive cold archive (per CRO S3)** — if customer requests Article 15 export pulling 5+ year-old anonymized records, can the export include the anonymized-record entries (without re-identification)? Recommendation: YES — anonymized record is still a record about the customer's cabinet; Article 15 right to know data is processed. Defer to COO compliance review.

---

## Dependencies

- **FW-096 (Spec 051) dependency:** proxy-audit JSONL stream feeds primary audit-log input; integration tested in Phase 8 of Spec 051.
- **FW-099 (Spec 053 candidate) dependency:** clickwrap DPA signature emits `dpa_signed` event; Stripe Token Billing meter results emit cap-spend events; signup-completion event.
- **FW-100 (Spec 055) dependency:** GDPR Article 17 erasure runbook integrates via pseudonymization-preserves-hash-chain pattern per AC #8.
- **FW-101 dependency:** customer dashboard reads audit-log via refslund.ai REST API for widget render + export endpoint.
- **CTO substrate:** new endpoint `POST /proxy/audit/log` (officer-side hook posts entries); new endpoint `GET /dashboard/audit/{cabinet}/{cursor}` (customer dashboard reads); hash-chain checkpoint job (daily 00:05 UTC cron); checkpoint Git-mirror substrate; append-only filesystem config; anonymization-marker on pseudonymized entries.
- **CoS coordination:** COO-as-DPO holds authority for cross-cabinet log access; CoS coordinates the Captain access-grant ratification (Spec 055 v7.1 H1 ratified, msg 2737).
- **CRO sweep dependency:** quarterly review of hash-chain integrity literature + audit-log SaaS competitive landscape (CRO 4h sweep cadence covers).

---

## Out of scope

- **Real-time streaming audit log via WebSocket/SSE** — Phase 2 polish. Phase 1 uses 60s polling.
- **Customer-side log retention beyond Cabinet's hot/cold storage** — customer can download + store locally if they want longer retention; not a Cabinet responsibility.
- **Audit log search across customer cabinets by Cabinet ops** — Cabinet ops doesn't have cross-customer search Phase 1 (privacy concern). COO/CoS access per-cabinet via DPO oversight. Phase 2 may add filtered cross-customer queries with explicit Captain ratification per query class.
- **Audit log analytics dashboards (cost trends, officer activity heatmaps, anomaly detection)** — Phase 2 polish. Phase 1 surfaces raw timeline + 7-day cost trend only.
- **AI-classified audit log entries (anomaly detection via Sonnet/Opus)** — Phase 2 + Spec 050 §3 §3.4 broader analytics. Cost overhead vs Phase 1 minimum-viable.
- **Customer can write notes/annotations on log entries** — Phase 2 dashboard polish.
- **Multi-language audit log entries** (DA/EN per Phase 1 Danish-first localization) — Phase 2; Phase 1 emits English by default with key event-types localized at dashboard-render time.

---

## Phasing

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | CRO + CoS + COO parallel adversary review fold → v2 | v1 LANDED | v2 LANDED |
| 2 | CPO self-spawned review subagent fresh-context audit | v2 LANDED | v3 LANDED (if findings) OR v2 ship-ready |
| 3 | CTO substrate: refslund.ai POST /proxy/audit/log endpoint + GET /dashboard/audit/... endpoint + hash-chain validator + Git-mirror checkpoint job | v3 ratified | Endpoint live + mock-tamper test passes |
| 4 ║ | CTO substrate: append-only filesystem config (chattr +a) + immutable-file pattern + erasure pseudonymization marker | v3 ratified | Append-only enforced; test harness passes |
| 5 ║ | CTO substrate: officer-side hook integration (post-tool-use.sh + post-reply.sh post entries to refslund.ai) | v3 ratified | Officer hooks emit entries; chain integrity holds |
| 6 ║ | CTO substrate: Article 15 access-request endpoint + 30-day SLA tracker + ZIP export bundler | v3 ratified | Mock customer request → 30d tracker → bundle delivered |
| 7 | CTO substrate: customer dashboard widget wiring (FW-101 coupling) | Phases 3-5 GREEN, couples to FW-101 | Dashboard shows last-7-days + cost trend + per-officer filter |
| 8 | Test harness `cabinet/tests/test-customer-audit-log.sh` (≥10 assertions) | Phases 3-7 GREEN | All assertions passing in CI |
| 9 | End-to-end pilot: one Phase 1 customer cabinet emits log entries + customer verifies hash-chain + submits Article 15 + receives export | Phase 8 GREEN | Customer logs view dashboard; integrity verified; Article 15 cycle works |

**Critical path:** v1 → v2 → v3 → Phase 3 (substrate base) → Phases 4-6 parallel → Phase 7 → Phase 8 → Phase 9 e2e. 4 of 7 substrate phases parallelize after Phase 3 base.

---

## Review process

1. **CRO adversary review** — hash-chain integrity attack surface (collision attempts, tampering vectors, checkpoint compromise), Article 15 export PII-overdraw risk, append-only enforcement gaps.
2. **CoS architecture review** — cross-officer audit-log coordination, DPO access boundary, customer dashboard integration.
3. **COO compliance-failure adversary** — multi-failure-mode: hash-chain breaks during Article 15 cycle + sub-processor breach + customer requests erasure simultaneously.
4. **CPO self-spawned review subagent** — fresh-context audit (per [Review Before Commit] discipline).

Iterate until all 4 reviewers ack. Captain ratification not required (no Open Questions — all internal-officer-decisions per Captain msg 2583 multi-officer-process-is-legal-review framing).

---

**v1 LANDED 2026-05-20 22:50 UTC** (CPO authored under CoS Phase 1 priority queue continuation). CPO self-spawned review next per [Review Before Commit].
