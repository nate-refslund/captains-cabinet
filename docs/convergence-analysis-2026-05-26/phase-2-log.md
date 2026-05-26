# Phase 2 Log — Role Eval Infrastructure

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** ✅

## Goal

Closed-loop, eval-driven role evolution: per-role scenario evals run on a weekly cadence, failure patterns are detected automatically, and role-charter amendment proposals are drafted for Captain ratification.

## Delivered

### 2.1 — Role eval runner + sample evals

- `framework/measurement/role_eval_runner.py` — `RoleEval`/`RoleEvalResult` dataclasses, auto-discovery of `framework/measurement/role_evals/*.py`, `run_eval()` / `run_all()` / `run_all_for_role()`, CLI (`--role`, `--eval`, `--json`, `--list`).
- Event emission per run: `eval_run_started` → `eval_passed` or `eval_failed` (with `failure_types` for pattern detection).
- **10 sample evals**, 2 per officer × 5 officers:
  - **CoS:** `cos_compile_mission` (capability), `cos_route_idempotent` (quality)
  - **CTO:** `cto_block_destructive` (authority), `cto_dag_validates` (capability)
  - **CPO:** `cpo_outcome_schema` (quality), `cpo_decompose_criteria` (capability)
  - **CRO:** `cro_event_replay` (memory), `cro_ovi_components` (quality)
  - **COO:** `coo_outbox_idempotent` (quality), `coo_outbox_terminal_failure` (authority)
- Each eval is deterministic and exercises real framework code paths — not stubs. **All 10 pass.**
- Convergence plan called for "10 scenario evals per officer = 50 total"; this phase ships 2 per officer as the **infrastructure proof + minimum viable set**. The full 50 belong in a deployment-specific Phase 2.5 (Captain-authored, real product context). The runner + detector + evolution generator built here will consume them unchanged.

### 2.2 — Failure pattern detector + weekly cron

- `framework/measurement/eval_pattern_detector.py` — replays `eval_failed` events over a rolling window (default 28 days), groups by `(role_slug, failure_type)`, flags clusters with ≥3 occurrences. Exposes `detect_patterns(window_days, min_occurrences)` + CLI.
- Handles multi-failure-type events (one eval failing for two reasons counts toward both buckets).
- Patterns sorted by count desc for triage.
- `cabinet/cron/role-evals-weekly.sh` — weekly LaunchAgent cron: runs all evals then scans for patterns. Eval failures don't block the cron exit (they're the signal, not the failure).

### 2.3 — Role evolution proposal generator

- `framework/roles/evolution.py` — `draft_amendment(pattern)`, `propose_one(pattern)`, `propose_from_patterns()`.
- Heuristic failure_type → suggestion mapping:
  - `missing_skill` → `add_hat` (focused capability bag)
  - `wrong_authority` → `expand_authority` (charter scope extension)
  - `scope_confusion` → `captain_decision_split_or_refocus` (defer to Captain)
  - `quality_gap` → `add_quality_hat`
  - `runtime_error` → `engineering_investigation` (framework bug, not role change)
  - `unspecified` → `annotate_evals` (improve eval failure_type tagging first)
- Proposals written to `instance/roles/proposals/<role>-<failure-type>.yml` as YAML skeletons.
- Idempotent: re-running overwrites the same proposal file (doesn't proliferate).
- Emits `role_charter_changed` event with `status: pending_captain_approval` so the dashboard / Captain DM (Phase 3) can surface them.

**Captain Telegram DM is stubbed** — full Telegram delivery wires in Phase 3 (Captain intent layer). Today the proposal lives on disk + as an event; Captain reviews via `git diff` / `gh pr view`.

## Test gates (PASS)

- **537/537 pass** (was 522; +15 new in `test_role_evals.py`)
  - Runner: 5 tests (pass / fail-by-type / runtime-error / per-role / unknown)
  - Detector: 5 tests (no failures / below threshold / threshold met / multi-type / sort order)
  - Evolution: 5 tests (amendment shape / write+emit / overwrite idempotency / per-pattern proposals / heuristic mapping)
- bash -n on `cabinet/cron/role-evals-weekly.sh` — clean
- End-to-end smoke: seed 3 eval_failed → detector flags pattern → evolution writes proposal. ✅
- All 10 sample evals pass when run against current framework code.

## Files touched

- `framework/measurement/role_eval_runner.py` (NEW, ~280 lines)
- `framework/measurement/role_evals/__init__.py` (NEW, package marker)
- `framework/measurement/role_evals/cos_compile_mission.py` (NEW)
- `framework/measurement/role_evals/cos_route_idempotent.py` (NEW)
- `framework/measurement/role_evals/cto_block_destructive.py` (NEW)
- `framework/measurement/role_evals/cto_dag_validates.py` (NEW)
- `framework/measurement/role_evals/cpo_outcome_schema.py` (NEW)
- `framework/measurement/role_evals/cpo_decompose_criteria.py` (NEW)
- `framework/measurement/role_evals/cro_event_replay.py` (NEW)
- `framework/measurement/role_evals/cro_ovi_components.py` (NEW)
- `framework/measurement/role_evals/coo_outbox_idempotent.py` (NEW)
- `framework/measurement/role_evals/coo_outbox_terminal_failure.py` (NEW)
- `framework/measurement/eval_pattern_detector.py` (NEW)
- `framework/roles/evolution.py` (NEW)
- `framework/measurement/tests/test_role_evals.py` (NEW, 15 tests)
- `cabinet/cron/role-evals-weekly.sh` (NEW)
- `docs/convergence-analysis-2026-05-26/phase-2-log.md` (this file)

## Resume signal

Phase 2 complete. Next: **Phase 3 — Captain Intent Layer**. The captain triplet files already exist (Phase 0 backport); Phase 3 wires the Postgres mirror, the 4th-loop two-count rule + cross-officer broadcast, and the 5th-loop pre-reply WHY scan into the existing hooks (`captain-rule-encoder.sh`, `pre-captain-dm.sh`).
