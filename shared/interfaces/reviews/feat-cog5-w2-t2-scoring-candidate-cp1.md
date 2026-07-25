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
derivation PARAMETER, so the LABEL channel is closed — the wall shape of "a
row arriving with its own provenance REFUSES". `admission_eligible` now
refuses, fail-closed and BEFORE any floor is read, any machine dim on EITHER
side whose derivation is judge-sourced, absent, or out-of-enum
(`[FLOOR-DERIVATION]`), and the law is re-runnable at W6 surgery as
`assert_machine_floors_machine_derived` / `assert_derivation_refused`
(`[SIM4-X6-DERIVATION]`).

> **CORRECTED BY THE NOTES ROUND BELOW.** This section originally claimed the
> constructor wall meant "a caller can never NAME machine custody for a number
> it did not measure". That statement is FALSE as written and was disproved by
> the targeted re-review — closing the label channel does not close the
> evidence channel. See "N1 — the constructor wall's claim was false".

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

---

# NOTES ROUND (cp1 notes) — the five non-blocking notes from the targeted re-review

The targeted re-review of the fix round returned **SHIP**: both must-fixes are
genuinely closed, all 9 revert groups bite, the AST ladder is proven
byte-derived and fail-closed, and the deliberate non-ship of the keyed seal was
judged CORRECT. None of that is reworked here. This round closes the five
recorded gaps — one of which is a FALSE CLAIM in the corpus, and is the reason
the round exists. Suites: **114 → 120 passed** (6 skipped, unchanged).

## N1 — the constructor wall's claim was FALSE as written (the reason for this round)
The lib and this artifact both claimed: *"there is no derivation PARAMETER, so
a caller can never NAME machine custody for a number it did not measure."* The
re-reviewer disproved it. The caller controls the `evidence` argument, and the
evidence OBJECT'S TYPE fully determined the stamp, so a machine-SHAPED object
handed in beside the judge's number stamped machine custody with **no label
forgery at all**. Reproduced on this tree before the fix:

```
make_vector({"frozen_pass_rate": (0.99, MACHINE_KIND), ...},
            evidence={"frozen_pass_rate": {"case-001": True}, ...})
  -> stamped 'machine:replay_map'
  -> assert_machine_floors_machine_derived(fake) PASSES
  -> admission_eligible(fake, incumbent) == (True, [])
```

0.99 is the judge's number; the "replay map" is one fabricated row.

**(a) The claim is corrected in BOTH the lib and this artifact.** A docstring
claiming what the bytes do not deliver is the exact failure class this program
keeps catching (§13 rule 1: docstrings are claims, run them). The lib now
states the wall as TWO named channels plus a HONEST SCOPE block naming what
stays open; the derivation-enum comment and the module-docstring vocabulary
entry are corrected to match; the fix-round section above carries a correction
banner rather than a silent edit.

**(b) The fixture-tier hole is closed — the VALUE channel.** `make_vector` no
longer accepts a machine dim's number on the caller's word: for a MACHINE dim
carrying MACHINE evidence, the value is MEASURED from that evidence
(`measure_from_evidence` — a gate result's regressed count, a replay map's
passed/total, a scorer triple's quarantine fold), the pattern `candidate_vector`
already demonstrated. A declared number that disagrees with its own evidence is
a custody breach: the vector records the MEASUREMENT (the claim never enters
it) and stamps `DERIVATION_VALUE_MISMATCH`, deliberately OUTSIDE
`MACHINE_DERIVATIONS` so the existing fail-closed path refuses it with no new
plumbing at the joint. Stamp and measurement now come from ONE classifier
(`_classify_evidence`), so they can never drift apart.

**(c) The negative control the re-reviewer named is armed.**
`mutant_fabricated_evidence_for_a_machine_dim` — a one-row fabricated replay
map beside a judge number — now REDs three ways: the joint refuses
(`[FLOOR-DERIVATION]`), the stamp battery REDs (`[SIM4-X6-DERIVATION]`), and
the value battery names why under its own distinct tag (`[SIM4-X6-MEASURED]`).
Its other machine dim is deliberately HONEST so the mutant fails for the one
reason under test.

## N3 — the residual is now in the LIB, not only the artifact
Mirroring the shape of the N2-custody `HONEST SCOPE` note, `make_vector` now
carries its own HONEST SCOPE block naming **two declared residuals**:

1. **The evidence channel is still the caller's.** A fabricated replay map that
   AGREES with its own declared value still reads as machine custody. Binding a
   replay map to the identity of the frozen corpus that produced it is an
   UPSTREAM obligation (it lives at the replay stage that mints the map, not at
   the vector layer) and §9.1 ratifies no clause for it here. Pinned by
   `test_declared_residual_self_consistent_fabricated_evidence`, which asserts
   the residual is real and instructs that the HONEST SCOPE paragraph be
   retired in the same commit if a future round closes it — so the residual
   cannot rot back into a claim.
2. **The value law is FIXTURE-tier, not re-runnable at W6.** It holds at
   CONSTRUCTION, the only place the evidence exists; a §9.1 pack carries
   `{value, kind, derivation}` and NOT its evidence, so the check cannot be
   re-derived against a landed `scorers.py` pack without an obligation §9.1
   does not ratify. Same class as the keyed seal deliberately not shipped for
   the label channel. What DOES re-run at W6:
   `assert_machine_floors_machine_derived`, `assert_no_derivation_parameter`,
   `assert_derivation_refused`.

## N2 — the armed wall is now re-runnable
The `inspect.signature` check sat INLINE in the test over the FIXTURE
constructors, so at W6 it would still have been checking fixture code (N4's
`table_order` law got the lib-battery promotion; this one did not). Promoted to
**`assert_no_derivation_parameter(*constructors)`** (`[SIM4-X6-NO-LABEL]`),
which integrator surgery points at the real scorer/vector constructor. Armed by
its own biting mutant `mutant_constructor_with_derivation_parameter` — a
constructor that DOES take derivation labels, whose forged stamp is provably
invisible to the stamp battery, which is exactly why the wall must be a
signature check.

## N4 — `[P5-LADDER]` now has its paired `pytest.raises` arm
It was the only new tag without one — proven non-vacuous by hand, unarmed in
the corpus. `assert_certainty_capped` gains the same `source=` injection seam
`estate_certainty_ladder` already carries, and
`test_mutant_broken_ladder_scan_REDS[×2]` feeds a genuinely BROKEN
`states.py`: (i) `source == HUMAN_VERDICT_SOURCE` → `source == "any"` (no rung
is human-gated, the ladder derives an EMPTY above-cap set and would pass
anything), and (ii) the P5 cap literal drifted. Each arm asserts the honest
negative on the real bytes first, so a RED can only be the integrity guard.

## N5 — trailer / provenance mismatch, reconciled
Commit `27197a63` carries `Co-Authored-By: Claude Opus 5` while the three test
files and this artifact's fix-round provenance claimed Fable 5. **The trailer is
correct** — Opus 5 did the fix round (the program moved to Opus 5 as primary on
2026-07-25; commits name the model that did the work, historical commits keep
theirs). The in-file provenance lines were single statements covering whole
files that now hold content from BOTH models, so each is now split by scope:
original build `ab8fe00a` = Fable 5; fix rounds (`27197a63` + this notes round)
= Opus 5. Both halves are true as written.

## Methodology correction carried forward (re-reviewer, worth keeping)
`git diff --stat origin/master...HEAD -- framework/ cabinet/scripts/*.py` does
**NOT** return empty for a tests-only batch: git pathspec wildcards match `/`
and recurse, so `cabinet/scripts/*.py` swallows `cabinet/scripts/tests/*.py`.
Reproduced here — the naive form reports "3 files changed, 3429 insertions(+)"
and reads as a framework delta that does not exist. Use
`':(glob)cabinet/scripts/*.py'`, which stops at the slash and correctly returns
empty. Future rounds should not re-pay this.

## Verification (this tree, python3.12)
- both suites → **120 passed, 6 skipped** (was 114/6; +6 tests). The 6 skips
  are unchanged in IDENTITY and REASON, not merely in count: t1 shared-core
  join · candidate · gate-arm-cli · scorers · league.py · arming record.
- **Load-bearing proof (both directions, cache PURGED before every run, plus
  `PYTHONDONTWRITEBYTECODE=1`):** 5 new revert cases + 4 spot-checks of the
  previously verified groups, each proven green → REVERTED-RED → restored-green:
  N1b whole value law 1/1 · N1b mismatch STAMP alone 1/1 · N2 signature check
  1/1 · N4 ladder-vacuity guard 1/1 · N4 cap-drift guard 1/1 · SPOT MF1 joint
  gate 3/3 · SPOT MF1 construction stamp 3/3 · SPOT MF2ii cap assert 3/3 ·
  SPOT MF2ii byte-derived ladder 2/2.
- **Finding paid in this round (defence in depth, recorded because it changed a
  proof):** reverting the MF1 construction stamp ALONE no longer REDs
  `test_mutant_judge_derived_number_on_a_machine_floor_REDS` — the new value law
  independently catches that revert via the mutant's second machine dim. The
  group still bites (the other 2 of its 3 tests RED), and reverting the stamp
  and the value law TOGETHER REDs the third. A masked revert is not a dead
  revert, but it must be reported as masked, not as biting.
- `python3.12 cabinet/scripts/cog2-import-gate.py` → exit 0.
- `bash cabinet/scripts/check-layer-separation.sh` → new=0 (baseline 24,
  allowlist 19, current 43).
- `python3.12 cabinet/scripts/cognitive-architecture-census.py` → exit 0,
  observed==max, and its output is BYTE-IDENTICAL to the same script's output
  on a pristine `origin/master` clone (diffed, not inferred).
- full `python3.12 -m pytest cabinet/scripts/tests -q` (SERIAL, isolated
  clone) → **3519 passed, 18 skipped** = master's 3399/12 baseline + this
  unit's 120/6 EXACTLY. Delta vs the previous round: +6 passed, +0 skipped, no
  collateral movement anywhere in the estate.
- corpus purity: `git diff --name-status origin/master` → all four paths
  status **A**, zero deletions on every path (§13 additive-only).
- `ast.parse` over the three unit files read from the pushed commit's BYTES
  (`git show <sha>:<path>`) → clean.

## Still open after this round (stated plainly)
Review notes **3, 5, 8, 9, 10, 11** from the ORIGINAL review remain out of
scope and open (integrator to record), unchanged by this round. The two
declared residuals in N3 above are deliberate, contract-grounded non-ships,
not oversights.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 §12/§13, W2 T2). Original cp1
batch: Fable 5. Fix round + this notes round: Opus 5 (the program's primary
model from 2026-07-25).
