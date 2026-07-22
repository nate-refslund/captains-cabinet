# Checkpoint review — feat/cog2-unit1-rebuild-core (cp1)

**Unit 1 of COG-2** (shadow temporal world model "Cortex"): the deterministic-rebuild core.
Branch off master b393f41b (COG-2 contract). Contract: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md.

## What lands
- `framework/cortex/` — belief record (belief.py), pure deterministic fold engine (engine.py),
  tasks adapter (adapters.py), package init. Confidence is provenance/source-trust-weighted
  uncertainty (versioned trust table cabinet/config/cortex-source-trust.v1.yml), NOT a bare scalar.
- `framework/schemas/domains/cortex/{belief.v1,source-trust.v1}.json` — registered belief + trust schemas.
- `cabinet/scripts/{cog2-belief-hash,cog2-rebuild}.py` — CLI helpers over the engine.
- `cabinet/scripts/tests/test_cog2_rebuild_determinism.py` — 32 tests (contract §8 sim 1):
  the marquee gate `test_three_subprocesses_distinct_hashseeds_identical` (3 rebuilds as 3
  subprocesses under 3 distinct PYTHONHASHSEED → identical belief-store hash), physical-heap
  shuffle + duplication invariance, frontier law (fold behind last contiguous non-NULL event_id),
  and negative-control mutant seams (arrival-order / fresh-ULID / frontier-past-NULL) that must fail.
- Census amendment (cognitive-architecture-contract.yml): COG-2 phase allowance +6 modules / +1800
  noncomment lines (contract §10 ceiling; unit-1 measures +4 modules / +469 lines), tightened at phase end.

## Verification (orchestrator, python3.12, pg17 local)
- Determinism gate: **32 passed, 0 skipped** (re-run independently after the build agent stalled on
  optional extra proof; 0 skips ⇒ the pg-backed subprocess gate + DB backfill tests all ran).
- Census GREEN with the amendment. Modules import clean. Mutant seams default to correct behavior
  (the 32-pass proves no mutant is patched in as default).

## Shadow boundary (unit 1)
No authority/action module imports framework.cortex (grep clean); the engine reads no clock and no
randomness; the package writes no authoritative store. The mechanical AST import gate + verify script
land in a later unit; this unit's boundary is grep-verified.

## Not yet covered (later units)
Query API + temporal-fence + contradiction/unknown (unit 2); envelope-file + consequence adapters +
provenance/purge (unit 3); verifier/parity + corruption + cross-cabinet (unit 4); AST import gate +
verify-cognitive-phase2.sh + egg-manifest + census tighten + ledger done-flip (unit 5).
