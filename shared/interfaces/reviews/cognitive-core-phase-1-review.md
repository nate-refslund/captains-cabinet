# Cognitive Core Phase 1 (COG-1) — frozen post-implementation review (plan §12.3)

Verdict: PASS
Reviewed-Scope-Digest: 4f0dd91fd0d66e36f90ca251546cdf169eb5bd400378c56e57781303c31a33b2
Reviewed-Commit: 175ce93a06708f043bff58be969edf83a4840592 (advisory; frozen 4-cluster review inspected f62a3820, delta 175ce93a reviewed separately — see addendum)

Reviewed 2026-07-21 against base 0bf60e698a148616bebc1676119913d11b272535 (which carries the attack-reviewed plan). Independent fresh-context review: four adversarial cluster reviews (envelope plane; DB/capture plane; relay plane; cutover/parity/governance plane) reconciled by a Fable 5 lead synthesizer that re-verified every contested byte claim and re-ran the load-bearing gates itself. No implementer self-reports were consumed; every verdict derives from the committed bytes of the 7-commit range, docs/plans/cognitive-core-phase-1-contract-2026-07-20.md (THE standard), and docs/cognitive-core-foundry.md.

## Binding and exclusion boundary (this artifact + the two operative ledgers)

The digest above is SHA-256 over sorted `<mode> <sha> <path>` git ls-tree lines of the 43-path COG-1 scope = (rollback-manifest `remove` MINUS this artifact) UNION `restore_from_baseline`, computed over the committed tree at HEAD (cabinet/scripts/cognitive-phase1-review-scope.py, EXPECTED_SCOPE pin + resolve_scope()). Excluded by construction: (a) THIS artifact — REVIEW_ARTIFACT is subtracted from the scope and guard-refused if present, so recording the digest is non-self-referential and the flip of this file to the verdict line above cannot break the binding; (b) the two append-only operative ledgers, docs/plans/operative-egg-ledger-2026-07-07.yml and docs/plans/operative-egg-plan-2026-07-07.md — not scope members, so the later COG-1 status flip (in-flight to done, status-only) lands without touching the digest. Everything else that can change COG-1 behavior — including the rollback manifest and the scope tool itself — is bound: any post-review edit to a scope file changes the digest and verify-cognitive-phase1.sh BLOCKs until a re-review re-freezes it.

## Named interpretation — emission-scoped shadow gate (audited, confirmed consistent)

The foundry:255 stop condition ("changes live behavior before its shadow gate") is read EMISSION-scoped, exactly as plan §5.1 states honestly: what stays shadow until cutover is EMISSION; CAPTURE is live inside every officer_tasks transaction from the moment 047 applies, fail-closed by design, gated by pre-apply harness evidence plus a rehearsed one-command disarm. The code matches this posture precisely:

- Capture: cabinet/sql/047-officer-tasks-outbox.sql implements the stated fail-closed trigger — IS-DISTINCT no-op guard (:139-142), COALESCE actor (:150), suppression honored only for actor 'cpo-etl' else RAISE (:153-159), cabinet identity read from the pg_db_role_setting catalog with RAISE on unprovisioned / empty-session / divergent-spoof (:161-183), same-transaction INSERT with ON CONFLICT DO NOTHING (:189-209). The posture is restated in the DDL header (:13-21) and exercised against real ephemeral PostgreSQL 17 (capture suite: 24 passed, 0 skipped).
- Gated apply + rehearsed inverse: lib_cog1_harness.py builds an ephemeral PG17 cluster with a construction-based live-DSN fence (child env assembled from scratch, never os.environ.copy(); FORBIDDEN list covers NEON_CONNECTION_STRING / DATABASE_URL / REDIS_* / all libpq PG*; fence tests plant a live-canary in the parent env and prove the child cannot carry it). cog1-authority-flip.sh disarm/enable wraps psql ALTER TABLE officer_tasks DISABLE/ENABLE TRIGGER trg_officer_tasks_outbox_capture with ON_ERROR_STOP=1 and fail-loud on an unset DSN (:57-68); rehearsed against a real PG17 cluster (cutover suite 14/14) and inside cognitive-phase1-rollback-rehearsal.py (PASS).
- Everything defaults dark at this merge: the authority pointer is absent, and every consumer fails safe to legacy — my-tasks.sh:218 skips the legacy XADD only on the exact pointer value 'outbox'; the relay table drain is default OFF (relay.py:729-731 store_true; the cron wrapper arms it only via explicit flag/env after a fail-loud preflight — python3.12 pin exit 70, missing psycopg2 exit 71, unreadable pointer exit 72; absent pointer = legacy fail-safe); the relay's only registered stream adapter hardcodes cabinet:tasks:events:shadow (relay.py:304, used :475), so the committed code CANNOT write the live stream; 047 is applied to no live database by this merge — repo-wide, its only apply seams are the manual §12.2 production gate and load-preset.sh's provisioning block (:296-386), which is identity-GUC-first and gated with strict single-transaction apply so a fresh hatch can never hit the fail-closed RAISE; no launchd plist, deploy-mac, or services.yml change exists in the diff; the nightly falsifier honestly no-ops (exit 0) while the parity log is absent, so the merge adds no post-land noise.
- No silent live-emission change anywhere: the only live-touching edits are the plan-named ones — task-events-watch.py acceptance-WIDENING (validate → validate_any, :226-234; poison-discard/ACK behavior byte-unchanged), task_sync_runner.py payload.kind discriminator stamps on its three existing telemetry emits (types/counts unchanged), and relay queue() marker+flock on a path with zero production callers.

## Review dimensions

### Envelope plane
- Version dispatch precedes the v1 closed set: classify_fields (framework/triggers/envelope.py:383-403) routes through validate_any (:857-875) — dict-carrying-schema_version to validate_v2, everything else to the frozen v1 validate(). v1 is byte-frozen: extracted-function SHA-256 identical base vs candidate; the v1 red-team + enforce suites are 0-byte-diffed and re-run green (133 passed); test_envelope_v2.py source-pins the v1 region and constants (:771-807).
- v2 field set matches plan §4.2 / foundry:81 exactly: 12 always-required + lane_id/project_id/payload/payload_ref conditional + causation_id optional; scope levels must be ABSENT when not required, never null/sentinel (:812-816); sentinel refusal on identity/scope ids (:793-798) suite-pinned equal to Phase-0 contracts.py SENTINEL_IDS; classification is a closed vocabulary carried as DATA ONLY (:819-830) — no join law, the consumer never reads it; MAX_V2_ENVELOPE_BYTES=32768 separate from v1's 16384, both pinned with measured-fixture headroom; event_type must be domain-prefixed, is refused if a central-enum member, and must be declared by the registry-resolved payload_schema (:735-746) — a typo'd or missing x-cabinet-event-types annotation fails CLOSED. 300-iteration seeded fuzz never-accept/never-raise green.
- Domain registry is genuinely domain-local: schema_registry.py is lookup-only over committed per-domain JSON (no write API, no cache); central surfaces byte-unchanged (framework/events/emitter.py, cabinet/services.yml, framework/authority/classifier.py all 0-byte diffs); census PASS with the §10.1 allowance rows landed in the same commit as the first framework code.
- No competing Gate/store/effect-algebra/promotion path: new stores are exactly officer_tasks_outbox (the foundry:50 co-commit primitive) + task_sync; register_table_adapter (relay.py:455-464) is destination routing carrying the idempotency token — the §9.2-amended sibling seam, declaring no action/risk/undo vocabulary; the table drain emits zero central-ledger events; never-a-score self-test 12/12.

### DB/capture plane
- 047 columns match §5.2 verbatim (immutable-content projection first, relay bookkeeping after); idempotency_key TEXT NOT NULL UNIQUE (the §6.2 SQL-race fix) + event_id UNIQUE; task_sync PRIMARY KEY (canonical_id, destination); pgcrypto guard; cog1-replay-hash.py's IMMUTABLE_CONTENT_COLUMNS exclude bookkeeping/blocked_reason/destination with ORDER BY id (:59-74) — §9.3 exactly.
- Both 038 guards cloned faithfully (IS DISTINCT arm; COALESCE actor; trigger definition matches 038:267-269); the idempotency key embeds txid_current(); the sim-10 identity spoof RAISES at both layers.
- load-preset.sh orders the identity GUC strictly before — in fact gating — the 047 apply, static-tested (pos_046 < pos_identity < pos_047; ON_ERROR_STOP=1 and -1 pinned).
- CI (own commit 16a6edcd, cabinet-ci.yml only) adds the postgres:17 service + psycopg2-binary + postgresql-client with a harness-owned COG1_PG_DSN name fenced from live-store variables, so sims GATE rather than skip. The 16-to-17 pin is a documented S0 supersession.
- B1/B2 fresh baselines measured pre/post-047 on one ephemeral cluster; all p95 within the ratified x1.10+10ms bound (numbers below); the bound is test-enforced, not a checked-in constant.

### Relay plane
- One module extends framework/outbox — never a second outbox; the legacy-drain diff is limited to the queued_by marker filter + foreign-row telemetry (relay.py:203-223); dispatch_one/dispatch_pending bodies are byte-identical to base; queue() gains the sanctioned §6.2 flock + marker.
- Table-drain order proven: claim (FOR UPDATE SKIP LOCKED + TTL, :504-519) → event_id backfill in its own COMMITTED update strictly before any effect (:522-542; WHERE event_id IS NULL makes redelivery id-stable) → build → validate_v2 → cabinet backstop → adapter with the idempotency token → record (:581-610). XADD is argv-only redis-cli to the shadow stream (:467-488).
- Terminal taxonomy: only validation-class failures can go terminal past the attempt cap; transport is never terminal at any attempt count (:613-632); unclassified failures default to transport (fail-safe). The partition sim holds redis dead past cap+3 cycles and recovers with zero loss; the classification mutant is detected.
- psycopg2 import is lazy inside the drain path — proven by importing the module under an import hook that raises on psycopg2 (collection-safe in driver-less jobs, §9.4).

### Cutover / parity / governance plane
- Pointer discipline: one well-known host-global default path; env override tests-only; the framework never reads it (repo grep of framework/ non-test: zero hits); the my-tasks.sh diff is +7 lines, consult-only; fail-safe proven behaviorally (absent/empty/'outboxx' → legacy; exact 'outbox' → skip), including a zero-env context observing the flip through the default path.
- Consumer version-dispatch (the plan-review P0): _valid_envelope routes through validate_any; the v1-only-revert mutant poison-discards the SAME relay-built v2 entry (built via relay.build_dispatch_fields, not a hand fixture) — invalid_envelope==1, no blocked_card, empty needs-ledger; the positive rig shows consumed + ACKed + blocked_card filed end-to-end; a static pin forbids raw validate() in the function body. v1 consumer suites unbroken (108 passed).
- Parity: the reader composes into the ENABLED nightly falsifier — no new service row (services.yml byte-identical); asymmetric EFFECTIVE-mapped predicate with cpo-etl suppression exclusion, phantom/coverage/legacy-subset clauses, keyed on outbox + history + the windowed legacy stream and never the central outbox_* ledger (task-sync-drift-falsifier.py:561-629); the freshness floor counts CYCLES — one JSONL line per relay cycle — per complete UTC day, with an absent day inside the observed range a BREACH (:634-661); two consecutive breach dates escalate to ONE captain card via the existing attention gateway.
- Governance: census budgets at exact caps (delta below); the COG-0 frozen-historical note is a pure append landed in the allowance-bearing commit (§10.3 sequencing honored); Phase-0 surfaces byte-unchanged except the contract-yml allowance rows; egg exclusions with paired expect-absent rows (48 passed, 1 skipped); the rollback manifest closes over the 43-file footprint with 3 one-command runtime inverses + the allowance-removal clause (10 passed, incl. the footprint-coverage ratchet and digest teeth); FW-019 cp1-cp5 present as APPROVE artifacts; check-layer-separation new=0; germline zero-contact (diff paths ∩ germline-lock list = empty); A13 and ledger-status-parity GREEN (ids=349 md_rows=349).

## Findings register (reconciled across the four clusters; ranked)

F1 — cutover live-target seam NOT implemented. Recorded here as a HARD PRE-CUTOVER BLOCKER (rung-4 eligibility condition). It does not block this dark merge.
Plan §8.4 specifies "the wrapper resolves the pointer and passes the target down" and "the relay targets the LIVE stream cabinet:tasks:events" at cutover. The bytes have no such path: relay.py:304 hardcodes SHADOW_STREAM (used :475) with no target parameter on the drain, the adapter, or the CLI (:720-745); the cron wrapper preflights pointer READABILITY only and passes no target; the §9.1 consumer-compat rig is implemented hermetically (test_cog1_cutover.py monkeypatches _xreadgroup/_xack) — it proves consumer acceptance of relay-BUILT v2 entries plus the v1-only-revert mutant, but not stream routing. Consequence if flipped on these bytes (after a production 047 apply + relay arming): my-tasks.sh:218 suppresses the legacy XADD while the relay keeps writing only shadow — cabinet:tasks:events goes dark, task-events-watch starves, and neither the asymmetric parity clause (vacuous when legacy is silent) nor the freshness floor (counts cycles, which continue) alarms. The flip script header's "the relay owns the durable tasks exhaust" overstates these bytes. No deferral was recorded in cp1-cp5, the rollback manifest, or the plan (the only in-range plan edit is the §9.2 amendment) — this artifact is that record.
Why this does not block the merge: cutover execution is NOT a §11.1 exit gate; rung 4 sits behind the §12.2 production-apply gate, the §8.2 named arming sequence, the ≥7-day clean soak, and the §8.4 eligibility judgment; the merged state is dark by construction (the relay cannot write the live stream at all — over-satisfying foundry:255 for emission); and no automated caller of cog1-authority-flip.sh exists (repo grep: human-runbook only).
BINDING CONDITIONS (additive to §8.4's consumer gate — cutover is INELIGIBLE until all three): (a) the pointer-to-target seam lands: the wrapper resolves the pointer VALUE and passes the stream target down; the relay accepts it with shadow as the hard default; the framework still never reads the pointer; (b) an end-to-end routing rig proves pointer=outbox → the relay XADDs the sandbox Redis's cabinet:tasks:events (the §9.1 stated construction), with a mutant proving the rig detects a shadow-stuck relay; (c) the cog1-authority-flip.sh header is corrected until (a) lands. These are scope-file code changes: they re-bind the digest and take re-review per §12.3. The COG-1 done-flip ledger commit MUST carry a dated deferral note naming "relay live-stream retarget + end-to-end routing rig" as a hard pre-cutover blocker (same status-only commit as F4).

F2 (P3) — v2 sentinel refusal is raw-compare while the Phase-0 dialect it mirrors normalizes: envelope.py:795-798 checks the raw value against V2_SENTINEL_IDS, but contracts.py:293/:388 membership-check .strip().lower(); 'Default'/'NONE'/' null ' pass v2 validation as scope ids. Pilot unaffected (cabinet_id is DB-provisioned; lane/project absent at cabinet scope). Fix on the next envelope wave: normalize before membership + case/whitespace forgery test rows.

F3 (P3) — a 047 re-apply silently re-arms a disarmed capture trigger: DROP TRIGGER IF EXISTS + CREATE (047:217-220) recreates ENABLED regardless of a prior `disarm`, and the file is advertised idempotent/safe-to-re-run, with load-preset re-applying it at preset load. Runbook rule until fixed: any 047/preset re-apply during a disarm incident must be followed by re-disarm; preferred fix preserves the trigger's enabled state across re-apply.

F4 (P3) — the COG-1 ledger row carries a duplicate last_update key (operative-egg-ledger yml :3341 "2026-07-20" and :3345 "2026-07-19"; last-wins parsers resolve the machine-read freshness field to the STALER date) and a stale rollback field ("no-op until implementation starts"). Pre-existing at base 0bf60e69, unfixed in range. Fix in the done-flip status-only commit: collapse to a single last_update and point rollback at docs/plans/cognitive-core-phase-1-rollback-manifest-2026-07-20.yml; append-only note discipline.

F5 (P3) — hatch-seam divergence: only load-preset.sh gained the identity+047 block; cabinet-bootstrap.sh's schema list does not include 047, acknowledged only by an inline comment. Dark-safe (no 047 = no capture; the identity gate prevents the RAISE), but bootstrap-provisioned instances silently lack the outbox. Record a queryable debt row (owner cognitive-core-program).

F6 (P3 — down-ranked from a cluster P2, resolved by shipped bytes) — the relay's parity JSONL field "samples" carries the per-cycle CLAIMED count (relay.py:655-656), an invitation for a reader to sum it and false-breach an idle-but-live relay. The shipped reader already counts LINES per day (cog1_freshness_floor increments once per line), so the floor semantics are correct in this candidate: an idle-but-live relay passes; an absent/short day breaches (suite-tested). Residual follow-up: rename the field to 'claimed' + add an explicit per-line heartbeat token; also the relay docstring's "the falsifier reader [is] OTHER waves" is stale — the reader landed in this same candidate.

F7 (P3) — the standard was amended mid-implementation: plan §9.2 register_adapter() → register_table_adapter() plus the signature-collision rationale (the ONLY plan edit in the range, verified by git diff). Honest, matches the shipped seam, cp3-reviewed; named here so post-attack-review plan drift stays auditable.

F8 (P3 — pre-existing, honestly disclosed) — 038's constraint-guard compares pg_get_constraintdef() against a PG16-era string; under PG17 the re-add collides (masked in production by fail-soft psql; surfaced by the COG-1 harness, which applies 038 non-strict then verifies the load-bearing objects). Out of the COG-1 file-set; follow-up owner outside this phase. 047 itself applies strict and clean.

F9 (note) — soak/cutover eligibility must be judged on POSITIVE evidence: ≥7 consecutive complete days each PRESENT (≥1,000 cycle-lines against the nominal 1,440) with clean verdict lines from the falsifier reader — never absence-of-breach: run_cog1_parity honestly no-ops exit-0 while the parity log is absent (correct fleet-wide), so a never-armed relay on the pilot box produces zero verdict lines, not breach lines.

F10 (note) — the program checklist's expected count for test_cog1_outbox_capture.py ("22p") is stale-low: the frozen candidate carries 24 tests, all green on real PostgreSQL 17.10 with 0 skips.

## Commands and results

Lead synthesizer re-runs at f62a3820 (house interpreter python3.12; PATH includes postgresql@17):
- cabinet/scripts/cognitive-phase1-review-scope.py --print → the digest recorded above; independently matches the two cluster computations of it.
- cabinet/scripts/cognitive-architecture-census.py --check → PASS; all 10 budgets at exact cap (central_event_types 91<=91, central_action_types 30<=30, services 57/44, framework modules 209<=209, noncomment lines 62239<=62239, named_compiler 1<=1, duplicate_event_writer_sinks 3<=3).
- pytest framework/outbox/tests → 61 passed, 0 skipped (real-PG17 + sandbox-redis table-drain sims ran).
- pytest framework/triggers/tests → 393 passed (v1 frozen + v2 + registry; 454 combined with outbox).
- pytest cabinet/scripts/tests/test_cog1_cutover.py → 14 passed (incl. real-PG disarm/enable rehearsal + the wrong-trigger-name negative control).
- pytest cabinet/scripts/tests/test_cognitive_phase1_rollback.py → 10 passed (footprint ratchet + digest teeth).
- pytest cabinet/scripts/tests/test_cog1_replay_hash.py → 20 passed (run added by the lead: no cluster had explicitly reported this §11.1 instrument suite).
- cabinet/evals/never-a-score/harness.py --self-test → 12/12 green.
- cabinet/scripts/ledger-status-parity.sh → GREEN (ids=349 md_rows=349); cabinet/scripts/check-layer-separation.sh → new=0.

Cluster re-runs accepted with transcripts: test_cog1_outbox_capture.py 24 passed / 0 skipped on PostgreSQL 17.10; v1 red-team + enforce 133 passed over 0-byte-diffed suites; consumer suites (test_task_events_watch.py + test_envelope_redteam.py) 108 passed; test_cog1_parity.py + test_cog1_fencing.py 52 passed (incl. raw-column/symmetric-predicate/floor/escalation mutants); test_egg_export.py 48 passed 1 skipped; evidence-detector/calibration/launcher-hardcode sweeps 55 passed; cognitive-phase1-rollback-rehearsal.py PASS ("only append-only operative history remains", 28/28 golden evals inside); lazy-import proof under a psycopg2-raising import hook; B1/B2 fresh baselines N=60, all p95 within x1.10+10ms — B1 ms: start 35.21→36.94, block 37.60→39.52, unblock 38.25→39.84, done 38.17→39.63; B2 ms: create 11.34→11.70, done 11.36→11.64 (outbox INSERT overhead ~1-2 ms/verb).

Still owed by the landing/done-flip protocol (§12.5, §11.1) — not by this artifact: the full land battery, the N≥50 kill-point loop with recorded evidence, master CI green 7/7 per-job after push, and the ≥7-day soak verdict lines. The soak and the F1 binding conditions gate CUTOVER eligibility, not this merge.


## Addendum — post-review delta (175ce93a), mini-reviewed

After the frozen review of f62a3820, one small delta commit landed before the
PASS flip, mini-reviewed by a fresh Opus checker (verdict: approve, 7/7 checks):

1. Shallow-checkout skip guard in test_cognitive_phase1_rollback.py — CI's
   shallow clone lacks the baseline SHA (git diff exit 128); the footprint
   ratchet now skips honestly there and provably still RUNS on full clones
   (10 passed, 0 skipped on this clone).
2. The F1 deferral is now MECHANICALLY ENFORCED, not just recorded:
   cog1-authority-flip.sh's 'outbox' verb REFUSES (exit 64, before any pointer
   write) while the §8.4 relay live-stream retarget seam is unimplemented
   (probe: COG1_LIVE_STREAM_TARGET absent from relay.py — fail-closed if
   relay.py is missing too). legacy/disarm/enable stay ungated; harness-only
   override env; header corrected to the honest not-yet-executable state;
   dedicated teeth test (refuse→64+no-write; override→writes; legacy ungated).
   The F1 binding eligibility conditions in this artifact stand unchanged —
   the seam + end-to-end routing rig + shadow-stuck mutant land under §12.3
   re-review before cutover eligibility; the interlock's probe token is the
   seam's own landing marker.

The Reviewed-Scope-Digest above binds the FINAL bytes (175ce93a). The four
frozen clusters' evidence applies to f62a3820; the delta's three files were
re-reviewed independently as above.
