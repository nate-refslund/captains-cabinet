# Cognitive Core Phase 2 — Shadow Temporal Epistemic World Model ("Cortex") — REV 2 (post-attack)

**Revision:** rev 2, 2026-07-19 — folds the four-lens plan-attack panel (architecture + adversarial-correctness on Fable; operations + governance on Opus). Every blocker/major is FIXED in-text or carries an explicit disposition in §14. Finding ids are namespaced: A-\* (architecture), C-\* (correctness), O-\* (operations), G-\* (governance).

**Parent:** `docs/cognitive-core-foundry.md` (Cortex charter §4.3 :86-96; invariants :49, :52, :53, :60, :61; Phase-2 charter + required simulations + exit :166-172; migration law :241-247; stop conditions :249-261; capacity law :148)
**Prior contracts:** `docs/plans/cognitive-core-phase-0-contract-2026-07-19.md` (template shape; budgets §3.1; scope semantics §3.2; canonicalization §3.3; never-a-score review question §5) · `docs/plans/cognitive-core-phase-1-contract-2026-07-20.md` (envelope v2 §4; outbox/relay §5-6; phase-local-twin rule §3; recorded debt §3 row `framework/events/schema.sql`)
**Grounding:** COG-2 grounding map (4 Opus readers + Fable synthesis over `b032dfdf`; premise-check HOLDS), cited as "ground §n"; plus the rev-2 attack panel, whose byte-verifications at `b032dfdf` (047 DDL, `relay.py`, `consequence.py`, `egg-export-manifest.txt`, `cabinet-ci.yml`, census validator, ledger row `:3345-3352`) are incorporated as grounding.
**Ground pin (plan authorship):** origin/master `b032dfdf`; CI run `29889434486` green per-job. **(A-m14)** This pin was authored in a different clone and is NOT verifiable from every tree; every header count and floor is PROVISIONAL until S0 re-pins current origin/master + a fresh green per-job CI run id — S0's re-pin is the authoritative baseline, and no header claim is relied on before it. Machine contract already declares `world_model: rebuildable_projection` (`cabinet/config/cognitive-architecture-contract.yml:85`). Behavioral floor: the Phase-0 targeted floor (2,050 passed, 5 skipped) plus the landed COG-1 suites; exact counts re-recorded at S0. The implementation wave re-runs the §12.1 dirty-guard/wave inventory before any edit.
**Runtime posture:** additive, shadow-only, read-only over authority. Cortex writes NO authoritative store, emits NO events, adds NO services.yml row, edits NO germline path, and is imported by NO authority/action code (mechanically gated, §7). Projection deletion is always safe by construction **at a frozen source state** (§7.3 retention contract — A-B3). The read pointer exists but is `none` for the whole phase (§9 risk 8).
**Provenance:** authored and self-ratified per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20 cognitive-masterplan continuous grant. Captain-law calibrations bound: (a) THIN SLICE — `tasks/task-event@1` plus exactly ONE legacy ledger adapter (consequence) (§2); (b) NEVER-A-SCORE — confidence is provenance/source-trust-weighted uncertainty with explicit unknown, never a collapsed quality scalar (§5.6, enforcement corrected per G-F3).

---

## 1. Purpose and optimization target

Phase 2 proves, on one bounded slice, that a disposable bitemporal projection over domain truth can answer "what did we believe, as of when, on what evidence" without ever becoming a second authority. The optimization target is the foundry's (:24): verified mission value per unit of Captain attention/time/cost/risk — never belief volume, coverage, or code size.

**Vector evidence (micro-measurables; each is a gate instrument, none is a scalar score):**

| id | measurable | today (evidence) | exit target |
|---|---|---|---|
| M1 | rebuild determinism | no projection exists (ground §1b.1) | identical canonical chained hash after 3 rebuilds from zero AND after physical-layer shuffle/duplication, **within one hash epoch** `(engine_version, trust_table_version, rank_table, source_set, frontier)` (A-m13); 3 rebuilds run as 3 subprocesses under 3 distinct `PYTHONHASHSEED` values (C-F3) |
| M2 | as-of correctness | leakguard fences retrieval but is not a queryable temporal store (ground §1b.3) | zero temporal leaks on seeded histories across both time axes, INCLUDING derived state (`status`/`superseded_by`/`contradicts` re-derived per cutoff — C-F7). **Honesty clause (A-B1/C-F2/O-B1):** both production sources this phase are single-clock (axis-degenerate); the two-axis proof runs through the production envelope-file adapter (§5.2a), a real fold/query path with no production feed this phase — declared, not hidden |
| M3 | contradiction + unknown honesty | no code models belief conflict (ground §1b.4) | conflicting beliefs coexist cross-linked with per-side provenance; zero-evidence queries return explicit `unknown`. **Honesty clause (C-F10):** no production event pair in this slice CAN contradict (§5.5); M3 is a declared fixture-proof through the production fold+query path; the first contradiction-capable source pairing is a named obligation of the next adapter phase |
| M4 | provenance completeness | n/a | 100% of beliefs resolve to ≥1 `event_id` + the universal provenance minimum; source purge (tombstone-model, §5.4b) flips status with lineage intact **across projection delete + rebuild-from-zero** (A-B3/C-F12) |
| M5 | shadow boundary | n/a | zero imports of `framework.cortex` from authority/action code; zero write attempts against any source; cross-cabinet ingest and unscoped queries fail closed; zero data-plane reads of the cortex cache path from forbidden trees (grep sweep — C-F20) |
| M6 | latency/storage envelope | unmeasured | as-of query p50/p95 + full-rebuild wall time + store bytes measured on the full pinned history in the nightly/opt-in path; CI runs a bounded history measurement-only (O-B4) |

**Refused metrics:** belief count, subjects covered, events folded, "% of enum modeled", LOC, module count. Activity is never success.

## 2. Phase-2 slice selection record — THIN SLICE (bound)

Unchanged in scope: the phase-2 slice is:

1. **v2 stream:** `tasks/task-event@1` — the COG-1 outbox (`cabinet/sql/047-officer-tasks-outbox.sql`), read as a table with the frontier law of §5.3 (A-B2/C-F1).
2. **exactly ONE legacy adapter:** the consequence ledger (`framework/fidelity/consequence.py`). **Justification corrected (A-m12/C-F5):** its supersession chains are ENRICHMENT chains (the identity tuple is ts-inclusive — `consequence.py:515-528` — so cross-time supersession of the same `(actor, action, subject)` does not occur by construction). What the adapter proves is the SEAM: deterministic synthetic provenance, history-preserving raw iteration behind the domain's own fences, translation-vs-collapse equivalence against `read_ledger()`, and legacy-regime belief validation. That is the real risk surface; "hardest translation" is withdrawn as the claim.
3. **(rev 2) envelope-file adapter** (§5.2a) — a production adapter in `adapters.py` that folds validated v2 envelope JSONL with independent `occurred_at`/`recorded_at`. No production source feeds it this phase; it is the two-axis and contradiction proof instrument AND the seam any future envelope-durable source uses. Declared openly — it is real fold/query code, not a test-only shim (C-F2 fix, C-F4/C-F9 seam discipline).

Undo-journal and org_events adapters remain **out of phase**. **Named later-phase obligation (C-F10):** the first source pairing capable of producing a real production contradiction (e.g. org_events × tasks on a shared subject) must land with a production-contradiction sim, since this slice cannot exercise one outside fixtures. No third production source folds until this slice's exit gates are green.

## 3. Component disposition table

| component | disposition | evidence |
|---|---|---|
| envelope v2 doorway (`envelope.py:862` `validate_any`; fail-closed) | **reuse — v2 + envelope-file streams ONLY (A-M7)** | `validate_any` gates every envelope-shaped ingest. Legacy consequence rows are structurally unrepresentable as v2 (no `recorded_at`, no uuid4 `correlation_id`) — they are NOT forced through `validate_any`; they validate at the belief level against `belief.v1.json` under the legacy provenance regime (§4, C-F13). The prior "validates every ingested envelope" claim is corrected |
| COG-1 outbox stream (047 DDL; `relay.py:695-751`) | **reuse (read-only source) — corrected semantics** | the table has NO `recorded_at` column (`occurred_at TIMESTAMPTZ DEFAULT NOW()` only) and `event_id` is NULL until relay backfill (047:63-66) — the prior "carries the bitemporal pair" claim is withdrawn (A-B1). Adapter pins `observation_time := occurred_at` (axes degenerate, declared) and folds only behind the §5.3 frontier (A-B2/C-F1) |
| relay pure row→v2 builder (`relay.py:403-455` `build_dispatch_fields`) | **reuse via allowlist (A-M8)** | the ONE row→v2 mapping; `adapters.py` imports it rather than re-implementing (drift-proof). S0 verifies it is importable pure; if impure, its pure core is extracted inside `framework/outbox` in the same wave (census delta counted). A byte-equivalence test pins adapter output to relay output on shared rows |
| canonical hashing (`recorder.py:144-162`; `cog1-replay-hash.py` chained pattern) | **reuse + extend** | one dialect, one place; cortex imports recorder's pure canonicalization. **(G-F5)** this is a PRIVATE symbol of a frozen germline module — recorded explicitly as a coupling; the recorder-vs-cortex byte-parity test is the standing tripwire, and any future germline recorder edit re-runs it; S0's import-purity check must clear before code |
| consequence ledger | **compose via ONE new adapter + a small ADDITIVE extend of `consequence.py` (A-M6/C-F5/O-B2)** | `read_ledger()` pre-collapses LWW and discards `(file,line)` — it cannot yield chains, so "single read path, no re-implementation" was self-contradictory as written. Resolution: add `iter_ledger_rows()` to `consequence.py` itself — a history-preserving iterator that reuses the module's OWN `_safe_ledger_files` symlink fence and `_is_consequence_row` shape filter and yields `(file, line, row)`. The adapter consumes it; zero filter logic is cloned. Fold sim-row policy is UNCONDITIONAL (sim rows always dropped, independent of `CABINET_SIM_MODE` — no env input to the pure fold; the decision is recorded in the fold manifest). Mandatory equivalence test: adapter chain-heads == `read_ledger()` survivors on shared fixtures incl. sim rows, symlinked files, equal-ts enrichment pairs |
| supersession prior art (org_runtime, undo `jid`) | **deferred — interface only** | unchanged |
| as-of fencing idiom (`leakguard.py`) | **reuse (test idiom) — with the C-F7 caveat** | the ts-scan is structurally blind to derived-state leaks (digest-valued link fields); sim 2 therefore adds the closure assertion (§8) beyond the leakguard idiom |
| sim rigs (`lib_cog1_harness.py`, mutant pattern, relay harness) | **extend (O-B5)** | the harness has no role/grant support (connects as superuser only) — the `cortex_ro` seam is NEW harness surface: idempotent `CREATE ROLE cortex_ro LOGIN` + `GRANT SELECT` provisioning + connect-as-role helper. Enumerated, not hidden under "reuse" |
| cog1-parity design (`task-sync-drift-falsifier.py`) | **compose + extend** | `cog2-parity-falsifier.py` clones the pattern; the parity invocation is added INSIDE `task-sync-drift-falsifier.py` (COG-1 precedent, falsifier :511-534) — `services.yml` stays BYTE-IDENTICAL (`git diff --quiet` clean; G-F7). Sampling frame corrected per C-F16 (§8 sim 6) |
| domain-local schema registry | **extend (fixtures only, zero code)** | unchanged |
| authoritative domains | **reuse read-only** | unchanged; plus the §7.3 retention contract they now explicitly owe the projection (C-F12) |
| Phase-0/1 review/verify tooling | **new phase-local twins** | unchanged; extraction stays recorded debt. **(O-B6)** the §7.1 import gate is NET-NEW (stdlib-`ast` walk + grep backstop) — the "check-layer-separation.sh idiom" characterization is withdrawn (that script only covers framework→instance/presets coupling and cannot express intra-framework deny rules) |
| Cortex engine + belief store + query API + contradiction representation + projection-side fence + read pointer + trust table | **new** | ground §1b items 1-7; §6 enumerates files |
| **retire** | **none** | unchanged |

## 4. The belief record (pinned field-by-field)

Schema authority: `framework/schemas/domains/cortex/belief.v1.json`.

| field | discipline |
|---|---|
| `belief_id` | DETERMINISTIC: recorder-dialect digest of `(kind, subject_key, dimension, provenance.event_id, adapter_ordinal)`. **(A-B3/C-F12) `claim_digest` is REMOVED from the identity tuple** — identity must survive content purge; `event_id` survives an outbox payload-NULL, so identity is stable across content loss. `adapter_ordinal` = 0-based index of this belief among the beliefs one adapter emits for one event (deterministic per adapter version). Never a build-time ULID/uuid (sim-1 mutant) |
| `kind` | closed enum per foundry:89, unchanged |
| `subject_key` | canonical domain-scoped key: `tasks/<task_id>`; `consequence/<identity-tuple-digest>` where the digest is over the ledger's OWN ts-INCLUSIVE identity tuple (A-m12 — matching the domain's semantics; divergence would change what parity means). Pinned per adapter, never free-text |
| `dimension` | **(A-m10/C-F10) NEW REQUIRED FIELD** — the claim dimension supersession and contradiction key on, pinned mechanically per adapter (§5.4/§5.5): tasks adapter → `status` (entity beliefs) / `occurrence` (observation beliefs); consequence adapter → `consequence`; envelope-file adapter → carried from the envelope's `payload_schema`-declared dimension. Never heuristic content comparison |
| `claim` | canonical JSON (recorder dialect), schema-resolved. `claim_digest` = recorder digest of canonical claim bytes — a STORED field, no longer identity. Post-purge: `claim` and `claim_digest` are ABSENT (§5.4b) |
| `source_time` | valid time. Outbox: `:= occurred_at`. Consequence: `:= ts` parsed-or-ABSENT (C-F6 — the adapter parses to the single UTC-second spelling or yields honest absence; it NEVER passes garbage through, unlike the cog1 `_utc_second` precedent; fixtures pin fractional/offset/garbage inputs). Envelope-file: `:= occurred_at` |
| `observation_time` | transaction time. Outbox: `:= occurred_at` (**axes degenerate — declared**, A-B1: capture is co-committed with the transaction, defensibly "when the system learned it"; `dispatched_at` is REJECTED — relay-owned, mutable, NULL for undrained rows, breaks M1). Consequence: `:= ts` or absent (degenerate). Envelope-file: `:= recorded_at` (the real two-axis path). `source_time ≤ observation_time` stays descriptive, never validated |
| `confidence` | fixed-point ppm int, derived at fold time from the versioned trust table, or ABSENT = unknown, never 0; always paired with `source_trust` |
| `source_trust` | `{table_version, producer_key}`. **(G-F4)** schema invariant in `source-trust.v1.json`: `producer_key` MUST be a source/component identity drawn from the adapter-declared producer set — an officer identity is structurally invalid (never-a-score latch, asserted by the panel re-check and the schema itself) |
| `provenance` | **(C-F13) single schema, two regimes, universal minimum:** `event_id` + `producer` + `stream_rank` are required on EVERY belief, no exceptions. The v2/envelope-file regime additionally requires the full envelope tuple (`cabinet_id, scope_kind, correlation_id, causation_id?, classification, payload_schema`, …). The legacy regime's allowed-absent set is ENUMERATED IN THE SCHEMA keyed by `stream_rank` — a v2-derived belief carrying legacy-shaped (half-empty) provenance is a structural rejection (pinned mutant). Missing scope levels absent, never sentinel-filled |
| `supersedes` / `superseded_by` | within-subject+dimension lineage; supersession-without-erase (foundry:53) |
| `contradicts` | `[belief_id…]`, symmetric, never auto-resolved; **stored SORTED** (every derived collection entering canonical bytes is sorted — C-F3) |
| `status` | derived, single-valued, pinned priority `source_purged > superseded > contradicted > asserted` — computed once from `(superseded_by?, contradicts≠∅?, purged?)` |
| `claim_completeness` | `inline \| ref_only \| purged` — `payload_ref` envelopes yield `ref_only`; the fold never derefs |

**Canonical-hash exclusion list:** unchanged (wall-clock ingest bookkeeping, index row ids, quarantine counters, cache state — excluded by construction; fold manifest hashed separately).

## 5. Derivation law (source → belief)

### 5.1 Pure deterministic fold, full-refold-only

`beliefs = fold(f, sort(events, K))`, `f` pure — **and (A-M6) env-free: no environment variable is a fold input** (sim-row policy is unconditional). Chained hash: recorder dialect per row, `acc = sha256(acc ‖ canonical_row)` over beliefs in `belief_id` order.

**(A-m11) Rows, never file bytes:** the canonical hash is computed by RE-PARSING and re-canonicalizing each JSONL row and chaining — never by hashing the file byte stream. The writer emits exactly the canonical bytes (`\n` line terminator, trailing newline present, `ensure_ascii=False` — non-ASCII passes through per recorder dialect), so writer bytes and re-derived bytes agree, and verification proves it.

**(A-m13) Hash-epoch law:** M1's "identical hash" is defined RELATIVE to the epoch tuple `(engine_version, trust_table_version, rank_table, source_set, frontier)`, all recorded in the fold manifest. Changing any element (a COG-7 source collapse, a trust edit, a new adapter) is an EPOCH BUMP — a new honest hash lineage, never a determinism regression. The belief MODEL survives source re-keying; the hash lineage deliberately does not.

**Convergence law:** unchanged — full-refold-only; incremental-arrival and rebuild-from-zero are the same computation. Suffix-checkpointing stays deferred behind a hash-equivalence gate.

### 5.2 Canonical sort key K — and the split of duties (A-B4)

`K = (observation_time, stream_rank, intra_stream_seq, event_id)` remains the pinned total FOLD-PROCESSING order, with:

- **(A-M5) null ordering pinned:** ABSENT `observation_time` sorts BEFORE all present values; ties resolve on the remaining components (total order preserved). Absent-`observation_time` beliefs are additionally EXCLUDED from observation-fenced answers (mirroring the existing source-time exclusion) — they appear only in unfenced current-belief queries.
- `stream_rank` enum: `0 = officer_tasks_outbox`, `1 = consequence ledger`, `2 = envelope-file`. Schema-frozen per engine version.
- `intra_stream_seq`: outbox `id` / consequence `(file, line)` from `iter_ledger_rows()` / envelope-file `(file, line)`.

**SUPERSESSION AUTHORITY IS NOT K (A-B4):** per-subject+dimension supersession is decided in the SOURCE's own total order — `(stream_rank, intra_stream_seq)` — because outbox `id` is the only order guarantee COG-1 gives and `occurred_at` (= transaction-start `NOW()`) can invert against commit order under long transactions. `observation_time` is a QUERY-FENCE AXIS ONLY, never the supersession authority. K orders fold processing and nothing about K's `observation_time` lead can invert a supersession chain. (Sim-1 gains a long-transaction seed: late `id`, early `occurred_at` — supersession must follow `id`.)

### 5.2a The envelope-file adapter (two-axis instrument)

Reads v2 envelope JSONL (each line `validate_any`-gated, fail-closed), both timestamps from the envelope. It is production code in `adapters.py` — the general seam for future envelope-durable sources — with no production feed this phase (declared in §2). Sims 2 and 3 ride it; sim seeds therefore traverse the SAME fold and query code as production streams (no test-only ingest seam — C-F4/C-F9 discipline).

### 5.3 Frontier, dedupe, snapshot, and the two clocks

- **(A-B2/C-F1) Outbox frontier law:** each fold reads its Postgres sources under ONE REPEATABLE READ snapshot (A-M9). Eligible outbox rows = `event_id IS NOT NULL AND id ≤ F`, where `F = min(id WHERE event_id IS NULL) − 1` if any NULL exists in-snapshot, else `max(id)`. Cortex deliberately TRAILS the relay; `F`, `max(id)`, and the lag are recorded in the fold manifest. The frontier NEVER advances past a NULL — so a late backfill can never land behind the frontier and be skipped. A NULL-`event_id` row older than a pinned age (default 24h) is surfaced in the manifest AND the parity verdict line as a frontier-blocker — never silently skipped, never folded. **S0 must answer:** does the relay ever backfill `failed_terminal_at` rows? If provably never, such rows are quarantined-with-receipt past the age threshold (decision recorded; sim-1 seeds the case either way).
- **Ingest dedupe by `event_id`** (unchanged); `idempotency_key` is recorded in provenance as the capture-stable secondary key.
- **Two-clock discipline:** unchanged in principle; note honestly that on production streams this phase the axes coincide (§4) and the distinction is exercised via §5.2a.

### 5.4 Supersession — via adapters, one state machine

- **v2 tasks adapter:** same `subject_key` + same `dimension`, later `(stream_rank, intra_stream_seq)` ⇒ supersedes (NOT later-K — §5.2).
- **consequence adapter:** consumes `iter_ledger_rows()` (§3); identity-tuple groups become explicit enrichment `supersedes` chains ordered by `(file, line)`; synthetic provenance: `event_id = digest("consequence:" + canonical_source_row)`, `producer = "framework/fidelity/consequence"`, `stream_rank = 1`; ts parse-or-absent (C-F6).
- **envelope-file adapter:** envelope verbatim, like v2.

**(§5.4b — A-B3/C-F12) Purge model, pinned:** purge = SOURCE-side tombstone ONLY. For the outbox: payload NULL'd, row + `event_id` + `occurred_at` survive ⇒ every refold (including rebuild-from-zero after projection deletion) deterministically regenerates the belief as a `source_purged` stub (claim absent, identity intact — possible because identity no longer embeds claim bytes). Day-file deletion on the consequence side is a **GAP, not a purge** (moved to sim 5); the consequence domain has no purge mechanism today and consequence purge is OUT OF SCOPE this phase (sim-4's purge arm runs on the outbox stream only). A cross-source purge-receipt stream is future work, not needed for this slice.

**Status state machine:** unchanged — single derived function, pinned priority, no double-transitions.

### 5.5 Contradiction — never LWW, and honest about reach

Definition unchanged (independent lineages, same `subject_key` + `dimension`, neither superseding ⇒ both stored, symmetric sorted cross-links, full conflict set surfaced). **(C-F10) Reachability declared:** in THIS slice no production pair can contradict — tasks is a single producer whose same-subject events supersede; consequence subjects are ts-inclusive-unique; the streams share no subject namespace. M3 is therefore a fixture-proof through production code (envelope-file adapter). Sim 3 adds: (i) a POSITIVE fixture — a known-conflicting pair MUST cross-link (kills the degenerate per-event-unique-dimension implementation); (ii) a same-producer/disjoint-correlation-chain seed with a PINNED verdict (supersedes, not contradicts — same producer = same lineage by definition here, pinned).

### 5.6 Unknown stays unknown + confidence — NEVER-A-SCORE (bound)

- Unknown semantics unchanged. **(C-F11) Three cases pinned distinct:** zero-evidence subject ⇒ explicit `unknown`; subject whose only belief is `source_purged` ⇒ the belief WITH its status (never `unknown` — purged ≠ ignorant); scope-mismatch ⇒ HARD ERROR (§7.4 — denial never masquerades as ignorance; mutant pinned).
- Trust-table mechanics unchanged (versioned, producer-keyed, hashed rebuild input, static-at-derivation, absent-producer ⇒ absent confidence) + the G-F4 producer-identity schema invariant.
- **(G-F3) Never-a-score enforcement CORRECTED:** the previously cited `never-a-score/harness.py` C1 + token sweeps give cortex ZERO coverage (C1 scans golden-eval-scalar tokens; C2 is recorder-only AST) — that citation is withdrawn. Cortex's REAL mechanical guards, stated plainly: (1) the §7.1 import gate (authority/action cannot reach the API this phase); (2) the SHAPE guard — no bare-scalar confidence accessor exists; the query API returns only the full tuple `(value?, source_trust, provenance, status, conflict_set)`. Both land as PERMANENT CI tests (not phase-scoped manual gates): a standing ratchet test fails the suite if `query.py` ever grows a bare-scalar accessor, so the later reader-wiring phase INHERITS the guard and must amend it consciously. (3) SCOPE — confidence never aggregates per-officer/per-candidate, never feeds Gate/trust-ladder/promotion. The panel re-asks Phase-0 question 10 against THESE guards, not the withdrawn citation.

## 6. Storage decision and proposed file surface

**Storage:** unchanged — belief JSONL canonical + disposable SQLite index + fold manifest, under `cabinet/cache/cortex/`; Postgres rejected. **Refinements:** (A-m11) hash = re-derived rows, never file bytes (§5.1). **(C-F15) Serve-time binding:** `query.py` verifies the manifest's belief-store hash against the JSONL on open and at a pinned revalidation interval BEFORE serving from the index; mismatch ⇒ REFUSE (no window where a corrupt canonical store is served from an intact index). Index rebuilds are never fully silent: each writes a receipt surfaced in the parity verdict line.

| file | purpose |
|---|---|
| `framework/cortex/__init__.py` | package boundary; import-inert |
| `framework/cortex/belief.py` | record, validation (two-regime provenance schema), canonical bytes, identity, chained hash |
| `framework/cortex/engine.py` | pure fold: snapshot read, frontier law, dedupe, K, source-order supersession, contradiction post-pass, status, atomic JSONL write, fold manifest (epoch tuple, frontiers, seen-set intervals, lag, frontier-blockers) |
| `framework/cortex/query.py` | as-of both axes with per-cutoff derived-state re-derivation (C-F7), conflict sets, explicit unknown, purged-vs-unknown-vs-denied triad, scope fence, serve-time hash verification |
| `framework/cortex/adapters.py` | THREE adapters: tasks-outbox (via relay's allowlisted pure builder), consequence (via `iter_ledger_rows()`), envelope-file; deterministic synthetic provenance; rank table |
| `framework/fidelity/consequence.py` | **EXTEND (additive only):** `iter_ledger_rows()` history-preserving iterator reusing the module's own fences (A-M6); zero changes to existing functions; dirty-guarded, non-germline (S0 re-verifies) |
| `framework/schemas/domains/cortex/belief.v1.json`, `.../source-trust.v1.json` | registry-resolved; provenance regimes + producer-identity invariant baked into the schemas |
| `cabinet/config/cortex-source-trust.v1.yml` | versioned trust table; hashed rebuild input |
| `cabinet/cache/cortex/beliefs.jsonl` + `cortex-index.sqlite3` + `fold-manifest.json` | runtime artifacts (gitignore verified: `cabinet/cache/*`, `cabinet/logs/*`) |
| `cabinet/scripts/cog2-rebuild.py` | rebuild CLI + `--provision-ro` (idempotent `CREATE ROLE cortex_ro LOGIN` + enumerated grants — G-F6) |
| `cabinet/scripts/cog2-belief-hash.py` | hash instrument |
| `cabinet/scripts/cog2-parity-falsifier.py` | parity cycle — authoritative-frame sampling (§8 sim 6); FORBIDDEN from importing `framework.cortex.adapters` (C-F17, enforced by the import gate) |
| `cabinet/scripts/cognitive-phase2-rollback-rehearsal.py` | **(O-B3) named explicitly** — clones the Phase-0/1 rehearsal incl. `must_remain_unchanged` byte-diff (G-F2) |
| seven test suites (unchanged names) | §8, with rev-2 hardened seeds/mutants |
| `cabinet/scripts/verify-cognitive-phase2.sh` | phase-local twin; net-new AST import gate; `READY_FOR_CI` |
| `cabinet/scripts/cognitive-phase2-review-scope.py` | review-to-bytes binder |
| `cabinet/scripts/egg-export-manifest.txt` | **(O-B3) EDITED in the landing commit:** `delete` + `expect-absent` lines for `verify-cognitive-phase2.sh`, `cognitive-phase2-review-scope.py`, `cognitive-phase2-rollback-rehearsal.py`; `test_egg_export.py` phase list extended in the same commit (`docs/plans` is already wholesale-excluded — the .md/.yml need no lines) |
| `docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml` | §12.4, now incl. `must_remain_unchanged` |
| `~/.cabinet/state/cog2-read-pointer` | `none` all phase |
| operative ledger + plan parity rows | COG-2 status flip (row exists at ledger `:3345` — verified by the ops lens; §12.5 is a flip, not an add) |

No listed file is germline at baseline; re-checked fresh at S0 and before commit.

## 7. Shadow boundary — mechanical gates, not doctrine

**7.1 Zero calls from authority/action code — NET-NEW gate (O-B6):**
- Forbidden-importer rule unchanged (frontdoor/acting/authority/action lanes/officer runners/live-verb scripts; baseline-zero, shrink-only). The gate is a NEW stdlib-`ast` import-graph walk + grep backstop in `verify-cognitive-phase2.sh` AND `test_cog2_fencing.py` (scratch-tree mutant) — NOT a `check-layer-separation.sh` extension (that citation withdrawn). `cog2-parity-falsifier.py` is added to the forbidden-importer set for `framework.cortex.adapters` specifically (C-F17).
- **Reverse gate, corrected scope (G-F1):** the allowlist applies to FRAMEWORK-MODULE imports: `framework.triggers.envelope`, `framework.triggers.schema_registry`, `framework.evidence.recorder` (pure canonicalization), `framework.outbox.relay` (ONLY `build_dispatch_fields` — A-M8; S0 purity check, extraction fallback per §3), `framework.fidelity.consequence` (ONLY `iter_ledger_rows`), own package. Third-party allowlist pinned separately: `psycopg2` (lazy, in-function, relay precedent), `yaml`, stdlib (`sqlite3`, `json`, `hashlib`, …). Any OTHER framework import fails the gate; any other third-party import fails it too.
- **(C-F20) Data-plane backstop:** the grep sweep over forbidden trees additionally flags the literal `cabinet/cache/cortex` path and a `cortex` token. Residual risk stated honestly: the import gate covers modules, the sweep covers the obvious data-plane bypass (`open()` on the store); a determined covert bypass is beyond mechanical reach this phase and is accepted as residual, revisited when the read pointer first flips.

**7.2 Read-only-by-construction (G-F6 refined):** `cortex_ro` role, SELECT-only, grant list ENUMERATED and minimal: `officer_tasks_outbox`, `officer_tasks` (the parity falsifier's sample frame) — nothing else; provisioning = `cog2-rebuild.py --provision-ro` (idempotent SQL; run by harness/CI; the one prod invocation is a named runbook line in the review artifact). `test_cog2_fencing.py` attempts UPDATE and INSERT under the role and asserts refusal, and asserts the grant catalog matches the enumerated list exactly. Files opened read-only; no write path outside `cabinet/cache/cortex/`.

**7.3 Projection-loss-safety + retention contract:** unchanged design, PLUS **(C-F12) the previously implicit dependency now declared:** rebuild-from-zero is well-defined only under a NO-PRUNE RETENTION CONTRACT on the sources — outbox rows are never deleted (payload-NULL is the only purge), consequence files are append-only-retained. This contract is what the sources owe the projection; a future retention/compaction change on either source must re-open this section (tripwire: the gap classifier's genesis-shift alarm, §8 sim 5). "Deletion is always safe" is precise now: deleting the PROJECTION is always safe; deleting SOURCE history is a domain decision the projection detects and reports, never masks.

**7.4 Cross-cabinet fail-closed (C-F19 hardened):** ingest fence refuses foreign `cabinet_id`, `classification: cross_cabinet`, sentinel ids — AND an ABSENT `cabinet_id` on any envelope-path ingest (absent ≠ local; absent fails closed), AND any `validate_any`-FAILING envelope — every refusal writes a quarantine receipt; silent skip is itself a pinned mutant failure (a silent drop is an undetected loss the parity frame must never mask). Query fence unchanged: missing/unresolvable/mismatched scope ⇒ HARD ERROR, never empty-success.

## 8. Gate simulations — tests-first mutant table (rev-2 hardened)

All suites on `EphemeralPG17` (+ new ro-role seam) under `python3.12`, macOS + Linux CI (COG-1 postgres service container verified present in `framework-tests` by the ops lens; S0 re-confirms).

| # | gate | seeds (rev-2 additions bold) | asserts (rev-2 additions bold) | negative-control mutants (must FAIL) |
|---|---|---|---|---|
| 1 | **deterministic rebuild** | scripted outbox history; consequence JSONL; **mid-sequence NULL-`event_id` row → fold → backfill → refold (frontier pinned both times)**; **long-transaction seed: late `id`, early `occurred_at`**; **physical heap shuffle after seeding (scattered in-place UPDATEs / delete+reinsert prefix — C-F4)** | 3 rebuilds **as 3 subprocesses under 3 distinct `PYTHONHASHSEED` values (C-F3)** ⇒ identical hash; shuffle/dup ⇒ identical; **engine SELECT string-pinned to carry `ORDER BY id` (`_SELECT_SQL` literal pattern)**; recorder byte-parity; **supersession follows `id`, not `occurred_at`, on the long-tx seed (A-B4)** | arrival-order builder; fresh-ULID builder; **frontier advancing past a NULL row (C-F1)**; **`dispatched_at`-reading adapter — refold after simulated redelivery differs (C-F2)**; **set-iteration-order `contradicts` (can only fail under the subprocess harness)** |
| 2 | **temporal fence** | correction at obs-T3 about src-T1 **via the envelope-file adapter (production two-axis path)**; **same-second correction + cutoff seed, both intra-second K orderings (C-F8)**; **out-of-order arrival: earlier-`observation_time` event ingested after a later one (C-F9)** | as-of answers **re-derive `status`/`superseded_by`/`contradicts` from the sub-history `observation_time ≤ cutoff` (C-F7)** — T2 answer shows `status: asserted`, empty conflict set, no `superseded_by`; **closure assertion: every belief_id appearing anywhere in an answer (incl. link fields) resolves within the cutoff**; fence pinned INCLUSIVE-≤, leak predicate `ts > cutoff` (C-F8) | `source_time`-only fence; **rowid/`ingested_at`-keyed fence (fails only on the out-of-order seed)**; stored-final-status server (fails the T2 assert) |
| 3 | **contradiction + unknown** | two-producer conflict via envelope-file adapter; zero-evidence subject; **purged-only subject; scope-mismatch query (C-F11)**; **same-producer/disjoint-correlation seed (pinned verdict: supersedes)**; **positive fixture: known-conflicting pair MUST cross-link (C-F10)** | both rows, symmetric sorted links, full conflict set + tuples; explicit `unknown`; **purged-only ⇒ status-bearing answer, never `unknown`; scope-mismatch ⇒ HARD ERROR** | silent LWW; default-for-unknown; bare-scalar accessor; **per-event-unique-dimension degenerate (fails the positive fixture)**; **`unknown` returned for scope-mismatch (denial-as-ignorance)** |
| 4 | **provenance + purge** | full history; **outbox payload NULL'd (tombstone purge, §5.4b) → warm refold → PROJECTION DELETED → rebuild-from-zero (C-F12)** | universal provenance minimum on every belief; post-purge `source_purged` with lineage intact; **post-delete rebuild reproduces the EXACT pinned belief set + hash (identity survives content loss)** | provenance-dropping builder; empty-provenance acceptance; **v2 belief carrying legacy-shaped provenance accepted (C-F13)**; **claim-bytes-derived belief_id (post-purge rebuild diverges — A-B3)** |
| 5 | **corruption + gap** | JSONL byte-flip; **corrupt JSONL with INTACT index (C-F15)**; **gap taxonomy seeds (C-F14/A-M9): (a) rollback-burned sequence id — benign; (b) deleted early row below frontier — breach; (c) genesis shift — breach**; consequence day-file deletion (**reclassified here from sim 4**) | detect ⇒ REFUSE ⇒ rebuild restores hash; **query against intact index with corrupt JSONL REFUSES (serve-time hash binding)**; gap = SEEN-SET REGRESSION against the prior manifest (repeatable-read snapshot), sequence holes classified benign; zero fabricated bridging beliefs; **index rebuilds write receipts** | silent self-healing; gap-bridging inference; **hole-as-breach classifier (fails seed a)**; **forward-window checker blind to below-frontier deletion (fails seed b)** |
| 6 | **shadow parity** | live-shaped seeded history; **deleted-subject seed: one subject's beliefs removed from the JSONL (C-F16)**; **seeded adapter mis-translation: equal-ts enrichment order flipped (C-F17)**; **breach → unsampled → breach sequence (C-F18)** | sampling frame = the AUTHORITATIVE side (distinct task_ids from `officer_tasks`/outbox; identity chains from `consequence.read_ledger()` — the domain's own reader, NEVER cortex adapters); an in-slice authoritative subject Cortex cannot answer IS a breach; **sticky re-sampling: breach subjects force-included every cycle until clean**; per-day sample floor; second-consecutive-breach ⇒ captain card; doctor-probed | enum-membership predicate; **store-sampled frame (structurally cannot fail the deleted-subject mutant — the tell)**; **adapter-derived ground truth (f(x)==f(x); fails the mis-translation seed)**; **memoryless re-sampler (fails the escalation seed)** |
| 7 | **cross-cabinet + boundary** | foreign/sentinel/`cross_cabinet` envelopes; **ABSENT-`cabinet_id` envelope; `validate_any`-FAILING envelope (C-F19)**; scope-less/mismatched queries; UPDATE+INSERT under `cortex_ro`; scratch-tree forbidden import; **forbidden-tree `open()` of the cache path (grep sweep — C-F20)** | every refusal writes a quarantine receipt — **absent-id and validator-fail included; silent skip = failure**; HARD-ERROR fences; ro refusal + grant-catalog match; import gate red; **standing no-bare-scalar ratchet green (G-F3)** | empty-success fence; quarantine-without-receipt; **absent-cabinet_id folded as local**; **validator-fail silently skipped** |

**Measurement gate (M6, exit :172) — (O-B4) CI-safe:** CI (`framework-tests`, 15-min budget) runs a BOUNDED history (5,000 outbox + 500 consequence rows), measurement-only — numbers recorded, ceilings NOT asserted. The FULL pinned history (≥50,000 + ≥5,000, ≈90 live-rate days, rates recorded at S0) runs opt-in (`COG2_FULL_HISTORY=1`) and in the nightly falsifier context. Ceilings (as-of p95 ≤ 250ms; full rebuild ≤ 60s; store ≤ 5× source bytes) are asserted ONLY under `COG2_ENFORCE_P95=1` on a quiet host — the exact `COG1_ENFORCE_P95` precedent. The exit-gate evidence is the full-history measured numbers in the review artifact; later reviews may tighten ceilings, never loosen.

## 9. The twelve grounding risks — dispositions (rev-2)

| # | risk | disposition |
|---|---|---|
| 1 | storage | RESOLVED (§6) + serve-time hash binding (C-F15) |
| 2 | canonical serialization | RESOLVED (§5.1) + rows-not-bytes pinned, newline/`ensure_ascii` pinned, sorted collections (A-m11, C-F3) |
| 3 | fold-order determinism | RESOLVED (§5.2-5.3): full-refold + frontier law + repeatable-read snapshot + subprocess hash-seed harness; supersession authority split from K (A-B4) |
| 4 | supersession composition | RESOLVED (§5.4): source-order authority; purge tombstone model; status single derived function |
| 5 | confidence semantics | RESOLVED (§5.6) with CORRECTED enforcement citation + standing ratchet (G-F3) + producer-identity invariant (G-F4) |
| 6 | slice | RESOLVED (§2), justification honesty-corrected (A-m12); contradiction-capable source = named next-phase obligation (C-F10) |
| 7 | `payload_ref` | RESOLVED (§4), unchanged |
| 8 | read pointer | RESOLVED, unchanged (`none` all phase) |
| 9 | Phase-1 schema.sql debt | RE-DEFERRED, unchanged (not on this surface) |
| 10 | fourth-authority / COG-7 | RESOLVED (§7.3) + hash-epoch law makes COG-7 re-keying an epoch bump, not a regression (A-m13) |
| 11 | census/A13 | RESOLVED (§10, §12.5); allowance integers at commit (validator requires positive ints — ops verification) |
| 12 | latency/storage method | RESOLVED (§8 measurement gate, CI-bounded per O-B4); no compaction; growth alarmed via parity verdict store-size field; source retention contract §7.3 |

## 10. Census amendment + budgets

Unchanged shape; both allowance rows land in the same commit as the first framework delta, `additional` as MEASURED positive integers (validator `cognitive-architecture-census.py:278`). **Clarification (A-M6/A-M8):** the additive `iter_ledger_rows()` lines in `consequence.py` (and, if the S0 purity check forces it, an extracted pure builder in `framework/outbox`) count against the SAME `framework_production_noncomment_lines` allowance — the line ceiling (1,800) covers all framework deltas of this phase wherever they land; a builder extraction also consumes +1 of the module allowance (planning estimate stays 5 + 1 contingency, measured at commit). Non-moving budgets unchanged (enums, services, sinks, compiler, layer counts).

## 11. Exit gates (foundry :172 verbatim, mapped)

| clause | instrument | evidence artifact |
|---|---|---|
| identical canonical hash after three rebuilds | sim 1 (subprocess triple + physical shuffle + backfill/refold pins), within one hash epoch | recorded hashes + epoch tuples in the review artifact |
| correct as-of answers on seeded histories | sim 2 (sub-history re-derivation + closure + boundary + out-of-order seeds) | suite run + fixtures |
| contradictions are preserved | sim 3 (incl. positive cross-link fixture; declared fixture-proof, §1 M3 honesty clause) | suite run |
| unknown remains unknown | sim 3 triad + sim 5 gap case | suite run |
| cross-Cabinet reads fail closed | sim 7 (incl. absent-id + validator-fail quarantine) | suite run + receipts |
| projection loss cannot lose authoritative data | sims 1/4/5 (incl. purge→delete→rebuild) + §7.3 retention contract | rebuild transcripts |
| zero calls from authority/action code | §7.1 net-new AST gate + grep/data-plane sweep + standing ratchet | gate output, CI green per-job |
| shadow query latency and storage envelope measured | §8 M6 full-history numbers (nightly/opt-in path) | measured numbers beside ceilings in the review artifact |

Plus the 7-day parity soak (authoritative-frame, sticky re-sampling) before the `done` flip. Gate law unchanged: fix or roll back, never lower a threshold.

## 12. Tests-first sequence, reviews, rollback, landing

### 12.1 S0 ground refresh (before any edit)

As rev-1, PLUS: verify relay backfill semantics for `failed_terminal_at` rows (pin the §5.3 decision); verify `build_dispatch_fields` importable pure (else trigger the §3 extraction fallback); verify recorder canonicalization importable pure (G-F5); dirty-guard now also covers `framework/fidelity/consequence.py` (EXTENDED, not read-only) and `cabinet/scripts/egg-export-manifest.txt` + `cabinet/scripts/tests/test_egg_export.py` (EXTENDED — O-B3); measure live rates; confirm the postgres service container; provision-ro seam dry-run; `.gitignore` no-edit decision re-verified.

### 12.2 Tests-first order

As rev-1 (suites 1-8 with the rev-2 seeds/mutants land failing-for-the-right-reason before implementation), with one addition: **step 0 —** the standing no-bare-scalar ratchet and the AST import gate land first (they gate everything after). M6 harness last. Implementation follows; soak starts after green-on-master.

### 12.3 Review loop

Unchanged, with the panel's questions updated: never-a-score question 10 is re-asked against the ACTUAL guards (§5.6 (1)-(3)), not the withdrawn harness citation; plus: does supersession ever consult `observation_time`? does any fold input come from the environment? does rebuild-after-purge reproduce the pinned set?

### 12.4 Rollback manifest

As rev-1, PLUS **(G-F2)** a `must_remain_unchanged:` block covering the Phase-0 ∪ Phase-1 protected-surface union (`services.yml`, `emitter.py`, `classifier.py`, `authority-matrix.yml`, `learning/gate.py`, `framework/authority`, `framework/evidence`, `captain-vetoes.yml`, `.layer-separation-{baseline,allowlist}`) — cortex touches none, so the rehearsal's `git diff --quiet` per-path check passes; without the block the cloned rehearsal's coverage test (`test_cognitive_phase1_rollback.py:169` pattern) fails. Code inverse additionally restores `consequence.py`, `egg-export-manifest.txt`, and `test_egg_export.py` from the S0 SHA. Rehearsal script is the named `cognitive-phase2-rollback-rehearsal.py` (§6).

### 12.5 Landing protocol + ledger mechanics (A13)

As rev-1 (COG-2 row already exists at ledger `:3345` — a status FLIP, verified), PLUS the **egg-manifest step (O-B3):** the landing commit adds the three `delete`+`expect-absent` lines and extends the `test_egg_export.py` phase list; the land battery includes `test_egg_export.py` green. Provenance lines unchanged.

## 13. Non-goals, stop conditions, capacity law

As rev-1, with additions: no production feed for the envelope-file adapter this phase; no consequence purge mechanism; no source retention/compaction changes (a domain retention change trips §7.3's re-open clause); no bare-scalar accessor ever (standing ratchet outlives the phase). Stop conditions and capacity law inherited unchanged; phase-local tripwires now also include: a frontier-blocker older than the pinned age that S0's relay-semantics decision cannot explain, and any grep-sweep hit on the cortex cache path from a forbidden tree. Hygiene note unchanged.

## 14. Attack-finding disposition register (rev 2 — every blocker/major, plus minors)

| finding | disposition | where |
|---|---|---|
| A-B1 / C-F2 / O-B1 (no `recorded_at` on source) | **FIXED** — `observation_time := occurred_at` pinned; degeneracy declared; two-axis proof moved to the production envelope-file adapter | §3, §4, §5.2a, M2 |
| A-B2 / C-F1 (NULL `event_id`) | **FIXED** — frontier law: `event_id IS NOT NULL`, never past earliest NULL, lag + blockers in manifest; `failed_terminal` decision pinned at S0; seeds + frontier mutant | §5.3, §8 sim 1, §12.1 |
| A-B3 / C-F12 (purge vs refold) | **FIXED** — `claim_digest` dropped from identity; purge = source tombstone (outbox only); day-file deletion reclassified as gap; retention contract declared; purge→delete→rebuild sim pinned | §4, §5.4b, §7.3, §8 sim 4 |
| A-B4 (supersession inversion) | **FIXED** — supersession authority = `(stream_rank, intra_stream_seq)`; `observation_time` = fence axis only; long-tx seed | §5.2, §8 sim 1 |
| A-M5 (K null-undefined) | **FIXED** — absent-first ordering + fence exclusion pinned | §5.2 |
| A-M6 / C-F5 / O-B2 (consequence read path) | **FIXED** — additive `iter_ledger_rows()` in `consequence.py` (declared extend); unconditional sim-row policy (env-free fold); equivalence test | §3, §5.1, §6 |
| A-M7 (legacy ≠ v2 envelope) | **FIXED** — legacy validates at belief level; `validate_any` claim narrowed to envelope-shaped streams | §3, §4 |
| A-M8 (mapping duplication) | **FIXED** — relay's pure `build_dispatch_fields` allowlisted + equivalence test; extraction fallback if impure at S0 | §3, §7.1, §10 |
| A-M9 / C-F14 (BIGSERIAL gaps) | **FIXED** — seen-set regression + repeatable-read snapshot + gap taxonomy + both-direction seeds | §5.3, §8 sim 5 |
| A-m10 / C-F10-dimension | **FIXED** — `dimension` field added, adapter-pinned mechanically | §4, §5.4/5.5 |
| A-m11 (bytes vs rows) | **FIXED** — re-parse hashing + newline/ASCII discipline pinned | §5.1 |
| A-m12 (overstated consequence claim) | **FIXED** — justification rewritten honestly; ts-inclusive subject keys pinned | §2, §4 |
| A-m13 (COG-7 hash lineage) | **FIXED** — hash-epoch law | §5.1, §9 r10 |
| A-m14 (unverifiable pin) | **FIXED** — header claims provisional-until-S0, S0 authoritative | header |
| C-F3 (hash-seed nondeterminism) | **FIXED** — sorted collections + 3-subprocess distinct-seed harness | §4, §8 sim 1 |
| C-F4 (arrival-order seam) | **FIXED** — physical heap shuffle + `ORDER BY` string pin | §8 sim 1 |
| C-F6 (legacy ts passthrough) | **FIXED** — parse-or-absent, garbage fixtures | §4 |
| C-F7 (derived-state leak) | **FIXED** — per-cutoff re-derivation + closure assertion | §5.5-adjacent query law, §8 sim 2 |
| C-F8 (boundary semantics) | **FIXED** — inclusive-≤, `ts > cutoff` predicate, same-second seed | §8 sim 2 |
| C-F9 (ingest-order proxy) | **FIXED** — out-of-order seed + rowid mutant | §8 sim 2 |
| C-F10 (unreachable contradiction) | **FIXED (honesty) + DEFERRED (substance):** fixture-proof declared; first contradiction-capable source pairing = named next-phase obligation — real production contradiction is impossible within the thin slice, and widening the slice to manufacture one would violate the capacity law | §1 M3, §2, §5.5 |
| C-F11 (unknown/purged/denied) | **FIXED** — triad pinned + mutants | §5.6, §8 sim 3 |
| C-F13 (two-regime laundering) | **FIXED** — universal minimum + schema-enumerated allowed-absent + regime-binding mutant | §4, §8 sim 4 |
| C-F15 (refuse-to-serve window) | **FIXED** — serve-time hash binding + rebuild receipts | §6, §8 sim 5 |
| C-F16 (sampling frame) | **FIXED** — authoritative-side frame + deleted-subject mutant | §8 sim 6 |
| C-F17 (tautological ground truth) | **FIXED** — domain-reader requirement + falsifier import ban + mis-translation seed | §8 sim 6, §7.1 |
| C-F18 (breach continuity) | **FIXED** — sticky re-sampling + escalation seed | §8 sim 6 |
| C-F19 (absent-id / validator-fail) | **FIXED** — fail-closed on absence, quarantine-with-receipt for validator failures, silent-skip mutant | §7.4, §8 sim 7 |
| C-F20 (data-plane bypass) | **FIXED (partial) + ACCEPTED residual** — path/token sweep added; covert bypass beyond mechanical reach this phase, stated honestly, revisited at read-pointer flip | §7.1 |
| O-B3 (egg manifest leak) | **FIXED** — manifest lines + test list + landing step + rollback restore | §6, §12.1, §12.5, §12.4 |
| O-B4 (CI timeout/flake) | **FIXED** — bounded CI history measurement-only; full history nightly/opt-in; `COG2_ENFORCE_P95` precedent | §8 measurement gate |
| O-B5 (harness relabel) | **FIXED** — extend, seam enumerated | §3, §7.2 |
| O-B6 (layer-sep mischaracterization) | **FIXED** — net-new AST gate stated | §3, §7.1 |
| G-F1 (self-contradicting allowlist) | **FIXED** — framework-scope allowlist + pinned third-party allowlist | §7.1 |
| G-F2 (missing must_remain_unchanged) | **FIXED** — Phase-0∪1 union block in the manifest | §12.4 |
| G-F3 (mis-cited enforcement) | **FIXED** — citation withdrawn; real guards named; standing ratchet added | §5.6 |
| G-F4 (producer-key latch) | **FIXED** — schema invariant, panel re-check | §4 |
| G-F5 (private germline symbol) | **FIXED (recorded)** — coupling recorded, byte-parity tripwire, S0 purity check | §3 |
| G-F6 (ro under-specified) | **FIXED** — grants enumerated, provisioning named, catalog-match test | §7.2 |
| G-F7 (services.yml intent) | **FIXED** — byte-identical stated at the edit site | §3 |
| Phase-1 schema.sql debt | **RE-DEFERRED** (unchanged, off-surface) | §9 r9 |

---

## VERDICT

Every blocker and major resolves to a concrete, mechanical design change — and in nearly every case the resolution IS the fix the attacking lens itself specified (frontier predicate, occurred_at pinning, identity-without-claim-digest, source-order supersession, sub-history re-derivation, authoritative-frame sampling, egg-manifest lines, allowlist scoping, must_remain_unchanged block). Adopting reviewer-prescribed fixes does not create novel unreviewed architecture; the two genuinely new pieces of surface (the envelope-file adapter and `iter_ledger_rows()`) are small, single-purpose, and each carries its own pinned equivalence/mutant test. Checking the four readiness criteria: all six-plus-one gate sims are now sound on paper with mutants that fail the exact escapes the panel found (the deleted-subject parity mutant, the frontier-past-NULL mutant, the corrupt-JSONL-intact-index mutant, the post-purge-rebuild pin); the shadow boundary is mechanical end-to-end (net-new AST gate with a scoped allowlist, enumerated ro grants, path-literal sweep, standing ratchet) with its one residual risk stated rather than hidden; the thin slice held (no new production sources — the envelope-file adapter has no feed and the consequence extend is additive plumbing); and never-a-score is reconciled against the REAL guards with the false citation withdrawn and a permanent ratchet added. The honesty clauses (axis degeneracy, fixture-proof contradiction) trade claimed coverage for true claims, which is the foundry's own law. Remaining risk is implementation-tier and S0-conditional (relay backfill semantics, builder purity), and both conditions are pinned as S0 gates with decided fallbacks — not open design questions.

COG-2 PLAN: READY

## Changelog (what the attack changed)

1. **Time model:** `observation_time := occurred_at` for the outbox (no `recorded_at` exists on the table); production axes declared degenerate; two-axis proof moved to a new production envelope-file adapter.
2. **Identity:** `claim_digest` removed from `belief_id`; identity = `(kind, subject_key, dimension, event_id, adapter_ordinal)` — survives purge; new required `dimension` field.
3. **Frontier law:** fold only behind the last contiguous backfilled `event_id`, under a repeatable-read snapshot; lag + blockers in the manifest.
4. **Ordering split:** supersession authority = source order `(stream_rank, intra_stream_seq)`; `observation_time` demoted to fence axis; K null-ordering pinned.
5. **Purge redefined:** source-side tombstone (outbox only); day-file deletion reclassified as gap; explicit no-prune retention contract on sources.
6. **Consequence seam:** additive `iter_ledger_rows()` in `consequence.py` replaces the impossible "single read path" compose; env-free fold (unconditional sim-row policy); equivalence test vs `read_ledger()`.
7. **Query correctness:** as-of answers re-derive status/links per cutoff + closure assertion; inclusive-≤ boundary; serve-time store-hash verification; unknown/purged/denied triad.
8. **Parity rebuilt:** authoritative-side sampling frame, domain-reader ground truth, falsifier banned from cortex adapters, sticky breach re-sampling.
9. **Gap detection:** seen-set regression + taxonomy, replacing naive BIGSERIAL contiguity.
10. **Hardened harness:** subprocess hash-seed triple rebuild, physical heap shuffle, `ORDER BY` string pin, ~15 new seeds/mutants across the seven suites.
11. **Governance:** allowlist scoped (framework vs third-party, relay pure builder + consequence iterator admitted), never-a-score citation corrected + standing bare-scalar ratchet, producer-identity schema invariant, `must_remain_unchanged` block in the rollback manifest, egg-export-manifest + `test_egg_export.py` landing step, ro grants enumerated with named provisioning, `services.yml` byte-identical stated.
12. **CI economics:** M6 bounded in CI (measurement-only), full history nightly/opt-in, ceilings behind `COG2_ENFORCE_P95`.
13. **Honesty clauses:** contradiction declared fixture-proof (first contradiction-capable source = named next-phase obligation); hash-epoch law for COG-7; header pin provisional-until-S0; harness relabeled extend; "check-layer-separation idiom" and "hardest translation" claims withdrawn.

COG-2 PLAN: READY