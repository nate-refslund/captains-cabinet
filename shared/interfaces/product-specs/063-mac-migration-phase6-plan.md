# Spec 063 — Mac Migration Phase 6 Plan (Cabinet Worktrees + Adapter Contract)

- **Version:** v1.1 (CTO 5 MUST-fold safety + path findings folded)
- **Date:** 2026-05-23 (v1.0 → v1.1 07:15 UTC)
- **Author:** CoS (autonomous per Captain msg 2605, 2607, 2612)
- **Status:** READY for CTO re-confirm + Captain execution

**v1.1 changelog — CTO 5 MUST-fold + 2 SHOULD-fold + 2 NIT findings (msg 2026-05-23 06:59 UTC):**
- **(1) Worktree-remove safety guard (HIGHEST PRIORITY — load-bearing for dev-tasks coexistence):** 6.2 originally used `~/work/cabinet-worktrees/` tilde-string-compare, which NEVER matches the resolved `/Users/cabinet/work/...` path. Symlink/`..`-traversal attacks defeat the boundary. v1.1 uses `realpath` + literal `$HOME` prefix + case-glob.
- **(2) Source repo path on Mac:** `/workspace/product` is the Docker convention; on Mac it's `~/work/captains-cabinet`. 6.1 updated.
- **(3) Task-completion hook surface clarified:** app-layer (Next.js API route on the customer dashboard) vs Postgres NOTIFY listener. 6.3 updated to specify the chosen surface (Postgres NOTIFY for non-Mac-side reliability).
- **(4) `git worktree remove --force` forensics:** before delete, log uncommitted state to `cabinet/logs/worktree-removed/<task-id>.txt` so we have a paper trail if a force-delete loses work.
- **(5) `tsconfig.json` coverage for adapter template:** 6.6 needs explicit tsconfig that includes `cabinet/adapters/_template/` so the type-check stays meaningful.
- **SHOULD-fold:** worktree-add idempotency (re-run on same task-id), error message clarity. Both folded.
- **NIT:** held.
- **Parent directive:** Captain Mac Mini Directive msg 2599 §Phase 6 ("Cabinet worktrees + adapter contract formalization — 1 day")
- **Predecessors:** Spec 057-062 (Phases 0-5)
- **Successor:** Spec 064 (Phase 7 — full officer rollout + observability)

---

## 1. Phase 6 goal (from directive)

Cabinet worktree lifecycle works end-to-end (per-task worktree at `~/work/cabinet-worktrees/`, auto-cleanup on task completion). Adapter contract documented + templated. No new adapters shipped — Notion + Linear legacy adapters keep existing READMEs. Critical: Cabinet worktrees at `~/work/cabinet-worktrees/` must NEVER touch `.claude/worktrees/` (dev-tasks territory per Phase B).

## 2. Inputs from Phase 5

- Mac mini runs CoS + screenpipe + daily-digest LaunchAgent
- All officers Telegram-dark except CoS (Lead-only)
- Constitution carries Lead-only Telegram + Lead-only computer-use clauses

## 3. Captain ratifications

- **Mac Migration Directive §Risk #4:** worktree immediate cleanup means no in-worktree rollback. Restic hourly + Time Machine hourly cover host-level recovery.
- **A11 Library + /tasks canonical** — `/tasks` records own the `worktree_path` field.

## 4. Checkpoint structure

Phase 6 decomposes into **9 checkpoints**. Directive estimates 1 day; realistic 4-5 hours focused.

### Checkpoint 6.1 — Write `cabinet/scripts/worktree-add.sh`

- **Pre-conditions:** Phase 5 complete.
- **Actions:**
  1. Write `cabinet/scripts/worktree-add.sh`:
     ```bash
     #!/bin/bash
     # worktree-add.sh <officer> <task-id> <branch>
     # Creates git worktree at ~/work/cabinet-worktrees/<officer>-<task-id>/
     # Records the worktree path in the /tasks record as worktree_path
     # Returns the path
     ```
  2. Use `git worktree add` against `$HOME/work/captains-cabinet` (CTO v1.1 #2 — Mac uses `~/work/captains-cabinet`, NOT the Docker convention `/workspace/product`).
- **Golden eval:**
  - `bash -n` passes
  - Test invocation creates worktree under `~/work/cabinet-worktrees/`
  - /tasks record's `worktree_path` field updated via Postgres
- **Rollback:** `rm` script + git worktree remove created worktree.
- **Effort:** 30-45 min.

### Checkpoint 6.2 — Write `cabinet/scripts/worktree-remove.sh`

- **Pre-conditions:** 6.1 PASS.
- **Actions:**
  1. Write `cabinet/scripts/worktree-remove.sh`:
     ```bash
     #!/bin/bash
     # worktree-remove.sh <task-id>
     # Looks up worktree path from /tasks record
     # Runs git worktree remove --force <path>
     # Clears worktree_path field
     # CRITICAL: operates ONLY on ~/work/cabinet-worktrees/. NEVER touches .claude/worktrees/.
     ```
  2. **Explicit safety guard (v1.1 CTO #1 — realpath, not tilde-string):**
     ```bash
     CABINET_WORKTREE_ROOT="$HOME/work/cabinet-worktrees"
     # Resolve symlinks + .. to canonical absolute path
     RESOLVED=$(realpath -m "$worktree_path" 2>/dev/null || echo "/dev/null/INVALID")
     # Case-glob against literal HOME-prefixed root (handles macOS case-insensitive FS)
     case "$RESOLVED" in
       "$CABINET_WORKTREE_ROOT"/*)
         # OK — path resolves inside our root; safe to remove
         ;;
       *)
         echo "REFUSE: path $RESOLVED does not resolve under $CABINET_WORKTREE_ROOT" >&2
         exit 1
         ;;
     esac
     # Forensics (CTO #4): log uncommitted state before --force removal
     mkdir -p cabinet/logs/worktree-removed
     git -C "$RESOLVED" status --porcelain > "cabinet/logs/worktree-removed/${task_id}.txt" 2>/dev/null || true
     ```
- **Golden eval:**
  - `bash -n` passes
  - Test invocation removes the worktree from 6.1 test
  - **Critical safety test:** attempt to point worktree_path at `.claude/worktrees/foo` and call worktree-remove.sh — should refuse, NOT remove, exit non-zero
- **Rollback:** `rm` script.
- **Effort:** 30-45 min.

### Checkpoint 6.3 — Add task-completion hook calling worktree-remove.sh (v1.1 CTO #3 — Postgres NOTIFY)

- **Pre-conditions:** 6.2 PASS.
- **Actions:**
  1. **Hook surface decision (CTO #3):** use Postgres NOTIFY listener (not app-layer Next.js route). Reasons: Mac-side reliability (Next.js dashboard may not be running 24/7); Postgres NOTIFY is durable for the small payload; matches existing Spec 041 due_at trigger pattern.
  2. Add Postgres trigger on `officer_tasks` table: when status transitions to terminal state (`done` / `cancelled`), emit `NOTIFY cabinet_task_terminal, '<task_id>'`.
  3. Write `cabinet/scripts/worktree-listener.sh` — long-running process listening on `LISTEN cabinet_task_terminal`. On notification, invoke `worktree-remove.sh <task-id>`.
  4. Register worktree-listener as a LaunchAgent: `cabinet/launchd/com.cabinet.worktree-listener.plist`.
- **Golden eval:**
  - Marking a test /tasks record `done` via Postgres update triggers NOTIFY
  - worktree-listener receives notification + invokes worktree-remove.sh
  - `.claude/worktrees/` UNTOUCHED (verified by safety guard from 6.2)
  - Force-delete forensics log exists at `cabinet/logs/worktree-removed/<task-id>.txt`
- **Rollback:** drop Postgres trigger; bootout worktree-listener LaunchAgent.
- **Effort:** 60-90 min (substantive hook integration).

### Checkpoint 6.4 — Document Cabinet worktree contract

- **Pre-conditions:** 6.3 PASS.
- **Actions:**
  1. Write `docs/worktrees.md` with explicit "Cabinet worktrees only, NEVER dev-tasks" framing
  2. Reference Phase B (dev-tasks plugin) future scope
- **Golden eval:** doc exists with the Cabinet-vs-dev-tasks distinction prominent.
- **Rollback:** `rm` doc.
- **Effort:** 30 min.

### Checkpoint 6.5 — Write `cabinet/adapters/README.md` adapter contract

- **Pre-conditions:** 6.4 PASS.
- **Actions:**
  1. Write `cabinet/adapters/README.md` with the directive's adapter contract:
     ```typescript
     interface CabinetAdapter {
       name: string;
       type: 'tasks' | 'library' | 'both';
       pushTask?(task: TasksRecord): Promise<{ external_id: string }>;
       pushSpace?(record: LibraryRecord, space: string): Promise<{ external_id: string }>;
       pullTask?(external_id: string): Promise<TasksRecord>;
       pullSpace?(external_id: string, space: string): Promise<LibraryRecord>;
       resolveConflict: 'cabinet_wins' | 'external_wins' | 'newest_wins' | 'manual';
       handleWebhook?(payload: unknown): Promise<void>;
     }
     ```
  2. Include "what adapters are NOT" — they are bidirectional mirrors, not lifecycle orchestrators (per Phase B distinction).
- **Golden eval:** README at expected path with interface + non-confusion section.
- **Effort:** 30 min.

### Checkpoint 6.6 — Write `cabinet/adapters/_template/` skeleton

- **Pre-conditions:** 6.5 PASS.
- **Actions:**
  1. Create `cabinet/adapters/_template/` with `adapter.ts`, `webhook.ts`, `field-mapping.yml`, `README.md` skeletons.
  2. Make `adapter.ts` skeleton type-check (placeholder implementation of `CabinetAdapter` interface).
- **Golden eval:**
  - 4 skeleton files exist
  - `tsc --noEmit cabinet/adapters/_template/adapter.ts` (or equivalent) passes
- **Rollback:** `rm -rf cabinet/adapters/_template/`.
- **Effort:** 45 min.

### Checkpoint 6.7 — Add `instance/config/adapters.yml` (all disabled)

- **Pre-conditions:** 6.6 PASS.
- **Actions:**
  1. Create `instance/config/adapters.yml`:
     ```yaml
     adapters:
       notion:
         enabled: false
       linear:
         enabled: false
     ```
- **Golden eval:** file exists + parses as YAML.
- **Effort:** 5 min.

### Checkpoint 6.8 — Document existing legacy Notion + Linear adapters

- **Pre-conditions:** 6.7 PASS.
- **Actions:**
  1. Write `cabinet/adapters/notion/README.md` if missing (or refresh) — references existing Notion MCP usage
  2. Write `cabinet/adapters/linear/README.md` if missing
- **Golden eval:** both READMEs exist.
- **Effort:** 30 min.

### Checkpoint 6.9 — Phase 6 baseline doc + commit

- **Pre-conditions:** 6.1-6.8 PASS.
- **Actions:** Write `docs/migration-phase6-baseline.md`; commit + push.
- **Effort:** 20 min.

## 5. Effort estimate (whole Phase 6)

**Realistic: 4-5 hours focused.** Directive's 1 day matches.

## 6. Stop-the-line gates

1. **6.2 worktree-remove safety guard fails the test** (removes from `.claude/worktrees/` accidentally). Halt + fix the path-prefix check. **Critical — this is the dev-tasks-coexistence boundary the directive flagged.**

## 7. Phase 6 → Phase 7 handoff

When Phase 6 completes:
- Cabinet worktree lifecycle works
- Adapter contract documented + templated; no new adapters shipped
- Phase 7 brings up full officer rollout against this clean substrate

## 8. Sign-off

DRAFT ready for CTO tech review. All checkpoints CoS-executable.
