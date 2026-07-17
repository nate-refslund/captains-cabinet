# Checkpoint review — feat/evidence-phase2-batch-b cp1 (integration)

**Date:** 2026-07-17 · **Reviewer:** evidence Phase-2 Batch-B integrator
(Fable 5) · **Scope:** the composed four-group batch off `3fcb340c`
(27 files) — groups `action-lane`, `learning-gate`, `watchdog-session`,
`authority-verbs`, each adversarially reviewed per-group before
integration; this checkpoint reviews the COMPOSITION.

## What this checkpoint lands

The design-of-record's §3 Phase 2 items 2+3 (+ §7 R-1): act-class
producers with evidence-before-action FAIL-CLOSED semantics on the action
lane (`action_exec.py`/`run_action_lane.py` + reconciler outcome labels)
and the learning/gate machinery (`gate.py`/`apply_watch.py`); receipt-class
telemetry for watchdog/doctor verdicts, officer-session lifecycle
transitions, and the R-1 authority/control-plane (posture caps,
`need_approved`, `kind_frozen`, germline/kill-switch window observations,
structured `veto-scope:` consequence refs) riding the Batch A mirror.
Both new sweep services ship `disabled: true` (enable = deploy step).
Germline surface: 8 schg files, ceremony-gated via
`docs/proposals/germline-amendment-evidence-phase2b-2026-07-17.md`
(exact union + same-day unlock→checkout→relock block; no boundary
extension — lock-set definition files byte-identical).

## Integration decisions (beyond the four reviewed patches)

1. **Merge conflicts** (expected): `framework/events/emitter.py`
   `VALID_EVENT_TYPES` + `_AGGREGATE_MAP` — resolved keep-all
   (watchdog/session classes + authority classes + `kind_frozen` +
   `need_approved`), deduped (0 duplicate literals; mirror allow-list ⊂
   emitter vocabulary verified). `framework/evidence_mirror.py`
   `MIRRORED_ORG_EVENT_TYPES` auto-merged clean (adjacent regions);
   grouped comment organization kept.
2. **Seam reconciliation — one recording path per event class,
   repo-wide:** every new receipt class has exactly ONE emit site
   (`watchdog_outcome_failed`+`doctor_verdict`+`officer_restarted`+
   `officer_limit_wake` → `framework/watchdog/receipts.py` lens;
   `officer_session_*` → lifecycle sweep only — it deliberately does NOT
   re-emit restart/wake verbs; posture caps → `binder_wire.py`;
   `posture_changed`/`germline_*` → authority sweep; `need_approved` →
   `needs.py`; `kind_frozen` → `action_undo.py`). Act-class surfaces
   record via `ActLifecycle` trials only — none of their org event types
   (`eval_run_started`/`eval_passed`/`eval_failed`, `action_*`) are
   mirror-listed, so no class records twice (R-13 division honored).
3. **Authority sweep self-check added** (integration edit): the
   `emit-officer-lifecycle-transitions.py` LOUD-never-blocking mirror
   allow-list self-check idiom replicated into
   `emit-authority-transitions.py` (`SWEEP_EVENT_TYPES`); the A2
   reconciler's `authority-control-plane` surface now names its live
   producer instead of reporting a false gap.
4. **Coverage pin updated to the composed truth** — no single group could
   flip it: `test_evidence_coverage.py::test_real_repo_json_shape_stable`
   now pins the five Batch B surfaces WIRED with exact producer lists AND
   the four remaining honest gaps.
5. **Layer-separation root-cause fixes** (5 new `FRAMEWORK_PATH_INSTANCE`
   flags removed, no baseline/allowlist growth): the three producers that
   re-typed the store layout (`gate.py`, `apply_watch.py`,
   `action_reconcile.py`) now lazily import the ONE canonical
   `journey.EVIDENCE_REL` (the `evidence_mirror._production_store_root`
   idiom — also kills constant-drift risk); the two new test files derive
   scratch layouts from `journey.EVIDENCE_REL` / `posture.posture_path()`
   / `posture.narrow_cap_path()` instead of literals. Known pre-existing
   wart (NOT this batch): `action_exec.py` still carries its own tuple
   under its Captain-ratified allowlist entry — cleanup candidate for a
   future ceremony, left untouched to keep this diff minimal.
6. **CRIT-5 pin false-positive avoided:** a comment in `action_undo.py`
   (`unfreeze()'s`) matched the structural pin's call-shaped regex; the
   comment was reworded — the pin itself is untouched and green (37
   passed).

## Contract proof (the review's second question)

- **Happy-path stability:** BASE (worktree @3fcb340c) framework suite
  5408 passed/24 skipped; composed 5546 passed/24 skipped — +138 (exactly
  the four groups' new tests), 0 removed. cabinet/scripts/tests BASE 1392
  passed/4 skipped → composed 1392 passed/4 skipped. BASE-vs-composed
  happy-path probe (authority verbs, normalized artifacts): domain
  outputs byte-identical; deltas = designed additive receipt classes +
  mirror correlation stamps + reviewed `veto-scope:` refs only.
- **Fail-closed / degrade-loud fires ONLY under injected failure:** group
  suites cover the act arms (typed refusals via store-parent-as-file
  injection; `test_gate_evidence.py` `_break_store`, action-lane fence
  tests); composed-tree standalone injection verified the receipt chain:
  domain write lands + stderr WARN + `evidence_mirror_degraded` org event
  + marker row. Fault-probe note: `probe_smoke_and_faults.py` fault C
  (chmod-500 store) FAILS on BASE and composed identically — the recorder
  normalizes store perms at construction (`recorder.py` chmod 0o700), so
  that injection technique is void, not the contract; the sanctioned
  injection shape passes.
- **Determinism:** evidence suite 126 green (v1+v1.1 verify); onboarding
  195+1s; `test_act_bytestream.py` 2 green; dogfood harness ok=true
  (15 scenarios, checksums_ok, post-purge store ok, source unchanged).

## Gate battery (composed tree)

| gate | result |
|---|---|
| `python3.12 -m pytest framework -q` | 5546 passed, 24 skipped |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 1392 passed, 4 skipped |
| lockstep consistency | 371 passed |
| `check-layer-separation.sh` | OK — new=0 |
| `run-golden-evals.sh` (incl. EVAL-025) | 27/27 PASS |
| `docs-track-code-sweep.sh` | GREEN (findings=0) |
| dashboard `tsc --noEmit` | exit 0 |
| A2 coverage line | `evidence covers 9 of 13 action-taking surfaces; named gaps: attention-hygiene, probes-verification, roles-missions-lifecycle, ops-consequence-scripts` |

## Invariants re-checked at composition

Lock set byte-identical (`germline-lock.sh`, `immutable-core.yml`,
hooks dir — `git diff` empty); `evidence-read.sh` untouched; no generic
emit CLI/API; new detail keys registered in `classification.py` and
redaction-covered before hashing; no env var fuel-bearing (pytest fences
only); trigger/heartbeat/delivery exhaust never recorded
(`NEVER_MIRRORED_EXHAUST` disjointness test green); never-a-score
(EVAL-025) green; both sweep services `disabled: true`; observe-only
soak-safe (append-only observation, D8).
