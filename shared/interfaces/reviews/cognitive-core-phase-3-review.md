# COG-3 §12.3 FROZEN REVIEW — Causal Objective/Value Graph (Objectives)

**Scope:** the COG-3 surface at commit `86746524` (`feat/cog3-wave4`, "cog3: w4c integration nit — r14 token sweep extended to the objectives schema surface"): `framework/objectives/**` (7 core + 5 adapter modules, 1894 lines), `framework/schemas/domains/objectives/{node,edge,prediction,scorecard}.v1.json`, `cabinet/scripts/cog3-{rebuild,graph-hash,ovi-parity,staleness}.py`, the phase twins, `cabinet/scripts/tests/test_cog3_*.py` + `lib_cog3_*.py`, the D1 seam (`framework/cortex/adapters.py` + `test_cog2_asof_fence.py`), `cog2-import-gate.py` extension.
**Re-verified scope:** the F1 fix at wave tip `27e3c0f6` ("cog3-f1: bind the WHOLE objectives serve surface (kill serve_objective/recommend REFUSE-limb bypass)") — the ONLY commit atop the panel base (`git log 86746524..27e3c0f6` = 1 commit; the cherry-pick of fix commit `5bafa7db`; 3 files: `framework/objectives/query.py`, `cabinet/scripts/tests/test_cog3_exit_fixtures.py`, `cabinet/config/cognitive-architecture-contract.yml`). Panel findings bind to base `86746524`; the F1 disposition + the re-verify command log bind to tip `27e3c0f6`.
**Reviewer:** fresh-context Fable panel (clean-room clone, zero prior-session context; this run, 2026-07-23). F1 re-verify: independent re-verify pass (same clean-room clone advanced to tip `27e3c0f6`, 2026-07-23) — re-ran the panel's F1 probe with its OWN tamper code + the full battery; every number in the re-verify log below is from that pass's runs.
**Contract:** `docs/plans/cognitive-core-phase-3-contract-2026-07-22.md` rev 1 + build-time adjudications of record (R-A, R-B, schema idiom, §5.2b two limbs, wave-3/4 addenda).
**Method:** every claim below is bound to bytes (`file:line`) or a run executed by this panel (`python3.12`; postgres@17 on PATH). No doc or comment was trusted un-run.

Reviewed-Scope-Digest: e98fc026bae0fa4c579bf4deed8302da2ef26a4d855db7fe59e909f5650c9f63
(Re-bound at landing, 2026-07-23: after the freeze, two ADMINISTRATIVE commits joined the
wave-4 cp3 FW-019 artifact to the three footprint surfaces (rollback manifest + review-scope
tool + closure-test constant), which are themselves inside the reviewed scope — moving the
digest from 6c800e12… . Zero reviewed BEHAVIOR bytes changed since the re-verified tip
27e3c0f6: git diff 27e3c0f6..HEAD touches only review artifacts and those three footprint
rows. The panel verdict stands.)

---

## Standing questions — findings

### Q1 — Does any code path STORE or CACHE a derived epistemic state contrary to §5.4?

**NO.** The pinned shape holds exactly:

- Derivation happens at COMPILE only: `states.derive_edge_state` has exactly ONE production caller — `framework/objectives/graph.py:520` (inside `_compile`). Grep over `framework/` + `cabinet/scripts/*.py` (tests excluded) returns no other caller; `framework/objectives/query.py` never imports or invokes it — the serve surface has NO re-derivation API.
- Persisted rows carry the compiled state labeled by the manifest epoch: `graph.py:528-534` writes `"state"`/`"flags"` into the edge row; `graph.py:568-596` records the epoch tuple `(graph_builder_version, roots_hash, cortex_belief_store_hash, cortex_fold_epoch, trust_table_version, scope, cutoff)` in `graph-manifest.json`. This is the §5.4-pinned shape, not stored authorship.
- No sticky-state input path: `_compile` never reads a prior `graph.jsonl` (`_read_graph_rows` at `graph.py:633` is called only by the hash/serve functions, `graph.py:659,667`); state is a pure function of roots + cutoff-fenced views. Run: `test_cog3_sim2_stale_verdict.py::test_superseded_evidence_redemotes_on_rebuild` PASSED (stored-status mutant class bitten).
- Counterfactual branches carry their own `counterfactual: true` manifests (`graph.py:604-606`); predictions store forecasts, never epistemic states (`counterfactual.py:60-89`).
- The §8 "disposable index" (`objectives-index.sqlite3`) is NOT implemented — zero `sqlite` references in the tree — so no state cache exists there either (see F4).

### Q2 — Does any accessor return a bare scalar — including via ovi_view?

**NO.** Ratchet run: `test_cog3_no_scalar_ratchet.py` → **27 passed**; `test_cog3_sim6_no_scalar.py` → **22 passed**. The ratchet (`lib_cog3_no_scalar.py:42-53`) AST-forbids `total/score/__float__/composite/aggregate/fitness/...` accessors, OVI composite tokens in `ovi_view.py`, numeric edge-weight identifiers and schema props. Panel probe (direct run): `ovi_view.project({"instr_a": .4, "instr_b": .9})` → `{"instr_a": {"value": 0.4}, "instr_b": {"value": 0.9}}` — per-instrument cells only; zero composite/total/weight attributes on the module (`ovi_view.py:18-22` is the whole surface). `ScorecardView` (`query.py:62-69`) carries no `__float__`/total; `recommendation_record` rejects a scalar scorecard (`query.py:114-122`); floors are vector-independent, unknown never passes (`query.py:76-99`).

### Q3 — Does supersession/lineage ever consult correlation_id?

**NO.** Grep `correlation_id|causation_id` over `framework/objectives/` → **0 hits**. The objectives tree implements no supersession of its own — lineage is delegated entirely to the cortex `as_of` surface, called defaults-only (`graph.py:203,214,225`); the correlation-as-lineage fold is the cortex's LABELED MUTANT seam (`framework/cortex/engine.py:149-150` — "MUTANT: chain, not producer"), unreachable from objectives: the defaults-only AST pin over `framework/objectives/` is green (`test_cog3_objectives_ast_pin.py` → **36 passed**) and `test_cog2_asof_fence.py` → **29 passed**.

### Q4 — Does any fold/build input come from the environment (clock, env var, cwd) — incl. the roots path and --now?

**NO for the fold; declared-parameter discipline holds.** Grep `os.environ|getenv|datetime.now|utcnow|time.time|getcwd|Path.cwd|expanduser|gethostname` over `framework/objectives/` → **0 hits**. `build_graph(roots_path, cache_dir, scope, cutoff)` takes every input as a declared parameter (`graph.py:620-630`); the cortex sibling is derived from `cache_dir` (`graph.py:629`), `roots_path` is recorded in the manifest (`graph.py:583`), the cutoff is hard-gated canonical at the `_compile` entry (`graph.py:295-300`). CLIs: `cog3-rebuild.py:134-135` — `--cutoff` REQUIRED, `--roots` a declared arg with the CLI-owned default (`cog3-rebuild.py:37`, §7.6 — no instance literal in framework; exit-fixture grep cell `test_objectives_framework_carries_no_instance_product_tokens` PASSED); `cog3-staleness.py:75` — `--now` REQUIRED, never a clock. Exception, instrument-scope only (F3): `cog3-ovi-parity.py:95,202,237` reads three env seams (`CABINET_ROOT`, `COG3_OVI_PARITY_DATA_JSON`, `COG3_OVI_VIEW_CMD`) — the parity FALSIFIER, not a fold/build input; no clock read (pinned: `test_cog3_ovi_parity.py::test_committed_parity_script_reads_no_clock` PASSED).

### Q5 — Does rebuild-after-verdict-purge demote the edge?

**YES.** Run: `test_cog3_sim2_stale_verdict.py::test_purged_human_verdict_revokes_tested_lineage_intact` PASSED — the same edge derives `intervention_supported` on the live human confirm, then `hypothesized` (P6, no flags) against the purged store, with lineage intact (the purged view still present, `value is None`, completeness `purged`). Mechanism at bytes: `states.py:62-66` (`_is_purged`) makes the purged view inert in every predicate; revocation is free by construction (no revocation API to get wrong). The supersession twin (`test_superseded_evidence_redemotes_on_rebuild`) PASSED: P5 at the early cutoff → P4 `hypothesized`+`direction_contested` after the contradicting head.

### Q6 — Can any non-`verdict_human` source reach P3 by ANY path?

**NO path found.** Bytes: P3 requires `verdict == "confirmed" and source == HUMAN_VERDICT_SOURCE` on a machine-verified join (`states.py:207-211`, constant pinned `states.py:39`), plus non-empty stripped assumptions (`states.py:191-192,231`). Exact string equality — fail-closed on every variant. Panel probe (direct `derive_edge_state` runs, verified-join-eligible views): sources `verdict_judge`, `verdict_gate`, `system`, absent, `Verdict_Human`, `VERDICT_HUMAN`, `" verdict_human"`, `"verdict_human "`, `"verdict_human\n"`, `verdict_humanx`, `verdict_huma`, `""` — **all 12 capped at `observationally_supported`; 0 reached P3**; the genuine `verdict_human` control DID reach P3. A rank-0 (non-consequence-stream) human confirm does NOT promote (`states.py:88-89`); empty and whitespace-only assumptions block P3 (and P5 → P6). Suite pins: `test_machine_or_absent_confirm_caps_at_observationally_supported[verdict_judge|verdict_gate|system|absent_source]` — 4 PASSED; `test_assumptionless_machine_confirm_derives_p6_not_the_p5_ceiling` PASSED; exhaustive `test_cog3_state_function.py` → **59 passed**. The drift tripwire binds the graph constant to the domain's `_REVIEW_SOURCES` from OUTSIDE the import pin (`test_cog3_verdict_vocab_tripwire.py:53` deliberately imports `framework.fidelity.consequence`) → **11 passed**.

### Q7 — Does the import closure of `framework.objectives` reach fidelity/authority/acting/frontdoor/missions/ovi?

**NO.** Panel subprocess probe importing ALL 12 modules (`framework.objectives` + model/states/graph/query/counterfactual/ovi_view + the 5 adapter modules) then scanning `sys.modules`: `FORBIDDEN_IN_CLOSURE: []`; cortex closure exactly `framework.cortex{,.belief,.engine,.query}` — the sanctioned substrate reached via the query surface (N5 allows this explicitly). Static import inventory over the tree: stdlib + `framework.objectives.*` + exactly `as_of, load_beliefs_verified, StoreCorruptError` from `framework.cortex.query` (`graph.py:31`, `query.py:31`) — inside the seven enumerated symbols. Runs: `test_cog3_objectives_ast_pin.py` → **36 passed** (incl. transitive-closure + `load_beliefs`/fidelity mutants); `python3.12 cabinet/scripts/cog2-import-gate.py` → OK ("no authority/action code imports the cortex or objectives shadow models"); `test_cog3_import_gate.py` → **58 passed** (both directions + data-plane sweep + missions mutants).

### Q8 — Does anything serve a counterfactual manifest or mixed-epoch states?

**At panel base `86746524`: `serve_graph` no — all three REFUSE limbs verified; `serve_objective`/`recommend` YES — they bypassed all three limbs (finding F1, must-fix). FIXED at tip `27e3c0f6` and RE-VERIFIED by this pass: all THREE public serve functions now REFUSE all three limbs (see F1 row + the re-verify command log).**

- `serve_graph` refuses: a `counterfactual: true` manifest (`query.py:204-205`); a tampered/partial `graph.jsonl` via the rows-hash binding (`query.py:209-214`); a mixed-epoch live store INCLUDING the built-without-store null hole (`query.py:216-230`). Runs: `test_cog3_sim3_counterfactual.py::test_serve_refuses_a_counterfactual_manifest` PASSED; `test_cog3_sim2_stale_verdict.py::test_serve_refuses_states_derived_against_a_refolded_store` PASSED; panel probe: `serve_graph` on a real branch dir → `ServeRefused`; on a row-tampered canonical cache → `ServeRefused`. Branch isolation: `test_counterfactual_branch_isolates_output_and_leaves_canonical_byte_identical` PASSED.
- **But** (at base `86746524`) `serve_objective` (`query.py:234-245`) and `recommend` (`query.py:248-271`) called `_read_records` directly and never bound the manifest: panel probe — `serve_objective(<branch_dir>, ...)` on a manifest-labeled `counterfactual: true` branch **ANSWERED** (no refusal); `recommend(<branch_dir>, ...)` **ANSWERED**; `serve_objective` on the tampered canonical cache **ANSWERED** the tampered row. The module's own docstring framed the three limbs as the serve surface's law; the bytes implemented them only in `serve_graph`. No test pinned the other two entries against the REFUSE limbs (grep at base: no such cell).
- **FIXED at tip `27e3c0f6`** (cherry-pick of fix commit `5bafa7db`): the limb logic is extracted into ONE internal bound loader `_load_bound` (`query.py:195-236` — counterfactual limb :209-210, rows-hash limb :214-219, mixed-epoch + built-without-store null hole :220-235), and ALL THREE public entries route through it before reading a single record (`serve_graph` :246, `serve_objective` :256, `recommend` :274); identical `ServeRefused` shape, no public signature change. Pinned by the NEW `TestServeSurfaceUniformity` (`test_cog3_exit_fixtures.py:557-584`): 3 fns x 3 limbs REFUSE + 3 pristine positive controls = 12 cells on the fixture-1 cache built end-to-end through the real CLI (pre-fix, the 6 objective/recommend limb cells did not raise — discriminating). Re-verify probe (this pass, OWN tamper code — appended junk row / `counterfactual: true` manifest flip / sibling-cortex refold): **9/9 limb cells raised `ServeRefused` with the limb-correct message; 3/3 positive controls ANSWERED** on the pristine cache (the `objective/faster-checkout` node is present and the answers are genuine bound reads: `recommend` cites the store's `observationally_supported` + `intervention_supported` edges, `effective: true`; node records carry no `state` key so `serve_objective` answers the declared `unknown` default with empty flags).

### Q9 — Exit gates N1-N6 (see table below). All six have mechanical proofs in the tree and all ran green this session.

### Q10 — Anything else that would refuse ship?

Full battery `python3.12 -m pytest cabinet/scripts/tests/test_cog3_*.py cabinet/scripts/tests/test_cognitive_phase3_rollback.py -q` → **349 passed, 2 skipped** (both skips are DECLARED measure-only perf cells, `test_cog3_measurement.py:208,216`, `COG3_ENFORCE_P95` unset, numbers recorded). `python3.12 cabinet/scripts/cognitive-phase3-rollback-rehearsal.py` → **PASS 29/29** ("only append-only operative history remains"; notes this review file as a declared remove path). `bash cabinet/scripts/verify-cognitive-phase3.sh` → **READY_FOR_CI** (29/29; correctly states CI-green is not proven locally). `python3.12 cabinet/scripts/cognitive-architecture-census.py --check` → **exit 0**, every budget at observed <= max incl. `framework_production_modules 226<=226`, `framework_production_noncomment_lines 64993<=64993`, `named_compiler_modules 1<=1` (zero-headroom by design, allowance rows landed). Egg export: `egg-export-manifest.txt:142-150,454-457,552-554` carries the phase-twin delete + expect-absent lines and cog3-CLI expect-present lines; `test_egg_export.py:493-526` extended. Read-pointer tripwire: `test_cog3_read_pointer.py` → **3 passed**. D1 seam: `test_cog2_asof_fence.py` → **29 passed** (4 consequence/correlation cells selected-run green). `.gitignore:203` covers `cabinet/cache/*`. Worktree byte-clean after all runs (`git status --porcelain` empty). The only refuse-ship item found is F1.

---

## Findings register

| id | severity | finding | file:line | disposition |
|---|---|---|---|---|
| F1 | **MUST-FIX** | `serve_objective` and `recommend` bypass all three serve REFUSE limbs (§5.3/§5.4): they read `graph.jsonl` directly without binding the manifest, so a `counterfactual: true` branch dir, a rows-tampered cache, and a mixed-epoch cache all ANSWER instead of raising `ServeRefused`. Mechanically demonstrated by panel probe (3/3 bypasses); contradicts the contract's "the serve surface REFUSES" law and the module's own docstring (`query.py:12-19`). The sim2/sim3 REFUSE mutants pin only `serve_graph`. Shadow-only today (no consumer, no read pointer), but the masquerade wall A-M5 exists precisely so no binding-free path survives to flip time. | at base: `query.py:234-245`, `query.py:248-271`, vs `query.py:193-231`; fix: `query.py:195-236,246,256,274` | **FIXED** at tip `27e3c0f6` (cherry-pick of fix commit `5bafa7db`), re-verified by this pass: ONE bound loader `_load_bound` (`query.py:195-236`) enforces all three limbs and `serve_graph`/`serve_objective`/`recommend` ALL route through it (`query.py:246,256,274`) — exactly the prescribed shape (route through the binding + pin per entry). Pinned by `TestServeSurfaceUniformity` (`test_cog3_exit_fixtures.py:557-584`, 12 cells: 3 fns x 3 limbs REFUSE + 3 positive controls; the 6 objective/recommend limb cells did not raise pre-fix). Re-verify probe with independent tamper code: 9/9 limb cells `ServeRefused` (limb-correct messages), 3/3 pristine controls ANSWER. Battery at tip: 361 passed 2 skipped; census `--check` exit 0 (`framework_production_noncomment_lines 65012<=65012`, allowance row landed in the same commit). |
| F2 | MEDIUM | The N4 fold authentication limbs are exercisable only via reserved fixture keys baked into the production fold: `obj.get("forged_root_node_id", …)` / `obj.get("recorded_roots_hash", roots_hash)` default to self-consistent values, so in the production input shape both limbs are vacuously satisfied (self-comparison) and only fixture-injected forgeries can trip them. Fail-closed in every direction (injecting the keys can only RAISE, never widen), and the sim5 mutants do fail for their named escapes — but unlike the cortex's five mutant-seam kwargs (blessed + pinned defaults-only), these seams carry no defaults-only pin and are un-labeled input keys. | `graph.py:359-361`; cells `test_cog3_sim5_root_integrity.py:347,360` | Recorded, not ship-blocking in shadow (schema PRESENCE wall + orphan flagging + `roots_hash` in the epoch tuple carry the production protection). Recommend a named-seam pin (reserved-key test) in the next unit. |
| F3 | LOW | The OVI parity falsifier reads three env seams: `CABINET_ROOT` (root override), `COG3_OVI_PARITY_DATA_JSON` (sample injection, priority over `--sample-data`), `COG3_OVI_VIEW_CMD` (external reader). Instrument-scope only, never a fold/build input; no clock (pinned); the seam swaps the SHARED raw sample, so it cannot green a broken reader (broken reader → `error` verdict, `test_broken_reader_is_an_error` PASSED). | `cog3-ovi-parity.py:95,202,237` | Recorded as declared instrument seams; acceptable. |
| F4 | LOW | `objectives-index.sqlite3` — named in contract §8's proposed file surface and in N1's coverage sentence — is not implemented anywhere (zero `sqlite` hits in the tree). N1's "disposable index" clause is satisfied vacuously. §8 is expressly "proposed", so this is honest absence, not drift — but the contract text and tree now disagree on a named artifact. | contract §8 vs tree | Recorded; either build the index when needed or strike the name in the next contract amendment. |
| F5 | INFO | Two battery skips are declared measure-only perf ceilings (`COG3_ENFORCE_P95` unset): full rebuild 0.00487s and serve p95 0.3662ms recorded, ceilings not asserted. | `test_cog3_measurement.py:208,216` | As designed. |
| F6 | INFO | A `confirmed` review verdict from ANY source (or on a non-verified join) is read as direction-supporting fuel (`_direction`, `states.py:134-140`) — i.e. spoofed/machine confirms still earn P5 (with assumptions). This is exactly the contract's P5 ceiling for non-human-verdict evidence, verified by the Q6 probe matrix; noted so nobody later mistakes P5-on-spoof for a breach. | `states.py:118-146` | As designed (P5 is the declared cap). |

---

## N1-N6 exit-gate table

| gate | mechanical proof in tree | run + result |
|---|---|---|
| N1 rebuild determinism | `test_cog3_sim1_objective_conflict.py::TestConflictedRebuildHashTriple::test_three_subprocesses_distinct_hashseeds_identical` (3 subprocess rebuilds, `PYTHONHASHSEED` 0/1/987654321, conflicted fixture); delete→rebuild-from-zero: `test_cog3_exit_fixtures.py:240` (`test_fixture_software_product_cabinet`); scope honored — `predictions/`+`counterfactuals/` excluded by name (rows-chain over graph rows only, `graph.py:644-652`; predictions carry their OWN chained manifest, `counterfactual.py:45-57`) | PASSED (both cells run individually this session; sim1 suite 14 passed; exit fixtures 4 passed). Hash path-dependence across DIFFERENT roots paths is the recorded wave-3 adjudication; all N1 comparisons hold the path fixed |
| N2 causal-state honesty | seeded histories in `test_cog3_sim2_stale_verdict.py` (superseded/contested/purged + `verdict_judge`/`verdict_gate`/absent-source confirm seeds + refold-REFUSE) and the exhaustive predicate matrix `test_cog3_state_function.py`; machine-wrong caps at P4 never `falsified` (`states.py:214-215,235-236`) | sim2 **18 passed**; state function **59 passed**; panel spoof probe 12/12 capped, 0 reached P3 |
| N3 no-scalar | permanent ratchet `test_cog3_no_scalar_ratchet.py` over `framework/objectives/` incl. `ovi_view` composite mutant + schema weight props (`lib_cog3_no_scalar.py:42-53`); SIM-6 vector law | ratchet **27 passed**; sim6 **22 passed**; probe: per-instrument projection only |
| N4 root integrity | `test_cog3_sim5_root_integrity.py`: root bytes byte-identical after build, orphan-answerable-with-flag, rootless = `SchemaRejection` vs dangling/forged-`roots_hash` = `states.BuildFailure` (two DISTINCT types, `graph.py:51-56` vs `states.py:55-59`; fold limbs `graph.py:344-371`) | **13 passed** (incl. both fold-limb mutants + limb-type distinctness). Vacuity caveat recorded as F2 |
| N5 shadow boundary | module gate `cog2-import-gate.py` (extended, both directions + data-plane sweep) + `test_cog3_import_gate.py` + the NET-NEW AST pin + transitive-closure test `test_cog3_objectives_ast_pin.py` + pointer tripwire `test_cog3_read_pointer.py` | gate run **OK**; import gate **58 passed**; AST pin **36 passed**; read pointer **3 passed**; panel subprocess closure probe: forbidden namespaces **empty** |
| N6 OVI per-instrument parity | `test_cog3_ovi_parity.py`: exact per-instrument vs legacy ground truth on pinned windows, breach cells (perturbed/dropped/composite/smuggled-aggregate), no-clock + no-objectives-import pins on the committed script | **12 passed** |

---

## Command log (this run)

1. clone + checkout `867465243b28b4b6e5c2b544a839ae684d11e8fe` → HEAD `86746524`
2. full battery (`test_cog3_*.py` + `test_cognitive_phase3_rollback.py`) → 349 passed, 2 skipped
3. grep env/clock/cwd over `framework/objectives/` + 4 CLIs → 0 fold hits; 3 parity-instrument seams
4. grep `correlation_id|causation_id` over `framework/objectives/` → 0 hits
5. import inventory grep → stdlib + internal + 3 sanctioned cortex symbols only
6. `test_cog3_objectives_ast_pin.py` → 36 passed; `cog2-import-gate.py` → OK
7. panel probe Q2/Q6/Q7 (closure subprocess; `ovi_view.project`; 12 verdict-source spoofs + rank-0 + assumptions gates) → all clean, 0 spoofs reached P3
8. `test_cog3_sim2_stale_verdict.py` → 18 passed; `test_cog3_sim3_counterfactual.py` → 16 passed
9. Q5/Q8 named cells (purge, supersede, refold-REFUSE, counterfactual-REFUSE, branch isolation) → 5 passed
10. panel serve-bypass probe → `serve_graph` refused 2/2; `serve_objective`/`recommend` bypassed 3/3 (**F1**)
11. per-suite: sim1 14, sim4 16, sim5 13, sim6 22, state_function 59, verdict_vocab 11, ratchet 27, import_gate 58, census_wall 4, read_pointer 3, adapters 22, exit_fixtures 4, ovi_parity 12 — all passed
12. N1 triple + delete→rebuild cells individually → 2 passed
13. rollback rehearsal → PASS 29/29; `verify-cognitive-phase3.sh` → READY_FOR_CI 29/29
14. census `--check` → exit 0 (observed <= max on every budget)
15. `cognitive-phase3-review-scope.py --print` → scope digest emitted (binding is the integrator's)
16. `test_cog2_asof_fence.py` → 29 passed (D1 consequence + correlation cells green)
17. egg-manifest/gitignore/tripwire greps + `git status --porcelain` → clean tree

### Re-verify pass (2026-07-23 — F1 fix, tip `27e3c0f6`)

18. `git fetch origin feat/cog3-wave4` + checkout `27e3c0f6801dd8dea12b8eb281a9ef7167e9d3dd`; `86746524` verified ancestor; `86746524..27e3c0f6` = exactly 1 commit (the F1 fix, cherry-pick of `5bafa7db`; 3 files)
19. independent F1 probe re-run (OWN tamper code, not the suite's helper; fixture-1 cache built once end-to-end via the real `cog3-rebuild.py` CLI, isolated copy per cell): pristine cache → `serve_graph`/`serve_objective`/`recommend` all **ANSWER** (3/3 positive controls; `objective/faster-checkout` node + `observationally_supported`/`intervention_supported` edges confirmed present in the cache, so the answers are genuine bound reads); tampered rows (appended junk row) → 3/3 `ServeRefused` "graph rows-hash mismatch"; `counterfactual: true` manifest flip → 3/3 `ServeRefused` "refusing to bind a counterfactual manifest (§5.3)"; mixed-epoch (sibling-cortex refold, sim2 idiom) → 3/3 `ServeRefused` "mixed-epoch: live cortex store hash != …" — **9/9 limb cells REFUSE, limb-correct messages; 0 bypasses**
20. `test_cog3_exit_fixtures.py` (16 = 4 + the 12 new uniformity cells) + `test_cog3_sim2_stale_verdict.py` (18) + `test_cog3_sim3_counterfactual.py` (16) → **50 passed**
21. full battery (`test_cog3_*.py` + `test_cognitive_phase3_rollback.py`) at tip → **361 passed, 2 skipped** (= panel's 349 + the 12 uniformity cells; same two DECLARED measure-only perf skips)
22. `bash cabinet/scripts/verify-cognitive-phase3.sh` → **READY_FOR_CI** (29/29 PASS; rollback rehearsal PASS). Run with this draft set aside so the gate ran its review-absent SKIP-loud branch over the COMMITTED tree — the same branch the panel's run took (the gate binds committed bytes; with the draft present-but-untracked it correctly BLOCKS with "review artifact is not tracked", the §12.3 freeze protocol: the integrator force-adds + freezes this file at landing, which then activates the Verdict + `--verify` byte binding)
23. `cognitive-architecture-census.py --check` at tip → exit 0, every budget observed <= max incl. `framework_production_noncomment_lines 65012<=65012` (zero-headroom held; the +19-line allowance row landed in the fix commit)
24. draft restored byte-identical after the verify run; `git status --porcelain` → clean tree

---

## Must-fix list

- **F1** — `serve_objective` + `recommend` must enforce (or route through) the three serve REFUSE limbs (`counterfactual: true`, rows-hash binding, mixed-epoch/null-hole), with a pinned mutant per entry, before the serve surface is treated as contract-complete. (`framework/objectives/query.py:234-245,248-271` at base) — **DISCHARGED** at tip `27e3c0f6` (fix commit `5bafa7db`): `_load_bound` routes all three entries, `TestServeSurfaceUniformity` pins 3 fns x 3 limbs + positive controls, re-verify probe 9/9 REFUSE / 3/3 ANSWER, battery 361 passed 2 skipped, `verify-cognitive-phase3.sh` READY_FOR_CI. No open must-fix items remain.

Verdict: PASS
