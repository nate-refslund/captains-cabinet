# Review — feat/cog4-w6-e3 cp1 (COG-4 W6 e3: §10 latency/cost MEASUREMENT)

FW-019 batch proof for the COG-4 W6 e3 measurement unit (branch
feat/cog4-w6-e3, from feat/cog4-w6-e2). Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §10 + §1 N6 (MR2 —
the phantom-M6 class must not recur, LESSONS L1102). Self-ratified per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan grant;
Fable-for-execution allowed (2026-07-23), unit ran on Opus 4.8 1M.

## 1. What landed (the §10 measurement surface)

| file | disposition | purpose |
|---|---|---|
| `cabinet/scripts/cog4-measure.py` | NEW (503 lines) | the §10 measurement CLI — deterministic proxies (always-on, EXACT) + wall-clock (measured tripwire, env-armed); `--baseline` writes the dated S0 artifact, `--check` gates against it (the REAL same-commit armed consumer, §10.3) |
| `cabinet/scripts/tests/fixtures/cog4/cog4-measure-baseline-2026-07-24.json` | NEW (tracked, phase record) | the dated S0 baseline — proxies (5 activations / 5 budget units) + per-organ wall-clock p95 (frozen S0 measurement); sibling of the N9 `cog4-parity-record.json` |
| `cabinet/scripts/verify-cognitive-phase4.sh` | EDIT (twin flip) | the §10 armed leg flipped LIVE — e1's file-existence deferral discharged; unconditional `export COG4_ENFORCE_BOUND=1` + a real `cog4-measure.py --check` against the S0 baseline |
| `cabinet/scripts/tests/test_cog4_measure_baseline.py` | NEW (299 lines) | pre-proves OUT-OF-BAND, GREEN (16/16), exactly what the two retired corpus arms will assert + the drift-pin + the CLI mutants (mirrors `test_cog4_parity_record.py`) |
| `cabinet/scripts/egg-export-manifest.txt` | EDIT | CLI + baseline ride the egg (expect-present, the parity-record precedent); the twin-binding pre-prove test is phase-landing tooling — deleted from the egg (the twin it binds never ships) |

## 2. The two metric classes at exactly §10.5 honesty strength

- **Deterministic proxies (always-on, EXACT):** the composed wake vehicle
  (`cog4-organ-runner`) is SCHEDULER-BLIND (§9.5) — one activation per composed
  organ per fixed wake — so the pilot's per-wake activation set is a
  DETERMINISTIC projection of the real composed manifests (one decision row per
  organ; `budget_units` = `cost_model.units_per_wake`; `descriptor.capability`
  = the first namespaced `domain_operation`). Folded from the MATERIALIZED
  `schedule.jsonl` (written, re-parsed — "from the schedule artifact", §10),
  fold shape byte-identical to the corpus reference
  `test_cog4_measurement.proxies_from_schedule_rows`. EXACT tolerance: measured
  > baseline REDs. Proven equal to the corpus fold on both the fixture rows and
  the real measurement rows.
- **Wall-clock (measured tripwire, env-armed):** per pilot organ, the per-wake
  PLANNING wall-clock (manifest load + validate + project — the composed-runner
  orchestration overhead COG-4 introduces), measured in-process/hermetically
  (planning overhead only). Bound = `max(p95*1.25, p95+5s)` for sub-10s rows —
  the S0 floor-aware note. The absorbed projection scripts' OWN runtime is
  UNCHANGED by composition (same absorbed command) and out of scope; a
  deploy-host full-latency path (non-hermetic, never CI) is a possible FUTURE
  mode, NOT implemented by this CLI. Asserted ONLY when armed
  (COG4_ENFORCE_BOUND=1); unarmed = DECLARED skip.

## 3. The bound helper — self-contained, drift-pinned (not a test-lib import)

`cog4-measure.py` carries its OWN `wall_clock_bound` (a CLI that rides the egg
must not import a `tests/` lib, and dragging `framework.watchdog` via
`lib_cog4_floors` would be a spurious coupling). The drift-tripwire
`test_cog4_measure_baseline.py::test_drift_pin_bound_equals_corpus_helper` binds
it BYTE-EQUAL to the corpus `lib_cog4_floors.wall_clock_bound` across the pinned
value table (0, .005, 2, 9.99, 10, 40, … + error parity) — the contract's
drift-pin idiom (§4.2 undo-grammar precedent). One formula, proven identical.

## 4. Negative controls (§10.4) — all bite

- inflated `cost_model` (units_per_wake 1→800) → `budget_units_total 804 > 5`
  REDs on the exact budget proxy, always-on (no arm). Over-activation NOT fired.
- extra composed organ → `activations 6 > 5` REDs, always-on.
- inflated p95 (undo-sweep 8.0 vs bound 7.0) → wall-clock RED when armed; the
  in-bound row (12.5 <= 15.0) stays clean.
All three exercised at the CLI level (subprocess, mutant organ dir) in
`test_cog4_measure_baseline.py::TestSeededRegressionMutants` — GREEN.

## 5. Corpus contradictions (CORPUS IMMUTABLE §13 — integrator surgery)

Two W2 corpus arms in `test_cog4_measurement.py` are RED BY DESIGN (the W1-u2
companion-failure idiom) now that the §10 surface has landed; a builder cannot
edit the corpus, so the retirement routes via `contradictions[]` and this unit
pre-proves both GREEN out-of-band:

1. `TestAntiPhantomConsumer::test_verify_twin_arm` — RED (twin exists + carries
   `COG4_ENFORCE_BOUND` → `pytest.fail("retire this vacuity skip")`). The
   retired arm keeps "the twin consumes COG4_ENFORCE_BOUND" — pre-proven by
   `test_twin_consumes_the_flag` + `test_twin_arms_the_flag_live`.
2. `TestWallClockTripwire::test_real_pilot_measurement_arm` — flipped SKIP→RED
   by landing `cog4-measure.py` (`assert not cli.exists()`). The retired arm
   loads the real baseline, binds measured p95 to the bound, binds real proxies
   to the S0 baseline — pre-proven by `TestProxiesReproduceExact` +
   `TestWallClockBoundBinding` + `TestArmedCheckLive`.

## 6. Verification (committed bytes)

- cog4 sweep: unarmed `5 failed / 686 passed / 2 skipped`; armed
  `5 failed / 687 passed / 1 skipped`. The 5 fails are ALL designed retire-me
  vacuity arms: the 2 measurement arms above (mine, pre-proven) + 3 pre-existing
  (e2 floor + 2 runner arms — e2's recorded contradictions). ZERO unexplained.
- `test_cog4_measure_baseline.py`: 16/16 GREEN.
- cog2-import-gate exit 0; check-layer-separation OK; census --check rc 0
  (cabinet-side footprint only — ZERO framework modules/lines, no allowance
  row); egg-export 58 passed; A13 parity green; HEAD-bytes parse OK.
- **Rollback rehearsal is DESIGNED-RED on this unit branch** (sibling residue:
  `cog4-measure.py` + the S0 baseline + this FW-019 review are uncovered by the
  §16 manifest's remove list). Per the manifest's `sibling_landing_note` (lines
  54-60) the LANDING INTEGRATOR extends `cognitive-core-phase-4-rollback-
  manifest-2026-07-24.yml` AND the review-scope twin frozenset in the SAME
  commit (a drift check forces the pair) — a builder must NOT touch either
  half. The strict inverse-diff equality IS the completeness ratchet, working.

## 7. For the LANDING integrator (surgery this unit routes)

1. Retire `test_cog4_measurement.py::test_verify_twin_arm` to keep only the
   first assertion (twin consumes `COG4_ENFORCE_BOUND`).
2. Retire `test_cog4_measurement.py::test_real_pilot_measurement_arm` to bind
   the real pilot baseline (load `cog4-measure-baseline-2026-07-24.json`; each
   organ measured p95 <= `lib_cog4_floors.wall_clock_bound(baseline)`; real
   proxies == baseline). `test_cog4_measure_baseline.py` is the green template.
3. Extend the §16 rollback manifest remove list + the review-scope twin
   frozenset (same commit): `cabinet/scripts/cog4-measure.py`, the baseline
   (already under the `cabinet/scripts/tests/fixtures/cog4` dir entry),
   `cabinet/scripts/tests/test_cog4_measure_baseline.py`, this review artifact.

Verdict: PASS (unit-branch scope — designed corpus/rehearsal reds are the
integrator's surgery, pre-proven/recorded here).
