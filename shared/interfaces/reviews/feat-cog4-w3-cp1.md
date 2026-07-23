# FW-019 wave artifact — feat/cog4-w3 cp1 (W3 LANDING: four SHIP units + the phase's first corpus surgery)

Contract: `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §6, §7,
§8.3–§8.4, §11, §12, §13, §14.2 W3. Integrator provenance: per §13 + the unit
contradictions[] routes, W3 landing 2026-07-24; per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant.

## Units landed (branch = u2 tip by ancestry, then u3/u4 cherry-picked)

| unit | tip landed | what | review chain |
|---|---|---|---|
| u1 | 9f436c8d (ancestry) | C3 projection-kernel extraction (`framework/projection`, stdlib-only, +2 modules/+295 lines) | SHIP first-pass; cp artifact `feat-cog4-w3-u1-cp1.md` |
| u2 | d10f3e7f (branch base) | shadow scheduler on the kernel (`framework/scheduler` 5 modules, snapshot/fold/serve + 2 CLIs, +688 lines; boundary rows edit) | SHIP first-pass; cp artifact `feat-cog4-w3-u2-cp1.md` |
| u3 | af2254d9 → e81667f3 (cherry-pick) | cortex kernel adoption — belief.py/engine.py route through the kernel, byte-compat gated, net −10 lines; serve-binding PARKED | SHIP first-pass; contradiction routed (kernel read_rows param) |
| u4 | 9ea856d8 → ed89f9f0 (cherry-pick) | PARK objectives kernel adoption — cross-corpus contradiction marker doc only | SHIP first-pass |

All four units were SHIP first-pass at review. u2 CONTAINS u1 by ancestry, so
the branch starts at u2's tip; the only cherry-pick conflict was the expected
`cognitive-architecture-contract.yml` allowance row (u2 and u3 both extended it
independently off u1) — resolved by RECOMPUTING on the integrated tree (below).

## Allowance reconciliation (the running-total idiom — measured, not summed)

- modules: 226 base + 2 (u1) + 5 (u2) = **233**; row `additional: 7`
  (auto-merged clean).
- noncomment lines: 65012 base + 295 (u1) + 688 (u2) − 10 (u3) = **65985**; row
  `additional: 973`, reason narrative merged u1+u2+u3 with em-dash reasons.
- `cognitive-architecture-census.py --check` on the integrated tree: **PASS at
  observed==max on both rows** (233<=233, 65985<=65985) — the yml numbers are
  the census's own measurement, not arithmetic.

## Corpus surgery ledger (integrator-only power, §13; the COG-3
## three-retired-guards precedent — every retirement carries a dated note in
## the test file citing the discharged condition)

| id | site | retirement condition discharged | surgery |
|---|---|---|---|
| S1 | `test_cog4_scheduler_ast_pin.py::TestSchedulerTransitiveClosure` | "when framework/scheduler/ (or organs/, projection/) lands, delete the skip and enable the real-tree closure scan" — projection landed (u1, 9f436c8d), scheduler landed (u2, d10f3e7f) | split: `test_landed_trees_real_closure_is_clean` subprocess-imports all 7 landed modules (`framework.projection{,.kernel}` + `framework.scheduler{,.fold,.model,.serve,.snapshot}`) and asserts ZERO forbidden-plane modules load — PASSES on the integrated tree; `test_organs_tree_is_armed_and_absent` keeps the organs leg absence-armed unchanged (still absent) |
| S2 | same file — the 3 scheduler-tree vacuity guards (import pin / as_of defaults-only / no-subprocess-no-socket) | "when framework/scheduler/ lands, delete the skip and keep the green-by-vacuity assertion as the real-tree pin" — discharged by u2 | each converted to `test_real_tree_scans_clean`: the real `L.scheduler_*_violations(_REPO) == []` pins — all 3 PASS on the landed tree (u2's claim verified) |
| S3 | `test_cog4_sim_fold.py::TestRealFoldSurfaceArms` — 9 fold-arm vacuity skips | "retire this skip when framework/scheduler/ lands (§7.2 build_schedule); activation is `C.run_real_arm(<arm>, tmp_path, repo=_REPO)`" — discharged by u2 | all 9 arms converted to the documented one-line activation; all 9 run LIVE GREEN on the real surface (sims 1/2/4/7/8/13 + purity env/clock + the N1 triple incl. all three N2 bound variants inside `sim7_starvation`'s `starvation_variants`) |
| S4 | `lib_cog4_corpus.real_surface_import_probe` + `TestArmedProbeMachinery::test_probe_flips_when_the_surface_lands` | u2's routed contradiction: the probe child inherited the pytest cwd (the repo); `python -c` puts cwd on sys.path, so a BARE scratch-root probe resolved the REAL tree the moment it landed | ADJUDICATED a genuine probe defect (the probe must answer about repo_str only — u2's report claim confirmed by direct reading): cwd now pins to the probed root; dated note in the lib docstring; the machinery test passes unmodified |
| S5 | full-sweep residue | every remaining companion-RED retired-by-condition or a genuine defect | ZERO unexplained failures — sweep is fully clean (below) |

## Integrated verification (all on the integrated tree, `python3.12`)

- full `cabinet/scripts/tests` sweep: **3094 passed / 33 skipped / 0 failed**
  — reconciles exactly with u2's pre-surgery 3080/32/14: 13 guard conversions +
  1 probe fix moved 14 designed REDs to passes; the organs leg is the +1 skip.
- kernel batteries: **47/47** (`test_cog4_kernel_parity` + `test_cog4_kernel_store`).
- `test_cog2_*`: **283 passed** (u3's byte-compat gate count) + 3 pre-existing
  declared skips; `test_cog3_*`: **376 passed** / 2 skips.
- u3 byte-compat SPOT-VERIFY (independent, not the suite): real driver chain
  (fold → build_manifest → write_projection → verify_store →
  load_beliefs_verified) over the same fixture corpus on the integrated tree vs
  a pristine origin/master worktree — stores BYTE-IDENTICAL: beliefs.jsonl sha
  765d6ef0…, fold-manifest.json sha 980c935f…, belief_store_hash 8f94dfe0…,
  961 rows verified-loaded on both.
- boundary harness (`test_cog4_boundary_rows` + `test_cog2_import_gate` +
  `test_cog3_import_gate`): **196 passed** (u2's rows edit verified);
  `cog2-import-gate.py` exit **0**.
- census `--check`: PASS observed==max (above). layer-sep: OK, new=0.
- egg-export + HEAD-bytes yml parse: run at commit time (recorded in the PR).

## Parked-adoption debt (recorded, riding future units)

1. **u3 f2/g — cortex serve-binding**: `kernel.verified_single_read` hardcodes
   its internal reader; adopting it for `query._verified_rows` would bypass
   `engine.read_beliefs_jsonl` and break the F4 no-window monkeypoint
   (`test_cog2_corruption` TOCTOU). Needs a kernel `read_rows` parameter — u1
   owns the kernel bytes; the kernel is NOT extended in this landing (§6.4
   explicitly allows parked adoption; marker
   `docs/plans/cog4-w3-u3-cortex-serve-adoption-park-2026-07-24.md` is landed).
   The f2/g completion is parked debt riding a future unit.
2. **u4 — objectives kernel adoption**: boundary ROW 6 sanctions
   objectives→projection; the COG-3 objectives symbol pin (never-weakens)
   forbids it — cannot adopt without a corpus edit or a covert import. Parked
   with marker `docs/plans/cog4-w3-u4-objectives-kernel-adoption-PARKED-2026-07-24.md`
   (resolution recommendation + empty-graph gotcha inside). Scheduler (u1/u2)
   already proves the kernel's second instantiation.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
