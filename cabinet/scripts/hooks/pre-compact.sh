#!/bin/bash
# pre-compact.sh — Captures officer operational state BEFORE context compaction
# Writes to local file (fast, never fails) + PostgreSQL (persistent, async-tolerant)
# The post-compact hook reads this state and injects it back into context.

OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Host note (2026-07-07, same fix as record-experience.sh): the legacy
# `redis` default silently failed on Mac-native (the Docker service name
# does not resolve), so the state reads below returned empty. localhost
# resolves on Mac AND Docker exports REDIS_HOST=redis-<slug>, so both work.
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

STATE_DIR="$CABINET_ROOT/instance/memory/tier2/$OFFICER"
STATE_FILE="$STATE_DIR/.session-state.json"
mkdir -p "$STATE_DIR"

# ============================================================
# 1. Collect Redis operational state
# ============================================================
TOOL_CALLS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:toolcalls:$OFFICER" 2>/dev/null | grep -o '[0-9]*' || echo "0")
. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh" 2>/dev/null
TRIGGER_COUNT=$(trigger_count "$OFFICER" 2>/dev/null | grep -o '[0-9]*' || echo "0")

# Collect schedule timestamps — use jq for safe JSON construction
SCHEDULE_JSON="{}"
while read -r key; do
  [ -z "$key" ] && continue
  task="${key##*:}"
  val=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$key" 2>/dev/null)
  SCHEDULE_JSON=$(echo "$SCHEDULE_JSON" | jq --arg k "$task" --arg v "$val" '. + {($k): $v}')
done < <(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "cabinet:schedule:last-run:$OFFICER:*" 2>/dev/null)

# ============================================================
# 2. Capture a narrative excerpt — the officer's OWN curated working
#    memory — so post-compact can re-surface it into context. Claude
#    Code's native compaction summary is best-effort; this is a
#    deterministic floor under it (the working notes + .remember buffer
#    this officer maintains). All values reach jq via --arg (string),
#    never the filter body, so filenames/content cannot inject.
# ============================================================
NOTES_FILE="$STATE_DIR/working-notes.md"
NARRATIVE=""
[ -f "$NOTES_FILE" ] && NARRATIVE="$(tail -c 1500 "$NOTES_FILE")"
REMEMBER_NOW="$CABINET_ROOT/.remember/now.md"
if [ -f "$REMEMBER_NOW" ]; then
  NARRATIVE="$NARRATIVE

--- .remember/now.md (live buffer) ---
$(tail -c 1000 "$REMEMBER_NOW")"
fi

# ============================================================
# 3. Write local state file using jq (always valid JSON)
# ============================================================
jq -n \
  --arg officer "$OFFICER" \
  --arg captured_at "$TIMESTAMP" \
  --arg narrative "$NARRATIVE" \
  --argjson tool_calls "${TOOL_CALLS:-0}" \
  --argjson pending_triggers "${TRIGGER_COUNT:-0}" \
  --argjson schedules "$SCHEDULE_JSON" \
  '{officer: $officer, captured_at: $captured_at, tool_calls: $tool_calls, pending_triggers: $pending_triggers, schedules: $schedules, narrative_excerpt: $narrative}' \
  > "$STATE_FILE"

# ============================================================
# 4. Store to PostgreSQL for cross-session persistence (best-effort)
# ============================================================
# Source env if NEON_CONNECTION_STRING not already set
[ -z "$NEON_CONNECTION_STRING" ] && source "$CABINET_ROOT/cabinet/.env" 2>/dev/null

if [ -n "$NEON_CONNECTION_STRING" ]; then
  # NOTES_FILE already set above (section 2); same path, reused here.
  WORKING_NOTES=""
  [ -f "$NOTES_FILE" ] && WORKING_NOTES=$(tail -c 3000 "$NOTES_FILE")

  # Use psql variables (:'var' syntax) via heredoc for injection-safe parameterized insert
  # Note: :'var' only works via stdin/heredoc, NOT with -c flag
  #
  # Async but OBSERVED (P1b, 2026-07-07): the old form was a bare
  # `psql ... 2>/dev/null ... &` — fire-and-forget, so every failed insert
  # vanished (zero session_memories liveness, per the memory audit). The
  # background SUBSHELL below keeps compaction non-blocking but captures the
  # exit: on failure it appends one line to this officer's
  # .session-insert-failures.log AND INCRs
  # cabinet:memory:session_insert_failures — the counter the daily falsifier
  # line carries (falsifier-report.py), so silent loss is now measurable.
  (
    if ! psql "$NEON_CONNECTION_STRING" -q \
      -v officer="$OFFICER" \
      -v content="$WORKING_NOTES" \
      -v state="$(cat "$STATE_FILE")" \
      2>/dev/null <<'SQLEOF'
INSERT INTO session_memories (officer, snapshot_type, content, structured_state) VALUES (:'officer', 'pre_compact', :'content', :'state'::jsonb);
SQLEOF
    then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) officer=$OFFICER session_memories INSERT failed (captured by pre-compact wrapper)" \
        >> "$STATE_DIR/.session-insert-failures.log" 2>/dev/null
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INCR "cabinet:memory:session_insert_failures" > /dev/null 2>&1
    fi
  ) &
fi

# ============================================================
# 5. Queue the narrative excerpt into Cabinet Memory (P1b, 2026-07-07)
# ============================================================
# session_memory was a documented source_type with zero rows ever — the
# officer's own curated pre-compaction narrative never reached semantic
# memory. Queue it on the embed stream (memory-worker embeds + upserts).
#   source_id = <officer>-<captured_at> (unique per compaction)
# Best-effort: empty narrative is refused by memory_queue_embed itself;
# any failure is swallowed — this hook must NEVER block compaction.
(
  source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh" 2>/dev/null || exit 0
  declare -f memory_queue_embed > /dev/null || exit 0
  SM_META=$(jq -nc --arg trust "officer" --arg writer "$OFFICER" \
    '{snapshot_type: "pre_compact", trust: $trust, writer: $writer}')
  memory_queue_embed "session_memory" "${OFFICER}-${TIMESTAMP}" \
    "$OFFICER" "" "$NARRATIVE" "$SM_META" "$TIMESTAMP"
) > /dev/null 2>&1 || true

# Always exit 0 — hooks should never block
exit 0
