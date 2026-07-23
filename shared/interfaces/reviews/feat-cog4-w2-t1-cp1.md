# Checkpoint review — feat/cog4-w2-t1, cp1 (W2 T1 scheduler-fold corpus)

**Scope:** the COG-4 W2 T1 corpus unit (contract
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §12 sims
1/2/4/7/8/13 + N1 + N2 + the §7.1 A-M6 purity mutants), off origin/master
`cee6741e`. Purely ADDITIVE new files (~2.4k lines → FW-019 artifact at
commit time; this is it):

* `cabinet/scripts/tests/lib_cog4_corpus.py` — the W2 corpus CORE (T1-owned;
  T2/T3 import, never create): the corpus-pinned wake-snapshot schema
  (`cog4-wake-snapshot/v1`, §7.1/§2.1 incl. all four SF2 families declared +
  hashed), the corpus-pinned schedule artifacts + rows-hash algebra (§7.2 +
  §6.3 mandatory `schedule_rows_hash`), the reference fold simulator, the
  eight §12 negative-control mutants, subprocess runners (C-F3
  PYTHONHASHSEED children), and the runner-parameterized sim assert
  batteries the real surface retires onto (`run_real_arm`).
* `cabinet/scripts/tests/test_cog4_sim_fold.py` — the T1 suite: fixture
  self-consistency (+ tamper negative), all nine arm batteries LIVE on the
  reference fold, every mutant bite proven live, the N1 instrument's
  three-artifact coverage proven, the armed-probe machinery proven both
  directions on a scratch tree, and 9 vacuity-guarded real-surface arms
  (companion absence assertion + armed ModuleNotFound proof + retirement
  condition — the W1-u2 mergeability idiom).
* `cabinet/scripts/tests/fixtures/cog4/fold/*.json` — six authored,
  SELF-CONSISTENT wake-snapshot seeds (burst, quiet, cost-spike, starvation,
  contradiction, self-prioritization); SF2 family hashes recompute from the
  fixture's own data (tamper REDs).

## Review basis (self-review checklist; a fresh reviewer re-runs everything)

1. **Corpus law (§13) held:** zero existing test/lib files edited —
   `git status` shows only the three additive paths. No shared pinned
   constant duplicated: the scheduler tree path is imported from the
   W1-landed `lib_cog4_ast_pins`; cross-unit constants (artifact names,
   rows-hash key, snapshot schema) live in the T1-owned lib.
2. **Mergeability (the W1-u2 idiom):** suite runs GREEN on the bare tree —
   40 live passes + exactly 9 vacuity skips (one per real arm). Every skip
   carries a retirement condition naming the one-line activation
   (`run_real_arm(<arm>, tmp_path, repo=_REPO)`) and a COMPANION
   `assert not (framework/scheduler).exists()` that REDs at landing; the
   import probe's two-way discrimination is itself proven live on a scratch
   tree, so the guard cannot rot into a tautology.
3. **Every §12-named mutant bites NOW (proven this run, not deferred):**
   dict-order tie-break → `[N1-TRIPLE]`; idle-spin → `[SIM2-EMPTY]`;
   cost-ignoring → `[SIM4-CEILING]`; starvation-prone → `[SIM7-BOUND]`;
   LWW/auto-resolve → `[SIM8-BOTH]`; self-weight-update → all three named
   escapes on three narrow checks (`[SIM13-CACHE-ONLY]`,
   `[SIM13-POLICY-ECHO]`, `[SIM13-NO-SELF-WEIGHT]`); env-reading →
   `[PURITY-ENV]`; datetime.now → `[PURITY-CLOCK]`.
4. **N1/N2 at contract strength:** N1 = identical combined hash across 3
   subprocess rebuilds under 3 distinct PYTHONHASHSEED values from the SAME
   snapshot + delete→rebuild reproduction + proven coverage of all three
   artifacts (remove-any → RED; tamper-any → hash change). N2 = chosen
   within the DECLARED bound, with the bound proven a snapshot INPUT
   (organ-declared 3 / 5 and scheduler_policy default 4 move the choice wake
   exactly; wait state re-declared + re-hashed per wake).
5. **Gates green on this tree:** cog2-import-gate exit 0 (new files join the
   sweep; no cortex/objectives token anywhere in them); W1 guard set + gate
   suites 310 passed / 7 skipped; census 29 passed (tests budget-exempt —
   framework budgets untouched at observed==max); layer-sep 0 new;
   egg-export 58 passed.
6. **Known asymmetry (deliberate, integrator-visible):** the corpus pins the
   decision-record shape (every eligible op gets exactly one select|defer
   row; defer reasons named; conflicts defer BOTH sides) — the corpus is the
   executable spec for W3; a W3 disagreement routes to the integrator, never
   a test edit.

Provenance: authored + self-ratified per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant (W2 T1, Fable 5).
