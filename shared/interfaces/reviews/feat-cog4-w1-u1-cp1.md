# Checkpoint review — feat/cog4-w1-u1, cp1 (COG-4 W1 u1: C2 boundary-engine conversion)

**Scope:** the C2 kickoff unit of the COG-4 contract
(`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §8.1–§8.3, §14.3
Fable-for-execution named unit), off `origin/master` `de5d16c4`. Three files,
well over the FW-019 300-line threshold → this artifact is required.

1. `cabinet/config/boundary-manifest.yml` (NEW, tracked) — the declarative
   boundary law: the NINE pre-conversion §8.1 rules as three legacy rows
   (cortex module row carrying the falsifier ban + the cache-store backstop
   literal; objectives module row carrying the reverse action-plane ban; the
   objectives-store data-plane row), PLUS the four §8.3 COG-4 rows
   (`framework.scheduler` / `framework.organs` / `framework.projection` module
   rows and the schedule-store data-plane row) with the DELIBERATE-ABSENCE
   allowlists exactly as §8.3 pins them: `cog4-organ-runner.py` absent from
   the scheduler + schedule-store allowlists (scheduler-blind runner, §9.5);
   `cog4-parity.py` the one sanctioned dual-plane importer (organs row only);
   `cog3-ovi-parity.py` absent from the objectives allowlist (the pre-existing
   :265-268 idiom, now a first-class `deliberately_absent` field the loader
   fail-closes on and the harness proves bites).
2. `cabinet/scripts/cog2-import-gate.py` — refactored IN PLACE into the
   generic engine consuming the yml (name, CLI contract, all nine rule ids,
   scan semantics preserved; module-granular BY DESIGN kept — `symbol_pin` is
   documentation-only, §8.4; fail-closed manifest loading; row regexes built
   from `re.escape`d literals only; back-compat module constants derived from
   the manifest because the existing suites import them).
3. `cabinet/scripts/tests/test_cog4_boundary_rows.py` (NEW) — the per-row
   mutant harness: every mutant GENERATED from the row itself (scratch tree +
   forbidden import / store mention into a fake importer), engine must RED
   with that row's rule id — so every future row ships with its bite proven,
   including rows whose target trees do not exist yet (the four COG-4 rows are
   exactly that today).

## Verification evidence (all python3.12, this clone, pre-commit)

- **Byte-compat gate (§8.2):** pre-conversion outputs captured at HEAD in all
  three modes (check / --report / --json + exit codes); post-conversion
  outputs byte-identical (both empty violation sets, rc 0/0/0).
- **Mutant parity, old vs new:** for each of the nine §8.1 rules, a scratch
  fixture isolating that rule was scanned by the PRESERVED pre-conversion gate
  copy and the new engine: identical violation lists per rule, identical
  combined-fixture json output (9 violations), identical exit codes (1/1).
- **Existing suites, untouched and green:** `test_cog2_*` + `test_cog3_*`
  (incl. both import-gate suites and `test_cog3_ovi_parity`): 629 passed,
  5 skipped (the pre-existing declared measure-only skips, enforce flags
  unarmed). New harness: 80 passed. Combined run: 709 passed, 5 skipped.
- **Layer-sep:** `check-layer-separation.sh` OK (new=0, fixed=0).
- **Census:** `cognitive-architecture-census.py` PASS — all budgets at
  observed==max, unchanged (this unit adds ZERO framework modules/lines; all
  three files are cabinet/config-, cabinet/scripts- or tests-side).
- **Engine self-flag safety:** the repo scan covers the engine + harness
  themselves; both fold clean (no contiguous store tokens — the assembled-
  token discipline moved into "select rows structurally / build strings from
  row data").

## Deliberate, recorded normalizations (no legacy-visible change)

- Check order normalized to 1, 2, R, 3, D (reverse before the sweeps): no
  input distinguishes the orders for the legacy rows — reverse rows only scan
  their own internal tree, which the same row's sweep always skips. Recorded
  in the engine docstring.
- Violation-mode prose generalized to name the manifest (rule lines keep the
  exact `  + <path>:<RULE>` shape); the empty-scan OK line is byte-identical
  to pre-conversion — the §8.2 byte-compat target.
- The cortex row's allowlist now DECLARES the pre-conversion Check-3 skip
  union (cog3 CLIs + objectives-internal + cog3 test globs were already
  legitimate cortex readers in the old code; the yml states it). The
  objectives row's exact allowlist stays the pinned three (test-asserted set
  equality).
- Engine row/config classes are plain `__slots__` classes, NOT dataclasses:
  `test_cog3_ovi_parity` loads the hyphen-named engine without a sys.modules
  registration, where dataclass string-annotation resolution crashes.

## Known pre-existing failure, NOT this unit (recorded)

`test_cognitive_phase2_rollback.py::test_manifest_covers_committed_cog2_footprint`
fails on any full clone at current master (`.gitleaks.toml` modified post-
phase-2 trips the open-ended-HEAD ratchet) — the exact anti-pattern COG-4
contract §16 names and assigns to C1 slate work. Unrelated to this unit and
outside its named suites.

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; unit ran on Fable 5 per §14.3
(Fable-for-execution named candidate).
