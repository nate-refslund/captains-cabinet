#!/bin/bash
# start-officer-mac.sh — Start an Officer Claude Code session on Mac native.
#
# Invoked by LaunchAgent (com.cabinet.officer.<role>.plist). Reads officer
# capabilities, builds the right Claude Code invocation flags (telegram_bot
# gate + cua-driver MCP overlay), starts a detached tmux session, and launches
# claude inside.
#
# Per Spec 059 v1.1 Checkpoint 2.7 + CTO v1.1 #4 (tmux new-session -d) + Spec
# 060 v1.1 (telegram_bot capability gate) + Spec 061 v1.2 (drives_computer
# capability gate with jq deep-merge per CTO v1.1 #1 CRITICAL).
#
# Usage (LaunchAgent calls this):
#   /bin/bash $REPO_ROOT/cabinet/scripts/start-officer-mac.sh <officer>

set -euo pipefail

OFFICER="${1:?Usage: start-officer-mac.sh <officer>}"
REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
LOGS_DIR="$HOME/Library/Logs/cabinet"
SESSION_NAME="officer-$OFFICER"
MODEL="${CABINET_MODEL:-claude-sonnet-4-6}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

mkdir -p "$LOGS_DIR"

cd "$REPO_ROOT"

# Source .env (TELEGRAM tokens, NEON_CONNECTION_STRING, etc.)
if [ -f "cabinet/.env" ]; then
  set -a; source cabinet/.env 2>/dev/null; set +a
fi

# Assemble runtime constitution + safety + preset (idempotent)
bash cabinet/scripts/load-preset.sh 2>&1 | tail -3 >&2

# ===========================================================
# Capability resolution (Spec 060 + Spec 061 capability gates)
# ===========================================================
# Returns "true" if officer has the capability, "false" otherwise
read_capability() {
  local role="$1" cap="$2"
  if grep -E "^${role}:${cap}$" cabinet/officer-capabilities.conf > /dev/null 2>&1; then
    echo "true"
  else
    echo "false"
  fi
}

HAS_TELEGRAM=$(read_capability "$OFFICER" "telegram_bot")
HAS_CUA_DRIVER=$(read_capability "$OFFICER" "drives_computer")

# ===========================================================
# MCP config — framework .mcp.json + (if drives_computer) overlay
# ===========================================================
# Per Spec 061 v1.1 CTO #1 CRITICAL: jq DEEP-MERGE preserving framework mcpServers.
# Shallow merge would silently overwrite notion/linear/neon/library with overlay-only.
MERGED_MCP_PATH="/tmp/cabinet-merged-mcp-${OFFICER}.json"
if [ "$HAS_CUA_DRIVER" = "true" ] && [ -f "instance/agents/$OFFICER/mcp.json" ]; then
  jq -s '.[0] as $base | .[1] as $overlay
         | $base * $overlay
         | .mcpServers = ($base.mcpServers + $overlay.mcpServers)' \
     .mcp.json "instance/agents/$OFFICER/mcp.json" \
     > "$MERGED_MCP_PATH"
  MCP_FLAG="--mcp-config $MERGED_MCP_PATH"
else
  MCP_FLAG=""  # Claude Code reads .mcp.json by default
fi

# ===========================================================
# Telegram bot token resolution
# ===========================================================
# Lead-only (per Spec 060 v1.1): only officers with telegram_bot=true get a bot token.
# Non-Lead officers run Telegram-dark (no --channels plugin:telegram).
TELEGRAM_FLAG=""
if [ "$HAS_TELEGRAM" = "true" ]; then
  OFFICER_UPPER=$(echo "$OFFICER" | tr '[:lower:]' '[:upper:]')
  TOKEN_VAR="TELEGRAM_${OFFICER_UPPER}_TOKEN"
  BOT_TOKEN="${!TOKEN_VAR:-}"
  if [ -n "$BOT_TOKEN" ]; then
    export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
    TELEGRAM_FLAG="--channels plugin:telegram@claude-plugins-official"
  else
    echo "start-officer-mac.sh: telegram_bot=true but $TOKEN_VAR not set in env" >&2
  fi
fi

# ===========================================================
# Heartbeat — SETEX 900s TTL per Spec 064 v1.1 CTO #3
# ===========================================================
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%s)" > /dev/null 2>&1 || true

# Export OFFICER_NAME for hooks (stop-hook.sh + post-tool-use.sh etc.)
export OFFICER_NAME="$OFFICER"

# ===========================================================
# tmux session + claude launch
# ===========================================================
# tmux new-session -d creates detached (no terminal attached) — per CTO v1.1 #4
# LaunchAgent doesn't have a TTY, so attached tmux would fail to start.

# Kill any existing session for this officer (idempotent restart)
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Start fresh detached session
tmux new-session -d -s "$SESSION_NAME" -x 220 -y 50

# Build the claude invocation
CLAUDE_CMD="cd $REPO_ROOT && claude --model $MODEL $MCP_FLAG $TELEGRAM_FLAG --dangerously-skip-permissions"

# Send the launch command into the tmux session
tmux send-keys -t "$SESSION_NAME" "$CLAUDE_CMD" C-m

# ===========================================================
# Wait for prompt / settings.json prompts (PROMPT_REGEX from master start-officer.sh)
# ===========================================================
PROMPT_REGEX="(I am using this for local development|Continue (as-is|conversation)|Summari[sz]e|Trust the (files|hooks)|Do you trust|Choose your theme|Welcome to Claude|edit .*\.claude/settings\.json|allow .*\.claude/settings\.json|Edit .*settings\.json|update .*\.claude/settings|Allow Claude to (edit|modify))"
DEADLINE=$(($(date +%s) + 45))

while [ $(date +%s) -lt $DEADLINE ]; do
  sleep 2
  pane_output=$(tmux capture-pane -t "$SESSION_NAME" -p 2>/dev/null | tail -30)
  if echo "$pane_output" | grep -qE "$PROMPT_REGEX"; then
    # C-m carriage return (per master start-officer.sh fix)
    tmux send-keys -t "$SESSION_NAME" C-m
    sleep 1
  elif echo "$pane_output" | grep -qE "(Try.*for new ideas|tab.*complete|Bypassing Permissions|^\s*>\s*$)"; then
    break
  fi
done

# Brief settle
sleep 2

# Send boot prompt — tells the officer to initialize + announce
tmux send-keys -t "$SESSION_NAME" "You are $OFFICER. Read your role definition at .claude/agents/$OFFICER.md and your session start checklist. Read your foundation skills in memory/skills/. Read your tier 2 notes in instance/memory/tier2/$OFFICER/. Then announce yourself on the warroom: bash $REPO_ROOT/cabinet/scripts/send-to-group.sh '<b>$OFFICER online (Mac native).</b> Session started. Checking for pending work.' — then check for pending triggers and overdue work immediately." Enter

echo "start-officer-mac.sh: $OFFICER started in tmux session $SESSION_NAME (model=$MODEL, telegram=$HAS_TELEGRAM, cua_driver=$HAS_CUA_DRIVER)"

# LaunchAgent keeps the script alive (KeepAlive) — wait forever so launchd
# treats this as a long-running process. Without this, launchd KeepAlive
# loop would restart immediately on script exit.
while true; do
  # Re-stamp heartbeat every 10 min (TTL is 15 min so we have margin)
  sleep 600
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%s)" > /dev/null 2>&1 || true
done
