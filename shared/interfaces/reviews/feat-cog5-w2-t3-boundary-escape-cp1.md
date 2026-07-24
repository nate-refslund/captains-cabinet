# FW-019 checkpoint review — feat/cog5-w2-t3-boundary-escape cp1

COG-5 **W2 corpus, unit T3 — BOUNDARY/ESCAPE family**. Branch
`feat/cog5-w2-t3-boundary-escape` off master `a1357829`. Contract
`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` §12 sims 6/7/11 +
the X5/X7 exit arms + §12.1 (the declared regression bound). Tests-first,
gates-before-code; batch is **NEW test/lib files ONLY — zero framework/config
delta** (census GREEN, observed==max on all 10 budgets; tests are
budget-exempt). Batch ~2166 lines ⇒ this artifact (FW-019).

## What landed (4 new files, all ADDITIVE — corpus law §13)
- **`cabinet/scripts/tests/lib_cog5_boundary_fixtures.py`** (T3-OWNED; every
  public helper prefixed `lib_cog5_boundary_`). Imports the committed
  `framework.evolution.contracts` surface (REUSE, read-only) and guards a
  SELF-ARMING optional import of the t1-owned `lib_cog5_corpus` (skips while
  absent, arms at integration — never created here). Fixture machinery:
  allowlist env-scrub + credential-marker leak detector (marker NAMES
  assembled at runtime; values are explicit fixture fakes — no secret is ever
  represented); both-ways git hooksPath pinning + euid-refusal + outside-
  workdir fingerprint/diff + 127.0.0.1-only egress probe (the gate
  `_default_runner` laws replicated, never imported); cost-ceiling snapshot
  guard + snapshot-digest drift; the §6.2 provenance closed enum +
  ingester-stamped custody + counting predicate; X7 case-metadata validator;
  the S0 baseline-artifact parser + linear percentile + floor-aware
  wall-clock bound + pass-state/files-swept/sweep-violation checkers.
- **`test_cog5_sim_boundary.py`** — sim 6 (holdout leakage) + X7 + §7.4
  Stage-A honesty + §6.2 synthetic-never-counts. LIVE: aggregate-only receipt
  validates via `validate_holdout_receipt`; every per-case-carrying receipt
  refuses structurally; league/generator scratch imports of the holdout
  module RED under the SHIPPED engine + W1 ROW 8.
- **`test_cog5_arena_escape.py`** — sim 7 (credential/network escape) + X5 +
  sim 11 (cost explosion). LIVE: scrubbed-env-observed via subprocess;
  hooksPath both-ways; euid law; outside-workdir diff empty; loopback egress
  instrument; the reference league loop halts/defers with a recorded reason
  and archives per-candidate cost.
- **`test_cog5_measurement.py`** — the §12.1 declared-bound armed twin
  (`COG5_ENFORCE_BOUND`, the COG-4 N6 shape cloned). LIVE: the LANDED
  §12.1.1 baseline artifact parses fail-loud and its numbers reconcile (p95
  recomputes to 182.76 s; the formula reproduces 228.4 s; pass-state green;
  sweep violations 0); anti-phantom consumer scanner (this file is the
  designated consumer) with scratch bite controls.

## Biting negative controls — proven NOW on scratch fixtures (contract §12)
Each mutant asserts BOTH the escape (mutant tolerates) AND the real gate's
bite, in one test body:
- sim 6 — **per-case field tolerated in a receipt**: a schema-dropping
  tolerant validator returns `()` on a leaking receipt while
  `holdout_receipt_structural_issues` REDs (demonstrated live);
  **allowlisted league import of holdout_gen**: a mutated manifest copy
  allowlisting the league scans the same tree CLEAN that the real manifest
  REDs — side by side.
- sim 7 — **env-passthrough** (planted fake credentials survive → detector
  finds ≥4) vs the scrubbed env (0); **hook-execution-not-disabled** (hostile
  pre-commit runs, sentinel present) vs both-ways pinning (no sentinel);
  outside-workdir write mutant → named non-empty diff.
- sim 11 — **cost-ignoring loop** keeps spending (165 > 100, no halt) → the
  overrun oracle REDs; **league-tunable ceilings** → snapshot-digest drift
  REDs; missing per-candidate cost → named finding.
- §12.1 — **seeded battery RED** / **vanished baseline test** / **inflated
  wall-clock stub** / **unexplained sweep growth** each RED when armed
  (monkeypatch on the same env seam the twin will export).
- X7 — a metadata-less case REFUSES ingestion (every required field).
- §6.2 — a `synthetic`-marked row counted toward a minimum REDs; laundering
  (real provenance from a non-real source) REDs; the ingester stamp
  overwrites candidate-set provenance.

## The mergeability pattern (contract §13; proven)
Every arm targeting not-yet-built surfaces (`framework/evolution/{sandbox,
arena,league,holdout_gen,bench_factory}.py`, the `cog5-holdout-oracle`/
`cog5-league` CLIs, `verify-cognitive-phase5.sh`) carries a vacuity SKIP with
an explicit RETIREMENT CONDITION in its docstring PLUS a COMPANION absence
assertion. Demonstrated: touching `framework/evolution/holdout_gen.py` turns
`test_holdout_gen_absent_companion` RED; removing it greens again. Fixture-
machinery arms run LIVE. The wave merges GREEN on the bare tree where no
implementation exists.

Synthetic-corpus law encoded where the family touches it: every league-ish
fixture row carries `fitness_claim: 'none'` (§6.3) and synthetic/sim_replay
provenance, and the §6.2 counting predicate counts ZERO of them — synthetic
never opens the league or grounds a live-fitness claim.

## Verification (re-runnable — a reviewer re-runs everything)
- New suites on the BARE tree: `test_cog5_sim_boundary.py` + `test_cog5_
  arena_escape.py` = 57 passed / 8 skipped; `test_cog5_measurement.py` = 22
  passed / 2 skipped (armed `COG5_ENFORCE_BOUND=1` = 23 passed / 1 skipped —
  the posture arm goes live, proving it is a posture skip not vacuity). All
  10 skips are vacuity/posture/self-arming, each justified.
- Full existing sweep: `pytest cabinet/scripts/tests/` = **3478 passed / 22
  skipped**, zero failures (cog4 + cog5-W1 untouched + passing;
  `framework/evolution/tests` 47 passed — contracts REUSE read-only).
- `cog2-import-gate.py` exit 0 (my files join the sweep; assembled-token
  discipline — no foreign data-plane store token as a literal); layer-sep
  exit 0 (new=0); census exit 0 (all budgets observed==max).

Model: authored on **Fable 5** (judgment tier — corpus authorship). Provenance:
per the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant.
