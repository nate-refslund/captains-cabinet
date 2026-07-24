# Review — feat/cog4-w5-x1 cp1 (COG-4 W5 x1: dispatch-shadow CLI)

**Batch:** `cabinet/scripts/cog4-dispatch-shadow.py` (new CLI) +
`cabinet/scripts/tests/lib_cog4_dispatch_adapter.py` (new retirement-vehicle
adapter lib) + `cabinet/scripts/tests/test_cog4_dispatch_cli.py` (new unit
battery, 59 tests) + this artifact. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §7.3 (six-limb
recheck), §7.4 (fallback + pointer tripwire), §8.4 (dispatch import pin),
§13 (corpus immutable — ZERO edits under existing tests; verified by
`git status` scope).

## Self-review findings (checked before commit)

1. **Import pin** — `lib_cog4_ast_pins.dispatch_import_violations(repo) == []`
   over the real CLI: only `framework.scheduler.serve` +
   {risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap} +
   `graduation.evaluate` + stdlib. The model/kernel modules are OFF-pin, so
   the store-vocabulary literals ("schedule_rows_hash", the three artifact
   names) are documented mirrors used ONLY to classify a loader refusal —
   rows are never served around `serve_schedule` (F1).
2. **Hermetic closure** — a full green pipeline run (runpy, rc 0) loads no
   `framework.acting` / `framework.frontdoor` module: hermetic mode never
   calls `_act_with_undo_gap` (its probes import the doors at call time);
   the declared-undo-gap check (`undo_contract` "none" under an
   `act_with_undo` verdict) carries the hermetic N5 obligation. `--live-joint`
   is the documented machine-state-dependent operator mode.
3. **Fail-closed sweep** — absent/malformed descriptor, budget_units,
   freshness_needs, idempotency discipline, organ manifest, deps shape:
   each refuses THAT row with a named reason; unknown verdict tokens and
   underivable action_types refuse fail-safe (`authority:propose_only`);
   recorded-null wake-input hashes refuse symmetrically (N3).
4. **Budget accounting** — refused rows consume no budget (fixture parity);
   cumulative only advances on `would_dispatch` (N4 tested incl.
   planner-admitted overflow).
5. **SF1** — key re-derived from the manifest discipline over
   {organ, operation, wake_id} with the corpus canonical dialect
   (ensure_ascii=False; byte-equal to the corpus derivation); row-carried
   keys ignored; replay gated across runs through the persisted log;
   corrupt log = loud setup refusal (never guess).
6. **Atomicity** — shadow-log append: O_EXCL lock (loser fails loud) +
   O_EXCL tmp + fsync + os.replace; the CLI writes ONLY the shadow log
   (store-bytes purity tested).
7. **Known accepted shapes** — (a) refusal-reason classification maps the
   kernel's message text to the corpus tokens (`rows_hash_mismatch`,
   `rows_hash_key_absent`, `snapshot_hash_mismatch`) after an availability
   probe; unmatched integrity messages surface honestly as
   `serve_refused:<kernel detail>` — no limb is ever skipped by
   classification (serve already refused). (b) planner `defer` rows are
   recorded `refused/planner_deferred:<reason>` (limb `planner`) — grants
   nothing, rechecks nothing. (c) the pointer default reads `~` by design
   (the tripwire targets operator machine state; tests inject
   `--pointer-path`).

## Corpus/arm state at this commit (handoff to the integrator)

The 11 W2 vacuity arms keying on this CLI flip skip→RED by design (their
companion absence assertions; retirement texts name the integrator move):
`test_cog4_dispatch_ast_pin.py::test_real_cli_is_armed_and_absent` + the 10
`test_cog4_sim_dispatch.py::TestRealDispatchCliArms` arms. The post-surgery
state is PRE-PROVEN GREEN out-of-band by `test_cog4_dispatch_cli.py`
(same seeds/asserts, real CLI, real kernel stores) — 59/59 green.
Full sweep: 3255 passed / 11 designed-RED / 18 pre-existing skips (none
added, none removed). cog2-import-gate exit 0; layer-sep 0 new; census
unchanged (zero framework delta — cabinet-side unit).

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-for-execution (Captain
2026-07-23 calibration) — this unit authored on Fable 5.
