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
# Audit #12 (2026-07-07): docker-era `redis` default -> loopback (native Mac
# deployment); the Stop-guard + cost ledger were no-ops in non-launchd sessions.
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# ============================================================
# 0. COST LEDGER (audit #13, germline window 2 2026-07-07)
# ============================================================
# Moved here from stop-hook.sh, which is wired to NO hook event (Stop ->
# THIS script) — the only writer of cabinet:cost:tokens:* was dead, so
# cost-report.sh / cron/cost-summary.sh / cost-dashboard.sh / the
# mcp-server cost surface all read an empty ledger. Runs BEFORE the
# stop-guard so every Stop event records the turn (guard-blocked stops
# included); writes only Redis + nothing on stdout (the guard's
# decision:block JSON protocol stays clean). Officer-gated like the guard;
# CABINET_HOOK_TEST_MODE=1 skips it (harnesses must not write production
# cost keys — feedback_test_harness_production_sinks.md).
if [ "$OFFICER" != "unknown" ] && [ "${CABINET_HOOK_TEST_MODE:-0}" != "1" ]; then
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
  if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    # Last assistant entry with usage data; usage + model from the same turn.
    LAST_ENTRY=$(tail -100 "$TRANSCRIPT_PATH" | jq -c 'select(.type == "assistant" and .message.usage != null) | {usage: .message.usage, model: .message.model}' 2>/dev/null | tail -1)

    if [ -n "$LAST_ENTRY" ] && [ "$LAST_ENTRY" != "null" ]; then
      INPUT_TOKENS=$(echo "$LAST_ENTRY" | jq -r '.usage.input_tokens // 0' 2>/dev/null)
      OUTPUT_TOKENS=$(echo "$LAST_ENTRY" | jq -r '.usage.output_tokens // 0' 2>/dev/null)
      CACHE_WRITE=$(echo "$LAST_ENTRY" | jq -r '.usage.cache_creation_input_tokens // 0' 2>/dev/null)
      CACHE_READ=$(echo "$LAST_ENTRY" | jq -r '.usage.cache_read_input_tokens // 0' 2>/dev/null)
      MODEL=$(echo "$LAST_ENTRY" | jq -r '.model // "unknown"' 2>/dev/null)

      # Microdollars for integer math (rates: see stop-hook.sh provenance).
      case "$MODEL" in
        *fable*)
          COST_MICRO=$(( INPUT_TOKENS * 10 + OUTPUT_TOKENS * 50 + CACHE_WRITE * 12500 / 1000 + CACHE_READ * 1000 / 1000 ))
          ;;
        *opus*)
          COST_MICRO=$(( INPUT_TOKENS * 15 + OUTPUT_TOKENS * 75 + CACHE_WRITE * 3750 / 1000 + CACHE_READ * 300 / 1000 ))
          ;;
        *)
          COST_MICRO=$(( INPUT_TOKENS * 3 + OUTPUT_TOKENS * 15 + CACHE_WRITE * 750 / 1000 + CACHE_READ * 60 / 1000 ))
          ;;
      esac

      CONTEXT_TOKENS=$(( INPUT_TOKENS + CACHE_READ + CACHE_WRITE ))
      CONTEXT_WINDOW=${CONTEXT_WINDOW_SIZE:-1000000}
      CONTEXT_PCT=0
      [ "$CONTEXT_WINDOW" -gt 0 ] 2>/dev/null && CONTEXT_PCT=$(( CONTEXT_TOKENS * 100 / CONTEXT_WINDOW ))

      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HSET "cabinet:cost:tokens:$OFFICER" \
        last_input "$INPUT_TOKENS" \
        last_output "$OUTPUT_TOKENS" \
        last_cache_write "$CACHE_WRITE" \
        last_cache_read "$CACHE_READ" \
        last_cost_micro "$COST_MICRO" \
        last_model "$MODEL" \
        last_context_tokens "$CONTEXT_TOKENS" \
        last_context_pct "$CONTEXT_PCT" \
        last_updated "$TIMESTAMP" \
        > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "cabinet:cost:tokens:$OFFICER" 86400 > /dev/null 2>&1

      # Daily totals (FW-072 pool-mode field scheme preserved: per-project
      # fields when CABINET_ACTIVE_PROJECT is set, legacy fields otherwise —
      # one HINCRBY per Stop per dimension, no double-count).
      TODAY=$(date -u +%Y-%m-%d)
      PROJ="${CABINET_ACTIVE_PROJECT:-}"
      if [ -n "$PROJ" ]; then
        FIELD_PREFIX="${OFFICER}_${PROJ}"
      else
        FIELD_PREFIX="${OFFICER}"
      fi
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HINCRBY "cabinet:cost:tokens:daily:$TODAY" \
        "${FIELD_PREFIX}_input" "$INPUT_TOKENS" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HINCRBY "cabinet:cost:tokens:daily:$TODAY" \
        "${FIELD_PREFIX}_output" "$OUTPUT_TOKENS" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HINCRBY "cabinet:cost:tokens:daily:$TODAY" \
        "${FIELD_PREFIX}_cache_write" "$CACHE_WRITE" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HINCRBY "cabinet:cost:tokens:daily:$TODAY" \
        "${FIELD_PREFIX}_cache_read" "$CACHE_READ" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HINCRBY "cabinet:cost:tokens:daily:$TODAY" \
        "${FIELD_PREFIX}_cost_micro" "$COST_MICRO" > /dev/null 2>&1
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "cabinet:cost:tokens:daily:$TODAY" 172800 > /dev/null 2>&1
    fi
  fi
fi

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
