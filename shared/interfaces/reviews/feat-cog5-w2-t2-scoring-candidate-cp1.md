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

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 §12/§13, W2 T2, Fable 5).
