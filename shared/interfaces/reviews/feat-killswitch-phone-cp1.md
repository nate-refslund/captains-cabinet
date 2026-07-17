# Checkpoint review — feat-killswitch-phone (integration, cp1)

Date: 2026-07-17
Scope: integration of two independently built + adversarially reviewed lanes
(captain-controls Phase 1: kill-switch from the phone) onto master.
Base: origin/master `2e04642e` (same tip both lane reviews verified against;
master did not move between review and integration).
Merges: `a389d99a` (card lane), `a454eb64` (watchdog lane). File-disjoint —
zero overlapping paths between the lanes (verified via `git diff --name-only`
+ `comm -12` before merging).

## Lane 1 — feat-killswitch-card @ 448d8943 (verdict: SHIP)

/killswitch Telegram control card + tap wire (comms surface + officer
inbound poller). Reviewed with ZERO P0/P1 findings; no fix round required —
builder and reviewer verified the same commit. Three non-blocking
observations, all explicitly deferred by the review's own terms:
1. EVAL-001 doc enumeration lives in a germline-locked file — requires a
   CG-tracked amendment (queued for when the watchdog-lane CG row lands);
   touching the germline file from an integration lane is forbidden doctrine.
2. `emit_flip_event` fragility — watchdog-lane design note on pre-existing
   zero-diff code, not this lane's surface.
3. Corridor plan-analysis MCP unavailable in the build environment —
   process note only (unavailable for builder, reviewer, and integrator).

Lane re-verification at 448d8943: lane suites 52 passed; docs sweep
13 passed; layer-sep no new violations; poller + kill-switch-events
regressions 78 passed; merge-tree clean against 2e04642e.

## Lane 2 — feat/killswitch-watchdog @ 90c63238 (verdict: SHIP-WITH-FIXES, fixes applied)

Kill-switch watchdog service (re-arm the E-stop on unattributed clears),
base commit 4afd3398 + review-fix commit 90c63238 (3 files, +125/-20).
Findings 1–5 applied in the fix round:
1. MEDIUM — manifest-row test rewritten to the W10 conditional convention
   (YAML-loaded; `disabled` only with non-empty `disabled_reason`), so the
   enable ceremony no longer turns CI red; label/kind/command/interval pins
   kept exact.
2. MEDIUM-LOW — plan doc `captain-controls-no-terminal-2026-07-17.md`
   as-built amendment recording the provenance-keyed verdict rule (literal
   newest-row rule was unsafe), cited per 2026-07-07 full-autonomy grant.
3. LOW — new test: unreachable redis is a loud failsafe noop
   (`noop-unobservable-redis`, rc 0, WARN, no state write).
4. LOW — new test: dry-run never re-arms even past grace (no SET, no audit
   row, no notify, no state write).
5. LOW — `rearm()` TimeoutExpired routed to the existing FATAL path
   (`rearm_rc: "timeout"`, rc 1, anomaly kept for retry) + docstring
   invariant updated + pinning unit test.
Finding 6 residuals: left per the review's explicit no-action scope.
Mutation verification: both re-introduced mutants caught by the new tests
(1 failed each), mutants restored, zero `CalledProcessError` residue.

Lane verification at 90c63238: watchdog suite 18 passed; neighbors
81 passed; generate-plists rc=0 (row manifest-parked, not rendered);
layer-sep no new violations.

## Integration verification (this worktree, python3.12, post-merge tree)

- Pre-existing-failure baseline: at pristine origin/master 2e04642e
  (pre-merge), `test_evidence_seam_bypass_replay.py::
  test_shipped_catalog_harness_still_green[evidence-access.sh]` FAILS
  (1 failed, 23 passed) — reproduced independently by builder, reviewer,
  and integrator on pristine master. NOT introduced or touched by either
  lane.
- Full `cabinet/scripts/tests -q`: `1 failed, 1443 passed, 5 skipped in
  225.92s` — the single failure is exactly the pre-existing baseline test;
  zero delta from the merges.
- `framework/comms` tests: `195 passed in 0.95s`.
- Golden evals (`run-golden-evals.sh`, sandboxed redis): `Total: 27 |
  Pass: 27 | Fail: 0 | Skip: 0` — ALL PASSED.
- Layer separation: `baseline=24 allowlist=18 current=42 new=0 fixed=0` —
  OK, no new violations.
- Docs sweep: `DOCS_SWEEP GREEN (files=45 findings=0)`.

Integrator verdict: both lanes land as reviewed; no unreviewed source
changes introduced by integration (merges only, plus this artifact).
