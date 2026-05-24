# Spec 066 — Claude Code Built-in Tasks → officer_tasks Mirror

**Version:** v1 (documents as-built v1 shipped commit 91717e2 + formalizes conventions)
**Date:** 2026-05-24
**Status:** v1 SHIPPED (mirror mechanics live, ~141 CoS tasks backfilled). This spec is the formal record + the design contract for the tagging-discipline layer (not yet built) + dashboard requirements.
**Priority:** P1
**Framework ticket:** FW-116
**Owner:** CoS (owns the hook + SQL — shipped), CPO (owns this spec + the metadata/tagging-discipline design), CTO (owns the dashboard view)
**Parent:** Spec 038 (officer_tasks schema) + Spec 039 (Linear→/tasks cutover). The /tasks Postgres store became the canonical backlog at the 2026-04-26 cutover; this closes the loop so officers' real working state (CC built-in tasks) flows into it without manual double-entry.
**Evidence:** Captain msgs 2749-2755 (2026-05-24) — feature directive + 5 decisions (one-way, mirror-everything-incl-deletes, metadata→columns mapping, soft-not-hard tagging discipline, Captain-never-authors).
**Canonical artifact home:** Library Specs Space (per A11).

---

## Problem

Officers use Claude Code's **built-in task tools** (TaskCreate / TaskUpdate / TaskList) as their live working list — it's in-session, low-friction, and the natural place to track what they're doing. But the **canonical cross-officer backlog is `officer_tasks` (Postgres, surfaced at `/tasks`)** since the Spec 039 Linear cutover. Without a bridge, the two diverge:

1. **`/tasks` goes stale.** Officers' real work lives in CC tasks; `/tasks` only sees what someone manually re-enters. The dashboard, Captain's view, and CoS's priority math all read a false picture.
2. **Double-entry tax.** Asking officers to author in both CC tasks AND `/tasks` is friction they won't sustain — the working list wins, the canonical store rots.
3. **No cross-officer / historic view.** CC tasks are per-session, per-officer, ephemeral. There's no single place to see "what is every officer working on, and what's the history."

The fix is a **one-way mirror**: officers keep using CC tasks as their working list; every change reflects into `officer_tasks` automatically, so `/tasks` becomes the single live + historic cross-officer view with zero double-entry.

## Solution

A **PostToolUse hook** (`post-task-mirror.sh`, matcher `TaskCreate|TaskUpdate`) mirrors every CC task change into `officer_tasks` via a shared idempotent upsert (`lib/task-mirror-upsert.sql`). A one-time `backfill-cc-tasks.sh` seeds an officer's existing tasks. Direction is strictly one-way (CC → officer_tasks); Captain reads `/tasks` (dashboard + Telegram), never authors there.

### Design decisions (Captain msgs 2751-2755)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **One-way only** (officers author in CC tasks → mirror to /tasks) | Captain is Telegram-only + dashboard-read-only. Two-way sync would need conflict resolution + a write surface Captain doesn't use. |
| D2 | **Mirror everything, including deletes → `cancelled`** | Never hard-delete — preserves history. A deleted CC task becomes a `cancelled` officer_task, not a gap. |
| D3 | **Structured fields via task `metadata` → typed columns** | Officers tag once in CC task metadata; the mirror maps to the existing officer_tasks columns. |
| D4 | **Tagging discipline = auto-inference + SOFT nudge, NOT hard enforcement** | Captain explicit: don't block an officer's task on a missing tag. Infer what we can; nudge gently; never reject. |
| D5 | **Captain never authors in /tasks** | /tasks is a read-only reflection + cross-officer view for Captain; the authoring surface is the officer's CC tasks. |

## As-built mechanics (v1, commit 91717e2)

### Hook: `cabinet/scripts/hooks/post-task-mirror.sh`
- **Trigger:** PostToolUse matcher `TaskCreate|TaskUpdate` in `.claude/settings.json` — runs ONLY on task tool calls (zero overhead elsewhere; also fast-exits if `tool_name` isn't a task tool).
- **Fail-safe contract (load-bearing):** all DB work is **backgrounded + error-swallowed**. The hook must NEVER block or break an officer's tool flow. If Postgres is down, the mirror silently skips; the officer's CC task (their working source of truth) is unaffected. `exit 0` always.
- **Kill switches:** `CABINET_TASK_MIRROR_DISABLED=1` (disable entirely) + `CABINET_HOOK_TEST_MODE=1` (skip in eval/test) + requires `OFFICER_NAME` (exits if unknown).
- **Task-id resolution:** TaskUpdate carries `taskId` in input. TaskCreate returns a STRING (`"Task #<n> created successfully: …"`, NOT a JSON `{id}`), so the hook parses the **leading `#<n>`** (the id is always the first `#<n>`, ahead of any `#<n>` in the subject); object-shape `.id` kept as a forward-compat fallback.
- **Record source:** prefers the authoritative on-disk record `~/.claude/tasks/<session>/<id>.json` (reflects full post-update state); falls back to `tool_input`.
- **external_ref** = `<officer>:<cc-task-id>`; **external_source** = `claude-tasks`.

### Status mapping (CC → officer_tasks; constraint: queue|wip|done|cancelled)
| CC status | officer_tasks status |
|-----------|----------------------|
| `completed` | `done` |
| `in_progress` | `wip` |
| `deleted` / `cancelled` | `cancelled` |
| `pending` / other | `queue` |

`started_at` set on first wip/done; `completed_at` on done; `cancelled_at` on cancelled (all `COALESCE`-guarded so they don't churn).

### SQL: `cabinet/scripts/lib/task-mirror-upsert.sql` (shared by hook + backfill — fix lands once)
- **Idempotent upsert WITHOUT a unique index:** `UPDATE … WHERE external_source='claude-tasks' AND external_ref=:extref`; `INSERT … WHERE NOT EXISTS (SELECT 1 FROM upd)`. Parameterized via `psql -v` (no string interpolation — injection-safe).
- **CRITICAL — pooler-safe trigger suspend:** the mirror reflects the officer's REAL working state, so it must bypass the two AUTHORING-discipline triggers (`app.etl.suspend_wip_limit`, `app.etl.suspend_founder_check`) — officers legitimately have >3 in-flight CC tasks (WIP=3-per-context limit governs /tasks-authored tasks), and a founder-tagged task without a due should still mirror. **These MUST be `SET LOCAL` inside an explicit `BEGIN; … COMMIT;`** — `NEON_CONNECTION_STRING` is the PgBouncer **pooler** endpoint, where a plain `SET` persists on the server backend and leaks to the next client that checks it out, silently disabling the triggers cabinet-wide (review caught this: 5/5 fresh connections read the leaked GUCs). `SET LOCAL` reverts at COMMIT, scoping the suspend to this write only.
- **Sticky metadata:** `COALESCE(NULLIF(:new,''), existing)` — a metadata-less update (e.g. just flipping status) doesn't wipe a prior tag. Status / title / description always overwrite from source.

### Backfill: `cabinet/scripts/backfill-cc-tasks.sh <officer> <session-id>`
One-time per officer per session; idempotent (same upsert, keyed on external_ref). Iterates `~/.claude/tasks/<session>/*.json`. Find session id: `ls -t ~/.claude/tasks | head -1`. Reports backfilled/skipped counts.

## Metadata-key convention (the formal tagging contract)

Officers tag a CC task by setting keys in its `metadata` object. The mirror maps each to a typed `officer_tasks` column. **All are optional + sticky** (absent → keep existing on update; untagged on create → column default).

| metadata key | officer_tasks column | Accepted values | Default if absent |
|--------------|---------------------|-----------------|-------------------|
| `project` (or `context_slug`) | `context_slug` | any context slug (`sensed`, `cabinet-framework`, …) | `$CABINET_ACTIVE_PROJECT`, else **`untagged` sentinel — NEVER NULL** (see CTO #3 resolution) |
| `due` (or `due_at` / `due_date`) | `due_at` + `due_date` | ISO-8601 prefix `YYYY-MM-DD…` (bad format dropped) | keep existing |
| `priority` | `priority` | `P0` \| `P1` \| `P2` \| `P3` (else dropped) | keep existing |
| `founder_action` | `founder_action` | `true` \| `false` | keep existing (insert default `false`) |
| `type` | `type` | `task` \| `epic` | keep existing (insert default `task`) |

`due` maps to BOTH `due_date` (date — what the founder-needs-due rule checks) and `due_at` (timestamptz — Spec 041 reminder trigger). Tag once, both populate.

### CTO #3 resolution — context_slug NOT-NULL invariant (data-model decision)

`OfficerTask.context_slug` is typed non-null (`lib/tasks.ts:48`, "NOT NULL per AC #21; every row has a validated slug"). The v1 mirror writes NULL on untagged tasks (the ~141 backfilled CoS rows), which conflicts with the type → latent UI null-crash (board grouping / filter / sort assume `string`).

**Decision: the mirror NEVER writes NULL `context_slug` — untagged resolves to a reserved `untagged` sentinel slug.** Chosen over CTO option (b) relax-type-to-`string|null` because:
- Holds the existing NOT-NULL invariant + filter/grouping/sort logic intact — no consumer null-safety audit, no UI-crash surface (CTO's preferred (a)).
- Faithful to "officer working-tasks may legitimately be project-less" (CTO (b)'s concern) — but represents project-less as an **explicit, queryable, nudge-able value** rather than an ambiguous NULL.
- Distinct from `adhoc` (a *real* context = genuinely-cross-project work). `untagged` = "untagged, needs triage" — it's exactly what the soft-nudge prompts the officer to fix.

**Implementation (v1.1 correction — small):**
- Hook + backfill: replace the `NULLIF(:'proj','')→NULL` default with `untagged` when both `metadata.project` and `$CABINET_ACTIVE_PROJECT` are empty. (CoS owns the hook/SQL edit.)
- One-time data fix: `UPDATE officer_tasks SET context_slug='untagged' WHERE external_source='claude-tasks' AND context_slug IS NULL;` (the ~141 existing rows).
- `lib/tasks.ts` type stays `string` (invariant preserved); CTO adds the `untagged` bucket to grouping.

## Tagging-discipline layer (design requirement — NOT in v1; CPO design, CoS implements)

Per D4 (soft, not hard). Two parts:

### 1. Auto-inference (reduce manual tagging)
On TaskCreate, infer metadata the officer didn't set, where confidence is high:
- **`context_slug`** — already done (defaults to `$CABINET_ACTIVE_PROJECT`). Keep.
- **`founder_action`** — infer `true` if subject/description matches founder-action signals (`/\b(captain|founder|nate) (needs?|must|to)\b/i`, "credential", "approve", "App Store", "BotFather", "migration you", etc.). Inference is a SUGGESTION surfaced via the nudge (below), not a silent write — officer confirms.
- **`priority`** — infer from keywords (`P0`/`urgent`/`blocker`/`gate-blocking` → P0; `P1`/`high` → P1) as a nudge suggestion.
- **`type=epic`** — infer if the task has subtasks (manageSubtasks used).

### 2. Soft nudge (never blocks)
When a created task lacks high-value metadata that couldn't be confidently inferred, surface a **non-blocking advisory** (stderr from a companion PostToolUse step OR a system-reminder), e.g.:
> *"Mirrored to /tasks untagged for project — consider `metadata.project` so it routes to the right context. (advisory, not required)"*

Specifically nudge when: (a) no `project` AND `$CABINET_ACTIVE_PROJECT` unset → task lands context-less; (b) `founder_action:true` but no `due` → the founder-accountability loop needs a date (this mirrors the AUTHORING trigger the mirror suspends, re-surfaced as a *nudge* on the source side where it's appropriate). The nudge NEVER rejects the task (Captain D4).

## Dashboard requirements (CTO owns the view)

`/tasks` must surface the mirrored tasks as the cross-officer backlog:
- **Group by `context_slug`** (project lens) with an **`untagged` bucket** (filter `context_slug='untagged'` — the sentinel for untagged tasks; also a signal the nudge isn't landing). Per CTO #2: the existing `?context=` filter + `COALESCE(context_slug,'')` already supports this; the `untagged` sentinel is a concrete filterable value (cleaner than empty-string/NULL matching).
- **Filter by `officer_slug`, `status`, `priority`, `founder_action`, `type`.**
- **Show `external_source='claude-tasks'`** provenance (distinguish mirrored-from-CC vs any legacy/ETL rows) — read-only badge.
- **Founder-action view:** all `founder_action=true` tasks across officers with `due_date`, days-overdue (feeds CoS accountability loop + morning briefing).
- **History:** `cancelled` tasks visible (filterable out by default) — the deletes→cancelled preservation is only valuable if surfaceable.
- **Read-only.** No author/edit controls — authoring is in officers' CC tasks per D1/D5.

## Acceptance criteria

1. **Hook fires only on task tools** — `post-task-mirror.sh` is a PostToolUse matcher `TaskCreate|TaskUpdate`; a non-task tool call is a no-op (fast-exit).
2. **Fail-safe** — with Postgres unreachable, an officer's TaskCreate/TaskUpdate completes normally (hook exits 0, mirror silently skipped). Test: point `NEON_CONNECTION_STRING` at a dead host → task tool still succeeds.
3. **Idempotent** — running the same task change (or re-running backfill) twice produces exactly one `officer_tasks` row (keyed on `external_source`+`external_ref`), not duplicates.
4. **Status mapping** — completed→done, in_progress→wip, deleted/cancelled→cancelled, pending→queue; `started_at`/`completed_at`/`cancelled_at` set per transition.
5. **Metadata mapping + stickiness** — each metadata key maps to its column; a metadata-less status-only update does NOT wipe prior tags (COALESCE-sticky).
6. **Deletes preserved** — a deleted CC task → `cancelled` officer_task (row exists, not removed).
7. **Pooler-safe trigger suspend (regression-critical)** — after a mirror write, a FRESH pooled connection reads `app.etl.suspend_wip_limit` / `app.etl.suspend_founder_check` as UNSET (the SET LOCAL did not leak). Eval: mirror-write then open N fresh connections, assert GUCs unset on all N.
8. **TaskCreate id parse** — the `#<n>` from the TaskCreate response string is correctly extracted as the task id (not a `#<n>` embedded in the subject).
9. **Backfill** — `backfill-cc-tasks.sh <officer> <session>` seeds existing tasks idempotently + reports counts.
10. **Soft nudge never blocks** (tagging-discipline layer) — an untagged or founder-without-due task still mirrors successfully; the nudge is advisory-only (no non-zero exit, no rejection).
11. **context_slug NOT-NULL invariant holds (CTO #3)** — every mirror-written row has a non-null `context_slug` (active project, explicit tag, or `untagged` sentinel). Eval: mirror an untagged task with `$CABINET_ACTIVE_PROJECT` unset → assert `context_slug='untagged'`, NOT NULL. One-time backfill sets existing NULL rows to `untagged`.

## Edge cases

- **Postgres down / pooler timeout** — `PGCONNECT_TIMEOUT=5`; silent skip; officer unaffected (AC #2).
- **Pooler GUC leak** — the headline risk; SET LOCAL + explicit transaction (AC #7). A plain SET here would silently disable authoring triggers cabinet-wide.
- **TaskCreate response format change** — if CC ever returns a JSON `{id}` instead of the `"Task #<n>…"` string, the `.id`/`.task.id` fallback catches it.
- **Multi-session** — task store is `~/.claude/tasks/<session>/`; the hook reads the live session's record. Backfill is per-session (officer runs once per session they want seeded). Cross-session history accrues in officer_tasks via external_ref.
- **Untagged task** — lands with `context_slug` = active project, else the `untagged` sentinel (never NULL, per CTO #3); surfaced in the dashboard `untagged` bucket + nudged to tag properly.
- **Bad due format** — ISO-prefix guard drops it (no malformed timestamptz cast).
- **Officer renames a task** — title always overwrites (not sticky), so the mirror tracks renames.

## Dependencies

- **Spec 038** — `officer_tasks` schema (columns: officer_slug, title, description, status, context_slug, due_at, due_date, priority, founder_action, type, external_source, external_ref, started_at/completed_at/cancelled_at).
- **Spec 041** — due-at reminder trigger (composes with `due_at`).
- **Authoring-discipline triggers** — the WIP=3-per-context limit + founder_action⇒due_date rule, with their `app.etl.suspend_*` escape hatches (shared with the Linear/GitHub migration ETL).
- **`CABINET_ACTIVE_PROJECT`** env (context default).

## Out of scope

- **Two-way sync** (officer_tasks → CC tasks) — explicitly not built (D1). Officers author in CC tasks only.
- **Captain authoring in /tasks** (D5) — /tasks is read-only for Captain.
- **The dashboard view implementation** — requirements here; CTO builds.
- **Hard tagging enforcement** — explicitly rejected (D4).

## Phasing

- **v1 (SHIPPED, 91717e2):** mirror hook + shared upsert + backfill + status/metadata mapping + pooler-safe suspend. ~141 CoS tasks backfilled.
- **v1.1 (next):** (a) context-sentinel fix — mirror writes `untagged` not NULL (CoS hook/SQL edit + one-time backfill of ~141 NULL rows) per CTO #3; (b) tagging-discipline layer (auto-inference + soft nudge) — CPO finalizes inference rules, CoS implements as a companion PostToolUse advisory.
- **v1.2:** dashboard view (CTO) per requirements above (source badge + project filter/untagged bucket + founder-action view + history).

## Review process

CoS authored + shipped v1 (owns the hook); a review agent already caught the pooler-GUC-leak (SET→SET LOCAL) pre-ship. This spec = CPO formal record + design contract. CoS confirms the as-built section matches; CTO confirms dashboard requirements are buildable; COO adversary optional (low-risk, fail-safe, already-shipped + reviewed).
