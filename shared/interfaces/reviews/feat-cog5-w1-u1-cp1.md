# FW-019 checkpoint review — feat/cog5-w1-u1 cp1

COG-5 W1 unit **u1** — Evolutionary-Foundry BOUNDARY ROWS + AST PINS + STAGE-A
holdout interim + the foundry `.gitignore` row. Branch `feat/cog5-w1-u1` from
`feat/cog5-w1-u0` (450e0e46). Contract `docs/plans/cognitive-core-phase-5-
contract-2026-07-24.md` §10 + §7.5 Stage A + §5.4; S0 report §10 W1 scope.

Batch is **test files + config ROWS only — zero framework delta** (census GREEN,
observed==max on all 10 budgets). >300 lines ⇒ this artifact (FW-019).

## What landed
- **`cabinet/config/boundary-manifest.yml`** — 3 rows APPENDED after ROW 7 (ROW 6
  `framework.projection` :316-345 **byte-untouched**, verified by diff = pure
  addition):
  - **ROW 8** `framework.evolution.holdout_gen` (module, sweep-only) — league-
    invisible: importable by `cog5-holdout-oracle` + `test_cog5_holdout_*` ONLY;
    NARROW `internal_prefix: framework/evolution/holdout_gen/` so the sibling
    evolution modules are non-internal/blind. rule `UNALLOWLISTED_HOLDOUT_GEN_IMPORTER`.
  - **ROW 9** `shared/interfaces/foundry/archive` (data_plane) — the archive
    store; allowlist = archive.py/emitter.py + cog5-archive-restore + cog5-league
    + test globs; `candidate/generator/arena` DELIBERATELY ABSENT (no candidate
    write path, §5.2 WALL). NARROW `internal_prefix: framework/evolution/archive/`.
    Also delivers the projections-can't-read-the-archive half of §10's deny.
    rule `FORBIDDEN_ARCHIVE_DATAPLANE`.
  - **ROW 10** `framework.evolution` (module, reverse-only) —
    `reverse_forbidden: [framework/frontdoor, framework/acting]`.
    rule `FORBIDDEN_EVOLUTION_IMPORTS_ACTION`.
- **`cabinet/scripts/tests/test_cog5_boundary_rows.py`** (NEW) — COG-5 content
  pins + explicit per-row rule-id bites + the §10 projection-deny / ROW-6
  non-extension proofs. (The generic `test_cog4_boundary_rows.py` harness ALSO
  auto-generates a biting mutant per new row — both green.)
- **`cabinet/scripts/tests/lib_cog5_ast_pins.py`** (NEW, stdlib-only) + the three
  §10 sibling pins (NEW, vacuity-armed, companion-absence + retirement conditions):
  `test_cog5_holdout_ast_pin.py` (importer-side league-invisibility),
  `test_cog5_league_ast_pin.py` (allow-list + no-subprocess),
  `test_cog5_sandbox_ast_pin.py` (deny-list: archive writer + credential holder).
- **`cabinet/scripts/tests/test_cog5_holdout_pin.py`** (NEW) — §7.5.5 Stage-A
  content pin (vacuity-armed sha256 + a fixture proof the pin machinery REDs on a
  byte-change) + the egg-exclusion-carried assertion. Docstring states honestly:
  **NOT Ring-0** (CI tripwire only; no schg/hook/gate-S0 refusal until Stage B).
- **`cabinet/scripts/egg-export-manifest.txt`** — Stage-A interim `delete` +
  `expect-absent framework/evolution/holdout_gen.py` (vacuity-armed; retired at
  Stage B). No egg row for the foundry data-plane (untracked ⇒ never in the HEAD
  cut; R116 fail-closes on any tracked stray).
- **`.gitignore`** — `shared/interfaces/foundry/` (§5.4) +
  **`test_cog5_gitignore_foundry.py`** (NEW) git check-ignore assertion.

## Design decisions worth a reviewer's eye
1. **ROW 10 excludes `framework/authority`.** `framework/evolution/tests/
   test_contracts.py:16-17` legitimately imports `authority.classifier`
   (ACTION_TYPES) + `authority.matrix` (RISK_CLASSES). A module-granular row
   cannot carve the read-surface out of `authority.policy_engine`, so per §10 the
   authority joint is an AST-pin concern ("never a row"), landing with its
   consuming modules (W6). `learning`/`fidelity` likewise excluded (touches_ring0
   / graduation-read joints). The row fences the two live-execution lanes
   (frontdoor/acting) that evolution NEVER needs. Verified: committed tree scans
   clean; the carve-out is proven not-reverse-flagged in the boundary test.
2. **Narrow `internal_prefix` on ROWs 8/9** so sibling evolution modules are
   non-internal (a `framework/evolution/` prefix would silently blind the
   protections). `archive.py` is allowlisted EXACTLY (not internal under the
   narrow prefix).
3. **Projection-denies + ROW-6 non-extension** are delivered by EXISTING rows
   (ROW 1/2/4 sweeps deny evolution→cortex/objectives/scheduler; ROW 6 denies
   evolution→projection since no evolution importer is allowlisted) + ROW 9
   (denies projections→archive). No redundant rows — proven by assertion.
4. **Sandbox deny = exactly {archive writer, credential holder}** per §10;
   frontdoor/acting fenced by ROW 10 (not duplicated). Env-scrub is behavioral
   (sim-7, a later wave), not a static pin.

## Verification (all on this branch, python3.12, hermetic HOME)
- cog2-import-gate.py exit **0**; committed-tree scan **0 violations** (10 rows).
- check-layer-separation.sh **new=0**.
- census **GREEN** (observed==max ×10; zero framework delta).
- Boundary/import/AST-pin battery (cog2/3/4 + cog5): **420 passed**.
- test_egg_export.py: **passed** (export runs clean with the interim exclusion).
- Full `cabinet/scripts/tests`: **3308 passed, 40 skipped, 1 failed** — the 1
  failure `test_observe_only.py::test_native_secret_reads_block_direct_and_realpath_aliases`
  is **PRE-EXISTING + ENVIRONMENTAL** (proven: fails IDENTICALLY with my tracked
  edits stashed; self-contained tmp_path + the UNCHANGED pre-tool-use.sh hook; S0
  baseline shows this green on the launching instance / master CI 30110130410).
  2 collection errors (`test_world_asset_{forge,intake}.py`) are PRE-EXISTING
  (missing PIL in this hermetic clone; both files untouched).
- verify-cognitive-phase4.sh: runs post-commit (binds committed bytes) — result
  recorded in the landing.

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
