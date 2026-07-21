#!/bin/bash
# my-tasks.sh — Officer CLI for /tasks board state (Spec 038 Phase A v1.3).
#
# Transitions the caller's rows in the `officer_tasks` table and broadcasts
# on Redis pub/sub so the /tasks SSE stream pushes a live update.
#
# v1.2 deltas (COO adversary ratified msg 1623):
#   038.3 — context YAML absence is FATAL at CLI entry (not just a warning).
#   038.4 — block/unblock accept status IN ('queue','wip'); done/cancel clear
#           blocked + blocked_reason (the trigger's CHECK enforces this).
#   038.9 — every transaction SETs LOCAL app.cabinet_officer = :'slug' so the
#           officer_task_history AFTER trigger records the actual actor.
#
# v1.3 delta — durable task events (cabinet/docs/tasks-board.md):
#   Every REAL transition ALSO emits one A6-enveloped entry on the Redis
#   stream cabinet:tasks:events via lib/triggers.sh task_event_emit (id,
#   old_status→new_status, actor, context_slug, ts — titles/reasons NEVER
#   ride the event). The thin cabinet:tasks:updated pub/sub broadcast below
#   is UNCHANGED byte-for-byte (dashboard SSE contract). Emission is
#   best-effort: the DB row is the source of truth, so an emit failure warns
#   on stderr but never fails the mutation. Idempotent re-runs that change
#   nothing (unblock on an unblocked row, block on an already-blocked row)
#   emit NO event. done/block/unblock/cancel capture the pre-update state
#   atomically via an UPDATE..FROM self-join (RETURNING machine fields FIRST,
#   untrusted title LAST; parsing anchors on the first '^<digits>|' line so a
#   title containing a newline+fake row can never spoof the id).
#
# Usage:
#   my-tasks.sh start "<title>" [--linked-url X] [--linked-kind linear|github|library] [--linked-id Y] [--context SLUG]
#   my-tasks.sh done <id>
#   my-tasks.sh block <id> "<reason>"
#   my-tasks.sh unblock <id>
#   my-tasks.sh queue "<title>" [--linked-url X] [--linked-kind ...] [--linked-id Y] [--context SLUG]
#   my-tasks.sh list
#   my-tasks.sh cancel <id>
#
# WIP cap per officer = 3 (Spec 038 v1.1). `start` errors listing current WIP
# titles if caller is at cap; `block` flips the `blocked` boolean overlay on
# a specific WIP row (still counts toward cap — blocked is a state, not a
# separate bucket).
#
# Caller identity (first match wins — Spec 038 v1.1 AC #9 requires at least
# one of the first two to be set):
#   1. --as <slug> flag               (spec-primary)
#   2. $CABINET_OFFICER env var       (spec-primary)
#   3. --officer <slug> flag          (legacy alias, kept for compat)
#   4. $OFFICER_NAME env var          (legacy alias, kept for compat)
#   5. basename of $(pwd) if under /opt/founders-cabinet/officers/<slug>
#
# Context isolation (Spec 038 v1.1 AC #21 — context_slug is NOT NULL):
#   --context <slug>            (overrides everything)
#   cabinet_resolve_context     (lib/lanes.sh — the shared preset-aware chain):
#     $CABINET_CONTEXT env > instance/config/active-project.txt >
#     officer-lane derivation from instance/config/contexts/*.yml (exact slug,
#     else longest '<lane>-' prefix — e.g. a portfolio '<lane>-ceo' officer) >
#     single-declared-lane > platform.yml lane_default (must be a declared lane)
# If none resolves, the script errors before touching the DB. Slugs are
# CLI-validated ([a-z0-9][a-z0-9-]*, ≤32 — Spec 038 §4.8) before any use.
#
# Requires: psql in PATH, $NEON_CONNECTION_STRING. Redis pub is optional
# (silent skip if redis-cli missing — SSE fallback polling still works).

# `set -e` would abort on expected failures (e.g. WIP-cap psql error) and
# short-circuit our human-readable error reporting. We opt in to -u (undefined
# vars) and pipefail (pipeline exit propagation) only.
set -uo pipefail

usage() {
  grep '^# ' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

[ $# -lt 1 ] && usage

CMD=""
TITLE=""
REASON=""
TARGET_ID=""
LINKED_URL=""
LINKED_KIND=""
LINKED_ID=""
CONTEXT_SLUG=""
OFFICER_OVERRIDE=""

CMD="$1"; shift

# First positional after command: title, reason, or task id for applicable commands
case "$CMD" in
  start|queue)
    TITLE="${1:-}"; [ $# -gt 0 ] && shift
    ;;
  block)
    TARGET_ID="${1:-}"; [ $# -gt 0 ] && shift
    REASON="${1:-}"; [ $# -gt 0 ] && shift
    ;;
  unblock|done|cancel)
    TARGET_ID="${1:-}"; [ $# -gt 0 ] && shift
    ;;
  list) : ;;
  *) usage ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --linked-url)  LINKED_URL="$2";  shift 2 ;;
    --linked-kind) LINKED_KIND="$2"; shift 2 ;;
    --linked-id)   LINKED_ID="$2";   shift 2 ;;
    --context)     CONTEXT_SLUG="$2"; shift 2 ;;
    --as)          OFFICER_OVERRIDE="$2"; shift 2 ;;  # Spec 038 v1.1 AC #9
    --officer)     OFFICER_OVERRIDE="$2"; shift 2 ;;  # legacy alias
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# --- slug + connection setup -------------------------------------------------

OFFICER_SLUG=""
if [ -n "$OFFICER_OVERRIDE" ]; then
  OFFICER_SLUG="$OFFICER_OVERRIDE"
elif [ -n "${CABINET_OFFICER:-}" ]; then
  OFFICER_SLUG="$CABINET_OFFICER"
elif [ -n "${OFFICER_NAME:-}" ]; then
  OFFICER_SLUG="$OFFICER_NAME"
else
  CWD="$(pwd)"
  if [[ "$CWD" =~ ^/opt/founders-cabinet/officers/([a-z0-9-]+) ]]; then
    OFFICER_SLUG="${BASH_REMATCH[1]}"
  fi
fi

if [ -z "$OFFICER_SLUG" ]; then
  echo "ERROR: cannot determine officer slug. Pass --as <slug>, set \$CABINET_OFFICER, or run from officers/<slug>/." >&2
  exit 1
fi

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "ERROR: \$NEON_CONNECTION_STRING not set." >&2
  exit 1
fi

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"

# Preset-aware context resolution (config-split fix, 2026-07-17): every rung
# below --context lives in lib/lanes.sh cabinet_resolve_context — the SAME
# chain the dashboard, task_sync_runner.py and the (staged) officer launchers
# resolve, so a portfolio deployment with no active-project.txt still lands
# each officer's tasks in its lane: $CABINET_CONTEXT env >
# active-project.txt > officer-lane derivation from contexts/*.yml >
# single-declared-lane > platform.yml lane_default.
# shellcheck source=lib/lanes.sh
. "$(cd "$(dirname "$0")" && pwd)/lib/lanes.sh"
if [ -z "$CONTEXT_SLUG" ]; then
  CONTEXT_SLUG="$(cabinet_resolve_context "$OFFICER_SLUG")" || CONTEXT_SLUG=""
fi

# Spec 038 v1.1 AC #21: context_slug is NOT NULL at DB level. Fail fast with
# a readable message rather than letting psql report a CHECK violation.
if [ -z "$CONTEXT_SLUG" ]; then
  echo "ERROR: context_slug required. Pass --context <slug>, set \$CABINET_CONTEXT, write instance/config/active-project.txt, or declare your lane in instance/config/contexts/ (cabinet_resolve_context printed the full chain above)." >&2
  exit 1
fi

# Spec 038 §4.8: the CLI validates slug shape FIRST (the dashboard maps a
# malformed slug to 503 "shouldn't happen — CLI validates first"; this is
# that gate). Also keeps the contexts/<slug>.yml existence probe below
# path-traversal-proof — resolver-derived slugs already conform, this guards
# the --context flag path with the same FW-073 shape.
if ! [[ "$CONTEXT_SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] || [ "${#CONTEXT_SLUG}" -gt 32 ]; then
  echo "ERROR: context '$CONTEXT_SLUG' is invalid — slugs match [a-z0-9][a-z0-9-]* (max 32 chars)." >&2
  exit 1
fi

# Per AC #21 + v1.2 038.3: the context MUST resolve to a readable YAML file.
# Fatal — otherwise rows would refer to contexts that never exist on disk,
# orphaning them from config and confusing the dashboard badge logic.
if [ ! -f "$CABINET_ROOT/instance/config/contexts/$CONTEXT_SLUG.yml" ]; then
  echo "ERROR: context '$CONTEXT_SLUG' has no YAML at instance/config/contexts/$CONTEXT_SLUG.yml." >&2
  echo "       Create the file first (see instance/config/contexts/README), or pick a valid --context." >&2
  exit 1
fi

WIP_CAP=3

# psql wrapper: -v ON_ERROR_STOP=1 propagates errors; -A -t for clean output
psql_q() {
  psql "$NEON_CONNECTION_STRING" -v ON_ERROR_STOP=1 -A -t -q "$@"
}

# Broadcast helper (fire-and-forget — SSE will degrade to polling if skipped)
broadcast() {
  command -v redis-cli >/dev/null 2>&1 || return 0
  local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" \
    PUBLISH cabinet:tasks:updated \
    "{\"officer_slug\":\"$OFFICER_SLUG\",\"timestamp\":\"$ts\"}" >/dev/null 2>&1 || true
}

# Durable task events (v1.3): task_event_emit lives in lib/triggers.sh — the
# house trigger-bus emit path, so the A6/A12 envelope law (validate + enforce
# BEFORE the XADD) applies to this producer like every other bus producer.
MY_TASKS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib"
if [ -f "$MY_TASKS_LIB_DIR/triggers.sh" ]; then
  # shellcheck source=lib/triggers.sh
  . "$MY_TASKS_LIB_DIR/triggers.sh"
fi

# emit_event <task_id> <old_status> <new_status> — best-effort durable event.
# The DB mutation already committed when this runs: a lost event must warn
# (task_event_emit is fail-loud on stderr) but NEVER fail the verb. Missing
# lib (deployment skew) degrades to a no-op, same stance as broadcast().
#
# COG-1 §8.4 authority pointer (byte-minimal consult): when it reads exactly
# 'outbox' the relay owns the durable exhaust and this legacy direct XADD is
# skipped. Absent/unreadable/any-other value => legacy (fail-safe: the direct
# emit still fires). Default host-global path; CABINET_COG1_AUTHORITY overrides
# for tests/scratch only. Literal is layer-legal here (cabinet/scripts).
emit_event() {
  [ "$(cat "${CABINET_COG1_AUTHORITY:-$HOME/.cabinet/state/cog1-authority}" 2>/dev/null)" = "outbox" ] && return 0
  type task_event_emit >/dev/null 2>&1 || return 0
  task_event_emit "$OFFICER_SLUG" "$CONTEXT_SLUG" "$@" || true
}

# --- commands ----------------------------------------------------------------

case "$CMD" in

  start)
    [ -z "$TITLE" ] && { echo "ERROR: title required" >&2; exit 2; }
    # WIP<=3 is enforced by the `trg_enforce_officer_wip` BEFORE trigger —
    # a concurrent start that would bring the count to 4 raises
    # `WIP limit (3) exceeded ...`, which psql prints to stderr. We surface
    # a readable hint listing current WIP via the EXISTING lookup.
    OUTPUT=$({ psql_q \
      -v slug="$OFFICER_SLUG" -v title="$TITLE" \
      -v lurl="${LINKED_URL:-}" -v lkind="${LINKED_KIND:-}" \
      -v lid="${LINKED_ID:-}" -v ctx="${CONTEXT_SLUG:-}" \
      <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
INSERT INTO officer_tasks (officer_slug, title, status, linked_url, linked_kind, linked_id, started_at, context_slug)
VALUES (
  :'slug', :'title', 'wip',
  NULLIF(:'lurl',''), NULLIF(:'lkind',''), NULLIF(:'lid',''), NOW(), NULLIF(:'ctx','')
) RETURNING id, title;
COMMIT;
SQL
} 2>&1)
    RC=$?
    if [ $RC -ne 0 ] || echo "$OUTPUT" | grep -qE "WIP limit|duplicate key"; then
      # Surface existing WIP titles for a readable error
      EXISTING=$(psql_q -v slug="$OFFICER_SLUG" -v ctx="${CONTEXT_SLUG:-}" <<SQL
SELECT id || '|' || title FROM officer_tasks
 WHERE officer_slug = :'slug'
   AND COALESCE(context_slug,'') = COALESCE(NULLIF(:'ctx',''),'')
   AND status = 'wip'
 ORDER BY started_at DESC NULLS LAST;
SQL
)
      if [ -n "$EXISTING" ]; then
        echo "ERROR: WIP cap ($WIP_CAP) reached for $OFFICER_SLUG. Current WIP:" >&2
        echo "$EXISTING" | awk -F'|' '{print "  - id="$1" "$2}' >&2
        echo "Finish/cancel one before starting another." >&2
      else
        echo "$OUTPUT" >&2
      fi
      exit 1
    fi
    echo "$OUTPUT" | grep -E '^[0-9]+\|' | tail -1 | awk -F'|' '{print "STARTED id="$1" title="$2}'
    # Event id anchors on the FIRST '^<digits>|' line (the real RETURNING row —
    # a title embedding "\n99|fake" cannot spoof it; display above is cosmetic).
    NEW_ID=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    NEW_ID="${NEW_ID%%|*}"
    [ -n "$NEW_ID" ] && emit_event "$NEW_ID" "" "wip"
    broadcast
    ;;

  done)
    [ -z "$TARGET_ID" ] && { echo "ERROR: task id required (use 'my-tasks.sh list' to find yours)" >&2; exit 2; }
    # v1.3: UPDATE..FROM self-join returns the PRE-update state (o.*) in the
    # same atomic statement — machine fields first, untrusted title LAST.
    OUTPUT=$(psql_q -v slug="$OFFICER_SLUG" -v id="$TARGET_ID" <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
UPDATE officer_tasks t
   SET status = 'done', completed_at = NOW(), blocked = false, blocked_reason = NULL
  FROM officer_tasks o
 WHERE o.id = t.id
   AND t.id = :'id'::bigint
   AND t.officer_slug = :'slug'
   AND t.status = 'wip'
RETURNING t.id, o.status, o.blocked, t.title;
COMMIT;
SQL
)
    ROW=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    if [ -z "$ROW" ]; then
      echo "ERROR: task id=$TARGET_ID not found, not in WIP, or wrong officer" >&2
      exit 1
    fi
    TASK_ID=$(printf '%s\n' "$ROW" | awk -F'|' '{print $1}')
    OLD_STATUS=$(printf '%s\n' "$ROW" | awk -F'|' '{print $2}')
    WAS_BLOCKED=$(printf '%s\n' "$ROW" | awk -F'|' '{print $3}')
    printf '%s\n' "$ROW" | awk -F'|' '{print "DONE id="$1" title="$4}'
    [ "$WAS_BLOCKED" = "t" ] && OLD_STATUS="blocked"
    emit_event "$TASK_ID" "$OLD_STATUS" "done"
    broadcast
    ;;

  block)
    [ -z "$TARGET_ID" ] && { echo "ERROR: task id required" >&2; exit 2; }
    [ -z "$REASON" ] && { echo "ERROR: reason required" >&2; exit 2; }
    # 038.4: block accepts status IN ('queue','wip'). blocked_state_coherent
    # CHECK enforces done/cancelled cannot be blocked.
    OUTPUT=$(psql_q -v slug="$OFFICER_SLUG" -v id="$TARGET_ID" -v reason="$REASON" <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
UPDATE officer_tasks t
   SET blocked = true, blocked_reason = :'reason'
  FROM officer_tasks o
 WHERE o.id = t.id
   AND t.id = :'id'::bigint
   AND t.officer_slug = :'slug'
   AND t.status IN ('queue', 'wip')
RETURNING t.id, o.status, o.blocked, t.title;
COMMIT;
SQL
)
    ROW=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    if [ -z "$ROW" ]; then
      echo "ERROR: task id=$TARGET_ID not found, not in queue/WIP, or wrong officer" >&2
      exit 1
    fi
    TASK_ID=$(printf '%s\n' "$ROW" | awk -F'|' '{print $1}')
    OLD_STATUS=$(printf '%s\n' "$ROW" | awk -F'|' '{print $2}')
    WAS_BLOCKED=$(printf '%s\n' "$ROW" | awk -F'|' '{print $3}')
    printf '%s\n' "$ROW" | awk -F'|' '{print "BLOCKED id="$1" title="$4}'
    # Event only when the row ENTERS blocked — re-blocking an already-blocked
    # row (reason refresh) is a no-op transition and emits nothing.
    if [ "$WAS_BLOCKED" != "t" ]; then
      emit_event "$TASK_ID" "$OLD_STATUS" "blocked"
    fi
    broadcast
    ;;

  unblock)
    # Spec §3.3 AC #7: idempotent on already-unblocked rows.
    # UPDATE matches any queue/wip row owned by caller; SET clears both cols
    # regardless of current state so re-running is a no-op (blocked was
    # already false, blocked_reason already NULL → same row after UPDATE).
    [ -z "$TARGET_ID" ] && { echo "ERROR: task id required" >&2; exit 2; }
    OUTPUT=$(psql_q -v slug="$OFFICER_SLUG" -v id="$TARGET_ID" <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
UPDATE officer_tasks t
   SET blocked = false, blocked_reason = NULL
  FROM officer_tasks o
 WHERE o.id = t.id
   AND t.id = :'id'::bigint
   AND t.officer_slug = :'slug'
   AND t.status IN ('queue', 'wip')
RETURNING t.id, o.status, o.blocked, t.title;
COMMIT;
SQL
)
    ROW=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    if [ -z "$ROW" ]; then
      # Row genuinely not found / wrong owner / not active — NOT the
      # "already unblocked" case (that matched and no-op'd).
      echo "ERROR: task id=$TARGET_ID not found, not in queue/WIP, or wrong officer" >&2
      exit 1
    fi
    TASK_ID=$(printf '%s\n' "$ROW" | awk -F'|' '{print $1}')
    OLD_STATUS=$(printf '%s\n' "$ROW" | awk -F'|' '{print $2}')
    WAS_BLOCKED=$(printf '%s\n' "$ROW" | awk -F'|' '{print $3}')
    printf '%s\n' "$ROW" | awk -F'|' '{print "UNBLOCKED id="$1" title="$4}'
    # Idempotent no-op (already unblocked) emits nothing; a real unblock
    # returns the row to its underlying queue/wip status.
    if [ "$WAS_BLOCKED" = "t" ]; then
      emit_event "$TASK_ID" "blocked" "$OLD_STATUS"
    fi
    broadcast
    ;;

  queue)
    [ -z "$TITLE" ] && { echo "ERROR: title required" >&2; exit 2; }
    OUTPUT=$(psql_q \
      -v slug="$OFFICER_SLUG" -v title="$TITLE" \
      -v lurl="${LINKED_URL:-}" -v lkind="${LINKED_KIND:-}" \
      -v lid="${LINKED_ID:-}" -v ctx="${CONTEXT_SLUG:-}" \
      <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
INSERT INTO officer_tasks (officer_slug, title, status, linked_url, linked_kind, linked_id, context_slug)
VALUES (
  :'slug', :'title', 'queue',
  NULLIF(:'lurl',''), NULLIF(:'lkind','')::text, NULLIF(:'lid',''), NULLIF(:'ctx','')
) RETURNING id, title;
COMMIT;
SQL
)
    RC=$?
    [ $RC -ne 0 ] && { echo "$OUTPUT" >&2; exit 1; }
    echo "$OUTPUT" | awk -F'|' '{print "QUEUED id="$1" title="$2}'
    NEW_ID=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    NEW_ID="${NEW_ID%%|*}"
    [ -n "$NEW_ID" ] && emit_event "$NEW_ID" "" "queue"
    broadcast
    ;;

  cancel)
    [ -z "$TARGET_ID" ] && { echo "ERROR: id required" >&2; exit 2; }
    OUTPUT=$(psql_q -v slug="$OFFICER_SLUG" -v id="$TARGET_ID" <<'SQL'
BEGIN;
SELECT set_config('app.cabinet_officer', :'slug', true);
UPDATE officer_tasks t
   SET status = 'cancelled', blocked = false, blocked_reason = NULL
  FROM officer_tasks o
 WHERE o.id = t.id
   AND t.id = :'id'::bigint
   AND t.officer_slug = :'slug'
   AND t.status NOT IN ('done','cancelled')
RETURNING t.id, o.status, o.blocked, t.title;
COMMIT;
SQL
)
    ROW=$(printf '%s\n' "$OUTPUT" | grep -E '^[0-9]+\|' | head -1)
    if [ -z "$ROW" ]; then
      echo "ERROR: task id=$TARGET_ID not found, already closed, or wrong officer" >&2
      exit 1
    fi
    TASK_ID=$(printf '%s\n' "$ROW" | awk -F'|' '{print $1}')
    OLD_STATUS=$(printf '%s\n' "$ROW" | awk -F'|' '{print $2}')
    WAS_BLOCKED=$(printf '%s\n' "$ROW" | awk -F'|' '{print $3}')
    printf '%s\n' "$ROW" | awk -F'|' '{print "CANCELLED id="$1" title="$4}'
    [ "$WAS_BLOCKED" = "t" ] && OLD_STATUS="blocked"
    emit_event "$TASK_ID" "$OLD_STATUS" "cancelled"
    broadcast
    ;;

  list)
    # v1.2: filter by active context so Personal/Work/Adhoc tasks don't mix.
    psql_q -v slug="$OFFICER_SLUG" -v ctx="$CONTEXT_SLUG" <<'SQL'
SELECT
  status,
  CASE WHEN blocked THEN '⛓' ELSE ' ' END AS b,
  id,
  LEFT(COALESCE(title,''), 70) AS title,
  COALESCE(blocked_reason,'') AS blocked_reason
FROM officer_tasks
WHERE officer_slug = :'slug'
  AND context_slug = :'ctx'
  AND status IN ('wip','queue')
ORDER BY CASE status WHEN 'wip' THEN 0 ELSE 1 END, created_at;
SQL
    ;;

  *) usage ;;
esac
