# FW-019 checkpoint review — feat/cog5-w2-t2-scoring-candidate cp1

COG-5 W2 unit **T2** — the SCORING/CANDIDATE tests-first corpus family.
Branch `feat/cog5-w2-t2-scoring-candidate` off master `a1357829`. Contract
`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` §12 (sims 2/3/4/5/8)
+ §4/§4.5 (arming battery, both honest-negative arms) + §9.3 (certainty
grammar + SIM-2 extension arms) + §6.2/§6.3 (provenance laundering + league
closure) + §9.1 (vector law) + §13 (corpus law — this unit is purely ADDITIVE
new files; no existing test/lib/config file touched).

Batch is **three NEW test-surface files — zero framework delta, zero config
delta** (census GREEN rc=0, observed==max on every budget; tests are
budget-exempt by the census's framework-tree scope). >300 lines ⇒ this
artifact (FW-019).

## What landed
- **`cabinet/scripts/tests/lib_cog5_scoring_fixtures.py`** (NEW, T2-owned per
  the W2 naming law) — the family's reference machinery + corpus-pinned
  vocabulary: the §4.3/§4.5 arming composition over the REAL
  `regression_gate.evaluate_gate` + the REAL `gate.ratify(runner=, probe_fn=,
  root=)` seam on a SCRATCH root (gate.py consumed at call-site, byte-
  untouched); the §9.1 vector schema (`vector` separated from `table_order`;
  `unknown` quarantine; machine-floor eligibility with the incumbent-first
  tie law — a tie is not an improvement); machine-dimension ranking; the
  sim-5 divergence comparator; the sim-8 triple-run discipline (3 subprocess
  runs, distinct PYTHONHASHSEED); the §6.2 chain-of-custody ingester +
  counting predicate; the §6.3 closure validator + open predicate; the §9.3
  vocab tripwire clone; every §12-named negative-control mutant as an
  explicit function. Estate byte-binds via AST (JUDGE_HARD_BAR/MIN_PAIRS/
  BASELINE_MATCH_RATE + the states.py grammar tokens) — never an
  unallowlisted import. Guarded import of the T1-owned `lib_cog5_corpus`
  (un-joined parallel branch; see the join guard below).
- **`cabinet/scripts/tests/test_cog5_sim_scoring.py`** (NEW) — sims 2/3/4/5/8
  live on fixtures + the §4 arming battery (honest-PASS demo end-to-end
  through the real seam with per-stage non-vacuity asserts; known-bad FAIL;
  §4.5 no_verdict refusal with the named reason `no_regression_evidence`;
  §4.5 flat-candidate honest negative; escape arm = env-scrub canary +
  outside-workdir diff; Ring-0 refusal through the seam) + the §9.3
  tripwires/SIM-2 extension arms + the gate-seam LIVE pins (ratify kwonly
  seam present; gate.py/graduation.py carry NO
  regression/league/foundry/evolution token — the §4.1 weakening tripwire
  made mechanical) + vacuity-guarded arms for scorers.py / candidate.py /
  cog5-gate-arm.py (companion absence assertions + armed ModuleNotFound
  probes + probe-flip fixture proof + retirement conditions) + the T1
  shared-core join guard.
- **`cabinet/scripts/tests/test_cog5_league_closed.py`** (NEW — the exit
  battery names this file) — §6.2 provenance laundering arm (ingester stamps
  provenance from the named source class; row-supplied provenance REFUSES;
  missing/out-of-enum REFUSES; only real_live/real_mined from NAMED real
  sources count) + §8.1 synthetic-never-opens + §6.3 closure validator
  (league_open false; minimums verbatim; holdout_freeze posture; laundered
  actuals caught; YAML round-trip) + the §9.1 vector law at the league joint
  (table_order reaches no admission joint; composite may order the table;
  unknown/judge never satisfy floors) + vacuity-guarded arms for league.py +
  the §6.3 arming record (guard body already validates REAL bytes on landing).

## Mutants proven BITING in this run (a gate without a biting mutant is
decoration — §12; each has a fixture-invariant assert proving the mutant
actually escapes, then a pytest.raises proving the battery catches it)
sim 2 judge-only rank · sim 3 insensitive quarter-bucket fold · sim 4 judge-
satisfies-a-floor (X3) + promotes-on-league-score at the edge joint · sim 5
divergence-averaged-away · sim 8 nondeterminism-averaged-into-the-vector ·
§4.5 no_verdict→pass · no_verdict→fail · flat→pass · flat→error · escape
env-passthrough · escape outside-writer · §9.3 league-writes-verdict_human ·
§6.2 trusting-ingester laundering · count-all laundering · laundered actuals
block · §8.1 open-on-total-rows · §6.3 live-fitness row · missing
fitness_claim field · premature league_open flip · minimums drift · missing
holdout_freeze line · §9.1 table_order-keyed predicate.

## Self-review findings (fixed in-batch before commit)
1. **Boundary breach caught by the shipped engine:** the first draft's
   `estate_grammar()` imported `framework.objectives.states` —
   `cog2-import-gate.py` FAILED with `UNALLOWLISTED_OBJECTIVES_IMPORTER`
   (the objectives row allowlists no cog5 file). Fixed by AST-reading the
   two grammar tokens from file bytes (the family needs the tokens, not the
   module); no allowlist edit — the manifest is another unit's surface and
   this unit is additive-only (§13). Gate re-run: exit 0.
2. **Sim-3 mutant would not have bitten under a name-alphabetical tie:**
   under the insensitive fold, "improving" ties "incumbent" and the original
   name tiebreak still ranked it above — the mutant would have passed the
   battery. Fixed principled, not cosmetic: the reference ranking's TIE LAW
   is incumbent-first (a challenger outranks ONLY by strict machine
   superiority — the §4.2/§9.1 demonstrated-improvement posture), and the
   mutant now REDs.

## Evidence (this tree, python3.12)
- `python3.12 -m pytest cabinet/scripts/tests/test_cog5_sim_scoring.py
  cabinet/scripts/tests/test_cog5_league_closed.py -q` → **84 passed,
  6 skipped** (skips = the 6 designed vacuity guards: t1 core join,
  scorers/candidate/gate-arm CLI, league.py, arming record — each with a
  companion absence assertion that REDs on landing).
- `python3.12 cabinet/scripts/cog2-import-gate.py` → exit 0.
- `bash cabinet/scripts/check-layer-separation.sh` → OK (new=0).
- `python3.12 cabinet/scripts/cognitive-architecture-census.py` → exit 0,
  observed==max, zero framework delta.
- full `python3.12 -m pytest cabinet/scripts/tests -q` sweep: baseline
  3399 passed / 12 skipped before this unit; re-run green with the unit's
  +84/+6 (recorded in the unit's structured hand-back).

## Contradictions routed
None. The un-joined T1 `lib_cog5_corpus.py` is the expected parallel-wave
state, handled by the mergeability pattern (guarded import + skip +
companion), not a contradiction.

---

# FIX ROUND (cp1 fix) — fresh-context adversarial review returned FIX_FIRST

An independent fresh-context review of the batch above filed **2 MUST-FIXES
and 10 notes**. Both must-fixes were CIRCUMVENTIONS of the phase's crown-jewel
certainty laws: the corpus as written would have let a future `scorers.py` /
`league.py` violate the law with the whole battery GREEN. Both are closed,
plus four folded notes. Suites: **84 → 114 passed** (6 skipped, unchanged).

## MUST-FIX 1 — a judge-derived value satisfied a MACHINE floor (X6/§9.1)
The floor law was enforced by a dim's `kind` LABEL alone; nothing bound a
machine dim's VALUE to machine evidence, so a scorer could copy the judge's
number into `frozen_pass_rate` and be admitted. Proven repro before the fix:
`admission_eligible(proxy, incumbent) == (True, [])` with a 0.99 judge number
on both machine floor dims.

Closed by lifting the §6.2 chain-of-custody shape onto the vector: each dim
now carries a **`derivation`** stamped BY THE CONSTRUCTOR from the evidence
OBJECT it read (`rg.GateResult` → `machine:gate_result`; a `{case: bool}`
replay map → `machine:replay_map`; the sim-8 triple outputs →
`machine:scorer_triple`; a `JudgeEvidence` → `judge:llm_score`). There is no
derivation PARAMETER, so a caller can never NAME machine custody for a number
it did not measure — the wall shape of "a row arriving with its own
provenance REFUSES". `admission_eligible` now refuses, fail-closed and BEFORE
any floor is read, any machine dim on EITHER side whose derivation is
judge-sourced, absent, or out-of-enum (`[FLOOR-DERIVATION]`), and the law is
re-runnable at W6 surgery as `assert_machine_floors_machine_derived` /
`assert_derivation_refused` (`[SIM4-X6-DERIVATION]`).

New arms: `test_reference_scorer_binds_every_machine_dim_to_machine_evidence`
· `test_the_constructor_wall_no_caller_may_name_a_derivation` ·
`test_mutant_judge_derived_number_on_a_machine_floor_REDS` (the review's exact
repro) · `test_mutant_unprovenanced_machine_dim_REDS` ·
`test_a_laundered_incumbent_refuses_too`.

**Deliberately NOT added:** a mutant that hand-forges the derivation LABEL. A
value-level check cannot catch it, and the only mechanism that could (a keyed
seal over the vector) would impose an obligation on the real `scorers.py` that
NO contract clause ratifies — corpus overreach. The honest, contract-grounded
wall (`inspect.signature`: no derivation parameter exists) is armed instead,
and the residual is named here rather than papered over with a mutant that
bites nothing.

## MUST-FIX 2 — the §9.3 machine-class battery UNDER-SCANNED (two holes)
(i) `vocab_violations.walk()` scanned string VALUES only, so a row minting
`{"tested": true, "falsified": false}` as KEYS returned `[]` with the tripwire
green. The walk now scans mapping KEYS as well as values, at any depth.
(ii) Nothing enforced the P5 cap: a row carrying `certainty:
"intervention_supported"` — a REAL states.py P3 token, above the cap, and
invisible to the Captain-vocabulary regex — passed both
`assert_machine_class_vocab` and `assert_league_row_closed_shape`. The cap was
asserted only inline against the reference row-maker that sets it itself
(near-tautological).

Closed with `assert_certainty_capped`, bound to a ladder **DERIVED FROM
`framework/objectives/states.py` BYTES** (AST, never an import — the
objectives boundary row allowlists no cog5 importer, and never a hardcoded
list): a state is machine-reachable iff `derive_edge_state` has a
`return EdgeState(STATE_X, …)` whose enclosing guards do NOT test a
human-verdict fuel flag (a flag assigned True inside a branch whose test names
`HUMAN_VERDICT_SOURCE`). That derives `above_cap = {falsified,
intervention_supported}` — exactly the rungs states.py:237 calls reachable
only past "the CAP for all non-human-verdict evidence". The cap now rides
`assert_league_row_closed_shape`, so every row-validating caller inherits it.

New arms: `test_captain_vocabulary_in_a_FIELD_NAME_REDS` ·
`test_nested_captain_vocabulary_keys_are_seen_at_depth` ·
`test_machine_speak_keys_do_not_false_positive` ·
`test_p5_cap_ladder_is_derived_from_the_states_bytes` ·
`test_ladder_scan_is_a_discriminator_not_a_constant` (feeds a MUTATED
states.py and proves the derived sets MOVE — the scan is a discriminator, not
a constant) · `test_reference_rows_are_capped_at_p5` ·
`test_mutant_certainty_above_the_p5_cap_REDS[×2]` ·
`test_mutant_intervention_supported_slips_the_vocabulary_scan` ·
`test_certainty_outside_the_states_vocabulary_REDS[×4]` ·
`test_closed_league_rows_are_capped_at_the_states_p5_rung`.

## Folded notes closed
- **N1** (`reference_edge_promotion` trusted any dict carrying
  `review.source: verdict_human`, INCLUDING a league artifact; the minting
  battery that REDs was a separate call nobody composed): the predicate now
  skips machine-class artifacts BEFORE reading `review`
  (`is_machine_class_artifact`), the old class-blind body is retained as the
  named mutant `mutant_promotes_on_forged_league_review`, and
  `assert_machine_class_never_promotes` (`[SIM2X-FORGED-VH]`) composes the two
  arms. Arms: `test_sim2_extension_forged_league_row_cannot_promote_REDS` ·
  `test_composed_battery_runs_minting_and_joint_together` ·
  `test_a_real_human_verdict_still_promotes` (the honest negative — the human
  channel is not broken by the class check).
- **N2** (§6.2 says provenance can never be "set OR REWRITE"; only SET was
  armed — a post-ingest rewrite counted, and `assert_count_honest` AGREED
  because it recomputed from the same mutated row). **Chose genuine detection
  over a vacuity-guarded deferral:** ingestion now SEALS the custody fields
  under an ingester-plane key (`hmac`), so a post-ingest rewrite breaks the
  seal; the counting predicate and `assert_count_honest` both require intact
  custody. Rationale: custody-bound-at-ingest is an obligation §6.2 states
  directly, so it belongs in this unit; T1's append-only archive chain is the
  PHYSICAL counterpart and is named as such in the code. Stated honestly in
  the lib: the key models the plane boundary (§5.2 WALL), it is not a
  cryptographic defence against same-process code. Arms:
  `test_ingestion_seals_the_custody_fields` ·
  `test_mutant_provenance_REWRITTEN_after_ingest_REDS` ·
  `test_mutant_counter_ignoring_custody_REDS` ·
  `test_rewritten_rows_cannot_open_the_league` ·
  `test_laundered_actuals_from_a_rewritten_corpus_REDS`.
- **N4** (§9.1's `table_order` law was the only one of 14 with no lib-level
  battery): promoted to `assert_table_order_never_reaches_the_joint(pack,
  incumbent, predicate=…)` so integrator surgery can re-run it against the
  real joint. Arms: `test_table_order_law_holds_as_a_reusable_battery` +
  the rewritten `test_mutant_predicate_keying_on_table_order_REDS`.
- **N7** (the escape assert was a single named canary while the child env
  carried extra vars): `assert_arm_escape` now refuses any credential-SHAPED
  env NAME (`TOKEN|KEY|SECRET|PASSWORD|ANTHROPIC|OAUTH`, names only — no value
  is ever read or recorded), armed by
  `make_partial_leak_mutant_runner`, which scrubs the canary and leaks
  `ANTHROPIC_OAUTH_TOKEN` instead — defeating the old single-name check.
  Arms: `test_mutant_partial_credential_leak_REDS` ·
  `test_scrubbed_env_carries_no_credential_shaped_name`.

## Fix-round findings (paid in this round)
1. **The OS injects env vars BELOW the harness's explicit dict.** The first
   draft of the escape positive asserted `set(env) == {PATH, PYTHONHASHSEED}`
   and went RED: macOS adds `LC_CTYPE` and `__CF_USER_TEXT_ENCODING` to an
   explicit-env child. The claim "only these names reach the child" is FALSE
   and the assert now states what is true — no credential-CLASS name reaches
   it — which is exactly why the arm is a class check, not an allowlist
   equality. (This is the concrete form of the review's N7 observation.)
2. **A vacuity guard sharing a tag with the law it guards makes its own
   mutant test vacuous.** `assert_certainty_capped`'s "ladder scan went
   vacuous" guard originally raised `[P5-CAP]`, so a `pytest.raises(match=
   "[P5-CAP]")` mutant test went GREEN on a BROKEN scan. Split to
   `[P5-LADDER]`; caught by the round's own mutation proof, not by reading.
3. **A negative control that cannot reach the floor proves nothing.**
   `mutant_rewrite_after_ingest` first laundered only `generator`-class rows
   (~9 of 25 — below the floor of 10), so `test_rewritten_rows_cannot_open_
   the_league` stayed green with the custody check REVERTED. It now launders
   every non-real row and the arm discriminates.

## Verification (this tree, python3.12)
- both suites → **114 passed, 6 skipped** (was 84/6; +30 tests, skips
  unchanged — the 6 designed vacuity guards are untouched).
- **Load-bearing proof (both directions, per fix):** each fix was REVERTED in
  the lib and the paired tests re-run — every one goes RED, none merely
  passes against the good reference: MF1 joint gate 3/3 · MF1 construction
  stamp 3/3 · MF2i key walk 2/2 · MF2ii cap assert 3/3 · MF2ii byte-derived
  ladder 4/4 · N1 class skip 1/1 · N2 counting custody 4/4 · N2 ingest seal
  1/1 · N4 battery 1/1 · N7 credential class 1/1. (Run under
  `PYTHONDONTWRITEBYTECODE=1`: same-second rewrites of the lib were being
  served from `__pycache__` and silently reported a reverted fix as still
  passing — a false GREEN in the proof harness itself.)
- every `assert_*` battery is called on reference output AND has a paired
  RED-tag test; every `mutant_*` function is exercised. The two batteries
  with no paired mutant (`assert_arm_known_bad_refused`,
  `assert_arm_honest_pass` — both pre-existing, neither flagged by the
  review) were re-proven NON-VACUOUS by hand: each REDs when fed the other
  arm's pack and stays green on its own.
- `python3.12 cabinet/scripts/cog2-import-gate.py` → exit 0.
- `bash cabinet/scripts/check-layer-separation.sh` → new=0.
- `python3.12 cabinet/scripts/cognitive-architecture-census.py` → exit 0,
  observed==max, zero framework delta.
- full `python3.12 -m pytest cabinet/scripts/tests -q` → **3513 passed, 18
  skipped** = master's 3399/12 baseline + this unit's 114/6 EXACTLY (no
  collateral movement anywhere in the estate).
- corpus purity: `git diff origin/master...HEAD` touches only this unit's own
  three files + this artifact — additions only (§13).

## Review notes recorded as OUT OF SCOPE (integrator to record)
Notes **3, 5, 8, 9, 10, 11** — partial-bite nuances, sim-5 holdout-aggregate
coverage, mutant-modeling purity, hash-collision coupling, the imprecise
companion claim, and arming-record actuals — are deliberately NOT addressed in
this round and remain open. Note **6** was already resolved (sim 7's full
escape battery is unit T3's scope, not T2's).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 §12/§13, W2 T2, Fable 5).
