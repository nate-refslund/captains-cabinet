#!/bin/bash
# on-instructions-loaded.sh — Fires when CLAUDE.md / .claude/rules/*.md loads (CC v2.1.150 InstructionsLoaded hook)
# Pure observability — per docs, this hook has NO decision control.
#
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name,
#     file_path, memory_type, load_reason,
#     globs?, trigger_file_path?, parent_file_path? }
# memory_type: User, Project, Local, Managed
# load_reason: session_start, nested_traversal, path_glob_match, include, compact
#
# Useful for: detecting which rules were loaded when, tracing nested CLAUDE.md
# traversals across worktrees, and validating that the preset addenda made it
# into the runtime constitution.

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

FILE_PATH=$(echo "$HOOK_INPUT" | jq -r '.file_path // "unknown"' 2>/dev/null)
MEMORY_TYPE=$(echo "$HOOK_INPUT" | jq -r '.memory_type // "unknown"' 2>/dev/null)
LOAD_REASON=$(echo "$HOOK_INPUT" | jq -r '.load_reason // "unknown"' 2>/dev/null)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

echo "on-instructions-loaded: $OFFICER file=$(basename "$FILE_PATH") memory_type=$MEMORY_TYPE reason=$LOAD_REASON" >&2

# Append to an instructions-load JSONL log so the learning loop can answer
# "which rules were active in session X?" deterministically.
LOAD_LOG_DIR="${CABINET_EVENT_LOG_DIR:-/tmp/cabinet-events}"
mkdir -p "$LOAD_LOG_DIR" 2>/dev/null
LOAD_LOG="$LOAD_LOG_DIR/instructions-loaded-$(date -u +%Y-%m-%d).jsonl"

jq -n \
  --arg officer "$OFFICER" \
  --arg file "$FILE_PATH" \
  --arg memtype "$MEMORY_TYPE" \
  --arg reason "$LOAD_REASON" \
  --arg session "$SESSION_ID" \
  --arg ts "$TIMESTAMP" \
  '{officer: $officer, file_path: $file, memory_type: $memtype, load_reason: $reason, session_id: $session, observed_at: $ts}' \
  >> "$LOAD_LOG" 2>/dev/null || true

exit 0
