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
  arena_escape.py` = 61 passed / 8 skipped; `test_cog5_measurement.py` = 22
  passed / 2 skipped (armed `COG5_ENFORCE_BOUND=1` = 23 passed / 1 skipped —
  the posture arm goes live, proving it is a posture skip not vacuity). All
  10 skips are vacuity/posture/self-arming, each justified.
- Full existing sweep: `pytest cabinet/scripts/tests/` = **3482 passed / 22
  skipped**, zero failures (cog4 + cog5-W1 untouched + passing;
  `framework/evolution/tests` 47 passed — contracts REUSE read-only).
- `cog2-import-gate.py` exit 0 (my files join the sweep; assembled-token
  discipline — no foreign data-plane store token as a literal); layer-sep
  exit 0 (new=0); census exit 0 (all budgets observed==max).

Model: authored on **Fable 5** (judgment tier — corpus authorship). Provenance:
per the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant.

---

# cp2 — FIX ROUND (adversarial review returned FIX_FIRST, one must-fix)

Fix authored on **Opus 5** (execution tier — a scoped, reviewer-specified
close). Files touched: this unit's own four + this artifact. Zero
framework/config delta (census output byte-identical to master).

## M1 — the "credential files" seed class had NO arm (sim 7 / X5 / §4.4)
Row 7 names four seed classes; three were instrumented (env, network,
out-of-workdir writes). Credential-file READ reach had none, while the module
docstring quoted the seed VERBATIM including "credential files" — a docstring
claiming what the bytes did not deliver (§13 rule 1).

**The hole, reproduced before fixing** (read-only, path reasoning only —
nothing under the real home was ever stat-ed): under this corpus's own
`lib_cog5_boundary_scrub_env(...)`, `HOME` is absent from the scrubbed env,
but `Path.home()` → `os.path.expanduser('~')` falls back to
`pwd.getpwuid(os.getuid()).pw_dir` when HOME is ABSENT, so home still
resolved to the real home. **Absence is not confinement.** A candidate that
READS a credential and copies it INWARD is invisible to both shipped
instruments: the env detector is name-keyed over the environment (a file is
not an env var) and the X5 fence is write-keyed over the OUTSIDE tree (an
inward copy leaves it byte-identical).

**Closed by** (all in T3-owned files):
- `LIB_COG5_BOUNDARY_HOME_CREDENTIAL_CLASSES` — the four §4.4-named path
  classes (screenpipe dir, OAuth/credential cache, `.env`, keychain dir),
  names assembled at runtime per the file's existing discipline.
- `lib_cog5_boundary_plant_home_credentials()` — plants EXPLICITLY-FAKE
  fixture files under a SCRATCH home. No real credential file is ever read,
  copied, or represented.
- `lib_cog5_boundary_home_resolution_probe()` — resolves `Path.home()` in a
  candidate subprocess and reports it. Stats nothing, so it is safe against
  any env (including the escaping one it exists to expose).
- `lib_cog5_boundary_home_reach_probe()` / `..._home_reach_findings()` — the
  fenced reach probe + its NAMED-findings oracle, with optional `copy_into`
  to demonstrate read-then-exfiltrate.
- **TWIN SAFETY FENCES** inside the probe: it refuses if the resolved home is
  the real pwd home, AND refuses if it lies outside a caller-declared scratch
  root. Proven redundant: disabling the first still refuses via the second.

**CONFINEMENT MECHANISM chosen** — an EXPLICIT `HOME` OVERRIDE pointing into
the arena workdir (the same override seam the scrub already uses for
`ARENA_WORKDIR_MARKER`). Rationale, stated in both docstrings: expanduser
consults `HOME` first and falls back to pwd only when it is ABSENT, so an
override confines what mere absence does not.

**DECLARED RESIDUAL, not claimed closed**: the override binds
expanduser-based resolution only — a candidate calling `pwd.getpwuid()`
directly still learns the real home path. Closing that needs an OS-level
fence, which is the W3 harness's job; the probe therefore REPORTS `pwd_home`
and the positive arm asserts the residual rather than hiding it.

## New arms (4, in `test_cog5_arena_escape.py::TestHomeCredentialReach`)
1. `test_home_unset_alone_does_not_confine_home` — the hole pinned as a test.
2. `test_confined_candidate_observes_no_credential_reach` — POSITIVE arm.
   Credentials ARE planted in a sibling harness home, so the empty finding
   set is a real discrimination, not an absence of anything to find.
3. `test_mutant_unconfined_candidate_reaches_planted_credentials` — MUTANT:
   all four classes reached and named.
4. `test_shipped_instruments_are_blind_to_the_credential_read` — the review
   finding itself pinned: on the same escape the env detector returns `[]`
   AND the X5 diff returns `[]`, while the new detector names all four.

## Both-directions proof (break-the-reference discipline, 4 experiments)
Run in a throwaway copy; the deliverable clone was never dirtied.
- **M-A detector blinded** (`..._home_reach_findings` → `[]`): arms 3 and 4
  RED; arms 1 and 2 correctly unaffected (they do not depend on naming).
- **M-B confinement dropped** (positive arm's HOME override removed): arm 2
  REDs — and the real-home fence caught it, so even the broken case never
  stat-ed a real credential path.
- **M-C one fence removed**: arm 1 still passes because the twin fence fires
  (`REFUSED (outside-scratch)`). Recorded honestly as evidence of redundancy,
  not as a bite. The both-fences-off experiment was NOT run: it would stat
  real credential paths, which the standing constraint forbids. Arm 1's
  `pytest.raises` is instead proven non-vacuous by arm 2, where the identical
  call returns normally.
- **M-D manifest glob widened** (ROW 8 `allowlist_globs` += `framework/
  evolution/*.py`): the new N5 pin REDs with its named message; restoring
  greens it.

## Also closed (reviewer's N1/N5)
- **N1** — `test_flag_has_a_real_consumer_now` docstring now states plainly
  that the assertion is SELF-SATISFYING at W2 (the corpus CARRIES the
  invariant) and that the real guarantee is the twin-arm pair.
- **N5** — `test_stage_a_interim_is_honest_not_ring0` now `pytest.skip(...)`s
  with a reason at Stage B instead of silently `return`-ing, so the Stage
  A→B transition is visible in the skip report; and its ROW 8 pin now checks
  `allowlist_globs` (pinned to the one sanctioned glob,
  `cabinet/scripts/tests/test_cog5_holdout_*.py`) as well as
  `allowlist_exact` — a widened glob admits a reader without ever touching
  the exact list.

## W3 retirement condition — EXTENDED
The REAL-HARNESS escape arm previously enumerated only "scrubbed env
observed, egress blocked, workdir confinement, euid/hooksPath laws", so W3
could have declared the escape sim green with the harness still leaking the
keychain. It now also binds credential-file/home-reach confinement — the
§4.4 path classes unreachable AND the pwd-fallback residual fenced at the OS
layer, not merely via HOME — with the explicit line: *the escape sim is NOT
green while the harness can still reach a credential file.* The companion
absence-assertion message was updated in the same commit to match.

## cp2 verification
- Unit suites: **83 passed / 10 skipped** unarmed (was 79/10), **84 / 9**
  armed (was 80/9). Skip count unchanged — the four new arms all run live.
- Full sweep from an ISOLATED clone: **3482 passed / 22 skipped**, vs master
  `a1357829` measured on the same machine at **3399 / 12** ⇒ delta **+83
  passed / +10 skipped**, exactly this unit's contribution. Zero failures.
- `cog2-import-gate.py` exit 0; layer-sep exit 0 with **new=0** (identical
  counts on master and fix — the assembled path tokens do not trip instance
  coupling); census exit 0 and **byte-identical to master**.
- Every pre-existing arm re-run and still non-vacuous; HEAD bytes `ast.parse`
  clean; `git diff origin/master...HEAD` touches only this unit's four files
  plus this artifact.
- Wall-clock note (not a regression): the sweep measured 350.4 s here against
  the S0 artifact's 228.4 s bound — but master measured 346.0 s on the same
  loaded machine, so the fix delta is +4.4 s (+1.3 %). The §12.1 twin that
  takes a FRESH baseline is W6/W7; the corpus deliberately does not measure
  its own p95.
