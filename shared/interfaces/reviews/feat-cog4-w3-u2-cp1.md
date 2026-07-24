# FW-019 review artifact — feat/cog4-w3-u2 cp1 (COG-4 W3 u2: scheduler on the kernel)

Contract: `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §7.1-§7.5,
§6.3, §4.4, §8.3-§8.4, §11, §13. Branch base: `feat/cog4-w3-u1` (kernel
present). The W2 fold corpus (`test_cog4_sim_fold.py` + `lib_cog4_corpus.py`)
is the executable spec — byte-untouched by this unit.

## Batch

| file | what |
|---|---|
| `framework/scheduler/__init__.py` | import-inert package root (the projection idiom) |
| `framework/scheduler/model.py` | corpus-pinned vocabulary + ASCII canonical dialect + FILE-ORDER `schedule_rows_hash` + §7.1 hard-error `validate_snapshot` + atomic `write_snapshot` (kernel (e)/(g)) |
| `framework/scheduler/snapshot.py` | `build_snapshot(**declared)` — cortex via the `load_beliefs_verified`-bound manifest read; objectives via `serve_graph` ONLY; SF2 families + registry + services hashed; honest absence; no env/clock |
| `framework/scheduler/fold.py` | `build_schedule(snapshot_path, cache_dir)` — the pure §7.2 fold (conflict/starvation/ceiling laws, declared costs, canonical tie-break total order), kernel `manifest_envelope` + `atomic_write`, §7.5 O_EXCL writer lock (loser fails LOUD `ScheduleLockHeld`), writes ONLY cache_dir |
| `framework/scheduler/serve.py` | `serve_schedule` — the ONE kernel-bound loader (F1), `verified_single_read` + limbs: row shape, epoch completeness/§7.1 hash-key set/canonical cutoff, counts honesty, snapshot-record hash binding |
| `cabinet/scripts/cog4-snapshot.py` | snapshot CLI — owns all path defaults/injection (§4.4); `--cutoff`/`--scope` required (never clock-defaulted) |
| `cabinet/scripts/cog4-schedule.py` | fold CLI — reports THROUGH `serve_schedule` (F1), lock-held exit 2 |
| `cabinet/scripts/tests/test_cog4_scheduler_surface.py` | NEW suite: the 9 W2 arm batteries live on the real surface (the retirement bodies), serve REFUSE limbs, the §7.5 concurrent-writer proof, end-to-end snapshot round-trip via real cortex/objectives stores + real CLIs |
| `cabinet/config/boundary-manifest.yml` | ROWS-only edit (the W1-u1 parked note): `framework/scheduler/*` added to the cortex + objectives rows' `allowlist_globs` (serve-surface readers; symbol law stays in the §8.4 pin) |
| `cabinet/config/cognitive-architecture-contract.yml` | COG-4 allowance rows extended to EXACT measured running totals — modules 2→7 (233 vs 226 base), lines 295→983 (65995 vs 65012 base), same commit as the code (§11) |

## Evidence (all re-runnable)

- **9/9 armed corpus batteries GREEN on the real surface** via
  `lib_cog4_corpus.run_real_arm(arm, tmp, repo)` — sims 1/2/4/7/8/13 +
  purity env/clock + the N1 PYTHONHASHSEED triple; now permanent CI coverage
  in `test_cog4_scheduler_surface.py::TestRealArmsLive`.
- **§8.4 pins over the real tree**: `scheduler_import_violations == []`,
  `scheduler_asof_default_violations == []`,
  `scheduler_subprocess_socket_violations == []`; transitive closure of all
  five `framework.scheduler*` modules CLEAN of the forbidden namespaces.
- **Boundary**: `cog2-import-gate.py` exit 0 over the final tree; the full
  boundary harness (`test_cog4_boundary_rows` + `test_cog2_import_gate` +
  `test_cog3_import_gate`) 196 passed AFTER the rows edit (the committed-tree
  byte-compat anchor `gate.scan(_REPO) == []` re-proven).
- **Census**: PASS at observed==max after the same-commit allowance rows
  (233/233 modules, 65995/65995 lines); census + wall suites 33 passed;
  `check-layer-separation.sh` OK (new=0).
- **Full sweep**: 3080 passed, 32 pre-existing declared skips, 14 failures —
  ALL designed/explained: 13 §13 companion-REDs demanding the W2 skip
  retirement (3 scheduler-pin guards + 9 fold-arm guards + the transitive-
  closure guard that was already RED on the u1 tip from `framework/projection`)
  plus `TestArmedProbeMachinery::test_probe_flips_when_the_surface_lands`,
  whose bare-tree premise the landing broke (probe child inherits cwd=repo;
  `python -c` puts cwd on sys.path, so the scratch-root probe now resolves the
  REAL tree — retire with the skips, or give the probe cwd isolation:
  integrator-owned).

## Deliberate adjudications (recorded, not silent)

1. **Store dialect** — the schedule store hashes with the CORPUS-pinned ASCII
   canonical dialect (`ensure_ascii=True`) and chains rows in FILE ORDER, not
   the kernel's recorder dialect / sorted-order parameterization: the corpus
   batteries re-derive the manifest hash with THEIR encoder over re-parsed
   rows, and file-order chaining makes a reordered-but-content-identical
   store REFUSE at serve (strictly stronger). Kernel (e)/(f)/(g)/(d) are
   still the store's write/serve/cutoff/envelope law.
2. **Crashed-writer lock debris fails loud** — §7.5 names no auto-steal;
   recovery is the rollback grammar (delete cache, rebuild). Never a timeout
   steal that would reopen the race.
3. **No organ registry yet** — the CLI's omitted-registry default is the
   honest EMPTY registry (organs land W4 behind the germline window); an
   explicitly passed path must exist.

Provenance: authored + self-ratified per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant; Fable-for-execution
named unit (Captain 2026-07-23 calibration). Corpus untouched:
`git diff --stat feat/cog4-w3-u1..HEAD -- cabinet/scripts/tests/test_cog4_sim_fold.py cabinet/scripts/tests/lib_cog4_corpus.py cabinet/scripts/tests/lib_cog4_ast_pins.py cabinet/scripts/tests/test_cog4_scheduler_ast_pin.py` is empty.
