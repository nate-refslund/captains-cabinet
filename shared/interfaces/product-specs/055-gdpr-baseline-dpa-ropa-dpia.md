# Spec 055: GDPR Baseline — DPA + ROPA + DPIA + Sub-Processor List + Annex III ToS Exclusion (FW-100 Phase 1 Priority 2)

**Version:** v7.2 (H1 + H4 RATIFIED) — v6 superseded

**v7.2 changelog — H4 Captain ratification (2026-05-24, msg 2742 "drop to 5"):** retention **RESOLVED to statutory minimum**, dropping the prior 7-year founder-buffer. **5 years** general accounting/billing (Bogføringsloven §10) + **10 years** for tax-relevant records (Skatteforvaltningsloven §47). Captain chose CPO Option (a) — sheds the ~2yr over-statutory liability CRO flagged (no clean Article 17(3)(b) basis for the buffer). Clean Article 17(3)(b) statutory basis → **no Article 6(1)(f) balancing test needed in the DPIA** (the M3 balancing requirement is now moot). Propagated below: data-handling matrix (7y→5y), erasure runbook step 6, ROPA retention field, DPIA (balancing dropped), privacy-policy Article 13 retention, AC #11(c). Downstream propagation targets for FW-100 build: ROPA record, `customer-erasure.sh` cold-archive logic, DPA retention clause, refslund.ai/privacy. **H3 (Anthropic wrapper) still pending Captain — NOT resolved here.**

**v7.1 changelog — H1 Captain ratification (2026-05-24, msg 2737 "Yes, COO as DPO"):** The long-pending H1 open question (DPO appointment — reopened in v4 when CRO surfaced the CoS-as-DPO Article 38(6) conflict) is **RESOLVED: COO-as-DPO.** Designation holds while COO is passive (DPO voluntary at Phase 1 per I2; active Article 39 duties ramp at customer #1 when COO reactivates for the install GDPR walkthrough). CoS-as-DPO retired (the msg-2583 Q2 answer is superseded). COO role-def DPO appendix applied to `presets/work/agents/coo.md` (FW-114). DPO contact = `dpo@refslund.ai` → COO. **This unblocks the GDPR ship gate** (DPA + ROPA + privacy-policy DPO-contact fields can now be finalized). Open Question #2 + AC #11(b) + line-70 RESOLVED-note updated below to reflect COO.
**v7 changelog:** CRO brief `2026-05-23-mac-native-cabinet-pre-staging.md` F5 finding folded. Mac migration (Captain msg 2599 8-phase native) requires erasure runbook covers Mac-native filesystem paths in addition to refslund.ai server-side erasure. Resolutions:
- **F5 Mac-native erasure paths:** §Right-to-erasure flow step 5 (customer MacMini-side erasure) extended with explicit Mac-native paths:
  - Tier 2 working notes: `~/Library/Application Support/refslund-cabinet/instance/memory/tier2/<officer>/`
  - Officer log files: `~/Library/Logs/refslund-cabinet/<officer>.log`
  - Cabinet state files: `~/Library/Application Support/refslund-cabinet/instance/config/`
  - Audit-log local fallback queue (per Spec 052 edge case #4): `~/Library/Caches/refslund-cabinet/audit-queue/`
  - LaunchAgent plists: `~/Library/LaunchAgents/dk.refslund.cabinet.officer.<role>.plist`
  - Customer-attached files (Telegram attachments processed by officers): `~/Library/Application Support/refslund-cabinet/attachments/<task-id>/`
  
  Mac-native erasure replaces Docker-container-volume-delete pattern. `cabinet/scripts/customer-erasure.sh` updated with `launchctl bootout gui/$(id -u) <plist>` per officer (per CTO #2 — `launchctl unload` deprecated macOS API; bootout works Big Sur+) + `rm -rf` per path + LaunchAgent plist removal. AC #6 updated to reference Mac-native paths.

  > **Namespace-tier pin (CTO cross-spec finding 2026-05-24 — prevents incomplete Article 17 erasure):** the erasure target above is `dk.refslund.cabinet.officer.<role>.plist`, which is correct for the **commercial customer tier** (refslund-branded + matches the `dk.refslund.cabinet.officer.*` code-signing identifier from Spec 058 Ckpt 1.8). BUT Spec 059's `deploy-mac.sh` currently writes `com.cabinet.officer.${OFFICER_ROLE}.plist` (STEP-internal namespace, intentionally kept to avoid churning shipped code). **If the commercial install (FW-098/FW-102) reuses 059's deploy-mac.sh, the plist filename and this erasure target must agree** or erasure misses the file → compliance gap at customer audit. **Decision PINNED — Option (a):** commercial-tier deploy writes `dk.refslund.cabinet.officer.*` plists (tier-aware `deploy-mac.sh` variant); STEP-internal stays `com.cabinet.officer.*`. CTO makes `deploy-mac.sh` tier-aware when FW-098/FW-102 builds. No change to this erasure path (already correct for commercial). Tracked as a build-time AC for FW-098/FW-102.

- **F5 Hetzner server-side erasure preserved:** refslund.ai-server-side erasure (audit-log cold-storage, Stripe legal-hold carve-out, Library Compliance Space records, customer-record DB) unchanged from v6. Two-tier erasure: Cabinet-Mac-side + refslund.ai-server-side. Both complete before erasure cycle closes.

- **F2 cross-reference TCC code-signing trap awareness:** customer-erasure.sh runs as user-context script (NOT root); needs TCC consent for filesystem ops in protected paths. AC #6 notes pre-erasure TCC validation step.

- **F4 cross-reference launchd KeepAlive supervisor simplification awareness:** post-Mac-migration, supervisor crash-loop substrate (referenced as "Article 32(1)(c) availability/resilience" in AC #15) shifts to "launchd KeepAlive built-in throttle." AC #15 will fold in v8 per CTO Spec 059 v1.1 Phase 2 KeepAlive policy: `SuccessfulExit:false` + `ThrottleInterval:30` (per CTO #3 cross-reference).
- **CTO #4 Tier 2 path portability:** ~/Library/Application Support/refslund-cabinet/instance/memory/tier2/<officer>/ path mapping needs Phase 2 substrate path-config-var (XDG-style) for portability across Hetzner/Mac/future hosts. Currently Hetzner is /opt/founders-cabinet/instance/memory/tier2/; Mac-native is ~/Library/ subpath. Spec 055 v7 documents the Mac-native paths; portability config var is CTO substrate Phase 2-8 work.
- **CTO #1 path branding bifurcation confirmed:** commercial customers use `refslund-cabinet/` branding (per Spec 050 v1.2 two-tier); STEP-internal uses `cabinet/` branding (per Spec 064). Spec 055 v7 erasure paths use commercial branding throughout (Phase 1 customer-facing). STEP-internal erasure inherits same pattern with branding swap.

- **F3 OS-update consideration in retention:** customer's macOS update may bring schema/path migrations Phase 2; v7 acknowledges out-of-scope ("Mac-major-version compatibility lockstep" per CRO OQ5).

**A11 + A12 + A13 + A14 preserved cleanly.** v7 amendment is pre-stage for Phase 2-8 Mac migration substrate work; ready to ratify once CTO Phase 2-8 specs drop + COO multi-failure-mode adversary lands on clean baseline.

**v6 prior changelog preserved below** (cross-spec coordination with Spec 052 v3 architecture fold).
**v6 changelog:** Spec 052 v3 surfaced cross-spec contradiction with Spec 055 v5 §Article 17 erasure runbook step 5. v5 said "audit log entries scrubbed" (deletion); Spec 052 AC #8 ratified pseudonymization (NOT deletion) preserving entry_hash via two-hash-field schema (CTO #8 fold). Two specs contradicted. **v6 resolution:** rewrite §Right-to-erasure flow step 5 to "audit log entries pseudonymized per Spec 052 AC #8 two-hash-field schema (original entry_hash preserved for chain integrity verification; pseudonym_marker_hash added for pseudonymization self-consistency)" — preserves hash-chain integrity per customer's right to integrity-verification while honoring Article 17. Ratification cascades through both specs.

**v5 prior changelog preserved below** (CoS architecture review fold).
**v5 changelog:** CoS architecture review surfaced 3 BLOCKERs (Spec 055-applicable) + 1 IMPROVEMENT + 1 POLISH. Resolutions:
- **CoS B2 A11 SSOT divergence:** Library Compliance Space ratified as SSOT in v3+v4 but `shared/interfaces/compliance/*.md` file-path anchors persisted in 9+ sites (lines 102-108, 165, 194-198, 202, 204, 212, 261). v5 routes ALL compliance artifacts through Library Compliance Space records. File-path anchors deprecated; replaced with `Library Compliance Space record: <name>` notation. `erasure-log.md` removed entirely per CTO #2 (was already removed in v3 changelog but body still referenced — now fully cleaned). MDX source-of-truth at `shared/interfaces/compliance/` retained ONLY as render-source for Next.js public pages (FW-101 dashboard subroute) per CTO #5 — clearly labeled as "MDX render source, not authoritative compliance record."
- **CoS B4 COO role-def amendment ticket:** filed as FW-114 (next available — actual filing in framework backlog at v5 ship). Parallel to H1 Captain ratification; without it, role-def gap surfaces at signup-live. CoS owns coordination.
- **CoS I1 H3 defense-dossier + Anthropic-ToS sweep workstream:** filed as FW-115 (Anthropic value-add defense-prep + quarterly ToS sweep ongoing). CRO owns sweep cadence (folds into existing 4h research-sweep); CPO owns defense-dossier artifact at `shared/interfaces/legal/anthropic-value-add-architecture.md` (or Library Compliance Space equivalent per A11 reconcile).
- **CoS P1 DPIA mitigation #4 A12 misuse:** A12 = officer-in-loop on architecture (process anchor), NOT privacy mitigation. Reword DPIA §4 mitigation: "human-in-the-loop officer oversight on agent execution" (process-level safeguard preserving customer decisional autonomy).
- **M1 fold-incomplete remaining references:** v4 changelog claimed Phase 4 counsel-review removed; AC #10 + #11 + Dependencies + line 281 still cite counsel review. v5 rewrites ALL 5 sites: "EU-law counsel reviewed" → "Cabinet multi-officer adversary review pass (CRO + CoS + COO per Captain msg 2583 Q1 resolution)"; Phasing table Phase 4 collapsed.

**Captain-DM-clarity (CoS handles in 07:00 briefing):** v4 changelog has 4 HIGH-RISK + 4 MEDIUM + 4 SCOPE nested under 3 reopened Open Questions — Captain briefing flattens to "2 ratification asks gate signup-live: who's DPO, how long do we keep records" + Anthropic-terms calculated bet framing. CoS owns Captain translation.

**v4 prior changelog preserved below** (CRO legal-research adversary fold).
**v3 prior changelog further below** (Captain msg 2583 ratification fold).
**v2 prior changelog further below** (CPO self-review + CTO tech review fold).
**v4 changelog:** CRO adversary review (4 HIGH-RISK BUGs + 4 MEDIUM BUGs + 4 SCOPE-GAPs + 2 FP-verify clean) treated Captain's "Cabinet multi-officer process IS legal review" framing as load-bearing — adversary surfaced with seriousness of external-counsel input. **2 HIGH-RISK items require Captain ratification before signup-live; 4 require structural changes.**

**HIGH-RISK requiring Captain ratification (gate-blocking for signup-live):**
- **H1 CoS-as-DPO violates Article 38(6) per CJEU Case C-453/21 + Belgian DPA Proximus precedent (€50k fine).** CoS coordinates ratification + audits + retro + sub-processor changes — structurally identical to Proximus. Article 38(6) violation is structural (not scale-dependent); €50k fine applied at any scale. **CPO recommends COO-as-DPO** (already owns compliance-adversary lane; doesn't coordinate ratification; doesn't determine processing means; adversary discipline = independence built-in). Alternative: external DPO-as-a-service (~€200-500/mo per A13 inapplicability — paid service, not gatekeeper). **Captain ratifies before any customer signup.** Spec 055 Q2 reopened.
- **H4 7-year retention beyond Bogføringsloven §10's 5-year statutory lacks Article 17(3)(b) legal basis.** "Founder conservative buffer" not a recognized GDPR legitimate interest. **CPO recommends (a):** reduce retention to statutory minimums (5y general billing per Bogføringsloven §10 + 10y tax-relevant per Skatteforvaltningsloven §47) — clean Article 17(3)(b) basis. Alternative: Article 6(1)(f) balancing test documented in DPIA; OR Captain explicit founder-liability acceptance in captain-decisions.md. Spec 055 Q3 reopened.

**HIGH-RISK requiring structural changes (no Captain re-ratify needed):**
- **H2 DPF certification check missing — SCC alone insufficient post-Schrems II.** New AC #17: verify DPF certification status per US sub-processor (dataprivacyframework.gov registry); cite certification ID in DPA for certified; document TIA per EDPB Recommendations 01/2020 for non-certified; re-verify quarterly (DPF stability uncertain pre-Schrems III).
- **H3 Anthropic wrapper/reseller terms risk** — Anthropic's 2026 commercial terms explicitly restrict "single subscription authenticate API access on behalf of third-party end users." Cabinet's value-add carve-out interpretation is operational risk: enforcement = Anthropic terminates → all customers lose service simultaneously. **New AC #18:** customer DPA + ToS risk-disclosure (acknowledges shared dependency on provider terms); documented contingency plan (per Spec 051 — but Q5 disabled OpenAI/Gemini fallback, so contingency = customer notification + service-pause + refund); CRO quarterly Anthropic-ToS-tracking sweep; A13 reframing — A13 says no permission outreach pre-leverage, but DOES require *defense preparation* (value-add architecture documentation, customer-base evidence, technical-implementation-not-pure-resale dossier).

**MEDIUM BUG fold-housekeeping:**
- **M1 Phase 4 counsel-review residual references** — 5 places in Spec 055 v3 still cite "EU-law counsel review" despite Q1 removal in v3 changelog. Phasing table line 257, Dependencies line 227, AC #10, AC #11, line 281 "Counsel-pass = signup-live gate." All rewritten to "Cabinet multi-officer adversary review pass (CRO + CoS + COO) per Captain msg 2583 Q1 resolution." Phase 4 collapses into Phase 4 "multi-officer adversary review fold + Captain ratification."
- **M2 Anthropic sub-processor onward-transfer chain (Anthropic → AWS)** unaddressed. Sub-processor list AC #4 amended: includes named sub-processors PLUS reference to each sub-processor's own sub-processor disclosure (Anthropic → AWS; Stripe → AWS+GCP; etc.). DPA template language acknowledges sub-sub-processors per each sub-processor's public disclosure.
- **M3 DPIA Article 6(1)(f) balancing test → MOOT (H4 resolved to statutory 5y/10y, msg 2742).** [History: this compounded H4 — IF the 7y buffer had been preserved, the DPIA would have needed a full Article 6(1)(f) balancing test. Captain chose statutory reduction instead, so retention now rests on Article 17(3)(b)/6(1)(c) legal-obligation basis, which needs no balancing test.] No DPIA balancing-test section required.
- **M4 Sub-processor 30-day objection window urgent-fallback edge case** explicit cross-ref between Spec 051 AC #4 + Spec 055 sub-processor list note: if Anthropic outage forces fallback AND any current customer hasn't completed 30-day objection window → Cabinet stops service for those customers (proxy-degraded per Spec 051 AC #8); customer notified + offered refund.

**SCOPE-GAPs:**
- **S1 EU AI Act Article 26 deployer obligations (Aug 2, 2026)** — even outside Annex III, general-purpose AI obligations may apply (transparency, AI literacy training, technical documentation, monitoring). New §EU AI Act Article 26 posture subsection — Phase 1 minimum compliance baseline; Phase 2 deeper obligations spec. Out of scope for v4 fold; flagged as Spec 056 candidate.
- **S2 CoS-as-DPO re-evaluation trigger lacks operational definition** — MOOT if H1 (a) COO-as-DPO ratified (no structural conflict; trigger removed). If H1 (b) external DPO ratified, trigger relocates to contractor renewal cycle.
- **S3 Stripe legal-hold anonymization protocol** — new AC #19: enumerates stripped fields (customer name/email/address/IP/phone/billing contact); replacement = random-token irreversible substitution (no mapping retained); transaction record retains amount + date + tax categorization; documented in DPA.
- **S4 Cap-bump audit threshold cross-spec inconsistency** — Spec 049 §cost-cap-audit cites $10 threshold; Spec 051 v2 says "$100." Cross-spec align: Spec 049 governs per-task bounded visual-UAT cap (justifying $10 threshold); Spec 051 governs per-cabinet-per-day cap structurally larger (justifying higher threshold). v4 fold updates Spec 051 to $25 USD (between $10 + $100; higher than Spec 049's per-task scale but lower than $100; defensible mid-point per cap-scale ratio).

**FP-verify clean ✓:** A13 (both specs) + A11 (both specs) per CRO F1+F2 verification.

**v3 prior changelog preserved below** (Captain ratification msg 2583 fold). **v2 prior changelog further below** (CPO self-review + CTO tech review fold).
**v3 changelog:** Captain msg 2583 (2026-05-20 22:26 UTC CoS-routed) ratified ALL 5 Open Questions in one pass:
- **Q1 EU-law counsel ID → RESOLVED:** NO external counsel Phase 1. Cabinet multi-officer process (CPO drafts → CoS architecture → CRO adversary → COO compliance) serves as legal review. Captain carries legal liability as founder. **Phase 4 (external counsel review) REMOVED from Phasing**; multi-officer adversary review fold IS the counsel-equivalent gate.
- **Q2 DPO appointment → RESOLVED (v7.1, superseded the v3 CoS answer):** **COO** serves as DPO (Captain msg 2737, 2026-05-24). NOT CoS (Article 38(6) conflict), NOT external contractor, NOT Phase 2 deferred. DPO contact = `dpo@refslund.ai` → COO. COO role-def DPO duties appendix applied (FW-114). Designation holds while COO passive; active duties ramp at customer #1.
- **Q3 Cold-storage retention → RESOLVED 5 years (msg 2742 "drop to 5", 2026-05-24; supersedes the v3 LOCKED-7y).** 5y general (Bogføringsloven §10) + 10y tax-relevant (Skatteforvaltningsloven §47). Captain dropped the 7y founder-buffer after the v4 H4 reopening flagged it lacked an Article 17(3)(b) basis. Clean statutory basis — no DPIA balancing test required.
- **Q4 Privacy-policy tone → LOCKED reader-friendly:** CPO double-drafts both legal-formal + reader-friendly variants; Captain ratifies finished pages per zajno.com taste anchor (not Captain-blocking before draft).
- **Q5 Sub-processor list freeze Phase 1 → LOCKED Anthropic-only:** OpenAI + Gemini fallback DISABLED in BOTH Spec 055 sub-processor list AND FW-096 (Spec 051) AC #4 fallback enablement gate. Cross-spec Q1 in FW-096 RESOLVED via same ratification.

**Phase 5a "gate-blocking" status REMOVED** — Q1+Q2 RESOLVED collapse Phase 5a. New phasing skips counsel-work, parallel-starts substrate phases earlier.

**CoS-as-DPO + Cabinet-as-counsel risk-class re-evaluation trigger:** at 5+ paying customers, CoS flags for re-evaluation — CoS-as-reviewer + CoS-as-DPO is defensible at Phase 1 scale (<5 customers Danish concierge), may need external counsel + human DPO at Phase 2 scale (self-serve + EU expansion). Captain rate-limited; this is the responsible risk-class boundary acknowledged by Captain.

**v2 prior changelog preserved below** (CPO self-review + CTO tech review fold).
**v2 changelog:** CPO self-review surfaced 4 BLOCKERs + 5 IMPROVEMENTs + 4 POLISH. Resolutions:
- **B1 Article 6 lawful basis missing:** new §Lawful basis subsection — Article 6(1)(b) performance of contract (core service delivery); Article 6(1)(f) legitimate interests (audit-log retention beyond contract necessity, fraud prevention, billing reconciliation); ROPA AC #2 extended to require lawful-basis field per Article 30(1)(b).
- **B2 Article 13/14 information notice content unspecified:** new AC #14 mandates refslund.ai/privacy contains all Article 13 disclosures — controller identity + contact, DPO contact (if appointed), purposes + lawful basis, recipients (sub-processor list cross-reference), third-country transfers, retention periods, data subject rights (access/rectification/erasure/restriction/portability/objection/automated-decision-making), right to withdraw consent, right to lodge complaint with supervisory authority (Datatilsynet for DK).
- **B3 Article 32 security measures unspecified:** new §Security measures subsection + AC #15 — covers Article 32(1)(a) pseudonymization + encryption (TLS 1.3 in transit, AES-256 at rest), 32(1)(b) ongoing CIA assurance (Cloudflare WAF, rate-limiting, intrusion detection), 32(1)(c) availability/resilience (Redis cluster, VPS failover, 99.9% SLA per FW-096 AC #8), 32(1)(d) regular testing (quarterly tabletop + annual penetration test).
- **B4 sub-processor list missing PostHog + Sentry:** added to sub-processor list with US-based + SCC required. Voyage AI assessed: processes Cabinet-internal research-brief content only (no customer data passes through); NOT a sub-processor for customer data. Listed in Out of scope.
- **I1 Article 33/34 breach 72h clock-start:** new explicit definition — "becoming aware" = sub-processor breach notification received OR Cabinet-internal incident confirmed via security-monitoring (not initial-alert; confirmed-incident). Notification threshold: per Article 33(1) "unless unlikely to result in risk to rights and freedoms of natural persons" — runbook decision tree included.
- **I2 Article 37 DPO analysis sharpened:** affirmative — Phase 1 scope NOT mandatory-DPO-triggering per Article 37(1) since (a) processing scale below "large-scale" threshold per WP29 Guidelines (<5000 data subjects, no systematic monitoring beyond audit-log retention), (b) Annex III ToS exclusion eliminates Article 37(1)(b) special-categories trigger, (c) no Article 37(1)(c) systematic-monitoring activity. Voluntary DPO recommended for trust-signal + Phase 2 readiness; Captain Q2 confirms appointment path.
- **I3 Annex III attestation enforceability:** strengthened ToS clause — (a) positive obligation: customer warrants and represents (not just acknowledges); (b) detection mechanism: Cabinet retains right to query customer's use case via support inquiry + may request usage description quarterly; (c) specificity: ToS defines "AI system used by Cabinet officer" in customer's context per Article 3(1) EU AI Act; (d) termination + indemnification clause for ToS violation (customer indemnifies Cabinet for any regulator action arising from customer's Annex III misuse).
- **I4 Q4 + Q5 CPO-resolvable, not Captain-only:** Q4 privacy-policy tone — CPO drafts BOTH variants (legal-formal + reader-friendly per zajno.com bar), presents finished pages to Captain via CoS, not a Captain-blocking question. Q5 OpenAI/Gemini freeze — duplicates FW-096 Q1 (already routed); cross-reference in spec, no separate Q5 routing. Open Questions reduced 5→3 (Q1 counsel, Q2 DPO, Q3 retention).
- **I5 Cloudflare logs PII handling:** explicit erasure runbook step — Cloudflare Logpush disabled by default for refslund.ai infrastructure; Workers logs retention configured to <30 days; if customer-specific log routing enabled (Phase 2), erasure cascade includes Logpush deletion + Workers log retention purge.
- **POLISH P1 retention duration:** corrected reference — Danish Bogføringsloven §10 requires 5 years for most accounting records; tax-relevant records 10 years per Skatteforvaltningsloven §47. v2 ROPA AC retention specifies: 5-year cold archive for general billing, 10-year for tax-relevant transactions (separate flags per record). Captain Q3 ratifies if longer retention desired beyond statutory.
- **POLISH P2 SCC module selection:** new AC #16 — DPA template SCC addendums explicitly identify module (Module 2 controller-to-processor for Anthropic/OpenAI/Gemini/ElevenLabs/Stripe/PostHog/Sentry; Module 3 processor-to-processor not applicable Phase 1 since Cabinet doesn't onward-transfer to other processors). Counsel review confirms module selection.
- **POLISH P3/P4 Phase 1 scope + anchor compliance verified clean ✓**

CTO tech-review fold (10 findings — 6 substrate, 3 architectural, 1 nit):
- **CTO #1 DPA digital signature mechanism:** clickwrap (checkbox + IP + timestamp + signed-document-hash) — GDPR-compliant under eIDAS, no DocuSign/SignWell dependency. Stripe checkout supports legal-agreement clickwrap natively. Log signed-DPA-instance to Library Compliance Space + audit log entry. AC #1 + Phase 6 wiring updated.
- **CTO #2 erasure logging single-source-of-truth:** Library Compliance Space is SSOT; `erasure-log.md` removed (auto-generated view if needed). Script writes via Library MCP `library_create_record` tool. AC #6 updated.
- **CTO #3 sub-processor erasure cascade automation gap:** Phase 1 ships MANUAL cascade (CoS emails sub-processors per template) for Anthropic (nothing to erase since no Cabinet-side retention), Hetzner (volume-delete), Cloudflare (manual log purge). AUTOMATED where API exists: Stripe customer delete, ElevenLabs force-delete. Don't over-promise. AC #6 updated with manual/automated split.
- **CTO #4 30-day SLA auto-tracking:** erasure ticket adds `requested_at`, `due_at` (auto = requested+30d), `completed_at` fields. Script auto-alerts CoS at day-25 + day-29 + day-31 (breach). ~5 lines added to customer-erasure.sh. AC #6 updated.
- **CTO #5 public pages CMS approach:** Next.js dashboard subroute MDX rendering — `app/(public)/{privacy,terms,sub-processors,data-handling,erasure}/page.mdx`. Markdown-source-of-truth at `shared/interfaces/compliance/`; same deploy pipeline as customer dashboard (FW-101). No external CMS dep per A3 + A11. AC #4, #5, #7, #14 updated.
- **CTO #6 audit-log encryption at rest:** pgcrypto column-level encryption for sensitive fields (officer-action payloads with PII) + LUKS full-disk-encryption on Hetzner VPS for everything else. AWS-KMS-style key custody: Captain holds master key. Folds into new §Security measures + AC #15 per B3 fold. Key-rotation discipline → FW-100b candidate for Phase 2.
- **CTO #7 sub-processor change customer notification cycle:** Q5 framing absorbed — enable OpenAI/Gemini at launch (listed in initial DPA + Phase 1 sub-processor list, DISABLED-pending-AC#4-fallback-Q1-ratify) avoids 30-day post-launch Article 28(2) notification cycle. FW-101 dashboard needs sub-processor banner + email-blast mechanism for future additions. Captain Q5 collapses to FW-096 Q1 (per CPO self-review I4); single Captain decision now spans both specs.
- **CTO #8 Captain Q1-Q5 ratification staging:** Phase 5 SPLIT into:
  - **Phase 5a:** Captain ratifies Q1 (counsel ID) + Q2 (DPO appointment) → unblocks Phase 4 counsel work + Phase 6-9 substrate parallel start
  - **Phase 5b:** Captain ratifies Q3 (cold-storage retention) AFTER counsel-pass on retention statute analysis (Bogføringsloven 5y vs Skatteforvaltningsloven 10y per record category)
  Q4 (privacy-policy tone) deferred to CPO double-draft + Captain ratifies-finished-pages (not Captain-blocking question per CPO I4). Q5 absorbed to FW-096.
- **CTO #9 breach-notification.sh tabletop:** hybrid script — generates TEST breach scenario payload (fake Anthropic notice) → SIMULATES cascade response (logs what would happen, sends nothing real) → CoS reviews simulation output for gaps. Real breach response stays manual until trust established. AC #12 updated.
- **CTO #10 nit timestamp:** v2 LANDED timestamp will reflect actual completion time.

**CTO alignment confirmations (no fold needed, just verified):** 8-artifact ship list ✓, Annex III ToS exclusion ✓, Phase 1 Danish-only EU-resident ✓, Library Compliance Space canonical ✓, Stripe legal-hold carve-out ✓, 5y/10y statutory cold-storage anonymization ✓ (updated from 7y per H4 msg 2742), DPO voluntary ✓, DPIA generic+addendum trigger ✓, 90-day hot audit ✓, Cabinet MacMini local out-of-scope ✓, A13 inapplicable (counsel = paid service, DPO = org role) ✓.

**Open Questions further reduced 3→2 via CTO #7 absorption of Q5:** Q1 (counsel ID) + Q2 (DPO appointment) gate-blocking; Q3 (retention duration) post-counsel-pass. **[ALL THREE NOW RESOLVED: Q1 cabinet-multi-officer-review (msg 2583), Q2 COO-as-DPO (msg 2737), Q3 5y/10y statutory (msg 2742). Only H3 Anthropic-wrapper remains pending Captain.]**
**Priority:** P0 — gates customer signup live + FW-099 Stripe wiring + FW-096 fallback enablement
**Framework ticket:** FW-100 (existing entry in `shared/cabinet-framework-backlog.md`)
**Owner:** CPO (spec) + EU-law counsel (legal review of DPA template + Annex III ToS) + Captain (final ratification) + CoS (Captain ratification pipeline + sub-processor list)
**Scope:** Compliance baseline artifacts shipped to refslund.ai customer signup flow + privacy-policy publication + ToS publication; covers EU customers (Phase 1 Danish-first per Captain msg 2565)
**Canonical artifact home:** Library Specs Space (this spec) + Library Compliance Space (signed DPA + ROPA records) + refslund.ai public pages (privacy policy + ToS)
**Evidence:** Captain msg 2565 (2026-05-20 13:58 UTC ratification — "DK + EU compliance baseline, Annex III high-risk use cases EXCLUDED from Phase 1 ToS"); CoS Spec 050 commercial-direction master Phase 1 priority list; GDPR Articles 17 (erasure), 28 (processor obligations), 30 (ROPA), 35 (DPIA), 44-49 (third-country transfer); EU AI Act Annex III (high-risk categories).

---

## Problem

Customer signups for commercial Cabinet require GDPR-compliant compliance baseline BEFORE any signup goes live. EU regulation imposes specific artifacts on processors (Cabinet) handling personal data on behalf of controllers (customer):

1. **DPA (Data Processing Agreement)** — Article 28 contract between controller (customer) and processor (Cabinet). Required at signup.
2. **ROPA (Record of Processing Activities)** — Article 30 internal record of processing activities. Required to be maintained + available to supervisory authority on request.
3. **DPIA (Data Protection Impact Assessment)** — Article 35 assessment of high-risk processing scenarios. Cabinet's LLM-driven officer decision-making likely triggers DPIA requirement.
4. **Sub-processor list** — Article 28 disclosure of all sub-processors (Anthropic, OpenAI, Gemini, ElevenLabs, Stripe, Cloudflare, Hetzner/Fly.io). Customer ratifies list at DPA signature.
5. **Customer data-handling matrix** — explicit per-data-type retention + storage location + access policy.
6. **Right-to-erasure flow** — Article 17 customer request + Cabinet honors + downstream sub-processor propagation + audit log.
7. **Annex III high-risk exclusion in ToS** — Captain ratified Phase 1 excludes EU AI Act Annex III use cases. ToS enforces via customer attestation + termination clause.
8. **Third-country transfer mechanisms (SCC)** — Anthropic + OpenAI + Stripe etc. are US-based; require Standard Contractual Clauses for legitimate transfer per Articles 44-49.

Without all 8 artifacts, customer signup is non-compliant — supervisory authority risk + customer refusal-to-sign risk.

## Solution

Phase 1 ships 8 compliance artifacts, each gated by EU-law counsel review + Captain final ratification:

1. **DPA template** — customer signs at signup as part of Stripe checkout (FW-099 wiring)
2. **ROPA document** — Library Compliance Space record-of-record (canonical per A11; MDX render-source at `cabinet/customer-templates/ropa.md`), maintained per customer
3. **DPIA document** — Library Compliance Space record-of-record (canonical; MDX render-source at `cabinet/customer-templates/dpia.md`); per-customer addendum if customer's use case introduces novel risks
4. **Sub-processor list** — public page at refslund.ai/sub-processors (Next.js MDX subroute per v5 CTO #5), updated when list changes (customer notification per Article 28(2) 30-day objection window)
5. **Customer data-handling matrix** — public page at refslund.ai/data-handling (Next.js MDX) + Library Compliance Space record-of-record (canonical per A11)
6. **Right-to-erasure runbook** — `cabinet/scripts/customer-erasure.sh` + customer-facing request flow at refslund.ai/erasure
7. **Annex III ToS exclusion clause** — in refslund.ai/terms; customer attestation at signup
8. **SCC addendums** — appended to DPA for US-based sub-processors

Phase 1 = Danish-first, EU customers only → simplifies third-country transfer (no transfers to customer's jurisdiction; all customer data stays EU-resident at Hetzner Frankfurt).

### Sub-processor list (initial Phase 1 — 9 sub-processors per v2 B4 + v4 H5 fold)

| Sub-processor | Purpose | Location | Transfer mechanism (per AC #17 DPF check) | SCC Module (per AC #16) | DPA-signed-by-Cabinet |
|---|---|---|---|---|---|
| **Anthropic** | LLM provider (Sonnet 4.6 primary, Opus 4.7 advisor) | US | SCC + DPF check (cert ID per AC #17) | Module 2 | Yes |
| **OpenAI** (provisional, fallback only) | LLM fallback on Anthropic outage | US | SCC + DPF check | Module 2 | Yes — pre-signed for capacity; **DISABLED per Captain msg 2583 Q5 ratification** (NOT pending; ratified-as-disabled). Future enable requires Article 28(2) 30-day notification window. |
| **Google (Gemini)** (provisional, fallback only) | LLM fallback alternative | EU/US mixed | EU adequacy + DPF check | Module 2 | Yes — pre-signed; **DISABLED per Captain msg 2583 Q5**. |
| **ElevenLabs** | Voice synthesis | US | SCC + DPF check | Module 2 | Yes |
| **Stripe** | Payment processing + Token Billing meter | US | SCC + DPF (Stripe on DPF list per CRO 054-14) | Module 2 | Yes |
| **Cloudflare** | DNS + TLS termination + edge cache | US (CDN; data residency configurable) | SCC + DPF check + EU-resident config | Module 2 | Yes |
| **Hetzner** (or Fly.io EU region) | VPS hosting for refslund.ai proxy + Redis | EU (Germany for Hetzner; EU regions for Fly.io) | None (EU-resident, no third-country transfer) | n/a (EU-resident) | Yes — primary infrastructure provider |
| **PostHog** (added v2 B4) | Product analytics (dashboard usage patterns) | US | SCC + DPF check | Module 2 | Yes |
| **Sentry** (added v2 B4) | Error monitoring + crash reports (step-network org per memory) | US | SCC + DPF check | Module 2 | Yes |
| ~~Apple iCloud~~ NOT a Cabinet sub-processor | per v4 H5 BLOCKER resolution Option (a): Cabinet does NOT enroll customer MacMini in iCloud Drive backup for cabinet data. Customer's own iCloud usage outside `cabinet/*` is customer-scope. | n/a | n/a | n/a | n/a |

Customer DPA enumerates this list at signature. New sub-processor addition triggers Article 28(2) customer notification + objection window (default 30 days) before activation. **Sub-processor's own onward transfers** (e.g., Anthropic → AWS; Stripe → AWS+GCP) acknowledged in DPA via reference to each sub-processor's public sub-processor disclosure (per v5 M2 fold).

### Customer data-handling matrix

| Data type | Storage location | Retention (hot) | Retention (cold) | Customer access | Sub-processor access |
|---|---|---|---|---|---|
| Telegram DMs (text) | refslund.ai audit log (server-side) | 90 days | 5 years general / 10 years tax-relevant (Bogføringsloven §10 / Skatteforvaltningsloven §47) | Customer dashboard view | None (internal audit only) |
| LLM API requests/responses (prompt + completion) | NOT STORED (proxy emits only token counts + metadata) | N/A | N/A | N/A — privacy-minimization | Anthropic processes during request; no Cabinet-side retention |
| Customer-uploaded files (attachments via Telegram) | Cabinet MacMini local storage (NOT server-side) | Until task completion + 7-day grace | None | Customer owns the files; their local storage | None |
| Voice messages (audio attachments) | refslund.ai server-side encrypted | 30 days | None unless customer opts in to archive | Customer dashboard download | ElevenLabs (during synthesis); destroyed post-synthesis |
| Officer Tier 2 working notes | Cabinet MacMini local (`instance/memory/tier2/`) | Indefinite (customer-controlled) | N/A — never leaves MacMini | Customer-owned via filesystem | None |
| Audit log entries (proxy + officer actions) | refslund.ai server-side | 90 days hot | 5 years cold (10y tax-relevant) | Customer dashboard view | None |
| Customer billing data (Stripe-managed) | Stripe | Stripe retention policy (7+ years) | Stripe-managed | Customer Stripe portal | Stripe only |
| Customer account profile (email, name, company, cabinet config) | refslund.ai server-side | Active customer + 30 days post-cancellation | None post-erasure | Customer dashboard | None |

Customer can request earlier deletion (right-to-erasure per Article 17 + Cabinet's runbook).

### Annex III high-risk exclusion (ToS clause)

Phase 1 customers attest at signup AND ToS prohibits the following Annex III categories per EU AI Act:

1. Biometric identification of natural persons (real-time or post-event remote)
2. AI systems for management/operation of critical infrastructure
3. AI in education or vocational training for evaluating learners or determining access
4. AI in employment, worker management, or access to self-employment (recruitment, performance evaluation, task allocation decisions)
5. AI for access to / enjoyment of essential public services (credit scoring, public benefits eligibility)
6. AI in law enforcement (profiling, predictive policing, evidence reliability assessment)
7. AI in migration, asylum, border control (visa, asylum, risk assessment)
8. AI in administration of justice or democratic processes (election integrity, court decisions)

**Customer attestation at signup:** checkbox + clickwrap acknowledgment "I will NOT use Cabinet for any of the 8 Annex III use cases above." ToS provides legal basis for immediate termination + data deletion if customer violates.

Phase 2 (post-leverage) may unlock specific Annex III categories with additional compliance scaffolding (Article 9 special categories of personal data, biometric-specific safeguards, etc.) — out of scope Phase 1.

### Right-to-erasure flow

Customer requests erasure via:
- **refslund.ai/erasure** web form (Phase 1) OR
- DM to Cabinet's account-bot (Phase 2 polish)

Cabinet erasure runbook (`cabinet/scripts/customer-erasure.sh`):
1. Receive erasure request → log to **Library Compliance Space** record (canonical per A11 v5 SSOT fold; replaces deprecated `erasure-log.md` filepath anchor per v3 CTO #2)
2. Validate identity (signed-in customer)
3. Generate erasure ticket → 30-day SLA per GDPR Article 17 (default 30-day; reasonable extension on complexity per Article 12(3))
4. Cascade erasure to sub-processors:
   - Anthropic: no Cabinet-side retention (proxy doesn't store prompts), nothing to erase downstream
   - Stripe: customer's payment data per Stripe retention policy (cannot delete due to legal hold; documented in DPA)
   - ElevenLabs: voice messages already 30-day TTL'd; force-delete if active
   - Cloudflare: edge cache flush + log retention purge
   - Hetzner: customer storage volumes deleted
5. Hot-storage purge: audit log entries scrubbed; account profile deleted; cabinet config archived for billing reconciliation then anonymized
6. Cold-storage handling: 5-year compliance hold (10y for tax-relevant records) preserved (anonymized), legal basis = Article 6(1)(c) compliance with legal obligation (Bogføringsloven §10 5y / Skatteforvaltningsloven §47 10y) + Article 17(3)(b) — retention required for legal claims defense. (Reduced from 7y per Captain msg 2742.)
7. Erasure completion notification to customer with audit-trail receipt
8. Audit-log of erasure event (high-priority entry)

### DPIA (Data Protection Impact Assessment)

Generic-product DPIA covers Cabinet's processing activities at the platform level. Per-customer addendums when customer's use case introduces novel risk (e.g., processing special categories of personal data, large-scale public surveillance, etc. — already excluded per Annex III ToS so unlikely Phase 1).

Generic DPIA structure:
1. **Description of processing:** Cabinet runs LLM-mediated officer decision-making on customer's business data via Telegram + audit log.
2. **Necessity + proportionality:** processing necessary for service delivery; minimization via prompt-not-stored discipline.
3. **Risk to data subjects:** (a) LLM output incorrect → customer business impact, (b) unauthorized access to audit log → privacy breach, (c) sub-processor breach upstream.
4. **Mitigation:** (a) officer-in-loop on architecture per A12; (b) audit log encrypted at rest + access-controlled; (c) sub-processor SCC + breach notification cascade.
5. **DPA Officer review:** Captain or designated DPO reviews + signs.

---

## Acceptance criteria

1. **DPA template AC** — DPA template record-of-record in **Library Compliance Space** (canonical per A11; render-source MDX at `shared/interfaces/compliance/dpa-template.md` is operational not authoritative); covers Article 28(3) all mandatory clauses (purpose, duration, categories of data, controller/processor obligations, sub-processor disclosure, audit rights, breach notification, data return/deletion on termination). Reviewed via Cabinet multi-officer process (CPO + CoS + CRO + COO) per Captain msg 2583. Customer signs via eIDAS-clickwrap at signup (FW-099 Stripe checkout step per Spec 054 CTO #1 + #6).

2. **ROPA AC** — ROPA record-of-record in **Library Compliance Space** (canonical per A11); covers Article 30(1) all mandatory fields (controller + DPO contacts [COO — DPO ratified msg 2737, contact dpo@refslund.ai], processing purposes, **lawful basis per Article 6(1)** [v4 B1 fold: 6(1)(b) performance of contract + 6(1)(f) legitimate interests for audit-log retention], data subject + data categories, sub-processors, third-country transfers, retention periods, security measures per AC #15). Internal document; available to supervisory authority on request within 1 working day.

3. **DPIA AC** — DPIA record-of-record in **Library Compliance Space** (canonical per A11); covers Article 35(7) all mandatory elements (description of processing, necessity + proportionality assessment, risk to rights + freedoms, mitigation measures including A12 officer-in-loop-on-architecture process anchor per v5 P1 fold). Generic-product DPIA + per-customer addendum trigger documented. **No Article 6(1)(f) retention-balancing test needed** — H4 RESOLVED to statutory 5y/10y (msg 2742), which has a clean Article 17(3)(b)/6(1)(c) legal-obligation basis; the v4 M3 balancing requirement is moot (it only applied if retention exceeded statutory).

4. **Sub-processor list AC (v4 H2 + v2 B4 + v6 X3 + v4 H5 NEW)** — public page at `refslund.ai/sub-processors` lists all 9 Phase 1 sub-processors with transfer mechanism + DPF certification status (per v4 H2 AC #17) + DPA-signed status:
   - **Anthropic** (LLM primary) — US, SCC + DPF check per AC #17
   - **OpenAI** (LLM fallback) — US, SCC + DPF check per AC #17; **DISABLED per Captain msg 2583 Q5 ratification** (NOT pending-anymore; ratified-as-disabled). Future enable requires Article 28(2) 30-day notification.
   - **Google (Gemini)** (LLM fallback) — EU/US, EU adequacy + DPF check; **DISABLED per Captain msg 2583 Q5**.
   - **ElevenLabs** (voice synthesis) — US, SCC + DPF check
   - **Stripe** (payment + Token Billing) — US, SCC + DPF check (Stripe on DPF list per CRO 054-14)
   - **Cloudflare** (DNS + TLS + edge) — US, SCC + DPF check
   - **Hetzner** (VPS hosting EU-resident OR Fly.io EU-region) — EU, no SCC required
   - **PostHog** (product analytics) — US, SCC + DPF check (added per v2 B4 fold)
   - **Sentry** (error monitoring) — US, SCC + DPF check (added per v2 B4 fold; step-network org config per memory `project_sentry_config.md`)
   - **NOT included** (per v4 H5 BLOCKER resolution): Apple iCloud Drive — Cabinet does NOT enroll customer MacMini in iCloud backup for cabinet data; customer's own iCloud usage outside `cabinet/*` directories is customer-scope, not Cabinet sub-processor (v4 Spec 053 H5 fold removes iCloud requirement from pre-install checklist).
   
   Updated when list changes; customer notified per Article 28(2) with 30-day objection window.

5. **Data-handling matrix AC** — public page at `refslund.ai/data-handling` (Next.js MDX render per v5 CTO #5; source at `cabinet/customer-templates/` per Spec 053 CTO #6 + Spec 055 v5 SSOT cleanup) carries the 8-row matrix above. Customer dashboard surfaces retention-status per data type (90-day audit log countdown visible per FW-101 / Spec 056). PII matrix retention = 5y general / 10y tax-relevant (H4 RESOLVED msg 2742).

6. **Right-to-erasure flow AC** — `cabinet/scripts/customer-erasure.sh` script + customer-facing form at `refslund.ai/erasure` (Spec 056 v3 erasure subpage); covers 8-step runbook above. Erasure-request record-of-record in **Library Compliance Space** (canonical per A11 v5 fold; replaces deprecated erasure-log.md filepath anchor). 30-day SLA tracked via shared `cabinet/scripts/sla-tracker.sh` substrate (per v2 CTO #4 + Spec 052 CTO #9). Stripe legal-hold limitation documented in DPA. Audit-log entries handled via **pseudonymization (NOT deletion) per Spec 052 AC #8 two-hash-field schema** (per v6 cross-spec contradiction resolution).

7. **Annex III ToS clause AC** — refslund.ai/terms includes 8-category exclusion verbatim + customer-attestation checkbox at signup (FW-099 Stripe checkout step). Violation → ToS termination clause + 30-day customer notice. Reviewed via Cabinet multi-officer process per Captain msg 2583. Customer-attestation enforceability per v4 I3 fold: positive obligation + monitoring + Annex III definition specific to Cabinet context + termination + indemnification.

8. **SCC addendums AC (v6 SCC Module 2 per v5 P2)** — DPA template includes SCC addendums for each US-based sub-processor (Anthropic + OpenAI + ElevenLabs + Stripe + Cloudflare + PostHog + Sentry) using **SCC Module 2 (controller-to-processor)** per Regulation 2022/679. Hetzner (EU-resident) doesn't require SCC. Module 3 (processor-to-processor) not applicable Phase 1 since Cabinet doesn't onward-transfer to other processors.

9. **Customer signup wiring AC** — FW-099 (Spec 054) Stripe checkout step embeds DPA signature + Annex III attestation + sub-processor list ratification via eIDAS-clickwrap (per Spec 054 CTO #1 + #6). Customer cannot complete signup without signing all 3. Signed records stored in **Library Compliance Space** (canonical) + customer Postgres record (operational, encrypted-at-rest per Spec 054 CTO #5).

10. **Multi-officer adversary review pass AC (per Captain msg 2583 Q1 resolution — replaces former EU-law counsel review AC, removed per v4 M1 fold)** — DPA template + Annex III ToS clause + DPIA generic document reviewed via Cabinet multi-officer process (CPO drafts → CoS architecture → CRO adversary → COO compliance). Reviewer pass records logged to Library Compliance Space. Multi-officer review-pass = signup-live gate. Re-evaluation trigger at 5+ paying customers (CoS-flagged) for upgrade to external counsel + external DPO at Phase 2 scale.

11. **Captain final ratification AC (post v4 H1+H3+H4+v6 H5 cycle)** — Captain reviews + ratifies: (a) sub-processor list (msg 2583 Q5 Anthropic-only Phase 1 RATIFIED), (b) DPO role assignment (RESOLVED msg 2737 2026-05-24: COO-as-DPO; supersedes the msg-2583 CoS-as-DPO answer after the v4 H1 Article 38(6) reopening), (c) retention durations (RESOLVED msg 2742 2026-05-24: 5y general + 10y tax-relevant statutory; dropped the prior 7y after the v4 H4 reopening), (d) Annex III ToS clause (msg 2583 Q4 reader-friendly tone RATIFIED), (e) Anthropic wrapper risk-acceptance (v4 H3 NEW pending Captain), (f) iCloud Drive removal from pre-install checklist (v4 H5 Option (a) clean removal, no Captain ratify required for removal — only Option (b) add-as-sub-processor needs Captain). Captain ratifications recorded in `shared/interfaces/captain-decisions.md`.

12. **Breach notification runbook AC** — `cabinet/scripts/breach-notification.sh` covers Article 33 (notify supervisory authority within 72h of CONFIRMED awareness per v4 I1 clock-start definition: sub-processor breach notification received OR Cabinet-internal incident confirmed via security-monitoring — NOT initial-alert) + Article 34 (notify data subjects without undue delay if high-risk). Notification threshold per Article 33(1) "unless unlikely to result in risk to rights and freedoms" — runbook decision tree included. Tested via tabletop exercise quarterly (CoS-owned per v3 Captain Q2 — pending v4 H1 COO-as-DPO transition; runbook ownership shifts to COO-as-DPO).

13. **Test harness AC** — `cabinet/tests/test-gdpr-baseline.sh` covers: DPA template loads + key sections present; ROPA mandatory fields populated incl. Article 6(1) lawful basis; DPIA generic addendum + Article 6(1)(f) balancing test (if retention extension applies); sub-processor list endpoint returns current state with DPF status + SCC module per entry; data-handling matrix endpoint returns valid JSON schema; erasure flow end-to-end (mock customer → erasure request → 8-step runbook execution → completion notification + pseudonymization-preserves-hash-chain validation per Spec 052 AC #8); Annex III attestation gates signup completion; SCC addendums present per Module 2 in DPA; Article 13/14 privacy notice content present per AC #14; Article 32 security measures present per AC #15; Stripe anonymization protocol per AC #19. ≥12 assertions total.

14. **Article 13/14 information notice AC (v4 B2 fold — NEW)** — refslund.ai/privacy publishes mandatory Article 13 disclosures: controller identity + contact, DPO contact (COO — ratified msg 2737; dpo@refslund.ai), processing purposes + lawful basis per Article 6(1), recipients (sub-processor list cross-reference to AC #4), third-country transfers + safeguards, retention periods (per AC #5 + #11), data subject rights (access/rectification/erasure/restriction/portability/objection/automated-decision-making per Articles 15-22), right to withdraw consent, right to lodge complaint with supervisory authority (Datatilsynet for DK). Reader-friendly tone per Captain msg 2583 Q4 + Spec 056 v3 AC #15 CRO copy-review.

15. **Article 32 security measures AC (v4 B3 fold — NEW)** — security measures documented in ROPA + DPA: **Article 32(1)(a) pseudonymization + encryption** (TLS 1.3 in transit; AES-256 at rest via pgcrypto column-level per Spec 054 CTO #5 for llm_proxy_key + audit_api_key; LUKS full-disk-encryption on Hetzner VPS per v5 CTO #6); **Article 32(1)(b) ongoing CIA assurance** (Cloudflare WAF; rate-limiting; intrusion detection); **Article 32(1)(c) availability/resilience** (Redis cluster per Spec 051 CTO #2; VPS failover Phase 2; 99.9% SLA target per Spec 051 AC #8); **Article 32(1)(d) regular testing** (quarterly tabletop per AC #12 + annual penetration test).

16. **SCC Module 2 selection AC (v5 P2 fold — NEW)** — DPA SCC addendums explicitly identify **Module 2 (controller-to-processor)** per Regulation 2022/679 for Anthropic + OpenAI + Gemini + ElevenLabs + Stripe + Cloudflare + PostHog + Sentry. Module 3 (processor-to-processor) not applicable Phase 1 since Cabinet doesn't onward-transfer beyond named sub-processors. Reviewed via Cabinet multi-officer process per Captain msg 2583.

17. **DPF certification check AC (v4 H2 fold — NEW)** — before sub-processor list ratification, verify DPF certification status for each US sub-processor (Anthropic + OpenAI + Gemini + ElevenLabs + Stripe + Cloudflare + PostHog + Sentry) via dataprivacyframework.gov registry. For DPF-certified: cite certification ID in DPA + sub-processor list public page. For non-certified: require documented TIA per EDPB Recommendations 01/2020. Re-verify quarterly (certifications can be withdrawn; DPF stability uncertain pre-Schrems III). DPF-invalidated contingency: sub-processor list re-evaluation trigger + customer notification per Article 28(2).

18. **Anthropic wrapper-terms risk-acceptance + defense dossier AC (v4 H3 fold — NEW, pending Captain ratification)** — customer DPA + ToS explicitly acknowledge Cabinet uses LLM provider through value-add proxy interpretation; customer accepts shared dependency on provider terms. Documented contingency plan: Spec 051 AC #8 proxy-degraded state on Anthropic enforcement (customer notification + service-pause + refund — fallback DISABLED per Captain msg 2583 Q5). Defense-preparation dossier per FW-115: `shared/interfaces/legal/anthropic-value-add-architecture.md` (Library Compliance Space mirror per A11) — value-add architecture documentation, customer-base evidence, technical-implementation-not-pure-resale evidence. CRO quarterly Anthropic-ToS tracking folds into existing 4h research-sweep cadence; material ToS changes trigger COO + Captain review. A13 reframing: don't outreach pre-leverage, DO prepare defense.

19. **Stripe legal-hold anonymization protocol AC (v4 S3 fold — NEW)** — Stripe billing data subject to Danish bookkeeping retention (5y per Bogføringsloven §10 + 10y tax-relevant per Skatteforvaltningsloven §47) cannot be deleted on Article 17 erasure. Anonymization protocol: stripped PII fields enumerated (customer name + email + address + IP + phone + billing contact); replacement = random-token irreversible substitution (no mapping retained for re-identification); transaction record retains amount + date + tax categorization for tax/accounting; documented in DPA so customer informs decision at signup. Audit-log entry on anonymization per Spec 052 AC #8 two-hash-field preservation.

---

## Edge cases

- **Sub-processor breach notification cascade** — if Anthropic notifies Cabinet of a breach, Cabinet must propagate to affected customers within Article 33 72h window. Runbook: parse Anthropic's breach notification → identify affected customer cabinets (via audit log) → email + dashboard banner per customer → notify supervisory authority if high-risk per Article 33.
- **Customer requests erasure mid-billing-cycle** — billing data retention conflicts with erasure (Stripe legal hold). Resolution: erasure of customer-facing surfaces + audit log purge proceeds normally; Stripe billing record anonymized (PII stripped, transaction record retained for tax/accounting per Danish bookkeeping law). Customer DPA includes clause explaining this carve-out.
- **Customer in non-EU jurisdiction** — Phase 1 is Danish-only per Captain msg 2565, so this edge case shouldn't arise. If a non-EU customer attempts signup, FW-099 Stripe checkout enforces EU-only billing address validation; non-EU rejected with "Phase 2 international expansion" message.
- **Customer data on Cabinet MacMini (Tier 2 notes, attachments)** — Cabinet has no access to customer's MacMini storage. Right-to-erasure: customer's own data on their own device; out of Cabinet's scope. DPA documents this scope boundary.
- **Anonymous data after erasure** — 5-year compliance hold (10y tax-relevant) retains anonymized billing records. Anonymization = irreversible (random-token substitution for customer ID; no re-identification path). Documented in erasure runbook step 6.
- **Sub-processor change between DPA signature and feature use** — e.g., Cabinet adds new sub-processor mid-cabinet-lifetime. Article 28(2) notice + 30-day objection window. Customer can object → Cabinet provides alternative OR refunds remaining subscription + offboards.
- **Supervisory authority audit request** — Danish DPA (Datatilsynet) or other EU SA requests ROPA + DPIA + breach log. Cabinet responds within 1 working day (Article 31 cooperation duty). Runbook: CoS retrieves from Library Compliance Space + sends within SLA.
- **Customer violates Annex III ToS** — Cabinet detects via support inquiry OR billing pattern (e.g., suspicious volume on hiring-decisions endpoints if such feature ever exists). Termination clause: 14-day notice + data export option + erasure. Customer's right to fair termination preserved.
- **DPO (Data Protection Officer) appointment** — GDPR Article 37 requires DPO if processing large-scale special categories OR systematic monitoring. Cabinet's Phase 1 scope likely doesn't trigger mandatory DPO appointment (Annex III exclusion + no special-categories processing). Voluntary DPO appointment recommended (Captain assumes the role OR appoints contractor). DPO contact in DPA + privacy policy.

---

## Open questions for Captain ratification

**Q1, Q4, Q5 RESOLVED via Captain msg 2583 (2026-05-20 22:26 UTC). Q2 + Q3 REOPENED per CRO adversary review v4 fold (2026-05-20 22:55 UTC) — legal-research-quality findings invalidated prior resolutions:**

1. ~~EU-law counsel identification~~ → **RESOLVED: NO external counsel Phase 1.** Cabinet multi-officer process (CPO + CoS + CRO + COO) IS the legal review. Captain carries founder legal liability. Phase 4 counsel-work item REMOVED.
2. **DPO appointment** → **RESOLVED 2026-05-24 (Captain msg 2737): COO-as-DPO.** [History: reopened in v4 per CRO H1 — CoS-as-DPO violates Article 38(6) per CJEU C-453/21 + Belgian DPA Proximus €50k precedent, structural not scale-dependent. CPO recommended COO-as-DPO (compliance-adversary lane; doesn't coordinate ratification; doesn't determine processing means; adversary discipline = independence built-in). Captain ratified.] COO role-def DPO appendix applied (FW-114). No longer gate-blocking — GDPR ship gate UNBLOCKED.
3. **Cold-storage retention duration** → **RESOLVED 2026-05-24 (Captain msg 2742 "drop to 5"): 5y general billing (Bogføringsloven §10) + 10y tax-relevant (Skatteforvaltningsloven §47).** [History: reopened in v4 per CRO H4 — 7y founder-buffer lacked an Article 17(3)(b) basis. CPO recommended option (a) statutory reduction; Captain chose it, shedding the ~2yr over-statutory liability.] Clean Article 17(3)(b) basis — no Article 6(1)(f) balancing needed. No longer gate-blocking.
4. ~~Privacy-policy tone~~ → **RESOLVED: reader-friendly.** CPO double-drafts both variants; Captain ratifies finished pages.
5. ~~Sub-processor list freeze Phase 1~~ → **RESOLVED: Anthropic-only.** OpenAI + Gemini fallback DISABLED in Spec 055 AND FW-096 (Spec 051) — cross-spec Q1 same ratification.

**NEW Open Questions surfaced by CRO adversary fold (require Captain ratification before signup-live):**

6. **H3 Anthropic wrapper/reseller terms risk-acceptance** — Anthropic's 2026 commercial terms restrict "single subscription authenticate API access on behalf of third-party end users." Cabinet's value-add carve-out interpretation is operational risk (Anthropic terminates → all customers lose service simultaneously). **Captain ratifies:** (a) accept known risk + ship under value-add interpretation + documented contingency (Spec 051 AC #8 proxy-degraded state) + CRO quarterly Anthropic-ToS-tracking sweep + defense-preparation dossier, OR (b) re-architect to per-customer-own-API-key model (Phase 2 BYOK). Recommendation: (a) — value-add justifiable; (b) is Phase 2 self-serve evolution anyway. **GATE-BLOCKING.**

**Re-evaluation trigger:** at 5+ paying customers, COO (NOT CoS — moot if H1(a) COO-as-DPO ratified) flags for re-evaluation of multi-officer-process-as-legal-review risk class. Phase 2 may require external counsel + DPO upgrade.

---

## Dependencies

- **EU-law counsel review** — Captain identifies + briefs counsel; CPO provides spec draft; counsel marks up; CPO folds; Captain ratifies. Gate for signup-live.
- **FW-099 Stripe checkout wiring** — DPA signature + Annex III attestation + sub-processor list ratification embedded in checkout step. CTO Phase 2 substrate (FW-099).
- **FW-096 LiteLLM proxy** — sub-processor list includes Anthropic + OpenAI + Gemini; fallback enablement gated on FW-100 DPA + Captain Q5.
- **FW-101 customer dashboard** — surfaces retention countdowns per data type + erasure-request UI.
- **CoS coordination** — Captain ratification of Q1-Q5 (above); counsel review scheduling; supervisory authority cooperation runbook tabletop quarterly.
- **Library Compliance Space** — new space for storing signed DPAs, counsel review records, breach logs, erasure logs. CPO requests CoS create Space at Phase 1 entry.

---

## Out of scope

- **DPO appointment as mandatory.** Phase 1 scope below Article 37 mandatory threshold. Voluntary appointment per Q2.
- **Article 9 special categories processing** (health, race, religion, sexual orientation, etc.) — Annex III ToS exclusion already covers most special-categories use cases. Phase 1 customers attest they will not process special categories.
- **Cross-border transfer to non-EU customers.** Phase 1 Danish-only. Phase 2 EU + Nordic expansion. Phase 3 international ratchets up SCC + adequacy considerations.
- **Customer-side compliance audits.** Cabinet provides DPA + ROPA + audit logs on request. Customer-internal compliance audits (their own Article 30 ROPA) are customer's responsibility, not Cabinet's.
- **AI-Act-specific high-risk system registration.** Annex III exclusion means Cabinet's Phase 1 use cases don't trigger high-risk system obligations (registration with EU AI database, conformity assessment, post-market monitoring). Phase 2 unlock of any Annex III category triggers these.
- **Customer-side data subject rights handling.** Customer is the controller for their employees' data; Cabinet provides processor-side cooperation. Customer's own DSR responses to their employees are customer's scope.
- **CRO competitive monitoring for compliance landscape changes** — separate ongoing CRO research-sweep responsibility (4h sweep cadence).

---

## Phasing

Phase-gated. Phases marked `║` parallelize after dependency clears.

| Phase | Scope | Depends on | Gate |
|---|---|---|---|
| 1 | CPO drafts spec v1 + 8 compliance artifact templates (this spec + DPA + ROPA + DPIA + sub-processor list + data-handling matrix + erasure runbook + Annex III ToS clause + SCC addendums) | None | v1 LANDED |
| 2 | CRO adversary review + CTO tech review + CoS architecture review + COO compliance-failure adversary parallel folds | v1 LANDED | v2 LANDED |
| 3 | CPO self-spawned review subagent fresh-context audit | v2 LANDED | v3 LANDED |
| 4 | EU-law counsel review + markup | v3 LANDED + Captain identifies counsel (Q1) | counsel-pass v3.1 LANDED |
| 5 | Captain final ratification (Q1-Q5) | v3.1 LANDED + counsel-pass | All Captain decisions logged in captain-decisions.md |
| 6 ║ | CTO substrate: Stripe checkout DPA-signature integration (FW-099 dependency) | v3.1 ratified | Customer signup demo flow signs DPA |
| 7 ║ | CTO substrate: customer-erasure.sh runbook + refslund.ai/erasure form | v3.1 ratified | Erasure end-to-end tested with mock customer |
| 8 ║ | CTO substrate: refslund.ai/sub-processors + refslund.ai/data-handling + refslund.ai/terms + refslund.ai/privacy public pages | v3.1 ratified | Public pages live + accessible |
| 9 ║ | CTO substrate: breach-notification.sh runbook + tabletop exercise | v3.1 ratified | Tabletop exercise passes |
| 10 | Library Compliance Space provisioning + CPO seeds with signed records as customers sign | v3.1 ratified + CoS creates Space | First customer DPA signed + filed in Space |
| 11 | Test harness `cabinet/tests/test-gdpr-baseline.sh` (≥10 assertions) | Phases 6-10 GREEN | All assertions passing in CI |
| 12 | End-to-end pilot: one Phase 1 customer signs DPA + ratifies sub-processor list + completes Annex III attestation + checkpoint erasure flow | Phase 11 GREEN | Customer signup live with full compliance posture |

**Critical path:** v1 → v2 → v3 → counsel-pass → Captain ratification → Phases 6-10 parallel → Phase 11 test → Phase 12 e2e pilot. EU-law counsel review is the long-lead-time item; Captain identifies counsel early.

---

## Review process

1. **CRO adversary review** — counsel-grade adversarial-input audit: customer attestation bypass, sub-processor disclosure timing edge cases, Annex III enforcement weak points, breach-notification cascade gaps, GDPR right-to-erasure scope-creep risks.
2. **CTO tech review** — FW-099 Stripe integration of DPA signature, customer-erasure.sh implementation discipline, public-pages CMS approach (refslund.ai/privacy etc.), audit-log retention enforcement at proxy + storage layer.
3. **CoS architecture review** — cross-officer compliance-state propagation, Library Compliance Space schema, Captain ratification pipeline efficiency, counsel review scheduling.
4. **COO compliance-failure adversary** — multi-failure-mode: customer requests erasure during active breach + Stripe holds billing data + Anthropic incident notice + Annex III violation detected simultaneously. What breaks?
5. **CPO self-spawned review subagent** — fresh-context audit before counsel routing (per [Review Before Commit] discipline).
6. **EU-law counsel markup** — qualified data-protection counsel reviews DPA + Annex III ToS clause + DPIA generic; CPO folds markup; routes back to counsel for re-pass if substantive changes.
7. **Captain final ratification** — Q1-Q5 above; recorded in captain-decisions.md.

Iterate until all 7 reviewers ack. Counsel-pass + Captain ratification = signup-live gate.

---

**v1 LANDED 2026-05-20 22:30 UTC** (CPO authored under CoS Phase 1 unblock 14:00 UTC). CPO self-spawned review next.
