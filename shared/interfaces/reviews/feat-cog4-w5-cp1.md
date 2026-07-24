# Review — feat/cog4-w5 cp1 (COG-4 W5 landing: dispatch-shadow + non-software cabinets + N9 parity record)

**Batch:** the three reviewed W5 units landed by pure ancestry (x3 ⊃ x2 ⊃ x1,
branch cut at origin/feat/cog4-w5-x3 = ea9da8ad; zero cherry-picks) + the
integrator corpus surgery (§13) + the two egg-manifest anchors + this
artifact. Contract: `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md`
§7.3/§7.4/§8.4 (x1), §12 N8/MR4 + §5.2/§5.4/§5.5 (x2), §1 N9 + §5.3 + §9.3
(x3), §13 (integrator-only corpus surgery).

## Units + chains (all three SHIP on first pass — zero fix rounds this wave, a first)

* **x1 — 7272db13** `cog4-dispatch-shadow.py` (§7.3 six-limb shadow
  comparator, SF1 idempotency, §7.4 tripwire) + `lib_cog4_dispatch_adapter.py`
  (the retirement vehicle) + `test_cog4_dispatch_cli.py` (59 tests, the
  out-of-band pre-proof). Review: feat-cog4-w5-x1-cp1.md — SHIP first-pass.
* **x2 — 4e8e3cec** three non-software fixture cabinets (garden-delivery,
  care-rota, harbor-warehouse; six §4.2-shaped manifests) end-to-end through
  the REAL CLI chain + `test_cog4_exit_fixtures.py` (8 tests, N8/MR4).
  Review: feat-cog4-w5-x2-cp1.md — SHIP first-pass.
* **x3 — ea9da8ad** the tracked N9 parity record + five S0 pilot manifests +
  `lib_cog4_parity_set.py` + `test_cog4_parity_record.py` (6 tests).
  Review: feat-cog4-w5-x3-cp1.md — SHIP first-pass.

## N9 PARITY HOLDS — 33/33 operations, zero divergent tuples

The tracked `cabinet/scripts/tests/fixtures/cog4/cog4-parity-record.json` is
the REAL `cog4-parity.py` two-independent-leg output over the entire pilot
set + all three fixture cabinets: **33 operations across 11 organs,
`record_errors == []`, `divergent_rows == []`** (independently recomputed at
landing). The descriptor-path tuple equals the ACTION_TYPES-path tuple on
every row — the evidence that the ACTION_TYPES plane is demonstrably only a
compatibility adapter (§5.3): nothing the descriptor plane enforces diverges
from it anywhere in the covered surface. Byte-reproducible from the committed
manifests across three PYTHONHASHSEEDs (x3 gate, re-proven in the landing
sweep).

## Integrator corpus surgery (per §13 + the unit contradictions[] routes, W5 landing 2026-07-24)

* **S1** — `test_cog4_sim_dispatch.py::TestRealDispatchCliArms`, all 10 arms
  (sims 3/5/6/9/10/11/12/14/15 + the §7.3 order battery): companion absence
  assertions tripped RED as designed on the x1 CLI landing; each arm retired
  per its docstring RETIREMENT CONDITION — same scenario seeds + same
  asserts, re-seeded onto REAL kernel-shaped stores via
  `lib_cog4_dispatch_adapter` (fixture-policy translated to the
  matrix_policy shape) and run against the landed CLI. All 10 LIVE GREEN.
  The dead `_absent_then_skip` guard deleted with the skips; the reference
  tier + every biting mutant stay untouched.
* **S2** — `test_cog4_dispatch_ast_pin.py`: vacuity arm retired per its text
  ("delete the skip, keep the green-by-vacuity assertion as the real pin") →
  `test_real_cli_scans_clean` now runs the live
  `dispatch_import_violations` scan over the REAL file. GREEN.
* **S3** — `test_cog4_parity.py::TestParityGateRealArtifact::
  test_real_record_arm`: record-keyed companion tripped RED on the x3 record
  landing; retired per its text — the arm now loads THE tracked record
  (singular, location pinned to `lib_cog4_parity_set.RECORD_PATH`) and gates
  it through the W2 reference checkers (`record_errors == []`,
  `divergent_rows == []`) + exact organ/operation coverage of the
  pilot+cabinet union. LIVE GREEN.
* **S4** — `test_cog4_parity_cli.py::TestBoundaryLawsLive::
  test_no_record_ever_written_inside_the_repo_by_this_battery` (x3's genuine
  additional finding): the whole-repo stray-record law now exempts EXACTLY
  the one tracked fixture path (a DELIBERATE W5-x3 artifact, not battery
  output; dated note in the test). The law still bites: scratch probe placed
  a stray record at `cabinet/scripts/cog4-parity-record.json` → test RED;
  removed → green.
* **S5 sweep law** — zero unexplained failures (reconciliation below).

## x2 SHAPE-NOTE reconciliation (recorded, no code change — no test demanded one)

The §4.2 cabinet manifests declare `idempotency` as an **op-id → discipline
string** map (packaging metadata, e.g. `garden/rota.compile: "week-of"`);
the dispatcher's organ-manifests INPUT uses the W2 dispatch-corpus shape
`idempotency: {key_fields: [...]}`. Reconciliation as x2 shipped it: the
dispatcher input DERIVES from the §4.2 manifest; the per-op discipline
strings stay packaging metadata and are never row-trusted — limb 6
re-derives keys from run context {organ, operation, wake_id} (SF1), which
x2's end-to-end replay probes proved against the real CLI. No contradiction
outstanding; nothing to change in either surface.

## Landing verification (this clone, python3.12)

* Full `cabinet/scripts/tests` sweep: **3281 passed / 17 skipped / 0
  failed**. Reconciles exactly vs the post-W4 baseline 3196 passed / 29
  skipped / 0 failed: +73 unit tests (x1 59, x2 8, x3 6) and 12 baseline
  skips converted to LIVE passes by S1–S3 (10 sim arms + 1 ast-pin arm + 1
  record arm); S4 restored the x3-tripped hygiene law to green (net-zero on
  counts). 3196+73+12 = 3281; 29−12 = 17; 0 failed.
* `framework/` suite: 6432 passed / 26 skipped / **1 pre-existing
  machine-local failure, NOT this wave's** —
  `fidelity/tests/test_retro_shim.py::test_reexports_constants` pins
  `LLM_MODEL == "claude-sonnet-4-6"` while the shim resolves the constant
  from this machine's live `~/.screenpipe/pipes/retrodiction/lib.py` (now
  `claude-sonnet-5`). Reproduced byte-identically on a pristine master
  (75da084f) worktree; CI's lib-less flavor takes the stub path and stays
  green. Out of W5 scope (framework/fidelity, no W5 diff touches it);
  routed to the meta-workspace backlog.
* Gates: `cog2-import-gate` exit 0 · layer-sep new=0 (baseline 24 /
  allowlist 19) · census PASS with ZERO framework delta (236 modules /
  66409 noncomment lines, all ratchets at baseline) · egg-export verify
  PASS incl. the two NEW anchors (`expect-present
  cabinet/scripts/cog4-dispatch-shadow.py`, `expect-present
  cabinet/scripts/tests/fixtures/cog4/cog4-parity-record.json` — the W4
  comment's "rides the W5/W6 pilot" trail closed) · germline byte-untouched
  (changed-path ∩ germline set = ∅) · ledger parses from HEAD bytes.

Provenance: integrator landing per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant; W5 landing integrator on
Fable 5 (judgment tier — corpus surgery is integrator judgment work).
