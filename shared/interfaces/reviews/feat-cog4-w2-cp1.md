# FW-019 checkpoint — feat/cog4-w2 (COG-4 W2 landing integration, 2026-07-23)

One PR lands the three reviewed W2 corpus units off `origin/master` `cee6741e`
(tip unmoved between unit builds and landing — verified by ls-remote at
integration start). Integrator: fresh-context Fable 5 session, scratch FULL
clone (never the live tree). Per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan grant. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md`.

## Units landed (review chains)

| unit | branch@sha | verdict chain | content |
|------|-----------|---------------|---------|
| t1 | feat/cog4-w2-t1 @0fa9c4bf (2 commits: e6850282 build + 0fa9c4bf fix) | FIX_FIRST(2) → fix → SHIP | scheduler-fold corpus: `lib_cog4_corpus.py` (T1-OWNED shared core; T2/T3 import, never create) + `test_cog4_sim_fold.py` + 6 self-consistent wake-snapshot fixture JSONs + cp artifact. The fix round closed BOTH reviewer escapes with a biting mutant each: (1) duplicate-decision rowset identity — the exactly-one-row law; (2) ceiling-vs-declared-cost binding. |
| t2 | feat/cog4-w2-t2 @8ad0fb0b | SHIP first-pass | dispatch/integrity corpus: `test_cog4_sim_dispatch.py` (§7.3 charter-quadruple order battery + 14 dispatch-side named-escape mutants) + `test_cog4_organ_runner.py` (§9.5 runner-invariance + 3 runner mutants) + cp artifact. Imports `lib_cog4_corpus` from t1. |
| t3 | feat/cog4-w2-t3 @55723a92 | SHIP first-pass | gate batteries: `test_cog4_measurement.py` (N6) + `test_cog4_parity.py` (N9) + `test_cog4_floor_conservation.py` (§9.2) + `test_cog4_organ_manifest.py` (§4.3/§5.2/§5.5) + `lib_cog4_floors.py` (floor-conservation reference checker) + cp artifact. |

Landing shape: `feat/cog4-w2` = master + 4 cherry-picks in dependency order
(e6850282 → 0fa9c4bf → 8ad0fb0b → 55723a92) → this cp commit. ALL FOUR
cherry-picks applied CLEAN — zero conflicts, zero joins, zero deviations
(the expected outcome: disjoint new-file sets; the only file modifications
in the wave are t1's fix commit editing t1's own two new files).

## Corpus-law compliance (§13)

`git diff master..HEAD --name-status` (pre-cp-commit) = **18 rows, ALL `A`**
— purely additive, ZERO existing files touched: 9 test/lib files, 6 fixture
JSONs, 3 per-unit FW-019 artifacts. All three per-unit cp artifacts carried
through the cherry-picks into the integrated tree (verified present). No
shared pinned constant duplicated: cross-unit constants live in the T1-owned
lib; t2/t3 import them.

## Live-vs-skipped accounting (exact, integrated tree)

| battery | live (passed) | vacuity-armed (skipped) |
|---------|--------------|-------------------------|
| t1 `test_cog4_sim_fold.py` | 42 | 9 |
| t2 dispatch + organ_runner | 61 | 12 (10 dispatch-shadow CLI arms + 2 organ-runner arms) |
| t3 measurement + parity + floor_conservation + organ_manifest | 83 | 7 |
| **W2 total** | **186** | **28** |

Every skip is a vacuity-armed real-surface arm in the W1-u2 mergeability
idiom: companion ABSENCE assertion that REDs the instant the target
surface/CLI lands + a named retirement condition (the one-line activation
binding the arm to the real surface). Fixture/reference machinery runs LIVE
— mutant bites proven at their NAMED escapes outside `pytest.raises`
(17 t2 mutants, 8 t1 §12 negative controls + the 2 fix-round mutants, t3
single-member divergence per tuple member).

## Full verification on the integrated branch

- Full `test_cog4_*` battery: **380 passed, 35 skipped, 0 failed** — exact
  reconciliation: W2 units 186/28 + W1-landed guards 194/7 (boundary rows 80
  + fleet-truth/AST-pin suite 114/7, both unchanged from the W1 freeze).
- Full `cabinet/scripts/tests` sweep: **3010 passed, 45 skipped, 0 failed**
  (5:21) — exact vs the 2824/17/0 master baseline: +186 passed +28 skipped,
  precisely the wave's additions. ZERO unexplained failures.
- `cog2-import-gate.py`: exit 0 (shadow boundary intact).
- Layer-sep: OK — new=0 (baseline 24, allowlist 19, unchanged).
- Census `--check`: exit 0, every budget observed == max (zero-headroom
  posture unchanged; no production modules/lines added — the wave is
  tests-only).
- `test_egg_export.py`: **58 passed, 1 skipped** standalone (green in the
  sweep too). NO manifest lines needed — precision note: tests under
  `cabinet/scripts/tests/` DO ship in the egg by default (the manifest
  deletes only specific instance-coupled tests); the W1 cog4 test files
  shipped with zero manifest lines (precedent), the W2 files reference only
  in-tree fixtures/libs that ship alongside, and the vacuity arms skip
  identically in the egg (target organs absent there too — green-by-vacuity
  is egg-safe by construction).
- HEAD-bytes parse: all 6 committed fixture JSONs load clean from
  `git show HEAD:` bytes.

## Landing-time addendum (2026-07-23, post-first-CI)

PR CI round 1: gitleaks RED — one finding, `generic-api-key` on t3's
fixture idempotency value at `test_cog4_organ_manifest.py:495` (the
garden-rota key with a `-2026-07-23` date suffix appended; entropy 3.607 ≥
the rule's 3.5 threshold; provably-synthetic garden-rota vocabulary, not a
credential — the string is deliberately not quoted verbatim here, a first
addendum draft that did quote it re-tripped the same rule on itself). Fix,
two coordinated parts:

1. **Root cause at HEAD:** value → `"garden-rota"` (entropy 3.096, below
   threshold; semantics identical — the field's only constraint is
   non-empty string; single occurrence repo-wide). Keeps the squash-merge
   commit, the egg, and all future tree scans clean by construction.
2. **Immutable introducing commit:** the t3 cherry-pick `3b1c75bc` is
   already pushed and range scans (CI scans the PR commit range) still see
   its diff; the branch is never force-rewritten (multi-writer push
   protocol). Per `.gitleaksignore`'s own documented convention for exactly
   this shape (the PR #139 precedent: fixed at HEAD, introducing commit
   fingerprinted as a provably-fake fixture), one sha-pinned fingerprint
   line is added for `3b1c75bc:…test_cog4_organ_manifest.py:generic-api-key:495`.
   A `.gitleaks.toml` path allowlist was REJECTED (would permanently exempt
   all cog4 test files from scanning).

Wave-shape note: the fingerprint line touches one PRE-EXISTING governance
file (`.gitleaksignore`, +1 line under its documented add-only convention).
Corpus law §13 (no existing TEST/LIB files edited, no pinned-constant
duplication) still holds untouched; the 18 corpus rows remain all-`A`.
Post-fix: organ-manifest suite 43/2, full cog4 battery 380/35/0 unchanged;
local gitleaks reproduction over the CI's exact commit range = 0 leaks
(evidence in the fix commit).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
