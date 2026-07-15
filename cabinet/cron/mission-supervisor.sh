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
#   4. Push each remaining task to the officer's Redis Stream.
#   5. Only after every push succeeds, confirm those exact current decisions
#      and emit `work_item_assigned`. A Redis failure leaves work routable.
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

# Source cabinet/.env (Telegram tokens etc.) if present — launchd/cron runs
# get no login environment, so without this every Telegram send dies
# token-less. set -a exports the vars to child scripts (send-to-group.sh /
# send-to-warroom.sh and helpers).
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi

# Redis defaults to localhost on Mac. The lib/triggers.sh default is 'redis'
# (Docker container DNS). Force IPv4 localhost unless caller overrides.
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export OFFICER_NAME="${OFFICER_NAME:-mission_supervisor}"

# --- identify newly-ready, unassigned tasks via Python module ---
# Routing decisions JSON: [{task_id, officer, mission_id, outcome_id, description}, ...]
# Always project first. Assignment is committed below only after Redis delivery.
SUPERVISOR_ARGS=(--json --dry-run)
ROUTING_JSON="$(cd "$CABINET_ROOT" && python3 -m framework.missions.supervisor "${SUPERVISOR_ARGS[@]}")"

# --- push Redis triggers for each newly-assigned task ---
# Source the trigger library after exporting REDIS_HOST so the lib picks up
# our override instead of its 'redis' default.
# shellcheck source=cabinet/scripts/lib/triggers.sh
. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"

COUNT=0
DELIVERED_JSON='[]'
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
      # trigger_send returns non-zero when XADD fails. With set -e this stops
      # before assignment confirmation, so the task resurfaces next pass.
      trigger_send "$officer" "$msg"
      DELIVERED_JSON="$(printf '%s' "$DELIVERED_JSON" | jq --argjson row "$line" '. + [$row]')"
      printf 'mission-supervisor: routed %s → %s\n' "$task_id" "$officer" >&2
    fi
    COUNT=$((COUNT + 1))
  done < <(printf '%s' "$ROUTING_JSON" | jq -c '.[]?')
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$DELIVERED_JSON" != "[]" ]; then
  CONFIRMED_JSON="$(printf '%s' "$DELIVERED_JSON" | \
    (cd "$CABINET_ROOT" && python3 -m framework.missions.supervisor --confirm-stdin --json))"
  if [ "$(printf '%s' "$CONFIRMED_JSON" | jq 'length')" -ne "$COUNT" ]; then
    echo "mission-supervisor: FATAL delivery confirmation count mismatch — assignments not trusted" >&2
    exit 1
  fi
fi

# --- output ---
if [ "$JSON_OUT" -eq 1 ]; then
  printf '%s\n' "$ROUTING_JSON"
fi

echo "mission-supervisor: $COUNT task(s) routed (dry-run=$DRY_RUN)" >&2
exit 0
