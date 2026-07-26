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
# METER REWRITE (2026-07-26). The inline jq+bash arithmetic that used to live
# here under-reported by a MEASURED 16.0x across 279 real transcripts. Three
# independent faults, every one of them failing toward under-reporting:
#
#   1. `tail -100 | jq | tail -1` billed only the LAST assistant entry per Stop,
#      but a response contains one API call per tool round-trip — a 30-call turn
#      was billed as one. (4.4x of the gap.)
#   2. Cache tokens were charged at 0.25x/0.02x of the input rate instead of the
#      published 1.25x/0.1x. The `*fable*` arm directly above was correct, which
#      is how the opus/sonnet arms survived review. (3.8x.)
#   3. No concept of the 1-hour cache TTL (2.0x input); 100% of cache writes in
#      real transcripts are the 1h flavour. (1.1x.)
#   Plus: an unrecognized model fell through to the CHEAPEST row (Sonnet).
#
# Pricing now lives in exactly one place — framework/cost/meter.py — where the
# cache rates are DERIVED from the input rate by multiplier, so the 5x error is
# not expressible. Naive summing would have over-counted instead: the transcript
# repeats one assistant entry per CONTENT BLOCK (821 entries / 352 real API
# responses in a measured sample), so the parser dedupes by message.id and
# carries a per-session watermark to bill each response exactly once.
#
# Metering is now a WATCH, not a gate: the Captain removed the spend cap on
# 2026-07-26, so nothing here can refuse a call, and every failure mode is
# best-effort + exit 0.
if [ "$OFFICER" != "unknown" ] && [ "${CABINET_HOOK_TEST_MODE:-0}" != "1" ]; then
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
  if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    _METER_OUT=$(PYTHONPATH="$CABINET_ROOT" REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
      python3 -m framework.cost.record_turn \
        --transcript "$TRANSCRIPT_PATH" \
        --session "$SESSION_ID" \
        --officer "$OFFICER" \
        --project "${CABINET_ACTIVE_PROJECT:-}" 2>&1)
    [ -n "$_METER_OUT" ] && echo "$_METER_OUT" >&2
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
