# COG-5 W2 — integration landing (T1 + T2 + T3 composed)

Date: 2026-07-25 · Branch: `feat/cog5-w2` · Base: `origin/master` @ `138a253236fd79be519a0771f59ab1aeb1e664c7`
Role: integrator (composition only — no unit rework). Model: Opus 5 (1M), the program's primary model from 2026-07-25.

## Composition

Cherry-picked in the load-bearing order — T1 first, because it OWNS
`cabinet/scripts/tests/lib_cog5_corpus.py`, the cross-unit core T2 and T3
import guardedly and were reviewed against.

| # | unit | commits taken | conflicts |
|---|---|---|---|
| 1 | T1 archive-lineage | `93fb88df` `3732e408` `b3754a93` `3df892a6` | none |
| 2 | T2 scoring-candidate | `ab8fe00a` `27197a63` `da413d4b` | none |
| 3 | T3 boundary-escape | `8a13e818` `1ec1546d` | none |

**Zero cherry-pick conflicts.** The three branches touch disjoint file sets, so
composition is a pure union; `git ls-tree` confirms `lib_cog5_corpus.py` at blob
`c298a2ae62b41cab9ada87003d033b153c5bae0e` on the composed tree — byte-identical
to what T2/T3 were reviewed against.

**Deviation from the landing brief, recorded.** The brief named T1 as
"commits `b3754a93` then `3df892a6`", T2 as `da413d4b`, T3 as `1ec1546d` — i.e.
tip commits only. Those are deltas on top of parents that are NOT on master
(merge-base `a1357829`; master has only `c9b521b9` + `138a2532` beyond it), so
cherry-picking the named commits alone would have applied edits to files that do
not exist. The full per-branch ranges were taken instead, which is also what the
brief's own "verified blob `c298a2ae` across all four T1 commits" implies.

## A. Join-skips retired (corpus surgery, §13)

The 16 skips in the composed cog5 corpus were enumerated and classified. **None
of the 16 is a unit seam** — every one names a genuinely absent future-wave
surface (`framework/evolution/{sandbox,arena,league,archive,holdout_gen,scorers,candidate,bench_factory}.py`,
`cabinet/scripts/verify-cognitive-phase5.sh`, the W6 arming record — each
verified absent on disk) or is the declared COG-4 §10.5 posture skip that is
documented to STAY. Retiring any of them would have been wrong.

The real join-skips were the three **self-arming sibling guards**. Composition
had already flipped all three to their live path, so they were not in the skip
report — but their skip/early-return branches survived as dead code that would
have silently re-opened the seam if the core were ever removed or renamed. All
three are now unconditional assertions:

| # | seam | was | now |
|---|---|---|---|
| 1 | `test_cog5_sim_scoring.py::TestCorpusCoreJoin::test_core_absence_companion` | `if FIX.CORE is not None: return` (silent pass post-join) | `test_core_is_joined_and_bound` — `assert FIX.CORE is not None` |
| 2 | `…::TestCorpusCoreJoin::test_core_join_guard` | `pytest.skip("t1 shared core … not yet joined")` | `test_core_import_binds_the_bytes_on_disk` — asserts the file exists **and** `CORE.__file__` resolves to it (a same-named module shadowed on `sys.path` now REDs) |
| 3 | `test_cog5_sim_boundary.py::TestSharedCorpusIntegration::test_provenance_vocabulary_agrees_with_t1_core` | `pytest.skip(...)` + a `break`-on-first-name loop | `assert corpus is not None`; every probed name that exists is checked, and at least one must exist |

Seam 3 also closed two silent-pass holes: the old loop bound the FIRST of
`("PROVENANCE", "LIB_COG5_CORPUS_PROVENANCE", "PROVENANCE_ENUM")` that existed
and broke, so a divergent second name was never read and a core exposing none of
the three passed vacuously. That is precisely the order-dependence T1 pins from
its own side in `test_provenance_exposed_under_every_probed_name`.

**No converted assert failed** — there is no cross-unit contradiction.

**Proven biting, not asserted.** With `lib_cog5_corpus.py` moved out of the tree,
the three converted tests → **3 failed, 0 skipped** (pre-conversion: 1 silent
pass + 2 skips). The core was restored and `git status` confirms a byte-identical
restore. Sibling corpora were not weakened or deleted anywhere (§13 / brief §E);
every change is a conversion or a strengthening.

## B. Contract X1 citation

`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` §1 cell X1 cited
`test_cog5_archive_lineage.py`; the delivered file is `test_cog5_sim_archive.py`.
Corrected.

**Whole-tree sweep, and a sweep-integrity trap paid.** A repo-root `grep -r`
silently under-reports in this environment: the interactive `grep` is a shell
function wrapping `ugrep --ignore-files`, which honours `.gitignore`, so it skips
every `shared/interfaces/**/*.md` review artifact. The sweep was redone with
`git grep` **and** `command grep -rn` (bypassing the wrapper); both agree on
exactly three occurrences: the contract cell (fixed) and two in T1's own cp2/cp3
artifacts, which are the reviewers *reporting* the discrepancy and are correct as
historical records — deliberately left.

## C. T2's two open notes, folded

1. **Stale echo** — `test_cog5_sim_scoring.py::test_the_constructor_wall_no_caller_may_name_a_derivation`
   still read "there is structurally no parameter through which a scorer could
   declare a machine derivation **for a number it did not measure**". N1 disproved
   that run-on: the evidence object is the caller's, so a machine-SHAPED
   fabrication earns machine custody with no label forgery. The comment is now
   scoped to the LABEL channel it actually walls, and points at the VALUE channel
   and at the declared residual (`test_declared_residual_self_consistent_fabricated_evidence`,
   `make_vector`'s HONEST SCOPE block).
2. **Over-determined mutant** — `mutant_judge_number_into_machine_dim` handed
   `JudgeEvidence` to BOTH machine dims, so two dims were bad at once and
   reverting the MF1 construction stamp alone was MASKED. One-line remedy, mirroring
   the discipline the sibling `mutant_fabricated_evidence_for_a_machine_dim` already
   carried: `frozen_regressions` now takes an honest `_rg.GateResult(outcome=OUTCOME_PASS)`
   whose regressed count matches its declared 0.

**Proven, both directions** (MF1 construction stamp reverted to label-derived,
value law untouched, `__pycache__` purged + `PYTHONDONTWRITEBYTECODE=1`):

- with the fix (one judge-fed machine dim) → `test_mutant_judge_derived_number_on_a_machine_floor_REDS` **FAILED** — the bite is restored;
- without it (both dims judge-fed) → the same revert **PASSED** — the reported masking reproduced exactly.

Fixtures file restored to sha `99122298e154d1508c3ffd996ed02c40af9e55a760ec7c411a3b9edc78d2e507` (pre-proof == post-proof).

## D. T1 re-review findings, all three taken

1. `test_cog5_sim_archive.py` module docstring — the store-layer claim was
   unqualified. It now carries the bound: it holds against a BARE deletion, not
   against a complete editor that also re-mints the anchor, and points at
   `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor` (E4).
2. `ReferenceArchive.append()` — heal-on-open was documented nowhere, and the
   eventual `framework/evolution/archive.py` implementer reads this model. One
   docstring block: `append` does NOT call `heal()`, so appending after an
   interrupted commit clobbers `pending.json` and leaves the store
   `ANCHOR_MISSING`; `heal()` is idempotent so calling it on every open is safe.
   Recorded as **transient** (self-heals at the next cadence point) and explicitly
   NOT the permanent bug that cp3 fixed.
3. `append_crashing_after_commit` omits the anchor, so at an on-cadence sequence
   it models a state real `_commit` cannot reach. Strictly conservative, so it
   stands; the parametrize id is now
   `crash-before-the-pending-clear-anchor-omitted` and the fixture docstring says
   why. Free: nothing outside this file references the id.

## Frozen-review digest re-bind — measured, and NOT needed

The brief assigned W2 a mandatory digest re-bind before landing. **Measured
against the tree, W2 moves no digest, so there is nothing to re-bind.** This note
is the dated administrative record of that finding.

Digest = SHA-256 over `git ls-tree -r HEAD` for each phase's EXPECTED_SCOPE.
Measured on master, on the composed branch, and after the integration edits:

| binder | master `138a2532` | `feat/cog5-w2` (landed state) | verdict |
|---|---|---|---|
| COG-0 | `63f4643a…` | `63f4643a…` | unchanged |
| COG-1 | `2fb7a390…` | `2fb7a390…` | unchanged |
| COG-2 | `98bae784…` | `98bae784…` | unchanged |
| COG-3 | `34a382fa…` | `34a382fa…` | unchanged |
| **COG-4** | `093e5866…` | `093e5866…` | **unchanged — `--verify` OK both sides** |

Why: W2 adds new files under `cabinet/scripts/tests/` and
`shared/interfaces/reviews/`, and edits only cog5 corpus files plus the phase-5
contract. **None of those paths is in any phase's EXPECTED_SCOPE**, and no scope
entry is a directory that would capture them (the DIR entries are
`framework/{projection,scheduler,organs}`, `cabinet/scripts/tests/fixtures/cog4`,
`cabinet/config/organs`). The phase-5 contract has no binder — there is no
`cognitive-phase5-review-scope.py`. No census allowance, egg-manifest or
layer-separation change was required either, so no in-scope file was touched
indirectly.

COG-4 is the live binding (`--verify` → OK). COG-0/1/2/3 are already BLOCK on
**master**, unchanged by this branch — they are the digest-frozen historical
instances their own docstrings describe, and this landing neither improves nor
worsens them.

The branch that DOES move it is the parked one: `fix/import-gate-dynamic-forms`
@ `a57cc78d` edits `cabinet/scripts/cog2-import-gate.py`, which sits in the
COG-2, COG-3 **and** COG-4 scopes, taking COG-4 to `d8d316b2…` (BLOCK). It was
left entirely alone per the brief and rebases + re-binds after this lands.

## Verification (this tree, `python3.12`, serial, `__pycache__` purged + `PYTHONDONTWRITEBYTECODE=1`)

Baseline **re-measured on `origin/master` @ `138a2532`** in an isolated worktree
(the brief's cited 3399/12 is stale — master gained 2 tests in `c9b521b9`):

| battery | master baseline | composed + integrated | delta |
|---|---|---|---|
| `cabinet/scripts/tests` | 3401 passed / 12 skipped / 0 failed | **3700 passed / 28 skipped / 0 failed** | +299 / +16 |
| cog5 subset (`-k cog5`) | — | **366 passed / 16 skipped / 0 failed** | — |
| `framework/` | 6433 / 25 / **1 failed** | 6433 / 25 / **1 failed** | 0 |
| `cabinet/scripts/task_adapters/tests` | — | 38 passed | — |
| `cabinet/scripts/world-aesthetic/tests` | — | 87 passed / 5 skipped | — |

The single `framework/` failure is `framework/fidelity/tests/test_retro_shim.py::TestRetroShim::test_reexports_constants`
— the known pre-existing red on any machine carrying the out-of-repo
retrodiction library (it asserts `claude-sonnet-4-6`; the library moved to
`claude-sonnet-5` on 2026-07-22). Present identically on the re-measured master
baseline, invisible to CI, tracked separately, not this wave's.

Gates:

- `python3.12 cabinet/scripts/cog2-import-gate.py` → **rc=0** (shadow boundary intact)
- `bash cabinet/scripts/check-layer-separation.sh` → **new=0** (baseline 24, allowlist 19, current 43)
- `python3.12 cabinet/scripts/cognitive-architecture-census.py` → **rc=0**, observed == max on every row (zero headroom preserved; no allowance change needed)
- `bash cabinet/scripts/run-golden-evals.sh` → **29 pass / 0 fail / 0 skip**

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 W2 integration landing).
