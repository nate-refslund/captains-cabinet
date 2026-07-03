# Germline amendment proposal — `task_create` action type (2026-07-03)

**Status:** AWAITING CAPTAIN. Germline files (`framework/authority/classifier.py`,
`framework/policies/authority-matrix.yml`) are Captain-applied only. Reply
**"apply task_create"** and the session applies exactly this diff, updates the
FIX-1/FIX-6/7 CI tests in the same commit, and records the ruling in
captain-decisions.md.

**Why (strategy report, corrected rec 2 — adversarially verified):** the action
lane's `monday_task_create` cards cannot be classified — the kind exists in no
enum, so every verdict on a create-card lands in the `__unstamped__` sentinel
that BY DESIGN can never graduate. Without this amendment, the first-graduation
campaign burns your verdict budget for zero progress. `monday_task_update`
already maps to the existing `board_status` type (stamping live as of tonight);
creates need this one new type.

**What it does NOT do:** it does not touch the six hard-ceiling classes, does
not move anything out of `network_write`, and does not flip any behavior to
auto — a freshly stamped `task_create` cell starts `unmeasured` → propose_only
exactly like every other cell, and graduates only through the normal bar
(n≥20 human verdicts, fitness ≥0.85, recency-clean). The separate, bigger
act-with-undo amendment (pm_write/calendar_write carve-out) is NOT part of
this — it ships as its own proposal after this wire proves itself.

## Diff 1 — framework/authority/classifier.py

```diff
 _REVERSIBLE = {
     "task_status_move", "board_status", "label", "tier2_note",
-    "draft_only", "local_edit",
+    "draft_only", "local_edit", "task_create",
 }
```

Plus a classify_action branch: an action-lane Monday create (board allowlisted,
agent-tagged, no human assignees) classifies `task_create`; anything else
falls through unchanged.

## Diff 2 — framework/policies/authority-matrix.yml

```diff
 risk_classes:
   reversible:
     action_types:
-      [task_status_move, board_status, label, tier2_note, draft_only, local_edit]
+      [task_status_move, board_status, label, tier2_note, draft_only, local_edit, task_create]
```

No verdict-table changes — `task_create` inherits the reversible class rows
(graduated → auto, everything else → propose_only) that already exist.

## Same-commit obligations (Docs Must Track the Code)

- FIX-1 CI test: enum membership assertion gains `task_create`.
- FIX-6/7 ceiling assertions: unchanged (no ceiling class touched) — re-run to prove.
- captain-decisions.md entry: this ruling, superseding nothing (additive).
- Golden evals: full suite re-run; EVAL-014 gate anchors unaffected.
