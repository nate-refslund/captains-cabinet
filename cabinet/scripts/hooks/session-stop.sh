#!/bin/bash
# session-stop.sh — Stop hook (fires when the officer finishes a response).
# Two jobs, in order:
#   1. NEVER-STOP-DURING-A-TASK guard — re-inject "continue" while work remains.
#   2. Session-end observability (only reached when NOT blocking).

HOOK_INPUT=$(cat)
# hook lives at cabinet/scripts/hooks/, so repo root is three levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# ============================================================
# 1. NEVER-STOP-DURING-A-TASK GUARD (Captain directive 2026-06-23, emphatic:
#    "YOU MUST NEVER EVER STOP DURING A TASK" — corrected 4+ times)
# ============================================================
# Context is NEVER a reason to stop — the pre/post-compact hooks preserve state
# across auto-compaction (the Chair built them), so compaction is a feature, not a
# stop signal. This guard BLOCKS the stop (Claude Code decision:block protocol)
# whenever there is active work, re-injecting "take the next action":
#   - cabinet:active-task:<officer> — a self-directed task flag the officer SETs
#     at the start of ANY multi-step task (with a TTL safety) and DELs ONLY when
#     the task is truly complete. This is the signal a self-directed task is open.
#   - pending triggers in the officer's stream.
# Independent of context %. A per-session block cap prevents a runaway if work
# never clears (stuck-safety).
#   Disable:   CABINET_STOP_GUARD_DISABLED=1
#   Block cap: CABINET_STOP_GUARD_MAX_BLOCKS (default 12)
#   Test short-circuit: CABINET_HOOK_TEST_MODE=1
if [ "${CABINET_STOP_GUARD_DISABLED:-0}" != "1" ] \
   && [ "${CABINET_HOOK_TEST_MODE:-0}" != "1" ] \
   && [ "$OFFICER" != "unknown" ]; then

  GUARD_MAX_BLOCKS=${CABINET_STOP_GUARD_MAX_BLOCKS:-12}
  ACTIVE_TASK=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:active-task:$OFFICER" 2>/dev/null)

  PENDING_TRIGGERS=0
  if [ -r "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh" ]; then
    # shellcheck source=/dev/null
    . "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh" 2>/dev/null
    PENDING_TRIGGERS=$(trigger_count "$OFFICER" 2>/dev/null | grep -o '[0-9]*' | head -1)
    [[ "$PENDING_TRIGGERS" =~ ^[0-9]+$ ]] || PENDING_TRIGGERS=0
  fi

  if [ -n "$ACTIVE_TASK" ] || [ "$PENDING_TRIGGERS" -gt 0 ] 2>/dev/null; then
    BLOCK_KEY="cabinet:stop-guard:blocks:${OFFICER}:${SESSION_ID}"
    BLOCKS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$BLOCK_KEY" 2>/dev/null)
    [[ "$BLOCKS" =~ ^[0-9]+$ ]] || BLOCKS=0

    if [ "$BLOCKS" -lt "$GUARD_MAX_BLOCKS" ] 2>/dev/null; then
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INCR "$BLOCK_KEY" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "$BLOCK_KEY" 86400 > /dev/null 2>&1

      WORK=""
      [ -n "$ACTIVE_TASK" ] && WORK="active task → ${ACTIVE_TASK}"
      [ "$PENDING_TRIGGERS" -gt 0 ] 2>/dev/null && WORK="${WORK}${WORK:+ ; }${PENDING_TRIGGERS} pending trigger(s)"

      REASON="DO NOT STOP — work in progress (${WORK}). Captain directive (2026-06-23, corrected 4+ times): NEVER stop mid-task. Context is NEVER a reason — the pre/post-compact hooks preserve your state across auto-compaction (you built them); compaction is a feature, not a stop. Take the NEXT concrete action on the task NOW. Only when the task is TRULY complete, run: redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} DEL cabinet:active-task:${OFFICER} — then you may stop. (Block ${BLOCKS}/${GUARD_MAX_BLOCKS}; past the cap a stop is allowed as a stuck-safety.)"

      jq -n --arg r "$REASON" '{decision: "block", reason: $r}'
      exit 0
    fi
  fi
fi

# ============================================================
# 2. Session-end observability (only when NOT blocking)
# ============================================================
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SET "cabinet:session:ended:$OFFICER" "$TIMESTAMP" EX 86400 > /dev/null 2>&1

python3 "$CABINET_ROOT/framework/events/emitter.py" \
  session_ended "$OFFICER" \
  "{\"session_id\": \"$SESSION_ID\", \"ended_at\": \"$TIMESTAMP\"}" \
  2>/dev/null || true

echo "session-stop: $OFFICER session ended at $TIMESTAMP" >&2
exit 0
