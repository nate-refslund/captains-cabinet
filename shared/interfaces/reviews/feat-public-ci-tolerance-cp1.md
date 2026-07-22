# Checkpoint review — feat/public-ci-tolerance (cp1)

**Branch:** feat/public-ci-tolerance off origin/master @e3f92100
**Batch:** 40 files, +639/−120 (six pre-built lane diffs A–F, integrated conflict-free).
**Reviewer context:** orchestrator convergence (candor law; two-tier routing —
Opus execution built the lanes, Fable judgment reviews teeth post-integration).

## Problem
The scrubbed public "egg" export tree runs the SAME test/gate suites as the
source-instance tree, but the export deliberately strips instance artifacts
(platform.yml, concrete launchd plists, egg-export-manifest.txt, populated
captain-rules / world-binding indexes, the retro pipe). ~33 cabinet/scripts
tests + a handful of framework tests + two evals therefore go RED on the public
tree — with **zero real framework bugs**. The new relaunch repo's own CI is red
for exactly this reason, which blocks the Captain review checkpoint.

## Fix pattern — artifact-anchored tolerance
Each affected test detects whether the **source-instance artifact it consumes**
is present:
- **Present** (source tree) → the test runs FULL and must pass with **no skip
  firing** (teeth intact).
- **Absent** (public export tree, artifact scrubbed) → the test skips-loud or
  falls back to a shipped preset/template twin.

Detection is by **artifact presence** (`git ls-files` / `os.path.exists` /
row-count of the consumed surface / an `ARCHIVED-NOTE.md` export marker) — never
by a bare environment flag. Where an env license is used (A3
`CABINET_WORLD_DATA_OPTIONAL`) it is **double-keyed**: the skip additionally
requires the counted surface to genuinely be 0-row AND a stripped-instance path,
so on the populated source tree it cannot skip even with the flag set.

## Lanes
- **A** (harness/validator tolerance): never-a-score `harness.py` archive-aware
  staleness (`_archived_dormant` keys on `ARCHIVED-NOTE.md`; source without the
  marker keeps full staleness teeth); `world-binding-validator.py` 0-row
  data-optional tolerance (double-keyed as above); + public-ci items,
  ledger-status-parity, captain-rules eval.
- **B** (docs-track-code sweep): runbook + skill + README doc updates so
  docs-track-code-sweep.sh stays green after the code moves; docs-sweep-allowlist.
- **C** (`actfirst_canary.py`): import-time `_DEFAULT_BOARD = env.tasks_board()`
  → call-time resolution. `env.tasks_board()` returning '' and fail-closing is
  the intended behavior; the import-time capture was the only bug.
- **E** (env-resolution): small helper resolution fix.
- **F** (`fidelity/retro.py`): `_RetroUnavailable.__getattr__` + the PEP 562
  module `__getattr__` no longer proxy dunder names (raise AttributeError on
  `__x__`); conftest resolves the retro pipe via `framework.env.retro_pipe_dir()`
  instead of a hardcoded `~/.screenpipe`.
- **D** (cabinet/scripts/tests, 11 files, D1–D8): skipif-absent on egg-stripped
  manifest/gate readers (D1); `live_roster()` documented `{cos,cto,cpo,coo,cro}`
  fallback when platform.yml absent (D2); `_default.yml` context that survives
  the egg (D3); shipped `presets/portfolio/agents/cos.md` fallback (D4); skipif
  on the concrete fidelity-f1 plist the portable egg ships only as a template
  (D5); `docs/templates/CLAUDE-egg.md`→shipped `CLAUDE.md` fallback (D6); D7 = no
  test change (A4's harness fix covers the egg-only EVAL-025 path); world
  validator gate bound to a hermetic populated captain-rules index + a 0-row SKIP
  pin (D8).

## Cross-lane dependency (verified satisfied)
D7 defers to A4; D8's zero-row pin arms only when A3 is present. Both A3
(`world-binding-validator.py`) and A4 (`never-a-score/harness.py`) are in this
integrated batch (confirmed by grep on the applied tree), so D7/D8 arm and run
full on the source tree rather than self-skipping.

## Teeth invariant (the thing that must not regress)
On the SOURCE tree every tolerance must be dormant: full teeth, no skip beyond
the two documented baseline skips (test_library_retirement_ratchet.py "ceremony
landed"; framework/ retro/redis baseline). A tolerance that skips on the source
tree would pass-by-skipping and hide weakened teeth — CI green alone cannot catch
this, which is why a Fable adversarial teeth-review gates the merge in addition
to per-job CI.

## Battery
Hermetic local suites (framework/, cabinet/scripts/tests, task_adapters,
world-aesthetic, docs-track-code-sweep, ledger-status-parity,
check-layer-separation, captain-rules eval) run pre-push; the redis/pg/node-bound
golden-evals + dashboard steps are proven by PR CI on GitHub (the authority).

### Battery result (local hermetic, python3.12, 2026-07-22)
- **framework/**: 6433 passed, 26 skipped (retro/redis baseline). GREEN.
- **cabinet/scripts/tests**: 1924 passed, 5 baseline skips, **1 "failure" =
  `test_cognitive_phase1_rollback.py::test_manifest_covers_committed_cog1_footprint`
  — a full-clone-only artifact**: it fails on a pristine e3f92100 full clone too
  (pre-existing `.mcp.json` drift from a prior wave, not this change) and is
  **skipped on CI** (the framework-tests job checks out shallow → BASELINE_SHA
  absent → the test's own guard skips it; verified the only `fetch-depth: 0` job
  is `gitleaks`, which runs no pytest). Not a regression, not a CI blocker.
- **task_adapters/tests**: 38 passed. **world-aesthetic/tests**: 87 passed, 5
  skipped. **docs-track-code-sweep / ledger-status-parity /
  check-layer-separation / captain-rules eval**: all PASS.

### Two integration reconciliations (parallel lanes; found + fixed at convergence)
1. **COG-0 census budget**: the integrated framework production fixes add +7
   non-comment lines (retro dunder guard + actfirst_canary call-time), tripping
   `framework_production_noncomment_lines` (62297 vs pinned 62290). Recorded as a
   named `temporary_allowances` phase `relaunch-ci-tolerance` (+7, measured),
   matching the existing `relaunch-killswitch` (+25) precedent — the ratchet's
   designed mechanism, not a threshold nudge. Census now ok:True, 62297==62297.
2. **A3↔D8 contract**: A3's 0-row SKIP is triple-keyed (flag + 0 rows + an
   egg-export "per R116" emptied marker over a SLASHED repo-relative path — a
   marker-less/framework 0-row surface still FAILs = teeth against rot).
   Verified `egg-export.sh:176` stamps exactly that marker on the emptied
   captain-rules index, so **A3 correctly skips it on the real public tree**.
   D8's fixture used a bare, marker-less filename so it could never arm and
   always self-skipped; fixed the fixture (subdir path + marker) so D8 now ARMS
   and actually exercises A3 on both trees (27 passed, 0 skipped).

### Teeth invariant — HELD
No tolerance skip fires on the source tree beyond the documented baseline
(retro/redis in framework/; the CI-skipped rollback artifact). D8 now runs full
on the source tree and asserts the SKIP-vs-FAIL boundary; A3 keeps a hard FAIL
for any marker-less 0-row surface. Redis/pg/node-bound golden-evals, dashboard,
MCP, clean-room, gitleaks, zizmor, null-hatch → proven by PR CI (the authority).
