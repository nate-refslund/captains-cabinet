# Phase 5 Log — Task-System Adapters

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** (1 real adapter shipped, 4 skeletons documented)

## Goal

The Cabinet's canonical task model (`officer_tasks`, `mission_steps`, event ledger) syncs bidirectionally to any external task system. Captain configures one per project. Plan called for 5 adapters: Monday + Jira + Linear + Asana + GitHub Issues.

## Delivered

### 5.1 — Base adapter interface

`cabinet/scripts/task_adapters/base.py`:

- `CanonicalTask` dataclass — universal task representation with lowest-common-denominator fields across all five external systems
- `SyncResult` dataclass — sync cycle outcome (pulled / pushed / conflicts / errors / timestamps)
- `TaskAdapter` ABC with abstract methods: `health_check`, `pull`, `push`, `delete`, `link`
- `get_adapter(project_config)` factory — instantiates the right adapter based on `project_config['tasks']['system']`
- Auth contract: each adapter declares `auth_env_var`; `TaskAdapter.auth_token()` reads from env
- Conflict resolution policy documented: **canonical wins** — external changes get overwritten on next sync with a warning logged

### 5.2 — GitHub Issues adapter (FULLY IMPLEMENTED)

`cabinet/scripts/task_adapters/github_issues.py`:

- Uses the locally-installed `gh` CLI (no env-var token needed — `gh auth login` handles auth)
- `health_check`: verifies `gh auth status` + `gh repo view <repo>` both succeed
- `pull`: `gh issue list --state all --json ...` → maps to `CanonicalTask`
- `push`: idempotent upsert keyed on `cabinet:<canonical_id>` label. Edit existing or create. Handles state transitions (open ↔ closed) via `gh issue close/reopen`
- `delete`: closes with reason "not planned" (gh has no hard-delete for non-admins)
- `link`: adds the `cabinet:<canonical_id>` label
- Status mapping: open / in_progress (label "wip") / blocked (label "blocked") / done (closed, completed) / cancelled (closed, not planned)
- Role mapping: `officer:<slug>` label
- Priority mapping: `priority:<level>` label

GitHub Issues was chosen for the first real adapter because (1) `gh` CLI is already on Captain's Mac, (2) no env token needed, (3) Cabinet's framework backlog already lives in GitHub Issues per CLAUDE.md.

### 5.3 — Skeleton adapters (Monday + Jira + Linear + Asana)

Each ships as a `TaskAdapter` subclass with:

- Documented API: endpoint URL, auth type, target mapping table (CanonicalTask ↔ external item)
- Required `project_config` shape (with `tasks.config.<field>` keys explained inline)
- Constructor validates the required `tasks.config` fields (e.g. Monday needs `board_id`, Jira needs `domain`+`email`+`project_key`)
- `health_check()` returns `False` (placeholder)
- `pull/push/delete/link` raise `NotImplementedError` with a one-line hint about which API call to implement

`linear.py` carries an additional **WRITE FORBIDDEN** warning per Spec-039 cutover (Linear is read-only archive on Cabinet deployments bound by Spec-039). The adapter is shipped for two reasons: (1) audit / migration reads still need it, (2) new Cabinet deployments not bound by Spec-039 may use Linear actively.

### 5.4 — Sync runner

- `cabinet/scripts/task_sync_runner.py` — orchestrates one sync cycle. Reads `instance/config/active-project.txt` → loads `instance/config/projects/<slug>.yml` → instantiates adapter via `get_adapter()` → runs `pull()` (skeletons return empty) → emits events.
- `cabinet/cron/task-sync.sh` — thin bash wrapper for launchd. `--health` mode for adapter health check. `--json` mode for machine-readable summary.
- Phase 5 ships **pull-only**. The push side requires reading Cabinet's canonical task store, which is Phase 6 work (product-bootstrap populates the canonical store from the explored product). Documented in the runner.
- Sync emits `outbox_queued` / `outbox_dispatched` events (reusing Phase 1.4 outbox event vocabulary).

## Test gates (PASS)

- 19 new tests in `cabinet/scripts/task_adapters/tests/test_base.py`:
  - `CanonicalTask` construction (minimal + full)
  - `SyncResult` default
  - `get_adapter` factory: missing system / unknown / each of the 5 supported
  - Adapter contract: each of 5 implements all abstract methods (parametrized)
  - Skeleton enforcement: Monday push, Jira pull, Linear push (with archive warning), Asana delete all raise `NotImplementedError`
- Full suite: **556/556 pass** (was 537; +19 new adapter tests)
- bash -n on `cabinet/cron/task-sync.sh` — clean

## Files touched

- `cabinet/scripts/task_adapters/__init__.py` (NEW, marker)
- `cabinet/scripts/task_adapters/base.py` (NEW, ~150 lines)
- `cabinet/scripts/task_adapters/github_issues.py` (NEW, ~240 lines — fully implemented)
- `cabinet/scripts/task_adapters/monday.py` (NEW, skeleton)
- `cabinet/scripts/task_adapters/jira.py` (NEW, skeleton)
- `cabinet/scripts/task_adapters/linear.py` (NEW, skeleton + Spec-039 warning)
- `cabinet/scripts/task_adapters/asana.py` (NEW, skeleton)
- `cabinet/scripts/task_adapters/tests/__init__.py` (NEW, marker)
- `cabinet/scripts/task_adapters/tests/test_base.py` (NEW, 19 tests)
- `cabinet/scripts/task_sync_runner.py` (NEW)
- `cabinet/cron/task-sync.sh` (NEW)
- `docs/convergence-analysis-2026-05-26/phase-5-log.md` (this file)

## Deferred

- **Real implementations of 4 skeleton adapters** — Captain provides credentials; adapter authors fill in the documented API calls. Per-adapter effort: ~3-4 hours each.
- **Push side of the sync runner** — depends on Phase 6 (product-bootstrap populates canonical task store).
- **Round-trip integration test against a real GitHub repo** — needs a test repo and the test would have side effects (creates issues). Test is documented but not auto-run.

## Resume signal

Phase 5 complete (1 real adapter + 4 skeletons + factory + sync runner). Next: **Phase 6 — Product-agnostic onboarding**: `bootstrap-project.sh` that clones a repo, detects stack, generates project config, runs holistic exploration, and surfaces findings to Captain.
