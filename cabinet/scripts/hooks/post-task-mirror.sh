#!/bin/bash
# post-task-mirror.sh — mirror Claude Code built-in tasks → officer_tasks (Postgres /tasks).
#
# Wired as a PostToolUse matcher for TaskCreate|TaskUpdate (see settings.json), so it
# ONLY runs on task tool calls — zero overhead on every other tool call.
#
# One-way by design (Captain msg 2751): officers author/update/tag/assign in CC's built-in
# tasks; this mirrors them into officer_tasks so /tasks is the single live + historic
# cross-officer view. Nate + the dashboard read /tasks; they don't author there.
#
# Mirror EVERYTHING (Captain msg 2751): every task, every status, including deletes
# (→ cancelled, never hard-deleted — preserves history).
#
# Project assignment: set metadata.project on the task → mirrors to context_slug
# (the existing multi-project field: sensed / cabinet-framework / etc). Untagged → NULL.
#
# FAIL-SAFE CONTRACT: this hook must NEVER block or break an officer's tool flow. All
# DB work is backgrounded + error-swallowed. If Postgres is down, the mirror silently
# skips; the officer's CC task (the source of truth for their working list) is unaffected.

HOOK_INPUT=$(cat)

# Fast-exit on non-task tools — keeps this a no-op for the vast majority of tool calls.
TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
case "$TOOL_NAME" in
  TaskCreate|TaskUpdate) ;;
  *) exit 0 ;;
esac

OFFICER="${OFFICER_NAME:-unknown}"
[ "$OFFICER" = "unknown" ] && exit 0

# Disable hook entirely with CABINET_TASK_MIRROR_DISABLED=1; skip in eval/test mode.
[ "${CABINET_TASK_MIRROR_DISABLED:-0}" = "1" ] && exit 0
[ "${CABINET_HOOK_TEST_MODE:-0}" = "1" ] && exit 0

# Everything below is backgrounded + guarded — cannot affect the officer's tool flow.
(
  TOOL_INPUT=$(echo "$HOOK_INPUT" | jq -c '.tool_input // {}' 2>/dev/null)
  TOOL_OUTPUT=$(echo "$HOOK_INPUT" | jq -c '.tool_response // {}' 2>/dev/null)
  SID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null)

  # Task id: TaskUpdate carries taskId in input. TaskCreate returns it in the response,
  # which is a STRING like "Task #179 created successfully: …" (NOT a JSON {id} object) —
  # so parse the leading "#<n>". The task id is always the first "#<n>" in that message
  # ("Task #<id> …"), ahead of any "#<n>" inside the subject. Object-shape .id kept as a
  # forward-compatible fallback in case CC changes the response format.
  TID=$(echo "$TOOL_INPUT" | jq -r '.taskId // empty' 2>/dev/null)
  if [ -z "$TID" ]; then
    RESP=$(echo "$HOOK_INPUT" | jq -r '.tool_response // empty' 2>/dev/null)
    TID=$(printf '%s' "$RESP" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
    [ -z "$TID" ] && TID=$(printf '%s' "$RESP" | jq -r '.id // .task.id // empty' 2>/dev/null)
  fi
  [ -z "$TID" ] && exit 0

  # Prefer the authoritative on-disk record (reflects the full post-update state);
  # fall back to the tool_input. Store: ~/.claude/tasks/<session>/<id>.json
  REC=""
  STORE="$HOME/.claude/tasks/$SID/$TID.json"
  if [ -r "$STORE" ]; then REC=$(cat "$STORE" 2>/dev/null); fi
  echo "$REC" | jq -e . >/dev/null 2>&1 || REC="$TOOL_INPUT"

  SUBJECT=$(echo "$REC" | jq -r '.subject // .title // empty' 2>/dev/null)
  DESC=$(echo "$REC" | jq -r '.description // empty' 2>/dev/null)
  CCSTATUS=$(echo "$REC" | jq -r '.status // "pending"' 2>/dev/null)
  [ -z "$SUBJECT" ] && exit 0

  # CC status → officer_tasks status (constraint: queue|wip|done|cancelled)
  case "$CCSTATUS" in
    completed) ST=done ;;
    in_progress) ST=wip ;;
    deleted|cancelled) ST=cancelled ;;
    *) ST=queue ;;
  esac

  # Structured fields carried in the task's metadata, mapped to typed columns
  # (Captain msg 2753). Each is STICKY: empty/absent → keep existing on update,
  # so a metadata-less update (e.g. just flipping status) doesn't wipe a prior tag.
  #   metadata.project        → context_slug   (untagged → cabinet's active project, else NULL)
  #   metadata.due[_at|_date] → due_at         (composes with Spec 041 due-reminder trigger)
  #   metadata.priority       → priority       (P0-P3 only, else dropped)
  #   metadata.founder_action → founder_action (bool)
  #   metadata.type           → type           (task|epic)
  PROJECT=$(echo "$REC" | jq -r '.metadata.project // .metadata.context_slug // empty' 2>/dev/null)
  [ -z "$PROJECT" ] && PROJECT="${CABINET_ACTIVE_PROJECT:-}"
  DUE=$(echo "$REC" | jq -r '.metadata.due // .metadata.due_at // .metadata.due_date // empty' 2>/dev/null)
  [[ "$DUE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2} ]] || DUE=""   # ISO-prefix guard; bad format → drop
  PRIO=$(echo "$REC" | jq -r '.metadata.priority // empty' 2>/dev/null)
  case "$PRIO" in P0|P1|P2|P3) ;; *) PRIO="" ;; esac
  FOUNDER=$(echo "$REC" | jq -r 'if (.metadata // {} | has("founder_action")) then (.metadata.founder_action | tostring) else "" end' 2>/dev/null)
  case "$FOUNDER" in true|false) ;; *) FOUNDER="" ;; esac
  TYPE=$(echo "$REC" | jq -r 'if (.metadata // {} | has("type")) then .metadata.type else "" end' 2>/dev/null)
  case "$TYPE" in task|epic) ;; *) TYPE="" ;; esac

  EXTREF="${OFFICER}:${TID}"

  # DB conn (hooks run without the officer's full env)
  if [ -z "$NEON_CONNECTION_STRING" ]; then
    # shellcheck source=/dev/null
    source /opt/founders-cabinet/cabinet/.env 2>/dev/null
  fi
  [ -z "$NEON_CONNECTION_STRING" ] && exit 0

  # Idempotent upsert WITHOUT a unique index: UPDATE the mirrored row; if none, INSERT.
  # Keyed on (external_source='claude-tasks', external_ref='<officer>:<id>'). Parameterized
  # via psql -v (no string interpolation — injection-safe). Metadata fields use
  # COALESCE(NULLIF(new,''), existing) so they're sticky; status/title/desc always overwrite.
  #
  # Suspend the two AUTHORING-discipline triggers for this ETL write (they ship with these
  # exact escape hatches — used by the Linear/GitHub migration): the mirror reflects the
  # officer's REAL CC working state, so it must not be rejected by the WIP=3-per-context
  # limit (officers legitimately have >3 in-flight CC tasks) or the founder_action⇒due_date
  # rule (a founder tag without a due should still mirror). Those disciplines apply to
  # tasks AUTHORED in /tasks, not to this read-only reflection. due maps to BOTH due_date
  # (date, what the founder rule checks) and due_at (timestamptz, Spec 041 reminder trigger).
  PGCONNECT_TIMEOUT=5 psql "$NEON_CONNECTION_STRING" -q \
    -v officer="$OFFICER" \
    -v title="$SUBJECT" \
    -v desc="$DESC" \
    -v st="$ST" \
    -v proj="$PROJECT" \
    -v due="$DUE" \
    -v prio="$PRIO" \
    -v founder="$FOUNDER" \
    -v ttype="$TYPE" \
    -v extref="$EXTREF" \
    -f /opt/founders-cabinet/cabinet/scripts/lib/task-mirror-upsert.sql >/dev/null 2>&1
) >/dev/null 2>&1 &

exit 0
