#!/bin/bash
# on-post-tool-failure.sh — Fires after a tool call fails (CC v2.1.150 PostToolUseFailure hook)
# Captures tool failures for the learning loop and failure-pattern detector.
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name,
#     tool_name, tool_input, tool_use_id, error }
#
# Per docs: hook cannot block (the tool already failed). Used for logging and
# side effects. Returning decision:"block" surfaces stderr to Claude.
#
# We append failures to a dedicated JSONL so the existing failure-pattern
# detector (cabinet/scripts/lib/failure-patterns.py or similar) can replay them.

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Audit #12 (2026-07-07): docker-era `redis` default -> loopback (native Mac
# deployment; non-launchd sessions were silently no-op'ing telemetry).
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null)
TOOL_USE_ID=$(echo "$HOOK_INPUT" | jq -r '.tool_use_id // "unknown"' 2>/dev/null)
ERROR_MSG=$(echo "$HOOK_INPUT" | jq -r '.error // "unspecified"' 2>/dev/null | head -c 500)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

echo "on-post-tool-failure: $OFFICER tool=$TOOL_NAME error=${ERROR_MSG:0:100}" >&2

# Bump a Redis counter for the failure-pattern detector (daily, 7d TTL).
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  INCR "cabinet:tool-failures:$OFFICER:$(date -u +%Y-%m-%d)" \
  > /dev/null 2>&1 || true
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  EXPIRE "cabinet:tool-failures:$OFFICER:$(date -u +%Y-%m-%d)" 604800 \
  > /dev/null 2>&1 || true

# Append to failure JSONL for the learning loop replay path.
FAIL_LOG_DIR="${CABINET_EVENT_LOG_DIR:-$HOME/Library/Application Support/cabinet/events}"
mkdir -p "$FAIL_LOG_DIR" 2>/dev/null
FAIL_LOG="$FAIL_LOG_DIR/tool-failures-$(date -u +%Y-%m-%d).jsonl"

# Preserve full tool_input (truncated to keep file size sane) for replay.
TOOL_INPUT_COMPACT=$(echo "$HOOK_INPUT" | jq -c '.tool_input // {}' 2>/dev/null | head -c 2000)

jq -n \
  --arg officer "$OFFICER" \
  --arg tool "$TOOL_NAME" \
  --arg tool_use_id "$TOOL_USE_ID" \
  --arg session "$SESSION_ID" \
  --arg err "$ERROR_MSG" \
  --arg ts "$TIMESTAMP" \
  --argjson input "${TOOL_INPUT_COMPACT:-null}" \
  '{officer: $officer, tool_name: $tool, tool_use_id: $tool_use_id, session_id: $session, error: $err, tool_input: $input, observed_at: $ts}' \
  >> "$FAIL_LOG" 2>/dev/null || true

exit 0
