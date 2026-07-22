# Checkpoint review — feat/cog2-unit1-rebuild-core (cp1)

**Unit 1 of COG-2** (shadow temporal world model "Cortex"): the deterministic-rebuild core.
Branch off master b393f41b (COG-2 contract). Contract: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md.

## What lands
- `framework/cortex/` — belief record (belief.py), pure deterministic fold engine (engine.py),
  tasks adapter (adapters.py), package init. Confidence is provenance/source-trust-weighted
  uncertainty (versioned trust table cabinet/config/cortex-source-trust.v1.yml), NOT a bare scalar.
- `framework/schemas/domains/cortex/{belief.v1,source-trust.v1}.json` — registered belief + trust schemas.
- `cabinet/scripts/{cog2-belief-hash,cog2-rebuild}.py` — CLI helpers over the engine.
- `cabinet/scripts/tests/test_cog2_rebuild_determinism.py` — 40 tests (contract §8 sim 1):
  the marquee gate `test_three_subprocesses_distinct_hashseeds_identical` (3 rebuilds as 3
  subprocesses under 3 distinct PYTHONHASHSEED → identical belief-store hash), physical-heap
  shuffle + duplication invariance, frontier law (fold behind last contiguous non-NULL event_id),
  negative-control mutant seams (arrival-order / fresh-ULID / frontier-past-NULL) that must fail,
  the `_SELECT_SQL` ORDER BY id + idempotency_key string pins (F1/F2), and the fold + trust
  fail-loud asserts (divergent-content identity collision / malformed-ppm-for-present-producer, F3/F4).
- Census amendment (cognitive-architecture-contract.yml): COG-2 phase allowance +6 modules / +1800
  noncomment lines (contract §10 ceiling; unit-1 measures +4 modules / +469 lines), tightened at phase end.

## Verification (orchestrator, python3.12, pg17 local)
- Determinism gate: **40 passed, 0 skipped** (0 skips ⇒ the pg-backed subprocess gate + DB backfill
  tests all ran). The determinism property holds identically; the review fix F1 changed the belief
  hash VALUE (idempotency_key now flows into provenance) but the gate asserts cross-rebuild IDENTITY
  and structural counts, not a fixed hash value — those stay green.
- Census GREEN with the amendment (F1/F3/F4 add +23 noncomment lines, 0 modules; well under ceiling).
  Modules import clean. Mutant seams default to correct behavior (the 40-pass proves no mutant is
  patched in as default).

## Shadow boundary (unit 1)
No authority/action module imports framework.cortex (grep clean); the engine reads no clock and no
randomness; the package writes no authoritative store. The mechanical AST import gate + verify script
land in a later unit; this unit's boundary is grep-verified.

## Deferred sim-1 mutants (contract §8 sim 1 negative controls)
Three of the five sim-1 negative-control mutants are covered here (arrival-order, fresh-ULID,
frontier-past-NULL — each with a documented seam that must fail). The other two are DELIBERATELY
DEFERRED, not gaps:
- **`dispatched_at`-reading adapter** (C-F2 — refold after a simulated redelivery must differ):
  positively covered in substance by `test_physical_heap_shuffle_invariant` (dispatch-bookkeeping
  churn — `claimed_at`/`attempts`/`dispatched_at` UPDATEs — leaves the hash identical), and the
  mutant is unbuildable through the read path anyway: `_SELECT_SQL` does not (and by law must not)
  fetch `dispatched_at`, so no adapter can key on it. A dedicated redelivery-mutant seam lands with
  the query/verifier units, not unit 1.
- **set-iteration-order `contradicts`** (only fails under the subprocess hash-seed harness): VACUOUS
  in unit 1 — the tasks stream is a single linear lineage, so every subject+dimension group has
  exactly one head and `contradicts` is always empty (declared, C-F10). The mutant becomes
  exercisable only once a contradiction-capable (multi-lineage) source pairing lands (unit 3+); it
  is meaningless to assert against an always-empty collection now.

## Not yet covered (later units)
Query API + temporal-fence + contradiction/unknown (unit 2); envelope-file + consequence adapters +
provenance/purge (unit 3); verifier/parity + corruption + cross-cabinet (unit 4); AST import gate +
verify-cognitive-phase2.sh + egg-manifest + census tighten + ledger done-flip (unit 5). Also:
- **§5.3 24h frontier-blocker aging** — a NULL-`event_id` row older than the pinned age must surface
  in the manifest + parity verdict as a frontier-blocker; `cog2-rebuild.py` passes no
  `frontier_blockers` today (the manifest field defaults empty). Unit-4 (verifier/parity) scope.
- **§5.2 K fold-processing order** — the total fold-processing order K `(observation_time,
  stream_rank, intra_stream_seq, event_id)` is unobservable on a single stream (belief output is
  sorted by `belief_id`, and supersession is source-order, not K); it becomes observable and lands
  with the multi-source units (consequence + envelope-file).
