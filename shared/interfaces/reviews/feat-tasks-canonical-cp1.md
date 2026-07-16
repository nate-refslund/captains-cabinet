# Checkpoint review — feat/tasks-canonical cp1 (2026-07-17)

Integrator checkpoint (FW-019) for the tasks-canonical wave: THREE reviewed
lane diffs landed as one unit on a clean worktree off origin/master
@e90d9d2b — context-doctrine (base cbf1c8ef), adapter-kit (base 1cd84459),
event-stream (base ff26a079). Staged churn 6,821 lines across 48 files
(verified file-by-file against the union of the three lane manifests —
nothing extra, nothing dropped).

## What landed

1. **context-doctrine** — canonical `/tasks` doctrine: constitution
   "Canonical task surface" clause + `CLAUDE.md`/`docs/templates/CLAUDE-egg.md`
   twins (same paragraph, three surfaces, byte-checked); preset-aware context
   resolver as parity-pinned twins — `cabinet_resolve_context` in
   `cabinet/scripts/lib/lanes.sh` (env > `active-project.txt` > declared lane >
   `lane_default`, every rung whitespace-stripped + shape-gated before use)
   consumed by `my-tasks.sh` + `task_sync_runner.py`; dashboard TS twin
   `src/lib/active-context.ts` replacing the inline resolver in
   `/api/tasks/route.ts` (import swap only — no authz surface change);
   `framework/env.py` resolver additions (fail-closed generic defaults);
   CI ratchet `framework/tests/test_canonical_tasks_ratchet.py`; amendment
   doc `docs/proposals/germline-amendment-context-resolver-2026-07-17.md`.
2. **adapter-kit** — `task_adapters/` base seam + auto-discovered conformance
   CI gate (in-memory reference adapter must pass everything, `_template`
   must fail everything; unregistered module in the package = red build);
   `github_issues.py` transport discipline (ONE `_gh()` door, argv lists
   only, `shell=True` forbidden by the conformance source scan, rate-limit
   classification); `task-sync-drift-falsifier.py` (nightly, ONE constant
   read-only `json_agg` SELECT — untrusted titles ride JSON escaping, never
   TSV; conn string env-else-`cabinet/.env`, value argv-only, never logged;
   scrubbed capped text in the flock JSONL; task text never reaches
   captain-card argv); `services.yml` rows `task-sync` (900s) +
   `task-sync-drift` (04:20); orphaned hand-kept
   `com.cabinet.task-sync.template.plist` DELETED (generate-plists pipeline
   owns rendering); doctor check 12 via `--probe` (pure file inspection).
3. **event-stream** — durable `cabinet:tasks:events`: `my-tasks.sh` emits
   through the house `task_event_emit` (A6/A12 envelope `enforce()` BEFORE
   the XADD, best-effort — emit failure never fails the mutation);
   `task-events-watch.py` consumer (fingerprint-deduped blocked-task Captain
   cards via the needs seam; card text interpolates shape-validated tokens
   only; redis via argv subprocess, read + XACK verbs only; unparseable
   config = OFF + warn, fail-safe); `instance/config/task-watch.yml` +
   `.example` (live file egg-scrubbed, `.example` ships —
   `egg-export-manifest.txt` delete + expect-present rules);
   `cabinet/docs/tasks-board.md`; dashboard emit gap filed honestly as
   ledger row R171 (todo), not absorbed.

## Integration decisions

- Sole cross-lane overlaps `my-tasks.sh` (context-doctrine + event-stream)
  and `task_sync_runner.py` (context-doctrine + adapter-kit): both files
  unchanged on master since cbf1c8ef → `git apply --3way` merged all hunks
  clean, zero conflicts.
- Ledger append-append race with the captain-reminders wave (master gained
  CAPTAIN-REMINDERS-1 after event-stream's base): resolved keep-both — §37
  captain-reminders kept, event-stream addendum renumbered §38, this wave's
  TASKS-CANON-1 row + §39 appended. A13 + uniqueness + status-parity all
  exit 0 on the resolved pair (ids=319, findings=0).
- SCHG GUARD: every touched path `ls -lO`-checked on the live box — no schg
  flags; none in `germline-lock.sh` FILES[]/DIRS[] (the constitution edit is
  NOT germline-locked and rides the amendment doc per the standing grant,
  provenance recorded in the ledger row). Zero hunks dropped.

## Security review (integrator pass)

- No secrets: only `postgres://stub/stub` test literal; conn strings
  env-sourced, never logged. No `/Users/nate` or bare `Nate` in framework
  additions (launcher-hardcode ratchet also green in framework/tests).
- All subprocess use is argv-list (falsifier psql, gh transport, redis in
  events-watch); no `shell=True` anywhere in the new code (conformance scan
  enforces it for adapters).
- Dashboard: `active-context.ts` shape-gates every slug before any
  `path.join` (traversal-safe); reads confined to `instance/config/` under
  `cabinetRoot()`.

## Verification (this worktree, python3.12)

- cabinet/scripts/tests: 1202 passed, 4 skipped; the `test_egg_export.py`
  block (1F+22E) is a PRE-COMMIT SEQUENCING ARTIFACT ONLY: the export cuts
  HEAD while the manifest reads the working tree, so the uncommitted
  `task-watch.yml.example` trips `expect-present` (reproduced manually:
  `VERIFY FAIL — expected in export but missing: instance/config/task-watch.yml.example`).
  MUST re-run green post-commit before push — recorded here as the gate.
  POST-COMMIT RESULT: 44 passed / 1 skipped after one legitimate pin
  update — the new amendment doc joins the R167 exact-set pin in
  `test_egg_export.py` (the pin exists precisely to force this review on
  every new amendment; docstring's historical "21" count left as the
  R167-era snapshot per the 2026-07-16 precedent).
- lib/tests 210 passed; task_adapters/tests 38 passed; framework/tests 716
  passed/1 skipped; full framework/ suite running in background, checked
  before push. Dashboard vitest 1765 passed / 100 files (node_modules
  symlinked from the live checkout — lockfiles sha256-identical).
- bash -n clean on all 6 touched .sh; py_compile clean on all new .py.
- generate-plists `--output-dir` render: both new plists render + plutil
  lint OK (StartInterval 900; calendar 04:20). Never run in install mode
  from this worktree.
- docs-track-code-sweep GREEN (files=41, findings=0);
  check-layer-separation new=0 (baseline=24 allowlist=18 current=42).

## Residuals

- R171 (dashboard emit parity) — filed todo, deliberate.
- Live-fleet arming (plist install for task-sync/task-sync-drift) rides the
  normal generate-plists + deploy path, NOT this worktree.
