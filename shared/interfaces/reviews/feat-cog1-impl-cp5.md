# Review artifact — feat/cog1-impl checkpoint 5 (W5: cutover pointer + version-dispatch + rollback manifest + phase-1 gates + census)

Branch: feat/cog1-impl · Base: 0bf60e69 (origin/master merge of #165)
Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §8.4 (one-command
pointer/adapter flip + inverse; capture-side disarm/enable), §4.1 (consumer
version dispatch — v1 AND v2 accepted, everything else byte-unchanged), §12.4
(machine-readable rollback manifest, before code), §12.5 (landing protocol +
ledger parity/stale-in-flight), §9.4 (CI teeth — its own separate commit), §10.1
(census allowance), §11.1 (legacy-behavior parity / cutover-eligibility).
S0 pin: production work store is PostgreSQL; cutover/inverse gates ran against a
real ephemeral cluster, no skips.

## Verdict: APPROVE (independent adversarial review, Fable 5, fresh context)

FW-019 batch artifact for a >300-line commit: new files total ~1,396 lines
(cog1-authority-flip.sh 76, verify-cognitive-phase1.sh 67,
cognitive-phase1-review-scope.py 174, cognitive-phase1-rollback-rehearsal.py 218,
rollback-manifest yml 132, test_cog1_cutover.py 364,
test_cognitive_phase1_rollback.py 365) plus modified files (my-tasks.sh +7,
task-events-watch.py +10/-3, egg-export-manifest.txt +14, test_egg_export.py +43)
— well over the 300-line threshold.

File-set (this wave):
- cabinet/scripts/cog1-authority-flip.sh (NEW — pointer flip + inverse +
  disarm/enable wrapping ALTER TABLE ... DISABLE/ENABLE TRIGGER).
- cabinet/scripts/my-tasks.sh (MODIFY — §8.4 cutover pointer consult only; +7).
- cabinet/scripts/task-events-watch.py (MODIFY — §4.1 consumer validate_any
  version-dispatch doorway; +10/-3).
- docs/plans/cognitive-core-phase-1-rollback-manifest-2026-07-20.yml (NEW).
- cabinet/scripts/verify-cognitive-phase1.sh (NEW — fail-closed phase-1 gate).
- cabinet/scripts/cognitive-phase1-review-scope.py (NEW — EXPECTED_SCOPE).
- cabinet/scripts/cognitive-phase1-rollback-rehearsal.py (NEW).
- cabinet/scripts/tests/test_cog1_cutover.py (NEW).
- cabinet/scripts/tests/test_cognitive_phase1_rollback.py (NEW).
- cabinet/scripts/egg-export-manifest.txt + cabinet/scripts/tests/test_egg_export.py
  (MODIFY — phase-1 private-tool egg-exclusions).
- cabinet/config/cognitive-architecture-contract.yml (COG-1 allowance rows,
  census-measured exact) — already landed by W3 1b30fa55; clean in the tree.
- docs/plans/operative-egg-ledger-2026-07-07.yml (COG-0 frozen-historical note
  ONLY) — already landed by W1 95f3a10f; clean in the tree.

## Findings / disclosures (verified — none blocking W5)

- **W4 concurrent-wave files** are present in the shared tree; W5 does NOT edit
  them — it only LISTS their paths in the rollback manifest remove/restore,
  cognitive-phase1-review-scope.py EXPECTED_SCOPE, and the completeness ratchet.
  This folding is plan-mandated (§12.4 — the phase rollback manifest is W5-owned;
  W4 cannot edit it). test_phase_1_manifest_is_closed and
  test_manifest_covers_committed_cog1_footprint pass. Not a scope violation.
- **Operative-ledger COG-1 row duplicate `last_update` key** (resolves to the
  STALER 2026-07-19) is a real freshness defect but NOT a W5 finding: introduced
  by W1 (95f3a10f), the ledger is UNMODIFIED in W5's tree, and W5's ledger scope
  is "COG-0 frozen-historical note ONLY" (§12.5 assigns the COG-1 row to the
  later done-flip commit). Fix owner = whoever lands the COG-1 done-flip. COG-0's
  own duplicate resolves to the FRESHER 2026-07-21, so COG-0 is benign.
- **`.github/workflows/cabinet-ci.yml`** is in the §12.4 code-inverse restore set
  but ABSENT from manifest.restore_from_baseline — correct, not a gap: it is
  untouched (§9.4 mandates the CI edit lands as its OWN separate commit, not yet
  landed); you cannot restore-from-baseline a file identical to baseline. The
  completeness ratchet will demand its addition the moment the §9.4 commit lands.

## Evidence re-run by the reviewer (house interpreter python3.12)

- test_cog1_cutover.py = **14 passed** (3 PG17 tests ACTUALLY RAN, not skipped:
  disarm/enable inverse rehearsal, mutant no-trigger-name, disarm-requires-
  connection — all against a real ephemeral cluster; negative controls bite:
  v1-only mutant poison-discards v2, bad-verb writes nothing, wrong/near-miss
  trigger name errors loudly).
- test_cognitive_phase1_rollback.py = **10 passed** (manifest closure, 3
  one-command runtime inverses, EXPECTED_SCOPE==manifest derivation, digest
  determinism + TEETH: mutate 047 DDL → digest changes → --verify BLOCKs; A13
  teeth; completeness ratchet).
- test_egg_export.py = **47 passed / 2 skipped** (the 2 skip pre-tracking as
  designed; text-level phase-1 exclusion gate green).
- test_task_events_watch.py = **25 passed** (v1 consumer regression — validate_any
  accepts v1 AND v2).
- cognitive-architecture-census.py --check = **PASS**, all 10 budgets at exact
  cap incl framework_production_modules 209<=209 and
  framework_production_noncomment_lines 62239<=62239 (measured-exact, zero slack).
- check-layer-separation.sh = **new=0** (W5 adds no framework code).
- never-a-score harness --self-test = 12/12 green; score-token grep of all W5
  files = clean.
- Phase-0 files (verify-cognitive-phase0.sh, cognitive-phase0-review-scope.py,
  its manifest, test_cognitive_phase0_rollback.py) BYTE-UNCHANGED in tree and
  baseline..HEAD.
- verify-cognitive-phase1.sh is fail-closed: BLOCKs on a dirty tree and on the
  absent Verdict:PASS review artifact (the expected downstream §12.3 state).
- Not run end-to-end: cognitive-phase1-rollback-rehearsal.py (a documented
  land-time gate — needs the W4/W5 files at HEAD); its structure/A13
  byte-identity/teeth are covered by the passing unit tests.
