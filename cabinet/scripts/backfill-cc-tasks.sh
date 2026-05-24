#!/bin/bash
# backfill-cc-tasks.sh <officer> <session-id> — one-time backfill of an officer's existing
# Claude Code built-in tasks into officer_tasks (/tasks). Idempotent (re-runnable): reuses
# the same shared upsert as the live mirror hook (lib/task-mirror-upsert.sql), keyed on
# external_ref='<officer>:<cc-task-id>'. Field parsing mirrors post-task-mirror.sh.
#
# Each officer runs it once for their current session to seed history; going forward the
# live hook keeps /tasks current. Find your session id: ls -t ~/.claude/tasks | head -1
set -uo pipefail

OFFICER="${1:?usage: backfill-cc-tasks.sh <officer> <session-id>}"
SID="${2:?usage: backfill-cc-tasks.sh <officer> <session-id>}"
DIR="$HOME/.claude/tasks/$SID"
[ -d "$DIR" ] || { echo "no task dir: $DIR" >&2; exit 1; }

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  # shellcheck source=/dev/null
  source /opt/founders-cabinet/cabinet/.env 2>/dev/null
fi
[ -z "${NEON_CONNECTION_STRING:-}" ] && { echo "no NEON_CONNECTION_STRING" >&2; exit 1; }

SQL=/opt/founders-cabinet/cabinet/scripts/lib/task-mirror-upsert.sql
n=0 skipped=0
for f in "$DIR"/*.json; do
  [ -e "$f" ] || continue
  REC=$(cat "$f" 2>/dev/null)
  echo "$REC" | jq -e . >/dev/null 2>&1 || { skipped=$((skipped+1)); continue; }

  TID=$(echo "$REC" | jq -r '.id // empty'); [ -z "$TID" ] && TID=$(basename "$f" .json)
  SUBJECT=$(echo "$REC" | jq -r '.subject // .title // empty'); [ -z "$SUBJECT" ] && { skipped=$((skipped+1)); continue; }
  DESC=$(echo "$REC" | jq -r '.description // empty')
  CCSTATUS=$(echo "$REC" | jq -r '.status // "pending"')
  case "$CCSTATUS" in
    completed) ST=done ;; in_progress) ST=wip ;; deleted|cancelled) ST=cancelled ;; *) ST=queue ;;
  esac
  PROJECT=$(echo "$REC" | jq -r '.metadata.project // .metadata.context_slug // empty')
  [ -z "$PROJECT" ] && PROJECT="${CABINET_ACTIVE_PROJECT:-}"
  DUE=$(echo "$REC" | jq -r '.metadata.due // .metadata.due_at // .metadata.due_date // empty')
  [[ "$DUE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2} ]] || DUE=""
  PRIO=$(echo "$REC" | jq -r '.metadata.priority // empty'); case "$PRIO" in P0|P1|P2|P3) ;; *) PRIO="" ;; esac
  FOUNDER=$(echo "$REC" | jq -r 'if (.metadata // {} | has("founder_action")) then (.metadata.founder_action | tostring) else "" end'); case "$FOUNDER" in true|false) ;; *) FOUNDER="" ;; esac
  TYPE=$(echo "$REC" | jq -r 'if (.metadata // {} | has("type")) then .metadata.type else "" end'); case "$TYPE" in task|epic) ;; *) TYPE="" ;; esac

  if psql "$NEON_CONNECTION_STRING" -q \
       -v officer="$OFFICER" -v title="$SUBJECT" -v desc="$DESC" -v st="$ST" \
       -v proj="$PROJECT" -v due="$DUE" -v prio="$PRIO" -v founder="$FOUNDER" \
       -v ttype="$TYPE" -v extref="${OFFICER}:${TID}" -f "$SQL" >/dev/null 2>&1; then
    n=$((n+1))
  else
    skipped=$((skipped+1))
  fi
done
echo "backfilled $n tasks for $OFFICER (session $SID); skipped $skipped"
