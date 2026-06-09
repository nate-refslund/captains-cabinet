#!/usr/bin/env bash
# mission-supervisor.sh — Event-sourced router that pushes newly-ready mission
# work-graph tasks to their assigned officers via Redis Streams.
#
# Phase 1.2 of the convergence plan. Closes the outer mission loop:
#   1. Read `instance/config/outcomes.yml` and compile active outcomes
#      (compiler applies event-sourced status overlay, so DONE/FAILED nodes
#      don't re-route).
#   2. For each mission, find ready_tasks() — deps DONE, status PENDING/READY.
#   3. Filter out tasks already assigned via the event ledger
#      (`work_item_assigned` events) — strict idempotency.
#   4. For each remaining task, emit `work_item_assigned` + push a Redis
#      Stream trigger to the assigned officer.
#
# Design: NO Postgres required. The event ledger is the source of truth for
# both completion (Phase 1.1) and assignment (Phase 1.2). Postgres becomes
# the indexed read-model layer in a later phase if needed for performance.
#
# Usage:
#   cron/mission-supervisor.sh           — single pass, exit 0
#   cron/mission-supervisor.sh --json    — print routing decisions as JSON
#   cron/mission-supervisor.sh --dry-run — compile + identify, do not emit/route
#
# Cadence: every 5 minutes (cron + launchd). Idempotent — re-running is safe.
#
# Environment:
#   CABINET_ROOT       — repo root (default: ../.. from this script)
#   REDIS_HOST         — Redis host (default: 127.0.0.1 for Mac, 'redis' in Docker)
#   REDIS_PORT         — Redis port (default: 6379)
#   CABINET_EVENT_LOG_DIR — event log path (default: ~/Library/Application Support/cabinet/events)
#   OFFICER_NAME       — actor label used when emitting events (default: mission_supervisor)

set -euo pipefail

# --- arg parsing ---
JSON_OUT=0
DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --json)    JSON_OUT=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '1,40p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "mission-supervisor: unknown arg: $a" >&2; exit 2 ;;
  esac
done

# --- resolve cabinet root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Redis defaults to localhost on Mac. The lib/triggers.sh default is 'redis'
# (Docker container DNS). Force IPv4 localhost unless caller overrides.
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export OFFICER_NAME="${OFFICER_NAME:-mission_supervisor}"

# --- identify newly-ready, unassigned tasks via Python module ---
# Routing decisions JSON: [{task_id, officer, mission_id, outcome_id, description}, ...]
# Emits work_item_assigned events as a side effect unless --dry-run is set.
SUPERVISOR_ARGS=(--json)
if [ "$DRY_RUN" -eq 1 ]; then
  SUPERVISOR_ARGS+=(--dry-run)
fi
ROUTING_JSON="$(cd "$CABINET_ROOT" && python3 -m framework.missions.supervisor "${SUPERVISOR_ARGS[@]}")"

# --- push Redis triggers for each newly-assigned task ---
# Source the trigger library after exporting REDIS_HOST so the lib picks up
# our override instead of its 'redis' default.
# shellcheck source=cabinet/scripts/lib/triggers.sh
. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"

COUNT=0
if [ -n "$ROUTING_JSON" ] && [ "$ROUTING_JSON" != "[]" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    officer=$(printf '%s' "$line" | jq -r '.officer')
    task_id=$(printf '%s' "$line" | jq -r '.task_id')
    description=$(printf '%s' "$line" | jq -r '.description')
    if [ "$DRY_RUN" -eq 1 ]; then
      printf 'mission-supervisor: [dry-run] would route %s → %s (%s)\n' "$task_id" "$officer" "$description" >&2
    else
      msg="Mission task ready: $description (id: $task_id) — run work-graph-complete.sh when done"
      trigger_send "$officer" "$msg"
      printf 'mission-supervisor: routed %s → %s\n' "$task_id" "$officer" >&2
    fi
    COUNT=$((COUNT + 1))
  done < <(printf '%s' "$ROUTING_JSON" | jq -c '.[]?')
fi

# --- output ---
if [ "$JSON_OUT" -eq 1 ]; then
  printf '%s\n' "$ROUTING_JSON"
fi

echo "mission-supervisor: $COUNT task(s) routed (dry-run=$DRY_RUN)" >&2
exit 0
