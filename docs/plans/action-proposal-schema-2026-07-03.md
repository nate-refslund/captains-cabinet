# Action-Proposal Schema — design spec (2026-07-03)

> **Status:** design-only, drafted ahead of implementation. Trunk step 4 of the
> capture→action lane (`capture-to-action-lane-design-2026-07-03.md` §4/§8).
> Implementation waits on **B2.1 correlation-id** landing. This spec is written
> to validate against the CURRENT consequence schema with the **minimum** additive
> change — three new `action_type` enum members, nothing else.

## 0. The load-bearing finding

The consequence ledger needs almost no change to carry action proposals:

- **`action` is a FREE non-empty string** — `consequence.py:114-117` checks
  `isinstance(str) and non-empty`, no enum. So `task-create`, `feature-impl`, etc.
  are already valid `action` values. **Zero schema change** for the action names.
- **`action_type` IS enum-constrained** — `consequence.py:126-135` requires
  membership in `ACTION_TYPES` (the shared classifier, `authority/classifier.py:72`,
  the ONE source of truth per FIX-1). This is the only place an additive change is
  needed, and only for the action_types that don't already exist.
- Decisions (`_PROPOSAL_DECISIONS`), outcome statuses (`_OUTCOME_STATUSES =
  {ok, failed, unknown}`), and review verdicts are **unchanged** — the existing
  `proposal_event` / `outcome_event` / `expire_event` lifecycle carries actions as-is.

## 1. Action types — reuse first, extend minimally

Current `ACTION_TYPES` (classifier.py): `board_status, task_status_move, local_edit,
git_push_nonmain, git_push_main, vercel_deploy_preview, vercel_deploy_prod,
external_email, external_message, internal_email, internal_message, label,
tier2_note, draft_only, env_write, secret_read/write, oauth_grant, token_grant,
provision_paid, purchase, billing, mcp_post/put/delete, ambiguous`.

| Lane action | `action` string | `action_type` | Reuse or additive | Executes | Executor seam | Ceiling class |
|---|---|---|---|---|---|---|
| Create a task | `task-create` | **`task_create`** | **ADDITIVE** (no create type exists; `task_status_move`/`board_status` are updates) | new row in the canonical work store (+ optional TaskAdapter mirror) | `framework/missions/compiler.py` + `cabinet/scripts/task_sync_runner.py` | none (low-blast) |
| Update a task | `task-update` | `task_status_move` **or** `board_status` | **REUSE** — both already exist | status/priority/field change on an existing item | `task_sync_runner.py` | none |
| Implement a feature | `feature-impl` | `local_edit` (edit) → `git_push_nonmain` (PR) | **REUSE** — both exist | worktree-isolated build → PR on a non-main branch | lane-CEO spawn (worktree isolation) | **edit/PR = none; `git_push_main` + `vercel_deploy_prod` stay CEILING** |
| Schedule a follow-up | `followup-schedule` | **`reminder_write`** | **ADDITIVE** (no reminder/schedule type) | a time-bound nudge (Reminders / brief queue) | reminders writer | none |
| Close a commitment | `commitment-close` | **`commitment_close`** | **ADDITIVE** (no commitment-state type; `tier2_note` is too generic) | mark an owed-by/owed-to commitment resolved with evidence | commitment-ledger writer | none |

**Additive change required (one file, three lines):** add `task_create`,
`reminder_write`, `commitment_close` to the `_TASK`/appropriate group feeding
`ACTION_TYPES` in `framework/authority/classifier.py:72` — plus classifier
detection rules that map the lane's executor calls to them. All three are
**non-ceiling** (they never touch `CEILING_ACTION_TYPES`). Because the classifier
is the single source of truth (FIX-1), adding them there propagates to the schema
validator, the emit-time stamp, and the gate verdict lookup atomically — no schema
SQL edit, no validator edit.

## 2. proposal_event payload shape

Reuse `loop.proposal_event(*, actor, lane, subject, ts, action, required, refs)`
unchanged. Per-action conventions:

```
actor    = {"kind": "officer", "id": "officer:<lane-ceo|cos>"}
action   = "task-create" | "task-update" | "feature-impl" | "followup-schedule" | "commitment-close"
subject  = the STABLE situation key — e.g. "commitment:<slug>" | "thread:<id>" |
           "task:<id>" | "meeting:<id>"  (this + actor + action + ts = the
           proposal_id identity tuple the binder cross-checks)
ts       = capture-signal time (ISO-8601, fractional ok)
refs     = [correlation_id (B2.1), source-signal ref, target-item ref] — the JOIN
           to the capture signal and the thing being acted on. Content (the task
           title/body) is NOT stored on the ledger (leak-safe, same as drafts);
           it lives in the redis card payload the binder reads by pid.
required = True   # every action is Captain-gated until its graduation cell lifts
```

The `action_type` is stamped at **emit** time (not on the pending proposal_event —
it is stamped when the outcome/decision is recorded, mirroring how the classifier
stamps today), so the pending card carries `action` and the executor's classified
`action_type` lands on the superseding outcome event.

## 3. Lifecycle (reuses the hardened binder + M-1 honest outcomes)

```
proposal_event(action="task-create", subject="commitment:colleague-call", …)
   │  emit_consequence(...) → pending on the ledger
   ▼
CARD to Captain  (·pid· = proposal_id; Chair echoes the pid — cp2 label-UX)
   │  Captain: send / ja / edit: … / skip: …
   ▼
binder_wire.handle_captain_update
   │  extract_pids + cross-check vs the open set (B-2 hardening) → bind the REAL pid
   │  handle_response emits the SUPERSEDING decision event BEFORE execution (fail-closed)
   ▼
EXECUTOR runs (task_sync_runner / lane spawn / reminder writer / commitment writer)
   │
   ▼
OUTCOME (M-1 — honest, never pre-emitted):
   outcome_event(...) with outcome.status =
      "ok"      (held)   ← executor RETURNED success (row written / PR opened / reminder set)
      "failed"          ← executor errored → a superseding outcome=failed amendment
   verdict ladder reads the REAL result; graduation cells get a true
   outcome_held_rate denominator per (officer, action_type).
```

Un-acted action proposals **expire** via `loop.expire_event` (verdict unknown, no
outcome) — the same hygiene that cleared the 13 parked drafts.

## 4. The hard ceiling — pinned, structural

`external_comms, deploy_prod, spend, secrets, network_write, credentials_grant`
never lift (blueprint hard-ceiling; `CEILING_ACTION_TYPES` in classifier.py:69).
Specifically for this lane:

- **NO `external_comms` action exists at all.** The lane defines no action that
  emits `external_email`/`external_message`. Comms is Nate's — this is structural,
  not a policy toggle. (The existing external_* action_types remain in the enum for
  the classifier's ceiling detection of *other* code paths; the action-lane simply
  never proposes one.)
- **`feature-impl` may `local_edit` + `git_push_nonmain` (PR) but never
  `git_push_main` / `vercel_deploy_prod`** — deploy stays Captain-only, already a
  ceiling class. The lane-CEO executor must be constrained to non-main pushes.
- `spend`/`purchase`/`billing`, `secret_*`, `oauth_grant`/`token_grant`,
  `provision_paid`, `mcp_delete` — no lane action maps to any of these.

## 5. Graduation posture (per action_type)

Cells key on `(officer, lane, action_type)`, all start **propose-first**. Only the
low-blast types graduate on evidence: `task_create`, `task_status_move`/`board_status`,
`reminder_write`. `feature-impl` (`local_edit`/`git_push_nonmain`) and
`commitment_close` stay propose-first far longer; ceiling types never graduate.
Starvation (ledger-liveness) auto-demotes a cell whose evidence stops flowing.

## 6. Open questions for implementation (resolve when B2.1 lands)

1. **`task_create` vs generalized `task_write`:** add a single `task_write` covering
   create+update, or keep `task_create` distinct from the existing
   `task_status_move`/`board_status` (finer graduation granularity)? Recommend
   distinct `task_create` — it lets create graduate separately from update.
2. **`commitment_close` executor authority:** closing a commitment writes to the
   commitment-ledger (screenpipe-side in flavor A). Confirm the write path honors
   the brain-bridge `append_agent_inbox`-only rule vs a dedicated close API.
3. **`action_type` stamp timing:** confirm stamping at outcome-emit (executor
   classifies its own call) vs pre-stamping on the pending proposal (Captain sees
   the classified type on the card). Recommend outcome-time to match today's
   classifier flow, with the card showing the human `action` string.
4. **subject stability for feature-impl:** a feature spec may span multiple capture
   signals — define whether `subject` keys on the spec id or the triggering signal
   (affects idempotency/dedup of repeat proposals).
5. **TaskAdapter mirror:** confirm the canonical local store (SQLite `officer_tasks`)
   is the write-of-record and Monday `5091706356` is a mirror for `task_create`
   specifically (PM-decoupling ruling — confirm it holds for action-writes).
