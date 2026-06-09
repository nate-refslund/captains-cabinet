#!/bin/bash
# on-config-change.sh — Fires when a config file changes mid-session (CC v2.1.150 ConfigChange hook)
# Captures config drift for the learning loop. Settings.json, plugin manifests, and
# skill registrations changing mid-session is signal that:
#   (a) the cabinet self-modified during runtime, or
#   (b) the captain hand-edited config — both worth recording.
#
# Receives on stdin:
#   { session_id, transcript_path, cwd, hook_event_name, config_source }
# config_source values: user_settings, project_settings, local_settings,
#                       policy_settings, skills
#
# Never blocks. Per docs, returning exit code 2 could block, but we always
# accept and log — the cabinet's safety enforcement lives in pre-tool-use.sh.

HOOK_INPUT=$(cat)
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-unknown}"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

CONFIG_SOURCE=$(echo "$HOOK_INPUT" | jq -r '.config_source // "unknown"' 2>/dev/null)
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Audit log
echo "on-config-change: $OFFICER config_source=$CONFIG_SOURCE at $TIMESTAMP" >&2

# Emit captain_decision_logged for the learning loop. Config drift = a meaningful
# state change worth replaying. We do NOT use a dedicated event type yet —
# emitter.py VALID_EVENT_TYPES is the gate; piggybacking on captain_decision_logged
# would mis-classify. So we append to a dedicated config-drift JSONL log instead.
DRIFT_LOG_DIR="${CABINET_EVENT_LOG_DIR:-$HOME/Library/Application Support/cabinet/events}"
mkdir -p "$DRIFT_LOG_DIR" 2>/dev/null
DRIFT_LOG="$DRIFT_LOG_DIR/config-drift-$(date -u +%Y-%m-%d).jsonl"

jq -n \
  --arg officer "$OFFICER" \
  --arg source "$CONFIG_SOURCE" \
  --arg session "$SESSION_ID" \
  --arg ts "$TIMESTAMP" \
  '{officer: $officer, config_source: $source, session_id: $session, observed_at: $ts}' \
  >> "$DRIFT_LOG" 2>/dev/null || true

exit 0
