# Phase 1 Log — Close the Mission Loops

**Started:** 2026-05-26
**Branch:** `claude/convergence` (off `origin/claude/clever-tesla-CS3Su-rebuild`)
**Status:** **COMPLETE** — all sub-phases (1.1, 1.2, 1.3, 1.4, 1.5, 1.6) landed.
Originally I expected 1.2 + 1.4 to need Postgres. Re-architected as event-sourced (Redis only), unblocking the full Phase 1 in this session.

## Goal

Make the org runtime actually loop: officers can mark mission steps done, OVI gets real event-ledger data, the system shows non-stub measurements end-to-end.

## Delivered sub-phases

### 1.1 — Mission completion loop (commit `b4c19fe`)

- `cabinet/scripts/work-graph-complete.sh <node_id> [--status done|failed|verified] [--evidence FILE_OR_TEXT]`
- `framework/missions/compiler.py::_apply_status_from_events(graph, outcome_id)` — event replay overlays DONE / FAILED / verified status on rebuilt work graphs
- `cabinet/scripts/lib/tests/conftest.py` smart yaml stub — only stubs when real module missing
- 8 new tests in `test_compiler.py` (480→488 total)

### 1.3 — OVI data wiring (this commit)

- `framework/ovi/compute.py::gather_from_events(window_days)` — materializes sample_data from event ledger
- CLI default: `python3 framework/ovi/compute.py` (no args) → uses `--from-events --window-days 7` (previously silently exited 1)
- New `--from-events` and `--window-days` flags
- `framework/ovi/components.yml` v2 — documents derivation per component, retains legacy DB queries for Phase 1.2+
- `cabinet/launchd/com.cabinet.ovi-weekly.template.plist` — passes `--from-events --window-days 7` explicitly
- 8 new tests in `test_compute.py` (39→47)

### 1.5 — outcome_to_verified scenario (this commit)

- `framework/measurement/scenarios/outcome_to_verified.py` — end-to-end loop closure scenario
  - Setup: roles + Captain-ratified outcome (4 measurable criteria)
  - Execute: compile mission → simulate completion + verification → recompile (overlay) → compute OVI
  - Verify: 13 assertions covering compilation, overlay, ready_tasks emptiness, event emission, OVI math
- 2 new pytest tests in `test_scenario_runner.py` exercising `outcome_to_verified` + `outcome_to_mission` via the Python API
- Bug fix in `framework/missions/compiler.py::_apply_status_from_events`: `verification_passed` now updates independently of status change (verified-after-completed case)
- Bug fix in `framework/measurement/scenarios/outcome_to_mission.py`: criterion "Sign-up form" replaced with "User signup flow" so role-matching keyword map succeeds

### 1.6 — Run tests + commit

- `framework/ + cabinet/scripts/lib/tests/` — **498/498 pass** (1.00s)
  - 131 framework (123 baseline + 8 new compiler overlay)
  - 8 new OVI gather_from_events
  - 2 new scenario_runner integration
  - 357 policy_engine + work_graph
- bash syntax checks (all script surfaces) — clean
- Smoke test of `work-graph-complete.sh`: event emitted, payload correctly extracted
- Smoke test of OVI CLI default: produces score 0.6150 from seeded event ledger

### 1.2 — mission-supervisor.sh (event-sourced router)

Re-architected as event-sourced — **no Postgres required**. The event ledger is the source of truth for both completion (Phase 1.1) and assignment (Phase 1.2).

- `framework/missions/supervisor.py` — testable module with `find_unassigned_ready_tasks()`, `route_pending_tasks()`, `already_assigned_ids()`, `main()` CLI
- `cabinet/cron/mission-supervisor.sh` — bash wrapper that calls `python3 -m framework.missions.supervisor --json` then loops Redis Stream pushes via `lib/triggers.sh::trigger_send`
- Idempotency via replay of `work_item_assigned` events. Re-running emits zero new work.
- Smoke-tested end-to-end: outcomes.yml → compile → identify 1 ready task → emit `work_item_assigned` → push Redis Stream message to `cabinet:triggers:engineering`. Second invocation routes 0 tasks. ✅
- 12 new tests in `framework/missions/tests/test_supervisor.py`

Starter content also committed: `instance/roles/active/engineering.yml` + `instance/roles/active/product.yml` + `instance/roles/lineage.yml` — gives the mission compiler something to match against on a fresh deployment.

### 1.4 — Transactional outbox (event-sourced)

Re-architected: the event ledger IS the outbox table. Classic transactional-outbox pattern applied to event sourcing.

- New event types in `framework/events/emitter.py`: `outbox_queued`, `outbox_dispatched`, `outbox_failed`
- `framework/outbox/relay.py` with:
  - `queue(destination, payload, actor, idempotency_key=None)` — emit `outbox_queued`. Idempotency-key dedup re-fires return the original event id.
  - `dispatch_pending()` — read pending (queued minus terminal-dispatched), dispatch each via registered adapter, emit `outbox_dispatched` (success) or `outbox_failed` (transient or terminal).
  - `register_adapter(destination, fn)` — pluggable; Phase 5 will register Monday/Jira/Linear/Asana/GitHub Issues/Notion adapters. Phase 1.4 ships only the no-op `stub` adapter for tests.
- Terminal-vs-transient: unknown destination → `terminal=True` (don't loop forever); adapter exception → `terminal=False` (retry next cycle).
- `cabinet/cron/outbox-relay.sh` — thin wrapper invoking `python3 -m framework.outbox.relay`
- Smoke-tested: 2 queued → dispatch → 1 dispatched + 1 skipped (unknown destination, terminal); subsequent run shows 0 pending. ✅
- 12 new tests in `framework/outbox/tests/test_relay.py` (queue / dispatch / idempotency / transient retry / payload integrity / pending tracking)

### 1.6 — Phase 1 closeout

- Full suite: **522/522 pass** (was 488 after Phase 1.3; +12 supervisor + +12 outbox + +10 from prior)
- All shell scripts pass `bash -n` syntax checks
- New scripts marked executable and integrated

## Files touched in this commit (Phase 1.2 + 1.4 + 1.6 closeout)

- `framework/events/emitter.py` — added outbox_queued / outbox_dispatched / outbox_failed event types
- `framework/missions/supervisor.py` — NEW (event-sourced routing module)
- `framework/missions/tests/test_supervisor.py` — NEW (12 tests)
- `framework/outbox/__init__.py` — NEW (package marker)
- `framework/outbox/relay.py` — NEW (queue + dispatch_pending + adapter registry)
- `framework/outbox/tests/__init__.py` — NEW
- `framework/outbox/tests/test_relay.py` — NEW (12 tests)
- `cabinet/cron/mission-supervisor.sh` — NEW (bash wrapper)
- `cabinet/cron/outbox-relay.sh` — NEW (bash wrapper)
- `instance/roles/active/engineering.yml` — NEW (starter role)
- `instance/roles/active/product.yml` — NEW (starter role)
- `instance/roles/lineage.yml` — NEW (role lineage log)

## Commits

- `40d127d` Phase 0 — Foundation merge
- `b4c19fe` Phase 1.1 — work-graph-complete + event-sourced status overlay (488 tests)
- `54637e0` Phase 1.3 + 1.5 — OVI from events + outcome_to_verified scenario (498 tests)
- `<this commit>` Phase 1.2 + 1.4 + 1.6 closeout — supervisor + outbox + starter roles (522 tests)

## Resume signal

Phase 1 is complete. Next phase: **Phase 2 — Role Eval Infrastructure** (50 scenario evals, 10 per officer × 5 officers, weekly cron, evolution proposals). See `05-convergence-plan.md` § Phase 2.

## Resume signal

A successor session resuming Phase 1 should:
1. Read this file + `05-convergence-plan.md` § Phase 1
2. `git log --oneline claude/convergence -10` to see latest commits
3. Continue with **Phase 1.2** (mission-supervisor.sh) — requires Postgres + Redis. May need to first wire up local dev Postgres if not available, or write the supervisor + tests against a stub.
4. Then **Phase 1.4** (transactional outbox), which depends on 1.2's DB schema additions.
5. Then **Phase 1.6 closeout commit** — already partially done; will finalize after 1.2+1.4 land.
